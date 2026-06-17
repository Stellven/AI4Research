# AI4Research GUI — Design Worklog

Isolated re-skin of the Solar Harness P0 GUI, rebranded **AI4Research**. All work
is on branch **`feat/p0-gui-claude`** in a separate worktree (`../solar-gui-claude`)
off `feat/p0-gui-react`. Nothing pushed/tagged. Zero cockpit/coordinator/scheduler/
planner/dispatch runtime changes — **UI + one perf fix only**. The original branch is
untouched, so the whole exploration is discardable.

**Stack:** React 18 + TS + Vite, served by a Python status server. Hand-written CSS
custom-property tokens in `src/styles.css` (single source of truth); components in
`src/App.tsx`; data shapes in `src/types.ts`; helpers in `src/format.ts`.

**Dev harness (dev-only, not shipped, in `/tmp/claude-mock-harness`):** a Python mock
that serves a deterministic **stalled** sprint fixture + injects latency; a Playwright
driver for screenshots / perf traces / computed-style probes / focus checks. Run: mock
on 8771, `PORT=8770 SOLAR_MOCK_API=http://127.0.0.1:8771 npm run dev`. Verify loop =
develop → screenshot (Playwright) → inspect (CDP computed styles + perf) → check
(WCAG contrast, typecheck, keyboard focus) → iterate.

---

## What was done, in order

### 0 · Toolchain setup
Installed (user scope): `frontend-design`, `chrome-devtools-mcp`, `playwright`.
Bundled fonts: **Schibsted Grotesk** (display/UI, SIL OFL) + **Geist Mono** (technical
values). Vetted + cloned (not wired): Impeccable, UI/UX Pro Max, accessibility-agents.
Note: plugins/skills installed mid-session don't load their slash-commands that session,
so I drove **Playwright + CDP directly** and applied the skills' *criteria* from their
files rather than via `/commands`.

### 1 · Perf fix (the lead item)
`useSessionData` had `await Promise.all([...5 endpoints...])` and set all state together,
so the DAG/plan/stall were held hostage by the slowest request (`/usage`). Rewrote to
**apply each slice as its own request resolves**, render the shell immediately (no
skeleton flash), stale-while-revalidate on session switch, and only show the hard-error
screen when core data is unreachable. **Measured (Playwright+CDP, /usage = 1500ms):
dashboard-derived content ~1700ms → ~445ms** (~3.8×); `/usage` fills independently.

### 2 · Design system + fonts
Authored **`DESIGN.md`** with machine-readable YAML token front matter + rationale body
(colors w/ a single `primary`, type scale + weight contrast, 4px spacing, radius, motion,
per-component states incl. focus ring, the signature element, a forbidden-defaults
ban-list incl. the "broadsheet/severe-minimal is itself an AI tell" trap, WCAG 2.2 AA
floor). Added a one-line pointer in `CLAUDE.md` so it auto-loads. Switched primary face
to Schibsted Grotesk; kept Geist Mono.

### 3 · Three signature variants → relay chosen
The spine: distinctiveness comes from the **subject** (multi-agent orchestration), not
borrowed minimalism. Built three takes on the stalled view, each a different "signature"
of the multi-agent gate: **relay** (agent baton + broken handoff), **dispatch**
(capability supply/demand ledger), **console** (mono operator log). Screenshotted all
three. **Owner picked `relay`**; dispatch/console removed from the app (archived in git
history).

### 4 · Rename + Codex-style home + explicit header
Renamed Solar Harness → **AI4Research** (brand, title, copy). Replaced the auto-redirect
to the first session with a **prompt-first landing** (chatbox + recent sessions). Original
lotus **`BrandMark`** SVG replaced the command glyph. Header made explicit (Task label +
status), removing the floating stall-subtitle; dropped the redundant **Plan** panel
(overlapped the agent signature). Decluttered the topbar (removed a non-functional
panel-toggle icon + a duplicate usage chip).

### 5 · Settings (interactive, honest)
Per-agent model selects, a lab-matrix segmented mode (All-Claude / All-GLM / Custom),
enable toggles, and provider API-key inputs (Anthropic, Z.ai). Honest banner: P0 has no
runtime write path, so nothing persists/transmits and **Save is disabled**.

### 6 · Token-usage architecture
**Per-sprint** tokens on the session view (reads `dashboard.data.sprint_usage`; honest
fallback to account-wide with a note when the runtime doesn't report per-sprint, since
`/usage` is account-wide and self-reports `not_per_sprint`). **Account-wide total** moved
to Settings ("Account token usage"). Deliverables cleaned: per-item page icon + type only
(MD/JSON), no byte size, no redundant section icon.

### 7 · Declutter pass
Stall stated **once** (was repeated 3×); quieter process stream (smaller titles,
timestamp-only kickers); controls back to **pills**; sidebar a faint translucency
(blur removed to honor the no-glassmorphism rule); WCAG AA fixes (darkened `subtle`
and `warning`); custom red/accent focus ring verified on keyboard nav.

### 8 · Huawei black/white/red theme (research-backed)
White canvas, ink `#1A1B1D` (not pure black), a cool 12-step neutral ramp, **Huawei red
`#CF0A2C` (PANTONE 186 C)** rationed as a *signal* (~<10%: lotus mark, active step, live
dot, focus, active relay agent). **Amber `#B26A00` owns "stalled"** (hue-separated so red
stays the brand, not the error color); "done" is quiet ink — no green.

### 9 · Process-as-hero
Demoted the repeated giant title to a thin **context bar**; the **process stream owns the
center**; the stall became a focal callout pinned at the head of the stream. *(Owner has
since asked to push this further — see the concept/wireframe pass; the stall card,
"Stalled" badge, "build phase", and redundant title are being removed in favor of the
relay's broken handoff + the stream itself.)*

---

## Research (two multi-agent workflows)
1. **Toolchain/craft research** — design-intelligence skills, browser MCPs, a11y tooling,
   the React/Vite stack, fonts + licensing, the DESIGN.md-as-harness pattern, and the
   craft references (Rauno/Vercel, Karri/Linear, Ström/Stripe) + anti-slop tells.
2. **AI4Research design research** — Huawei palette (exact hexes + red-rationing rules),
   coherence/harmony at Airbnb/Vercel/Linear/Stripe caliber, process-as-hero IA patterns
   + activity microcopy, deliverables presentation patterns, and a skills hunt (finding:
   there is **no** real "coherence/harmony" skill — the mechanism is the persistent
   design-system file, which is what DESIGN.md is).

## Verification done
Per change: `tsc --noEmit` (green), Playwright screenshots (multi-viewport), CDP
computed-style probes (confirmed Schibsted/Geist Mono actually applied, not fallbacks),
WCAG 2.1/2.2 AA contrast math on the palette, keyboard focus-ring check, and a production
`vite build` + smoke that the bundle boots.

## Open / not yet done
- Sync `DESIGN.md` tokens to the Huawei palette (still describes the old warm-paper/clay).
- Relay "flow" animation; full-bleed separation line; remove stall card/badge/phase/
  redundant title; selection/hover = darker grey fill; session status without grey dots
  (see concept/wireframe).
- Deliverables "pinned primary result when a final exists" (hybrid); richer step secondary
  microcopy; per-sprint model override (needs backend write path).
- Dead-code sweep (old Plan/dispatch/console code is inert but still in files).

## Commit trail (feat/p0-gui-claude)
perf (progressive load) · DESIGN.md + fonts · Schibsted/tokens/3 signatures · AI4Research
rename/home/header · interactive Settings · per-sprint + account usage · declutter/pills/
sidebar · lotus + relay-only · per-sprint usage fallback · Huawei theme · process-as-hero
— each with a `build:` commit rebuilding the static bundle.
