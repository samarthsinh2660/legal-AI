"""How a later judgment treated the case it cited.

This is the Shepard's/KeyCite question, and the one a lawyer most assumes
they are getting. It is also the one where a wrong answer is worst: telling
a reader a case is good law when it was overruled is worse than telling them
nothing, because they will stop checking.

So the classifier fails to NOT_CHECKED, never to FOLLOWED. An unclassified
edge and a followed one must never look alike.
"""

import legal_ai.agents.treatment as treatment_agent
from legal_ai.agents.treatment import Treatment, classify_treatments


def _reply(monkeypatch, text):
    monkeypatch.setattr(treatment_agent, "generate", lambda *a, **k: text)


CITED = [("(2019) 8 SCC 729", "We respectfully overrule that decision.")]


def test_an_overruling_from_the_reporter_table_is_kept():
    """The table states the treatment outright, so OVERRULED survives from
    that source -- it is only the model's inference that is refused."""
    from legal_ai.ingestion.treatment_table import extract_treatment_table

    table = extract_treatment_table(
        "Case Law Reference\n[1998] 1 SCR 50 overruled Para 9"
    )
    assert table[0][1] is Treatment.OVERRULED


def test_following_is_recognised(monkeypatch):
    _reply(monkeypatch, '{"treatments": [{"n": 1, "treatment": "FOLLOWED"}]}')
    assert classify_treatments(CITED)[0].treatment is Treatment.FOLLOWED


def test_distinguishing_is_not_overruling(monkeypatch):
    """Distinguishing leaves the earlier case good law on its own facts.
    Reporting it as overruled would retire a live authority."""
    _reply(monkeypatch, '{"treatments": [{"n": 1, "treatment": "DISTINGUISHED"}]}')
    result = classify_treatments(CITED)[0]
    assert result.treatment is Treatment.DISTINGUISHED
    assert not result.treatment.is_negative


def test_an_unreadable_reply_is_not_checked(monkeypatch):
    _reply(monkeypatch, "no json here at all")
    result = classify_treatments(CITED)[0]
    assert result.treatment is Treatment.NOT_CHECKED
    assert result.treatment is not Treatment.FOLLOWED


def test_an_unrecognised_label_is_not_checked(monkeypatch):
    _reply(monkeypatch, '{"treatments": [{"n": 1, "treatment": "APPROVED-ISH"}]}')
    assert classify_treatments(CITED)[0].treatment is Treatment.NOT_CHECKED


def test_a_citation_the_model_skipped_is_not_checked(monkeypatch):
    """Silence is not approval."""
    pair = CITED + [("[2015] 3 S.C.R. 100", "considered briefly")]
    _reply(monkeypatch, '{"treatments": [{"n": 1, "treatment": "FOLLOWED"}]}')
    results = classify_treatments(pair)
    assert results[1].treatment is Treatment.NOT_CHECKED


def test_nothing_to_classify_makes_no_call(monkeypatch):
    calls = []
    monkeypatch.setattr(treatment_agent, "generate",
                        lambda *a, **k: calls.append(1) or "{}")
    assert classify_treatments([]) == []
    assert calls == []


def test_one_call_for_many_citations(monkeypatch):
    calls = []
    monkeypatch.setattr(
        treatment_agent, "generate",
        lambda *a, **k: (calls.append(1), '{"treatments": []}')[1],
    )
    classify_treatments([(f"(20{n:02d}) 1 SCC 1", "text") for n in range(10)])
    assert len(calls) == 1


def test_only_overruling_counts_as_negative():
    assert Treatment.OVERRULED.is_negative
    assert not Treatment.FOLLOWED.is_negative
    assert not Treatment.CONSIDERED.is_negative
    assert not Treatment.NOT_CHECKED.is_negative


def test_the_model_may_not_return_overruled(monkeypatch):
    """Measured 2026-08-30: the model produced OVERRULED twice on the real
    corpus and was wrong both times -- once from a page-header citation
    collision, once from a reference list where the cited case was marked
    "affirmed" and a DIFFERENT case on the same line was overruled.

    0 for 2 on the label whose errors are worst. A false overruling retires
    an authority that still binds, so this verdict is now reserved for the
    reporter's own table (ingestion/treatment_table.py), which states it
    outright. From the model it becomes NOT_CHECKED, which withholds the
    clean bill without asserting a retirement.
    """
    _reply(monkeypatch, '{"treatments": [{"n": 1, "treatment": "OVERRULED"}]}')
    result = classify_treatments(CITED)[0]
    assert result.treatment is Treatment.NOT_CHECKED
    assert "reporter" in result.why.lower()
