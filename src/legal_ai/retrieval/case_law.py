"""When a question wants case law, and which court to look in.

Two deterministic decisions, no model call, following the same pattern as
legal_ai.context.clarification: whether a question asks for judgments is a
property of how it is phrased, not an ambiguity a model should weigh.

Keeping it deterministic matters for cost as much as correctness. Case
discovery fetches judgments from a third party, so firing it on every
statute lookup would add outbound requests and seconds to questions that
never wanted a case.
"""

from __future__ import annotations

import re

from legal_ai.context.models import ThreadContext

# Phrasing that asks for judicial authority rather than the text of a
# provision. "What does section 138 say" wants the statute; "what have the
# courts held under section 138" wants the case law.
_WANTS_CASE_LAW = re.compile(
    r"\b(case|cases|case ?law|judgment|judgement|judgments|judgements|"
    r"precedent|precedents|authority|authorities|ruling|rulings|"
    r"held|holding|decided|decision|verdict|"
    r"supreme court|high court|sc |hc |bench|"
    r"landmark|settled law|position of law)\b",
    re.IGNORECASE,
)

# Indian Kanoon's own court filters. The archive index carries no subject
# column, so full-text search is the only path to a case found by issue,
# and these are how that search is narrowed to a court.
_COURT_DOCTYPES: dict[str, str] = {
    "Supreme Court of India": "supremecourt",
    "Delhi High Court": "delhi",
    "Bombay High Court": "bombay",
    "Gujarat High Court": "gujarat",
    "Karnataka High Court": "karnataka",
    "Madras High Court": "chennai",
    "Calcutta High Court": "kolkata",
    "Kerala High Court": "kerala",
    "Rajasthan High Court": "rajasthan",
    "Allahabad High Court": "allahabad",
    "Punjab and Haryana High Court": "punjab",
    "Telangana High Court": "telangana",
    "Andhra Pradesh High Court": "andhra",
    "Patna High Court": "patna",
    "Orissa High Court": "orissa",
    "Gauhati High Court": "gauhati",
}

# Named explicitly in the question, which beats whatever the case file says:
# a Gujarat matter can still turn on a Supreme Court authority.
_EXPLICIT_COURT = (
    (re.compile(r"\bsupreme court\b|\bsc\b|\bapex court\b", re.IGNORECASE), "supremecourt"),
    (re.compile(r"\bdelhi\b", re.IGNORECASE), "delhi"),
    (re.compile(r"\bbombay\b|\bmumbai\b", re.IGNORECASE), "bombay"),
    (re.compile(r"\bgujarat\b|\bahmedabad\b", re.IGNORECASE), "gujarat"),
    (re.compile(r"\bkarnataka\b|\bbangalore\b|\bbengaluru\b", re.IGNORECASE), "karnataka"),
    (re.compile(r"\bmadras\b|\bchennai\b", re.IGNORECASE), "chennai"),
    (re.compile(r"\bcalcutta\b|\bkolkata\b", re.IGNORECASE), "kolkata"),
    (re.compile(r"\bkerala\b", re.IGNORECASE), "kerala"),
)


def wants_case_law(question: str) -> bool:
    """Whether the question asks for judicial authority.

    False is the common case and the cheap one: a statute lookup needs no
    outbound fetch. A false negative costs the user a follow-up question; a
    false positive costs every user seconds and a third-party request, so
    the pattern is written to be specific rather than generous.
    """
    return bool(_WANTS_CASE_LAW.search(question))


def court_filter(question: str, context: ThreadContext | None = None) -> str | None:
    """The court to search, as a full-text filter, or None for all courts.

    A court named in the question wins over the case file's jurisdiction. A
    Gujarat matter routinely turns on a Supreme Court authority, so
    inheriting the case's High Court and searching only there would hide
    the binding precedent.
    """
    for pattern, doctype in _EXPLICIT_COURT:
        if pattern.search(question):
            return doctype

    if context is not None and context.jurisdiction.court:
        return _COURT_DOCTYPES.get(context.jurisdiction.court)
    return None


def section_identifiers(evidence, conn, limit: int = 3) -> list[str]:
    """Retrieved statute Evidence rendered the way a judgment cites it.

    "Section 138 Negotiable Instruments Act, 1881", not the section's
    title. Titles are written for a reader who already knows which Act they
    are in: "Cognizance of offences" and "Power to direct interim
    compensation" say nothing about cheques, and a full-text search built
    from them returns whatever is merely famous. Measured 2026-08-24: bare
    titles returned Kesavananda Bharati for a cheque-bounce question.

    The number is what a judgment actually quotes, so it is the strongest
    handle we have for finding judgments about a provision.
    """
    import re as _re

    from legal_ai.knowledge.static.store import get_document

    out: list[str] = []
    for item in evidence:
        if len(out) >= limit:
            break
        if (item.document_type or "") != "section" or not item.document_id:
            continue
        match = _re.match(r"(act:[^:]+):sec-(.+)", item.document_id)
        if not match:
            continue
        act = get_document(conn, match.group(1))
        if act is None or not act.title:
            continue
        name = act.title.strip()
        if name.lower().startswith("the "):
            name = name[4:]
        out.append(f"Section {match.group(2)} {name}")
    return out
