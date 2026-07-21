# AutoSci Phase 5 Progress Log

Logged: 2026-06-17 14:51:59 EDT
Updated: 2026-06-17 15:49:46 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 5 registered AutoSci backend workers as Solar physical operators and bound
the Phase 3 `Scientific*` logical operators to those workers.

This phase does not add TaskGraph templates, evaluator gates, memory mutation,
ideation logic, or any AutoSci-owned end-to-end workflow runner. Solar remains
the workflow authority and only dispatches bounded backend actions through the
Phase 4 bridge.

## Files Changed

| Path or artifact | Operation | Commit | Note |
|---|---|---|---|
| `harness/config/physical-operators.json` | Modified | this phase commit | Added 8 AutoSci command-backend physical operators. |
| `harness/config/logical-operators.json` | Modified | this phase commit | Added 11 `Scientific*` logical-to-physical bindings. |
| `harness/artifacts/autosci/smoke/envelope.claim_extract.json` | Added, then removed | `987aefc2`, `f4ff02b8` | Temporary human-testable submit envelope was removed after verification; future checkers should create it temporarily and delete it after the run. |
| `docs/integrations/autosci/phase5-progress-log.md` | Added | this phase commit | This audit log for Phase 5. |

## Checker Carry-Forward Note

For future checker agents and follow-up conversations, use the current Phase 2
capsule token `cap.research-claim-extract`. Do not use the stale
`cap.scientific-claim-extract` token in AutoSci Phase 5/6 dispatch checks.

Claim extraction ownership clarification for later phases:

| Item | Phase 5 status | Later-phase wording |
|---|---|---|
| `ScientificClaimExtractor` | Already introduced in Phase 3 and covered by Phase 5 binding checks. | Later phases should say they used it, not added it. |
| `extract_claims` bridge action | Already available through the AutoSci bridge path by Phase 5 functional dispatch. | Later phases should say they used or validated it, unless they materially change action behavior. |
| `autosci-claim-extract-worker` | Registered as the AutoSci-backed physical worker in Phase 5. | Later phases should say they used it, not added it. |

Run operator-runtime submit checks from the project-local harness with
`HARNESS_DIR=$PWD` and the project `.venv` Python. System `python3` may not have
PyYAML, and without `HARNESS_DIR=$PWD` the runtime may fall back to
`~/.solar/harness` for capsule registry resolution.

Scheduler-cleanliness caveat: the current AutoSci physical operators can execute
through the local `backend: command` path, but their `owner_host` values are
still the placeholder `solar@example-host` and they do not declare an explicit
valid `host_id`. `operator_runtime.submit()` and `operatord` do not enforce
`owner_host`, so successful local smoke runs prove bridge execution, not full
Solar host-owned scheduling validity.

## Physical Operators

| Physical operator | Bridge action | Status | Logical coverage |
|---|---|---|---|
| `autosci-paper-ingest-worker` | `ingest_paper` | ok | `ScientificPaperIngestor` |
| `autosci-claim-extract-worker` | `extract_claims` | ok | `ScientificClaimExtractor` |
| `autosci-memory-update-worker` | `update_memory` | pending | `ScientificMemoryUpdater` |
| `autosci-idea-worker` | `generate_ideas` | pending | `ScientificIdeaGenerator`, `ScientificIdeaEvaluator` |
| `autosci-experiment-design-worker` | `design_experiment` | ok | `ScientificExperimentDesigner` |
| `autosci-experiment-run-worker` | `run_experiment` | ok | `ScientificExperimentRunner` |
| `autosci-claim-verify-worker` | `verify_claim` | ok | `ScientificClaimVerifier` |
| `autosci-report-worker` | `write_report` | ok | `ScientificReportPlanner`, `ScientificReportDrafter`, `ScientificPublicationProducer` |

## Binding Policy

| Area | Policy |
|---|---|
| Enabled backends | Use command backend through `plugins/autosci/bin/autosci_bridge.py run --action ... --envelope "$SOLAR_OPERATOR_ENVELOPE_JSON"`. |
| Pending backends | Memory update and idea generation/evaluation are registered but disabled until their later planned phases. |
| Capability names | Physical preferences use `cap.research-*`; no `cap.scientific-*` tokens were added. |
| Workflow ownership | No `AutoSciRunner` logical operator or binding was added. |
| Network | AutoSci physical operators are configured with `network: denied`. |
| Writes | Operator policy limits writes to artifact output scope. |

## Scheduler Cleanliness Issue

| Issue | Status | Impact | Recommended fix |
|---|---|---|---|
| AutoSci physical operators use placeholder `owner_host: solar@example-host` and no explicit `host_id`. | warn | AutoSci-backed surfaces are locally runnable but not cleanly schedulable by Solar's host/actor contract. | Add a real project-local command host entry, then set each AutoSci physical operator to that `host_id` and replace `owner_host` with a non-placeholder local owner such as `localhost` or the new host id. |

Recommended implementation shape:

```text
config/actor-hosts.json
  hosts.autosci_local_command_host
    host_type: local_command_worker
    lifecycle.state: online
    address.hostname: localhost
    address.harness_dir: <OpenSolar>/harness or project-local relative policy

config/physical-operators.json
  autosci-*-worker
    host_id: autosci_local_command_host
    owner_host: localhost
```

Do not treat Phase 5 as scheduler-clean until a host-binding validation confirms
the AutoSci physical operators resolve to a registered non-placeholder host. The
existing actor registry may infer a host when `host_id` is missing, but that
compatibility inference should not be the acceptance basis for AutoSci-backed
scheduling.

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | ok with warning | Used repo-local `HARNESS_DIR=<OpenSolar>/harness bash solar-harness.sh context inject`; Mirage source was degraded. |
| Physical operator JSON parse | ok | `python3 -m json.tool harness/config/physical-operators.json` passed. |
| Logical operator JSON parse | ok | `python3 -m json.tool harness/config/logical-operators.json` passed. |
| Smoke envelope JSON parse | ok | `python3 -m json.tool harness/artifacts/autosci/smoke/envelope.claim_extract.json` passed. |
| Operator registry verification | ok | Script confirmed all 8 AutoSci physical operators, command backend wiring, disabled pending workers, network policy, and `cap.research-*` preferences. |
| Logical binding verification | ok | Script confirmed 11 expected `Scientific*` bindings and no `AutoSciRunner` binding. |
| Dispatch smoke | ok | `operator_runtime.submit()` dispatched `autosci-claim-extract-worker`; operatord completed with exit code 0. |
| Bridge result validation | ok | `python3 plugins/autosci/bin/autosci_bridge.py validate --result artifacts/autosci/smoke/claim_extract_dispatch/result.json` returned `ok: true`. |
| Phase 6 promotion check rerun | ok | Temporary envelope using `cap.research-claim-extract`, `HARNESS_DIR=$PWD`, and project `.venv` submitted `autosci-claim-extract-worker`; `artifacts/autosci/smoke/result.json` and `evidence.jsonl` were updated with `research_claims.v1`. |
| Stale-token negative check | warn | The pasted `cap.scientific-claim-extract` envelope is obsolete and fails capsule resolution; this is expected after the Phase 2 rename to `cap.research-*`. |
| Temporary envelope cleanup | ok | `harness/artifacts/autosci/smoke/envelope.claim_extract.json` was deleted after the smoke test and removed from git in `f4ff02b8`. |
| Enabled physical worker execution probe | ok with caveat | Six enabled AutoSci command workers completed via local `operator_runtime.submit()` and emitted valid Evidence ABI, but this did not validate `owner_host` or `host_id`. |
| Disabled placeholder rejection | ok | `autosci-memory-update-worker` and `autosci-idea-worker` reject dispatch with `state=disabled`. |
| Host binding validation | warn | AutoSci workers still use placeholder `owner_host: solar@example-host` and no explicit `host_id`; fix before declaring scheduler-clean Phase 5. |

## Dispatch Smoke Evidence

| Field | Value |
|---|---|
| Envelope | `harness/artifacts/autosci/smoke/envelope.claim_extract.json` |
| Operator | `autosci-claim-extract-worker` |
| Task | `task-autosci-phase5-claim-extract-smoke` |
| Result status | `completed` |
| Bridge result | `harness/artifacts/autosci/smoke/claim_extract_dispatch/result.json` |

## Corrected Human-Testable Dispatch Plan

Create `harness/artifacts/autosci/smoke/envelope.claim_extract.json`
temporarily with the active capsule token:

```json
{
  "task_id": "smoke-autosci-claim-extract",
  "sprint_id": "sprint-autosci-smoke",
  "node_id": "n1_claim_extract",
  "operator_id": "autosci-claim-extract-worker",
  "task_type": "SCIENCE_CLAIM_EXTRACTION",
  "objective": "Extract testable claims from the sample paper.",
  "capability_capsule_id": "cap.research-claim-extract",
  "output_dir": "artifacts/autosci/smoke",
  "inputs": {
    "paper_path": "plugins/autosci/tests/fixtures/sample_paper.md",
    "source_evidence": "plugins/autosci/tests/fixtures/sample_paper.md"
  },
  "outputs": {
    "result_path": "artifacts/autosci/smoke/result.json",
    "evidence_path": "artifacts/autosci/smoke/evidence.jsonl"
  },
  "lease_ttl_seconds": 300
}
```

Run from `harness/`:

```bash
HARNESS_DIR="$PWD" ../.venv/bin/python - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "lib")
import operator_runtime

env = json.loads(Path("artifacts/autosci/smoke/envelope.claim_extract.json").read_text())
print(operator_runtime.submit(env))
PY
```

After verification, delete the temporary envelope:

```bash
rm artifacts/autosci/smoke/envelope.claim_extract.json
```

## Notes

- Generated smoke outputs under
  `harness/artifacts/autosci/smoke/claim_extract_dispatch/*` were produced for
  local verification and are not intended as part of the Phase 5 commit.
- Generated Phase 6 promotion-check outputs under `harness/artifacts/autosci/smoke/`
  are verification artifacts; do not recommit a persistent envelope fixture there.
- The six enabled AutoSci workers are runnable only in the local command-backend
  sense until the host-binding issue above is fixed.
- `autosci-memory-update-worker` is intentionally disabled because the bridge
  action is planned for Phase 9; enabling it now would create a fake memory path.
- `autosci-idea-worker` is intentionally disabled because idea generation and
  evaluation are planned for Phase 11; enabling it now would create fake
  ideation.
- Existing unrelated dirty files were left untouched.

## Done State

Phase 5 is functionally demonstrated when Solar can map native `Scientific*`
logical operators to bounded AutoSci physical workers, submit at least one
fixture-backed worker through the normal operator runtime, validate the resulting
Evidence ABI output, and still has no hidden AutoSci-owned full workflow runner.

Phase 5 is scheduler-clean only after the AutoSci physical operators use explicit
registered host bindings instead of placeholder `owner_host` values.
