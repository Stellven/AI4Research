# Solar Harness GUI Design System

This file is the visual contract for the Solar Harness React GUI. It exists to
prevent generic AI-dashboard defaults and must be read before visual UI work.

## Intent

Solar Harness is an engineering orchestration surface: process stream, results,
and session sidebar. It should feel quiet, exact, and operational, closer to
Codex, Linear, and Vercel than to a template dashboard. The interface keeps the
existing information architecture; craft comes from type, spacing, honest state,
and disciplined restraint.

## Typeface

Chosen UI/display typeface: Geist Sans.

Why: Geist is engineered for developer products, has a crisp contemporary
grotesk shape, supports variable weights, and creates a Vercel-adjacent craft
signal without leaning on default system fonts. Solar Harness uses it as both UI
and display type, with extreme weight contrast: 300 for most text, 650-720 for
headings and critical labels. Avoid the common 400/700 pairing.

Chosen monospace: Geist Mono.

Usage: monospace is reserved strictly for IDs, timestamps, capability names,
technical tokens, code, raw decisions, and file paths. It is never decorative.

Forbidden typefaces:

- Inter
- Roboto
- Open Sans
- Lato
- Arial
- default `system-ui` stacks as the primary design choice
- Space Grotesk

Type scale:

- 11px technical microcopy
- 12px labels and metadata
- 14px dense body
- 16px primary body
- 20px section emphasis
- 24px compact display
- 32px page display

## Color

The palette is monochrome-by-rule, with semantic color used only for truthful
system state.

Canvas and neutrals:

- `--solar-canvas`: #f6f4ef, a tinted near-white canvas
- `--solar-surface`: #fbfaf7, a quiet near-white surface
- `--solar-ink`: #171714, a tinted near-black text color
- `--solar-muted`: #5d5b55
- `--solar-subtle`: #8d8981
- `--solar-faint`: #d8d4cb
- `--solar-line`: rgba(23, 23, 20, 0.12)
- `--solar-line-soft`: rgba(23, 23, 20, 0.07)

One accent:

- `--solar-accent`: #d85f1f

Use the accent like the Hermes-orange principle: one primary accented element
per view, usually the New task action or one selected/focus mark. Never use it
as decorative wash.

Semantic colors:

- Success: #2f6f4e
- Warning/stalled: #a36518
- Danger: #a64235

Semantic colors communicate actual system state only. They are not brand
accents.

Forbidden color moves:

- Tailwind defaults such as indigo-600, slate-900, Tailwind blue
- purple/cyan gradients
- gradient text
- green progress gradients
- tinted glass panels
- decorative colored icons

## Structure

The app is card-less by default. Content sits on the canvas. Structure comes
from whitespace, type hierarchy, and hairline dividers.

Forbidden structure:

- uniform card grids
- nested cards inside cards
- box shadows and drop shadows
- glassmorphism, blur, or frosted panels
- gradients
- decorative illustration
- centered-everything symmetry

Allowed grouping:

- 0.5px or 1px hairline dividers
- generous whitespace on a 4px scale
- asymmetric/editorial placement where it clarifies the work
- filled backgrounds only for true controls, dialogs, and semantic blocked/error
  regions

## Space

Use a 4px scale. When a spacing choice feels merely sufficient, double it.
The default major gaps are 32px, 48px, and 64px. Small controls still align to
4px increments.

## Shape And Motion

Controls may use full pills (`999px`) to soften the minimal operational tone.
Repeated content and regions should not become rounded cards. Use 0-8px radii
only where shape improves a control or modal.

Motion is short and natural:

- `--solar-ease`: cubic-bezier(0.16, 1, 0.3, 1)
- `--solar-duration-fast`: 120ms
- `--solar-duration`: 180ms

Forbidden motion:

- bounce
- elastic
- overshoot
- slow reveal theater

## Signature Token

Signature token: the Solar rule-line.

`--solar-rule` is a thin divider made from a neutral hairline plus a short accent
tick. It appears on selected navigation, active stage rows, and primary focus
regions. This is the consistent fingerprint; it replaces shadows and colored
cards.

## Honest State Rules

- A stalled sprint must never show a filled percentage/progress bar.
- Use discrete phase states: spec, PRD, plan, build.
- Passed stages are plain neutral checks.
- The blocked stage is amber, hollow, and explicit.
- Do not synthesize "Result is available" while a sprint is stalled.
- Token usage is labeled per-model/day, never per-agent or per-sprint.
- Header status appears once in plain language.
- Raw tokens such as `no_matching_worker` live behind a Technical details
  expander.

## Centralization

All visual tokens live in `harness/status-server/react-app/src/styles.css` under
the `:root` block and use the `--solar-*` prefix. Component CSS must consume
those tokens and avoid one-off color, shadow, gradient, and font choices.
