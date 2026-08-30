"""Guarantee a provision a place in the results.

Measured 2026-08-29 on the versioned 50-question set:

    sections only    MRR 0.469   recall@10 78%
    whole corpus     MRR 0.325   recall@10 56%

The corpus went from 18 judgments to 10,505, and judgments now fill the top
of the list for questions whose answer is a section. They are not junk: on a
RERA possession question the judgments outranking s.18 were Laureate
Buildwell, Ireo Grace and Newtech Promoters -- the leading authorities on the
point. The defect is one-sidedness. A reader asking what the law says needs
the provision *and* the cases, and was getting only cases.

Reserving a slot rather than filtering by predicted intent, for two reasons.
Intent classification would need a model call on the hot path and would be
wrong sometimes, and being wrong there removes a whole category from the
answer. And most legal questions genuinely want both -- the provision to
know the rule, the judgments to know what courts made of it -- so guessing
which the reader "meant" answers a question they did not ask.

Ordering only. Nothing is filtered out, and no result is invented.
"""

from __future__ import annotations

from itertools import zip_longest

_STATUTE_TYPES = frozenset({"act", "section"})


def apply_type_floor(
    ranked_ids: list[str], types: dict[str, str], limit: int
) -> list[str]:
    """`ranked_ids` cut to `limit`, interleaved so both kinds stay in view.

    The strongest result keeps rank 1 whatever it is -- retrieval's best
    answer is not demoted for balance. Below that, statutes and judgments
    alternate, each in its own order, so the best provision surfaces near
    the top instead of behind ten judgments, and the best judgments surface
    near the top instead of behind ten sections.

    This serves both questions rather than guessing between them. A reader
    asking what the law says gets the provision *and* what courts made of
    it; a reader asking what courts have held gets the holdings *and* the
    provision they turn on. Whichever they wanted is high either way, which
    is why this needs no intent classifier on the hot path.

    Whichever side runs out, the other fills the remaining slots, so a list
    of one kind is returned in its original order.
    """
    if not ranked_ids:
        return []

    statutes = [i for i in ranked_ids if types.get(i) in _STATUTE_TYPES]
    others = [i for i in ranked_ids if types.get(i) not in _STATUTE_TYPES]
    if not statutes or not others:
        return ranked_ids[:limit]

    lead = ranked_ids[0]
    lead_is_statute = types.get(lead) in _STATUTE_TYPES
    (statutes if lead_is_statute else others).remove(lead)

    merged = [lead]
    # Alternate away from whatever led, so the other kind is next.
    first, second = (others, statutes) if lead_is_statute else (statutes, others)
    for a, b in zip_longest(first, second):
        if a is not None:
            merged.append(a)
        if b is not None:
            merged.append(b)
    return merged[:limit]
