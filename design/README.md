# Pramāṇa AI — Design System & UI/UX

Brand identity, design system, and the interactive UI prototype for the
Indian Legal Intelligence Platform described in [`../docs`](../docs).

## Contents

| File | What it is |
|---|---|
| [`pramana-ui.html`](./pramana-ui.html) | The interactive prototype. Self-contained — open it directly in a browser. No build, no server, no network requests. |
| [`BRAND.md`](./BRAND.md) | Name and its meaning, mark, personality, voice, disclaimer posture. |
| [`DESIGN_SYSTEM.md`](./DESIGN_SYSTEM.md) | Colour, typography, spacing, elevation, shape, component inventory, responsive rules. |
| [`UX_FLOWS.md`](./UX_FLOWS.md) | Information architecture, the main user journey, and a screen-by-screen walkthrough. |
| [`Stitch Prompt — Indian Legal AI Web App UI.md`](./Stitch%20Prompt%20—%20Indian%20Legal%20AI%20Web%20App%20UI.md) | The source brief used to generate the approved direction. |
| [`brand/`](./brand/) | The logo rendering (`pramana-logo.png`) and the original Stitch token sheet (`STITCH_DESIGN_TOKENS.md`) the system was derived from. |

## Viewing the prototype

```bash
xdg-open design/pramana-ui.html   # Linux
open design/pramana-ui.html       # macOS
```

Roughly 240KB, with Playfair Display and Inter embedded as base64 so it
renders identically offline.

## What's in it

Landing page, then a full application shell:

| Screen | Contents |
|---|---|
| **Landing** | Hero with a live research demo, the Ask → Research → Analyze → Verify workflow, capability cards, three pillars, source transparency |
| **Dashboard** | Greeting, central ask box, recent research, quick actions |
| **Research** | Three-pane workspace: research context / conversation with a structured cited answer / source-details panel |
| **Documents** | Split document viewer with AI extraction — key facts, legal issues, clauses, statutory sections, page references |
| **Cases** | Index of matters with status filters and a **New Case** form; opens into the *Patel v. Shah* workspace — AI summary, timeline, documents, issues, authorities table with relationship badges |
| **Judgments** | Dedicated case-law search — query, filters (court/year/judge/act/section/citation), ranked results with a *why relevant* line |
| **Legislation** | Statute browser — statutory text, legislative history, related sections, key interpretations |
| **Knowledge** | The citation graph — entity search, node filters, relationship legend |
| **Saved / History** | Collections and a searchable research log |
| **Settings** | The design system itself, rendered live from the same tokens every other screen uses |

Everything is navigable — sidebar routing, case tabs, collapsible research
progress, selectable issue cards.

## Visual direction

Derived from the approved Stitch exploration (token sheet preserved at
[`brand/STITCH_DESIGN_TOKENS.md`](./brand/STITCH_DESIGN_TOKENS.md)):
warm off-white surfaces, deep charcoal text, hairline borders, and a single
refined indigo accent (`#2563EB`), with Playfair Display for case names and
statutes against Inter for everything the machine says.

Two pillars — **Institutional Authority** and **Computational Precision**.
The reasoning behind each token is in
[`DESIGN_SYSTEM.md`](./DESIGN_SYSTEM.md#direction).

## Why this exists

The architecture docs describe a system whose entire discipline is *evidence
over invention*: every claim traceable, every source carrying provenance and a
verification status. This design makes that discipline **visible** rather than
leaving it a backend concern — provenance badges, research-progress steps,
source panels with paragraph-level extracts, and explicit "what may need
further verification" blocks appear wherever a claim reaches a user.

## Maintaining this

All tokens live in the `:root` block at the top of the `<style>` element in
`pramana-ui.html`. No literal hex values appear anywhere else in the file, so
changing a token updates every screen at once — including the design-system
screen's own swatches, which read the same variables.

There is no build step. Edit the HTML, reload the browser.
