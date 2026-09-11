What I'd do, in order

  ┌─────┬─────────────────────────────────────┬─────────────┐
  │     │               Change                │   Effort    │
  ├─────┼─────────────────────────────────────┼─────────────┤
  │ 1   │ Pinpoint into SourceLink            │ ~1 hour     │
  ├─────┼─────────────────────────────────────┼─────────────┤
  │ 2   │ Ask analyst for verbatim spans      │ prompt only │
  ├─────┼─────────────────────────────────────┼─────────────┤
  │ 3   │ Good-law node + answer slot + badge │ ~half day   │
  ├─────┼─────────────────────────────────────┼─────────────┤
  │ 4   │ Contrary-authority angle            │ ~half day   │
  └─────┴─────────────────────────────────────┴─────────────┘

  1 and 2 are nearly free and both raise how checkable an answer is. 3 is the one that changes what the product is — it's the difference between
  "here are provisions" and "here is law you can rely on".




vidence_builder.py:88 builds Location(paragraph=…, label=…) — "(1)", a proviso, "para 42". Evidence.location carries it.

  _sources() (agents/draft.py:175-195) never copies it into SourceLink.

  Reader sees [act:2158:sec-18]. A lawyer needs s.18(1) proviso. In legal work the pinpoint is the citation — an id without one isn't checkable
  at the speed a lawyer works.

  Cheapest fix in this list: add one field, copy one attribute, render it in citation-ref.tsx.

  3. Your strongest check almost never fires

  verification/quotes.py is the only stage that cannot hallucinate — pure string match, catches exactly the Delhi HC failure its docstring cites.

  It only fires on claims containing quotation marks. And analyst.PROMPT never asks for a quote.

  Add one rule to the analyst prompt — each claim carries one verbatim span of ≥40 chars from its source — and stage 3 flips from a rarity to the
  primary check, while stage 6 (the model verifier, your only per-answer model cost in verification) has less to do. Verification coverage goes
  up and cost goes down at the same time.

  4. Nothing looks for what cuts the other way

  research_plan.PROMPT asks for "distinct legal angles the question raises" and says prefer one angle. Correct for cost. But nothing ever
  searches for the exception, the proviso, or the contrary holding.

  The result reads as settled law even when it isn't. Practitioner surveys put "pressure-test the argument before I commit" in the top three.

  One extra planned angle, gated on the question being adversarial rather than lookup, plus a counter_authority slot rendered in its own block.

  5. No temporal currency

  Evidence has no date field. Nothing says "as amended by", "decided 1987", or "section repealed". An answer citing a repealed section renders
  identically to one citing live law — the same failure mode as #1, different axis.

      The output shape itself is already right

  DraftAnswer as slots rather than prose (schemas/answer.py), with needs_verification / unchecked / partially_supported as three separate blocks
  that never share a heading — that's the thing most tools get wrong. Don't change it.

  The gaps are all machinery you already built that never reaches the reader.

  ---

  1. Good-law status is built, tested, and never shown

  assess_good_law (retrieval/good_law.py), classify_treatments (agents/treatment.py), the reporter's own treatment table
  (ingestion/treatment_table.py) — all exist, all have tests.

  But the research graph is:

  document → context_builder → clarification → research → analyst → verification → draft → END

  build.py:58-79. No good-law node. DraftAnswer has no field for it. is_still_good_law lives in tools/graph.py:203 as an agent tool the main path
  never calls.

  So a user gets an overruled judgment cited with no mark on it. Your own CLAUDE.md §2 names OVERRULED vs NOT_CHECKED as a core third state —
  it's the one state that exists in code and renders nowhere. Web search confirms this is the #1 practitioner requirement: tools that "confirm
  cases are still good law."

  Cost: one node + one DraftAnswer field + one badge. Mostly wiring.












2 script of the data fix is there we have to run in the serve since worker nothing is done one more script is the 3 citation link fix




Good call to discuss first — this has a few real decisions in it. Here's how I'd think about it.

First: the law already tells us the rule, and it's in your corpus

Each new code ends with a repeal-and-savings section, and all three are sitting in your data — which is why their section counts are exactly 358, 531 and 170:

┌──────────┬──────────────┬──────────────────────────────────────────────────────────────────┐
│ New code │ Last section │                      What it says, in short                      │
├──────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
│ BNS      │ s.358        │ Offences committed before 1 July 2024 stay under the IPC         │
├──────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
│ BNSS     │ s.531        │ Proceedings already pending on that date continue under the CrPC │
├──────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
│ BSA      │ s.170        │ Repeal and savings for the Evidence Act                          │
└──────────┴──────────────┴──────────────────────────────────────────────────────────────────┘

So the system shouldn't invent the rule — it should cite those sections as the authority for it. Worth having a lawyer confirm the edge cases, though, because the deciding date isn't the same for every code:

- IPC vs BNS (what the offence is) → the date of the offence
- CrPC vs BNSS (how the case proceeds) → whether the proceeding was already pending

That's a real subtlety: a 2023 offence where the FIR was filed in 2025 is IPC for the offence but possibly BNSS for procedure.

When to show which — three situations

1. A case is attached. The case documents already have extracted dates. If the offence date is clearly before 1 July 2024 → lead with the IPC, mention BNS as successor. If there are several dates and it's unclear which is the offence → don't guess, show both.

2. A normal thread, and the question contains a date — "I was cheated in March 2023." The context builder already extracts this (relevant_date_from exists today — the clarification gate uses it for limitation). So we can decide the same way as a case.

3. A normal thread, no date — "What is the punishment for cheating?" This is the most common one, and the real decision. My recommendation:

▎ Cheating — BNS s.318, for offences on or after 1 July 2024.
▎ For offences before that date: IPC s.420.

Current law first, predecessor clearly labelled underneath. Not asking the user for a date — the clarification gate's own rule is "ask only when a missing fact makes the research wrong", and here both answers are right for their dates. Asking on every criminal question would train people to ignore the question.

The big dependency: we need a section mapping

To show "IPC s.420 → BNS s.318" at all, we need an IPC↔BNS, CrPC↔BNSS, IEA↔BSA table — about 1,300 rows.

This must come from an authoritative source, like the government's published correspondence tables. It must not be guessed by matching section titles or text similarity. A wrong mapping sends a lawyer to the wrong section, and it would look exactly as confident as a right one. Same reasoning as the treatment classifier, which isn't allowed to say OVERRULED until it's been measured.

The 13 vs 2,880 gap — why fixing it matters more than it looks

The fix itself is mechanical: re-resolve section references in the judgments now that the old codes exist in the corpus.

But combined with the mapping, it unlocks something valuable:

judgments discussing BNS     140
judgments discussing IPC   2,880

BNS is new, so it has almost no case law yet. Someone asking about BNS s.318 today gets almost nothing. With both fixed, they could see the IPC s.420 case law, clearly labelled as decided under the predecessor. Courts have been reading the new provisions in light of the old ones where the wording is the same — so that's what a lawyer would do by hand.

Dates on judgments

Show the decision date on every judgment — the data already exists for 99.5% of them:

▎ Rajesh v. State — (2019) 4 SCC 1 · Supreme Court · decided 2019, under IPC s.420

Cheap, and it answers "how old is this authority" without anyone having to ask.

Decisions I need from you

1. No-date questions: current law first with the old code underneath (my recommendation), or show both as equals?
2. The mapping source: do you have the official correspondence tables, or should I look for an authoritative published version? I'd rather do nothing than infer it.
3. Old case law for new-code questions: show IPC judgments on a BNS question, labelled as decided under the predecessor? I think yes — it's the only case law there is — but it's a judgement call about how much to lean on it.
4. Continuing offences — ones that span 1 July 2024. My instinct is always show both and say why. Worth checking with a lawyer.

Once those are settled, the build order would be: fix the citation links → load the mapping → dates on judgments → the old/new display rule.
