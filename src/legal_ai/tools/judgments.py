"""Query tools for Supreme Court / High Court judgments.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.

search_judgments returns up to `limit` Evidence. At limit=1 it is a lookup
-- the caller knows the case name. Above one it is discovery, and only the
full-text source can serve it: the archive index carries no subject,
headnote or keyword column, so a query phrased as an issue has nothing to
match there.
"""

from __future__ import annotations

from legal_ai.ingestion.judgments.dynamic_search import _search_indian_kanoon
from legal_ai.ingestion.judgments.dynamic_search import search_judgments as _search
from legal_ai.ingestion.judgments.store import store_judgment
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.retrieval.evidence_builder import to_evidence
from legal_ai.schemas.evidence import Evidence


def search_judgments(
    query: str,
    year: int | tuple[int, int] | None = None,
    limit: int = 1,
    store: bool = True,
    skip_db: bool = False,
    live: bool = True,
) -> list[Evidence]:
    """`skip_db=True` forces a fresh live search even if a cached DB
    match exists — use when a previous cached match turned out to be the
    wrong document (see dynamic_search.search_judgment's docstring).

    `live=False` restricts the search to what is already stored. Interactive
    callers should pass it: the live path scans every archive partition when
    no court is given, measured at 228s for a query that found nothing."""
    result = _search(query, year=year, limit=limit, skip_db=skip_db, live=live)
    if not result.found:
        return []

    if store and result.source != "database" and result.verified:
        for document in result.documents:
            store_judgment(document)

    return [to_evidence(document) for document in result.documents]


def get_judgment(document_id: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, document_id)
    finally:
        conn.close()
    return to_evidence(doc) if doc is not None else None


def discover_judgments(
    question: str,
    section_queries: list[str] | None = None,
    court: str | None = None,
    limit: int = 5,
    store: bool = True,
) -> list[Evidence]:
    """Judgments about an *issue*, for a question that names no case.

    This is the gap the lazy fetch path never covered. That path finds a
    judgment you can already name -- the archive index carries only court,
    year, judge, party, citation and CNR, with no subject column, so
    "cases about drugs" has nothing there to match. Full-text search is the
    only route from an issue to a case name, which is why it is the source
    here rather than the last resort it is in search_judgments.

    Two queries run, not one, because they were measured to find different
    things. On "bail in drug cases" the question's own wording returned
    Tofan Singh and Noor Aga -- the doctrine -- while the provision,
    "Section 37 Narcotic Drugs and Psychotropic Substances Act", returned
    Kerala v Rajesh and Rattan Mallik, the bail authorities the question
    actually asked for. They barely overlapped, so neither replaces the
    other and both feed the fusion.

    Results interleave by rank rather than being concatenated, so the best
    hit from each query sits near the top and neither buries the other.

    Stored by default: a judgment fetched once should answer locally the
    next time, and storing it is what builds the CITES_SECTION edges that
    let the graph eventually answer without going out at all.
    """
    queries = [question] + list(section_queries or [])

    per_query: list[list] = []
    for query in queries:
        try:
            per_query.append(_search_indian_kanoon(query, limit=limit, court=court))
        except Exception:
            # One failing query must not lose the others -- a third party
            # being slow is not a reason to answer with nothing.
            per_query.append([])

    merged = []
    seen: set[str] = set()
    for position in range(max((len(found) for found in per_query), default=0)):
        for found in per_query:
            if position >= len(found):
                continue
            document = found[position]
            if document.document_id in seen:
                continue
            seen.add(document.document_id)
            merged.append(document)
            if len(merged) >= limit:
                break
        if len(merged) >= limit:
            break

    if store:
        for document in merged:
            try:
                store_judgment(document)
            except Exception:
                # Storing is corpus growth, not the answer. Failing to
                # cache must not cost the caller the judgment itself.
                continue

    return [to_evidence(document) for document in merged]
