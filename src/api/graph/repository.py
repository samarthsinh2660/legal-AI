"""A readable neighbourhood of the citation graph.

The graph holds ~48,800 nodes and ~57,000 edges. No browser renders that,
and no reader wants it: an Obsidian-style view is useful because it shows
one thing and what touches it, not because it shows everything.

So this is always anchored on a document and bounded twice -- by hops and by
node count. The cap is not a performance guard, it is the feature: a
landmark judgment has ninety-five citations, and drawing all of them at once
produces a hairball that says less than a list would.

Read-only by construction. There is no write path in this module, and the
corpus is not something a reader may edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Two hops shows "what this cites, and what those cite". Three turns a
# landmark into a hairball.
MAX_HOPS = 2
DEFAULT_HOPS = 1

# Nodes returned, anchor included. Past roughly this many, a force layout
# stops being readable.
MAX_NODES = 120
DEFAULT_NODES = 60


@dataclass
class Neighbourhood:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)

    # True when the cap cut the result short. The viewer must say so:
    # a graph silently missing half its edges is a picture that lies.
    truncated: bool = False


def neighbourhood(
    driver,
    document_id: str,
    hops: int = DEFAULT_HOPS,
    limit: int = DEFAULT_NODES,
) -> Neighbourhood | None:
    """Nodes and edges within `hops` of `document_id`, or None if unknown.

    Edges are returned only between nodes that are themselves in the result.
    An edge pointing at something the cap removed would render as a line to
    nowhere.
    """
    hops = max(1, min(hops, MAX_HOPS))
    limit = max(2, min(limit, MAX_NODES))

    with driver.session() as session:
        anchor = session.run(
            "MATCH (n) WHERE n.document_id = $id "
            "RETURN n.document_id AS id, labels(n)[0] AS kind, n.title AS title",
            id=document_id,
        ).single()
        if anchor is None:
            return None

        rows = session.run(
            f"""
            MATCH (a) WHERE a.document_id = $id
            MATCH path = (a)-[*1..{hops}]-(b)
            WHERE b.document_id IS NOT NULL AND b.document_id <> $id
            RETURN DISTINCT b.document_id AS id,
                   labels(b)[0] AS kind,
                   b.title AS title,
                   length(path) AS hops
            ORDER BY hops, id
            LIMIT $limit
            """,
            id=document_id,
            limit=limit - 1,
        ).values()

        found = [
            {"id": row[0], "kind": row[1], "title": row[2], "hops": row[3]}
            for row in rows
        ]
        ids = [document_id] + [node["id"] for node in found]

        # Only edges whose both ends survived the cap.
        edges = session.run(
            """
            MATCH (a)-[r]->(b)
            WHERE a.document_id IN $ids AND b.document_id IN $ids
            RETURN a.document_id AS source, b.document_id AS target, type(r) AS kind
            """,
            ids=ids,
        ).values()

        # Was anything left out? Asked separately rather than inferred from
        # hitting the limit, which is only a hint.
        total = session.run(
            f"""
            MATCH (a) WHERE a.document_id = $id
            MATCH (a)-[*1..{hops}]-(b)
            WHERE b.document_id IS NOT NULL AND b.document_id <> $id
            RETURN count(DISTINCT b) AS total
            """,
            id=document_id,
        ).single()[0]

    nodes = [
        {
            "id": anchor["id"],
            "kind": anchor["kind"],
            "title": anchor["title"],
            "hops": 0,
        }
    ] + found
    return Neighbourhood(
        nodes=nodes,
        edges=[{"source": e[0], "target": e[1], "kind": e[2]} for e in edges],
        truncated=total > len(found),
    )
