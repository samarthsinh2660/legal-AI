# scripts/recon/aggregate.py
"""Render every scripts/recon/*.json ProbeReport into one findings doc.

See docs/superpowers/specs/2026-08-14-phase1-data-recon-design.md §4.4.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.recon.common import ProbeReport, REPORTS_DIR

DEFAULT_OUTPUT_PATH = Path("docs/DATA_RECON_FINDINGS.md")


def load_reports(directory: Path = REPORTS_DIR) -> list[ProbeReport]:
    if not directory.exists():
        return []
    reports = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        reports.append(ProbeReport.model_validate(data))
    return reports


def _verdict(report: ProbeReport) -> str:
    if not report.reachable:
        return "not viable for Phase 1 as probed — needs more investigation"
    if report.notes:
        return "reachable, with caveats — see notes"
    return "ready to build an ingestion adapter against"


def render_markdown(reports: list[ProbeReport]) -> str:
    lines = [
        "# Phase 1 Data Recon Findings",
        "",
        "Generated from `scripts/recon/aggregate.py` — do not hand-edit; "
        "re-run the probes and regenerate instead.",
        "",
        "## Summary",
        "",
        "| Source | Reachable | Access method | Formats | Licence | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for report in reports:
        lines.append(
            f"| {report.source} | {report.reachable} | {report.access_method} "
            f"| {', '.join(report.formats) or '—'} | {report.licence} "
            f"| {_verdict(report)} |"
        )

    lines.append("")
    lines.append("## Per-source detail")

    for report in reports:
        lines.append("")
        lines.append(f"### {report.source}")
        lines.append("")
        lines.append(f"- **Reachable:** {report.reachable}")
        lines.append(f"- **Auth required:** {report.auth_required}")
        lines.append(f"- **Access method:** {report.access_method}")
        lines.append(f"- **Sample fields:** {', '.join(report.sample_fields) or '—'}")
        lines.append(f"- **Approx volume:** `{report.approx_volume}`")
        lines.append(f"- **Formats:** {', '.join(report.formats) or '—'}")
        lines.append(
            f"- **Licence:** {report.licence} "
            f"(attribution required: {report.attribution_required})"
        )
        lines.append(f"- **Checked at:** {report.checked_at}")
        if report.notes:
            lines.append("- **Notes:**")
            for note in report.notes:
                lines.append(f"  - {note}")

    lines.append("")
    return "\n".join(lines)


def main(
    reports_dir: Path = REPORTS_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    reports = load_reports(reports_dir)
    markdown = render_markdown(reports)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)
    return output_path


if __name__ == "__main__":
    path = main()
    print(f"Wrote {path}")
