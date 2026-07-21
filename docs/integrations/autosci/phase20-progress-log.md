# AutoSci Solar Phase 20 Progress Log

Phase20 starts after phase19 full-parity runtime proof closure. Use this file
for AutoSci parity continuation work going forward, including first-class
native execution parity, non-runtime local parity, generated artifact UX parity,
and subsequent command-level fixes.

## Agent B First-Class Native Execution Parity Tightening

Logged: 2026-07-03 EDT

Intent: tighten slash-command paths where OpenSolar compatibility output could be
mistaken for native AutoSci execution. This keeps Solar approval/evidence gates,
but prevents scaffold or bridge-only output from presenting as native command
completion.

| Item | Status | Evidence |
|---|---|---|
| `$poster` native precondition | ok | `$poster report-001` no longer emits scaffold `poster_html`; the regular route records `paper_source_missing` until a paper directory containing `main.tex` is supplied. |
| Poster compatibility scaffold | ok | `tools/poster.py build --out` now requires explicit `--compat-scaffold`; the native template/outline/output path remains unchanged. |
| Poster approved renderer | ok | Approved renderer execution now requires actual poster HTML; no-paper route writes inconclusive runtime evidence instead of launching the renderer. |
| `$daily-arxiv` local native path | ok | Shim accepts `--feed`, `--decisions`, and `--no-external`; bridge runs native `tools/daily_arxiv.py prepare/finalize` against local inputs and attaches context/digest artifacts. |
| Side effects | ok | Daily local path defaults to `--no-external`; network, email, scheduler, and auto-ingest side effects remain gated. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| `$poster` could silently produce scaffold HTML without native paper source. | fixed | Scaffold output is only allowed in explicit smoke/compat mode; regular command records the missing native precondition. |
| `tools/poster.py build --out` looked like a native poster build. | fixed | `--compat-scaffold` is now required for scaffold output. |
| Approved poster renderer could be invoked before native poster HTML existed. | fixed | Renderer is blocked with `poster_html_exists=error` runtime evidence if HTML is missing. |
| `$daily-arxiv` with local feed/decisions did not execute native `daily_arxiv.py`. | fixed | Local feed path now invokes native prepare/finalize and maps candidates to Solar evidence schema. |
| Native daily candidates lacked Solar `literature_discovery.v1` required fields. | fixed | Added normalization through `_candidate_from_runtime`. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py tools/poster.py` | ok |
| `pytest -q harness/plugins/autosci/tests/test_root_tool_abi.py harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'poster or daily_arxiv or research_start_from'` | ok: 14 passed, 148 deselected |

## Agent B Remaining First-Class Native Execution Parity

Logged: 2026-07-03 EDT

Intent: continue closing first-class slash-command parity gaps where an
OpenSolar route could produce bridge-native output without invoking the native
AutoSci tool that owns the command semantics.

| Item | Status | Evidence |
|---|---|---|
| `$discover` default path | ok | Non-runtime `$discover` now invokes native `tools/discover.py` for `from-wiki`, `from-anchors`, `from-topic`, and `from-venue` modes, then adapts the native shortlist to Solar `literature_discovery.v1`. |
| `$discover` no-network path | ok | `AUTOSCI_DISABLE_NETWORK_FETCH=1` now reaches native `tools/discover.py --no-network-fetch`; native stdout/payload artifacts are archived. |
| `$init` local plan path | ok | Non-runtime `$init` now invokes native `tools/init_discovery.py prepare` and `tools/init_discovery.py plan --no-network-fetch`; prepare manifest and plan JSON are archived. |
| `$check` review | ok | No route change needed: `/check` already invokes native `tools/lint.py` and stores the lint report. |
| `$reset` review | ok | No route change needed: `/reset` already invokes native `tools/reset_wiki.py` for dry-run and approved execution. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| `$discover` used the OpenSolar backend directly instead of the native discovery CLI. | fixed | Bridge now dispatches to `tools/discover.py`; explicit fixture fallback remains limited to fixture/smoke mode. |
| `$init` produced a plan-only bridge result without native init planner artifacts. | fixed | Bridge now runs native `init_discovery.py prepare` and no-network `plan`, then records native artifacts. |
| Network/provider behavior could be conflated with local native parity. | guarded | `$init` uses native no-network local planning by default; provider fetch and bulk ingest still require approved runtime/source evidence. |
| `$check` and `$reset` looked suspicious during audit because their bridge actions contain Solar gates. | reviewed | Confirmed they already call `tools/lint.py` and `tools/reset_wiki.py`; no additional first-class fix was needed. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py` | ok |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_discover_from_wiki_limit harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ask_check_and_init_diagnostics` | ok: 2 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_discover_runtime_requires_provider_boundary harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_discover_runtime_attaches_provider_runtime_proof harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_discover_wiki_runtime_proof_is_not_live_provider harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_init_uses_verified_runtime_source_manifest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_init_write_fans_runtime_sources_into_wiki` | ok: 5 passed |
| `pytest -q harness/plugins/autosci/tests/test_source_cli_tools.py harness/plugins/autosci/tests/test_root_tool_abi.py::test_side_effect_root_tools_emit_truthful_non_mutating_evidence` | ok: 8 passed |
| `pytest -q harness/plugins/autosci/tests/test_literature_discover.py` | ok: 2 passed |

## Agent B First-Class Native Execution Parity Audit: Ingest

Logged: 2026-07-03 EDT

Intent: audit whether any first-class command execution path still bypassed a
native AutoSci root tool after the `$visualize`, `$poster`, `$daily-arxiv`,
`$init`, and `$discover` native-path fixes.

| Item | Status | Evidence |
|---|---|---|
| `$ingest` native source prepare | ok | `$ingest` now invokes `tools/prepare_paper_source.py` before bridge parsing; native payload/stdout artifacts are archived and preparation records `native_prepare_paper_source`. |
| Parser compatibility | ok | Existing `read_paper_source` parser remains responsible for the Solar `research_paper.v1` body/sections so parse quality and ABI output do not regress. |
| Remaining first-class audit | ok | Explicit root-tool commands now have native invocation or remain approval-gated remote/provider paths: visualize, poster, daily-arxiv, init, discover, ingest, check, reset, and remote execution. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| `$ingest` source normalization used only the OpenSolar backend. | fixed | Route now runs native `prepare_paper_source.py` and archives native payload/stdout. |
| Replacing the parser wholesale could alter `research_paper.v1` ABI and parse quality. | guarded | Native CLI is the source-normalization authority; existing parser still emits paper body/sections. |
| `research_wiki.py` calls appear in many native skills. | deferred | Treat as command-internal wiki mutation/UX parity unless the slash route has an explicit native root tool that is bypassed. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py` | ok |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_maps_positional_ingest_source test_autosci_skill_shim.py::test_autosci_skill_shim_ingests_pdf_with_extracted_text_and_no_fixture_leakage` | ok: 2 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k ingest` | ok: 8 passed, 146 deselected |
| `pytest -q harness/plugins/autosci/tests/test_source_cli_tools.py harness/plugins/autosci/tests/test_paper_prepare.py` | ok: 11 passed |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase20-progress-log.md` | ok |

## Agent B Problem 3 Side-Effect Parity: Visualize Serve Policy Gate

Logged: 2026-07-03 EDT

Intent: begin solving the side-effect parity class from the updated prompt:
allow the same bounded side effects in AutoSci parity modes instead of only
emitting health/proposal evidence. This slice covers `$visualize --serve`.

| Item | Status | Evidence |
|---|---|---|
| Central gate policy | ok | Added `harness/plugins/autosci/policy/gate_policy.py` with `strict_hitl`, `safe`, `parity_demo`, `unsafe_native`, and `autosci_native` modes. |
| Strict default | ok | Default mode remains `strict_hitl`; existing `$visualize --serve` without approval still does not execute the server path. |
| Visualize side effect | ok | In `parity_demo`, `$visualize --serve` auto-generates a synthetic policy approval and runs native `tools/serve.py --probe-server --port 0`. |
| Native server lifecycle | ok | `tools/serve.py --probe-server` binds a loopback HTTP server, probes `/api/health`, records `server_started=true`, and shuts down. |
| Evidence attachment | ok | Action evidence includes `outputs.policy_decision`, `provenance.gate_policy`, `gate_policy_decision_json`, and synthetic approval contract evidence. |
| Scope | partial | Only `$visualize --serve` is connected to the new policy gate in this slice; compile/poster/experiment/daily/reset remain follow-up action integrations. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The prompt's full policy request spans many side-effect routes. | scoped | Implemented the shared policy layer plus one representative route first; did not broad-edit all side-effect actions in one pass. |
| `serve.py --health-check` did not actually bind a server. | fixed | Added bounded `--probe-server`, which starts the HTTP server, probes it, then shuts it down. |
| System `python3` lacked PyYAML for native visualize/serve dependencies in a manual demo. | documented | Use the repo `.venv/bin/python` or harness Python for native tools requiring project dependencies. |
| Sandbox loopback restrictions can block the server probe. | documented | Focused pytest passed; manual demo needed an elevated loopback run to prove `server_started=true`. |
| Synthetic policy approval could be mistaken for human approval. | guarded | Synthetic refs use `policy:auto:<mode>:<action>:<timestamp>` and evidence warnings state no human approval was requested. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/policy/gate_policy.py tools/serve.py` | ok |
| `pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py` | ok: 9 passed |
| `pytest -q harness/plugins/autosci/tests/test_root_tool_abi.py::test_side_effect_root_tools_emit_truthful_non_mutating_evidence` | ok: 1 passed |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_visualize_serve_flag_without_server_execution test_autosci_skill_shim.py::test_autosci_skill_shim_visualize_parity_demo_auto_runs_server_probe test_autosci_skill_shim.py::test_autosci_skill_shim_visualize_serve_emits_approved_runtime_proofs` | ok: 3 passed |
| `pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py harness/plugins/autosci/tests/test_root_tool_abi.py::test_side_effect_root_tools_emit_truthful_non_mutating_evidence ...visualize serve tests` | ok: 13 passed |
| `env HARNESS_DIR=/private/tmp/opensolar_autosci_policy_smoke SOLAR_AUTOSCI_OUTPUT_HARNESS=/private/tmp/opensolar_autosci_policy_smoke python3 harness/plugins/autosci/bin/autosci_bridge.py smoke` | ok |
| `env HARNESS_DIR=/private/tmp/opensolar_autosci_policy_smoke SOLAR_AUTOSCI_OUTPUT_HARNESS=/private/tmp/opensolar_autosci_policy_smoke python3 harness/plugins/autosci/bin/autosci_bridge.py validate --result /private/tmp/opensolar_autosci_policy_smoke/artifacts/autosci/smoke/result.json` | ok |
| elevated demo: `.venv/bin/python harness/plugins/autosci/bin/autosci_skill_shim.py skill visualize "autosci graph" --serve --gate-mode parity_demo --run-id policy-demo-visualize-serve` | ok: `passed_count=1`; `visualize_web_health.json` has `server_started=true`, `server_stopped=true`; approval contract has `execution_verified=true`. |
| `git diff --check -- <changed AutoSci policy/visualize files>` | ok |

## Agent B Problem 3 Side-Effect Parity: Compile, Poster, And Local Experiment Run

Logged: 2026-07-03 EDT

Intent: continue solving the side-effect parity class after `$visualize --serve`
by letting policy-approved parity modes execute bounded local side effects for
publication compile, poster render/export, and local experiment run paths while
preserving runtime semantic verification.

| Item | Status | Evidence |
|---|---|---|
| Shared policy helper | ok | Added `_policy_prepare_auto_contract()` and `autosci_gate_policy_allowlist.v1` sidecars so side-effect actions can attach gate decisions and synthetic allowlist evidence consistently. |
| `$paper-compile` | ok | In `parity_demo`, discovered supported TeX executors are converted into a synthetic policy allowlist; actual completion still requires executor exit success and structurally valid PDF proof. |
| `$poster` | ok | In `parity_demo`, policy approval can trigger the existing approved renderer path, but only when concrete `poster_render_command` or `poster_renderer` allowlist evidence is supplied. |
| `$exp-run --env local` | ok | In `parity_demo`, policy approval can trigger a supplied concrete local command allowlist, then the existing runtime semantic and wiki mutation checks decide completion. |
| Evidence attachment | ok | Compile/poster/experiment evidence now includes `outputs.policy_decision`, `provenance.gate_policy`, `gate_policy_decision_json`, and relevant policy/allowlist sidecars. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The initial `$exp-run` policy allowlist treated exp-design's generic handoff command (`autosci_bridge.py run --action run_experiment`) as executable allowlist evidence. | fixed | `run_experiment` policy sidecars now record `declared_plan_commands` for audit only; executable selection still requires concrete command allowlist evidence or supplied verified runtime evidence. |
| Synthetic policy approval can look similar to user approval in downstream contracts. | guarded | Synthetic refs keep the `policy:auto:<mode>:<action>:<timestamp>` prefix and sidecars state that they are not human approval artifacts. |
| `$poster` cannot safely infer a browser renderer from policy mode alone. | guarded | The policy gate can approve execution, but the renderer still must come from concrete allowlist evidence. Missing renderer remains inconclusive. |
| TeX availability differs by machine. | guarded | `$paper-compile` auto-execution only allowlists supported executors discovered on `PATH`; missing executor or invalid PDF output remains inconclusive. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/policy/gate_policy.py tools/serve.py` | ok |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_parity_demo_auto_executes_local_command test_autosci_skill_shim.py::test_autosci_skill_shim_paper_compile_parity_demo_auto_executes_executor test_autosci_skill_shim.py::test_autosci_skill_shim_poster_parity_demo_auto_executes_renderer` | ok: 3 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'paper_compile or poster or exp_run'` | ok: 28 passed, 130 deselected |
| `pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py` | ok: 9 passed |
| `git diff --check -- <changed AutoSci problem3 files>` | ok |

## Agent B Problem 3 Side-Effect Parity: Init Source Fan-In

Logged: 2026-07-03 EDT

Intent: continue solving the side-effect parity class for remaining commands by
connecting `$init --write` to the policy-approved local wiki fan-in path without
auto-running provider/network fetch, email, remote execution, or bulk ingest.

| Item | Status | Evidence |
|---|---|---|
| `$init --write` policy approval | ok | In `parity_demo`, `$init --write` can generate synthetic policy approval/allowlist evidence for the local `wiki_fan_in` side effect. |
| Runtime source boundary | ok | Fan-in still requires supplied runtime source candidates with completed provider-source boundary evidence; policy mode does not fabricate source/provider proof. |
| Two-stage contract | ok | Before fan-in, the contract can be ready with runtime candidates but missing after artifacts; after real page/log/graph/rebuild files are written, those files are appended as after artifacts and the contract is refreshed. |
| Final readiness | ok | `init_sources_final_fan_in_boundary` reaches `init_sources_final_fan_in_ready` only after provider candidates, semantic runtime verification, wiki mutation, log, graph edge, index, and context brief evidence are present. |
| Scope preservation | ok | `$daily-arxiv` still emits ingest handoff for daily candidates and does not directly write paper pages or auto-send email/auto-ingest. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The original generic approval semantic check required after artifacts before fan-in, but fan-in itself produces the after artifacts. | fixed | `$init` now uses a two-stage source-runtime check for policy fan-in, then re-runs semantic verification after real fan-in files exist. |
| Runtime candidates could be replaced by the local init plan when semantic verification was incomplete only because after artifacts were missing. | fixed | If runtime candidate records are loaded, `$init` keeps them and does not fall back to the local plan candidate list. |
| Synthetic policy approval could be mistaken for live provider/network execution. | guarded | Policy allowlist text and handoff docs state that `$init` policy approval covers local wiki fan-in only. Provider/network, email, remote, and bulk ingest remain gated. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py` | ok |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_init_parity_demo_auto_fans_runtime_sources_into_wiki` | ok: 1 passed |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_init_uses_verified_runtime_source_manifest test_autosci_skill_shim.py::test_autosci_skill_shim_init_write_fans_runtime_sources_into_wiki test_autosci_skill_shim.py::test_autosci_skill_shim_init_parity_demo_auto_fans_runtime_sources_into_wiki` | ok: 3 passed |
| `pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py` | ok: 9 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'init or daily_arxiv or discover or source_fan_in or ingest'` | ok: 22 passed, 137 deselected |
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/policy/gate_policy.py` | ok |

## Agent B Problem 3 Side-Effect Parity: High-Risk Reset Execution

Logged: 2026-07-03 EDT

Intent: continue solving the side-effect parity class for commands with high-risk
side effects. This slice covers `$reset --scope ...` by connecting it to the
same policy gate while preserving default HITL blocking.

| Item | Status | Evidence |
|---|---|---|
| `$reset` policy approval | ok | High-risk policy modes can synthesize approval/allowlist evidence for native reset execution; default `strict_hitl` and `safe` stay blocked. |
| Native executor reuse | ok | Auto execution reuses `tools/reset_wiki.py --execute-approved`; no separate reset/delete implementation was introduced. |
| Before proof | ok | Policy reset execution writes `reset_before_snapshot.json` before mutation and appends it to the approval contract. |
| Runtime/after proof | ok | Completed reset appends `reset_wiki_runtime_evidence.json` and `reset_after_snapshot.json`, then emits approval, side-effect, and wiki-mutation proof manifests. |
| Scoped safety | ok | Regression test executes only against a pytest temporary wiki root and uses `--scope wiki`, leaving raw source files intact. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| High-risk reset could be over-enabled if policy mode alone bypassed audit evidence. | guarded | Execution still flows through native `reset_wiki.py`, and final contract verification depends on concrete runtime/after artifacts. |
| Destructive reset needs a pre-mutation state record. | fixed | Added a real before snapshot artifact instead of relying only on policy sidecars as preflight evidence. |
| Synthetic policy approval can be mistaken for human approval. | guarded | Evidence includes `outputs.policy_decision`; synthetic refs keep the `policy:auto:<mode>:reset_plan:<timestamp>` prefix. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py` | ok |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_reset_executes_approved_local_scope_with_runtime_proofs test_autosci_skill_shim.py::test_autosci_skill_shim_reset_autosci_native_auto_executes_scoped_reset` | ok: 2 passed |

## Agent B Problem 3 Side-Effect Parity: High-Risk Setup Config Write

Logged: 2026-07-03 EDT

Intent: continue solving high-risk side-effect parity by giving `$setup` a
controlled credential/config mutation path while preserving default status-only
behavior.

| Item | Status | Evidence |
|---|---|---|
| `$setup` explicit target | ok | Added `--setup-dotenv-path`; local config writes are not attempted unless the target `.env` path is explicit. |
| Policy approval | ok | High-risk policy modes can synthesize approval/allowlist evidence for setup credential/config mutation; default `strict_hitl` and `safe` stay blocked. |
| Approved after artifact | ok | Setup writes only key/value rows from the supplied after-artifact and only for known AutoSci setup keys. |
| Secret hygiene | ok | Evidence records key names, redacted before/after snapshots, runtime proof, and hashes/paths only; secret values are not serialized. |
| Gate truthfulness | ok | `workflow_evolution_gate.py` accepts applied setup only when approval contract, setup runtime evidence, after snapshot, approval proof, and side-effect proof are present. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The existing workflow-evolution gate rejected all protected-core applied changes except refine apply. | fixed | Added a narrow setup-control application exception requiring verified setup runtime/proof artifacts. |
| Existing external setup runtime evidence should not be treated as a local `.env` write request. | fixed | Local setup writes now require explicit `setup_dotenv_path`; external runtime evidence without a target path remains proposal/gated shaped. |
| Secret values can leak through evidence if serialized carelessly. | guarded | Regression test writes a fake secret to temp `.env` and asserts the secret is absent from setup evidence, contract, runtime evidence, and setup status. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/evaluators/scientific/workflow_evolution_gate.py` | ok |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_keeps_setup_gated test_autosci_skill_shim.py::test_autosci_skill_shim_setup_autosci_native_writes_explicit_dotenv_without_secret_leakage` | ok: 2 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'reset or setup'` | ok: 9 passed, 152 deselected |
| `pytest -q harness/tests/evaluators/scientific/test_workflow_evolution_gate.py` | ok: 2 passed |
| `pytest -q harness/tests/evaluators/scientific/test_workflow_evolution_gate.py harness/plugins/autosci/tests/test_gate_policy_modes.py` | ok: 11 passed |
| `pytest -q test_autosci_skill_shim.py::test_autosci_skill_shim_refine_applies_approved_after_artifact` | ok: 1 passed |
| `git diff --check -- <changed AutoSci setup/reset problem3 files>` | ok |

## Agent B Problem 3 Side-Effect Parity: Remaining Commands

Logged: 2026-07-03 EDT

Intent: finish the remaining problem-3 class for commands whose native AutoSci
behavior has real side effects. The goal was not to make every command succeed
without prerequisites; it was to let approved local/writeback/execution paths
perform the same kind of side effects and leave typed runtime proof, while
keeping provider, remote, and workflow mutation boundaries truthful.

| Item | Status | Evidence |
|---|---|---|
| Shared policy contract helpers | ok | Added bridge helpers for policy-auto approval contracts, existing-contract updates, local mutation runtime evidence, and policy decision attachment. |
| Local wiki/artifact writebacks | ok | `$prefill`, `$edit`, `$ask --crystallize`, and `$refine` can now apply approved local after artifacts and register concrete mutation runtime proof in the approval contract. |
| Claim and pilot verdict writeback | ok | `$exp-eval` and `$exp-pilot-eval` can now use policy-auto approval to write local wiki verdict state, log/edge/view updates, approval proof, side-effect proof, and mutation proof manifests. |
| Pilot runtime execution | ok | `$exp-pilot-run` can now execute an allowlisted local pilot command through the existing approved executor path and emit runtime/result/stdout/stderr/deploy/run-report evidence without writing wiki verdict state. |
| Status and collect side effects | ok | `$exp-status` and `$exp-run --collect` have high-risk policy paths for command/status/collect side effects, but remote execution requires policy allowlist plus `SOLAR_AUTOSCI_ALLOW_REMOTE=1`. |
| Research workflow evolution | guarded | Fixed a regression in the research workflow-evolution raw payload, but did not auto-apply workflow patch candidates. Workflow patch application remains proposed-only until a verified explicit patch path exists. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| Some remaining commands could be "proved" by sidecar evidence while still never performing the local mutation. | fixed | Local writeback commands now add concrete after artifacts and mutation runtime evidence to the approval contract before emitting approved mutation proof. |
| Claim/pilot verdict routes needed side effects, but pass/fail judgment belongs to eval routes, not run routes. | guarded | `$exp-pilot-run` produces runtime evidence only; `$exp-pilot-eval` owns verdict and wiki writeback. |
| Remote/status commands are high-risk and can be confused with local proof. | guarded | Remote/status/collect execution now requires both gate policy approval and `SOLAR_AUTOSCI_ALLOW_REMOTE=1`; otherwise the bridge reports gated/blocked state instead of faking provider proof. |
| Workflow evolution mutation would touch shared route/gate/workflow behavior. | guarded | The command still emits proposal/evidence only. No silent workflow, route, operator, or gate mutation was introduced in this pass. |
| Research workflow-evolution raw payload referenced an undefined setup execution variable. | fixed | The payload now remains proposed-only and no longer depends on an undefined local variable. |
| Codex sandbox denies localhost socket binding for provider/server probe tests. | environment | The full shim suite was split: non-socket tests passed in sandbox, then the three socket-bound tests passed with elevated permissions. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `pytest -q test_autosci_skill_shim.py::<prefill/edit/ask/refine problem3 tests>` | ok: 4 passed |
| `pytest -q test_autosci_skill_shim.py::<pilot-eval/exp-eval/pilot-run/status/collect problem3 tests>` | ok: 5 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'exp_pilot_run or exp_status or exp_collect or pilot_eval or exp_eval'` | ok: 25 passed, 145 deselected |
| `env PYTHONPATH=harness .venv/bin/python -m pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py` | ok: 9 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'not visualize_parity_demo_auto_runs_server_probe and not novelty_http_provider_marks_external_runtime and not review_invokes_openai_compatible_provider'` | ok: 167 passed, 3 deselected |
| elevated rerun of socket-bound shim tests: visualize server probe, novelty HTTP provider, Review LLM OpenAI-compatible provider | ok: 3 passed |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

## Agent B Problem 3 Side-Effect Access Requests

Logged: 2026-07-06 EDT

Intent: stop four native-parity commands from silently returning plan/dry-run
evidence when their native side effects are blocked by the active AutoSci gate
mode. The command should either use already-verified runtime evidence or emit a
typed access request that tells the caller what approval/opt-in is required.

| Item | Status | Evidence |
|---|---|---|
| Shared access request sidecar | ok | Added `autosci_side_effect_access_request.v1` generation with requested side effects, gate mode, blocking reasons, approval/runtime requirements, env opt-in hints, and `side_effect_access_request_json` artifacts. |
| `$daily-arxiv` | ok | Missing live feed access now emits `outputs.side_effect_access_required=true`; supplied verified runtime digest evidence can still complete without being downgraded. |
| `$research` | ok | Strict/safe blocked lifecycle side effects now appear in lifecycle runtime errors, human intervention points, pipeline status, and evidence outputs. |
| `$ideate` | ok | `generate_ideas` now uses approval-gated side-effect policy and emits access requests for model/source/wiki/pilot side-effect paths instead of a dry-run-only route. |
| `$exp-run` | ok | Approval-gated local/remote experiment execution now emits side-effect access requests when strict policy blocks command/wiki mutation execution. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| Solar Evidence ABI schemas do not allow a new top-level status value. | fixed | Evidence top-level status remains `inconclusive`; the blocking state is stored in `outputs.side_effect_access_status=blocked_side_effect_access_required` and in the sidecar. |
| Verified daily-arxiv runtime evidence was temporarily downgraded by strict policy. | fixed | Access requests are attached only when daily runtime evidence is not already semantically verified. |
| `ideate` route metadata still said `dry_run_only`. | fixed | Route config and skill metadata now say `approval_required`. |
| Local harness state files were dirty before this edit. | guarded | The change set avoids committing local process/watchdog state files and only targets AutoSci bridge/config/docs/tests. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py` | ok |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_strict_gate_emits_side_effect_access_requests_for_native_parity_commands` | ok: 1 passed |
| `pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py` | ok: 9 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions` | ok: 1 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_daily_arxiv_uses_verified_runtime_digest` | ok after verified-runtime guard fix |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_exp_run_native_options_without_fixture_fallback` | ok: 1 passed |

## Agent B Final Deliverable Projection And Continuation Contract

Logged: 2026-07-06 EDT

Intent: resolve two remaining parity concerns without requiring identical
intermediate artifact names or roots: final OmegaWiki-facing deliverables must
materialize into the wiki files that the SPA/serve path reads, and gate-blocked
native side effects must be resumable after explicit permission rather than
looking like terminal failures.

| Item | Status | Evidence |
|---|---|---|
| Graph deliverable projection | ok | `autosci_workspace_projector.py` now discovers `research_graph_update*.json` run artifacts and graph update artifacts referenced from action evidence, then appends enriched edges into `workspace/wiki/graph/edges.jsonl`. |
| Projection manifest | ok | When graph evidence exists, projector writes `wiki/graph/projection_manifest.json` with source evidence paths, projected/written edge counts, status, and limitations. |
| `$visualize` final graph parity | ok | Regression proves `$visualize` graph update evidence is projected into the final OmegaWiki graph file even when the intermediate file is `research_graph_update.visualize.json`. |
| Side-effect continuation | ok | `autosci_side_effect_access_request.v1` now embeds `autosci_side_effect_continuation.v1` with retry patch options for bounded policy mode, native mode, or strict HITL approval artifacts. |
| Gate behavior | ok | Blocked strict/safe runs still return `status=inconclusive`, but the evidence now marks the block as retriable and gives callers enough structure to ask for permission and retry the same envelope. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| Initial projector test assumed the source evidence would be the action evidence file. | fixed | The actual stronger path is direct discovery of `research_graph_update.visualize.json`; the test now asserts the final graph and projection manifest reference that source. |
| Final UI parity can be confused with intermediate schema parity. | guarded | The regression checks the final `workspace/wiki/graph/edges.jsonl` read surface, not merely the presence of a normalized graph evidence artifact. |
| Projection manifest could become unrelated command noise if written without graph evidence. | fixed | Manifest writing is conditional on discovered graph evidence; non-graph commands do not receive a fresh no-op graph projection manifest. |
| Permission continuation should not weaken default policy. | guarded | Default `strict_hitl` remains blocked for side effects; continuation only exposes explicit retry/access patch options. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_workspace_projector.py harness/plugins/autosci/bin/autosci_skill_shim.py` | ok |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_visualize_projects_action_graph_update_into_workspace_graph` | ok: 1 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_strict_gate_emits_side_effect_access_requests_for_native_parity_commands ...::test_autosci_skill_shim_visualize_projects_action_graph_update_into_workspace_graph ...::test_autosci_skill_shim_runs_remaining_gated_backend_actions` | ok: 3 passed |
| `pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py` | ok: 9 passed |

## Agent B All-Gate Authorization Continuation

Logged: 2026-07-06 EDT

Intent: bring every AutoSci-facing gated condition up to the "ask for
authorization, then continue/resume" standard without weakening real failure
gates. This covers bridge approval contracts, side-effect access requests,
route-level shim gates, the generic scientific workflow runner, and the legacy
research lifecycle smoke runner used by `$research --scheduler-run`.

| Item | Status | Evidence |
|---|---|---|
| Approval contracts | ok | `_approval_contract()` and `_refresh_approval_contract()` now embed `autosci_gate_authorization_request.v1` with a retriable `autosci_gate_continuation.v1` when approval/runtime artifacts are missing. |
| Route-level shim gates | ok | Approval-gated routes add `autosci_route_gate_authorization_request.v1` to skill-run outputs when the current run is schema-only/blocked or scheduler authorization is required; stdout summaries expose `authorization_required` / request counts only for those blocked handoffs. |
| Generic workflow blocked nodes | ok | `run_scientific_workflow.py` blocked nodes now include `scientific_workflow_gate_authorization_request.v1` plus continuation/resume args. |
| Blocked workflow process behavior | ok | Generic workflow authorization blocks now return process exit `0` by default while preserving `lifecycle_status=blocked`; `--legacy-blocked-exit-code` retains exit `3` for legacy callers. |
| Legacy scheduler blocked nodes | ok | `run_scientific_lifecycle_smoke.py` blocked external and human-gate nodes now include `scientific_workflow_gate_authorization_request.v1`; the shim invokes `--authorization-blocked-exit-zero` so `$research --scheduler-run` can surface blocked/resume state without returning a process failure. |
| Ideate smoke guard | ok | Fixture/smoke `generate_ideas` no longer emits side-effect access requests for hypothetical network/wiki/model side effects; explicit `--gate-mode strict_hitl` or real native/non-fixture ideate side-effect paths still emit access requests. |
| Failure boundary | guarded | Workflow-config drift, production dispatch boundary failure, and other real failed gates are not reclassified as authorization prompts. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| Lifecycle gate treated authorization-blocked runs with no node results as failed. | fixed | Authorization-blocked workflows are accepted as blocked/non-error when structured authorization requests exist. |
| "All gated conditions" could be interpreted as every historical `blocked` string in the repo. | scoped | This slice covers AutoSci public gate surfaces: bridge approval contracts, side-effect access, route-level shim gates, and generic scientific workflow gates. |
| Existing legacy smoke runner tests depend on blocked exit code `3`. | guarded | Direct legacy smoke runner behavior keeps exit `3`; shim-mediated runs opt into `--authorization-blocked-exit-zero` so the user-facing command can ask for authorization and continue later instead of surfacing a terminal process error. |
| `generate_ideas` strict policy initially blocked bounded fixture smoke. | fixed | Access requests are now attached only for explicit gate-mode runs or actual native/non-fixture ideate side-effect paths, preserving fixture scheduler smoke while keeping strict native ideate authorization prompts. |
| Route-level request was initially emitted for already-authorized passed actions. | fixed | Route-level authorization requests are now limited to schema-only/blocked action runs, no-action route evidence, or scheduler authorization requests; a passed parity-demo single-action run such as `$visualize --serve` does not ask again. |

### Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/tools/run_scientific_workflow.py harness/tests/evaluators/scientific/test_scientific_workflow_runner.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `pytest -q harness/tests/evaluators/scientific/test_scientific_workflow_runner.py` | ok: 2 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_visualize_serve_flag_without_server_execution ...::test_autosci_skill_shim_research_scheduler_blocked_gate_surfaces_authorization` | ok: 2 passed |
| `pytest -q harness/plugins/autosci/tests/test_gate_policy_modes.py harness/plugins/autosci/tests/test_approval_runtime_proof.py harness/tests/evaluators/scientific/test_scientific_workflow_runner.py` | ok: 14 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k "scheduler_blocked_gate_surfaces_authorization or accepts_visualize_serve_flag_without_server_execution or strict_gate_emits_side_effect_access_requests or research_scheduler_run_attaches_blocked_summary or research_scheduler_demo_uses_multi_node_preset"` | ok: 5 passed, 168 deselected |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_legacy_scheduler_run_attaches_blocked_summary ...::test_autosci_skill_shim_research_scheduler_run_records_human_gate ...::test_autosci_skill_shim_research_scheduler_blocked_gate_surfaces_authorization ...::test_autosci_strict_gate_emits_side_effect_access_requests_for_native_parity_commands` | ok: 4 passed |
| `pytest -q harness/tests/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py::test_scientific_lifecycle_smoke_blocks_configured_publication_tail_without_external_evidence ...::test_scientific_lifecycle_smoke_can_resume_external_blocked_nodes` | ok: 2 passed |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py -k "scheduler_blocked_gate_surfaces_authorization or accepts_visualize_serve_flag_without_server_execution or strict_gate_emits_side_effect_access_requests or research_legacy_scheduler_run_attaches_blocked_summary or research_scheduler_run_records_human_gate or research_scheduler_demo_uses_multi_node_preset"` | ok: 6 passed, 167 deselected |
| `pytest -q harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_parity_demo_auto_executes_local_command ...::test_autosci_skill_shim_visualize_parity_demo_auto_runs_server_probe ...::<scheduler authorization tests> ...::test_autosci_strict_gate_emits_side_effect_access_requests_for_native_parity_commands` | ok: 6 passed |
