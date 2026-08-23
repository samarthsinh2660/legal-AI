"""Case Agent -- understand the matter, not the question.

The Research Agent is stateless over public law: a question goes in,
evidence comes out, and nothing survives the call. This agent is stateful
over one matter, and that is what lets it answer things research
structurally cannot:

    "Which facts in our documents support the ownership claim?"
        -- the answer is in the user's files, not the corpus.

    "What are we missing?"
        -- twelve years' possession is required, eight are evidenced. That
           gap is only visible holding the legal test and the document
           facts at once. Searching public law cannot find what is absent
           from a private file.

Split the same way every other agent here is:

    timeline, facts,      deterministic. Dates decide limitation, and a
    applicable law,       model that invents one loses a case; ids are
    precedents            copied, never generated.

    issues, missing       one model call. Both need the documents and the
    facts                 law weighed together, and asking twice would
                          cost two calls to answer one question -- the
                          same merge plan_research made in Phase 3.

Control flow is code. The model reasons; it never decides what runs.
"""

from __future__ import annotations

import json

from legal_ai.case.models import Case, CaseAnalysis
from legal_ai.case.timeline import build_timeline
from legal_ai.config import DEFAULT_CONFIG
from legal_ai.context.models import DocumentFacts
from legal_ai.llm.client import generate
from legal_ai.schemas.evidence import Evidence

# Document types that are law rather than authority interpreting it.
_STATUTE_TYPES = frozenset({"act", "section"})

# Everything below caps an input that grows as a matter accumulates. A case
# is a container that only ever gets bigger -- documents, sessions, findings
# -- so any of these left unbounded eventually overruns the window, and the
# failure mode is a silently truncated analysis rather than an error.
#
# These are what make one model call sufficient here. When a real matter
# outgrows them, the answer is the fan-out research already uses -- analyse
# per issue and merge -- not a larger prompt. Nothing has outgrown them yet,
# so that is not built.

# Provisions and authorities shown. A matter with sixty retrieved sections
# does not need all sixty to have its issues named, and the tail is where
# the least relevant results sit.
MAX_LAW_SHOWN = 15

# Documents shown. Structure only, never bodies -- so this bounds a bundle
# of a thousand exhibits to the same prompt size as a bundle of eight.
MAX_DOCUMENTS_SHOWN = 20

# Extracted values per field on one document.
MAX_VALUES_PER_FIELD = 8

# Established findings shown, most recent first. A long-running matter
# accumulates these without limit; the recent ones are the ones a new
# analysis has to stay consistent with.
MAX_FINDINGS_SHOWN = 15

PROMPT = """You are a senior Indian litigator reviewing a case file.

CASE
{case}

FACTS FROM THE CLIENT'S DOCUMENTS
{facts}

LAW AND AUTHORITIES RESEARCHED SO FAR
{law}

ALREADY ESTABLISHED
{findings}

Two tasks.

1. "issues": the distinct legal issues this matter actually raises. Merge
   duplicates. Use the issues the documents raise and the law above -- do
   not invent an issue nothing here supports.

2. "missing_facts": what this matter would need to succeed and the
   documents do NOT show. Be specific and concrete. If the law above sets a
   requirement (a period, a notice, a registration) and no fact above
   satisfies it, that is a missing fact. Say what is needed, not what is
   wrong.

Return ONLY a JSON object:
{{"issues": ["..."], "missing_facts": ["..."]}}

Any list with nothing to report must be empty."""


def _render_case(case: Case) -> str:
    parts = [f"Title: {case.title}"]
    if case.case_number:
        parts.append(f"Case number: {case.case_number}")
    if case.court:
        parts.append(f"Court: {case.court}")
    if case.state:
        parts.append(f"State: {case.state}")
    if case.parties:
        parts.append("Parties: " + ", ".join(case.parties))
    return "\n".join(parts)


def _render_facts(documents: tuple[DocumentFacts, ...]) -> str:
    if not documents:
        return "No documents have been uploaded to this case."
    shown = documents[:MAX_DOCUMENTS_SHOWN]
    lines: list[str] = []
    for facts in shown:
        lines.append(f"[{facts.document_id}] {facts.document_type or 'document'}")
        for label, values in (
            ("parties", facts.parties),
            ("dates", facts.dates),
            ("raises", facts.issues),
            ("cites", facts.cited_sections),
        ):
            if values:
                lines.append(f"  {label}: " + "; ".join(values[:MAX_VALUES_PER_FIELD]))
    omitted = len(documents) - len(shown)
    if omitted:
        lines.append(f"({omitted} further document(s) not shown)")
    return "\n".join(lines)


def _render_law(evidence: list[Evidence]) -> str:
    if not evidence:
        return "No law has been researched for this case yet."
    return "\n".join(
        f"[{item.document_id}] {item.title or ''} -- {item.content[:300]}"
        for item in evidence[:MAX_LAW_SHOWN]
    )


def _render_findings(case: Case) -> str:
    if not case.findings:
        return "Nothing has been established yet."
    shown = case.findings[-MAX_FINDINGS_SHOWN:]
    lines = [f"- {finding.claim}" for finding in shown]
    omitted = len(case.findings) - len(shown)
    if omitted:
        lines.insert(0, f"(most recent {len(shown)}; {omitted} earlier not shown)")
    return "\n".join(lines)


def _parse(raw: str) -> dict:
    """Parse the model's JSON, tolerating a fenced block. {} on anything
    unparseable -- a bad generation must leave the deterministic half of
    the analysis intact rather than taking the case view down."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
    except (ValueError, IndexError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _strings(value) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return ()
    seen: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip() and item.strip() not in seen:
            seen.append(item.strip())
    return tuple(seen)


def _document_facts_summary(documents: tuple[DocumentFacts, ...]) -> tuple[str, ...]:
    """The case's facts, as the documents stated them.

    Assembled, not generated: each entry traces to a document id, so a
    "fact" in the case view is always something a file actually says.
    """
    facts: list[str] = []
    for document in documents:
        for issue in document.issues:
            entry = f"{issue} [{document.document_id}]"
            if entry not in facts:
                facts.append(entry)
    return tuple(facts)


def analyse_case(
    case: Case,
    documents: tuple[DocumentFacts, ...] = (),
    evidence: list[Evidence] | None = None,
) -> CaseAnalysis:
    """Everything the matter amounts to: timeline, facts, issues, law,
    precedents, and what is missing.

    `documents` is what the Document Agent extracted -- structure only,
    never the document body, so a case holding a thousand-page bundle costs
    the same here as one holding a notice.

    `evidence` is what the case's research sessions retrieved. Passing none
    is normal for a case created but not yet researched; the analysis then
    reports the documents and no law, rather than failing.
    """
    evidence = evidence or []

    statutes = [e for e in evidence if (e.document_type or "") in _STATUTE_TYPES]
    judgments = [e for e in evidence if (e.document_type or "") == "judgment"]

    timeline = build_timeline(documents)
    facts = _document_facts_summary(documents)

    issues: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    if documents or evidence:
        # Nothing to reason over on an empty case -- a model call there
        # would invent a matter rather than analyse one.
        try:
            parsed = _parse(
                generate(
                    PROMPT.format(
                        case=_render_case(case),
                        facts=_render_facts(documents),
                        law=_render_law(statutes + judgments),
                        findings=_render_findings(case),
                    ),
                    max_output_tokens=DEFAULT_CONFIG.extraction_model_max_tokens,
                )
            )
        except Exception:
            parsed = {}
        issues = _strings(parsed.get("issues"))
        missing = _strings(parsed.get("missing_facts"))

    if not issues:
        # The model failed or found nothing. The documents' own issues are
        # still real and already extracted, so fall back to them rather
        # than showing a case with no issues at all.
        issues = tuple(dict.fromkeys(i for d in documents for i in d.issues))

    return CaseAnalysis(
        case_id=case.case_id,
        timeline=timeline,
        facts=facts,
        issues=issues,
        applicable_law=tuple(e.document_id for e in statutes if e.document_id),
        precedents=tuple(e.document_id for e in judgments if e.document_id),
        missing_facts=missing,
    )
