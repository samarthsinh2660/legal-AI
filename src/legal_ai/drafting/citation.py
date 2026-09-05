"""Turn a corpus identifier into a citation a court would accept.

`act:2189:sec-138` is how this system addresses a provision. It is not how
a notice cites one, and the first rendered draft printed the raw id into
the body of a document meant for opposing counsel.

Deterministic, from the corpus's own metadata: the Act's short title and
the section number are stored, so nothing here is inferred and a model is
never asked to write a citation it could get wrong.

An id that resolves to nothing returns None rather than a guess. The caller
drops the citation instead of printing something that looks authoritative
and is not.
"""

from __future__ import annotations

import re

_SECTION = re.compile(r"^(act:[^:]+):sec-(.+)$")


def format_citation(conn, document_id: str) -> str | None:
    """`document_id` as a citation, or None if the corpus cannot place it."""
    match = _SECTION.match(document_id or "")
    if match:
        act_id, section = match.groups()
        title = _title(conn, act_id)
        if title is None:
            return None
        return f"Section {section} of {_the(title)}"

    if (document_id or "").startswith("judgment:"):
        return _judgment(conn, document_id)

    return None


def _title(conn, act_id: str) -> str | None:
    row = conn.execute(
        "SELECT title FROM documents WHERE document_id = %s", (act_id,)
    ).fetchone()
    return row[0].strip() if row and row[0] else None


def _judgment(conn, document_id: str) -> str | None:
    """Case name and reported citation, as a judgment is cited.

    Party names are left in the case the reporter printed them in. Title-
    casing them would mangle initials and abbreviations, and Indian reports
    print them in capitals anyway.
    """
    row = conn.execute(
        "SELECT title, citation FROM documents WHERE document_id = %s", (document_id,)
    ).fetchone()
    if row is None or not row[0]:
        return None
    name = re.sub(r"\bversus\b", "v.", " ".join(row[0].split()), flags=re.IGNORECASE)
    return f"{name}, {row[1]}" if row[1] else name


def _the(title: str) -> str:
    """The Act's title as it reads mid-sentence.

    Stored titles carry their own leading "The" and sometimes a trailing
    full stop, both of which land wrong inside "Section 138 of ...".
    """
    title = title.rstrip(".").strip()
    if title.startswith("The "):
        return "the " + title[4:]
    if title.lower().startswith("the "):
        return title
    return f"the {title}"
