"""Assemble a draft's input from the thread it came out of.

This is what makes the document the conversation's own. Three things are
read, and nothing is invented between them:

    matter        the case's description and what it has established
    conversation  the questions asked and the answers given
    law           the provisions those answers actually rested on

The last one matters most. `retrieved` is the union of the evidence ids
carried by the claims already stored in this thread, so the drafter can
only cite law the thread itself used and had verified. A citation the
conversation never relied on cannot reach the document, and
`drafting.validate` refuses one that tries.

Text is capped the way retrieval caps it: a section whole is worth having,
an entire Act pasted into a prompt is not.
"""

from __future__ import annotations

# A provision shown to the drafter. Long enough for a section with its
# provisos, which is where a notice's conditions live.
SECTION_CHARS = 4000

# Turns of conversation. A draft is written from what the thread settled,
# and the last several exchanges carry that; the first question rarely does.
RECENT_TURNS = 12

# Characters of any one turn. An answer runs to paragraphs and the drafter
# needs what it concluded, not its reasoning.
TURN_CHARS = 900


def thread_matter(conn, case_id: str | None, today) -> str:
    """The matter, as the case records it. Empty for a thread without one."""
    lines = [f"Today's date: {today.strftime('%d %B %Y')}"]
    if case_id is None:
        return "\n".join(lines)

    from legal_ai.case.store import get_case

    case = get_case(conn, case_id)
    if case is None:
        return "\n".join(lines)

    lines.append(f"Case: {case.title}")
    if case.state:
        lines.append(f"State: {case.state}")
    if case.description:
        lines.append(f"Context as the client described it: {case.description}")

    findings = getattr(case, "findings", ()) or ()
    if findings:
        lines.append("Established in this matter:")
        lines.extend(f"  - {finding.claim}" for finding in findings)
    return "\n".join(lines)


def thread_conversation(messages) -> str:
    """The exchange, oldest first, as the drafter reads it."""
    lines = []
    for message in list(messages)[-RECENT_TURNS:]:
        speaker = "Q" if message.role == "user" else "A"
        text = " ".join((message.content or "").split())[:TURN_CHARS]
        if text:
            lines.append(f"  {speaker}: {text}")
    return "\n".join(lines)


def thread_authorities(messages) -> set[str]:
    """Every document id the thread's own answers rested on.

    Taken from the stored claims rather than re-retrieved: the draft may
    cite what this conversation established and nothing else.
    """
    found: set[str] = set()
    for message in messages:
        answer = message.answer
        if not isinstance(answer, dict):
            continue
        for claim in answer.get("key_elements") or []:
            if isinstance(claim, dict):
                found.update(
                    str(i) for i in (claim.get("evidence_ids") or []) if str(i).strip()
                )
    return found


def render_law(conn, authorities: set[str]) -> str:
    """The text of each authority, as the drafter may quote it.

    A provision the corpus cannot produce is left out rather than named: an
    identifier with no text behind it is what made an earlier draft write a
    ground that carried a citation and said nothing.
    """
    if not authorities:
        return "  (none)"

    rows = conn.execute(
        "SELECT document_id, title, full_text FROM documents "
        "WHERE document_id = ANY(%s) ORDER BY document_id",
        (sorted(authorities),),
    ).fetchall()

    blocks = []
    for document_id, title, full_text in rows:
        text = " ".join((full_text or "").split())[:SECTION_CHARS]
        if not text:
            continue
        blocks.append(f'  {document_id}  {title}\n  "{text}"')
    return "\n\n".join(blocks) or "  (none)"
