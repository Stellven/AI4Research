# Session handoff — 2026-08-18

Worktree: `autosci-fixed-workflow/wt-evidence-to-poc`, branch
`task/research-evidence-to-poc-fixed`, base `7302ab2ba`.

Work single-threadedly. Do not create subagents.

## Environment facts (both prior blockers were misreadings)

- **Docker works.** `docker` on PATH is the Windows Docker Desktop shim and
  fails. A native Linux Docker Engine is installed via snap and running: use
  `/snap/bin/docker` (server 29.6.1 linux/amd64 on `/var/run/docker.sock`).
  Image built this session: `solar-harness-uat:20260818`,
  `sha256:95b6e2849b0ebc6759b2d64d5691cba0ccf86e46160fed7a7c2cd86769da8e18`.
- **Loopback binding works.** The old `PermissionError` is gone.
- **Windows interop is OFF** (`WSLInterop` binfmt not registered). No
  `explorer.exe` / `cmd.exe` / `wslview` can be launched. To hand the user a
  file, copy it to `/mnt/c/Users/ssubr/Downloads/` and give both paths.
- **Codex models:** `gpt-5.5` was quota-exhausted until 2026-08-19 23:46.
  `gpt-5.3-codex-spark` works and is what every run used
  (`SOLAR_CODEX_RESEARCH_MODEL`).
- **gstack browser:** `~/.solar/skills/gstack/browse/dist/browse`. Always
  `snapshot -i` after `goto` or refs are stale.
- **Stale servers bind 8766+.** Kill by PID via
  `ps -eo pid,cmd | grep symphony/status-server`. Never `pkill -f status-server.py`
  — it matches your own shell and kills the command.

## Committed

| commit | contents |
|---|---|
| `8d79c10a7` | dashboard-to-final path (request-id attribution, `SOLAR_INTENT_GATEWAY_DIR`, transient dispatch no-op, human-search diversion), dedicated capsules for A4-A8/B1-B3, A7 preservation fixes, AutoSci bridge revival (`cwd`), AutoSci capsule layer |
| `a82376f4d` | `autosci_skill_executor.py` — the seam that actually runs AutoSci — plus 7 tests |

## UNCOMMITTED (verified, but see the open failure below)

- `harness/lib/workflow_router.py` — `classify_research_request()`, three tiers:
  `simple` (no workflow) / `research_report` (`part_a_only`) /
  `research_poc` (`part_a_plus_poc`), plus a `classify` CLI command.
- `harness/plugins/autosci/operators/research_synthesis/base.py` —
  `research_query_terms()`, `subject_terms()`, `distill_search_query()`,
  `RESEARCH_INSTRUCTION_STOPWORDS`, `RESEARCH_GENERIC_TERMS`.
- `source_validation.py` — relevance gate now applies to **every** acquisition
  channel and requires a **subject-bearing** match.
- `source_discovery.py` + `production_research.py` — provider query is the
  distilled topic, not the raw request. `_topic_from_snapshot` distils only when
  the existing phrase patterns did not already strip the instruction, and never
  touches a fetched page title. Import of `distill_search_query` has a
  path-based fallback (with `sys.modules` registration) because the bridge runs
  it as a bare module.
- `physical-operators.json` — five `autosci-exec-*-worker` operators that run
  `autosci_skill_executor.py`.
- `research.evidence_to_poc.v1.workflow.json` — **version 1.4**; Part B science
  stages rebound to `cap.autosci-*`.
- New tests: `test_research_request_routing.py`,
  `test_source_relevance_gate.py`.

## The two contrivances that were found and fixed

The user challenged whether the demo was contrived. It was, in two ways, both
proven with a CRISPR prompt against the RAG-only frozen pack:

1. **The frozen pack bypassed relevance.** `_relevance_class` only checked
   query overlap for `live_search`; pack sources fell through to
   `content_described` purely because their title was >= 40 chars. A CRISPR
   request accepted **5 Retrieval-Augmented Generation papers** and produced a
   "source-linked, evidence-backed" report from them, passing every gate. The
   identical paper was `off_topic` by live search and `content_described` from
   the pack — the same bytes judged by provenance, not relevance.
2. **The search query was the raw prompt.** The whole instruction went to the
   providers, burying the topic. After the fix the same CRISPR request returns
   real CRISPR papers.

After the fix, the CRISPR request accepts **0** sources and **blocks at A4**
rather than fabricating a report. That is the correct behaviour.

There is a **third** contrivance, unfixed: the dashboard profile
`fixed_hybrid_demo_v1` sets `SOLAR_INTAKE_WORKFLOW_ID` for **every** prompt, so
routing is bypassed entirely. `classify_research_request()` exists to replace
that pin but **is not yet wired into the status server**.

## OPEN FAILURE — do not paper over

`tests/harness/workflow_contract/test_fixed_research_workflow.py::test_non_dry_registered_a1_to_a3_operator_runtime_daemon_and_solar_closeout`
fails with `Operator '...source-validation-worker' is not dispatchable: state=cooldown`.

Verified **not** caused by the relevance change: its fixture
(request "Research a bounded deterministic topic and produce an evidence-linked
report.", source "Deterministic contract source" / "Method: bounded retrieval…")
classifies as `content_described` with matched terms `['bounded','deterministic']`.
The cooldown is re-applied inside the test's own isolated harness, so something
else in that path fails first. **Root cause unknown.**

Separately, `test_non_dry_fixed_part_b_...[interactive-exact-plan]` was
intermittent earlier (2 of 4 combined runs, never in isolation, never captured).

## NEXT: the retrieval pipeline (the user's active request)

The user asked to research and implement better retrieval, mentioning **Serper**
and **Tavily** (free tiers), and offered to supply API keys. Measured evidence
from this session, query `mamba architecture transformer jepa`:

| provider | result |
|---|---|
| Semantic Scholar | **HTTP 429** without an API key — effectively absent in every run |
| OpenAlex | 118 hits, poor ranking; top hits were video diffusion and remote sensing |
| arXiv | **5/5 on-topic** (Mamba limitations, JEPA for 6G, Bi-Mamba+, UWM-JEPA, Sub-JEPA) |

Also measured: fewer, subject-only terms retrieve far better —
7 terms -> 39 hits of generic surveys; 3 terms -> 11,673 hits topped by the
canonical Mamba paper. `distill_search_query` is therefore capped at 5
subject-only terms.

Current policy providers are `['semantic_scholar', 'openalex', 'crossref']` and
the pipeline **unions** across them (confirmed: all three attempted per run).

Recommended, in order:

1. **Add arXiv** — free, no key, and by far the best of the three tested for
   ML/CS topics. Needs a backend, a policy-provider entry, capsule `effects.network`
   update, and tests.
2. **Decide on Serper/Tavily.** Both need keys the user must supply. They are
   web-search, not bibliographic, so they widen recall but weaken provenance —
   the evidence model assumes scholarly identifiers. If added, keep them a
   distinct acquisition channel so the relevance/provenance gates can treat them
   differently.
3. **Query fan-out.** Single-query lexical retrieval is inherently weak for
   comparative questions: `jepa` legitimately narrowed Mamba results from 11,673
   to 118 because few papers mention both. Issue several sub-queries and union.
4. Semantic Scholar needs an API key or it will keep 429ing.

The user also wants, later: simple prompts routed straight to `codex exec`, and
a semantic understanding layer for node difficulty/routing instead of regex.

## Architecture, as the user confirmed it

Part A (Solar: governance, evidence provenance, evaluators) -> Part B (AutoSci:
ideas, experiment design, benchmarking, claim verification) -> a final delivery
node. Part B is rebound to AutoSci but **the bridge only verifies evidence; the
executor is what runs the skills**, and Part B has never executed end to end.

Three-layer model for any new stage: **logical operator** (19 `Scientific*`
already exist) + **capability capsule** (the contract) + **physical operator**
(the command). Bindings map logical -> physical.

`experiment_approval` was left in place (150 references across 10+ files, and it
already does not pause). The user said no approval handling is needed; removing
the node is a separate refactor.

## UI

`DESIGN.md` governs. It forbids "fake linear flow/arrows"; done is quiet ink and
a check, **never green** — the user asked for green, which conflicts with the
token contract and needs `DESIGN.md` amended first. Confirmed real UI bugs, none
fixed: sprint title truncated in the **backend** (`workflow_intake.py:227`,
`request[:80]`, mid-word); the agent roster shows "Planner NOW" while
`target_role` is `builder_main` (likely derived from `phase: planning_complete`);
pending and done render identically.

Part B UI proposal (not implemented):
`docs/internal/agent_queue/PART_B_UI_PROPOSAL.md` and `.html`. Recommends a
stage roster plus an **evidence-lineage** panel over the 8 integrity checks —
real provenance chains with real hashes, not a drawn pipeline. AutoSci's own
graph is a **knowledge graph** (papers/concepts/methods), not an execution view,
and loads Cytoscape from a CDN, which would break the network-disabled container
UAT.

## Evidence roots

`artifacts/dashboard-full-uat-{,r2..r14}-20260818` (r13/r14 reach A1-A6),
`artifacts/adversarial-prompt-a-20260818` (the contrivance, before),
`artifacts/adversarial-prompt-a-final-20260818` (after: 0 accepted, 8 rejected).
Screenshots under each `screenshots/`.
