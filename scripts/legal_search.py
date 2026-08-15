"""CLI for the legal-data-retrieval skill — real DB, no LLM guessing.

Subcommands mirror what the eventual product's query layer will offer:
semantic search, exact lookup, and graph traversal. Each prints JSON so
the calling agent can parse it directly rather than scraping text output.

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


def cmd_citations(args: argparse.Namespace) -> None:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Judgment {document_id: $document_id})-[:CITES]->(b:Judgment)
            RETURN b.document_id AS document_id, b.citation AS citation, b.title AS title
            """,
            document_id=args.document_id,
        )
        citations = [
            {"document_id": r["document_id"], "citation": r["citation"], "title": r["title"]} for r in result
        ]
    print(json.dumps(citations, indent=2))


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

    p_citations = sub.add_parser("citations", help="List Judgments a Judgment cites via the graph.")
    p_citations.add_argument("document_id")
    p_citations.set_defaults(func=cmd_citations)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
