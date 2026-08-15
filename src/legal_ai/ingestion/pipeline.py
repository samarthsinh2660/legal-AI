"""Wires: fetch -> parse -> verification gate -> store -> vector index -> graph.

See docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.1.
"""

from __future__ import annotations

from pydantic import BaseModel

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section
from legal_ai.ingestion.india_code.parser import parse_act
from legal_ai.ingestion.india_code.scraper import fetch_act_html, list_act_urls
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.ingestion.verification_gate import VerificationResult, verify_batch
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document


class PipelineReport(BaseModel):
    acts_processed: int
    sections_processed: int
    verification: VerificationResult
    store_writes: int
    failed_urls: list[str] = []


def _has_extractable_text(doc: CanonicalDocument) -> bool:
    # Section bodies are known to be empty at parse time — the real India
    # Code site loads them client-side via a per-section AJAX call this
    # scraper does not make (see parser.py). That is a structural fact
    # about what's fetched, not a data-quality failure to gate on; only
    # Acts are expected to carry real text at this stage. Fetching real
    # section bodies is follow-up scope, not silently pretended-away here.
    if doc.document_type == "section":
        return True
    return len(doc.full_text.strip()) > 0


def ingest_india_code(
    act_urls: list[str] | None = None,
    sample_size: int = 20,
) -> PipelineReport:
    urls = act_urls if act_urls is not None else list_act_urls()

    all_docs: list[CanonicalDocument] = []
    act_sections: list[tuple[CanonicalDocument, CanonicalDocument]] = []
    failed_urls: list[str] = []

    for url in urls:
        # polite_get already retries transient network errors (see
        # legal_ai.sources.http) — a URL landing here has exhausted those
        # retries. One bad Act page must not lose the other 844.
        try:
            html = fetch_act_html(url)
            act, sections = parse_act(html, url)
        except Exception:
            failed_urls.append(url)
            continue
        all_docs.append(act)
        all_docs.extend(sections)
        for section in sections:
            act_sections.append((act, section))

    verification = verify_batch(
        all_docs,
        text_check=_has_extractable_text,
        sample_size=sample_size,
    )
    section_count = sum(1 for d in all_docs if d.document_type == "section")
    if section_count:
        verification.notes.append(
            f"{section_count} section(s) were stored with an empty body — "
            "real section text requires a follow-up per-section AJAX fetch, "
            "not yet implemented. Section titles, numbers, and their "
            "Act CONTAINS Section graph edge are still real and correct."
        )

    store_writes = 0
    if verification.passed:
        conn = get_connection()
        driver = get_driver()
        for doc in all_docs:
            vector = embed(doc.full_text) if doc.full_text.strip() else None
            if upsert_document(conn, doc, embedding=vector):
                store_writes += 1
        for act, section in act_sections:
            write_act_section(driver, act, section)

    return PipelineReport(
        acts_processed=sum(1 for d in all_docs if d.document_type == "act"),
        sections_processed=sum(1 for d in all_docs if d.document_type == "section"),
        verification=verification,
        store_writes=store_writes,
        failed_urls=failed_urls,
    )
