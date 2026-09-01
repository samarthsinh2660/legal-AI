"""Render a ThreadContext compactly for injection into a prompt.

Every node's prompt carries this, so verbosity is multiplied by the number
of nodes and by the fan-out width. Empty fields are omitted rather than
rendered as "None", which would spend tokens saying nothing.
"""

from __future__ import annotations

from legal_ai.context.models import ThreadContext

# Findings and documents are the two parts of a context that grow without
# bound as a case accumulates. Both are capped, because this string is
# carried by every node's prompt and multiplied by the fan-out width.
MAX_RENDERED_FINDINGS = 10
MAX_RENDERED_DOCUMENTS = 8

# Extracted values shown per field on one document. A bundle listing forty
# dates does not help the researcher choose a query, and the tail is where
# the least load-bearing ones sit.
MAX_VALUES_PER_FIELD = 6


def render(context: ThreadContext) -> str:
    lines = [f"Question: {context.question}"]

    if context.jurisdiction.state:
        lines.append(f"State: {context.jurisdiction.state}")
    if context.jurisdiction.court:
        lines.append(f"Court: {context.jurisdiction.court}")
    if context.relevant_date_from or context.relevant_date_to:
        start = context.relevant_date_from or "any"
        end = context.relevant_date_to or "any"
        lines.append(f"Relevant period: {start} to {end}")
    if context.needs_current_law:
        lines.append("Needs the law as it stands now, not as cached.")
    if context.case_id:
        lines.append(f"Part of case: {context.case_id}")
    if context.case_description:
        # The one line the user wrote about their own matter. It goes in
        # ahead of documents and findings because it is the cheapest context
        # an agent can have and the only one written by a human.
        lines.append(f"The matter: {context.case_description[:600]}")

    if context.documents:
        shown_docs = context.documents[:MAX_RENDERED_DOCUMENTS]
        omitted_docs = len(context.documents) - len(shown_docs)
        lines.append("")
        header = "From the case documents:"
        if omitted_docs:
            header += f" (first {len(shown_docs)}; {omitted_docs} more not shown)"
        lines.append(header)
        for facts in shown_docs:
            lines.append(f"- {facts.document_type or 'document'} [{facts.document_id}]")
            for label, values in (
                ("parties", facts.parties),
                ("dates", facts.dates),
                ("terms", facts.clauses),
                ("asserts", facts.claims),
                ("raises", facts.issues),
                ("cites", facts.cited_sections),
            ):
                if values:
                    lines.append(f"    {label}: " + "; ".join(values[:MAX_VALUES_PER_FIELD]))

    if context.established_findings:
        shown = context.established_findings[-MAX_RENDERED_FINDINGS:]
        omitted = len(context.established_findings) - len(shown)
        lines.append("")
        header = "Already established:"
        if omitted:
            header += f" (most recent {len(shown)}; {omitted} earlier omitted)"
        lines.append(header)
        for finding in shown:
            evidence = ", ".join(finding.evidence_ids)
            lines.append(f"- {finding.claim} [{evidence}]")

    return "\n".join(lines)
