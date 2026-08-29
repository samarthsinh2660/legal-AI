"""How much authority a judgment carries.

Phase 7's first question: of the judgments that answer a query, which one
actually matters? Retrieval ranks by relevance, which cannot tell a
Constitution Bench followed for thirty years from a single-judge order
nobody has cited. Both are "about" the section; only one settles it.

Two signals, kept apart on purpose:

  citation_count -- how many stored judgments cite this one. Influence:
      what practitioners actually follow. Soft, and it moves with corpus
      coverage, so it is a measurement of our shelf as much as of the law.

  bench_size -- how many judges sat. Binding force, and a hard rule rather
      than a popularity signal: a larger bench binds a smaller one whether
      or not anyone has cited it.

Blending them into one score would hide which is driving an order, so they
are ranked lexicographically instead -- citations first, bench as the
tie-breaker. See rank_by_authority for why that way round.

A zero citation_count means nothing in *our corpus* cites it. With the
corpus resolving a small fraction of the references it extracts, that is
the ordinary case and not a finding about the judgment.
"""

from __future__ import annotations

from dataclasses import dataclass

# Five judges is the constitutional threshold: Article 145(3) requires at
# least five for a substantial question of constitutional law.
CONSTITUTION_BENCH = 5


@dataclass(frozen=True)
class Authority:
    """What is known about one judgment's weight."""

    document_id: str
    citation_count: int = 0

    # None means the bench could not be read, NOT that it was one judge.
    bench_size: int | None = None

    @property
    def is_constitution_bench(self) -> bool:
        return self.bench_size is not None and self.bench_size >= CONSTITUTION_BENCH


def rank_by_authority(items: list[Authority]) -> list[Authority]:
    """Strongest first.

    Citations lead and bench breaks ties, rather than the other way round.
    Bench size is the stronger *legal* signal, but ordering by it first
    would put an uncited five-judge bench above the two-judge decision the
    profession actually follows on the question asked -- and the reader is
    looking for the governing authority on this point, not the largest
    bench in the corpus. Bench is surfaced on every result so a caller can
    say "and this one binds", which is the honest way to show it.

    Nothing is filtered. An uncited judgment ranks last but is still
    returned: with a thin corpus, absence of citations is absence of
    evidence.
    """
    return sorted(
        items,
        key=lambda x: (-x.citation_count, -(x.bench_size or 0), x.document_id),
    )


def authority_lookup(driver, conn, document_ids: list[str]) -> dict[str, Authority]:
    """Authority for each of `document_ids` that is a stored judgment.

    Two reads because the two signals live in two stores: CITES in-degree
    from Neo4j, bench_size from Postgres. Ids that are not judgments, or
    are not held, are simply absent -- callers rank a missing id as
    uncited rather than dropping it.
    """
    if not document_ids:
        return {}

    with driver.session() as session:
        rows = session.run(
            """
            MATCH (j:Judgment) WHERE j.document_id IN $ids
            OPTIONAL MATCH (citing:Judgment)-[:CITES]->(j)
            RETURN j.document_id AS document_id,
                   count(DISTINCT citing) AS citation_count
            """,
            ids=list(document_ids),
        )
        counts = {r["document_id"]: r["citation_count"] for r in rows}

    if not counts:
        return {}

    benches = dict(
        conn.execute(
            "SELECT document_id, bench_size FROM documents WHERE document_id = ANY(%s)",
            (list(counts),),
        ).fetchall()
    )
    return {
        document_id: Authority(
            document_id=document_id,
            citation_count=count,
            bench_size=benches.get(document_id),
        )
        for document_id, count in counts.items()
    }
