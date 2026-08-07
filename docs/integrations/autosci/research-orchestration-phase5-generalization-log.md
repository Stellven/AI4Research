# Research Orchestration Phase 5 Generalization Log

Baseline: `ea571c94ed06b439fb5ae0532ec4e934cea3c022`

Integration worktree: `C:/Users/j50058254/Desktop/Github repo/.phase5-worktrees/integration`

Branch: `codex/phase5-generalization-integration`

Current reviewed HEAD before final document/result commit: `0653e7f5efcf075e8b0e67d1a6619faba88ef0b9`

## Worker Rerun Evidence

| Worker | Decision | Follow-up commit | Rerun result | Integration action |
| --- | --- | --- | --- | --- |
| content-diversity-rerun | Accepted as real provider-injected failure evidence; superseded by integration live reruns after user authorization | none; worker tested `2f17619f47e40e39cd699ec165709ce88b0aff05` | worker pytest `3 passed`; both realistic cases failed final acceptance | No worker code commit expected. Integration added product repairs and reran live provider with process-only env. |
| lifecycle-recovery-rerun | Accepted after product repair | `a41848fc3996ae201500f33ef1016f91b735b534` | worker exposed `3 failed, 1 passed`; after integration repair `4 passed` | Cherry-picked as `27c438f81`; product fix commit `0d92ddb98`. |
| platform-provider-rerun | Accepted | `82979db091a6f3af9d22a066a04f3fe998cdc7c3` | worker `11 passed`; integration `11 passed` | Cherry-picked as `c990e8d23`. |

## Integration Commits This Round

| Commit | Purpose |
| --- | --- |
| `c990e8d23` | Port strict Phase 5 platform/provider checks. |
| `27c438f81` | Remove lifecycle test workarounds so product behavior is tested directly. |
| `0d92ddb98` | Route lifecycle experiment result evidence through approval and claim verification scopes. |
| `5b37cd2e` | Preserve content acceptance requirements in production model prompts. |
| `b439a113c` | Add explicit model `allowed_source_ids` and improve topic query extraction for live research providers. |
| `0653e7f5` | Tighten report quality prompt contract and add deterministic Evidence Method section when omitted. |

## Live Content Rerun

The user authorized OpenRouter/OpenAI live provider use and prohibited `gpt-5.6-sol`. Integration used OpenRouter with `AUTOSCI_RESEARCH_LLM_MODEL=gpt-5.6-luna`; the route archived model id as `openai/gpt-5.6-luna`. Provider keys were loaded only into the pytest subprocess from an allowlist and were not printed.

Final live command summary:

```powershell
python -m pytest tests/harness/research_orchestration/generalization/test_phase5_content_diversity.py -q --basetemp C:\tmp\p5qualbt20260806084035 -o cache_dir=C:\tmp\p5qualcache20260806084035
```

Environment summary: `AUTOSCI_LIVE_PROVIDER_TESTS=1`, provider `openrouter`, model `gpt-5.6-luna`, result root `C:/tmp/p5qual20260806084035`.

Result: exit code `0`; pytest `3 passed in 205.47s`. Pytest pass is not treated as case pass.

| Case | Runtime result | Gate result | Integration status | Evidence |
| --- | --- | --- | --- | --- |
| `zh_web_technical_report` | `completed`, exit code 0 | accepted, `gate_outcome=pass`, review `accept`, method rendered | PASS_WITH_KNOWN_LIMITATIONS | `C:/tmp/p5qual20260806084035/result.json`; report sha `d7b45832e934ab2c7c19f37659a26669db064aafd6d9ae184e1a90679e1849bb` |
| `en_rag_reliability_survey` | `failed`, exit code 2 | rejected, `gate_outcome=fail`, review `revise`, method rendered | FAIL | `C:/tmp/p5qual20260806084035/result.json`; report sha `a8d98cf90b1697a0ee3dd946325692a3b099165383d2e446fbb2e32933fdf6e1` |

The English query extraction repair did take effect: the final discovery query was `reliability and evaluation methods for retrieval-augmented generation systems`, and discovery used `production:semantic_scholar` with RAG-specific titles. Remaining failure is report quality: duplicate Conclusions and one imprecise citation mapping.

## Lifecycle Review

The lifecycle rerun removed four test workarounds:

1. Manual `experiment_approval_gate.write_scope` addition.
2. Manual experiment design payload injection of metrics/success criteria/sandbox write scope.
3. Manual `claim_verify` read scope and input artifact injection for experiment result.
4. Manual dependency/read-scope post-processing for `claim_verify -> experiment_monitor`.

The stricter test exposed product gaps at `2f17619f`: `claim_verify.read_scope` omitted `experiment_result.v1.json`, and `experiment_approval_gate.write_scope` did not include the experiment result path required by the product default sandbox. Integration fixed both in `apply_task_conditions`; rerun passed `4 passed in 20.67s`.

## Platform Review

The platform rerun did not relax return-code or final-status checks. It distinguishes:

- completed platform path: Windows and WSL controlled-services runs reach `completed`;
- entrypoint smoke only: formal bridge with scrubbed provider env reaches `awaiting_external`, not counted as completed E2E;
- provider resilience: 429 Retry-After, persistent 429, timeout recovery, hard failures, and completed-node dedupe all pass with finite bounded behavior.

Integration rerun: `11 passed in 46.51s`.

## Final Verification Commands

| Area | Command summary | Exit code | Result |
| --- | --- | --- | --- |
| Content diversity live | `pytest tests/harness/research_orchestration/generalization/test_phase5_content_diversity.py -q` with OpenRouter `gpt-5.6-luna` and result root `C:/tmp/p5qual20260806084035` | 0 | `3 passed in 205.47s`; `zh=PASS_WITH_KNOWN_LIMITATIONS`, `en=FAIL` by gate evidence |
| Seed portability | `pytest tests/harness/research_orchestration/generalization/test_phase5_seed_portability.py -q -p no:cacheprovider` | 0 | `7 passed in 12.67s` |
| Lifecycle recovery | `pytest tests/harness/research_orchestration/generalization/test_phase5_lifecycle_recovery.py -q` | 0 | `4 passed in 20.67s` |
| Platform/provider | `pytest tests/harness/research_orchestration/generalization/test_phase5_platform_provider_resilience.py -q --tb=short` | 0 | `11 passed in 46.51s` |
| State/routing | `pytest test_research_state_store.py test_research_production_routing.py -q` | 0 | `25 passed in 4.15s` |
| Production services, final HEAD | `pytest tests/plugins/autosci/test_production_research_services.py -q` | 0 | `13 passed in 1.02s` |
| Research synthesis operators, final HEAD | `pytest tests/plugins/autosci/research_synthesis_operators -q` | 0 | `50 passed in 0.86s` |
| Result validation/evaluator/runtime, final HEAD | `pytest test_research_result_validation.py test_research_orchestrator.py test_research_production_runtime.py -q` | 0 | `103 passed in 18.73s` |
| Phase 4 full selector | Phase 4 selector plus accepted Phase 5 tests and service regressions, run before the latest content repair commits | 0 | `472 passed in 895.72s` |

## Overall Verdict

Phase 5 is **FAIL / not fully passed**. The shared control plane is substantially repaired and live provider execution is now proven for content, but the English content-diversity case still fails final acceptance. The failure remains recorded as a product/report-quality blocker rather than being converted to environment blocked or pytest PASS.
