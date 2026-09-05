"""What a drafted document is, before it is a file.

The model returns this shape and nothing else. Everything a reader sees --
the letterhead, the formal opening, the clause numbering, the signature
block -- lives in the .docx template, so the model is asked only for the
parts that differ between two matters.

`warnings` and `needs_input` are not decoration. A draft is a document
someone may sign and send, so a draft that is the wrong instrument for the
matter, or that cannot be sent until an advocate supplies their enrolment
number, must say so where the reader cannot miss it. Same rule the rest of
the system follows: a thing we could not settle never renders like a thing
we settled.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Party:
    name: str
    address: str = ""


@dataclass(frozen=True)
class Ground:
    """One thing the law provides, with the identifier it rests on.

    `authority` is a document id from the corpus, validated against what was
    actually retrieved. An invented citation in a notice that gets sent is
    the worst failure this feature has.
    """

    text: str
    authority: str


@dataclass(frozen=True)
class Demand:
    what: str
    within_days: int = 15
    # Left as words rather than a date: the clock runs from receipt, which
    # nobody knows on the day of drafting.
    from_when: str = "receipt of this notice"


@dataclass(frozen=True)
class DraftStructure:
    document_type: str
    subject: str
    recipient: Party
    sender: Party
    facts: tuple[str, ...] = ()
    grounds: tuple[Ground, ...] = ()
    demand: Demand | None = None
    consequence: str = ""

    # An opinion ends in one; a notice makes a demand instead.
    conclusion: str = ""
    annexures: tuple[str, ...] = ()

    # What an advocate must supply before this can be sent.
    needs_input: tuple[str, ...] = ()

    # Why this draft may be the wrong document, or unsafe to send as it is.
    warnings: tuple[str, ...] = ()

    # Filled from the record, never by the model: the amount demanded must
    # equal the cheque exactly, and a rupee's difference invalidates the
    # notice (Kaveri Plastics v Mahdoom Bawa, SC 2025).
    values: dict[str, str] = field(default_factory=dict)
