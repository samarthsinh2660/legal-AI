"""CLI for the legal-data-retrieval skill — real DB, no LLM guessing.

Subcommands mirror what the eventual product's query layer will offer:
semantic search, exact lookup, judgment fetch-verify-store, and graph
traversal (Act/Section structure, judgment-to-judgment citations, and
judgment-to-Section citations). Each prints JSON so the calling agent can
parse it directly rather than scraping text output.

Judgment/citation subcommands delegate to the formal, tested tool
contracts in src/legal_ai/tools/ (Phase 2 Milestone 4) rather than
duplicating query logic here a third time.

Run: .venv/bin/python -m scripts.legal_search <subcommand> [args]
"""

from __future__ import annotations

import argparse
import json
import sys

from legal_ai.graphdb.client import get_driver
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import find_similar, get_document
from legal_ai.schemas.evidence import Evidence
from legal_ai.tools.graph import find_citations, find_judgment_sections, find_section_citations
from legal_ai.tools.judgments import search_judgments


def _evidence_json(evidence: Evidence) -> dict:
    return {
        "document_id": evidence.document_id,
        "document_type": evidence.document_type,
        "title": evidence.title,
        "full_text": evidence.content,
        "source_url": evidence.provenance.source.url,
    }


def cmd_search(args: argparse.Namespace) -> None:
    conn = get_connection()
    results = find_similar(conn, embed(args.query), limit=args.limit)
    conn.close()
    print(
        json.dumps(
            [
                {
                    "document_id": doc.document_id,
                    "document_type": doc.document_type,
                    "title": doc.title,
                    "distance": distance,
                }
                for doc, distance in results
            ],
            indent=2,
        )
    )


def cmd_get(args: argparse.Namespace) -> None:
    conn = get_connection()
    doc = get_document(conn, args.document_id)
    conn.close()
    if doc is None:
        print(json.dumps({"error": f"no document with id {args.document_id!r}"}))
        sys.exit(1)
    print(
        json.dumps(
            {
                "document_id": doc.document_id,
                "document_type": doc.document_type,
                "title": doc.title,
                "act_id": doc.act_id,
                "full_text": doc.full_text,
                "source_url": doc.provenance.source.url,
            },
            indent=2,
        )
    )


def cmd_act_sections(args: argparse.Namespace) -> None:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Act {document_id: $act_id})-[:CONTAINS]->(s:Section)
            RETURN s.document_id AS document_id, s.title AS title
            ORDER BY s.document_id
            """,
            act_id=args.act_id,
        )
        sections = [{"document_id": r["document_id"], "title": r["title"]} for r in result]
    print(json.dumps(sections, indent=2))


def cmd_search_judgment(args: argparse.Namespace) -> None:
    results = search_judgments(args.query, year=args.year, skip_db=args.skip_db)
    if not results:
        print(json.dumps({"found": False}))
        sys.exit(1)
    print(json.dumps({"found": True, **_evidence_json(results[0])}, indent=2))


def cmd_citations(args: argparse.Namespace) -> None:
    results = find_citations(args.document_id)
    print(json.dumps([_evidence_json(e) for e in results], indent=2))


def cmd_section_citations(args: argparse.Namespace) -> None:
    """Judgments that cite a given Section (real, verified, stored ones only)."""
    results = find_section_citations(args.section_id)
    print(json.dumps([_evidence_json(e) for e in results], indent=2))


def cmd_judgment_sections(args: argparse.Namespace) -> None:
    """Sections a given Judgment cites (real, resolved ones only — see
    docstring in src/legal_ai/tools/graph.py for unresolved-reference
    handling)."""
    results = find_judgment_sections(args.judgment_id)
    print(json.dumps([_evidence_json(e) for e in results], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the real legal knowledge base.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Semantic search over ingested documents.")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    p_get = sub.add_parser("get", help="Fetch a document's exact stored record by id.")
    p_get.add_argument("document_id")
    p_get.set_defaults(func=cmd_get)

    p_sections = sub.add_parser("act-sections", help="List a real Act's Sections via the graph.")
    p_sections.add_argument("act_id")
    p_sections.set_defaults(func=cmd_act_sections)

    p_search_judgment = sub.add_parser(
        "search-judgment",
        help="Find, verify, and store a real Supreme Court / High Court judgment by case name or citation.",
    )
    p_search_judgment.add_argument("query")
    p_search_judgment.add_argument("--year", type=int, default=None)
    p_search_judgment.add_argument(
        "--skip-db",
        dest="skip_db",
        action="store_true",
        help="Force a fresh live search even if a cached DB match exists — use when a "
        "previous cached match turned out to be the wrong document (same parties, "
        "different proceeding).",
    )
    p_search_judgment.set_defaults(func=cmd_search_judgment)

    p_citations = sub.add_parser("citations", help="List Judgments a Judgment cites via the graph.")
    p_citations.add_argument("document_id")
    p_citations.set_defaults(func=cmd_citations)

    p_section_citations = sub.add_parser(
        "section-citations", help="List Judgments that cite a given Act Section."
    )
    p_section_citations.add_argument("section_id")
    p_section_citations.set_defaults(func=cmd_section_citations)

    p_judgment_sections = sub.add_parser(
        "judgment-sections", help="List Act Sections a given Judgment cites."
    )
    p_judgment_sections.add_argument("judgment_id")
    p_judgment_sections.set_defaults(func=cmd_judgment_sections)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
