"""Which judgments to put in front of a conflict check.

A reader asking about a provision needs to know when courts have split on
it. Today they get whichever judgment ranked highest and no sign that
another High Court holds the opposite -- the disagreement is invisible, and
an answer built on one side of a split reads exactly like an answer built on
settled law.

Finding a split needs two holdings compared, which is a model call. This
module is the cheap half: choosing *which* holdings, so the expensive half
runs once over a handful of judgments rather than over every pair.

Two rules do most of the work:

**One judgment per court.** Two decisions of the same High Court are not a
split, whatever they say -- at worst they are that court's own inconsistency,
which a later bench of it resolves. Comparing them wastes the window.

**A few courts, not all.** Fifty judgments is 1,225 pairs, and nearly every
pair is one court agreeing with itself. Capping the courts bounds the cost
to something a single call can hold.
"""

from __future__ import annotations

from dataclasses import dataclass

from legal_ai.retrieval.authority import Authority, rank_by_authority

# Courts compared in one check. Four holdings is a readable answer and a
# window a model can attend to; more turns a split into a survey.
MAX_COURTS = 4

# Times a judgment must invoke a section before it counts as being *about*
# it. CITES_SECTION is created from a regex hit, so one mention is a passing
# reference -- a money-laundering judgment naming NI Act s.138 once is not an
# authority on cheque dishonour. A judgment that turns on a provision returns
# to it, and two is the cheapest line that separates the two cases.
MIN_MENTIONS = 2


@dataclass(frozen=True)
class CourtHolding:
    """One court's position on a provision, and how much it weighs."""

    document_id: str
    court: str
    passage: str
    authority: Authority


def select_candidates(
    holdings: list[CourtHolding], max_courts: int = MAX_COURTS
) -> list[CourtHolding]:
    """The strongest holding from each of up to `max_courts` courts.

    Empty when fewer than two courts are represented: one court on its own
    is not a split, and running a conflict check over it would spend a
    model call to answer a question that has no second side.

    A holding with no court is dropped rather than grouped under "": it
    cannot stand for a court in a disagreement between courts.
    """
    strongest: dict[str, CourtHolding] = {}
    for holding in holdings:
        if not holding.court:
            continue
        current = strongest.get(holding.court)
        if current is None or rank_by_authority(
            [holding.authority, current.authority]
        )[0] is holding.authority:
            strongest[holding.court] = holding

    if len(strongest) < 2:
        return []

    by_authority = rank_by_authority([h.authority for h in strongest.values()])
    order = {authority.document_id: rank for rank, authority in enumerate(by_authority)}
    return sorted(strongest.values(), key=lambda h: order[h.document_id])[:max_courts]
