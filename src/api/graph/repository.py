"""A readable neighbourhood of the citation graph.

The graph holds ~48,800 nodes and ~57,000 edges. No browser renders that,
and no reader wants it: an Obsidian-style view is useful because it shows
one thing and what touches it, not because it shows everything.

So this is always anchored on a document and bounded to one step and a
node count. The cap is not a performance guard, it is the feature: a
landmark judgment has ninety-five citations, and drawing all of them at once
produces a hairball that says less than a list would.

Read-only by construction. There is no write path in this module, and the
corpus is not something a reader may edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Nodes returned, anchor included. Past roughly this many, a force layout
# stops being readable.
MAX_NODES = 120
DEFAULT_NODES = 60

# Nodes per batch in the overview. The graph is 50,890 nodes: rendering it
# whole is not a view, and a force layout stops being readable well before
# that. So the reader asks for more rather than being given everything --
# progressive loading, with semantic grouping by document type, which is
# what the literature recommends for graphs of this size.
OVERVIEW_BATCH = 100


@dataclass
class Neighbourhood:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)

    # True when the cap cut the result short. The viewer must say so:
    # a graph silently missing half its edges is a picture that lies.
    truncated: bool = False

    # How many nodes the slice holds in total, or None where that was not
    # asked. Batching without it tells a reader they are looking at "100"
    # and leaves them to guess whether that is most of the corpus or a
    # thousandth of it -- the statutes slice holds 36,887.
    total: int | None = None


def neighbourhood(
    driver,
    document_id: str,
    limit: int = DEFAULT_NODES,
) -> Neighbourhood | None:
    """Nodes and edges one step from `document_id`, or None if unknown.

    One step, not a variable depth. A second hop reached what the
    neighbours cite rather than what this document does, and at a landmark
    judgment's fan-out it filled the canvas with documents the reader had
    not asked about. The UI offered the choice and nobody changed it.

    Edges are returned only between nodes that are themselves in the result.
    An edge pointing at something the cap removed would render as a line to
    nowhere.
    """
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
            """
            MATCH (a) WHERE a.document_id = $id
            MATCH path = (a)-[*1..1]-(b)
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
            """
            MATCH (a) WHERE a.document_id = $id
            MATCH (a)-[*1..1]-(b)
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


# What a reader can ask to see. Each is a slice of the same graph, ordered
# by how much of it points at the node -- so the first batch is the part
# worth recognising rather than an arbitrary hundred.
VIEWS = {
    # Judgments, and the citations between them.
    "judgments": (
        """
        MATCH (n:Judgment)<-[:CITES]-()
        WITH n, count(*) AS weight
        ORDER BY weight DESC, n.document_id
        SKIP $offset LIMIT $limit
        RETURN n.document_id, labels(n)[0], n.title
        """,
        """
        MATCH (a)-[:CITES]->(b)
        WHERE a.document_id IN $ids AND b.document_id IN $ids
        RETURN a.document_id, b.document_id, 'CITES'
        """,
    ),
    # Statute sections, and the judgments that interpret them.
    "statutes": (
        """
        MATCH (n:Section)<-[:CITES_SECTION]-()
        WITH n, count(*) AS weight
        ORDER BY weight DESC, n.document_id
        SKIP $offset LIMIT $limit
        RETURN n.document_id, labels(n)[0], n.title
        """,
        """
        MATCH (a)-[:CITES_SECTION]->(b)
        WHERE a.document_id IN $ids AND b.document_id IN $ids
        RETURN a.document_id, b.document_id, 'CITES_SECTION'
        """,
    ),
}


def _act_view(act_id: str):
    """One Act's sections, and which of them judgments cite."""
    return (
        """
        MATCH (a:Act {document_id: $act})-[:CONTAINS]->(n:Section)
        OPTIONAL MATCH (n)<-[:CITES_SECTION]-()
        WITH n, count(*) AS weight
        ORDER BY weight DESC, n.document_id
        SKIP $offset LIMIT $limit
        RETURN n.document_id, labels(n)[0], n.title
        """,
        """
        MATCH (a)-[:CITES_SECTION]->(b)
        WHERE a.document_id IN $ids AND b.document_id IN $ids
        RETURN a.document_id, b.document_id, 'CITES_SECTION'
        """,
    )


# Counted per slice rather than derived from the node query, which pages.
COUNTS = {
    "judgments": "MATCH (n:Judgment)<-[:CITES]-() RETURN count(DISTINCT n)",
    "statutes": "MATCH (n:Section) RETURN count(n)",
}


def overview(
    driver, view: str = "judgments", offset: int = 0, limit: int = OVERVIEW_BATCH
) -> Neighbourhood:
    """One batch of a named slice of the graph.

    Ordered by how much of the corpus points at each node, so the first
    batch is the part a reader recognises. `truncated` is true whenever a
    further batch exists, which is what tells the viewer to offer "load
    more" rather than implying it has shown everything.

    `total` is counted once, on the first batch only. It is what stops the
    batch reading as the whole slice, and paging is where it would cost
    something for nothing.
    """
    limit = max(1, min(limit, OVERVIEW_BATCH))
    offset = max(0, offset)

    if view in VIEWS:
        node_query, edge_query = VIEWS[view]
        params = {}
        count_query = COUNTS[view]
    else:
        node_query, edge_query = _act_view(view)
        params = {"act": view}
        count_query = (
            "MATCH (n:Section) WHERE n.document_id STARTS WITH $act + ':' "
            "RETURN count(n)"
        )

    with driver.session() as session:
        # One extra row, to learn whether another batch exists without a
        # second count query over the whole graph.
        rows = session.run(
            node_query, offset=offset, limit=limit + 1, **params
        ).values()
        more = len(rows) > limit
        rows = rows[:limit]

        nodes = [
            {"id": row[0], "kind": row[1], "title": row[2] or "", "hops": 0}
            for row in rows
            if row[0]
        ]
        ids = [node["id"] for node in nodes]

        # Sections do not cite each other, so a statute batch on its own
        # draws a hundred unconnected dots. Pull in the judgments that cite
        # them -- that is the graph a reader came to see.
        if ids and view != "judgments":
            citing = session.run(
                """
                MATCH (j:Judgment)-[:CITES_SECTION]->(s)
                WHERE s.document_id IN $ids
                WITH j, count(*) AS weight
                ORDER BY weight DESC
                LIMIT $cap
                RETURN j.document_id, labels(j)[0], j.title
                """,
                ids=ids, cap=limit,
            ).values()
            known = set(ids)
            for row in citing:
                if row[0] and row[0] not in known:
                    known.add(row[0])
                    nodes.append({
                        "id": row[0], "kind": row[1],
                        "title": row[2] or "", "hops": 1,
                    })
            ids = [node["id"] for node in nodes]

        # Only edges between nodes that are themselves shown. An edge to
        # something outside the batch would render as a line to nowhere.
        edges = [
            {"source": row[0], "target": row[1], "kind": row[2]}
            for row in session.run(edge_query, ids=ids).values()
        ] if ids else []

        total = (
            session.run(count_query, **params).single()[0] if offset == 0 else None
        )

    return Neighbourhood(nodes=nodes, edges=edges, truncated=more, total=total)
