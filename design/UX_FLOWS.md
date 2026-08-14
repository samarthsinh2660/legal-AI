# UX / Information Architecture — Pramāṇa AI

## Who this is for

One shared product for practising advocates, law students, legal researchers,
and individuals with a real legal question. There is no mode switch and no
forked IA — complexity is handled per-answer through structure (a short lede
first, detail below) rather than by splitting the product in two.

## Navigation

A persistent left sidebar on desktop, collapsing to a 68px icon rail below
860px. A landing page sits outside the authenticated shell.

```
Landing  →  Sign in  →  ┌ Pramāṇa AI ────────────────┐
                        │  + New Research            │
                        │                            │
                        │  Home                      │
                        │  New Research              │
                        │  Cases  ──▶ case workspace │
                        │  Documents                 │
                        │  Judgments                 │
                        │  Legislation               │
                        │  Knowledge                 │
                        │  Saved                     │
                        │  History                   │
                        │  ──────────                │
                        │  Settings                  │
                        │  Riya Mehta · Researcher   │
                        └────────────────────────────┘
```

**Judgments**, **Legislation** and **Knowledge** are separate destinations
rather than one merged "Knowledge" section: searching case law, browsing an
Act section by section, and exploring the citation graph are three different
tasks with three different shapes.

This maps onto the agent architecture in
[`../docs/AI_PROJECT_PROPOSAL.md`](../docs/AI_PROJECT_PROPOSAL.md): New
Research ↔ Supervisor + research agents, Documents ↔ Document Agent, Cases ↔
Case/Analyst Agent, Judgments/Legislation ↔ the dynamic research tools,
Knowledge ↔ the static knowledge graph.

## Main user journey

```
Landing → Sign in → Dashboard → Ask a legal question
   → (optional) upload supporting document
   → Research progress → structured answer → click a citation
   → Source panel → Save authority to case
   → Case workspace (timeline, issues, authorities) → Research again

Cases can also be created directly: Cases → New Case → attach documents and
research threads as the matter develops.
```

## Screen 1 — Landing

Sells the discipline, not the model. Hero: *"Research Indian Law with
Evidence, Not Guesswork."* The hero visual is a realistic research interface
mid-run — the actual demo question, with live research steps ticking through
India Code, Supreme Court precedents, and citation verification — rather than
an abstract AI illustration.

Sections: the four-step workflow (Ask → Research → Analyze → Verify),
capability cards, three pillars (Trusted Knowledge / Dynamic Research /
Verified Answers), and a source-transparency strip naming India Code, the
Supreme Court, High Courts and eCourts. No fabricated partnerships or logos.

## Screen 2 — Dashboard

A research workspace, not a metrics dashboard.

- Greeting + *"What would you like to research?"*
- A large central ask box with example prompts, **Upload Document**, and
  **Ask Legal AI**
- **Recent research** — query, date, jurisdiction, source count, status
- **Quick actions** — New Research, Analyze Document, Search Judgments,
  Search Statutes

## Screen 3 — Research workspace

The most important screen. Three panes:

```
┌ Research context ┬──── AI conversation ────┬ Source details ┐
│ Part of case ▸   │  User question          │ Verified · [1] │
│   Patel v. Shah  │  Research progress ▾    │ Court, case    │
│ Jurisdiction     │  Structured answer      │ Citation       │
│ Active documents │  with inline [1][2][3]  │ Para 42 extract│
│ Upload context   │  ──────────────────     │ Why it matters │
│                  │  Ask a follow-up…       │ Open · Save    │
└──────────────────┴─────────────────────────┴────────────────┘
```

The **Part of case** block at the top of the context pane is what makes the
research/case relationship visible at a glance: it names the matter this
thread is attached to and links straight into that case workspace. An
unattached thread shows an *Attach to case* action in its place.

**Research progress** is a collapsible list of high-level steps — understand
the issue, search India Code, search Supreme Court, search Gujarat HC, compare
precedents, verify citations — with done / in-progress / pending states. It
shows real work, never fake "thinking".

**The answer is never one paragraph.** It renders in a fixed structure, which
is the contract between the Draft Agent's output and this screen:

1. A direct lede answering the question
2. **Applicable Law** — a tinted callout with the operative provision
3. **Key elements to prove** / analysis
4. **Key judgments**
5. **What may need further verification**
6. A transparency line: sources used, verification time, professional-advice
   disclaimer

Inline citations render as `[1]` markers; clicking one opens the right-hand
**Source details** panel with the court, case name, citation, the relevant
paragraph extract, why it matters, and Open / Save actions.

## Screen 4 — Documents

Split-screen: the document on the left over a sunken canvas (rendered like a
printed page — this is a real document, so it stays paper-white regardless of
surrounding chrome), the AI analysis on the right.

The analysis panel mirrors the Document Agent's responsibilities from
`../docs/PHASE_1_AI_RESEARCH_PLAN.md` §6:

- **Key facts** — document type, execution date, consideration
- **Legal issues detected** — each with a severity border and a
  `Page 1, Para 4` location reference that highlights the source passage
- **Important clauses**
- **Relevant statutory sections**
- A **Your document** provenance badge, making clear this is extracted
  evidence about the matter, not a statement of law

## Research vs. Case — the core distinction

These are the two primary objects in the product and the difference has to be
obvious in the UI, not just in the data model.

| | **Research thread** | **Case** |
|---|---|---|
| Answers | One question | An ongoing matter |
| Lifetime | Ephemeral unless attached | Persistent, months or years |
| Owns | A conversation + its citations | Documents, threads, issues, authorities, timeline |
| Agent | Supervisor → researchers → draft | Case Agent, over accumulated evidence |
| Context | Query + jurisdiction | Query + jurisdiction **+ case facts, parties, established findings** |
| Can exist alone | Yes | Yes (created empty, filled over time) |

The clean mental model:

```
RESEARCH   "What does Indian law say about X?"

CASE       "What does Indian law mean for THIS matter,
            given these documents, facts, history and research?"
```

**One case contains many research sessions.** That is the load-bearing
relationship, and the UI has to show it:

```
Case: Patel v. Shah
  ├── Research: "Can adverse possession apply?"
  ├── Research: "What proves ownership?"
  ├── Research: "Relevant Gujarat HC judgments"
  └── Research: "Limitation period"
```

A research thread can stand entirely on its own — a quick question needs no
case, and a user may run twenty unrelated sessions. When a thread does belong
to a matter it is **attached** to the case, and its context is then seeded
with that case's parties, timeline and already-established findings
(`../docs/AI_PROJECT_PROPOSAL.md` §6).

That attachment is what turns chat into a work product: the same question
asked inside *Patel v. Shah* already knows the 1998 deed, the
adverse-possession defence, and the authorities verified earlier in that
matter.

### Two entry points, both valid

**Flow A — start with research** (you don't yet know if this becomes a matter):

```
New Research → ask question → get answer
    → "Save to case" → choose existing case, or create a new one
```

**Flow B — start with a case** (a lawyer who already has the matter):

```
Create Case → enter case information → upload documents
    → Case Workspace → Start research
```

### What the Case Agent adds

Once a case holds `petition.pdf`, `sale_deed.pdf`, `notice.pdf`,
`court_order.pdf`:

```
Document Agent   extracts facts from those documents
       ↓
Research Agent   finds the law and the judgments
       ↓
Case Agent       connects both to THIS matter
```

Which is what makes case-scoped questions possible at all:

> "Based on the documents in this case and the authorities we've researched,
> what are the key legal issues?"

> "Which facts in our documents support the ownership claim?"

> "Which cases are most relevant to our facts?"

These appear as suggested prompts on the case workspace's **Research** tab,
so the difference from ordinary research is demonstrated rather than
explained.

## Screen 5a — Cases index

Reached from the sidebar. This is the screen that was missing while the
product jumped straight into a single hardcoded matter.

- **Page header** stating what a case *is*, plus a primary **New Case** button
- **An explainer band** contrasting Research (one question) with Case (an
  ongoing matter) — placed here because this is exactly where a new user asks
  "how is this different from just chatting?"
- **Status filters** — Active / Archived
- **Search** across cases
- **Case tiles** — matter type, status badge, title, one-line description,
  jurisdiction, counts of *Documents · Authorities · Research*, and a
  **Last activity** line
- **A dashed "Create a new case" tile** as the last card, so the action is
  available from the grid itself, not only the header

### Creating a case

The **New Case** modal collects only what actually seeds the case context:

```
Case title              cause title, or a working name
Matter type + Status    property / contract / tenancy / criminal …
Jurisdiction + Court    state, and the court (or "not yet filed")
Parties                 petitioner/plaintiff, respondent/defendant
Case number             e.g. SCA/14562/2022 — blank if not yet filed
Description             one or two sentences on the dispute
```

The description field is explicitly labelled as seeding the case context that
every agent is initialized with, so users understand why it's worth writing
properly rather than leaving blank.

## Screen 5b — Case workspace

Header: matter type, court, case name, and a one-paragraph description.
Tabs: **Overview · Timeline · Documents · Issues · Research · Authorities**.

- **Overview** — an AI case summary card (marked Verified) with a *Key
  finding* block, plus the case timeline
- **Timeline** — dated events, each linking back to the source document
- **Issues** — one card per legal issue, with the provision it turns on, the
  authority count, and a status: research in progress / completed / **conflict
  detected**
- **Research** — every research session belonging to this matter, with its
  sources, verification state and status. Above the list, an *Ask about this
  case* card offers case-scoped prompts and a **New research in this case**
  button, so a thread started here inherits the case context
- **Authorities** — the knowledge graph made concrete as a table: case, court,
  year, **relationship** (Follows / Interprets / Cites / Distinguishes /
  Overruled) and relevance
- Right rail: **Authorities** and **Documents** stat tiles, and the key-issues
  list

The *conflict detected* state exists because the architecture explicitly
requires identifying conflicting authorities and missing information rather
than smoothing over them.

## Screen 6 — Judgments

A dedicated case-law search experience, separate from the conversational
research flow — sometimes you know exactly what you're looking for.

- A single large query field (`"anticipatory bail"`)
- Filters: court, year, judge, act, section, citation
- Sort: relevance / most recent / most cited
- Each result shows the case in serif, court, year, citation chip, bench
  where notable, a relevance badge, and a **Why relevant** line explaining
  the match rather than just asserting a score
- Per-result actions: Open judgment · Save · **Add to case**

## Screen 7 — Legislation

The statute browser. Breadcrumb (Statute browser → Act) then the section
title in serif, with **View on India Code** linking to the primary source.

Left: **Statutory Text** with legislative history — including the IPC → BNS
correspondence, which matters constantly in current Indian practice — and
**Related Sections**. Right: **Key Interpretations** by year, with verified
marks and bench notes.

## Screen 8 — Knowledge

The citation graph, on its own rather than squeezed beside statutory text.

Entity search, node-type filters (Sections / Judgments / Acts), and a graph
canvas with the section as the central node and interpreting judgments
arranged around it, each labelled with its relationship. Below, a legend of
relationship types.

Relationship names are exactly those defined in
`../docs/AI_PROJECT_PROPOSAL.md` §9 — `interpreted_by`, `cites`, `follows`,
`distinguishes`, `overrules`, `refers_to`, `amended_by`, `contains` — not
UI-invented synonyms. The legend also states plainly that model-extracted
relationships carry an extraction confidence and must be verified before
being treated as fact.

## Screens 9–10 — Saved & History

**Saved** groups research, judgments and provisions into collections
(Property Law, Criminal Matters, …). **History** is a searchable table of
every query with date, jurisdiction, source count and status.

## Cross-cutting: the provenance rule

Wherever a claim, source or extraction appears, it carries one of:

```
STATIC KNOWLEDGE    curated, versioned foundation
DYNAMIC RESEARCH    retrieved live for this question
YOUR DOCUMENT       extracted from a user upload
VERIFIED            citation checked and standing
```

This is the UI expression of the three-layer data architecture in
`../docs/DATA_LAYER_ARCHITECTURE.md`, and of its critical rule: usage-derived
knowledge is never presented as authoritative.

## Not designed yet

- **Drafting** (notices, petitions, replies) — deferred to a later phase in
  `../docs/PHASE_1_AI_RESEARCH_PLAN.md` §8
- **Per-user knowledge graphs** — deferred in
  `../docs/DATA_LAYER_ARCHITECTURE.md` §14; Knowledge shows one global graph
- **Auth, billing, settings internals** — the sidebar entries are
  placeholders; only the design-system reference is built behind Settings
