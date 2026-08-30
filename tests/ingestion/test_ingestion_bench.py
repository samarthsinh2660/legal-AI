"""Bench extraction -- who decided a judgment, and how many of them.

Bench size is not decoration: in Indian law a larger bench binds a smaller
one, so "which authority wins" cannot be answered without it. These tests
pin the shapes the SCR reporter actually prints, including the mangled ones
-- the header is OCR'd from a PDF, so spacing and case are not reliable.
"""

from __future__ import annotations

from legal_ai.ingestion.bench import extract_bench

SCR_HEADER = "[2013] 9 S.C.R. 283\nBAL GOPAL MAHESHWARI & ORS\nv.\nSANJEEV KUMAR GUPTA\n"


def test_two_judges():
    assert extract_bench(SCR_HEADER + "[R. F. NARIMAN AND NAVIN SINHA, JJ.]") == [
        "R. F. NARIMAN",
        "NAVIN SINHA",
    ]


def test_three_judges():
    names = extract_bench("[S. ABDUL NAZEER, INDU MALHOTRA AND ANIRUDDHA BOSE, JJ.]")
    assert names == ["S. ABDUL NAZEER", "INDU MALHOTRA", "ANIRUDDHA BOSE"]


def test_single_judge_uses_singular_suffix():
    assert extract_bench("[A.K. SIKRI, J.]") == ["A.K. SIKRI"]


def test_newline_inside_the_bracket():
    """The bracket wraps across lines in the PDF; that is not a new field."""
    names = extract_bench("[ABHAY MANOHAR SAPRE AND \nR. SUBHASH REDDY, JJ.]")
    assert names == ["ABHAY MANOHAR SAPRE", "R. SUBHASH REDDY"]


def test_cji_is_a_title_not_a_judge():
    """`CJI` sits inline where a name would; counting it inflates the bench."""
    names = extract_bench("[N. V. RAMANA, CJI, HIMA KOHLI AND\nC.T. RAVIKUMAR, JJ.]")
    assert names == ["N. V. RAMANA", "HIMA KOHLI", "C.T. RAVIKUMAR"]


def test_cji_without_its_comma():
    names = extract_bench("[S. A. BOBDE CJI, A. S. BOPANNA AND \nV. RAMASUBRAMANIAN, JJ.]")
    assert names == ["S. A. BOBDE", "A. S. BOPANNA", "V. RAMASUBRAMANIAN"]


def test_mixed_case_and_lowercase_and():
    names = extract_bench("[Bela M. Trivedi and Satish Chandra Sharma, JJ.]")
    assert names == ["Bela M. Trivedi", "Satish Chandra Sharma"]


def test_asterisk_marks_the_author_not_the_name():
    names = extract_bench("[M.M. Sundresh* and Rajesh Bindal, JJ.]")
    assert names == ["M.M. Sundresh", "Rajesh Bindal"]


def test_missing_comma_before_the_suffix():
    names = extract_bench("[K.S. RADHAKRISHNAN AND A.K. SIKRI JJ.]")
    assert names == ["K.S. RADHAKRISHNAN", "A.K. SIKRI"]


def test_citation_bracket_is_not_a_bench():
    """`[2013] 9 S.C.R. 283` is a bracket in the same header. Matching it
    would give every judgment a one-judge bench made of a page number."""
    assert extract_bench("[2013] 9 S.C.R. 283\nsome judgment text") == []


def test_no_bench_line_returns_empty():
    assert extract_bench("Bipul Bharali vs Prasanta Das on 31 May, 2024") == []


def test_empty_text():
    assert extract_bench("") == []


def test_only_the_header_is_searched():
    """A bracketed bench-looking string deep in the body is a quotation from
    another judgment, not this one's bench."""
    body = "x" * 9000 + "[R. F. NARIMAN AND NAVIN SINHA, JJ.]"
    assert extract_bench(body) == []


def test_constitution_bench():
    names = extract_bench(
        "[K.M. JOSEPH, AJAY RASTOGI, ANIRUDDHA BOSE, HRISHIKESH ROY "
        "AND C.T. RAVIKUMAR, JJ.]"
    )
    assert len(names) == 5
