from datetime import datetime, timezone

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.ingestion.verification_gate import verify_batch
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(i: int) -> CanonicalDocument:
    text = f"Full text of document {i}"
    return CanonicalDocument(
        document_id=f"act:{i}",
        document_type="act",
        title=f"Act {i}",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


def test_batch_passes_when_every_sampled_document_checks_out():
    docs = [_doc(i) for i in range(30)]
    result = verify_batch(docs, text_check=lambda d: True, sample_size=10, rng_seed=1)
    assert result.passed is True
    assert result.sampled_count == 10
    assert result.failed_document_ids == []


def test_batch_fails_when_a_sampled_document_has_no_extractable_text():
    docs = [_doc(i) for i in range(30)]

    def text_check(doc: CanonicalDocument) -> bool:
        return doc.document_id != "act:5"

    result = verify_batch(docs, text_check=text_check, sample_size=30, rng_seed=1)
    assert result.passed is False
    assert "act:5" in result.failed_document_ids


def test_batch_records_primary_source_check_when_provided():
    docs = [_doc(i) for i in range(5)]
    result = verify_batch(
        docs,
        text_check=lambda d: True,
        primary_source_check=lambda d: False,
        sample_size=5,
        rng_seed=1,
    )
    assert result.passed is False
    assert result.notes and "primary source" in result.notes[0].lower()


def test_batch_without_primary_source_check_notes_the_limitation():
    docs = [_doc(i) for i in range(5)]
    result = verify_batch(docs, text_check=lambda d: True, sample_size=5, rng_seed=1)
    assert result.passed is True
    assert any("no live primary-source check" in n.lower() for n in result.notes)


def test_sample_size_larger_than_batch_checks_everything():
    docs = [_doc(i) for i in range(3)]
    result = verify_batch(docs, text_check=lambda d: True, sample_size=100, rng_seed=1)
    assert result.sampled_count == 3
