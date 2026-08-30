"""Query tools over the judgment/statute citation graph.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.

Matches come from Neo4j, which holds only document_id/title, so each needs
a Postgres round-trip via get_document to fill Evidence.content.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.retrieval.authority import Authority, rank_by_authority
from legal_ai.retrieval.conflict import MIN_MENTIONS
from legal_ai.retrieval.evidence_builder import to_evidence
from legal_ai.retrieval.good_law import GoodLawResult
from legal_ai.schemas.evidence import Evidence


def _resolve_all(document_ids: list[str]) -> list[Evidence]:
    if not document_ids:
        return []
    conn = get_connection()
    try:
        docs = [get_document(conn, doc_id) for doc_id in document_ids]
    finally:
        conn.close()
    return [to_evidence(doc) for doc in docs if doc is not None]


def find_citations(judgment_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:Judgment {document_id: $id})-[:CITES]->(b:Judgment)
                RETURN b.document_id AS document_id
                """,
                id=judgment_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_section_citations(section_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment)-[:CITES_SECTION]->(s:Section {document_id: $id})
                RETURN j.document_id AS document_id
                """,
                id=section_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_judgment_sections(judgment_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment {document_id: $id})-[:CITES_SECTION]->(s:Section)
                RETURN s.document_id AS document_id
                """,
                id=judgment_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_leading_authorities(section_id: str, limit: int = 5) -> list[Evidence]:
    """The judgments on `section_id` that carry the most authority.

    find_section_citations returns everything citing a section in no
    meaningful order. This ranks them, which is the difference between a
    list and an answer: on a heavily-litigated provision the first is
    dozens of judgments a reader must triage themselves.

    Ranking is legal_ai.retrieval.authority -- citation count first, bench
    size as the tie-breaker. Both come from data already stored: CITES
    in-degree from Neo4j, bench_size from the backfilled column.

    Citation counts are computed over the stored corpus only. A judgment
    cited a thousand times in the reports shows zero here if we hold none
    of the citing cases, so this ranks what we can see, not the law.
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment)-[r:CITES_SECTION]->(:Section {document_id: $id})
                WHERE coalesce(r.mentions, 1) >= $min_mentions
                OPTIONAL MATCH (citing:Judgment)-[:CITES]->(j)
                RETURN j.document_id AS document_id,
                       count(DISTINCT citing) AS citation_count
                """,
                id=section_id,
                min_mentions=MIN_MENTIONS,
            )
            counts = {r["document_id"]: r["citation_count"] for r in result}
    finally:
        driver.close()

    if not counts:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT document_id, bench_size FROM documents "
            "WHERE document_id = ANY(%s)",
            (list(counts),),
        ).fetchall()
    finally:
        conn.close()

    ranked = rank_by_authority(
        [
            Authority(
                document_id=document_id,
                citation_count=counts.get(document_id, 0),
                bench_size=bench_size,
            )
            for document_id, bench_size in rows
        ]
    )
    return _resolve_all([item.document_id for item in ranked[:limit]])


def find_court_split(section_id: str) -> "ConflictFinding":
    """Whether the courts that have ruled on `section_id` disagree.

    Two steps, cheap first: the graph picks the strongest judgment from each
    of a few courts (legal_ai.retrieval.conflict), then one model call reads
    those holdings and says whether they can stand together
    (legal_ai.agents.conflict).

    NOT_CHECKED when fewer than two courts have ruled on the provision in
    the stored corpus. That is the common case: High Court coverage is
    thin, and a section litigated in one court here may be litigated in ten
    in the reports.
    """
    from legal_ai.agents.conflict import ConflictFinding, ConflictStatus, check_conflict
    from legal_ai.retrieval.conflict import CourtHolding, select_candidates

    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment)-[r:CITES_SECTION]->(:Section {document_id: $id})
                WHERE coalesce(r.mentions, 1) >= $min_mentions
                OPTIONAL MATCH (citing:Judgment)-[:CITES]->(j)
                RETURN j.document_id AS document_id,
                       count(DISTINCT citing) AS citation_count
                """,
                id=section_id,
                min_mentions=MIN_MENTIONS,
            )
            counts = {r["document_id"]: r["citation_count"] for r in result}
    finally:
        driver.close()

    if len(counts) < 2:
        return ConflictFinding(ConflictStatus.NOT_CHECKED, "fewer than two judgments stored")

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT document_id, court, bench_size, full_text FROM documents "
            "WHERE document_id = ANY(%s)",
            (list(counts),),
        ).fetchall()
    finally:
        conn.close()

    holdings = [
        CourtHolding(
            document_id=document_id,
            court=court or "",
            passage=text or "",
            authority=Authority(document_id, counts.get(document_id, 0), bench_size),
        )
        for document_id, court, bench_size, text in rows
    ]
    candidates = select_candidates(holdings)
    if not candidates:
        return ConflictFinding(ConflictStatus.NOT_CHECKED, "only one court has ruled")
    return check_conflict(candidates)


def is_still_good_law(judgment_id: str) -> "GoodLawResult":
    """Whether any later judgment held `judgment_id` wrongly decided.

    Reads the treatments written onto CITES edges by
    `scripts/classify_treatments.py`. Unclassified edges come back as
    NOT_CHECKED and taint the whole answer, so this returns a clean bill
    only when every citing judgment in the corpus was actually classified.

    NOT_CHECKED is the ordinary answer today: classification runs
    incrementally against a free-tier quota, and most edges have not been
    reached. That is the honest state, and it must not be softened into
    "no negative treatment" -- the whole value of this check is that its
    green light means something.
    """
    from legal_ai.agents.treatment import Treatment
    from legal_ai.retrieval.good_law import assess_good_law

    driver = get_driver()
    try:
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (citing:Judgment)-[r:CITES]->(:Judgment {document_id: $id})
                RETURN citing.document_id AS document_id, r.treatment AS treatment
                """,
                id=judgment_id,
            ).values()
    finally:
        driver.close()

    citing = []
    for document_id, treatment in rows:
        try:
            parsed = Treatment(treatment) if treatment else Treatment.NOT_CHECKED
        except ValueError:
            parsed = Treatment.NOT_CHECKED
        citing.append((document_id, parsed))
    return assess_good_law(citing)
