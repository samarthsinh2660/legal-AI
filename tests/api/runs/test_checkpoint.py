"""What a requeued run does not have to pay for twice.

The reaper brings an abandoned run back, and without this it starts from
nothing: about 7s of planning and 11s of retrieval, re-bought, for evidence
the dead worker had already found.

Only `findings` is carried. It is the expensive part and it is the only
part that round-trips *provably* -- Evidence is a pydantic model, so
`model_dump(mode="json")` and `model_validate` are exact. The ThreadContext
is a frozen dataclass and costs 1.3s to rebuild, so it is rebuilt.

The rule the restore obeys: all of it or none of it. A half-restored list
would put an answer's citations on evidence that was never properly
rebuilt, which is worse than paying for the search again.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.repository import create_thread, ensure_thread_schema
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef

USER = "test-user-ckpt"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-ckpt%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-ckpt%'")
        conn.commit()


def _evidence(document_id: str) -> Evidence:
    return Evidence(
        document_id=document_id,
        document_type="act",
        title="Dishonour of cheque",
        content="Where any cheque drawn by a person on an account maintained by him…",
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
    )


def _running(conn):
    thread = create_thread(conn, USER)
    runs.enqueue(conn, thread.thread_id, USER, "research", {})
    return runs.claim(conn, ("research",))["run_id"]


def test_a_run_with_no_checkpoint_restores_nothing():
    with connection() as conn:
        run_id = _running(conn)
        assert runs.restore_findings(conn, run_id) == []


def test_findings_survive_the_round_trip_exactly():
    """The whole reason only Evidence is carried: it is a pydantic model,
    so this is provable rather than hopeful."""
    original = [_evidence("act:2189:sec-138"), _evidence("act:2189:sec-139")]

    with connection() as conn:
        run_id = _running(conn)
        runs.save_findings(conn, run_id, original)
        restored = runs.restore_findings(conn, run_id)

    assert [e.model_dump() for e in restored] == [e.model_dump() for e in original]


def test_the_provenance_survives_too():
    """Evidence without its source is a claim we cannot attribute, which is
    the one thing this system may not produce."""
    with connection() as conn:
        run_id = _running(conn)
        runs.save_findings(conn, run_id, [_evidence("act:2189:sec-138")])
        restored = runs.restore_findings(conn, run_id)

    assert restored[0].provenance.source.name == "India Code"
    assert restored[0].provenance.retrieved_at.year == 2026


def test_saving_an_empty_list_stores_no_checkpoint():
    """A search that found nothing is not worth resuming, and a stored
    empty list would make the next attempt skip searching at all."""
    with connection() as conn:
        run_id = _running(conn)
        runs.save_findings(conn, run_id, [])
        assert runs.restore_findings(conn, run_id) == []


def test_a_checkpoint_that_cannot_be_read_restores_nothing():
    """All of it or none of it. Half a list would put citations on evidence
    that was never rebuilt -- worse than paying for the search again."""
    with connection() as conn:
        run_id = _running(conn)
        runs.save_findings(conn, run_id, [_evidence("act:2189:sec-138")])
        conn.execute(
            "UPDATE runs SET checkpoint = %s::jsonb WHERE run_id = %s",
            ('{"findings": [{"document_id": "act:1", "nonsense": true}]}', run_id),
        )
        conn.commit()

        assert runs.restore_findings(conn, run_id) == []


def test_a_requeued_run_keeps_its_checkpoint():
    """The point of the whole thing: the next worker inherits the search."""
    with connection() as conn:
        run_id = _running(conn)
        runs.save_findings(conn, run_id, [_evidence("act:2189:sec-138")])
        conn.execute(
            "UPDATE runs SET heartbeat_at = now() - interval '30 minutes' "
            "WHERE run_id = %s", (run_id,))
        conn.commit()

        runs.reap(conn, stale_after=60)
        assert runs.get(conn, run_id, USER)["status"] == "queued"

        job = runs.claim(conn, ("research",))
        assert job["run_id"] == run_id
        assert len(runs.restore_findings(conn, run_id)) == 1


def test_a_later_round_adds_to_the_checkpoint_rather_than_replacing_it():
    """`stream_graph` accumulates node *outputs*, so on a resumed run whose
    verification loops back, round two returns only its own new evidence.
    Saving that replaced the carried set -- and a third attempt would then
    restore the smaller one and, because a resumed run skips searching,
    answer from a fraction of what had been found."""
    first = [_evidence("act:2189:sec-138"), _evidence("act:2189:sec-139")]
    later = [_evidence("act:2189:sec-141")]

    with connection() as conn:
        run_id = _running(conn)
        runs.save_findings(conn, run_id, first)
        runs.save_findings(conn, run_id, later)

        restored = {e.document_id for e in runs.restore_findings(conn, run_id)}

    assert restored == {"act:2189:sec-138", "act:2189:sec-139", "act:2189:sec-141"}


def test_saving_the_same_evidence_twice_does_not_duplicate_it():
    with connection() as conn:
        run_id = _running(conn)
        runs.save_findings(conn, run_id, [_evidence("act:2189:sec-138")])
        runs.save_findings(conn, run_id, [_evidence("act:2189:sec-138")])

        assert len(runs.restore_findings(conn, run_id)) == 1
