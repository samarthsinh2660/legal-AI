# scripts/ingest_ipc_crpc.py
"""Ingest the Indian Penal Code 1860 and the Code of Criminal Procedure 1973.

Both were repealed on 1 July 2024 but still govern every offence committed
before that date, so they are live law the corpus has to hold.

Not from India Code: its REST API returns only the 2023 replacements for
these subjects and, for the old codes, nothing but amendment Acts by title.
The text therefore comes from a community compilation
(github.com/civictech-India/Indian-Law-Penal-Code-Json), which is why
provenance is source_type="research" — the same tier as Indian Kanoon —
and not "primary".

Run: .venv/bin/python -m scripts.ingest_ipc_crpc
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.ingestion.verification_gate import verify_batch
from legal_ai.knowledge.static.chunk_store import chunk_and_store
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef

_RAW = "https://raw.githubusercontent.com/civictech-India/Indian-Law-Penal-Code-Json/main"

# Act ids are words, not numbers: every other Act id in the corpus is
# `act:<India Code numeric handle>`, so a word id cannot collide with a
# handle India Code may later assign to these codes.
CODES = (
    ("act:ipc-1860", "The Indian Penal Code, 1860", f"{_RAW}/ipc.json", "Section"),
    ("act:crpc-1973", "The Code of Criminal Procedure, 1973", f"{_RAW}/crpc.json", "section"),
)


def _provenance(source_url: str, document_id: str) -> Provenance:
    return Provenance(
        source=SourceRef(
            name=(
                "civictech-India/Indian-Law-Penal-Code-Json "
                "(community compilation, not an official government source)"
            ),
            url=source_url,
            document_id=document_id,
            source_type="research",
        ),
        retrieved_at=datetime.now(timezone.utc),
        licence="No licence stated in the source repository",
        attribution_required=True,
    )


def _build(act_id: str, act_title: str, url: str, key: str):
    """Returns (act, sections, skipped) for one code.

    Section numbers are a mix of int and str in the source — the
    letter-suffixed ones (498A, 120B) are strings — so every id is built
    from str(). Sections with an empty body are skipped rather than stored:
    an empty row is unretrievable and would read as coverage we do not have.
    """
    with urllib.request.urlopen(url) as response:
        entries = json.load(response)

    sections: list[CanonicalDocument] = []
    skipped: list[str] = []
    now = datetime.now(timezone.utc)
    for entry in entries:
        number = str(entry[key]).strip()
        body = (entry["section_desc"] or "").strip()
        if not body:
            skipped.append(number)
            continue
        section_id = f"{act_id}:sec-{number}"
        sections.append(
            CanonicalDocument(
                document_id=section_id,
                document_type="section",
                title=entry["section_title"].strip(),
                act_id=act_id,
                full_text=body,
                content_hash=content_hash(body),
                provenance=_provenance(url, section_id),
                ingested_at=now,
            )
        )

    # The source has no Act-level text, so the Act document is its table of
    # contents: enough to match the Act by name, without restating section
    # bodies that are embedded separately.
    act_text = f"{act_title}\n\n" + "\n".join(
        f"Section {s.document_id.rsplit('sec-', 1)[1]}. {s.title}" for s in sections
    )
    act = CanonicalDocument(
        document_id=act_id,
        document_type="act",
        title=act_title,
        full_text=act_text,
        content_hash=content_hash(act_text),
        provenance=_provenance(url, act_id),
        ingested_at=now,
    )
    return act, sections, skipped


def main() -> None:
    conn = get_connection()
    driver = get_driver()

    for act_id, act_title, url, key in CODES:
        act, sections, skipped = _build(act_id, act_title, url, key)
        print(f"{act_title}: {len(sections)} sections parsed, {len(skipped)} skipped {skipped}")

        docs = [act, *sections]
        verification = verify_batch(docs, text_check=lambda d: bool(d.full_text.strip()))
        print(f"  verification passed={verification.passed} sampled={verification.sampled_count}")
        if not verification.passed:
            print(f"  FAILED: {verification.failed_document_ids}")
            continue

        writes = 0
        for doc in docs:
            if upsert_document(conn, doc, embedding=embed(doc.full_text)):
                chunk_and_store(
                    conn, doc.document_id, doc.full_text, doc.document_type,
                    title=doc.title,
                )
                writes += 1
        for section in sections:
            write_act_section(driver, act, section)
        print(f"  stored {writes} documents, {len(sections)} CONTAINS edges")

    driver.close()
    conn.close()


if __name__ == "__main__":
    main()
