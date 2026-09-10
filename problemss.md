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












2 script of the data fix is there we have to run in the serve since worker nothing is done 