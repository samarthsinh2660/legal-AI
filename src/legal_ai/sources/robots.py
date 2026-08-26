"""robots.txt compliance for the public sources we fetch from.

This is not politeness. Indian Kanoon's robots.txt carries thousands of
specific /doc/<id>/ disallow rules -- judgments a court has ordered
de-indexed, typically victim-privacy and right-to-be-forgotten matters.
Fetching one and putting it in front of a user republishes exactly what
was ordered suppressed, and a legal product is the worst possible party
to get that wrong.

Only the `User-Agent: *` group is read. We do not present as any of the
named crawlers, and the blanket `Disallow: /` entries in that file belong
to SemrushBot, CCBot, Yandex and AhrefsBot -- applying them to ourselves
would block every fetch, which is not what the file says about us.

Failing closed on a fetch error is deliberate. An unreachable robots.txt
means we do not know what is disallowed, and "we could not check" must not
resolve to "go ahead" when the cost of being wrong is republishing a
suppressed judgment.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from legal_ai.sources.http import polite_get

# Parsed rules per origin, so robots.txt is fetched once per process
# rather than once per document.
_CACHE: dict[str, tuple[str, ...] | None] = {}


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _path(url: str) -> str:
    parts = urlsplit(url)
    return parts.path or "/"


def parse_wildcard_disallows(text: str) -> tuple[str, ...]:
    """Disallow paths in the `User-Agent: *` group.

    A group ends at the next User-agent line. Other groups are ignored
    entirely -- see the module docstring on why applying their blanket
    rules to us would be wrong.
    """
    disallows: list[str] = []
    in_wildcard = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            in_wildcard = value == "*"
        elif field == "disallow" and in_wildcard and value:
            disallows.append(value)
    return tuple(disallows)


def _rules(origin: str) -> tuple[str, ...] | None:
    """Cached rules for `origin`; None when robots.txt could not be read."""
    if origin in _CACHE:
        return _CACHE[origin]
    try:
        response = polite_get(f"{origin}/robots.txt")
        rules = parse_wildcard_disallows(response.text) if response.status_code == 200 else None
        # A 404 means no restrictions, which is different from unreachable.
        if response.status_code == 404:
            rules = ()
    except Exception:
        rules = None
    _CACHE[origin] = rules
    return rules


def is_allowed(url: str) -> bool:
    """Whether robots.txt permits fetching `url`.

    Matching is by prefix, as the standard specifies: a rule of
    "/doc/12345/" blocks that path and anything under it.
    """
    rules = _rules(_origin(url))
    if rules is None:
        return False  # unknown rules -- see the module docstring
    path = _path(url)
    return not any(path.startswith(rule) for rule in rules)


def reset_cache() -> None:
    """Drop cached rules. For tests, and for a long-lived process that
    should not trust a day-old copy of a file it must obey."""
    _CACHE.clear()
