# RC8 Codex Runtime Smoke Review

Date: 2026-07-01

This review package documents the RC8 runtime integration branch at runtime code
HEAD `cd528d0a`. The branch has a passing isolated Codex-only smoke E2E, plus
deterministic contract tests for the runtime fixes that led up to it.

## 1. Branch State

- Worktree: `/tmp/solar-rc8-runtime-integrated`
- Branch: `integration/rc8-runtime-mode-contract`
- Runtime code HEAD under review: `cd528d0a fix(runtime): keep graph open during active repair`
- Base branch: `upstream/openJiuwen-Solar`
- Base commit / merge-base: `cdc7e90334437796232e019a0dd689d33e53e7f2`
- Upstream comparison before this review document: `0 behind, 21 ahead`
- Pre-report `git status --short`: clean

Commit list from `upstream/openJiuwen-Solar..HEAD` before this docs-only review
commit:

```text
cd528d0a fix(runtime): keep graph open during active repair
92c5615d fix(runtime): emit patch proof from sidecar obligations
154a1d48 fix(runtime): register Codex model aliases
f26ce84b fix(runtime): preserve Codex auth in isolated live E2E
f01e81e2 test(runtime): add isolated Codex live E2E harness
b20e44d3 test(runtime): guard against installed harness contamination
7f9718b5 refactor(runtime): route graph dispatcher tools entrypoint to lib
5ba3bdee fix(runtime): bound evaluator capacity stalls and archive attempts
2db50662 fix(runtime): record route proof and recover stale operator status
7bd02a10 fix(runtime): treat repo workspace as dispatch-provisioned
30169c80 fix(runtime): sync closeout and command attribution
d2339f21 fix(runtime): synthesize node patch proof sidecars
d9dc0ab4 fix(runtime): admit implementation-capsule test authoring
63769097 fix(runtime): bind Codex operators to active harness
6578bb9d fix(runtime): suppress legacy planner pane when role pool is active
fcee2d97 fix(runtime): avoid readline locale crash in self-complete runner
d00903ab fix(runtime): fence repaired eval generations and duplicate node dispatch
c7783029 fix(runtime): surface node patch artifacts for eval proof
0c66ae6a fix(runtime): correlate eval closeout to active PM task
8ad0da81 fix(runtime): capture coordinator self-complete output safely
b787e9be fix(runtime): enforce Codex and Claude route selectors
```

## 2. Deterministic Test History

The deterministic checks below passed before the live E2E was accepted.

### Model Registry Contract

Codex/OpenAI aliases were registered in `harness/config/model-registry.json`.
The following model-registry CLI checks passed:

```bash
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json validate-main gpt-5.5
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json validate-main gpt-5.3-codex-spark
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json provider gpt-5.5
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json model-key gpt-5.3-codex-spark
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json validate-main opus
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json validate-main claude
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json validate-main anthropic-sonnet
python3 harness/lib/model_registry.py --registry harness/config/model-registry.json validate-main anthropic-opus
```

Current expected Claude alias failures were preserved for `sonnet`,
`sonnet-4`, and `opus-4`.

### Focused Runtime Tests

The following compile and pytest checks passed on the integration branch before
the final live E2E:

```bash
python3 -m py_compile \
  harness/lib/graph_scheduler.py \
  harness/lib/graph_node_dispatcher.py \
  harness/lib/route_proof.py

python3 -m pytest -q \
  tests/harness/graph/test_graph_status_sync.py \
  tests/harness/graph/test_graph_dispatch_submit.py \
  tests/harness/runtime/test_graph_node_dispatcher_patch_proof.py \
  tests/harness/runtime/test_route_proof.py \
  tests/harness/test_pm_dispatch.py \
  tests/harness/runtime/test_codex_operator_contract.py
```

Result: `75 passed, 3 warnings`. The warnings were existing
`datetime.utcnow()` deprecation warnings in runtime helper code.

Coverage included:

- repair lifecycle tests:
  - active repair does not let stale failed `node_results` terminalize dependencies
  - failed parent status reopens when graph has active repair/re-eval work
  - repaired handoff schedules fresh evaluator dispatch with repair generation metadata
- graph patch-proof tests:
  - `patch_diff exists` without a `field` triggers patch proof
  - `output_present` with `field=patch_diff` is honored
  - patch proof presence is true only when a real non-empty patch file exists
- route-proof tests:
  - OpenAI-only proof passes
  - non-OpenAI provider violation is detected
- PM dispatch tests:
  - implementation capsule test-authoring aliases are canonicalized
  - provider-policy route behavior stays fail-closed
- Codex operator contract tests:
  - command construction and output/result path contracts remain stable

## 3. Live E2E Evidence

Run command:

```bash
SOLAR_LIVE_E2E_ALLOW=1 scripts/live-codex-e2e-isolated.sh --timeout-seconds 1800 --poll-seconds 30
```

Run metadata:

- Sprint: `sprint-20260701-202854-intent-write-a-python-command-line--c42d1e2f`
- Sandbox: `/tmp/solar-live-codex-e2e.mNglEl`
- Preserved bundle: `/tmp/RC8-CODEX-ONLY-LIVE-E2E-CD528D0A-PASS-20260701-202854`
- Final status: `passed`
- Final phase: `finalized`
- Final task graph status: `passed`
- Poll result: status reached `passed` at poll 23
- Worktree status after run: clean
- Current-run process residue after teardown delay: clean for `/tmp/solar-live-codex-e2e.mNglEl`

Route-proof summary:

```json
{
  "ok": true,
  "selected_runtime": "codex",
  "allowed_providers": ["openai"],
  "violations": [],
  "stage_count": 5,
  "providers": ["openai"]
}
```

Stage / operator / model / provider table:

| Stage | Node | Operator | Model | Provider | Result |
| --- | --- | --- | --- | --- | --- |
| Planner | `N0` | `mini-codex-gpt55-medium-planner-1` | `gpt-5.5` | `openai` | completed |
| Builder | `S1_SPEC_IMPL_DOCS` | `mini-codex-gpt53-spark-builder-1` | `gpt-5.3-codex-spark` | `openai` | completed / passed |
| Builder | `S2_EXECUTION_EVIDENCE` | `mini-codex-gpt53-spark-builder-1` | `gpt-5.3-codex-spark` | `openai` | completed / passed |
| Evaluator | `S3_INDEPENDENT_REVIEW` | `mini-codex-gpt55-medium-evaluator-1` | `gpt-5.5` | `openai` | completed |
| Builder closeout | `S3_INDEPENDENT_REVIEW` | `mini-codex-gpt53-spark-builder-1` | `gpt-5.3-codex-spark` | `openai` | completed / passed |

Artifact list:

- Status: `sprint-20260701-202854-intent-write-a-python-command-line--c42d1e2f.status.json`
- Task graph: `sprint-20260701-202854-intent-write-a-python-command-line--c42d1e2f.task_graph.json`
- Route proof: `sprint-20260701-202854-intent-write-a-python-command-line--c42d1e2f.route-proof.json`
- Patch proof: `sprint-20260701-202854-intent-write-a-python-command-line--c42d1e2f.S1_SPEC_IMPL_DOCS-patch.diff`
  - size: `7023` bytes
  - references `uniqwords.py`
- S1 evaluator artifacts:
  - `sprint-20260701-202854-intent-write-a-python-command-line--c42d1e2f.S1_SPEC_IMPL_DOCS-eval.md`
  - `sprint-20260701-202854-intent-write-a-python-command-line--c42d1e2f.S1_SPEC_IMPL_DOCS-eval.json`
- Run ledgers:
  - `pm-inbox/`
  - `operator-results/`
  - `dispatch-ledger.jsonl`
- Logs:
  - `evidence/logs/status-server.out.log`
  - `evidence/logs/status-server.err.log`
  - `evidence/logs/cockpit-start.log`
- Generated workspace artifacts:
  - `workdir/uniqwords.py`
  - `workdir/tests/test_uniqwords.py`
  - `workdir/README.md`

No failure markers were present in the evidence directory:

- no `INVALID_EVIDENCE.json`
- no `TIMEOUT_NOT_PRODUCT_PROOF.json`
- no `MODEL_REGISTRY_PREFLIGHT_FAILED.json`
- no `*FAILED*.json`

## 4. Scope Statement

This smoke proves:

- Codex-only PM -> Planner -> Builder -> Evaluator smoke path.
- OpenAI-only fail-closed route proof for this smoke.
- Node patch-proof sidecar generation.
- Basic artifact and evidence closeout.

This smoke does not yet prove:

- Claude-only runtime.
- Setup wizard or installer.
- Windows WSL fresh install.
- macOS fresh install.
- Deep research or live web research.
- AutoSci.
- Long report generation.
- Repair lifecycle in live E2E, although deterministic repair tests pass.

## 5. Known Risks

- Older unrelated `/tmp/solar-live-codex-e2e.*` coordinator/watchdog leftovers
  were observed on the host from previous runs. The current passing run cleaned
  up after teardown delay, but cleanup hygiene should be handled separately.
- `route-proof.json` should receive a product-release review before declaring
  provider routing fully release-gated.
- The setup wizard branch is separate from this runtime integration branch.
- The server-side setup gate is still separate.
- The direct browser dashboard path may bypass the Electron preload gate until
  the server-side gate is added.

## 6. Recommended Next Steps

1. Push `integration/rc8-runtime-mode-contract` for review after approval.
2. Do cleanup hygiene in a separate patch.
3. Run Claude-only equivalent or fail-closed proof.
4. Run a realistic AI4Research prompt after branch review.
5. Integrate the setup wizard later through a separate integration branch.
