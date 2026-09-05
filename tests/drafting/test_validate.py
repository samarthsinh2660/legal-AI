"""The checks a draft must pass before it becomes a file.

Deterministic on purpose: every defect here is mechanical, and a regex
catches it every time where a review call catches it most of the time. The
cases below are real output from the drafting prompt as it was developed --
v1 failed them, v3 passes.
"""

from legal_ai.drafting.models import Demand, DraftStructure, Ground, Party
from legal_ai.drafting.validate import validate

RETRIEVED = {"act:2189:sec-138", "act:2189:sec-139", "act:2189:sec-142"}


def _draft(**overrides) -> DraftStructure:
    base = dict(
        document_type="s138_demand_notice",
        subject="Notice under Section 138",
        recipient=Party(name="Mr. Rohan Malhotra", address="B-14, Green Park, Delhi"),
        sender=Party(name="Mr. Arjun Verma", address="44, Nizamuddin East, Delhi"),
        facts=("You issued cheque no. 0472913 in favour of my client for {{amount}}.",),
        grounds=(Ground(text="Dishonour is an offence.", authority="act:2189:sec-138"),),
        demand=Demand(what="pay my client the sum of {{amount}}"),
        consequence="Criminal prosecution will follow.",
    )
    base.update(overrides)
    return DraftStructure(**base)


def test_a_clean_draft_passes():
    assert validate(_draft(), RETRIEVED) == []


def test_a_citation_that_was_never_retrieved_is_caught():
    """The worst failure this feature has: an invented authority in a
    document someone signs and sends."""
    draft = _draft(
        grounds=(Ground(text="Something.", authority="act:9999:sec-1"),)
    )

    assert any("not retrieved" in failure for failure in validate(draft, RETRIEVED))


def test_a_ground_carrying_a_citation_but_no_text_is_caught():
    draft = _draft(grounds=(Ground(text="   ", authority="act:2189:sec-142"),))

    assert any("no text" in failure for failure in validate(draft, RETRIEVED))


def test_a_currency_mark_beside_the_token_is_caught():
    """The template supplies the symbol. Both writing it renders "Rs. Rs."."""
    draft = _draft(demand=Demand(what="pay Rs. {{amount}} forthwith"))

    assert any("currency mark" in failure for failure in validate(draft, RETRIEVED))


def test_an_amount_written_as_a_figure_is_caught():
    """A demand that does not equal the cheque exactly invalidates the
    notice, so the figure is never the drafter's to write."""
    draft = _draft(demand=Demand(what="pay Rs. 5,00,000 forthwith"))

    assert any("figure" in failure for failure in validate(draft, RETRIEVED))


def test_reciting_a_notice_as_already_sent_is_caught():
    """The document is itself the demand; this made it cite itself."""
    draft = _draft(
        facts=("A statutory demand notice was sent on 2 August 2026.",)
    )

    assert any("already sent" in failure for failure in validate(draft, RETRIEVED))


def test_a_missing_address_must_at_least_be_asked_for():
    draft = _draft(recipient=Party(name="Mr. Rohan Malhotra", address=""))

    assert any("does not ask for one" in failure for failure in validate(draft, RETRIEVED))


def test_a_placeholder_address_counts_as_missing():
    draft = _draft(recipient=Party(name="X", address="[Address not on file]"))

    assert any("does not ask for one" in failure for failure in validate(draft, RETRIEVED))


def test_a_missing_address_that_is_asked_for_passes():
    draft = _draft(
        recipient=Party(name="X", address="[Address not on file]"),
        needs_input=("Complete address of the drawer, for service",),
    )

    assert validate(draft, RETRIEVED) == []


def test_a_draft_with_no_facts_or_grounds_is_caught():
    draft = _draft(facts=(), grounds=(), demand=None)
    failures = validate(draft, RETRIEVED)

    assert any("no facts" in f for f in failures)
    assert any("no provision" in f for f in failures)
    assert any("demands nothing" in f for f in failures)


def test_ordinary_legal_prose_is_not_mistaken_for_an_amount():
    """"two years," matched the money check: it read the "rs" in "years"
    as "Rs" and accepted the bare comma after it as the figure. Real text,
    from the drafting prompt's own output."""
    draft = _draft(
        consequence=(
            "punishable with imprisonment for a term which may extend to two "
            "years, or with fine which may extend to twice the amount of the "
            "cheque, or both."
        )
    )

    assert validate(draft, RETRIEVED) == []


def test_a_figure_in_a_citation_or_a_date_is_not_an_amount():
    draft = _draft(
        subject="Notice under Section 138 of the Negotiable Instruments Act, 1881",
        facts=("The cheque dated 12 July 2026 for {{amount}} was returned unpaid.",),
    )

    assert validate(draft, RETRIEVED) == []
