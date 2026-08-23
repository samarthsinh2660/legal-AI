"""Timeline building. Deterministic: a wrong date loses a limitation point."""

from datetime import date

from legal_ai.case.timeline import build_timeline, parse_date
from legal_ai.context.models import DocumentFacts


def _facts(document_id: str, *dates: str) -> DocumentFacts:
    return DocumentFacts(document_id=document_id, dates=tuple(dates))


def test_numeric_dates_are_read_day_first():
    # Indian legal documents are day-first throughout. Reading 03/04/2021
    # as 4 March would move a limitation date by a month.
    assert parse_date("03/04/2021") == date(2021, 4, 3)
    assert parse_date("15.03.2021") == date(2021, 3, 15)
    assert parse_date("15-03-2021") == date(2021, 3, 15)


def test_written_month_forms_are_read():
    assert parse_date("15th March, 2021") == date(2021, 3, 15)
    assert parse_date("12 Sept 2019") == date(2019, 9, 12)
    assert parse_date("March 15, 2021") == date(2021, 3, 15)


def test_an_impossible_date_is_none_not_an_exception():
    # 31 February is a typo in someone's notice, not a reason to fail the
    # whole case view.
    assert parse_date("31.02.2021") is None


def test_a_date_that_cannot_be_resolved_is_none():
    assert parse_date("the following Monday") is None
    assert parse_date("within 30 days") is None


def test_entries_are_ordered_earliest_first():
    timeline = build_timeline((
        _facts("doc-1", "30 June 2021", "12 March 2019"),
        _facts("doc-2", "01.01.2020"),
    ))
    assert [e.parsed for e in timeline] == [
        date(2019, 3, 12), date(2020, 1, 1), date(2021, 6, 30),
    ]


def test_undated_events_are_kept_and_sort_last():
    # Dropping them would show a confident timeline with holes in it.
    timeline = build_timeline((_facts("doc-1", "within 30 days", "12 March 2019"),))
    assert len(timeline) == 2
    assert timeline[0].parsed == date(2019, 3, 12)
    assert timeline[1].parsed is None
    assert timeline[1].raw == "within 30 days"
    assert timeline[1].is_dated is False


def test_every_entry_traces_to_its_document():
    timeline = build_timeline((_facts("doc-1", "12 March 2019"), _facts("doc-2", "01.01.2020")))
    assert {e.document_id for e in timeline} == {"doc-1", "doc-2"}


def test_the_same_date_in_two_documents_is_kept_twice():
    # Two documents evidencing the same event is corroboration a lawyer
    # needs to see, not a duplicate to collapse.
    timeline = build_timeline((_facts("doc-1", "12 March 2019"), _facts("doc-2", "12 March 2019")))
    assert len(timeline) == 2


def test_a_repeated_date_within_one_document_is_recorded_once():
    timeline = build_timeline((_facts("doc-1", "12 March 2019", "12 March 2019"),))
    assert len(timeline) == 1


def test_the_raw_text_is_preserved_verbatim():
    timeline = build_timeline((_facts("doc-1", "15th March, 2021"),))
    assert timeline[0].raw == "15th March, 2021"


def test_no_documents_gives_an_empty_timeline():
    assert build_timeline(()) == ()
