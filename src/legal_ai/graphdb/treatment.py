"""Fill in CITES.treatment where the reporter did not state it.

`graphdb/ingest.py` writes treatment for every citation the Supreme Court
Reports print in their own Case Law Reference table -- deterministic, free,
and done the moment a judgment is stored. This is the second pass, for the
citations no such table covered, and it is the only part of the treatment
story that costs a model call.

Batching is across citing judgments, not within one. Measured 2026-08-29:
grouping per judgment averaged 1.4 edges a call, because most citing
judgments cite only one or two cases the corpus also holds. Filling each
batch from whatever judgments it takes reached 10.9 edges a call on the
2026-09-09 run, so a per-judgment pass would cost roughly eight times the
quota for the same edges. That is why this runs once at the end of an
ingest job rather than inside the store step.

A finding of NOT_CHECKED writes nothing. An edge with no treatment reads as
NOT_CHECKED already, and recording the model's shrug as if it were a
reading would make an unclassified edge indistinguishable from one that was
examined.
"""

from __future__ import annotations

from typing import Callable

import neo4j
import psycopg

from legal_ai.agents.treatment import BATCH_SIZE, Treatment, classify_treatments
from legal_ai.ingestion.citations import extract_citation_contexts, normalise_citation

_PENDING = """
MATCH (a:Judgment)-[r:CITES]->(b:Judgment)
WHERE r.treatment IS NULL AND b.citation_key IS NOT NULL
RETURN a.document_id AS citing, b.document_id AS cited,
       b.citation_key AS cited_key
"""

_WRITE = """
MATCH (a:Judgment {document_id: $citing})-[r:CITES]->(b:Judgment {document_id: $cited})
SET r.treatment = $treatment, r.treatment_why = $why
"""


class Result:
    """What a pass spent and what it wrote."""

    def __init__(self) -> None:
        self.calls = 0
        self.written = 0
        self.counts: dict[str, int] = {}


def classify_untreated(
    driver: neo4j.Driver,
    conn: psycopg.Connection,
    limit: int = 50,
    on_batch: Callable[[Result], None] | None = None,
) -> Result:
    """Classify untreated CITES edges, spending at most `limit` model calls.

    Resumable: edges that already carry a treatment are not selected, so a
    run stopped by quota picks up where it left off.
    """
    result = Result()

    with driver.session() as session:
        pending = session.run(_PENDING).values()
    if not pending:
        return result

    by_citing: dict[str, list[tuple[str, str]]] = {}
    for citing, cited, cited_key in pending:
        by_citing.setdefault(citing, []).append((cited, cited_key))

    batch: list[tuple[str, str, str]] = []

    def flush() -> None:
        nonlocal batch
        if not batch:
            return
        findings = classify_treatments([(cited, context) for _c, cited, context in batch])
        result.calls += 1
        with driver.session() as session:
            for (citing_id, cited, _context), finding in zip(batch, findings):
                if finding.treatment is Treatment.NOT_CHECKED:
                    continue
                # Count what the write actually set. A Cypher SET whose MATCH
                # finds nothing is a silent no-op, so counting the attempt
                # would report edges treated that were never touched.
                summary = session.run(
                    _WRITE, citing=citing_id, cited=cited,
                    treatment=finding.treatment.value, why=finding.why,
                ).consume()
                if not summary.counters.properties_set:
                    continue
                result.written += 1
                result.counts[finding.treatment.value] = (
                    result.counts.get(finding.treatment.value, 0) + 1
                )
        batch = []
        if on_batch:
            on_batch(result)

    for citing, targets in by_citing.items():
        if result.calls >= limit:
            break
        row = conn.execute(
            "SELECT full_text FROM documents WHERE document_id = %s", (citing,)
        ).fetchone()
        # End the read transaction before the model call. Postgres holds the
        # row lock until commit, and a batch takes minutes; leaving it open
        # let a concurrent ingest's ALTER TABLE queue behind this read, and
        # every later reader queue behind the ALTER.
        conn.commit()
        if not row or not row[0]:
            continue

        by_key: dict[str, str] = {}
        for citation, context in extract_citation_contexts(row[0]):
            # Last occurrence wins: a court often notes a case early and
            # disposes of it late, and the later passage is the holding.
            by_key[normalise_citation(citation)] = context

        for cited, cited_key in targets:
            if cited_key in by_key:
                batch.append((citing, cited, by_key[cited_key]))
                if len(batch) >= BATCH_SIZE:
                    flush()
                    if result.calls >= limit:
                        break
    if result.calls < limit:
        flush()
    return result
