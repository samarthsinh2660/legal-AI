"""Paging.

No list endpoint uses this yet. It is tested now because the properties
below are the ones that get quietly broken the first time somebody wires it
up: an uncapped limit, and a `has_more` that lies on the last page.
"""

import pytest
from pydantic import ValidationError

from api.utils.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Page,
    PageParams,
    PageResponse,
)


def test_defaults_are_a_sane_first_page():
    params = PageParams()
    assert params.offset == 0
    assert params.limit == DEFAULT_LIMIT


def test_an_oversized_limit_is_rejected_not_clamped():
    """A client that asks for 5,000 rows should be told its request was
    wrong, not quietly handed 100 and left believing it has everything."""
    with pytest.raises(ValidationError):
        PageParams(limit=MAX_LIMIT + 1)


def test_a_zero_or_negative_limit_is_rejected():
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            PageParams(limit=bad)


def test_a_negative_offset_is_rejected():
    with pytest.raises(ValidationError):
        PageParams(offset=-1)


def test_has_more_is_true_mid_way_through():
    page = Page(items=[1, 2], total=10, limit=2, offset=0)
    assert page.has_more


def test_has_more_is_false_on_the_last_page():
    page = Page(items=[9, 10], total=10, limit=2, offset=8)
    assert not page.has_more


def test_a_short_last_page_is_not_reported_as_having_more():
    """The bug this guards: reading a partial page as "there must be more"
    and looping forever."""
    page = Page(items=[10], total=10, limit=5, offset=9)
    assert not page.has_more


def test_an_empty_result_has_no_more():
    assert not Page(items=[], total=0, limit=20, offset=0).has_more


def test_the_wire_shape_mirrors_the_page():
    page = Page(items=["a"], total=3, limit=1, offset=0)
    body = PageResponse.of(page)
    assert body.items == ["a"]
    assert (body.total, body.limit, body.offset) == (3, 1, 0)
    assert body.has_more is True


def test_total_is_the_count_before_paging():
    """Without it a client cannot tell a last page from a short one, and
    cannot render a pager at all."""
    page = Page(items=[1], total=100, limit=1, offset=0)
    assert page.total == 100 and len(page.items) == 1
