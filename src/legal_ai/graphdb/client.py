# src/legal_ai/graphdb/client.py
"""Neo4j driver for the initial, structural-only knowledge graph.

See docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.4.
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
