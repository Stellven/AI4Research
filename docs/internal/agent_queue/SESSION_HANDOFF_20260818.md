# Session handoff - 2026-08-18

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
  - it matches your own shell and kills the command.

## Committed

| commit | contents |
|---|---|
| `8d79c10a7` | dashboard-to-final path (request-id attribution, `SOLAR_INTENT_GATEWAY_DIR`, transient dispatch no-op, human-search diversion), dedicated capsules for A4-A8/B1-B3, A7 preservation fixes, AutoSci bridge revival (`cwd`), AutoSci capsule layer |
| `a82376f4d` | `autosci_skill_executor.py` - the seam that actually runs AutoSci - plus 7 tests |
| `ecbeb0d7a` | relevance gate over every acquisition channel, query distillation, request-tier routing, Part B rebound to `cap.research-external-*` (contract v1.4) |
| `f30e8a311` | this handoff and the Part B UI proposal |

## Was uncommitted, now in `ecbeb0d7a`

- `harness/lib/workflow_router.py` - `classify_research_request()`, three tiers:
  `simple` (no workflow) / `research_report` (`part_a_only`) /
  `research_poc` (`part_a_plus_poc`), plus a `classify` CLI command.
- `harness/plugins/autosci/operators/research_synthesis/base.py` -
  `research_query_terms()`, `subject_terms()`, `distill_search_query()`,
  `RESEARCH_INSTRUCTION_STOPWORDS`, `RESEARCH_GENERIC_TERMS`.
- `source_validation.py` - relevance gate now applies to **every** acquisition
  channel and requires a **subject-bearing** match.
- `source_discovery.py` + `production_research.py` - provider query is the
  distilled topic, not the raw request. `_topic_from_snapshot` distils only when
  the existing phrase patterns did not already strip the instruction, and never
  touches a fetched page title. Import of `distill_search_query` has a
  path-based fallback (with `sys.modules` registration) because the bridge runs
  it as a bare module.
- `physical-operators.json` - five `autosci-exec-*-worker` operators that run
  `autosci_skill_executor.py`.
- `research.evidence_to_poc.v1.workflow.json` - **version 1.4**; Part B science
  stages rebound to `cap.research-external-*`.
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
   the pack - the same bytes judged by provenance, not relevance.
2. **The search query was the raw prompt.** The whole instruction went to the
   providers, burying the topic. After the fix the same CRISPR request returns
   real CRISPR papers.

After the fix, the CRISPR request accepts **0** sources and **blocks at A4**
rather than fabricating a report. That is the correct behaviour.

There is a **third** contrivance, unfixed: the dashboard profile
`fixed_hybrid_demo_v1` sets `SOLAR_INTAKE_WORKFLOW_ID` for **every** prompt, so
routing is bypassed entirely. `classify_research_request()` exists to replace
that pin but **is not yet wired into the status server**.

## The cooldown failure - resolved as unreproducible, NOT as fixed

`test_non_dry_registered_a1_to_a3_operator_runtime_daemon_and_solar_closeout`
now passes in isolation, with the other two `non_dry` tests, across the whole
`test_fixed_research_workflow.py` file (65 passed), and across the whole
`tests/harness/workflow_contract` directory (205 passed). Nothing was changed to
make it pass, so treat it as an unexplained intermittent, not a fixed defect. If
it returns, capture the failing run before touching anything.

Historic detail:

Verified **not** caused by the relevance change: its fixture
(request "Research a bounded deterministic topic and produce an evidence-linked
report.", source "Deterministic contract source" / "Method: bounded retrieval…")
classifies as `content_described` with matched terms `['bounded','deterministic']`.
The cooldown is re-applied inside the test's own isolated harness, so something
else in that path fails first. **Root cause unknown.**

Separately, `test_non_dry_fixed_part_b_...[interactive-exact-plan]` was
intermittent earlier (2 of 4 combined runs, never in isolation, never captured).

## Retrieval pipeline (DONE - measured)

Two free, no-key providers were added to the fixed workflow's discovery service
(`harness/plugins/autosci/services/production_research.py`) and the single-shot
fallback was replaced by a bounded chain.

**What was actually wrong.** The earlier note that the pipeline "unions across
providers" was incorrect. It was a cascade with a threshold: OpenAlex ran only
if fewer than 3 candidates were held, Crossref only if still fewer than 3. So
one broadly-indexed, weakly-ranked provider returning three rows terminated
discovery, and the relevance gate downstream had nothing on topic left to admit.

**Changes.**

- `_arxiv()` - arXiv Atom API, no key. Covers computing, physics, mathematics.
  Its `<id>` is stated over http and is canonicalized to https, because the
  downstream URL policy would otherwise reject discovery's own result.
- `_europe_pmc()` - Europe PMC REST, no key. Covers the life sciences, which
  arXiv does not index. This is what makes a biomedical request retrievable.
- `_open_json` was split into `_open_body` + parse so a non-JSON provider shares
  the same retry, size cap, and per-attempt evidence archiving.
- The chain is `semantic_scholar -> arxiv -> europe_pmc -> openalex -> crossref`
  and continues until the candidate budget is full **and** at least
  `MIN_DISCOVERY_PROVIDERS` (2) independent providers have contributed.
- `_select_candidates()` takes seeded sources first, then round-robins across
  providers, so a 20-row response cannot crowd out a 2-row on-topic one.
- Dedup now also collapses identical normalized titles, not just identifiers: a
  preprint and its published record carry different DOIs and were each spending
  a slot.
- `provider_usage[].status` distinguishes `completed` / `empty` / `failed`.
  Previously any provider whose rows lost the cut was reported as `failed`,
  which was untrue and became far more likely once the chain widened.
- `_is_stopword_compound()` in `base.py` drops hyphenated compounds built
  entirely from deliverable words. `evidence-linked` was one token and was
  spending one of the five query slots.

**Measured, live, after the change.**

| request | result |
|---|---|
| `mamba architecture transformer jepa` | 5 arXiv hits all on topic (Mamba limitations, JEPA for 6G, Bi-Mamba+, UWM-JEPA, Sub-JEPA) interleaved with 4 OpenAlex |
| `crispr off-target effects high-content screening` | 9/9 on topic, split arXiv + Europe PMC |

Before the change the CRISPR query returned image profiling and bibliometrics,
and the Mamba query was topped by video diffusion and remote sensing.

Semantic Scholar still returns HTTP 429 without an API key and contributes
nothing. arXiv rate-limits hard (`Rate exceeded.`, no `Retry-After`, needs ~30s)
which exceeds the policy's 12-second total wait, so it can fail on a busy host;
the chain absorbs that.

## OPEN: Serper and Tavily need a decision, not just a key

There is already a working Serper client with a usage ledger at
`harness/lib/research/cli.py:482`, and an `arxiv_search` at `:687` - but they
belong to the **DeepResearch** product line, not the AutoSci fixed workflow.
They return hits; they do not archive per-attempt request/response evidence,
which is what the fixed workflow's proof gate consumes. That is why `_arxiv`
was written inside the archiving service rather than reusing `arxiv_search`.

The blocker for the fixed workflow is not the key, it is the policy. The
retrieval authorization is `public_bibliographic_no_key_v1` and declares
`credential_mode: "public_no_key"` and `secret_refs: []`, and the dispatcher
validates those exact values (`graph_node_dispatcher.py`). A keyed provider
needs a second policy (`credential_mode: "api_key"` plus `secret_refs`) and a
distinct acquisition channel, because a web result is not a scholarly record and
the relevance/provenance gates should not treat them alike.

Free-tier terms, checked 2026-08-18:

- **Serper**: 2,500 credits **one-time**, not monthly. Note
  `SERPER_DEFAULT_MONTHLY_LIMIT = 2500` in `cli.py:58` assumes a monthly reset,
  which does not match how the free grant works.
- **Tavily**: 1,000 credits per month, no card.

Recommendation: the free no-key providers already closed the measured gap on the
user's own example, so a key is not needed to make retrieval work. Add Serper or
Tavily only when the requirement is genuinely web coverage (industry reports,
docs, blog posts) rather than literature, and do it as a separate keyed policy.

## Request routing is now wired in (the third contrivance)

`_classify_intake_request()` in `harness/lib/symphony/status-server.py` replaces
the blanket `SOLAR_INTAKE_WORKFLOW_ID` pin. For a prompt with no explicit
workflow_id, when the dashboard profile has pinned the research contract:

- `simple` drops the pin and every `SOLAR_RESEARCH_*` profile variable, so the
  request takes the generic planner path.
- `research_report` keeps the contract and narrows the execution profile to
  `part_a_only`.
- `research_poc` keeps the contract at `part_a_plus_poc`.

An explicit `workflow_id` from the caller always wins, and an environment that
was never pinned is left untouched. The verdict is returned to the caller as
`request_routing` on the intake response. Tests:
`tests/harness/test_status_server_intake_routing.py`.

`_RESEARCH_MARKERS` was widened with vocabulary an engineering request would not
use (`meta-analysis`, `related work`, `preprint`, `arxiv`, `bibliograph*`,
`empirical study/comparison`, `evidence-linked`). Bare `investigate`, `compare`
and `evidence` were deliberately NOT added: a false positive sends a debugging
task through the fifteen-node contract, a false negative only costs a rephrase.

Residual gap, unfixed and expected: a research request phrased with no scholarly
vocabulary at all still routes `simple`, e.g. "investigate whether diffusion
models beat GANs and run an experiment". This is the case the semantic
understanding layer the user asked for later would cover. Regex routing cannot.

## Remaining retrieval ideas

1. **Query fan-out.** Single-query lexical retrieval is weak for comparative
   questions: `jepa` legitimately narrowed Mamba results from 11,673 to 118
   because few papers mention both. Issue several sub-queries and union.
2. Semantic Scholar needs an API key or it will keep 429ing.
3. `harness/lib/research/policies/source_authority.json` scores `arxiv.org` and
   `doi.org` at 0.90 but does not know `europepmc.org`. The fixed workflow does
   not read that policy, so this is only a follow-up for DeepResearch.

## A convention this session broke, and fixed

The Part B capsules were originally added as `cap.autosci-*`. That violates the
phase-17 naming cleanup, which requires research-named, vendor-neutral
capability ids and is enforced by
`tests/harness/evaluators/scientific/test_phase17_naming_cleanup.py`.
`docs/integrations/autosci/phase2-capsule-report.md:55` states the rule outright:
"No capsule is named `cap.autosci-*`".

They are renamed to `cap.research-external-*` (external science-agent runtime
evidence), which is what they actually are. They stay separate from the
`cap.research-poc-*` family because the contracts genuinely differ: the poc
family selects against Part A's accepted evidence, the external family verifies
runtime evidence an outside agent produced.

Renamed: the seven capsule files and their ids, the capsule registry, the v1.4
workflow bindings, `test_autosci_capsule_layer.py` and
`test_fixed_research_workflow.py`.

## Pre-existing failures on this machine: 33 of them

A broad gate over `tests/harness/workflow_contract`, `tests/plugins/autosci`,
`tests/repairs/live_research_provider` and `tests/harness/evaluators/scientific`
reports 34 failures. Every one was checked against the session base commit
`7302ab2ba` in a separate worktree.

| suite | count | status |
|---|---|---|
| `test_autosci_skill_shim.py` | 22 | identical failure set at base, diffed by name |
| `test_scientific_lifecycle_runtime_smoke.py` | 5 | all 5 reproduce at base |
| `test_report_gate.py`, `test_lifecycle_gate.py` | 4 | reproduce at base |
| `test_phase19_parity_bridge.py` | 2 | both reproduce at base |
| `test_phase17_naming_cleanup.py` | 1 | THIS ONE WAS OURS, now fixed |

Most trace to local state this checkout does not have and that is gitignored:
`harness/artifacts/autosci/workspace/wiki` (read by the ingest boundary at
`autosci_bridge.py:7208`) and `artifacts/scientific_report.txt` (read by the
report gate). The gates fail closed, which is correct behaviour against missing
evidence, so these look environment-dependent rather than broken. Nobody had run
these suites during the session, which is why they surfaced only at the end.

Do not treat the 33 as a licence to ignore the suites. Confirm the environment
hypothesis before changing any gate.

## Part B is unblocked: AutoSci is on this machine

`SOLAR_AUTOSCI_HOME` was never set, which is why `autosci_skill_executor.py`
had no target and Part B has never executed end to end. The checkout exists:

    /home/ssubr/openjiuwen-solar-integration/autosci-spike/upstream-autosci-codex
      .agents/skills/  ->  ideate, exp-design, exp-run, exp-eval, paper-draft,
                           and 24 more (29 total), at upstream e40a156

Set `SOLAR_AUTOSCI_HOME` to that path to run B1-B7 for real. Expect it to
consume Codex quota; `gpt-5.5` was exhausted, `gpt-5.3-codex-spark` works.

### BUT the executor cannot chain the stages yet

`autosci_skill_executor.py` builds every prompt as `f"{skill} {request}"`, where
`request` is the original free-text research request. That is only correct for
the first stage. Read the skill signatures:

| stage | skill | argument it actually takes |
|---|---|---|
| idea_evaluation | `$ideate` | `[topic] [--max-ideas N] [--auto]` |
| experiment_design | `$exp-design` | `<idea-slug>` |
| experiment_run | `$exp-run` | `<experiment-slug> [--review] [--collect] [--full] [--env]` |
| experiment_monitor | `$exp-status` | `[--pipeline <slug>] [--auto-advance]` |
| claim_verification | `$exp-eval` | `<experiment-slug> [--auto]` |
| report_delivery | `$paper-draft` | `<paper-plan-path>` |

So `$exp-design "give me a deep research report on ..."` never resolves to an
idea, and Part B fails at B2. Three things are needed before an end-to-end run:

1. **Thread identifiers between stages.** `$ideate` writes `wiki/ideas/{slug}.md`;
   `$exp-design` writes `wiki/experiments/{exp-slug}.md` with `linked_idea` set
   and appends to the idea's `linked_experiments`. The executor has to read the
   slug the previous stage produced (from the wiki, not by scraping stdout) and
   pass it forward.
2. **Pass the non-interactive flags.** `$ideate` and `$exp-eval` take `--auto`,
   `$exp-status` takes `--auto-advance`. The executor passes none of them, so a
   skill can pause for confirmation inside a non-interactive `codex exec`. The
   user was explicit: "there is no approval handling needed it should be end to
   end".
3. **Decide what happens on an empty stage.** If `$ideate` writes zero surviving
   ideas, B2 has no slug. Fail closed with a real non-zero exit; never
   synthesise a slug.

`wiki/ideas/` and `wiki/experiments/` are both empty in the checkout, so the
first `$ideate` run has to populate them before anything downstream can work.

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
a check, **never green** - the user asked for green, which conflicts with the
token contract and needs `DESIGN.md` amended first. Confirmed real UI bugs, none
fixed: sprint title truncated in the **backend** (`workflow_intake.py:227`,
`request[:80]`, mid-word); the agent roster shows "Planner NOW" while
`target_role` is `builder_main` (likely derived from `phase: planning_complete`);
pending and done render identically.

Part B UI proposal (not implemented):
`docs/internal/agent_queue/PART_B_UI_PROPOSAL.md` and `.html`. Recommends a
stage roster plus an **evidence-lineage** panel over the 8 integrity checks -
real provenance chains with real hashes, not a drawn pipeline. AutoSci's own
graph is a **knowledge graph** (papers/concepts/methods), not an execution view,
and loads Cytoscape from a CDN, which would break the network-disabled container
UAT.

## Evidence roots

`artifacts/dashboard-full-uat-{,r2..r14}-20260818` (r13/r14 reach A1-A6),
`artifacts/adversarial-prompt-a-20260818` (the contrivance, before),
`artifacts/adversarial-prompt-a-final-20260818` (after: 0 accepted, 8 rejected).
Screenshots under each `screenshots/`.
