"""Render a ThreadContext compactly for injection into a prompt.

Every node's prompt carries this, so verbosity is multiplied by the number
of nodes and by the fan-out width. Empty fields are omitted rather than
rendered as "None", which would spend tokens saying nothing.
"""

from __future__ import annotations

from legal_ai.context.models import ThreadContext

# Findings are the only unbounded part of the context. A long thread would
# otherwise grow its own prompt without limit.
MAX_RENDERED_FINDINGS = 10


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
