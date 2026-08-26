"""Case graph nodes. Thin, like graph.nodes -- the work lives elsewhere."""

from __future__ import annotations

from legal_ai.graph.case_state import CaseState


def load_case(state: CaseState) -> dict:
    """Fetch the case and whatever has already been read from its files.

    Missing structure is left missing rather than extracted here, so the
    extract node can tell "not read yet" from "read, and says nothing".
    """
    from legal_ai.case.files import get_facts, list_case_files
    from legal_ai.case.store import ensure_case_schema, get_case
    from legal_ai.knowledge.static.db import get_connection

    conn = get_connection()
    try:
        ensure_case_schema(conn)
        case = get_case(conn, state["case_id"])
        if case is None:
            return {"case": None, "error": f"no case {state['case_id']!r}"}

        documents = []
        for document_id, _filename in list_case_files(conn, state["case_id"]):
            facts = get_facts(conn, document_id)
            if facts is not None:
                documents.append(facts)
    finally:
        conn.close()
    return {"case": case, "documents": documents, "error": None}


def extract(state: CaseState) -> dict:
    """Read any file whose structure is not on record yet.

    Usually a no-op: extraction runs at upload and is stored. This covers
    the file uploaded with `extract_facts=False` for a bulk attach, and the
    one whose extraction failed when no model was reachable.
    """
    from legal_ai.agents.document import extract_document_facts
    from legal_ai.case.files import get_case_file_text, list_case_files, store_facts
    from legal_ai.knowledge.static.db import get_connection

    case = state.get("case")
    if case is None:
        return {}

    known = {facts.document_id for facts in state.get("documents") or []}
    conn = get_connection()
    added = []
    try:
        for document_id, _filename in list_case_files(conn, case.case_id):
            if document_id in known:
                continue
            text = get_case_file_text(conn, document_id)
            if not text or not text.strip():
                continue
            facts = extract_document_facts(document_id, text)
            store_facts(conn, document_id, facts)
            added.append(facts)
    finally:
        conn.close()
    if not added:
        return {}
    return {"documents": list(state.get("documents") or []) + added}


def analyse(state: CaseState) -> dict:
    """Timeline, facts, issues, applicable law, precedents, missing facts,
    contradictions. One model call -- see legal_ai.agents.case."""
    from legal_ai.agents.case import analyse_case

    case = state.get("case")
    if case is None:
        return {"analysis": None}
    return {
        "analysis": analyse_case(
            case,
            tuple(state.get("documents") or []),
            list(state.get("evidence") or []),
        )
    }
