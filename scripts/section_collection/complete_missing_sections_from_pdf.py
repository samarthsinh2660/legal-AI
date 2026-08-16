"""Fill genuinely source-missing Section bodies from India Code's own PDF.

Scope: only Sections confirmed empty at the primary AJAX source AND not
explained by a real non-commencement (see act:1978's Part IA, left alone
deliberately — filling not-yet-force text would misrepresent current law
regardless of source). See docs/superpowers/specs/2026-08-15-section-body-fetch-design.md.

Extraction uses Gemini (an LLM) only to *locate and copy* each section's
verbatim text out of the PDF's raw extracted text — not to generate or
paraphrase. Every result is validated (non-empty, plausible length, no
refusal wording) before being written, and provenance is set to make it
clear this text came from the PDF fallback + AI-assisted extraction, not
the primary AJAX source.

Run: .venv/bin/python -m scripts.section_collection.complete_missing_sections_from_pdf
"""

from __future__ import annotations

import io
import json
import os
import re
import time

import pypdf
from google import genai

from legal_ai.ingestion.schema import content_hash
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import get_document, upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.sources.http import polite_get

# Part IA (Arbitration Council of India) was enacted but never brought
# into force — no commencement notification exists. Filling this with
# real text would misrepresent it as current law. Left alone on purpose.
EXCLUDE_ACT_IDS = {"act:1978"}

# Tried in order; a 503 (overload) or other transient failure on one
# falls through to the next rather than blocking the whole run on
# whichever model is busy right now. All confirmed reachable with this
# key before use.
MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-3-flash-preview"]


def get_pdf_url(act_source_url: str) -> str | None:
    html = polite_get(act_source_url).text
    match = re.search(r'href="(/bitstream/[^"]*\.pdf)"', html, re.IGNORECASE)
    if match is None:
        return None
    return "https://www.indiacode.nic.in" + match.group(1)


def extract_pdf_text(pdf_url: str) -> str:
    response = polite_get(pdf_url)
    reader = pypdf.PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() for page in reader.pages)


def ask_gemini_for_sections(client: genai.Client, act_title: str, pdf_text: str, numbers: list[str]) -> dict:
    prompt = f"""You are extracting text from an official Indian legal Act PDF — {act_title}.

Below is the raw text extracted from the PDF (page breaks and formatting
may be imperfect). For each of these section numbers: {numbers}

Find that section's real operative body text (not its table-of-contents
entry, not any annexed Schedule with similarly-numbered clauses) and
return it verbatim — copy exactly what is written, do not summarize,
paraphrase, correct, or add anything. Exclude the leading section number
and heading line itself (e.g. for "43A. Some Heading.—(1) Text starts
here", return only "(1) Text starts here...", not the "43A. Some
Heading.—" part) — the number and heading are already stored separately;
only the body text is needed. If a section number genuinely does
not appear with real body text anywhere in this document, use null for
its value.

Return ONLY valid JSON, no markdown fences, no commentary:
{{"<number>": "<verbatim text or null>", ...}}

PDF TEXT:
{pdf_text}
"""
    last_error: Exception | None = None
    for model in MODELS:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                text = resp.text.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\n|\n```$", "", text)
                return json.loads(text)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                # 429 is the free-tier per-minute token quota — a fixed
                # short sleep isn't enough headroom, and switching models
                # doesn't help since they share the same account quota.
                # Wait out a full window before retrying.
                if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                    time.sleep(65)
                elif attempt == 0:
                    time.sleep(5)
        # this model failed twice — move on to the next one immediately
    raise last_error if last_error is not None else RuntimeError("no models configured")


def _is_valid_extraction(text: object) -> bool:
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if len(stripped) < 15:
        return False
    refusal_markers = ["cannot find", "not found", "does not appear", "i could not", "unable to locate"]
    return not any(marker in stripped.lower() for marker in refusal_markers)


def run() -> None:
    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
    conn = get_connection()

    act_rows = conn.execute(
        """
        SELECT s.act_id, a.title, a.provenance->'source'->>'url' AS url
        FROM (SELECT DISTINCT act_id FROM documents WHERE document_type='section' AND full_text='') s
        JOIN documents a ON a.document_id = s.act_id
        ORDER BY s.act_id
        """
    ).fetchall()

    total_filled = 0
    total_skipped = 0
    for act_id, act_title, source_url in act_rows:
        if act_id in EXCLUDE_ACT_IDS:
            print(f"{act_id}: SKIPPED (excluded — not-yet-commenced provisions)")
            continue

        rows = conn.execute(
            "SELECT document_id FROM documents WHERE document_type='section' AND act_id=%s AND full_text=''",
            (act_id,),
        ).fetchall()
        numbers = [doc_id.rsplit(":sec-", 1)[-1] for (doc_id,) in rows]

        pdf_url = get_pdf_url(source_url)
        if pdf_url is None:
            print(f"{act_id}: SKIPPED (no PDF link found)")
            total_skipped += len(numbers)
            continue

        pdf_text = extract_pdf_text(pdf_url)
        try:
            results = ask_gemini_for_sections(client, act_title, pdf_text, numbers)
        except Exception as exc:  # noqa: BLE001
            # One Act exhausting every model/retry shouldn't crash the rest
            # of the run — it just stays empty and gets picked up next time
            # (resumable by construction, same as fill_section_bodies.py).
            print(f"{act_id}: FAILED — {exc!r}")
            total_skipped += len(numbers)
            continue

        filled = 0
        for number in numbers:
            text = results.get(number)
            if not _is_valid_extraction(text):
                total_skipped += 1
                continue
            document_id = f"{act_id}:sec-{number}"
            doc = get_document(conn, document_id)
            if doc is None:
                total_skipped += 1
                continue
            doc.full_text = text.strip()
            doc.content_hash = content_hash(doc.full_text)
            doc.provenance = Provenance(
                source=SourceRef(
                    name="India Code (PDF, AI-assisted extraction)",
                    url=pdf_url,
                    document_id=document_id,
                    source_type="primary",
                ),
                retrieved_at=doc.provenance.retrieved_at,
                licence=doc.provenance.licence,
                attribution_required=doc.provenance.attribution_required,
            )
            vector = embed(doc.full_text)
            upsert_document(conn, doc, embedding=vector)
            filled += 1

        total_filled += filled
        print(f"{act_id}: filled {filled}/{len(numbers)}")

    print(f"\nDONE. Total filled: {total_filled}  Total skipped: {total_skipped}")
    conn.close()


if __name__ == "__main__":
    run()
