"""Choosing which judgments to compare when courts may have split.

Comparing every pair on a heavily-litigated section is combinatorial and
pointless: fifty judgments is 1,225 pairs, nearly all of them the same court
agreeing with itself. A split that matters is between *courts*, so the
candidate set is the strongest judgment from each of a few different courts.
"""

from legal_ai.retrieval.authority import Authority
from legal_ai.retrieval.conflict import CourtHolding, select_candidates


def h(doc_id: str, court: str, citations: int = 0, bench: int | None = None) -> CourtHolding:
    return CourtHolding(
        document_id=doc_id,
        court=court,
        passage="the court held something",
        authority=Authority(doc_id, citation_count=citations, bench_size=bench),
    )


def test_one_judgment_per_court():
    """Two judgments of the same court are not a split, whatever they say."""
    picked = select_candidates([
        h("a", "Delhi High Court", 5),
        h("b", "Delhi High Court", 3),
        h("c", "Bombay High Court", 4),
    ])
    assert {p.court for p in picked} == {"Delhi High Court", "Bombay High Court"}
    assert len(picked) == 2


def test_the_strongest_judgment_represents_its_court():
    picked = select_candidates([
        h("weak", "Delhi High Court", 1),
        h("strong", "Delhi High Court", 20),
        h("other", "Bombay High Court", 4),
    ])
    delhi = [p for p in picked if p.court == "Delhi High Court"]
    assert [p.document_id for p in delhi] == ["strong"]


def test_a_single_court_is_not_a_split():
    """Nothing to compare -- one court cannot disagree with itself here."""
    assert select_candidates([h("a", "Delhi High Court", 5)]) == []


def test_courts_are_capped():
    """Every extra court is another judgment in the model's window."""
    holdings = [h(f"j{n}", f"Court {n}", n) for n in range(10)]
    assert len(select_candidates(holdings, max_courts=3)) == 3


def test_the_most_authoritative_courts_come_first():
    picked = select_candidates([
        h("minor", "Court A", 1),
        h("major", "Court B", 50),
        h("middle", "Court C", 10),
    ], max_courts=2)
    assert [p.document_id for p in picked] == ["major", "middle"]


def test_missing_court_is_not_a_court():
    """A judgment with no court field cannot be attributed to one, so it
    cannot stand for that court in a split."""
    picked = select_candidates([
        h("known", "Delhi High Court", 5),
        h("orphan", "", 9),
        h("other", "Bombay High Court", 2),
    ])
    assert "orphan" not in [p.document_id for p in picked]


def test_empty():
    assert select_candidates([]) == []
