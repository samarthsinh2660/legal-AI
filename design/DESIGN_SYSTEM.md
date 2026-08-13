# Design System — Pramāṇa AI

Every token below is defined as a CSS custom property at the top of
[`pramana-ui.html`](./pramana-ui.html). That file is the source of truth — if
this document and the CSS disagree, trust the CSS and correct this file.

The system is derived from the approved Stitch design exploration. Its
original token sheet is preserved at
[`brand/STITCH_DESIGN_TOKENS.md`](./brand/STITCH_DESIGN_TOKENS.md), and the
logo rendering at [`brand/pramana-logo.png`](./brand/pramana-logo.png). The
generated reference screens themselves have been removed now that every one
of them is reproduced in `pramana-ui.html`.

## Direction

Two pillars: **Institutional Authority** and **Computational Precision**.

The interface should read like a well-bound legal brief or an official
gazette — rigorous alignment, ample negative space, high-contrast text — not
like a tech-startup dashboard. The emotional target is calm reliability and
absolute transparency about where every statement came from.

Explicitly avoided: loud gradients, glassmorphism, cartoonish AI visuals,
generic chatbot layouts, dark "cyber AI" chrome, excessive animation, and
rainbow UI. One accent colour does all the chromatic work.

**Single committed light theme.** There is no dark mode and no
`prefers-color-scheme` branch. A warm off-white ground is part of the
paper-like identity, so the design commits to it rather than shipping a
second, weaker theme. Every colour is painted explicitly from a token.

## Colour

### Surfaces

| Token | Hex | Role |
|---|---|---|
| `--surface` | `#F9F9F9` | Page canvas — warm off-white, softer than pure white |
| `--surface-card` | `#FFFFFF` | Level 1: cards, panels, sidebar, top bar |
| `--surface-sunken` | `#F4F3F3` | Recessed: search field, document canvas, key-finding blocks |
| `--surface-muted` | `#EEEEEE` | Chips, inactive fills, citation markers |
| `--surface-tint` | `#EEF2FF` | Primary-tinted: active nav, callouts, AI avatar |

### Ink & structure

| Token | Hex | Role |
|---|---|---|
| `--ink` | `#1A1C1C` | Primary text |
| `--ink-variant` | `#434655` | Secondary text, body prose |
| `--ink-muted` | `#737686` | Metadata, captions, placeholders |
| `--line` | `#E5E5E5` | 1px hairline borders — the main structural device |
| `--line-strong` | `#C3C6D7` | Emphasised dividers, dashed drop zones |

### Primary — the single accent

| Token | Hex | Role |
|---|---|---|
| `--primary` | `#2563EB` | Refined indigo. Buttons, links, focus rings, active nav, verified marks. |
| `--primary-hover` | `#1D4FD8` | Hover state |
| `--primary-deep` | `#1E3A8A` | Wordmark and logo serif — a deeper, more editorial navy |
| `--on-primary` | `#FFFFFF` | Text on a primary fill |

Used *sparingly*. If a screen has more than one solid indigo button, one of
them is wrong.

### Provenance — the core idiom

The UX principle the product is built on: always make clear **what the AI
knows** vs **what it researched** vs **what came from your documents**. These
three badges appear wherever a claim, source, or extraction is shown. They are
deliberately quiet — neutral-leaning, never competing with the primary.

| Token | Hex | Label | Meaning |
|---|---|---|---|
| `--prov-static` | `#1B5E3F` | STATIC KNOWLEDGE | Curated, versioned foundation: Constitution, India Code, settled Supreme Court authority. Deep forest green. |
| `--prov-dynamic` | `#2563EB` | DYNAMIC RESEARCH | Retrieved live for this question. Authority depends on the named source. |
| `--prov-document` | `#434655` | YOUR DOCUMENT | Extracted from a user upload. Evidence about the matter — never a statement of law. |
| `--primary` | `#2563EB` | VERIFIED | The verification pass confirmed the citation exists, the paragraph supports the claim, and the authority stands. |

Each badge pairs its colour with a dot and a text label, so meaning survives
greyscale printing and colour-blindness.

### Semantic feedback

| Token | Hex | Use |
|---|---|---|
| `--ok` | `#1B5E3F` | Completed, analyzed, high relevance |
| `--warn` | `#94620B` | In progress, pending review, medium relevance |
| `--danger` | `#BA1A1A` | Conflict detected, overruled, distinguished, flagged clause |

Semantic colour is separate from the accent — a status is never mistaken for
a link.

## Typography

A dual-font strategy: the serif carries the authority of the *source*, the
sans carries the machine's *reading* of it.

| Role | Face | Used for |
|---|---|---|
| **Serif** | Playfair Display 700 | Case titles, statute headings, section heads, stat values, the wordmark — the "soul" of the content |
| **Sans** | Inter 400 / 500 / 600 | Navigation, AI analysis, tables, forms, labels — the "brain" of the platform |

Rules:
- Case names and statute titles are **always** serif, so they stand apart
  from AI-generated prose around them.
- `caps` (12px, 600, `0.05em` tracking, uppercase) for metadata labels —
  "Bench", "Date of judgment", "Research context".
- Body line-height stays at or above 1.5 so dense legal terminology doesn't
  crowd; answer prose runs at 1.7.

Both faces are embedded as base64 `@font-face` data URIs — no CDN, no network
request, works offline. Only the four weights actually used are included
(~128KB total).

### Scale

| Token | Size | Use |
|---|---|---|
| `--t-display` | 40px | Landing hero |
| `--t-title` | 32px | Case titles, page headings |
| `--t-heading` | 24px | Section heads |
| `--t-statute` | 20px | Statute/card serif heads |
| `--t-lg` | 18px | Answer body, hero subtitle |
| `--t-md` | 16px | UI body |
| `--t-sm` | 14px | Secondary text |
| `--t-xs` | 13px | Dense metadata, citations |
| `--t-2xs` | 12px | Caps labels |

## Layout & spacing

A strictly enforced **8px grid**: `--s1` 8, `--s2` 16, `--s3` 24, `--s4` 32,
`--s5` 40, `--s6` 48.

- Desktop target **1440px**; landing content caps at 1280px with 40px outer
  margins to evoke a printed page.
- Whitespace is generous *between* major sections but content *within* dense
  lists (search results, statute lists, authority tables) stays tight so a
  lawyer can scan volume quickly.
- Layout uses flex/grid `gap`, never per-element margins.

## Elevation

Depth comes from tonal layering and hairlines, not shadow.

- **Level 0** — `--surface`, all page backgrounds.
- **Level 1** — `--surface-card` with a 1px `--line` border. Cards, panels.
  No shadow.
- **Level 2** — `--shadow-2` (`0 4px 20px rgba(26,26,26,.08)`), reserved for
  genuinely floating things: the landing hero demo and the document page.
- **Active state** — no shadow. A 2px `--primary` left border marks the
  selected nav item; a `--primary` border marks a selected card.

## Shape

| Token | Value | Applies to |
|---|---|---|
| `--r-sm` | 4px | Citation markers, location refs, chips |
| `--r` | 8px | Buttons, inputs, small cards — modern without being bubbly |
| `--r-md` | 12px | Large containers, modals, composer |
| `--r-full` | pill | Badges, avatars, graph nodes — distinguishes them from actionable buttons |

## Component inventory

All rendered live with real data on the **Settings → design system** screen of
the prototype.

| Component | Class | Notes |
|---|---|---|
| Primary button | `.btn-primary` | Solid indigo, white text |
| Secondary button | `.btn-ghost` | White fill, 1px border |
| Provenance badge | `.badge-static` / `-dynamic` / `-document` / `-verified` | Dot + label |
| Status badge | `.badge-ok` / `-warn` / `-danger` | Completed / in progress / conflict |
| Relationship badge | reuses the above | Follows, Interprets, Cites, Distinguishes, Overruled |
| Citation chip | `.chip` | Mono-numeric, for `(2019) 8 SCC 729` |
| Inline citation | `.cite` | Clickable `[1]` marker that opens the source panel |
| Location ref | `.locref` | `Page 1, Para 4` — jumps to the document passage |
| Card | `.card` | White, 1px border, 12px radius |
| Stat tile | `.stat` | Serif value over a caps label |
| Tabs | `.tab` | Underline active, optional count pill |
| Research progress | `.progress-card` | Collapsible step list — done / doing / todo |
| Law callout | `.law-callout` | Tinted block with a 3px primary left border |
| Source panel | `.rw-source` | Right rail: badges, extract, why-it-matters, actions |
| Timeline | `.timeline` | Vertical, current event marked in primary |
| Authority table | `.auth-table` | Case / court / year / relationship / relevance |
| Entity graph | `.graph-canvas` | Dotted ground, central section node, related judgments |
| Case tile | `.case-tile` | Index card: type, status, title, counts. `.new` variant is the dashed create-case affordance |
| Filter pill | `.filter-pill` | All / Active / Closed, with counts |
| Explainer band | `.explainer` | Tinted two-column block distinguishing Research from Case |
| Linked case | `.linked-case` | Shows which matter a research thread belongs to |
| Modal | `.modal-backdrop` / `.modal` | New Case form. Closes on backdrop click and Escape |
| Form field | `.field` | Label, control, hint. Focus ring uses `--surface-tint` |
| Back link | `.back-link` | Detail → index navigation |
| Case picker | `.case-option` | Radio-style case selection in the Save-to-case modal |
| Result row | `.result-row` | Judgment search result: case, court, citation, relevance, *why relevant* |
| Filter grid | `.filter-grid` | Responsive search-filter block |

## Responsive behaviour

| Breakpoint | Behaviour |
|---|---|
| ≥1280px | Full three-pane research workspace (context / thread / sources); split document viewer |
| <1280px | Source panel hides; document analysis narrows |
| <1080px | Research context hides; all two-column layouts stack; document analysis moves below the page |
| <860px | Sidebar collapses to a 68px icon rail; single-column throughout; landing nav links hide |
