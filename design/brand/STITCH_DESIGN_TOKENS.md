---
name: Nyaya AI
colors:
  surface: '#f9f9f9'
  surface-dim: '#dadada'
  surface-bright: '#f9f9f9'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f3f3'
  surface-container: '#eeeeee'
  surface-container-high: '#e8e8e8'
  surface-container-highest: '#e2e2e2'
  on-surface: '#1a1c1c'
  on-surface-variant: '#434655'
  inverse-surface: '#2f3131'
  inverse-on-surface: '#f1f1f1'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#5f5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e2dfde'
  on-secondary-container: '#636262'
  tertiary: '#943700'
  on-tertiary: '#ffffff'
  tertiary-container: '#bc4800'
  on-tertiary-container: '#ffede6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#e5e2e1'
  secondary-fixed-dim: '#c8c6c5'
  on-secondary-fixed: '#1c1b1b'
  on-secondary-fixed-variant: '#474746'
  tertiary-fixed: '#ffdbcd'
  tertiary-fixed-dim: '#ffb596'
  on-tertiary-fixed: '#360f00'
  on-tertiary-fixed-variant: '#7d2d00'
  background: '#f9f9f9'
  on-background: '#1a1c1c'
  surface-variant: '#e2e2e2'
typography:
  display-case-title:
    fontFamily: Playfair Display
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  display-case-title-mobile:
    fontFamily: Playfair Display
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-statute:
    fontFamily: Playfair Display
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-ui-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-ui-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-ui-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-mono:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 8px
  container-max: 1280px
  gutter: 24px
  margin-desktop: 40px
  margin-mobile: 16px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
---

## Brand & Style
The design system is built on the pillars of **Institutional Authority** and **Computational Precision**. It serves legal professionals in India who require both the speed of AI and the gravity of traditional law. 

The visual style is **Sophisticated Minimalism**. It avoids the "tech-startup" aesthetic of high-saturation gradients and playful illustrations. Instead, it mirrors the experience of reading a well-bound legal brief or an official gazette. The interface relies on rigorous alignment, ample negative space, and a high-contrast palette to ensure information is the primary focus. The emotional response is one of calm reliability and absolute transparency.

## Colors
The palette is restrained to maintain professional focus and reduce cognitive load during long research sessions.

- **Surface (Warm Off-White):** #FDFCFB is used for all primary backgrounds to reduce the harshness of pure white while maintaining a paper-like quality.
- **Ink (Deep Charcoal):** #1A1A1A provides maximum legibility for body text and primary UI elements.
- **Accent (Refined Indigo):** #2563EB is used sparingly for primary actions, links, and "Source Verified" indicators.
- **Structure (Subtle Neutral):** #E5E5E5 is used for thin 1px borders to separate sections without adding visual weight.
- **Feedback:** Use a deep forest green for "Official Citations" and a muted crimson for "Overruled" status indicators, ensuring they remain within the professional tone of the system.

## Typography
This system employs a dual-font strategy to balance modernity with tradition.

1. **Serif (Playfair Display):** Reserved for the "Soul" of the content—case names, specific statutes, and authoritative quotes. It evokes the history of the Indian judiciary.
2. **Sans-Serif (Inter):** Used for the "Brain" of the platform—AI summaries, navigation, data tables, and input fields. It ensures clarity and speed of reading.

**Hierarchy Rules:**
- Case titles should always use the Serif font to stand out from the AI-generated analysis.
- Use `label-caps` for metadata like "Bench," "Date of Judgment," or "Citation Number."
- Maintain a line height of at least 1.5x for body text to handle complex legal terminology without crowding.

## Layout & Spacing
The system utilizes a strictly enforced **8px grid**. 

**Layout Model:**
- **Desktop:** 12-column fluid grid with a 1280px max-width. Use 24px gutters. Content should be centered with generous 40px outer margins to evoke the look of a printed document.
- **Mobile:** 4-column grid with 16px margins. 
- **Information Density:** While whitespace is generous between major sections (`stack-lg`), internal content like "Search Results" or "Statute Lists" should remain dense (`stack-sm`) to allow lawyers to scan high volumes of information quickly.

**Reflow:** On tablets, the sidebars (typically used for "Table of Contents" or "Cited Authorities") should collapse into a bottom sheet or a hidden drawer to prioritize the primary reading experience.

## Elevation & Depth
Depth is signaled through **Tonal Layering** and **Minimal Shadows**.

- **Level 0 (Base):** #FDFCFB. All main page backgrounds.
- **Level 1 (Card/Container):** Pure white (#FFFFFF) surfaces with a subtle 1px border (#E5E5E5). This is used for search result items and document containers.
- **Level 2 (Floating):** Used for dropdowns and context menus. Use an extremely soft, diffused shadow: `0px 4px 20px rgba(26, 26, 26, 0.08)`. 
- **Active State:** No shadows. Use a 2px Indigo (#2563EB) left-border accent to indicate a selected document or active navigation item.

## Shapes
The shape language is controlled and precise.

- **Standard Elements:** Buttons, input fields, and small cards use a **8px (0.5rem)** radius. This provides a modern feel without appearing too "bubbly" or informal.
- **Large Containers:** Content blocks and modals use a **12px (0.75rem)** radius.
- **Interactive Indicators:** Small badges (e.g., "Supreme Court", "High Court") use a full pill-shape to distinguish them from actionable buttons.

## Components
- **Primary Buttons:** Solid Indigo (#2563EB) with white text. 8px radius. Text in `label-caps`.
- **Secondary Buttons:** Ghost style with 1px border (#E5E5E5) and Charcoal (#1A1A1A) text.
- **Legal Cards:** White background, 1px border (#E5E5E5). The title of the case should be in `headline-statute`. Include a small indigo "Source Verified" icon in the top right.
- **Input Fields:** 1px border (#E5E5E5) that shifts to 2px Indigo (#2563EB) on focus. Placeholder text in muted charcoal.
- **Citations:** Inline chips with a light grey background (#F1F1F1) and mono-type styling for easy identification of reference codes (e.g., *2023 INSC 45*).
- **Source Transparency Panel:** A distinct sidebar or footer area within cards that uses a slightly different background tint (#F9F8F7) to list the specific paragraphs of a judgment from which the AI derived its summary.