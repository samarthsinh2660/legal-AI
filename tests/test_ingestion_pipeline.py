from unittest.mock import MagicMock

from legal_ai.ingestion.india_code.parser import parse_act
from legal_ai.ingestion.pipeline import ingest_india_code
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import get_document

# Mirrors the real india code DSpace item page structure (see
# tests/test_india_code_parser.py for the source of truth on this
# fixture's shape). The section body <p id="secpNNNN"> is deliberately
# non-empty here (unlike the real site, which loads it via AJAX) so this
# pipeline test can exercise the verification gate's text-extraction check
# without also asserting anything about India Code's AJAX behaviour.
ACT_HTML = """
<html><body>
<div class="display-item">
  <a href="/bitstream/123456789/2263/1/act.pdf">
    <p id="short_title">The Specific Relief Act, 1963</p>
  </a>
  <div class="hideshowsection" id="accordion1">
    <a class="title" href="/show-data?sectionId=6">
      <span class="label label-default">Section 6.</span>
      Suit by person dispossessed of immovable property
    </a>
    <p id="secp6">If any person is dispossessed without consent, they may sue within six months.</p>
  </div>
</div>
</body></html>
"""


def test_ingest_india_code_reports_counts_with_mocked_fetch(monkeypatch):
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.fetch_act_html",
        lambda url: ACT_HTML,
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.upsert_document",
        MagicMock(return_value=True),
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.write_act_section",
        MagicMock(),
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.embed",
        lambda text: [0.0] * 384,
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.get_connection",
        MagicMock(),
    )
    monkeypatch.setattr(
        "legal_ai.ingestion.pipeline.get_driver",
        MagicMock(),
    )

    report = ingest_india_code(
        act_urls=["https://www.indiacode.nic.in/handle/123456789/2263"],
        sample_size=20,
    )

    assert report.acts_processed == 1
    assert report.sections_processed == 1
    assert report.verification.passed is True


def test_ingest_india_code_end_to_end_against_real_postgres_and_neo4j():
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM documents WHERE document_id LIKE 'act:2263%'")
    conn.commit()
    conn.close()

    import legal_ai.ingestion.pipeline as pipeline_module

    original_fetch = pipeline_module.fetch_act_html
    pipeline_module.fetch_act_html = lambda url: ACT_HTML
    try:
        report = pipeline_module.ingest_india_code(
            act_urls=["https://www.indiacode.nic.in/handle/123456789/2263"],
            sample_size=20,
        )
    finally:
        pipeline_module.fetch_act_html = original_fetch

    assert report.acts_processed == 1
    assert report.verification.passed is True

    conn = get_connection()
    stored = get_document(conn, "act:2263")
    conn.close()
    assert stored is not None
    assert stored.title == "The Specific Relief Act, 1963"
