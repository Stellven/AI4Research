---
name: Solar Harness GUI
version: 0.2-claude
description: >-
  Visual contract for the Solar Harness multi-agent orchestration GUI.
  Read before any UI work. Tokens are the source of truth; the prose says why.
tokens:
  color:
    ink: "#17171a"            # near-black text (slightly cool)
    canvas: "#f3f2ee"         # neutral warm paper — deliberately off the cream/terracotta default
    surface: "#faf9f6"        # quiet raised surface
    surface_quiet: "#ecebe6"  # sidebar / inset
    muted: "#56555a"          # secondary text
    subtle: "#88877f"         # tertiary text / metadata
    faint: "#d7d5ce"          # disabled / skeleton
    line: "rgba(20,19,24,0.12)"
    line_soft: "rgba(20,19,24,0.06)"
    line_strong: "rgba(20,19,24,0.22)"
    primary: "#b23a1e"        # THE single accent: now/active/primary-action/focus. <5% of viewport.
    blocked: "#9a6212"        # honest stall — rendered HOLLOW/amber, calm, never alarming
    complete: "#3f6150"       # quiet de-emphasized "done"; success is calm, not celebratory
    danger: "#9e3a2d"         # hard errors only
  typography:
    display:   { family: "Schibsted Grotesk", weights: [620, 720], tracking: "-0.012em" }
    body:      { family: "Schibsted Grotesk", weight: 320 }
    technical: { family: "Geist Mono", weight: 460, features: "tabular-nums" }
    scale_px: [11, 12, 14, 16, 20, 26]
    display_size: "clamp(2rem, 3vw, 3.05rem)"
    weight_contrast: "300/320 body vs 620-720 display — never the 400/700 default"
  space: { base: 4, major: [32, 48, 64] }
  radius: { control: 8, pill: 999, modal: 10, region: 0 }
  motion:
    ease: "cubic-bezier(0.16, 1, 0.3, 1)"
    fast: "120ms"
    base: "180ms"
    forbidden: [bounce, elastic, overshoot, slow-reveal-theater]
  focus: { ring: "2px solid var(--solar-accent)", offset: "3px", radius_px: 4 }
  variants:
    relay:    { primary: "#b23a1e", signature: "agent relay spine + broken handoff at the stall" }
    dispatch: { primary: "#1f6f5c", signature: "capability supply/demand gate as the stall hero" }
    console:  { primary: "#b5790d", signature: "mono operator log + a held dispatch line" }
---

# Solar Harness GUI Design System

The visual contract for the Solar Harness React GUI. It exists to prevent
generic AI-dashboard defaults and **must be read before visual UI work**. The
YAML front matter above is the machine-readable token source; everything in
`styles.css :root` derives from it.

## Intent

Solar Harness is a **multi-agent orchestration surface**: four named agents
(PM → Planner → Builder → Evaluator) hand work down a capability-routed DAG,
and the run **stalls honestly** when no agent advertises a needed capability.
The interface should feel quiet, exact, and operational — closer to Codex,
Linear, and Vercel than to a template dashboard. The information architecture
(process stream · results rail · session sidebar) is inherited; craft comes
from type, spacing, honest state, and disciplined restraint.

## The distinctiveness rule (the spine)

Distinctiveness must come from **the subject**, not from borrowed minimalism.
"Severe minimalism" — hairline rules, zero radius, dense broadsheet columns —
is itself one of today's AI-default looks; adopting it as a default is as much
a tell as a purple gradient. So identity here comes from making the **multi-
agent relay** legible: who acted, what was handed to whom, and exactly where a
capability gate held the work. Spend boldness in **one** place (the signature);
keep everything else quiet.

## Signature element (subject-derived)

The signature is **agent attribution + the handoff/gate**, not decoration.
Three expressions are under review (pick one):

- **relay** — a vertical agent spine; each process step is anchored to the agent
  that performed it, and the stall renders as a *broken handoff* where the baton
  cannot pass (no agent provides the capability).
- **dispatch** — the stall is framed as a *dispatch gate*: a compact
  supply/demand ledger (demanded capability vs what each of the four agents
  provides) with the gap called out.
- **console** — an honest *operator log*: agent · time · node in mono, hairline
  rows, the stall as a single "held" dispatch line.

A view has exactly one signature move. Resist adding a second.

## Typeface

- **Display / UI / body: Schibsted Grotesk** (SIL OFL, self-hosted variable
  woff2). A UI-purpose neo-grotesk with more editorial character than Inter or
  Geist — and notably *not* Geist, which has itself become a Vercel/AI tell.
  Use **extreme weight contrast**: 300/320 for most text, 620–720 for headings
  and critical labels. Never the default 400/700 pairing.
- **Technical: Geist Mono** (SIL OFL). Reserved strictly for IDs, timestamps,
  capability names, node ids, decisions, file paths, code, and tabular numbers
  (`font-variant-numeric: tabular-nums`). Never decorative.

Forbidden typefaces: Inter, Roboto, Open Sans, Lato, Arial, `system-ui` as a
primary choice, **Space Grotesk**, and **Geist Sans as the display face**
(reserved to Mono only here).

Type scale (px): 11 micro · 12 label · 14 dense body · 16 body · 20 emphasis ·
26 compact display · `clamp(2rem,3vw,3.05rem)` page display.

## Color

Monochrome-by-rule. Semantic color communicates **truthful system state only**,
never brand decoration. One accent per view, used like punctuation (<5% of the
viewport saturated). Each variant carries a distinct `primary` (see front
matter) so the three reads are genuinely different.

- Neutrals: `ink #17171a` on `canvas #f3f2ee`; `surface`, `surface-quiet`,
  `muted`, `subtle`, `faint`, and three hairline `line` strengths.
- `primary` — active/now, the primary action, the focus ring, the selected mark.
- `blocked` — the honest stall, drawn **hollow/amber**, calm not alarming.
- `complete` — quiet and de-emphasized; "done" is not a celebration.

Forbidden color moves: Tailwind defaults (indigo-600, slate-900, tailwind
blue); purple/cyan/blue gradients; **gradient text**; **green progress
gradients**; tinted glass panels; decorative colored icons; the
**warm-cream + terracotta** default pairing as the whole-app look.

## Structure

Card-less by default — content sits on the canvas; structure comes from
whitespace, type hierarchy, and hairline dividers. Cards only for genuinely
discrete, actionable objects, and then varied by role (not a uniform grid).

Forbidden structure: uniform card grids · nested cards · box/drop shadows ·
glassmorphism/blur/frost · gradients · decorative illustration ·
centered-everything symmetry.

Allowed grouping: 1px hairline dividers · generous 4px-scale whitespace ·
intentional asymmetry where it clarifies the work · filled backgrounds only for
true controls, dialogs, and semantic blocked/error regions.

## Space

A 4px scale. **When a spacing choice feels merely sufficient, double it.**
Default major gaps: 32 / 48 / 64px. Controls still align to 4px increments.

## Shape & motion

Controls may use a small radius (8px) or full pills for true controls; regions
and rows stay square (0). Motion is short and natural — `ease` cubic-bezier,
120ms fast / 180ms base, **transform + opacity only**, GPU-friendly. Forbidden:
bounce, elastic, overshoot, slow-reveal theater. High-frequency UI appears
instantly (no fade). `prefers-reduced-motion` is respected.

## Micro-states (quality floor — every interactive element)

default · hover · **focus-visible (custom ring: 2px `primary`, 3px offset,
4px radius)** · active · disabled · loading. Every data view also has **empty**
and **error** states. Inputs respond immediately. No dead hover states; no
un-eased snaps.

## Honest state rules (verify, do not assume)

- A stalled sprint **never** shows a filled percentage/progress bar.
- Use discrete phase states: spec · PRD · plan · build. Passed = plain neutral
  check; the blocked stage = amber, **hollow**, explicit.
- **Never** synthesize a "Result is available" / completed step while stalled.
- Token usage is labeled **per-model/day**, never per-agent or per-sprint.
- Header status appears once, in plain language ("No agent provides X").
- Raw tokens (`no_matching_worker`) live behind a **Technical details** expander.

## Accessibility floor (WCAG 2.2 AA)

Text contrast ≥ 4.5:1, large text / non-text / focus indicators ≥ 3:1. Visible
keyboard focus on every interactive element; logical focus order; no keyboard
traps. Reduced motion respected. Responsive down to mobile.

## Centralization

All visual tokens live in `harness/status-server/react-app/src/styles.css`
under `:root` with the `--solar-*` prefix (and `[data-variant]` overrides).
Component CSS consumes tokens only — no one-off color, shadow, gradient, or font.
