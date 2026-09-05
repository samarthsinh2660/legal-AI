"""A drafted structure becomes a .docx someone can send.

.docx rather than PDF because this is a draft: the advocate puts it on
their own letterhead, adds their enrolment number and signs. Word is the
format of the drafting stage precisely because it can be edited.
"""

from datetime import date

from docx import Document
import io
import pytest

from legal_ai.drafting.models import Demand, DraftStructure, Ground, Party
from legal_ai.drafting.render import UNFILLED, render


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


def _text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


def test_the_amount_is_filled_from_the_record_not_the_model():
    """The sum demanded must equal the cheque exactly -- a rupee's
    difference invalidates the notice -- so the drafter only ever writes a
    token and the figure comes from the record."""
    data = render(_draft(values={"amount": "Rs. 5,00,000/-"}))

    body = _text(data)
    assert "Rs. 5,00,000/-" in body
    assert "{{amount}}" not in body


def test_an_amount_we_do_not_hold_renders_as_a_blank_to_complete():
    """A token printed in a notice reads as a bug; a ruled blank reads as
    a field somebody has to fill, which it is."""
    body = _text(render(_draft(values={})))

    assert UNFILLED in body
    assert "{{amount}}" not in body


def test_a_raw_document_id_never_reaches_the_body():
    """`act:2189:sec-138` is how this system addresses a provision, not how
    a notice cites one. The first rendered draft printed it to opposing
    counsel."""
    body = _text(render(_draft(), citations={
        "act:2189:sec-138": "Section 138 of the Negotiable Instruments Act, 1881"
    }))

    assert "act:2189:sec-138" not in body
    assert "Section 138 of the Negotiable Instruments Act, 1881" in body


def test_an_unresolvable_citation_is_dropped_rather_than_printed():
    body = _text(render(_draft(), citations={}))

    assert "act:2189:sec-138" not in body
    assert "Dishonour is an offence." in body


def test_a_placeholder_address_renders_as_a_blank():
    body = _text(render(_draft(recipient=Party(name="X", address="[Address not on file]"))))

    assert "[Address not on file]" not in body
    assert UNFILLED in body


def test_warnings_and_missing_inputs_reach_the_document():
    """A draft that may be the wrong instrument has to say so where the
    reader cannot miss it."""
    body = _text(render(_draft(
        warnings=("The limitation period under Section 142 may have lapsed.",),
        needs_input=("Advocate's enrolment number",),
    )))

    assert "DELETE BEFORE SENDING" in body
    assert "may have lapsed" in body
    assert "enrolment number" in body


def test_a_clean_draft_carries_no_drafting_notes_page():
    body = _text(render(_draft()))

    assert "DELETE BEFORE SENDING" not in body


def test_an_unknown_document_type_is_a_programming_error():
    with pytest.raises(FileNotFoundError):
        render(_draft(document_type="not_a_template"))


def test_the_date_is_the_day_it_was_drafted():
    body = _text(render(_draft(), today=date(2026, 9, 5)))

    assert "05 September 2026" in body
