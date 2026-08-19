# tests/test_evidence.py
from datetime import datetime, timezone

from legal_ai.schemas.evidence import Evidence, Location, Provenance, SourceRef


def test_evidence_round_trips_through_json():
    source = SourceRef(
        name="Supreme Court of India",
        url="https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/",
        document_id="2023_1_INSC_1",
        source_type="primary",
    )
    provenance = Provenance(
        source=source,
        retrieved_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        licence="CC-BY-4.0",
        attribution_required=True,
    )
    evidence = Evidence(
        content="...a person in possession cannot be ousted...",
        provenance=provenance,
        location=Location(page=12, paragraph=42),
    )

    restored = Evidence.model_validate_json(evidence.model_dump_json())

    assert restored.provenance.source.name == "Supreme Court of India"
    assert restored.provenance.source.source_type == "primary"
    assert restored.location.paragraph == 42
    assert restored.provenance.attribution_required is True


def test_evidence_carries_optional_document_identity_fields():
    source = SourceRef(
        name="India Code",
        url="https://www.indiacode.nic.in/",
        source_type="primary",
    )
    provenance = Provenance(
        source=source,
        retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        licence="Government of India",
        attribution_required=False,
    )
    evidence = Evidence(
        content="Full section text here.",
        document_id="act:2158:sec-18",
        title="Return of amount and compensation.",
        document_type="section",
        provenance=provenance,
    )

    restored = Evidence.model_validate_json(evidence.model_dump_json())

    assert restored.document_id == "act:2158:sec-18"
    assert restored.title == "Return of amount and compensation."
    assert restored.document_type == "section"


def test_evidence_document_identity_fields_default_to_none():
    source = SourceRef(name="x", url="https://example.com", source_type="research")
    provenance = Provenance(
        source=source,
        retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        licence="x",
        attribution_required=False,
    )
    evidence = Evidence(content="text", provenance=provenance)

    assert evidence.document_id is None
    assert evidence.title is None
    assert evidence.document_type is None


def test_source_type_rejects_unknown_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SourceRef(
            name="x",
            url="https://example.com",
            source_type="not_a_real_type",
        )
