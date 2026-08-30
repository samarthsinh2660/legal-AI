"""Paging for list endpoints.

Nothing uses this yet; it exists so the first three list routes do not each
invent their own parameter names.

Offset paging, not cursor: the rows are a user's own cases and history, and
a UI needs `total` to render a pager at all.

The cap matters. An unbounded limit is a way to ask one request to
serialise a whole table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

T = TypeVar("T")


class PageParams(BaseModel):
    """Query parameters for a paged list.

    `limit` is capped by the schema rather than silently clamped in code: a
    client that asks for 5,000 rows should be told its request was wrong,
    not quietly handed 100 and left believing it has everything.
    """

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(default=0, ge=0)


@dataclass(frozen=True)
class Page(Generic[T]):
    """One page of rows, and how many there are in total.

    `total` is the count *before* limit and offset. Without it a client
    cannot tell a last page from a page that happens to be short, and
    cannot render a pager at all.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class PageResponse(BaseModel, Generic[T]):
    """The wire shape of a page. Mirrors `Page`."""

    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def of(cls, page: Page) -> "PageResponse":
        return cls(
            items=page.items,
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            has_more=page.has_more,
        )
