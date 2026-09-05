"""The checks a draft must pass before it becomes a file.

Deterministic on purpose: every defect here is mechanical, and a regex
catches it every time where a review call catches it most of the time.
"""

from legal_ai.drafting.models import DraftStructure, Paragraph, Section
from legal_ai.drafting.validate import validate

RETRIEVED = {"act:2189:sec-138", "act:ipc-1860:sec-120A"}


def _draft(**overrides) -> DraftStructure:
    base = dict(
        title="NOTICE UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881",
        sections=(
            Section(
                heading="FACTS",
                paragraphs=(Paragraph(text="You issued cheque no. 0472913."),),
            ),
            Section(
                heading="THE POSITION",
                paragraphs=(
                    Paragraph(
                        text="Dishonour for insufficiency of funds is an offence.",
                        authorities=("act:2189:sec-138",),
                    ),
                ),
            ),
        ),
    )
    base.update(overrides)
    return DraftStructure(**base)


def test_a_clean_draft_passes():
    assert validate(_draft(), RETRIEVED) == []


def test_a_citation_that_was_never_retrieved_is_caught():
    """The worst failure this feature has: an invented authority in a
    document someone signs and sends."""
    draft = _draft(
        sections=(
            Section("THE POSITION", (Paragraph("X", ("act:9999:sec-1",)),)),
        )
    )

    assert any("not retrieved" in f for f in validate(draft, RETRIEVED))


def test_reciting_the_step_the_document_is_taking_is_caught():
    """A notice that says a notice was sent cites itself."""
    draft = _draft(
        sections=(
            Section("FACTS", (Paragraph("A demand notice was sent on 2 August 2026."),)),
            Section("THE POSITION", (Paragraph("X", ("act:2189:sec-138",)),)),
        )
    )

    assert any("already" in f for f in validate(draft, RETRIEVED))


def test_a_document_resting_on_no_law_is_caught():
    draft = _draft(sections=(Section("FACTS", (Paragraph("Something happened."),)),))

    assert any("rests on no law" in f for f in validate(draft, RETRIEVED))


def test_a_document_with_no_paragraphs_is_caught():
    assert any("no paragraphs" in f for f in validate(_draft(sections=()), RETRIEVED))


def test_a_document_with_no_title_is_caught():
    assert any("no title" in f for f in validate(_draft(title="  "), RETRIEVED))


def test_an_opinion_on_pure_law_needs_no_facts():
    """A question asked in the abstract has no facts, and inventing some
    would be worse than having none."""
    draft = _draft(
        title="LEGAL OPINION",
        sections=(
            Section(
                "THE POSITION",
                (Paragraph("Conspiracy needs an agreement.", ("act:ipc-1860:sec-120A",)),),
            ),
        ),
    )

    assert validate(draft, RETRIEVED) == []


def test_ordinary_legal_prose_is_not_mistaken_for_a_defect():
    """"two years," once matched a money check that read the "rs" in
    "years" as a currency mark."""
    draft = _draft(
        sections=(
            Section(
                "THE POSITION",
                (
                    Paragraph(
                        "Punishable with imprisonment which may extend to two "
                        "years, or with fine which may extend to twice the "
                        "amount of the cheque, or both.",
                        ("act:2189:sec-138",),
                    ),
                ),
            ),
        )
    )

    assert validate(draft, RETRIEVED) == []
