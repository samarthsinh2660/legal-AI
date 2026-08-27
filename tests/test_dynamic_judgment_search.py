"""Ingest-time text handling for judgments fetched from the archive.

What a PDF's text layer yields is not always text. These cover the two
failure modes seen during the 2026-08-27 all-High-Court ingest: NUL bytes
Postgres cannot store, and pages that extract as noise or as nothing but
the registrar's e-signature.
"""



# --- NUL bytes: added 2026-08-27 after a real ingest loss ----------------

def test_nul_bytes_are_stripped_from_extracted_text():
    # pypdf emits NUL from some scanned text layers, and PostgreSQL text
    # columns cannot hold them: one judgment in ~1,500 was lost to
    # DataError during the all-High-Court ingest.
    from legal_ai.ingestion.judgments.dynamic_search import _strip_nuls

    assert _strip_nuls("JUDG\x00MENT") == "JUDGMENT"


def test_stripping_leaves_clean_text_untouched():
    from legal_ai.ingestion.judgments.dynamic_search import _strip_nuls

    assert _strip_nuls("ordinary judgment text") == "ordinary judgment text"


def test_content_hash_describes_the_stripped_text(monkeypatch):
    # The hash must cover what is actually stored, or a re-ingest of the
    # same judgment would look changed on every run.
    from legal_ai.ingestion.schema import content_hash
    from legal_ai.ingestion.judgments.dynamic_search import _strip_nuls, _to_canonical

    from bharat_courts.models import CourtType

    class FakeCourt:
        name = "Test High Court"
        court_type = CourtType.HIGH_COURT

    class FakeJudgment:
        cnr = "TESTNUL0001"
        case_id = "1/2020"
        court = FakeCourt()
        court_name_raw = None
        court_code = "test"
        citation = None
        petitioner = respondent = None
        decision_date = None
        disposal_nature = None
        title = "A versus B"
        year = 2020
        bench = None
        pdf_path = "some/path/doc.pdf"

    doc = _to_canonical(FakeJudgment(), "text with\x00 a nul", "fallback")
    assert "\x00" not in doc.full_text
    assert doc.content_hash == content_hash(_strip_nuls("text with\x00 a nul"))


# --- text quality: added 2026-08-27 after 174 unusable judgments were
# --- found already stored in the corpus.

def _doc(text: str):
    from datetime import datetime, timezone

    from legal_ai.ingestion.schema import CanonicalDocument, content_hash
    from legal_ai.schemas.evidence import Provenance, SourceRef

    return CanonicalDocument(
        document_id="judgment:quality-probe", document_type="judgment",
        title="Probe", court="Test", full_text=text, content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="p", url="https://e.com", source_type="primary",
                             document_id="judgment:quality-probe"),
            retrieved_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            licence="t", attribution_required=False),
        ingested_at=datetime(2026, 8, 27, tzinfo=timezone.utc))


def test_mojibake_is_rejected_despite_being_long():
    # A PDF with a broken font encoding map extracts as noise. One such
    # document ran to 60,857 characters and passed the old length check.
    from legal_ai.ingestion.judgments.dynamic_search import _text_check

    assert not _text_check(_doc('!" #$%$ &\'()) *+ ) ,, + !$ # %& \'' * 40))


def test_a_signature_only_scan_is_rejected_on_length():
    # The whole text layer of one scanned Punjab & Haryana judgment was the
    # registrar's e-stamp. Recorded here as the real thing, because it is
    # rejected by the LENGTH floor, not the alpha ratio -- the stamp is
    # ordinary English (alpha 0.66), merely useless. Documenting which rule
    # actually catches it stops a later "simplification" from dropping the
    # length floor on the theory that the ratio covers everything.
    from legal_ai.ingestion.judgments.dynamic_search import _text_check

    stamp = (
        "NAINA KATHIAT\n2025.12.31 19:21\nI attest to the accuracy and\n"
        "integrity of this document\n \nNAINA KATHIAT\n2025.12.31 19:21\n"
        "I attest to the accuracy and\nintegrity of this docum"
    )
    assert len(stamp.strip()) < 200
    assert not _text_check(_doc(stamp))


def test_real_judgment_prose_passes():
    from legal_ai.ingestion.judgments.dynamic_search import _text_check

    prose = (
        "The appellant challenges the order of the learned Single Judge "
        "dismissing the writ petition. Having heard counsel for the parties "
        "and perused the record, we find no reason to interfere. "
    ) * 3
    assert _text_check(_doc(prose))


def test_a_short_procedural_order_still_passes():
    # Real but terse. These are legitimate and must not be swept up with
    # the noise: the corpus contains genuine orders of ~220 characters.
    from legal_ai.ingestion.judgments.dynamic_search import _text_check

    order = (
        "BEFORE HON'BLE THE CHIEF JUSTICE WP (C) No.138 of 2017 dated "
        "20.12.2017 In view of the order passed in the connected matter, "
        "this writ petition stands disposed of accordingly as infructuous. "
        "The interim order granted earlier shall stand vacated forthwith."
    )
    assert len(order) >= 200
    assert _text_check(_doc(order))
