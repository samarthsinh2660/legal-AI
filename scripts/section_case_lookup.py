"""Query CITES_SECTION edges — which judgments apply a given Section,
and which Sections a given judgment cites.

Read-only: written by graphdb/ingest.py's write_judgment() as judgments
are stored (see scripts/search_judgment.py). A section with no results
here either genuinely has no stored judgment citing it yet, or the
judgments that do haven't been ingested — not proof it's never litigated.

Run:
  .venv/bin/python -m scripts.section_case_lookup judgments-for <section_id>
  .venv/bin/python -m scripts.section_case_lookup sections-in <judgment_id>
"""

from __future__ import annotations

import argparse
import json

from legal_ai.graphdb.client import get_driver


def cmd_judgments_for(args: argparse.Namespace) -> None:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (j:Judgment)-[:CITES_SECTION]->(s:Section {document_id: $section_id})
            RETURN j.document_id AS document_id, j.title AS title, j.citation AS citation
            ORDER BY j.document_id
            """,
            section_id=args.section_id,
        )
        judgments = [dict(r) for r in result]
    driver.close()
    print(json.dumps(judgments, indent=2))


def cmd_sections_in(args: argparse.Namespace) -> None:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (j:Judgment {document_id: $judgment_id})-[:CITES_SECTION]->(s:Section)
            RETURN s.document_id AS document_id, s.title AS title
            ORDER BY s.document_id
            """,
            judgment_id=args.judgment_id,
        )
        sections = [dict(r) for r in result]

        dangling = session.run(
            "MATCH (j:Judgment {document_id: $judgment_id}) RETURN j.dangling_section_citations AS raw",
            judgment_id=args.judgment_id,
        ).single()
    driver.close()
    print(
        json.dumps(
            {
                "resolved_sections": sections,
                "unresolved_references": (dangling["raw"] if dangling else None) or [],
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Query judgment <-> Section CITES_SECTION edges.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_judgments = sub.add_parser("judgments-for", help="List judgments citing a given Section.")
    p_judgments.add_argument("section_id", help='e.g. "act:19722:sec-13"')
    p_judgments.set_defaults(func=cmd_judgments_for)

    p_sections = sub.add_parser("sections-in", help="List Sections a given judgment cites.")
    p_sections.add_argument("judgment_id")
    p_sections.set_defaults(func=cmd_sections_in)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
