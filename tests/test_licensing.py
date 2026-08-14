# tests/test_licensing.py
import pytest

from legal_ai.sources.licensing import KNOWN_LICENCES, get_licence


def test_get_licence_returns_known_source():
    info = get_licence("supreme_court_bulk")
    assert info.licence == "CC-BY-4.0"
    assert info.attribution_required is True


def test_get_licence_raises_on_unknown_source():
    with pytest.raises(KeyError):
        get_licence("not_a_real_source")


def test_all_five_phase1_sources_are_registered():
    expected = {
        "supreme_court_bulk",
        "gujarat_hc_bulk",
        "india_code",
        "official_scr_search",
        "bharat_courts",
    }
    assert expected.issubset(KNOWN_LICENCES.keys())
