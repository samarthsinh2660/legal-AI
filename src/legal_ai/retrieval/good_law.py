"""Whether a judgment still stands as authority.

The reader-facing half of treatment classification. `agents/treatment.py`
says how each later judgment dealt with this one; this turns those into the
answer a lawyer wants: can I still rely on it?

Three states, and the third carries the weight. A corpus that resolves a
fraction of the citations it extracts sits in NOT_CHECKED far more often
than in a clean bill of health, and collapsing the two would ship the most
dangerous defect this system could: a confident green light nobody verified.
That is the same distinction Phase 6 drew between UNSUPPORTED and
INSUFFICIENT_EVIDENCE, for the same reason.

The conservative direction here is the opposite of the usual one. Any
citing judgment we failed to classify could be the overruling, so a single
unclassified citation is enough to withhold NO_NEGATIVE_TREATMENT. Only a
positively identified overruling produces DOUBTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import neo4j

from legal_ai.agents.treatment import Treatment


class GoodLaw(str, Enum):
    # A later judgment held it wrongly decided.
    DOUBTED = "DOUBTED"

    # Every citing judgment was classified, and none overruled it. This is
    # a statement about our corpus, never about the reports.
    NO_NEGATIVE_TREATMENT = "NO_NEGATIVE_TREATMENT"

    # Nothing cites it here, or something citing it was never classified.
    NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True)
class GoodLawResult:
    status: GoodLaw
    overruled_by: tuple[str, ...] = field(default_factory=tuple)

    # The citing judgments actually classified. Carried so a caller can
    # state the denominator: "no negative treatment among 4 we hold" is a
    # claim a reader can size, where "no negative treatment" is not.
    checked: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_a_warning(self) -> bool:
        """Whether this should be shown to the reader as a caution.

        Only a found overruling. NOT_CHECKED is the ordinary state of most
        of the corpus, and warning on it would train the reader to ignore
        the warning that matters.
        """
        return self.status is GoodLaw.DOUBTED


def assess_good_law(citing: list[tuple[str, Treatment]]) -> GoodLawResult:
    """The standing of a judgment, given how judgments citing it treated it.

    `citing` is (citing judgment id, treatment). Empty means nothing in the
    corpus cites it, which is NOT_CHECKED -- absence of citing judgments
    here is absence of coverage, not absence of overrulings.
    """
    overruled_by = tuple(
        document_id for document_id, treatment in citing if treatment.is_negative
    )
    if overruled_by:
        return GoodLawResult(GoodLaw.DOUBTED, overruled_by)

    if not citing or any(
        treatment is Treatment.NOT_CHECKED for _document_id, treatment in citing
    ):
        return GoodLawResult(GoodLaw.NOT_CHECKED)

    return GoodLawResult(
        GoodLaw.NO_NEGATIVE_TREATMENT,
        checked=tuple(document_id for document_id, _t in citing),
    )


def good_law_lookup(
    driver: "neo4j.Driver", judgment_ids: list[str]
) -> dict[str, GoodLawResult]:
    """Standing for several judgments in one traversal.

    The per-judgment `tools.graph.is_still_good_law` opens and closes a
    driver per call, which is right for an agent tool asking about one
    authority and wrong for an answer citing several. Ids with no citing
    judgment in the corpus come back NOT_CHECKED, which is the honest
    reading: nothing here cites it, so nothing here overruled it either.
    """
    if not judgment_ids:
        return {}

    with driver.session() as session:
        rows = session.run(
            """
            MATCH (citing:Judgment)-[r:CITES]->(cited:Judgment)
            WHERE cited.document_id IN $ids
            RETURN cited.document_id AS cited, citing.document_id AS citing,
                   r.treatment AS treatment
            """,
            ids=list(judgment_ids),
        ).values()

    citing: dict[str, list[tuple[str, Treatment]]] = {i: [] for i in judgment_ids}
    for cited, citing_id, treatment in rows:
        try:
            parsed = Treatment(treatment) if treatment else Treatment.NOT_CHECKED
        except ValueError:
            # An unreadable value is not a reading. Treating it as anything
            # else would let a typo in the graph clear a judgment.
            parsed = Treatment.NOT_CHECKED
        citing[cited].append((citing_id, parsed))
    return {i: assess_good_law(found) for i, found in citing.items()}
