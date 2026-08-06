# Research Orchestration Phase 5 Generalization Log

Baseline: `ea571c94ed06b439fb5ae0532ec4e934cea3c022`

Integration worktree: `C:/Users/j50058254/Desktop/Github repo/.phase5-worktrees/integration`

Branch: `codex/phase5-generalization-integration`

Current reviewed HEAD before final document/result commit: `5b37cd2e2510213a2702da4addfda019ff0ce89f`

## Worker Rerun Evidence

| Worker | Decision | Follow-up commit | Rerun result | Integration action |
| --- | --- | --- | --- | --- |
| content-diversity-rerun | Accepted as real provider-injected FAIL evidence | none; tested `2f17619f47e40e39cd699ec165709ce88b0aff05` | pytest `3 passed`; both realistic cases `FAIL` | No worker code commit expected. Product prompt contract fix added separately in integration. |
| lifecycle-recovery-rerun | Accepted after product repair | `a41848fc3996ae201500f33ef1016f91b735b534` | worker exposed `3 failed, 1 passed`; after integration repair `4 passed` | Cherry-picked as `27c438f81`; product fix commit `0d92ddb98`. |
| platform-provider-rerun | Accepted | `82979db091a6f3af9d22a066a04f3fe998cdc7c3` | worker `11 passed`; integration `11 passed` | Cherry-picked as `c990e8d23`. |

## Integration Commits This Round

| Commit | Purpose |
| --- | --- |
| `c990e8d23` | Port strict Phase 5 platform/provider checks. |
| `27c438f81` | Remove lifecycle test workarounds so product behavior is tested directly. |
| `0d92ddb98` | Route lifecycle experiment result evidence through approval and claim verification scopes. |
| `5b37cd2e` | Preserve content acceptance requirements in production model prompts. |

## Content Review

Provider variables in the content worker were process-only and recorded as present/absent, not values. Secret scan in worker evidence passed with no secret value hits.

Both realistic content cases ran the production bridge with live provider access and wrote real artifacts, including report, final acceptance, source validation, evidence synthesis, node records, provider usage archives, and hashes. Pytest passing only means the worker captured and asserted the evidence; it is not a case PASS.

| Case | Runtime result | Gate result | Evidence |
| --- | --- | --- | --- |
| `zh_web_technical_report` | `failed`, exit code 2 | FAIL: fewer than 2 cited sources / task success criteria not met | `C:/Users/j50058254/Desktop/Github repo/OpenSolar-Canonical/.codex-tmp/phase5-worker-results/content-diversity-rerun/result.json` |
| `en_rag_reliability_survey` | `failed`, exit code 2 | FAIL: explicit deliverable content requirement failed; report lacked method/evidence section | same result file |

Integration added a general product fix to the production model prompt contract: require at least two distinct cited sources when available and require an explicit Method/Evidence Method section for survey/technical reports. The integration process did not have provider secrets, so this fix remains not live-provider revalidated in this turn.

## Lifecycle Review

The lifecycle rerun removed four test workarounds:

1. Manual `experiment_approval_gate.write_scope` addition.
2. Manual experiment design payload injection of metrics/success criteria/sandbox write scope.
3. Manual `claim_verify` read scope and input artifact injection for experiment result.
4. Manual dependency/read-scope post-processing for `claim_verify -> experiment_monitor`.

The stricter test exposed product gaps at `2f17619f`: `claim_verify.read_scope` omitted `experiment_result.v1.json`, and `experiment_approval_gate.write_scope` did not include the experiment result path required by the product default sandbox. Integration fixed both in `apply_task_conditions`; rerun passed `4 passed in 12.07s`.

## Platform Review

The platform rerun did not relax return-code or final-status checks. It distinguishes:

- completed platform path: Windows and WSL controlled-services runs reach `completed`;
- entrypoint smoke only: formal bridge with scrubbed provider env reaches `awaiting_external`, not counted as completed E2E;
- provider resilience: 429 Retry-After, persistent 429, timeout recovery, hard failures, and completed-node dedupe all pass with finite bounded behavior.

Integration rerun: `11 passed in 46.51s`.

## Final Verification Commands

| Area | Command summary | Exit code | Result |
| --- | --- | --- | --- |
| Content diversity | `pytest harness/tests/research_orchestration/generalization/test_phase5_content_diversity.py -q` with provider env cleared and isolated result root | 0 | `3 passed in 556.70s`; local no-provider run records provider-blocked runtime evidence, not case PASS. |
| Seed portability | `pytest harness/tests/research_orchestration/generalization/test_phase5_seed_portability.py -q -p no:cacheprovider` | 0 | `7 passed in 12.67s` |
| Lifecycle recovery | `pytest harness/tests/research_orchestration/generalization/test_phase5_lifecycle_recovery.py -q` | 0 | `4 passed in 20.67s` |
| Platform/provider | `pytest harness/tests/research_orchestration/generalization/test_phase5_platform_provider_resilience.py -q --tb=short` | 0 | `11 passed in 46.51s` |
| State/routing | `pytest test_research_state_store.py test_research_production_routing.py -q` | 0 | `25 passed in 4.15s` |
| Production services | `pytest test_production_research_services.py -q` | 0 | `11 passed in 0.94s` |
| Result validation/evaluator/runtime | `pytest test_research_result_validation.py test_research_orchestrator.py test_research_production_runtime.py -q` | 0 | `103 passed in 16.51s` |
| Phase 4 full selector | Phase 4 selector plus accepted Phase 5 tests and service regressions | 0 | `472 passed in 895.72s` |
| `git diff --check` | whole worktree | 0 | passed |

## Overall Verdict

Phase 5 is **FAIL / not fully passed**. Generalization improved and the accepted regression suite is green, but the two live-provider content cases still failed final acceptance in the worker rerun. The content prompt repair added after that evidence needs a new provider-injected rerun before those cases can be promoted.
