"""Fill real section body text for every India Code Section still empty.

Resumable by construction: it only ever queries for Sections with
full_text='' and re-running just picks up whatever's left, so a crash
loses time, not progress. See
docs/superpowers/specs/2026-08-15-section-body-fetch-design.md

Every failure (per-section fetch error, missing actid/sectionId, act page
fetch error) is logged to section_fill_errors.csv next to this script,
with the document_id, act_id, and the exact reason, so failures can be
inspected and re-driven later instead of just seeing a count.

Run: .venv/bin/python -m scripts.section_collection.fill_section_bodies
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

from legal_ai.ingestion.india_code.section_body import extract_section_ajax_ids, fetch_section_text
from legal_ai.ingestion.schema import content_hash
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.chunk_store import chunk_and_store
from legal_ai.knowledge.static.store import get_document, upsert_document
from legal_ai.sources.http import polite_get

ERROR_LOG_PATH = Path(__file__).with_name("section_fill_errors.csv")


def _log_error(document_id: str, act_id: str, reason: str) -> None:
    is_new = not ERROR_LOG_PATH.exists()
    with ERROR_LOG_PATH.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["document_id", "act_id", "reason"])
        writer.writerow([document_id, act_id, reason])


def run() -> None:
    conn = get_connection()
    act_rows = conn.execute(
        """
        SELECT DISTINCT s.act_id, a.provenance->'source'->>'url' AS url
        FROM documents s
        JOIN documents a ON a.document_id = s.act_id
        WHERE s.document_type = 'section' AND s.full_text = ''
        ORDER BY s.act_id
        """
    ).fetchall()
    total_acts = len(act_rows)
    print(f"Acts with empty sections: {total_acts}", flush=True)

    total_filled = 0
    total_failed = 0
    start = time.monotonic()

    for i, (act_id, source_url) in enumerate(act_rows, start=1):
        rows = conn.execute(
            "SELECT document_id FROM documents WHERE document_type='section' AND act_id=%s AND full_text=''",
            (act_id,),
        ).fetchall()

        # India Code sometimes serves a real 200 response that just lacks the
        # section markup we expect (a soft block/rate-limit, not a network
        # error polite_get's retries would catch) — seen for real during the
        # server-side run: act pages fetched cleanly earlier that briefly
        # returned 0 extractable sections, then worked fine again minutes
        # later. Retry a few times with a real pause before giving up, since
        # marking every section in the Act failed loses far more than one
        # request's worth of work.
        ajax_ids: dict[str, tuple[str, str]] = {}
        fetch_error: Exception | None = None
        for attempt in range(3):
            try:
                act_html = polite_get(source_url).text
                ajax_ids = extract_section_ajax_ids(act_html)
                fetch_error = None
            except Exception as exc:  # noqa: BLE001
                fetch_error = exc
                ajax_ids = {}
            if ajax_ids or not rows:
                break
            time.sleep(30 * (attempt + 1))

        if fetch_error is not None:
            print(f"[{i}/{total_acts}] {act_id}: FAILED to fetch/parse Act page: {fetch_error!r}", flush=True)
            _log_error(act_id, act_id, f"act page fetch/parse failed: {fetch_error!r}")
            continue
        if not ajax_ids and rows:
            print(f"[{i}/{total_acts}] {act_id}: FAILED — 0 sections extracted after 3 attempts", flush=True)
            _log_error(act_id, act_id, "0 sections extracted from Act page after 3 attempts (possible soft block)")
            continue

        filled = 0
        for (document_id,) in rows:
            number = document_id.rsplit(":sec-", 1)[-1]
            ids = ajax_ids.get(number)
            if ids is None:
                total_failed += 1
                _log_error(document_id, act_id, "no actid/sectionId found on Act page")
                continue
            actid, section_id = ids
            text = None
            section_error: Exception | None = None
            for attempt in range(2):
                try:
                    text = fetch_section_text(actid, section_id)
                    section_error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    section_error = exc
                    time.sleep(15)
            if section_error is not None or text is None:
                total_failed += 1
                _log_error(document_id, act_id, f"SectionPageContent fetch failed: {section_error!r}")
                continue

            doc = get_document(conn, document_id)
            if doc is None:
                total_failed += 1
                _log_error(document_id, act_id, "document vanished from DB mid-run")
                continue
            doc.full_text = text
            doc.content_hash = content_hash(text)
            vector = embed(text) if text.strip() else None
            upsert_document(conn, doc, embedding=vector)
            chunk_and_store(
                conn, doc.document_id, doc.full_text, doc.document_type,
                title=doc.title,
            )
            filled += 1

        total_filled += filled
        elapsed_min = (time.monotonic() - start) / 60
        print(
            f"[{i}/{total_acts}] {act_id}: filled {filled}/{len(rows)}  "
            f"(running total: {total_filled} filled, {total_failed} failed, {elapsed_min:.1f} min elapsed)",
            flush=True,
        )

    print(f"\nDONE. Total filled: {total_filled}  Total failed: {total_failed}", flush=True)
    conn.close()


if __name__ == "__main__":
    run()
