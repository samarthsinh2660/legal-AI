"""QA for the run queue, end to end against a running API.

Not a unit suite. Every case here goes over HTTP to a live API with a live
worker behind it, because the properties being checked are the ones that
only exist when the two are separate processes: a job outliving a request,
a stream replaying to a client that was not there, a second message being
refused while the first is still going.

Usage:
    python scripts/qa/run_queue_qa.py [--base http://localhost:8000]

Needs LEGAL_AI_JWT_SECRET to mint its own tokens. Creates threads under
user ids prefixed `qa-`, and deletes them at the end.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from api.utils.tokens import issue_access_token  # noqa: E402

USER = "qa-primary"
OTHER = "qa-other"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  -- ' + detail if detail else ''}")
    return ok


class Api:
    def __init__(self, base: str, secret: str, user: str) -> None:
        self.base = base.rstrip("/")
        self.token = issue_access_token(user, secret=secret)

    def request(self, method: str, path: str, body=None, headers=None, raw=False):
        """`(status, parsed)`. Never raises on an HTTP error status.

        `raw` returns the body as bytes -- the draft download is a .docx,
        which is neither JSON nor text.
        """
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base}{path}", data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                **({"Content-Type": "application/json"} if data else {}),
                **(headers or {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = response.read()
                return response.status, (payload if raw else json.loads(payload))
        except urllib.error.HTTPError as error:
            payload = error.read()
            # An error body is never the thing the caller asked for, so a
            # `raw` caller gets bytes here too. Returning parsed JSON to one
            # of those meant `content[:8]` hit a dict and raised
            # KeyError(slice(None, 8, None)) -- a crashed case reporting
            # nothing about the endpoint it was testing.
            if raw:
                return error.code, payload
            try:
                return error.code, json.loads(payload)
            except json.JSONDecodeError:
                return error.code, payload.decode()

    def thread(self) -> str:
        _status, body = self.request("POST", "/threads", {})
        return body["data"]["thread_id"]

    def ask(self, thread_id: str, message: str, **extra):
        return self.request(
            "POST", f"/threads/{thread_id}/messages", {"message": message, **extra}
        )

    def messages(self, thread_id: str):
        return self.request("GET", f"/threads/{thread_id}/messages")[1]["data"]

    def run(self, run_id: str):
        return self.request("GET", f"/runs/{run_id}")

    def await_run(self, run_id: str, seconds: int = 300) -> str:
        deadline = time.monotonic() + seconds
        status = "unknown"
        while time.monotonic() < deadline:
            code, body = self.run(run_id)
            if code != 200:
                return f"gone({code})"
            status = body["data"]["status"]
            if status not in ("queued", "running"):
                return status
            time.sleep(2)
        return status

    def stream(self, run_id: str, last_event_id: str | None = None, timeout: int = 300):
        """Every SSE frame of a run, as `[(id, event, data), ...]`."""
        headers = {"Authorization": f"Bearer {self.token}"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        request = urllib.request.Request(f"{self.base}/runs/{run_id}/stream", headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            return error.code, []

        frames, buffer = [], ""
        for chunk in response:
            buffer += chunk.decode()
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                fields = {}
                for line in frame.splitlines():
                    for key in ("id", "event", "data"):
                        if line.startswith(f"{key}:"):
                            fields[key] = line[len(key) + 1:].strip()
                if "event" in fields:
                    frames.append((fields.get("id"), fields["event"], fields.get("data", "")))
        return response.status, frames


# --------------------------------------------------------------- the cases


def rejects_bad_input(api: Api) -> None:
    print("\nInput the API must refuse")

    # A fresh thread per case: one thread runs one turn at a time, so a case
    # that does get queued would make the next one a 409 and hide its result.
    for name, message in [
        ("an empty message is refused", ""),
        ("a whitespace-only message is refused", "   \n\t "),
        ("a non-breaking-space message is refused", "\u00a0\u00a0"),
        ("a message past the 4000-char ceiling is refused", "x" * 4001),
    ]:
        code, _body = api.ask(api.thread(), message)
        check(name, code in (400, 422), f"got {code}")

    code, body = api.ask(api.thread(), "x" * 4000)
    check("a message at exactly the ceiling is accepted", code == 202, f"got {code}")
    if code == 202:
        api.await_run(body["data"]["run_id"])

    code, body = api.ask(api.thread(), "  what is section 138?  ")
    if check("a padded message is accepted", code == 202, f"got {code}"):
        api.await_run(body["data"]["run_id"])

    code, _ = api.request("POST", "/threads/no-such-thread-id/messages", {"message": "hi"})
    check("an unknown thread is a 404", code == 404, f"got {code}")

    code, _ = api.request("GET", "/runs/deadbeef")
    check("an unknown run is a 404", code == 404, f"got {code}")


def refuses_other_peoples_work(api: Api, other: Api) -> None:
    print("\nWhat belongs to somebody else")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "hello")
    run_id = body["data"]["run_id"]

    code, _ = other.request("POST", f"/threads/{thread_id}/messages", {"message": "mine now"})
    check("another user cannot post to the thread", code == 404, f"got {code}")

    code, _ = other.run(run_id)
    check("another user cannot read the run", code == 404, f"got {code}")

    code, _frames = other.stream(run_id, timeout=10)
    check("another user cannot watch the stream", code == 404, f"got {code}")

    api.await_run(run_id)


def one_run_per_thread(api: Api) -> None:
    print("\nOne run per thread")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "what is the punishment under section 138")
    run_id = body["data"]["run_id"]

    code, error = api.ask(thread_id, "and what about section 420")
    check(
        "a second message while one is running is a 409",
        code == 409 and error["error"]["code"] == "run_in_progress",
        f"got {code}",
    )

    status = api.await_run(run_id)
    check("the first run still finished", status == "done", status)

    code, _ = api.ask(thread_id, "and what about section 420")
    check("a follow-up is accepted once the run is over", code == 202, f"got {code}")
    api.await_run(api.request("GET", f"/threads/{thread_id}")[1]["data"]["active_run"]["run_id"])


def replay_and_resume(api: Api) -> None:
    print("\nReplay and resume")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "what is the punishment under section 138")
    run_id = body["data"]["run_id"]
    api.await_run(run_id)

    _code, whole = api.stream(run_id)
    check("attaching after the run is over replays all of it", len(whole) >= 2, f"{len(whole)} frames")
    check("the last frame is terminal", whole[-1][1] in ("done", "error"), whole[-1][1])

    seqs = [int(seq) for seq, _kind, _data in whole if seq]
    check("ids are dense from 1", seqs == list(range(1, len(seqs) + 1)), str(seqs[:12]))

    _code, missed = api.stream(run_id, last_event_id=str(seqs[-2]))
    check("resuming replays only what was missed", len(missed) == 1, f"{len(missed)} frames")

    _code, past_end = api.stream(run_id, last_event_id=str(seqs[-1] + 500))
    check("resuming past the end replays nothing", past_end == [], f"{len(past_end)} frames")

    _code, garbage = api.stream(run_id, last_event_id="not-a-number")
    check("an unreadable resume header replays everything", len(garbage) == len(whole))

    _code, negative = api.stream(run_id, last_event_id="-5")
    check("a negative resume header replays everything", len(negative) == len(whole))


def two_watchers_agree(api: Api) -> None:
    print("\nTwo watchers, one run")
    import threading

    thread_id = api.thread()
    _code, body = api.ask(thread_id, "is anticipatory bail available for a cheque bounce case")
    run_id = body["data"]["run_id"]

    seen: dict[int, list] = {}

    def watch(index: int) -> None:
        _code, frames = api.stream(run_id)
        seen[index] = frames

    watchers = [threading.Thread(target=watch, args=(i,)) for i in range(2)]
    for watcher in watchers:
        watcher.start()
    for watcher in watchers:
        watcher.join(timeout=300)

    check("both watchers saw events", bool(seen.get(0)) and bool(seen.get(1)))
    check(
        "both watchers saw exactly the same events",
        seen.get(0) == seen.get(1),
        f"{len(seen.get(0, []))} vs {len(seen.get(1, []))}",
    )


def a_departed_reader_still_gets_the_answer(api: Api) -> None:
    print("\nThe reader leaves")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "what is the limitation period under section 142")
    run_id = body["data"]["run_id"]

    # Attach, read one frame, and drop the connection -- a closed tab.
    request = urllib.request.Request(
        f"{api.base}/runs/{run_id}/stream",
        headers={"Authorization": f"Bearer {api.token}"},
    )
    response = urllib.request.urlopen(request, timeout=60)
    response.read(1)
    response.close()

    status = api.await_run(run_id)
    check("the run finished with nobody watching", status == "done", status)
    stored = api.messages(thread_id)
    check(
        "the answer was stored anyway",
        [m["role"] for m in stored] == ["user", "assistant"],
        str([m["role"] for m in stored]),
    )


def the_short_paths(api: Api) -> None:
    print("\nThe paths that never reach the graph")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "thanks!")
    run_id = body["data"]["run_id"]
    started = time.monotonic()
    status = api.await_run(run_id, seconds=60)
    elapsed = time.monotonic() - started
    check("small talk finishes", status == "done", status)
    check("small talk is fast", elapsed < 20, f"{elapsed:.1f}s")

    _code, frames = api.stream(run_id)
    check("small talk emits no research steps", all(kind != "step" for _id, kind, _d in frames))
    reply = json.loads(frames[-1][2])
    check("small talk routes ANSWER", reply["route"] == "ANSWER", reply["route"])


def unicode_survives(api: Api) -> None:
    print("\nText that is not ASCII")
    thread_id = api.thread()
    question = "धारा 138 के तहत सज़ा क्या है? — and in English too"
    _code, body = api.ask(thread_id, question)
    api.await_run(body["data"]["run_id"])
    stored = api.messages(thread_id)
    check("the question came back byte-identical", stored[0]["content"] == question)


def a_deleted_thread_takes_its_run(api: Api) -> None:
    print("\nThe thread is deleted mid-run")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "what is the punishment under section 420")
    run_id = body["data"]["run_id"]
    time.sleep(2)

    code, _ = api.request("DELETE", f"/threads/{thread_id}")
    check("the thread deletes while its run is going", code == 200, f"got {code}")

    code, _ = api.run(run_id)
    check("its run goes with it", code == 404, f"got {code}")

    # The worker is still running the graph against a thread that no longer
    # exists. It must not take the process down.
    time.sleep(45)
    code, health = api.request("GET", "/health")
    check("the API is still healthy afterwards", code == 200 and health["data"]["status"] == "ok")


def drafting(api: Api) -> None:
    print("\nDrafting, as a second kind of job")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "what is the punishment under section 138")
    api.await_run(body["data"]["run_id"])

    # State the fixture's precondition rather than assume it. A drafter can
    # only cite what the thread established, so a turn that came back thin
    # -- which happens when the model API is rate-limited and the answer
    # falls through with no evidence -- makes the draft fail for a correct
    # reason. Without this the run reports "drafting is broken", which it
    # is not.
    messages = api.messages(thread_id)
    answer = (messages[-1].get("answer") or {}) if messages else {}
    grounded = [c for c in (answer.get("key_elements") or []) if c.get("evidence_ids")]
    if not check("the thread established something to draft from", bool(grounded),
                 f"{len(grounded)} grounded claims -- the model API may be throttled"):
        return

    code, started = api.request("POST", f"/threads/{thread_id}/drafts", {})
    check("a draft starts", code == 200, f"got {code}")
    draft_id = started["data"]["draft_id"]

    code, again = api.request("POST", f"/threads/{thread_id}/drafts", {})
    check("a second draft on the same thread is a 409", code == 409, f"got {code}")

    _code, thread = api.request("GET", f"/threads/{thread_id}")
    active = thread["data"]["active_run"]
    check("the thread's active run is the draft", active and active["kind"] == "draft", str(active))

    deadline = time.monotonic() + 240
    status = "running"
    while time.monotonic() < deadline:
        _code, drafts = api.request("GET", f"/threads/{thread_id}/drafts")
        status = drafts["data"][0]["status"]
        if status != "running":
            break
        time.sleep(3)
    check("the draft finishes", status == "done", status)

    code, content = api.request("GET", f"/drafts/{draft_id}/download", raw=True)
    # A .docx is a zip, so it opens with the zip magic number.
    check("the download is a real .docx", code == 200 and content[:2] == b"PK",
          f"{code}: {content[:60]!r}")


def a_draft_with_nothing_to_cite(api: Api) -> None:
    print("\nA draft the thread cannot support")
    thread_id = api.thread()
    _code, body = api.ask(thread_id, "hello")
    api.await_run(body["data"]["run_id"])

    code, started = api.request("POST", f"/threads/{thread_id}/drafts", {})
    if not check("it is accepted rather than refused up front", code == 200, f"got {code}"):
        return

    deadline = time.monotonic() + 240
    row = {}
    while time.monotonic() < deadline:
        _code, drafts = api.request("GET", f"/threads/{thread_id}/drafts")
        row = drafts["data"][0]
        if row["status"] != "running":
            break
        time.sleep(3)
    check("it ends in a terminal state, not a hang", row.get("status") in ("done", "failed"), str(row.get("status")))
    if row.get("status") == "failed":
        check("and it says why", bool(row.get("error")), str(row.get("error"))[:80])


def cleanup(api: Api, other: Api) -> None:
    for who in (api, other):
        _code, page = who.request("GET", "/threads?limit=100")
        for thread in page.get("data", {}).get("items", []):
            who.request("DELETE", f"/threads/{thread['thread_id']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()

    secret = os.environ.get("LEGAL_AI_JWT_SECRET")
    if not secret:
        print("LEGAL_AI_JWT_SECRET is not set")
        return 2

    api, other = Api(args.base, secret, USER), Api(args.base, secret, OTHER)

    code, health = api.request("GET", "/health")
    if code != 200:
        print(f"the API at {args.base} is not answering ({code})")
        return 2
    print(f"API at {args.base}: {health['data']}")

    for case in (
        rejects_bad_input,
        refuses_other_peoples_work,
        one_run_per_thread,
        replay_and_resume,
        two_watchers_agree,
        a_departed_reader_still_gets_the_answer,
        the_short_paths,
        unicode_survives,
        drafting,
        a_draft_with_nothing_to_cite,
        a_deleted_thread_takes_its_run,
    ):
        try:
            case(api, other) if case is refuses_other_peoples_work else case(api)
        except Exception as error:  # noqa: BLE001 - a crashed case is a failed case
            check(f"{case.__name__} raised", False, repr(error)[:160])

    cleanup(api, other)

    failed = [name for name, ok, _detail in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    for name in failed:
        print(f"  FAILED: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
