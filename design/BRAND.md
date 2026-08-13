# Brand — Pramāṇa AI

## Name

**Pramāṇa** (प्रमाण) — Sanskrit for *evidence*, *proof*, or *valid means of
knowledge*. In Indian epistemology, a *pramāṇa* is precisely the question of
**how you are entitled to claim you know something** — which is the exact
discipline this product enforces.

It names the core architectural principle from
[`../docs/AI_PROJECT_PROPOSAL.md`](../docs/AI_PROJECT_PROPOSAL.md):

> The AI should reason over legal evidence rather than invent legal knowledge.

"Nyaya" and "Kanoon" were considered and rejected — both are heavily used in
Indian legal tech (Indian Kanoon is itself one of the platform's candidate
data sources). Pramāṇa is distinctive, unclaimed in this space, and points at
*how* the system earns trust rather than merely what domain it works in.

Written with diacritics as **Pramāṇa AI** in the product wordmark; plain
"Pramana AI" is acceptable where diacritics can't be rendered.

Subtitle, where one is needed: **Indian Legal Intelligence**.

## Mark

A monogram **P** drawn as a single continuous stroke, with a balance-scale
glyph nested inside the counter and a distinctive fold at the lower left. The
scale is the legal signal; the unbroken stroke is the "chain of evidence"
reading; the fold reads as a turned page.

Two inks, both from the brand blues:

| Element | Colour |
|---|---|
| P stroke | `#2B56C4` — close to `--primary` |
| Scale, wordmark | `#1E2051` — close to `--primary-deep` |

The wordmark is a Didone-ish serif, which is why Playfair Display was chosen
as the system's display face: the UI's serif headings and the logotype belong
to the same family of shapes.

### Assets

| File | Use |
|---|---|
| [`brand/pramana-logo.png`](./brand/pramana-logo.png) | Original 1024×1024 master |
| [`brand/pramana-lockup.png`](./brand/pramana-lockup.png) | Mark + wordmark, 475×132, transparent — the default lockup |
| [`brand/pramana-mark.png`](./brand/pramana-mark.png) | Mark alone, 113×132, transparent — for the collapsed sidebar and favicons |

The prototype embeds the lockup and the mark as base64 PNGs rather than a
redrawn SVG. An earlier attempt to trace the mark by hand produced something
recognisably *not* the logo, so the artwork itself is the source of truth.
Both are cropped from the master, made transparent, and palette-quantised —
about 11KB combined, and they render correctly on any background.

Displayed at 34px tall (lockup) and 32px (mark) against artwork ~4× that
height, so it stays crisp on high-density displays.

## Personality

**Institutional Authority + Computational Precision.**

The product serves both practising advocates and individual citizens with
real legal exposure. It should feel like a well-bound brief or an official
gazette — precise, unhurried, quietly confident — never like a consumer chat
toy, and never like a "cyber AI" console.

In practice:

- **Precise over friendly.** "7 of 7 citations verified", not "All set!".
- **Evidence visible, not implied.** Every claim carries a source, a
  provenance badge, and where relevant a paragraph reference. This is the
  brand's single most important visual behaviour, not a feature.
- **Confident, not overconfident.** Assumptions are separated from
  established law. Contradictions, conflicting benches, and missing facts are
  surfaced — the *What may need further verification* block is a required
  part of every answer, not an optional footer.
- **Restrained.** One accent colour. No exclamation points, no emoji, no
  decorative motion.

## Voice

Three lines from the project's own guiding principles
(`../docs/AI_PROJECT_PROPOSAL.md` §12) serve as the voice check — product copy
should sit comfortably beside them:

> "The LLM is not the source of truth."

> "User feedback never directly overrides authoritative law."

> "Verification is a first-class component, not an afterthought."

Write from the reader's side of the screen — a lawyer or a citizen with a real
question, not a description of the pipeline serving them. "12 sources
verified" beats "verification agent completed successfully". Call the
research trace **Research progress**, never "AI thinking".

## Disclaimer posture

Every answer carries a transparency line — sources used, when citations were
last verified, and that this does not replace advice from a qualified legal
professional. It is treated as a required output field of the Draft Agent,
the same as citations.

It must be *present and honest* without dominating the interface: one quiet
line under the answer, not a banner competing with the content.

## What the brand is not

- Not a ChatGPT clone — the answer is a structured legal document, not a
  chat bubble.
- Not a "modern legal-tech startup" look — no gradients, no glass, no
  rounded-everything cards.
- Not NyayAssist. The competitor was studied for what reads as professional
  in this category; none of its branding, copy, or visual identity is used.
- Not decorative. Every badge, chip, and colour encodes a real distinction
  the backend can actually produce. If a proposed UI element doesn't map to
  something real, it doesn't ship.
