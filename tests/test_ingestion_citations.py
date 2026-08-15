# tests/test_ingestion_citations.py
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
