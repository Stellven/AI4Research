# Research Orchestration Phase 5 Generalization Report

## Verdict

Phase 5 overall result: **FAIL / NOT PASS**.

The integration branch proves the shared Solar research control plane across seed portability, local PDF, external evidence import, lifecycle recovery, interrupt/resume, Windows/WSL controlled completed paths, entrypoint smoke, provider retry/timeout/failure recovery, and live-provider content execution. It still does not prove full Phase 5 completion because the English RAG content-diversity case failed final acceptance after live OpenRouter rerun.

No live run used `gpt-5.6-sol`. The authorized live reruns used OpenRouter with model `gpt-5.6-luna` as process-only provider configuration; provider key values were not logged or committed.

## Case Results

| Case | Input | Production entrypoint | Workflow/control plane | Operators | Result | Evidence paths | Known limitations | Product fixes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chinese webpage technical report | Tencent News URL plus Chinese report prompt | `autosci_bridge.py research` | `SolarResearchRuntime` -> `ResearchOrchestrator`; route `seed_kind=url`, `workflow_kind=research_synthesis`, start `seed_fetch` | `seed_fetch`, `source_discovery`, `source_validation`, `evidence_synthesis`, `report_draft`, `independent_review`, `final_acceptance` | PASS_WITH_KNOWN_LIMITATIONS | `C:/tmp/p5qual20260806084035/result.json`; report sha `d7b45832e934ab2c7c19f37659a26669db064aafd6d9ae184e1a90679e1849bb` | Runtime completed and final gate passed; worker relevance heuristic still flags `report_relevant` because the Markdown report does not include the URL/domain token. | `b439a113c`, `0653e7f5` |
| English RAG reliability survey | English topic prompt | `autosci_bridge.py research` | same control plane; route `seed_kind=topic`, `workflow_kind=literature_synthesis`, start `source_discovery` | `source_discovery`, `source_validation`, `evidence_synthesis`, `report_draft`, `independent_review`, `final_acceptance` | FAIL | `C:/tmp/p5qual20260806084035/result.json`; report sha `a8d98cf90b1697a0ee3dd946325692a3b099165383d2e446fbb2e32933fdf6e1` | Query extraction now reaches Semantic Scholar with RAG-specific sources, but independent review still returned `revise`; final gate failed due duplicate Conclusions and one imprecise citation mapping. | `b439a113c`, `0653e7f5`; remaining report-quality repair required |
| Local PDF synthesis seed | Valid local PDF fixture | Production Solar runtime through seed worker test | seed portability route | PDF ingest and downstream report assertions | PASS | `tests/harness/research_orchestration/generalization/test_phase5_seed_portability.py` | Exact PDF limitation sentence remains in ingested artifact rather than verbatim final report. | Long-path input/output readers and validators preserved. |
| Invalid local PDF | Invalid PDF fixture | Production Solar runtime through seed worker test | same seed portability control plane | PDF rejection path | PASS | same seed test/result | None for tested path. | Maintained invalid-input rejection. |
| External experiment evidence import | Scoped external evidence JSON | Production Solar runtime through seed worker test | import/resume contract route | imported evidence, downstream citation | PASS_WITH_KNOWN_LIMITATIONS | same seed test/result | Contract-level external evidence import coverage, not a full external experiment lifecycle through `experiment_run` / `experiment_monitor`. | Artifact identity/hash/scope validation preserved. |
| Lifecycle full path | Paper/repo/evidence fixtures | Production Solar runtime through lifecycle test | scientific lifecycle workflow | claim verify, experiment design, approval, run, monitor, report, review | PASS | `tests/harness/research_orchestration/generalization/test_phase5_lifecycle_recovery.py` | Bounded fixture-backed lifecycle. | `0d92ddb98` |
| Interrupt/resume | Lifecycle interruption/resume scenario | Production Solar runtime through lifecycle test | same lifecycle control plane | completed-node resume behavior | PASS | same lifecycle test/result | None for tested path. | Resume does not rerun completed nodes. |
| Windows completed platform path | Controlled-services local platform probe | Production runtime/resolver, no live provider | same control plane with deterministic services | production route and artifact hash checks | PASS | `tests/harness/research_orchestration/generalization/test_phase5_platform_provider_resilience.py` | No live provider in this path. | Strict platform test merged. |
| WSL completed platform path | Direct WSL controlled-services probe with Linux paths | WSL helper / production runtime | same control plane | production route and artifact hash checks | PASS | same platform test/result | WSL system Python lacks pytest, but helper does not require pytest. | Strict WSL path handling test merged. |
| Windows entrypoint smoke | Formal bridge with provider env scrubbed | `autosci_bridge.py research` | literature synthesis route | `source_discovery` gate | ENTRYPOINT_SMOKE_PASS | same platform test/result | Stops at `awaiting_external`; not counted as completed E2E PASS. | Status truthfulness preserved. |
| WSL entrypoint smoke | Formal bridge via `wsl.exe`, provider env scrubbed | WSL `python3 autosci_bridge.py research` | same route/status as Windows | `source_discovery` gate | ENTRYPOINT_SMOKE_PASS | same platform test/result | Stops at `awaiting_external`; not counted as completed E2E PASS. | Status truthfulness preserved. |
| Provider 429 Retry-After recovery | Mock OpenAI-compatible route | `ResearchModelService` shared production service | same provider route | model provider adapter | PASS | `tests/plugins/autosci/test_production_research_services.py` and platform test | Unit/controlled transport regression; no live provider. | Same-route bounded retry added. |
| Persistent 429 | Mock persistent 429 provider | `ResearchModelService` | same provider route | model provider adapter | PASS | same service/platform tests | Fails finitely after retry budget; not converted to completed. | Finite retry budget exercised. |
| Provider timeout recovery | Mock timeout then success | `ResearchModelService` | same provider route | model provider adapter | PASS | same service/platform tests | Unit/controlled transport regression. | Same-route timeout retry added. |
| Provider hard failures | 401, 503, malformed response | Production provider adapter tests | same route/failure classifier | model provider adapter | PASS | same service/platform tests | No live provider. | Hard failures remain failed/current_blockers and are not written completed. |

## Final Verification

Previously completed full Phase 4 selector on this integration branch:

```powershell
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' -m pytest -q tests/harness/contracts/test_research_orchestration_contracts.py tests/harness/research_orchestration tests/plugins/autosci/research_synthesis_operators tests/plugins/autosci/test_evidence_physical_operators.py tests/plugins/autosci/scientific_lifecycle_action_operators tests/plugins/autosci/test_production_research_services.py tests/plugins/autosci/test_literature_discover.py --basetemp C:\tmp\phase5-final-phase4-selector-bt -o cache_dir=C:\tmp\phase5-final-phase4-selector-cache
```

Result: `472 passed in 895.72s`.

Final HEAD focused checks after live-provider repair commits:

- Content diversity live OpenRouter `gpt-5.6-luna`: `3 passed in 205.47s`; case evidence `zh=PASS_WITH_KNOWN_LIMITATIONS`, `en=FAIL`.
- Production research service tests: `13 passed in 1.02s`.
- Research synthesis operator tests: `50 passed in 0.86s`.
- Result validation/evaluator/runtime tests: `103 passed in 18.73s`.
- Prior Phase 5 worker tests retained: seed `7 passed`, lifecycle `4 passed`, platform/provider `11 passed`.
- `git diff --check`: passed on the final document diff.
- Secret scan: no provider key values were printed, archived in committed files, or staged.

## Remaining Limitations

1. English live-provider content still fails final acceptance because the generated report retained one citation precision issue and duplicate conclusion structure.
2. Chinese live-provider content final gate passes, but the worker relevance heuristic remains stricter than the deterministic gate because it expects URL/domain text in the final report.
3. Completed platform paths are controlled-services paths; formal Windows/WSL bridge runs with provider env scrubbed remain entrypoint smoke only.
4. Live provider behavior is nondeterministic; accepted status is based on recorded command, artifact, node/operator, review, and gate evidence, not pytest pass alone.
