---
name: AI4Research GUI
version: 0.3-claude
description: >-
  Visual contract for the AI4Research multi-agent orchestration GUI.
  Read before any UI work. Tokens are the source of truth; the prose says why.
tokens:
  color:
    # Huawei-derived black / white / red. Red is a SIGNAL (~<10% of any view), never a field.
    ink: "#1a1b1d"            # primary text / filled black UI (not pure #000)
    canvas: "#ffffff"         # the page
    surface: "#fafafb"        # quiet raised surface
    surface_quiet: "#f4f4f6"  # sidebar / inset / hover+selected fill
    muted: "#54565c"          # secondary text
    subtle: "#6e7077"         # tertiary text / metadata (nudged from #74767d for AA over the warm-glass sidebar)
    faint: "#d8d9dd"          # disabled / skeleton
    line: "#e6e6ea"           # default hairline / divider
    line_soft: "#efeff1"      # faint row divider
    line_strong: "#d3d4d9"    # border on fills
    primary: "#cf0a2c"        # THE accent — Huawei red (PANTONE 186 C); active/now/brand/focus only
    primary_ink: "#a60822"    # darker red for small/dense red text (AA on white)
    lotus_mid: "#a60822"      # BRAND MARK ONLY — mid petal shade (same as primary_ink)
    lotus_back: "#7a0a1d"     # BRAND MARK ONLY — deepest petal shade; gives the lotus front->back occlusion depth
    blocked: "#b26a00"        # 'stalled' amber — hue-separated so red stays the brand, never the error
    blocked_fill: "#fbefd0"
    complete: "#3a3b40"       # 'done' is quiet ink + a check — NO green
    danger: "#a60822"         # hard errors only, with an explicit glyph (never plain brand red)
    neutral_ramp: "#ffffff #fafafb #f4f4f6 #e9e9ec #d8d9dd #c2c3c8 #9a9ca3 #74767d #54565c #3a3b40 #26272b #1a1b1d"
  typography:
    display:   { family: "Schibsted Grotesk", weights: [660, 770], tracking: "-0.014em" }
    body:      { family: "Schibsted Grotesk", weight: 400 }
    technical: { family: "Geist Mono", weight: 460, features: "tabular-nums" }
    scale_px: [11, 12, 14, 16, 20, 26]
    weight_contrast: "quiet 400 body vs 660-770 display; 500/660 mids — not a flat 400/700"
  space: { base: 4, major: [32, 48, 64] }
  radius: { control: 999, pill: 999, modal: 10, small: 6, region: 0 }   # controls are pills
  motion:
    ease: "cubic-bezier(0.16, 1, 0.3, 1)"
    fast: "120ms"
    base: "180ms"
    forbidden: [bounce, elastic, overshoot, slow-reveal-theater]
  focus: { ring: "2px solid var(--solar-accent)", offset: "3px", radius_px: 4 }
  signature: "the multi-agent subject made legible — an honest agent STATUS ROSTER (no fake linear flow/arrows) + a static activity-log process stream that is the accurate non-linear record"
---

# AI4Research GUI Design System

The visual contract for the AI4Research React GUI. It exists to prevent generic
AI-dashboard defaults and **must be read before visual UI work**. The YAML front
matter is the machine-readable token source; everything in `styles.css :root`
derives from it.

## Intent

AI4Research is a **multi-agent orchestration surface**: four named agents
(PM → Planner → Builder → Evaluator) hand work down a capability-routed DAG, and
the run **stalls honestly** when no agent advertises a needed capability. The
interface should feel quiet, exact, and operational — Codex/Linear/Vercel craft,
not a template dashboard. IA = a prompt-first home, then a per-session view whose
**process stream is the hero**, with a session sidebar and a slim results rail.

## The distinctiveness rule (the spine)

Distinctiveness comes from **the subject**, not borrowed minimalism. "Severe
minimalism" (hairline rules, zero radius, dense broadsheet columns) is itself an
AI-default tell. Identity here comes from making the **multi-agent relay**
legible: who acted, what was handed to whom, and exactly where a capability gate
held the work. Spend boldness in **one** place (the signature); keep the rest
quiet. Every element must earn its place — if it doesn't answer the view's one
question, cut it.

## Signature element

The subject (multi-agent orchestration) made legible — **honestly**. The
orchestration is a capability-routed **DAG, not a line**, so do NOT draw a fixed
PM → Planner → Builder → Evaluator pipeline with directional flow/arrows — that
implies a linearity that isn't real.

- **Agent roster:** the four agents as a non-sequential status row (each shows its
  real current state); no connectors, no flow.
- **Process stream:** a static activity log (oldest → newest) — icon + actor/action
  title + time-on-the-right + an inline secondary line + inline borderless mono
  facts. This is the *accurate* record of the (non-linear) handoffs. No
  click-to-expand cards.
- A **stall** is communicated by the blocked agent's state + the blocked step in
  the stream (raw tokens inline) — **not** a separate "Stalled" card, badge, or
  "Technical details" box.

## Color — Huawei black / white / red

Monochrome by rule, on a **white** canvas with **ink `#1a1b1d`** (never pure
`#000`) and a cool 12-step neutral ramp. **Red `#cf0a2c` is the one accent and a
SIGNAL only** — rationed to ~<10% of any view: the brand mark (lotus), the
active/now agent, the live marker, the selected mark, the focus ring, and at most
one primary action. Never paint fields of red; never red gradients/glows/shadows.
Use `primary_ink #a60822` for small/dense red text (AA). White-on-red is the only
red-fill text pairing.

- **Stalled = amber `#b26a00`** (hue-separated from red so brand red is never
  mistaken for the error/stuck color).
- **Done = quiet ink + a check.** No green — success is calm, expressed with
  neutral ink, reserving the hue budget for red (brand) and amber (stalled).
- Structure with neutrals (dividers, borders, muted/subtle text), so red pops.

**Sanctioned exception — brand mark depth (owner-approved 2026-06):** the lotus mark
(and ONLY the mark) is an upright **lotus bloom** — petals fan up from one base — using
three lightness steps of the one red hue: `#cf0a2c` front/center, `#a60822` mid, `#7a0a1d`
outer/back. Outer petals recede in the darkest red, the center/front petals are the bright
brand red, so the three shades give the bloom its depth (it must read as a lotus, not a
radial/sunflower). All three are the same hue and AA on white (5.6 / 7.8 / 11.1:1); depth
comes from per-petal shade + stacking order, never an intra-petal gradient/glow/bevel. It
stays one rationed signal.

Forbidden color moves: Tailwind defaults (indigo/slate/tailwind-blue); purple/
cyan/blue gradients; gradient text; **green** "success"; fields of red / red
gradients / red glows; pure `#000`; rosy/warm-tinted neutrals (keep grays cool so
red is the only warm-saturated thing); a second brand accent.

## Typeface

- **Display / UI / body: Schibsted Grotesk** (SIL OFL, self-hosted variable
  woff2). Extreme weight contrast: quiet 400 body vs 660–770 headings, 500/660
  mids — not a flat 400/700. (Research suggested a cooler grotesk like Inter for
  the Huawei feel; **Inter is on the forbidden list**, so we keep Schibsted.)
- **Technical: Geist Mono** (SIL OFL) — IDs, timestamps, capability/node names,
  decisions, paths, code, tabular numbers (`tabular-nums`). Never decorative.

Forbidden typefaces: Inter, Roboto, Open Sans, Lato, Arial, `system-ui` as a
primary choice, Space Grotesk.

Type scale (px): 11 micro · 12 label · 14 dense body · 16 body · 20 emphasis ·
26 compact display.

## Structure & layout (process-as-hero)

Card-less by default; structure from whitespace, type hierarchy, and hairline
dividers. The session view leads with a **thin context bar** (no repeated giant
title — the title lives once in the topbar), the **process stream owns the center
column**, and a **collapsible results rail** (Deliverables + per-sprint usage) is
summoned on the right (see the deliverables-rail contract below). Separation lines
may run **full-bleed** to the edges. Cards only for genuinely discrete, actionable
objects.

Forbidden structure: uniform card grids · nested cards · box/drop shadows ·
gradients · decorative illustration · centered-everything symmetry.

**Sanctioned exception (owner-approved):** the **sidebar** may use a tasteful
translucent/glassy material (subtle backdrop blur + tint) for depth, and may carry a
subtle **warm hue** (`rgba(255,252,248,0.82)` — orange-leaning, derived from an orange
sibling of the brand red, NOT `#cf0a2c`, which would read pink). The warmth is a
**surface**, not a signal — the rationed red still lives only on the mark / active tick
/ focus ring. Text contrast must stay AA over the warm composite (this forced `subtle`
from `#74767d` to `#6e7077`; verified subtle 4.66 / muted 6.92 / ink 16.3:1). Footer
links (Settings) remain clearly legible.

**Crew launcher (home composer):** a small footer-left `Crew` pill opens a **floating
popover** (Codex-style — Radix, click / click-outside / Esc, persistent open state, never a
hover dropdown) holding **per-agent (PM/Planner/Builder/Evaluator) model selects** (the user
sets each directly — no preset row) and a **build-panes** stepper (parallel build workers,
capped at the runtime's real operator budget `physical_operators.count`), all seeded
read-only from the runtime. It is **staged-only**: P0 has no write path, so the selection is
not sent with the intake and "Start work" launches on the runtime's configured crew. That
honesty line ships **both** in the popover and in the always-visible composer caption (so it
reads at the moment of action, not only when the popover is open); never add a "Saved"/
success state. A popover is a sanctioned elevated surface (restrained layered shadow, not a
heavy drop shadow).

**Deliverables rail (session view):** the results rail is **collapsed by default** (clean
two-pane run); a `PanelRight` toggle in the run header opens it (`aria-expanded`), `×` or the
toggle closes it, and the open/closed choice persists (localStorage). Docked on desktop, it
transitions width 0 → ~300px (list) → ~480px (preview) while the run flexes to stay visible
beside it; on narrow viewports it overlays as a fixed drawer + scrim. **Master-detail:**
clicking a deliverable opens it **inside** the rail (never download / open-in-new-tab as the
default — those are explicit buttons), with a back control, type-aware rendering (markdown
via react-markdown **default-safe, no raw-HTML**; JSON pretty-printed with a monochrome tonal
highlight; images inline; a raw-source toggle), lazy fetch from the existing read endpoint
(`…/deliverables?path=`) with loading + error/retry. a11y: focus enters the preview on open
and returns to the originating row on back; Esc steps preview → list → collapsed.

## Space

A 4px rhythm (8px-derived steps, multiples only). **When spacing feels merely
sufficient, double it.** Major gaps: 32 / 48 / 64px.

## Shape & motion

Controls are **pills** (999px); regions/rows stay square. Motion is short and
natural — `ease` cubic-bezier, 120ms fast / 180ms base, **transform + opacity
only**. The relay may show a restrained traveling *flow* highlight (not a glow) to
indicate handoff direction. Forbidden: bounce, elastic, overshoot, slow-reveal
theater. High-frequency UI appears instantly. `prefers-reduced-motion` respected.

## Micro-states (quality floor — every interactive element)

default · hover · **focus-visible (2px red ring, 3px offset)** · active · disabled
· loading. Every data view has **empty** and **error** states. **Selected ≠
hover:** selected/active rows take a persistent darker neutral fill
(`surface_quiet`) + a rationed red tick; hover is a lighter transient fill — not
motion alone. Collapsible steps keep a **persistent** expanded state (changed
background + rotated chevron + `aria-expanded`), so a toggle never reads as
momentary.

## Honest state rules (verify, do not assume)

- A stalled sprint **never** shows a filled percentage/progress bar or a
  synthesized "Result is available".
- A stall is shown by the **relay's broken handoff + the process stream's blocked
  step** (whose raw tokens like `no_matching_worker` live in that step's
  expandable detail) — not a separate alarming card.
- **Token usage:** per-sprint on the session view (`dashboard.data.sprint_usage`);
  honest fallback to the account-wide per-model/day signal (with a note) when the
  runtime can't attribute per-sprint. The **account-wide total lives in Settings**.
- Settings controls are real but **do not persist** in P0 (no runtime write path);
  say so plainly; Save is disabled.

## Accessibility floor (WCAG 2.2 AA)

Text ≥ 4.5:1, large/non-text/focus ≥ 3:1. Never rely on color alone (pair status
with text/glyph). Visible keyboard focus everywhere; logical order; no traps.
Reduced motion respected. Responsive to mobile.

## Centralization

All visual tokens live in `harness/status-server/react-app/src/styles.css` under
`:root` with the `--solar-*` prefix. Component CSS consumes tokens only — no
one-off color, shadow, gradient, or font.
