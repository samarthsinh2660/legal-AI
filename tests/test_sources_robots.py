"""robots.txt compliance. Not politeness -- Indian Kanoon's file names
thousands of judgments a court ordered de-indexed."""

import pytest

from legal_ai.sources import robots


@pytest.fixture(autouse=True)
def clear_cache():
    robots.reset_cache()
    yield
    robots.reset_cache()


ROBOTS = """
# a comment
User-Agent: *
Disallow: /cached/
Disallow: /doc/1987695/
Disallow:

User-agent: CCBot
Disallow: /

User-agent: SemrushBot
Disallow: /
"""


def test_only_the_wildcard_group_is_read():
    # The blanket Disallow: / belongs to CCBot and SemrushBot. Applying it
    # to ourselves would block every fetch, which is not what the file says.
    assert robots.parse_wildcard_disallows(ROBOTS) == ("/cached/", "/doc/1987695/")


def test_an_empty_disallow_is_not_a_rule():
    # "Disallow:" with no value means nothing is disallowed, not that "" is.
    assert "" not in robots.parse_wildcard_disallows(ROBOTS)


def test_comments_are_stripped():
    assert robots.parse_wildcard_disallows("User-agent: *\nDisallow: /x/ # why") == ("/x/",)


def _serve(monkeypatch, text, status=200):
    monkeypatch.setattr(
        robots, "polite_get",
        lambda url, **kw: type("R", (), {"status_code": status, "text": text})(),
    )


def test_a_disallowed_document_is_refused(monkeypatch):
    _serve(monkeypatch, ROBOTS)
    assert robots.is_allowed("https://indiankanoon.org/doc/1987695/") is False


def test_an_allowed_document_is_permitted(monkeypatch):
    _serve(monkeypatch, ROBOTS)
    assert robots.is_allowed("https://indiankanoon.org/doc/149094324/") is True


def test_search_is_permitted(monkeypatch):
    _serve(monkeypatch, ROBOTS)
    assert robots.is_allowed("https://indiankanoon.org/search/") is True


def test_matching_is_by_prefix(monkeypatch):
    _serve(monkeypatch, ROBOTS)
    assert robots.is_allowed("https://indiankanoon.org/cached/anything") is False


def test_an_unreachable_robots_file_fails_closed(monkeypatch):
    # "We could not check" must not resolve to "go ahead" when the cost of
    # being wrong is republishing a suppressed judgment.
    def boom(url, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(robots, "polite_get", boom)
    assert robots.is_allowed("https://indiankanoon.org/doc/1/") is False


def test_a_missing_robots_file_allows_everything(monkeypatch):
    # A 404 means no restrictions, which is different from unreachable.
    _serve(monkeypatch, "", status=404)
    assert robots.is_allowed("https://example.org/doc/1/") is True


def test_robots_is_fetched_once_per_origin(monkeypatch):
    calls = []

    def counting(url, **kw):
        calls.append(url)
        return type("R", (), {"status_code": 200, "text": ROBOTS})()

    monkeypatch.setattr(robots, "polite_get", counting)
    for doc_id in range(5):
        robots.is_allowed(f"https://indiankanoon.org/doc/{doc_id}/")
    assert len(calls) == 1
