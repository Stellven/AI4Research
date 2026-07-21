# Gemini Deep Research — Harness Integration

End-to-end automation of Gemini Deep Research (DR) inside Solar-Harness:
take a research question (from a **user** or an **upstream operator**), optimize
it with the 李教授 prompt template, drive the DR web flow, monitor with retry,
and return a **classified, sourced** literature report — with machine-checkable
completion evidence instead of natural-language claims.

## The O1–O6 flow

| Outcome | What happens | Owner |
|---|---|---|
| O1 | Intake a `ResearchRequest` (user-direct **or** upstream-fed) | core controller |
| O2 | Optimize prompt via 李教授 template (mandatory classified-reference directive) | operator |
| O3 | Submit the DR job | operator |
| O4 | Confirm the research plan / start control | operator |
| O5 | Poll to terminal, classify state, retry on transient failure | core controller |
| O6 | Collect report + references; enforce success criteria | core controller |

The controller **never clicks**: all browser-side actions go through a
`BrowserOperatorPort`. The whole lifecycle is persisted as an append-only event
log, so any run can be reconstructed by replay and re-verified.

## Package layout

Two same-named packages, deliberately split by ownership:

- **Core runtime** — `lib/capabilities/gemini_deep_research/` (S03)
  - `schemas/` — data models (`ResearchRequest`, `OptimizedPrompt`, `DRPlan`,
    `DRRunHandle`, `DRResult`, `Reference`) + append-only `EventLog`
    (refuses secret-bearing payloads; writes under `var/`, never `/tmp`).
  - `core/` — `GeminiDRController` (O1–O6 state machine), `RetryPolicy` +
    `evaluate_success` (success criteria), `BrowserOperatorPort` protocol.
  - `compat/` — `DeepResearchBrowserAdapter` binds the port to the existing
    `browser_job_runtime` (the `DeepResearchBrowser` logical operator);
    `project_status` read-only run projection.
- **Orchestration / UI / evidence** — `integrations/gemini_deep_research/` (S04)
  - `orchestration/auto_activation.py` — `ready_nodes` (read-only DAG readiness),
    `decide_run_role` (run lifecycle → planner/builder/evaluator/human),
    `route_sprint` (pass-through to `workflow_guard`).
  - `ui/status_view.py` — epic → child-sprint → DAG-node tree projection
    (`build_epic_tree` / `render_text` / `to_dict`); blockers surface only when a
    sprint is genuinely waiting.
  - `evidence/completion_evidence.py` — `build_evidence` derives a structured
    completion packet from the event log; `verify_evidence` lets an evaluator
    re-derive the verdict instead of trusting prose.

Imports: core is importable top-level as `gemini_deep_research` (put
`lib/capabilities` on `PYTHONPATH`); the integration layer imports as
`integrations.gemini_deep_research` (harness root on path).

## Real-call gating (no quota spent by default)

Real Gemini web consumption is **OFF by default**. Set `GEMINI_DR_REAL_CALLS=1`
to drive the real browser; otherwise the adapter runs a mock job sequence that
exercises the full wiring against `browser_job_runtime` without spending DR
quota. In mock mode `collect` returns an **honest `FAILED`**
(`real_calls_disabled_no_research_output`) rather than fabricating references —
half-completion never masquerades as success.

## Success criteria (O6)

A run is `complete` only when: terminal state `done` + non-empty report +
`>= MIN_REFS` (3) references + at least one category + valid `http(s)` URLs.
Anything short (too few refs, not done, empty report) is an explicit `FAILED`
with a reason.

## Tests

From the harness root:

```bash
# S03 core (28) + S04 integration (24)
PYTHONPATH=lib/capabilities python3 -m unittest \
  gemini_deep_research.tests.test_core \
  integrations.gemini_deep_research.orchestration.test_auto_activation \
  integrations.gemini_deep_research.ui.test_status_view \
  integrations.gemini_deep_research.evidence.test_completion_evidence

# S05 V1 e2e O1–O6 flow
PYTHONPATH=lib/capabilities python3 -m pytest tests/gemini_deep_research/e2e -q

# S05 V2 negative-control + activation-proof
PYTHONPATH=lib/capabilities python3 -m pytest tests/gemini_deep_research/control -q
```

## Scope / safety

New capability lives entirely in `lib/capabilities/gemini_deep_research/`,
`integrations/gemini_deep_research/`, and `tests/gemini_deep_research/`. No
PROTECTED_CORE file is edited; the existing `workflow_guard`,
`graph_scheduler`, and `browser_job_runtime` are used read-only / through their
public functions.
