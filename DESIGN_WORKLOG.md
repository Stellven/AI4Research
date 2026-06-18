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

### 10 · Launcher crew · 3D logo · warm glass (2026-06-18)
Owner pass, research-grounded (a 5-agent design workflow: composer crew-picker IA, agent
matrix config, 3D-from-one-hue mark, lockup sizing, tinted glass).
- **Removed** the `{sprints.length}` "4" by the Sessions heading and the redundant home-page
  logo (it lives in the sidebar).
- **Brand mark → dimensional lotus.** Rebuilt `BrandMark` as a radial 5-petal lotus (pivot
  12,13; petals 72° apart, overlapping) with **three lightness steps of the one red hue**
  (`--lotus-front #cf0a2c` / `--lotus-mid #a60822` / `--lotus-back #7a0a1d`) painted
  back-to-front + a focal center node — 3D via occlusion, no glow/gradient/bevel. Fixed the
  "too short" complaint by **filling the viewBox** (old petals used ~56%): measured the mark
  box `40→80px` = the wordmark block `40→80px`, glyph `~44→79px` ≈ cap-of-line-1 →
  baseline-of-line-2. (Overrode the research's 28px/line-height-1.1 route — measurement showed
  parity already, and tightening line-heights had blast radius.)
- **Warm-glass sidebar.** Tint `rgba(252,252,253,0.82)` → `rgba(255,252,248,0.82)`
  (orange-leaning warm white, **not** pink — derived from an orange sibling, never `#cf0a2c`).
  Required paired AA change `--solar-subtle #74767d → #6e7077`; verified on the **sampled**
  composite (#FAF8F4): subtle 4.66 / muted 6.92 / ink 16.3:1 (old #74767d failed at 4.28).
  Confirmed the red active-tick still pops against the warm chrome.
- **Crew launcher (home composer).** Footer-left `Crew · {preset}` pill (monochrome at rest,
  no red) → **persistent inline disclosure** below the composer (not a hover dropdown — can't
  flicker): lab-matrix preset segmented + 4 per-agent model selects, seeded read-only from
  `fetchSettings().role_models`. **Staged-only & honest** — not sent with the intake, "Start
  work" launches on the runtime's configured crew; an action-strength note says so; no
  "Saved" state. Verified by Playwright: pill tracks selection, preset homogenizes rows +
  keeps panel open, per-row change flips to "Custom". Moved the CLI hint to a caption.
- DESIGN.md updated: `subtle` token, lotus shade tokens, two sanctioned-exception blocks
  (mark depth, warm glass), and the crew-launcher IA.

### 11 · Crew popover · build panes · lotus reshape (2026-06-18, owner-directed)
- **Crew → floating popover.** Owner wanted Codex-style: shrank the pill (~178→82px) and
  moved the crew config into a **Radix Popover** (click / click-outside / Esc, persistent,
  portaled — can't flicker). Added a **Build panes** stepper (parallel build workers) capped
  at the runtime's real `physical_operators.count` (4), seeded read-only; staged like the
  rest. Later, per owner, **removed the All-Claude/All-GLM/Custom preset row** — the user
  sets each agent's model directly (simplified `useCrew`: dropped labMode/applyPreset).
- **Lotus reshape.** The radial 5-petal mark read as a **sunflower**; owner asked for an
  actual lotus with the shades inside. Rebuilt `BrandMark` as an **upright lotus bloom**
  (7 petals fanning up from one base via `translate/rotate/scale`): outer petals `#7a0a1d`,
  mid `#a60822`, center/front `#cf0a2c` — the three shades give depth.
- Verified: tsc green, Playwright (pill 82px, popover opens/dismisses, stepper 1→4 capped,
  per-agent selects, no preset), prod-bundle smoke, logo zoom screenshot.

### 12 · Collapsible deliverables rail + inline preview (2026-06-18, owner-directed)
Owner spec: a Codex-style collapsible right rail with an in-panel file preview.
- **Rail.** Collapsed by default; `PanelRight` toggle in the run header (`aria-expanded`),
  `×`/toggle to close, open state persisted in **localStorage**. Docked desktop: width
  transitions 0 → 300px (list) → 480px (preview), run flexes to stay visible; **narrow:
  fixed overlay drawer + scrim**. Reduced-motion respected.
- **List state:** deliverables (clickable rows → preview) + per-sprint tokens.
- **Master-detail preview (inside the rail):** clicking opens the file inline — **never
  downloads / new-tabs by default** (those are explicit buttons). Back control, type-aware
  rendering — **markdown** via react-markdown + remark-gfm (**default-safe, no raw-HTML
  plugin** → agent content can't inject), **JSON** pretty-printed with a monochrome tonal
  highlight, **images** inline, plus a **raw-source toggle**. Lazy fetch from the EXISTING
  read endpoint `…/deliverables?path=` (confirmed against the real status-server handler:
  full content, matching content-types, no Content-Disposition — **no repo backend change**;
  the dev mock got content-serving + fixture bodies to match). Loading + error/retry.
- **a11y:** focus enters the preview on open and **returns to the originating row** on back;
  **Esc steps** preview → list → collapsed; preview body keyboard-scrollable.
- Deferred (flagged): collapsible JSON tree nodes; image preview path implemented but
  unverified (no image deliverable in the fixture).
- Verified: tsc green, Playwright a11y/behavior driver (collapsed=0 / list=300 / preview=480,
  focus in/out, Esc steps, localStorage persist), pixel screenshots (md table/code/blockquote,
  tonal JSON), **prod-bundle render smoke**. New deps: `react-markdown`, `remark-gfm`,
  `@radix-ui/react-popover`. DESIGN.md updated (deliverables-rail + per-agent crew + lotus).

---

## Research (three multi-agent workflows)
1. **Toolchain/craft research** — design-intelligence skills, browser MCPs, a11y tooling,
   the React/Vite stack, fonts + licensing, the DESIGN.md-as-harness pattern, and the
   craft references (Rauno/Vercel, Karri/Linear, Ström/Stripe) + anti-slop tells.
2. **AI4Research design research** — Huawei palette (exact hexes + red-rationing rules),
   coherence/harmony at Airbnb/Vercel/Linear/Stripe caliber, process-as-hero IA patterns
   + activity microcopy, deliverables presentation patterns, and a skills hunt (finding:
   there is **no** real "coherence/harmony" skill — the mechanism is the persistent
   design-system file, which is what DESIGN.md is).
3. **Launcher/logo/glass research** (iteration 10) — composer-attached crew/model-picker IA
   (Codex/Cursor/v0/Replit/Devin), multi-agent matrix config (CrewAI/AutoGen/LangGraph),
   3D-from-one-hue brand-mark occlusion, logo↔wordmark lockup sizing, and warm-tinted glass.
   *Caveat:* the synthesis hallucinated code-state from the **base** branch (`feat/p0-gui-react`
   — orange ramp, Geist, "Solar Harness") rather than this worktree; design decisions were
   used, every code-state claim was re-verified against the worktree, and sizing was decided
   by on-screen measurement (eyes over brief).

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
