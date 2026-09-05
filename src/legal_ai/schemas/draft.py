"""What a drafted document is, before it is a file.

Deliberately one shape for every document. An earlier version carried a
type per instrument -- a s.138 demand notice, with its own template, its own
prompt and a rule deciding which conversations it fitted. That does not
scale past the first document: Indian practice has hundreds, and a registry
of them answers "no document fits this thread" to almost every question
anyone asks.

So a document here is a title and a list of sections, and the sections are
whatever this conversation needs. A demand notice, an opinion, a reply, a
memo -- all of them are headings with numbered paragraphs under them, and
the model decides which headings this matter calls for.

`warnings` and `needs_input` are not decoration. A draft is a document
someone may sign and send, so one that is the wrong instrument for the
matter, or that cannot be used until an advocate supplies their enrolment
number, must say so where the reader cannot miss it. Same rule the rest of
the system follows: a thing we could not settle never renders like a thing
we settled.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Paragraph:
    """One numbered paragraph, with the law it rests on.

    `authorities` are document ids from the corpus, checked against what the
    conversation actually retrieved. An invented citation in a document that
    gets sent is the worst failure this feature has.
    """

    text: str
    authorities: tuple[str, ...] = ()


@dataclass(frozen=True)
class Section:
    """A heading and the paragraphs under it.

    The heading is the model's, because what a document needs is a fact
    about the document -- "FACTS", "THE POSITION", "DEMAND", "PRAYER" --
    and fixing the list here is what made the last design specific to one
    instrument.
    """

    heading: str
    paragraphs: tuple[Paragraph, ...] = ()


@dataclass(frozen=True)
class DraftStructure:
    # What the document is called at the top of the page, e.g. "LEGAL
    # OPINION" or "NOTICE UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS
    # ACT, 1881". The model names it, because naming it is choosing it.
    title: str
    subject: str = ""

    # Who it is addressed to, where the document is addressed to anyone. An
    # opinion has a client; a notice has a recipient; a memo has neither.
    addressed_to: str = ""
    on_behalf_of: str = ""

    sections: tuple[Section, ...] = ()

    # What an advocate must supply before this can be used.
    needs_input: tuple[str, ...] = ()

    # Why this draft may be the wrong document, or unsafe to send as it is.
    warnings: tuple[str, ...] = ()
