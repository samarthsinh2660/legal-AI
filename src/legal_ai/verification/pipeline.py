"""The verification funnel -- cheap deterministic stages first, model last.

Neither Shepard's nor KeyCite is a language model. They are citation graphs
and structured databases, and Lexis describes its own stack as taxonomies,
knowledge graphs, RAG and human review, with the model used where semantic
judgement is genuinely required. Harvey does not check good-law status with
a model either; it integrates Shepardizing.

So every question answerable by a lookup or a string comparison is answered
that way, before anything costs a token:

    1-2  citation exists, and this thread actually retrieved it   SQL
    3    quoted text appears in the cited document                strcmp
    6    the cited text supports the claim                        MODEL

Stages 1-3 can only reject. Stage 6 may only add rejections; it can never
overturn them.

Cost: one batched model call per answer for whatever stages 1-3 could not
settle, and none at all when they settle everything.
"""

from __future__ import annotations

import psycopg

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.schemas.verification import (
    Claim,
    ClaimVerdict,
    VerificationReport,
    Verdict,
)
from legal_ai.verification.groundedness import check_groundedness
from legal_ai.verification.quotes import check_quotations
from legal_ai.agents.verifier import check_support


def _fetch_sources(conn: psycopg.Connection, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT document_id, full_text FROM documents WHERE document_id = ANY(%s)",
            (list(ids),),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def verify(
    claims: list[Claim],
    conn: psycopg.Connection,
    available_ids: set[str] | None = None,
    use_model: bool = False,
    chain: tuple[str, ...] = DEFAULT_CONFIG.model_chain,
) -> VerificationReport:
    """Run the funnel over `claims`.

    `use_model` is the only thing the reader's verification level changes.
    Stages 1-3 always run: they cost nothing, and a fabricated citation
    reaching a user in the cheap mode would be indefensible. Cheaper means
    less checking effort, never no integrity.
    """
    if not claims:
        return VerificationReport()

    verdicts: list[ClaimVerdict] = []
    survivors: list[Claim] = []

    # --- stages 1-2: the citation exists, and we actually read it ---------
    grounded = check_groundedness(claims, conn, available_ids=available_ids)
    unsupported_by_reference = {id(claim): reason for claim, reason in grounded.unsupported}

    sources = _fetch_sources(
        conn, {doc_id for claim in grounded.grounded for doc_id in claim.evidence_ids}
    )

    for claim in claims:
        reason = unsupported_by_reference.get(id(claim))
        if reason is not None:
            # "cites no evidence" is a claim standing on nothing, which is
            # a defect in the claim. The other reasons are about documents
            # we do not hold or did not read -- a gap in our shelf, and
            # reporting that as a finding against the claim would tell a
            # lawyer we checked when we did not.
            verdict = (
                Verdict.UNSUPPORTED
                if reason == "cites no evidence"
                else Verdict.INSUFFICIENT_EVIDENCE
            )
            verdicts.append(ClaimVerdict(claim, verdict, reason, "reference"))
            continue

        # --- stage 3: quoted words must appear in the cited text ----------
        cited = {doc_id: sources.get(doc_id, "") for doc_id in claim.evidence_ids}
        quote_checks = check_quotations(claim.text, cited)
        invented = [check for check in quote_checks if not check.found]
        if invented:
            verdicts.append(ClaimVerdict(
                claim,
                Verdict.UNSUPPORTED,
                f"quotes words absent from the cited text: {invented[0].quote[:80]!r}",
                "quote",
            ))
            continue
        if quote_checks:
            # Every quoted span was found verbatim. Nothing a model could
            # add, so it is not asked.
            verdicts.append(ClaimVerdict(
                claim, Verdict.SUPPORTED, "quoted text found in the cited document", "quote"
            ))
            continue

        survivors.append(claim)

    # --- stage 6: paraphrase, which nothing mechanical can settle ---------
    if not survivors:
        return VerificationReport(verdicts=verdicts, model_calls=0)

    if not use_model:
        verdicts.extend(
            ClaimVerdict(
                claim,
                Verdict.INSUFFICIENT_EVIDENCE,
                "not checked: semantic verification was not enabled for this run",
                "skipped",
            )
            for claim in survivors
        )
        return VerificationReport(verdicts=verdicts, model_calls=0)

    semantic, calls = check_support(survivors, sources, chain=chain)
    verdicts.extend(semantic)
    return VerificationReport(verdicts=verdicts, model_calls=calls)
