from legal_ai.retrieval.chunking.judgment import chunk_judgment
from legal_ai.retrieval.chunking.statute import chunk_statute


def test_short_statute_text_is_a_single_chunk():
    chunks = chunk_statute("A short provision that fits comfortably.", max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].text == "A short provision that fits comfortably."
    assert chunks[0].ordinal == 0


def test_empty_text_produces_no_chunks():
    assert chunk_statute("", max_chars=1000) == []
    assert chunk_judgment("") == []


def test_statute_splits_on_subsection_markers_not_mid_clause():
    text = (
        "(1) " + "alpha " * 60
        + "(2) " + "beta " * 60
        + "(3) " + "gamma " * 60
    )
    chunks = chunk_statute(text, max_chars=400)

    assert len(chunks) > 1
    # every chunk must start at a real subsection boundary, never mid-clause
    assert all(c.text.lstrip().startswith("(") for c in chunks)


def test_statute_chunk_labels_record_the_subsection():
    text = "(1) " + "alpha " * 60 + "(2) " + "beta " * 60
    chunks = chunk_statute(text, max_chars=400)
    assert chunks[0].label == "(1)"
    assert any(c.label == "(2)" for c in chunks)


def test_statute_keeps_a_proviso_attached_to_its_clause_when_it_fits():
    text = "(1) The promoter shall refund the amount. Provided that interest applies."
    chunks = chunk_statute(text, max_chars=1000)
    assert len(chunks) == 1
    assert "Provided that" in chunks[0].text


def test_statute_ordinals_are_sequential_from_zero():
    text = "(1) " + "alpha " * 60 + "(2) " + "beta " * 60 + "(3) " + "gamma " * 60
    chunks = chunk_statute(text, max_chars=300)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_statute_covers_all_the_source_text():
    text = "(1) " + "alpha " * 40 + "(2) " + "beta " * 40
    chunks = chunk_statute(text, max_chars=300)
    joined = " ".join(c.text for c in chunks)
    assert "alpha" in joined and "beta" in joined
    for word in ("alpha", "beta"):
        assert joined.count(word) >= 40


def test_statute_splits_a_single_oversized_clause_rather_than_emitting_it_whole():
    text = "(1) " + "verylongclause " * 200
    chunks = chunk_statute(text, max_chars=400)
    assert len(chunks) > 1
    assert all(len(c.text) <= 800 for c in chunks)


def test_judgment_splits_on_numbered_paragraphs_and_keeps_the_number():
    text = (
        "1. The appellant filed a complaint before the authority.\n"
        "2. The respondent denied the allegations entirely.\n"
        "3. We have heard both learned counsel at length.\n"
    )
    chunks = chunk_judgment(text, max_chars=60)

    labels = [c.label for c in chunks]
    assert "1" in labels and "2" in labels and "3" in labels


def test_judgment_paragraph_number_survives_for_verification_citing():
    text = "41. Earlier reasoning.\n42. The crucial holding of this Court.\n"
    chunks = chunk_judgment(text, max_chars=40)
    holding = [c for c in chunks if "crucial holding" in c.text]
    assert holding and holding[0].label == "42"


def test_judgment_without_numbered_paragraphs_still_chunks():
    text = "This order has no numbering at all. " * 40
    chunks = chunk_judgment(text, max_chars=300)
    assert len(chunks) > 1
    assert all(c.text.strip() for c in chunks)


def test_judgment_ordinals_are_sequential_from_zero():
    text = "1. Alpha reasoning here.\n2. Beta reasoning here.\n3. Gamma reasoning here.\n"
    chunks = chunk_judgment(text, max_chars=25)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_a_year_on_its_own_line_is_not_a_paragraph_number():
    # The tail of a citation wraps onto its own line and reads exactly like
    # a paragraph marker. Labelling it "paragraph 2022" points a reader at a
    # paragraph the judgment does not have.
    text = (
        "41. Earlier reasoning of the Court on the first issue raised.\n"
        "2022. Reported in the digest at page four hundred and twelve.\n"
        "42. The crucial holding of this Court on the second issue.\n"
    )
    chunks = chunk_judgment(text, max_chars=60)

    assert "2022" not in [c.label for c in chunks]
    holding = [c for c in chunks if "crucial holding" in c.text]
    assert holding and holding[0].label == "42"


def test_a_year_does_not_break_the_paragraph_it_sits_in():
    text = (
        "7. The Court in its earlier decision, reported in\n"
        "2019. at page ten, took a different view of the matter.\n"
    )
    chunks = chunk_judgment(text, max_chars=400)

    # One paragraph, not two: the year is text inside paragraph 7.
    assert [c.label for c in chunks] == ["7"]
    assert "at page ten" in chunks[0].text


def test_a_four_digit_paragraph_outside_the_year_range_is_kept():
    # Judgments numbered past 999 exist. The test is the year range, not the
    # digit count, so a real paragraph 1024 survives.
    text = "1024. The conclusion of a very long judgment indeed.\n"
    chunks = chunk_judgment(text, max_chars=400)
    assert chunks[0].label == "1024"
