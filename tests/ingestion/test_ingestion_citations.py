# tests/ingestion/test_ingestion_citations.py
from legal_ai.ingestion.citations import extract_citations


def test_extracts_scc_style_citation():
    text = "As held in Ravinder Kaur Grewal v. Manjit Kaur, (2019) 8 SCC 729, the court..."
    assert "(2019) 8 SCC 729" in extract_citations(text)


def test_extracts_insc_style_citation():
    text = "This case, 2023 INSC 1043, follows the earlier ruling."
    assert "2023 INSC 1043" in extract_citations(text)


def test_extracts_air_style_citation():
    text = "See Nair Service Society v. K.C. Alexander, AIR 1968 SC 1165."
    assert "AIR 1968 SC 1165" in extract_citations(text)


def test_extracts_glr_style_citation():
    text = "The Gujarat High Court in 2023 GLR 1 held that..."
    assert "2023 GLR 1" in extract_citations(text)


def test_extracts_multiple_citations_without_duplicates():
    text = "See (2019) 8 SCC 729 and again (2019) 8 SCC 729, compare AIR 1968 SC 1165."
    result = extract_citations(text)
    assert result.count("(2019) 8 SCC 729") == 1
    assert "AIR 1968 SC 1165" in result


def test_returns_empty_list_when_no_citation_present():
    assert extract_citations("This section defines ownership generally.") == []


# --- SCR: added 2026-08-27 with the citation-resolution fix ---------------

def test_scr_citation_is_extracted():
    # The Bharat Courts archive reports every Supreme Court judgment by its
    # SCR citation, and those judgments cite each other the same way. With
    # no SCR pattern, 3,121 references in the corpus were never seen.
    text = "Followed in Kesavananda Bharati, [2018] 13 S.C.R. 1188, at para 4."
    assert "[2018] 13 S.C.R. 1188" in extract_citations(text)


def test_scr_spacing_and_stops_vary_but_are_one_citation():
    # Both spellings appear in the source PDFs, sometimes in one document.
    text = "see [2018] 13 S.C.R. 1188 and again at [2018] 13 SCR 1188"
    assert len(extract_citations(text)) == 1


def test_normalise_makes_the_two_spellings_equal():
    from legal_ai.ingestion.citations import normalise_citation

    assert normalise_citation("[2018] 13 S.C.R. 1188") == normalise_citation(
        "[2018] 13 SCR 1188"
    )


def test_normalise_does_not_collapse_different_cases():
    from legal_ai.ingestion.citations import normalise_citation

    assert normalise_citation("[2018] 13 SCR 1188") != normalise_citation(
        "[2018] 13 SCR 1189"
    )


def test_scr_and_scc_in_one_text_are_both_kept():
    # A judgment routinely carries its own SCR number and cites others by
    # SCC; dropping either loses real edges.
    text = "[2024] 10 S.C.R. 150 : 2024 INSC 749 ... relying on (2019) 8 SCC 729"
    found = extract_citations(text)
    assert "[2024] 10 S.C.R. 150" in found
    assert "(2019) 8 SCC 729" in found
    assert "2024 INSC 749" in found


def test_statute_extraction_is_a_separate_path():
    # This fix must not reach sections. extract_citations finds law reports;
    # section references are extract_section_references' job and stay there.
    assert extract_citations("Section 138 of the Negotiable Instruments Act, 1881") == []
