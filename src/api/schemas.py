"""The wire contract.

`AnswerModel` mirrors `schemas/answer.py::DraftAnswer` field for field, and
the reason it is a separate model rather than a serialised dataclass is that
the dataclass has no stable JSON form -- adding a field there would silently
change the wire, and a frozen tuple of `Claim` objects is not JSON at all.

The three flagged slots stay three slots. Collapsing `needs_verification`,
`partially_supported` and `unchecked` into one list would be the tidier
JSON and would destroy the distinction the whole verification phase exists
to draw: evidence against a claim, evidence narrower than a claim, and no
evidence looked at. A client cannot re-derive them once merged.
"""

from __future__ import annotations

from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

from legal_ai.schemas.answer import DraftAnswer


class ResearchRequest(BaseModel):
    """One question, optionally scoped to a case and its documents."""

    # Capped because the question is embedded in every downstream agent
    # prompt: an unbounded string is an unbounded token bill per request,
    # multiplied by the research fan-out.
    question: str = Field(min_length=1, max_length=4000)
    case_id: Optional[str] = None
    document_ids: list[str] = Field(default_factory=list, max_length=50)

    # None means "use the configured default" rather than "quick", so the
    # deployment's Configuration stays the single place that decides.
    verification_level: Optional[Literal["quick", "verified"]] = None

    @field_validator("question")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class ClaimModel(BaseModel):
    text: str
    evidence_ids: list[str]
    paragraph: Optional[int] = None


class AnswerModel(BaseModel):
    question: str
    lede: str
    key_elements: list[ClaimModel]
    applicable_law: list[str]
    key_judgments: list[str]
    needs_verification: list[str]
    unchecked: list[str]
    partially_supported: list[str]
    support_not_checked: bool
    citations: list[str]
    disclaimer: str

    @classmethod
    def of(cls, answer: DraftAnswer) -> "AnswerModel":
        return cls(
            question=answer.question,
            lede=answer.lede,
            key_elements=[
                ClaimModel(
                    text=claim.text,
                    evidence_ids=list(claim.evidence_ids),
                    paragraph=claim.paragraph,
                )
                for claim in answer.key_elements
            ],
            applicable_law=list(answer.applicable_law),
            key_judgments=list(answer.key_judgments),
            needs_verification=list(answer.needs_verification),
            unchecked=list(answer.unchecked),
            partially_supported=list(answer.partially_supported),
            support_not_checked=answer.support_not_checked,
            citations=list(answer.citations),
            disclaimer=answer.disclaimer,
        )


class ResearchResponse(BaseModel):
    """Either an answer or the question we need answered first.

    The clarification halt is a real graph outcome, not an error: a missing
    fact can make a question unanswerable, and researching it anyway wastes
    the run. It is reported as a 200 with `answer` null because nothing went
    wrong -- returning a 4xx would tell the client to fix its request when
    what is needed is the user's next sentence.
    """

    answer: Optional[AnswerModel] = None
    clarification_needed: Optional[str] = None

    # The plain-text rendering the graph has always produced, for clients
    # with no UI. Never the only thing returned: prose cannot show which
    # claims were checked.
    text: Optional[str] = None

    # Echoed so a client can tell which mode actually ran, rather than
    # assuming its request was honoured.
    verification_level: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: bool
    neo4j: bool


T = TypeVar("T")


class Success(BaseModel, Generic[T]):
    """The success envelope. Declared on a route as `Success[Payload]` so
    `/docs` shows the shape a client actually receives."""

    success: Literal[True] = True
    data: T


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Every error body. `code` is what a client branches on and stays
    stable when the wording changes."""

    success: Literal[False] = False
    error: ErrorDetail
