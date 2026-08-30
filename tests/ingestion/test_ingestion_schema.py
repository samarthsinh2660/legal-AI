# tests/ingestion/test_ingestion_schema.py
from datetime import date, datetime, timezone

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.schemas.evidence import Provenance, SourceRef


def _provenance() -> Provenance:
    return Provenance(
        source=SourceRef(
            name="India Code",
            url="https://www.indiacode.nic.in/handle/123456789/2263",
            document_id="act:1963-47",
            source_type="primary",
        ),
        retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        licence="Government of India — primary legislative source",
        attribution_required=False,
    )


def test_content_hash_is_stable_and_sensitive_to_text():
    a = content_hash("Section 6 text")
    b = content_hash("Section 6 text")
    c = content_hash("Section 6 text, amended")
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex digest


def test_canonical_document_act_round_trips_through_json():
    doc = CanonicalDocument(
        document_id="act:1963-47",
        document_type="act",
        title="The Specific Relief Act, 1963",
        court=None,
        citation=None,
        case_number=None,
        parties=None,
        decision_date=None,
        enactment_date=date(1963, 12, 13),
        disposal_nature=None,
        act_id=None,
        full_text="An Act to define and amend the law...",
        content_hash=content_hash("An Act to define and amend the law..."),
        provenance=_provenance(),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )

    restored = CanonicalDocument.model_validate_json(doc.model_dump_json())

    assert restored.document_type == "act"
    assert restored.enactment_date == date(1963, 12, 13)
    assert restored.provenance.source.name == "India Code"


def test_canonical_document_section_references_parent_act():
    doc = CanonicalDocument(
        document_id="act:1963-47:sec-6",
        document_type="section",
        title="Section 6",
        court=None,
        citation=None,
        case_number=None,
        parties=None,
        decision_date=None,
        enactment_date=None,
        disposal_nature=None,
        act_id="act:1963-47",
        full_text="Suit by person dispossessed of immovable property.",
        content_hash=content_hash("Suit by person dispossessed of immovable property."),
        provenance=_provenance(),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    assert doc.act_id == "act:1963-47"
