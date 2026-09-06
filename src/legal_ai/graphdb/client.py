# src/legal_ai/graphdb/client.py
"""Neo4j driver for the structural knowledge graph.

Structural only: what cites what, what contains what, who decided what.
Nothing here holds document text -- that lives in Postgres, and the graph
holds ids and titles so a traversal stays cheap.
"""

from __future__ import annotations

import os

import neo4j

_DEFAULT_URI = "bolt://localhost:7688"
_DEFAULT_USER = "neo4j"
_DEFAULT_PASSWORD = "legal_ai_dev"


def get_driver() -> neo4j.Driver:
    uri = os.environ.get("NEO4J_URI", _DEFAULT_URI)
    user = os.environ.get("NEO4J_USER", _DEFAULT_USER)
    password = os.environ.get("NEO4J_PASSWORD", _DEFAULT_PASSWORD)
    return neo4j.GraphDatabase.driver(uri, auth=(user, password))
