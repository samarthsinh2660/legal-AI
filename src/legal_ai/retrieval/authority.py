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
