"""The funnel -- stage order, routing, and what each mode costs.

The properties under test are structural: which stage settles a claim, that
the model is not consulted about anything already settled, and that the
cheap mode still refuses a fabricated citation.
"""

import json

import pytest

from legal_ai.knowledge.static.db import get_connection
from legal_ai.schemas.verification import Claim, Verdict
from legal_ai.agents import verifier as support_module
from legal_ai.verification.pipeline import verify

REAL = "act:2158:sec-18"
ALSO_REAL = "act:2158:sec-19"
FAKE = "act:9999:sec-does-not-exist"


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.close()


@pytest.fixture
def model(monkeypatch):
    """Records calls; answers SUPPORTED for everything asked."""
    calls = []

    def _generate(prompt, **kwargs):
        calls.append(prompt)
        count = prompt.count("CLAIM:")
        return json.dumps({"verdicts": [
            {"n": i, "verdict": "SUPPORTED", "why": "ok"} for i in range(1, count + 1)
        ]})

    monkeypatch.setattr(support_module, "generate", _generate)
    return calls


# ------------------------------------------------- stages 1-2, no model

def test_a_fabricated_citation_is_refused_without_the_model(conn, model):
    report = verify([Claim("invented", (FAKE,))], conn, use_model=True)

    assert report.verdicts[0].stage == "reference"
    assert report.model_calls == 0
    assert model == []


def test_the_cheap_mode_still_refuses_a_fabricated_citation(conn):
    """Cheaper means less checking effort, never no integrity.

    UNSUPPORTED, not INSUFFICIENT_EVIDENCE: an id that does not exist is a
    defect in the claim, not a gap in our shelf. Calling a fabricated
    citation "we could not check" would be the softest possible
    description of the thing this system most needs to report.
    """
    report = verify([Claim("invented", (FAKE,))], conn, use_model=False)

    assert report.verdicts[0].verdict is Verdict.UNSUPPORTED
    assert report.verdicts[0].stage == "reference"


def test_a_real_document_this_thread_never_read_is_a_gap_not_a_fabrication(conn):
    # The other half of the same distinction: the document is real, we
    # simply did not retrieve it. Re-research can fix that, so it is also
    # what needs_research exists to catch.
    report = verify([Claim("cites a real but unread section", (REAL,))],
                    conn, available_ids={ALSO_REAL}, use_model=False)

    assert report.verdicts[0].verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert report.needs_research == ["cites a real but unread section"]


def test_a_quick_mode_skip_does_not_trigger_re_research(conn):
    # Researching harder cannot supply a check the reader chose not to pay
    # for; looping on it would spend every pass to no effect.
    report = verify([Claim("a buyer may recover money", (REAL,))],
                    conn, available_ids={REAL}, use_model=False)

    assert report.verdicts[0].stage == "skipped"
    assert report.needs_research == []


def test_a_claim_citing_nothing_is_a_finding_against_it(conn):
    # A claim standing on nothing is a defect in the claim, not a gap in
    # our corpus, so it is UNSUPPORTED rather than INSUFFICIENT.
    report = verify([Claim("the law says so", ())], conn)

    assert report.verdicts[0].verdict is Verdict.UNSUPPORTED


def test_a_document_we_never_retrieved_is_a_gap_not_a_finding(conn):
    # We did not check this claim. Saying UNSUPPORTED would tell a lawyer
    # we checked and found against them.
    report = verify(
        [Claim("cites something unread", (REAL,))], conn, available_ids={ALSO_REAL}
    )

    assert report.verdicts[0].verdict is Verdict.INSUFFICIENT_EVIDENCE


# ----------------------------------------------------- stage 3, no model

def test_an_invented_quotation_is_caught_without_the_model(conn, model):
    claim = Claim(
        'Section 18 provides that "the promoter shall forfeit the entire project '
        'and surrender every licence to the authority forthwith".',
        (REAL,),
    )
    report = verify([claim], conn, available_ids={REAL}, use_model=True)

    assert report.verdicts[0].verdict is Verdict.UNSUPPORTED
    assert report.verdicts[0].stage == "quote"
    assert report.model_calls == 0
    assert model == []


# --------------------------------------------------------- stage 6 routing

def test_a_paraphrase_reaches_the_model(conn, model):
    report = verify(
        [Claim("a buyer may recover money from the promoter", (REAL,))],
        conn, available_ids={REAL}, use_model=True,
    )

    assert report.verdicts[0].stage == "semantic"
    assert report.model_calls == 1
    assert len(model) == 1


def test_claims_reaching_the_model_share_one_call(conn, model):
    claims = [
        Claim("a buyer may recover money", (REAL,)),
        Claim("interest is payable on the refund", (REAL,)),
        Claim("the authority supervises the promoter", (REAL,)),
    ]
    report = verify(claims, conn, available_ids={REAL}, use_model=True)

    assert report.model_calls == 1
    assert len(model) == 1
    assert model[0].count("CLAIM:") == 3


def test_the_model_is_not_asked_about_claims_already_settled(conn, model):
    settled = Claim("cites nothing", ())
    paraphrase = Claim("a buyer may recover money", (REAL,))

    verify([settled, paraphrase], conn, available_ids={REAL}, use_model=True)

    assert model[0].count("CLAIM:") == 1
    assert "cites nothing" not in model[0]


def test_nothing_reaches_the_model_when_stages_1_to_3_settle_everything(conn, model):
    report = verify([Claim("cites nothing", ())], conn, use_model=True)

    assert report.model_calls == 0
    assert model == []


# --------------------------------------------------------------- modes

def test_the_cheap_mode_makes_no_model_call(conn, model):
    report = verify(
        [Claim("a buyer may recover money", (REAL,))],
        conn, available_ids={REAL}, use_model=False,
    )

    assert report.model_calls == 0
    assert model == []


def test_an_unchecked_claim_is_marked_unchecked_not_approved(conn):
    # The cheap mode must not present a claim it never checked as verified.
    report = verify(
        [Claim("a buyer may recover money", (REAL,))],
        conn, available_ids={REAL}, use_model=False,
    )

    assert report.verdicts[0].verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert report.verdicts[0].stage == "skipped"
    assert report.verdicts[0].needs_flagging


# --------------------------------------------------------------- report

def test_no_claims_is_a_clean_empty_report(conn):
    report = verify([], conn)

    assert report.verdicts == [] and report.model_calls == 0
    assert report.all_supported


def test_insufficient_evidence_is_flagged_but_is_not_a_finding_against(conn):
    report = verify([Claim("cites something unread", (REAL,))], conn, available_ids=set())
    verdict = report.verdicts[0]

    assert verdict.needs_flagging
    assert verdict.verdict.is_a_finding_against_the_claim is False
    assert report.unsupported_texts == []


def test_every_verdict_records_the_stage_that_reached_it(conn, model):
    claims = [Claim("cites nothing", ()), Claim("a buyer may recover", (REAL,))]
    report = verify(claims, conn, available_ids={REAL}, use_model=True)

    assert {v.stage for v in report.verdicts} == {"reference", "semantic"}
