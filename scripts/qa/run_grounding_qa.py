"""QA for the promise the product is named after.

Pramāṇa means the question of how you are entitled to claim you know
something. Everything else here -- the queue, the worker, the stream -- is
plumbing. This checks the thing the plumbing exists to protect:

    every citation in an answer names a document we actually hold,
    a question the corpus cannot answer says so rather than inventing,
    and a claim nothing supports is not presented as supported.

Run against a live stack:
    LEGAL_AI_JWT_SECRET=... python scripts/qa/run_grounding_qa.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import psycopg  # noqa: E402

from api.utils.tokens import issue_access_token  # noqa: E402

BASE = os.environ.get("QA_BASE", "http://localhost:8000")
DSN = os.environ.get("DATABASE_URL", "postgresql://legal_ai:legal_ai_dev@localhost:5433/legal_ai")
TOKEN = issue_access_token("qa-grounding", secret=os.environ["LEGAL_AI_JWT_SECRET"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  -- ' + detail if detail else ''}")
    return ok


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={**AUTH, **({"Content-Type": "application/json"} if data else {})},
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read())


def ask(question: str) -> tuple[str, dict]:
    """Ask, wait, and return `(thread_id, the stored answer)`."""
    thread_id = call("POST", "/threads", {})["data"]["thread_id"]
    run_id = call("POST", f"/threads/{thread_id}/messages",
                  {"message": question})["data"]["run_id"]
    while call("GET", f"/runs/{run_id}")["data"]["status"] in ("queued", "running"):
        time.sleep(3)
    messages = call("GET", f"/threads/{thread_id}/messages")["data"]
    return thread_id, (messages[-1].get("answer") or {}) if len(messages) > 1 else {}


def cited_ids(answer: dict) -> set[str]:
    """Every document id the answer points at, from wherever it points."""
    ids: set[str] = set()
    for claim in answer.get("key_elements") or []:
        ids.update(claim.get("evidence_ids") or [])
    for key in ("applicable_law", "key_judgments", "citations"):
        ids.update(answer.get(key) or [])
    return {i for i in ids if i}


def held(conn, ids: set[str]) -> set[str]:
    if not ids:
        return set()
    rows = conn.execute(
        "SELECT document_id FROM documents WHERE document_id = ANY(%s)", (list(ids),)
    ).fetchall()
    return {r[0] for r in rows}


def main() -> int:
    conn = psycopg.connect(DSN)
    threads: list[str] = []

    print("\nEvery citation names a document we hold")
    for question in [
        "what is the punishment under section 138 of the Negotiable Instruments Act",
        "what does section 139 of the Negotiable Instruments Act presume",
    ]:
        thread_id, answer = ask(question)
        threads.append(thread_id)
        ids = cited_ids(answer)
        real = held(conn, ids)
        invented = ids - real
        check(f"{question[:46]}…", not invented and bool(ids),
              f"{len(real)}/{len(ids)} resolve" + (f", INVENTED: {sorted(invented)}" if invented else ""))

    print("\nA claim is only presented as supported if it was checked")
    thread_id, answer = ask("what is the punishment under section 138")
    threads.append(thread_id)
    claims = answer.get("key_elements") or []
    grounded = [c for c in claims if c.get("evidence_ids")]
    ungrounded = [c for c in claims if not c.get("evidence_ids")]
    # Asserted before the interesting check, because "none without
    # evidence" is trivially true of no claims at all -- which is what a
    # throttled model produces, and what made this pass while proving
    # nothing.
    if check("the answer actually made claims", bool(claims),
             f"{len(claims)} claims -- the model API may be throttled"):
        check("no claim sits in key_elements without evidence", not ungrounded,
              f"{len(grounded)} grounded, {len(ungrounded)} bare")
    check("the four verdict buckets are all present",
          all(k in answer for k in
              ("key_elements", "needs_verification", "partially_supported", "unchecked")))

    print("\nA question the corpus cannot answer says so")
    thread_id, answer = ask(
        "what are the prescribed interest rates under the Karnataka RERA rules"
    )
    threads.append(thread_id)
    ids = cited_ids(answer)
    invented = ids - held(conn, ids)
    check("it invents no citation for law we do not hold", not invented,
          f"INVENTED: {sorted(invented)}" if invented else f"{len(ids)} citations, all real")
    note = (answer.get("coverage_note") or "") + " " + (answer.get("lede") or "")
    check("and it says something about the gap", bool(answer.get("coverage_note")),
          (answer.get("coverage_note") or "(no coverage note)")[:70])

    print("\nAsked about something the retrieved law does not cover")
    # Deliberately a question the planner *can* work with, so it reaches
    # retrieval and the model. The earlier version asked about a section
    # that does not exist, which planned no angles at all -- so nothing was
    # ever generated and the test proved nothing about fabrication.
    thread_id, answer = ask(
        "under section 138 of the Negotiable Instruments Act, is a "
        "cryptocurrency transfer a cheque"
    )
    threads.append(thread_id)
    ids = cited_ids(answer)
    invented = ids - held(conn, ids)
    check("it reached the model at all", bool(ids) or bool(answer.get("lede")),
          f"{len(ids)} citations")
    check("no fabricated document id", not invented,
          f"INVENTED: {sorted(invented)}" if invented else f"{len(ids)} citations, all real")
    claims = answer.get("key_elements") or []
    bare = [c for c in claims if not c.get("evidence_ids")]
    check("it invented no unsourced claim about crypto", not bare,
          f"{len(bare)} claims with no source")

    for thread_id in threads:
        urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/threads/{thread_id}", method="DELETE", headers=AUTH))
    conn.close()

    failed = [n for n, ok, _d in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    for name in failed:
        print(f"  FAILED: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
