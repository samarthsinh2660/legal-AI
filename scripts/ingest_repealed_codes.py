# scripts/ingest_repealed_codes.py
"""Ingest the three criminal codes repealed on 1 July 2024: the Indian
Penal Code 1860, the Code of Criminal Procedure 1973 and the Indian
Evidence Act 1872.

All three still govern every offence and proceeding begun before that
date, so they are live law the corpus has to hold.

Not from India Code: its REST API returns only the 2023 replacements for
these subjects and, for the old codes, nothing but amendment Acts by title.
The text therefore comes from a community compilation
(github.com/civictech-India/Indian-Law-Penal-Code-Json), which is why
provenance is source_type="research" — the same tier as Indian Kanoon —
and not "primary".

Where that compilation has an empty body, PATCHED_SECTIONS supplies the
text from a named source with its own provenance.

Run: .venv/bin/python -m scripts.ingest_repealed_codes
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
    ("act:iea-1872", "The Indian Evidence Act, 1872", f"{_RAW}/iea.json", "section"),
)


# Sections the compilation leaves empty, supplied from another source as
# (body, source name, source url). Each gets that source's provenance
# rather than the compilation's.
#
# 304B: text from the Legislative Department's A1860-45.pdf (Internet
# Archive mirror; indiacode.nic.in is unreachable), checked word for word
# against indiankanoon.org/doc/653797/. They differ only where OCR read
# "(1)" as "(/)" and Indian Kanoon has "purpose" for "purposes".
PATCHED_SECTIONS: dict[str, tuple[str, str, str]] = {
    "act:ipc-1860:sec-304B": (
        "(1) Where the death of a woman is caused by any burns or bodily "
        "injury or occurs otherwise than under normal circumstances within "
        "seven years of her marriage and it is shown that soon before her "
        "death she was subjected to cruelty or harassment by her husband or "
        "any relative of her husband for, or in connection with, any demand "
        "for dowry, such death shall be called “dowry death”, and "
        "such husband or relative shall be deemed to have caused her death.\n"
        "Explanation.—For the purposes of this sub-section, "
        "“dowry” shall have the same meaning as in section 2 of the "
        "Dowry Prohibition Act, 1961 (28 of 1961).\n"
        "(2) Whoever commits dowry death shall be punished with imprisonment "
        "for a term which shall not be less than seven years but which may "
        "extend to imprisonment for life.",
        "The Indian Penal Code, 1860 (A1860-45.pdf, Legislative Department), "
        "Internet Archive mirror, OCR text",
        "https://archive.org/details/a-1860-45",
    ),
}


def _patch_provenance(name: str, url: str, document_id: str) -> Provenance:
    return Provenance(
        source=SourceRef(
            name=name,
            url=url,
            document_id=document_id,
            source_type="research",
        ),
        retrieved_at=datetime.now(timezone.utc),
        licence="Government of India work; no licence stated on the mirror",
        attribution_required=True,
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
    from str(). Sections with an empty body are skipped rather than stored
    unless PATCHED_SECTIONS supplies one: an empty row is unretrievable and
    would read as coverage we do not have.
    """
    with urllib.request.urlopen(url) as response:
        entries = json.load(response)

    sections: list[CanonicalDocument] = []
    skipped: list[str] = []
    now = datetime.now(timezone.utc)
    for entry in entries:
        number = str(entry[key]).strip()
        body = (entry["section_desc"] or "").strip()
        section_id = f"{act_id}:sec-{number}"
        patch = PATCHED_SECTIONS.get(section_id) if not body else None
        if patch is not None:
            body, patch_name, patch_url = patch
            provenance = _patch_provenance(patch_name, patch_url, section_id)
        else:
            provenance = _provenance(url, section_id)
        if not body:
            skipped.append(number)
            continue
        sections.append(
            CanonicalDocument(
                document_id=section_id,
                document_type="section",
                title=entry["section_title"].strip(),
                act_id=act_id,
                full_text=body,
                content_hash=content_hash(body),
                provenance=provenance,
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
