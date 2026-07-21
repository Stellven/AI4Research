# AI4Research Full QA Audit — post-gated update

## 1. Executive summary

**Final verdict: NOT READY for a full-repository success or live AutoSci parity claim.** All 1,435 rows that were formerly `NOT_RUN` now have an explicit terminal classification, but 112 atomic features are confirmed FAIL and 381 previously inconclusive rows outside the targeted NOT_RUN follow-up remain inconclusive.

Overall 2,117-row status: PASS 843, FAIL 112, BLOCKED_EXPECTED 36, INCONCLUSIVE_EXPECTED 381, SKIPPED_ENV 126, SKIPPED_NA 619, NOT_RUN 0.

For the 861 Codex-relevant rows selected from the former NOT_RUN set (after excluding Claude/SciDAG/SciMem), the final result is PASS 639, FAIL 72, SKIPPED_ENV 105, SKIPPED_NA 45, with zero NOT_RUN and zero INCONCLUSIVE_EXPECTED. The 576 excluded rows are preserved in `excluded-feature-ledger.csv`.

Tests used the local repository code at the locked SHA, from a detached isolated checkout. Production source was not modified. No live provider, real browser profile, real Calendar/email, remote machine, release, credential, or real user vault mutation was performed.

## 2. Tested repo, branch, and commit

| Field | Value |
|---|---|
| Source | `https://github.com/Stellven/AI4Research.git` |
| Requested/local branch | `openJiuwen-Solar` |
| Locked/tested SHA | `fb3f589b08e4167ac3cb0043fb3d59801a0f110b` |
| Code source used | Local locked checkout under this audit directory |
| Production source edits | None |
| Live phase | Not executed |

## 3. Environment

- Platform: macOS-27.0-arm64-arm-64bit-Mach-O (arm64)
- Shell: /bin/zsh; Python: Python 3.14.2; Node: v26.1.0; Bun: 1.3.14
- Git: git version 2.54.0 (Apple Git-157); tmux: tmux 3.6b; jq: jq-1.7.1-apple
- Follow-up gate boundary: disposable local fixtures only; no live credentials/provider/network or real external-app mutation.

## 4. Inventory validation result

The control workbook contains 2,117 atomic rows (workflow 652, foundations 844, misc. 621). The locked checkout contains 5,259 tracked files and the generated function/module/route/script inventory contains 31,463 rows. Fifteen public production entrypoints remain classified `missing-feature-row`.

Post-follow-up corrections include two nonexistent `skills-md` rows changed to `SKIPPED_NA`, concrete Obsidian/Calendar/RAGFlow/Codex/browser/Gemini entrypoints, and explicit documentation-only classifications for office and browser-automation.

## 5. Feature coverage summary by part

| Part | PASS | FAIL | BLOCKED_EXPECTED | INCONCLUSIVE_EXPECTED | SKIPPED_ENV | SKIPPED_NA | FLAKY | NOT_RUN | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| workflow | 337 | 77 | 2 | 130 | 17 | 89 | 0 | 0 | 652 |
| foundations | 280 | 12 | 30 | 130 | 3 | 389 | 0 | 0 | 844 |
| misc. | 226 | 23 | 4 | 121 | 106 | 141 | 0 | 0 | 621 |

`feature-results.csv` is authoritative. Coverage mapping and execution status are separate fields; a mapped test is not treated as proof unless its atomic assertions were validated.

## 6. Function inventory summary

- Inventory rows: 31463
- Classification counts: generated 1, mapped 22556, missing-feature-row 15, support-only 162, test-only 8729
- Public unmapped entrypoints: 15

## 7. Test execution summary

| Execution surface | Result | Interpretation |
|---|---|---|
| Original strict eligible phase | 93 targets passed, 14 failed; 523 tests passed, 15 failed, 3 errored, 1 skipped | Direct testcase attribution; fixture/local only. |
| Approved AutoSci gated selection | 8 passed | Disposable wiki/raw/approval fixtures only. |
| Control-plane plan verdict | 13 assertions passed | Approved verdict stored only in a disposable sprint. |
| Approved gate atomic contracts | 2 passed, 1 failed | Survey archive bypassed approval. |
| Misc side-effect gate contracts | 1 passed, 4 failed | Four surfaces lack a human approval boundary. |
| Manual/oracle contracts | 11 passed, 2 failed | Exact semantic rubrics; no provider claims. |
| Remaining app/browser/provider contracts | 13 passed, 5 failed | Fake/local providers and disposable data; no live parity. |
| Selected former-NOT_RUN subset | PASS 639, FAIL 72, SKIPPED_ENV 105, SKIPPED_NA 45 | Zero unresolved status in this 861-row scope. |

`command-log.tsv` now contains 90 commands with working directory, exit code, timestamps, evidence paths, and linked feature IDs.

## 8. Detailed feature results

The complete 2,117-row result set is `feature-results.csv`. The table below records the final 20 blocker-remediation decisions from the approved isolated follow-up.

| Feature ID | Result | Atomic feature | Rationale |
|---|---|---|---|
| `WF-0422-CAPTURED-OUTPUT-HAS-SOURCE-1CDA2F` | PASS | Captured output has source URL, timestamp, and artifacts. | A fake in-process browser probe ran through the locked submit/poll/collect entrypoints and produced a page.json with the exact final URL, non-empty start/finish timestamps, screenshot, HTML, text, metadata, and result JSON artifacts in a disposable directory. |
| `WF-0423-RETRIES-FAILS-CHECKPOINTED-STATE-089989` | PASS | Retries/fails with checkpointed state and no duplicate side effects. | A deterministic running-to-failed sequence persisted its terminal state, repeated polling byte-preserved the checkpoint, and repeated collection overwrote the same bounded artifact set without creating duplicate side effects. |
| `WF-0425-RUNS-RECORDS-BROWSER-AUTOMATION-FAA4C2` | PASS | Runs/records browser automation or reports unavailable browser deterministically. | Two identical social-browser CLI invocations with no wired pipeline returned the same typed lease-fallback exit code, browser_ready=0 status, and explicit no-pipeline message without attempting a live browser. |
| `WF-0426-CAPTURED-OUTPUT-HAS-SOURCE-6F503B` | FAIL | Captured output has source URL, timestamp, and artifacts. | The isolated mock social-browser pipeline stored a post and JSON sidecars, but the Knowledge raw artifact omitted source_url and the queue artifact omitted a screenshot artifact binding, so URL, timestamp, and capture artifacts are not unified in the required output contract. |
| `MISC-0305-HANDLES-SUPPORTED-SOURCE-REQUEST-0F0924` | FAIL | Handles supported source/request inputs and rejects unsupported ones. | The shipped skills/office directory contains only SKILL.md prose and no executable dispatcher or adapter, so there is no entrypoint that accepts supported office requests or rejects unsupported ones. |
| `MISC-0307-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5310ED` | FAIL | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | The shipped office skill has no executable provider boundary and therefore cannot emit a structured failed/inconclusive result when Himalaya, Reminders, Things, Notion, or Trello is unavailable. |
| `MISC-0310-HANDLES-SUPPORTED-SOURCE-REQUEST-28972A` | PASS | Handles supported source/request inputs and rejects unsupported ones. | The Obsidian CLI created a note only inside a disposable vault for a supported request and argparse rejected an unsupported command with a non-zero process status. |
| `MISC-0312-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-CBB1BC` | PASS | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | The Obsidian CLI received a nonexistent disposable vault, exited non-zero with an explicit Vault not found reason, created no vault or fake note, and returned no fabricated data. |
| `MISC-0315-HANDLES-SUPPORTED-SOURCE-REQUEST-2B0A68` | PASS | Handles supported source/request inputs and rejects unsupported ones. | The calendar adapter accepted a supported create request against a fake gog executable and returned the fixture event ID, while missing required fields and an unknown action were rejected non-zero. |
| `MISC-0317-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5022AD` | PASS | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | With an empty PATH the calendar adapter returned non-zero structured JSON stating gog command not found; an unknown provider likewise returned non-zero typed JSON and no event data. |
| `MISC-0322-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-E5C821` | PASS | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | The mapped browser skill's structured setup.json explicitly reports setupComplete=false and names Chrome, API-key, dependency, and browser-command prerequisites as unavailable instead of reporting synthetic browser output. |
| `MISC-0327-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-AF98BB` | PASS | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | The Obsidian wiki status entrypoint ran under an isolated empty HOME and emitted valid JSON with configured=false, empty repo/vault paths, and all skill-install flags false, without creating fake integration evidence. |
| `MISC-0330-HANDLES-SUPPORTED-SOURCE-REQUEST-717B2C` | PASS | Handles supported source/request inputs and rejects unsupported ones. | The RAGFlow CLI accepted a supported search request and emitted its typed offline result; argparse rejected an unsupported source choice with a non-zero status. |
| `MISC-0332-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-83BF1C` | PASS | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | With no config, base URL, key, dataset, or network, RAGFlow returned exit 2 and structured JSON with hits=[] plus ragflow:missing_base_url, proving it does not fabricate retrievals. |
| `MISC-0335-HANDLES-SUPPORTED-SOURCE-REQUEST-24C223` | PASS | Handles supported source/request inputs and rejects unsupported ones. | The Codex operator accepted a non-empty dispatch through a fake isolated codex executable and wrote the exact result artifact; an empty dispatch was rejected with exit 64 and an explicit reason. |
| `MISC-0337-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-2C2F4E` | FAIL | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | When the Codex CLI is absent, codex_operator.py raises an uncaught FileNotFoundError traceback and writes no typed failed/inconclusive status artifact. |
| `MISC-0347-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-89ACF0` | FAIL | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | browser-automation/setup.json truthfully reports every prerequisite unavailable, but the mapped skill package ships no executable runtime file that can turn that state into a structured invocation failure; it is documentation-only. |
| `MISC-0375-HANDLES-SUPPORTED-SOURCE-REQUEST-5089BE` | PASS | Handles supported source/request inputs and rejects unsupported ones. | The locked Gemini Deep Research ResearchRequest model accepted and round-tripped a supported user request, while rejecting blank text and an unsupported source through typed InvalidResearchRequest exceptions without provider access. |
| `MISC-0300-HANDLES-SUPPORTED-SOURCE-REQUEST-1A39A8` | SKIPPED_NA | Handles supported source/request inputs and rejects unsupported ones. | The taxonomy names skills-md, but the locked checkout has no skills-md directory or executable and the prior map incorrectly points this row to skills/solar/SKILL.md; there is no such product surface to execute. |
| `MISC-0302-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-6ED8E4` | SKIPPED_NA | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | The taxonomy names skills-md, but the locked checkout has no skills-md provider boundary; the prior skills/solar mapping is stale and this unavailable-provider atom is not applicable to a real shipped surface. |

### All confirmed FAIL rows (112)

| Feature ID | Part | Atomic feature | Defect/evidence |
|---|---|---|---|
| `WF-0007-CREATES-SPRINT-INTAKE-ARTIFACTS-92818B` | workflow | Creates sprint/intake artifacts with stable IDs and raw request preserved. | D-020 |
| `WF-0008-INTAKE-ROUTES-GRAPH-SPRINT-45CDE3` | workflow | Intake routes to graph/sprint queue without hidden mutation. | evidence/codex-not-run-phase/junit/codex-nr-0230.xml |
| `WF-0017-UPDATES-MODEL-CONFIG-ONLY-55333B` | workflow | Updates model config only when --apply is supplied. | D-032 |
| `WF-0018-INVALID-MODEL-REJECTED-ALLOWED-14FEE5` | workflow | Invalid model rejected with allowed options. | D-032 |
| `WF-0021-FAILURE-PRESERVES-LOGS-STATUS-D58946` | workflow | Failure preserves logs and status without orphaned state. | D-002 |
| `WF-0027-FAILURE-LEAVES-SOURCE-DATA-40F13A` | workflow | Failure leaves source data intact and reports partial state. | evidence/codex-not-run-phase/audit-tests/remaining-safe-atomic-contracts-final2.junit.xml |
| `WF-0041-FAILS-REPORTS-MISSING-STATE-38916C` | workflow | Fails or reports missing state without creating hidden success artifacts. | D-025 |
| `WF-0057-EXECUTION-READY-ONLY-WHEN-C66D5E` | workflow | Execution-ready only when handoff, approval, and artifact plan are complete. | D-003 |
| `WF-0067-NO-CODE-REMOTE-EXECUTION-9BB20A` | workflow | No code/remote execution occurs without approval/allowlist/runtime evidence. | D-003 |
| `WF-0069-MODE-SPECIFIC-COMMAND-APPROVAL-E7B0E0` | workflow | Mode-specific command/approval path is explicit and does not confuse local with remote proof. | D-003 |
| `WF-0070-MISSING-CONTRACT-YIELDS-INCONCLUSIVE-3260D2` | workflow | Missing contract yields inconclusive access request; approved contract enables allowed command. | D-003 |
| `WF-0078-CANDIDATE-ARTIFACT-INCLUDES-HYPOTHESIS-3B1F71` | workflow | Candidate artifact includes hypothesis, approach, novelty, priority, provenance. | D-003; D-006 |
| `WF-0086-SOURCE-FULLY-REGISTERED-ONLY-1F8E0A` | workflow | Source is fully registered only when memory/graph/index/context evidence is present. | evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml |
| `WF-0091-TARGET-RESOLVED-REJECTED-ACTIONABLE-B20BDE` | workflow | Target is resolved or rejected with actionable ambiguity. | evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml |
| `WF-0105-UNCONFIRMED-CITATIONS-EXPLICIT-BLOCKERS-A7B45F` | workflow | Unconfirmed citations are explicit blockers, not hidden warnings. | evidence/codex-not-run-phase/audit-tests/remaining-safe-atomic-contracts-final2.junit.xml |
| `WF-0135-REPORTS-MISSING-PRESENT-CONFIG-9BF2D6` | workflow | Reports missing/present config without writing secrets. | D-007 |
| `WF-0136-NONINTERACTIVE-MISSING-VALUES-PRODUCE-D7413D` | workflow | Noninteractive missing values produce exact remedy. | D-007 |
| `WF-0137-WRITES-OCCUR-ONLY-EXPLICIT-2CB04C` | workflow | Writes occur only with explicit values and approval. | D-007 |
| `WF-0138-SETUP-READINESS-DISTINGUISHES-DETERMINISTIC-1BF3FE` | workflow | Setup readiness distinguishes deterministic checks from live provider proof. | D-007 |
| `WF-0139-SELECTS-RELEVANT-PAPERS-CONCEPTS-7B56D9` | workflow | Selects relevant papers/concepts and reports too-few/none cases. | phase4_pytest_matrix_installed_home |
| `WF-0151-VALID-PDF-SOURCE-PREPARATION-97CC16` | workflow | Valid PDF/source preparation emits research_paper.v1 with provenance; malformed/missing PDF fails or is inconclusive without false completion. | D-008 |
| `WF-0154-NETWORK-SOURCE-REQUIRES-PROVIDER-D4104F` | workflow | Network source requires provider/approval boundary and records fetch/provenance status. | phase4_autosci_plugin_pytest_final |
| `WF-0156-SOURCE-FULLY-REGISTERED-ONLY-748617` | workflow | Source is fully registered only when memory/graph/index/context evidence is present. | D-008 |
| `WF-0176-REPORTS-INCOMPLETE-METHOD-EVIDENCE-E24804` | workflow | Reports incomplete method evidence without inventing procedure. | D-031 |
| `WF-0177-GENERATED-CANDIDATES-CITE-SOURCE-FA4851` | workflow | Generated candidates cite source evidence and gap links. | D-031 |
| `WF-0233-LOADS-BOUNDED-PILOT-SPEC-059100` | workflow | Loads bounded pilot spec and rejects missing datasets/config. | evidence/codex-not-run-phase/audit-tests/remaining-safe-atomic-contracts-final2.junit.xml |
| `WF-0234-GENERATED-PILOT-CODE-RECORDED-49FB18` | workflow | Generated pilot code is recorded with command/log paths before execution. | evidence/codex-not-run-phase/audit-tests/remaining-safe-atomic-contracts-final2.junit.xml |
| `WF-0242-UNCONFIRMED-CITATIONS-EXPLICIT-BLOCKERS-5D6C04` | workflow | Unconfirmed citations are explicit blockers, not hidden warnings. | evidence/codex-not-run-phase/audit-tests/remaining-safe-atomic-contracts-final2.junit.xml |
| `WF-0247-ARCHIVAL-WRITEBACK-EXPLICIT-APPROVED-0CA46A` | workflow | Archival writeback is explicit and approved when mutating wiki. | D-024 |
| `WF-0260-REPORTS-MISSING-PRESENT-CONFIG-234895` | workflow | Reports missing/present config without writing secrets. | evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml |
| `WF-0261-NONINTERACTIVE-MISSING-VALUES-PRODUCE-0C96FF` | workflow | Noninteractive missing values produce exact remedy. | evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml |
| `WF-0264-MISSING-INVALID-SCOPE-REJECTED-E14DB0` | workflow | Missing/invalid scope is rejected; dry-run plan lists exact mutations. | D-025 |
| `WF-0265-PLAN-GENERATED-WITHOUT-MUTATION-38B119` | workflow | Plan is generated without mutation and is not research success evidence. | D-025 |
| `WF-0276-REPORTS-DETERMINISTIC-STRUCTURAL-ERRORS-65ACD8` | workflow | Reports deterministic structural errors by severity. | D-027 |
| `WF-0277-DRY-RUN-PROPOSES-FIXES-6FC1FB` | workflow | Dry-run proposes fixes without mutation; fix mode mutates only explicit fixable items. | D-025 |
| `WF-0279-FAILS-REPORTS-MISSING-STATE-8DE992` | workflow | Fails or reports missing state without creating hidden success artifacts. | D-025 |
| `WF-0344-NODE-MAPPED-CORRECT-LOGICAL-9D8FAC` | workflow | Node is mapped to the correct logical operator/capabilities for run or collect experiment evidence. | D-003 |
| `WF-0345-NODE-EMITS-VALIDATES-EXPERIMENT-284628` | workflow | Node emits or validates experiment_result.v1 with provenance, status, artifacts, and limitations. | D-003 |
| `WF-0346-GATE-ACCEPTS-VALID-EVIDENCE-83279C` | workflow | Gate accepts valid evidence and rejects or marks failed/inconclusive evidence without overclaiming. | D-003 |
| `WF-0347-COMPLETED-EVIDENCE-REUSED-FAILED-86886E` | workflow | Completed evidence is reused; failed/inconclusive/missing artifacts rerun or stay pending as configured. | D-003 |
| `WF-0348-NODE-RUNS-ONLY-WHEN-92AD28` | workflow | Node runs only when dependencies are passed or records pending/inconclusive with missing parents. | D-003 |
| `WF-0389-EXECUTES-PLANS-BENCHMARK-ISOLATED-A65F7D` | workflow | Executes or plans benchmark with isolated artifacts and no unintended repo mutation. | phase4_shell_test_sweep_installed_home |
| `WF-0391-FAILURE-EXPLICIT-PRESERVES-LOGS-9009F3` | workflow | Failure is explicit and preserves logs/artifacts. | evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml |
| `WF-0397-EXECUTES-PLANS-BENCHMARK-ISOLATED-62E9AD` | workflow | Executes or plans benchmark with isolated artifacts and no unintended repo mutation. | phase4_shell_test_sweep_installed_home |
| `WF-0405-EXECUTES-PLANS-BENCHMARK-ISOLATED-31810F` | workflow | Executes or plans benchmark with isolated artifacts and no unintended repo mutation. | evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml |
| `WF-0417-EXECUTES-PLANS-BENCHMARK-ISOLATED-5B79C9` | workflow | Executes or plans benchmark with isolated artifacts and no unintended repo mutation. | phase4_shell_test_sweep_installed_home |
| `WF-0421-RUNS-RECORDS-BROWSER-AUTOMATION-D5E6FF` | workflow | Runs/records browser automation or reports unavailable browser deterministically. | evidence/codex-not-run-phase/junit/codex-nr-0141.xml |
| `WF-0426-CAPTURED-OUTPUT-HAS-SOURCE-6F503B` | workflow | Captured output has source URL, timestamp, and artifacts. | D-030 |
| `WF-0434-JOB-FAILS-FAILING-UNDERLYING-EE12FB` | workflow | Job fails on failing underlying command and uploads useful logs/artifacts. | evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml |
| `WF-0435-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-B115CE` | workflow | Expected artifacts or status summaries are produced on success/failure. | evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml |
| `WF-0438-JOB-FAILS-FAILING-UNDERLYING-DD0F6A` | workflow | Job fails on failing underlying command and uploads useful logs/artifacts. | evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml |
| `WF-0439-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-0F1251` | workflow | Expected artifacts or status summaries are produced on success/failure. | evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml |
| `WF-0442-JOB-FAILS-FAILING-UNDERLYING-74BC93` | workflow | Job fails on failing underlying command and uploads useful logs/artifacts. | evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml |
| `WF-0443-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-9BB2AA` | workflow | Expected artifacts or status summaries are produced on success/failure. | evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml |
| `WF-0561-QUEUES-DOCUMENTS-IDEMPOTENTLY-RECORDS-639219` | workflow | Queues documents idempotently and records status/watermarks. | evidence/codex-not-run-phase/audit-tests/knowledge-remaining-direct-contracts-final.junit.xml |
| `WF-0573-SEPARATES-BLOCKERS-RECOMMENDATIONS-EF2559` | workflow | Separates blockers from recommendations. | D-027 |
| `WF-0574-DOES-NOT-MUTATE-UNLESS-438A74` | workflow | Does not mutate unless explicit repair mode exists and is approved. | D-027 |
| `WF-0576-SEPARATES-BLOCKERS-RECOMMENDATIONS-694C05` | workflow | Separates blockers from recommendations. | D-027 |
| `WF-0577-DOES-NOT-MUTATE-UNLESS-A2EB53` | workflow | Does not mutate unless explicit repair mode exists and is approved. | D-027 |
| `WF-0579-SEPARATES-BLOCKERS-RECOMMENDATIONS-5830E3` | workflow | Separates blockers from recommendations. | D-027 |
| `WF-0580-DOES-NOT-MUTATE-UNLESS-10CFFA` | workflow | Does not mutate unless explicit repair mode exists and is approved. | D-027 |
| `WF-0590-IDENTIFIES-CHANGED-UNINDEXED-DOCUMENTS-3300DA` | workflow | Identifies changed/unindexed documents deterministically. | phase4_shell_test_sweep_installed_home |
| `WF-0591-UPDATES-INDEX-STATES-WATERMARKS-F53A6D` | workflow | Updates index states and watermarks idempotently. | phase4_shell_test_sweep_installed_home |
| `WF-0596-IDENTIFIES-CHANGED-UNINDEXED-DOCUMENTS-2CB69F` | workflow | Identifies changed/unindexed documents deterministically. | phase4_shell_test_sweep_installed_home |
| `WF-0597-UPDATES-INDEX-STATES-WATERMARKS-3E8B89` | workflow | Updates index states and watermarks idempotently. | phase4_shell_test_sweep_installed_home |
| `WF-0599-IDENTIFIES-CHANGED-UNINDEXED-DOCUMENTS-9CF653` | workflow | Identifies changed/unindexed documents deterministically. | phase4_shell_test_sweep_installed_home |
| `WF-0600-UPDATES-INDEX-STATES-WATERMARKS-38BEA7` | workflow | Updates index states and watermarks idempotently. | phase4_shell_test_sweep_installed_home |
| `WF-0602-IDENTIFIES-CHANGED-UNINDEXED-DOCUMENTS-509010` | workflow | Identifies changed/unindexed documents deterministically. | phase4_shell_test_sweep_installed_home |
| `WF-0603-UPDATES-INDEX-STATES-WATERMARKS-25413E` | workflow | Updates index states and watermarks idempotently. | phase4_shell_test_sweep_installed_home |
| `WF-0604-QUARANTINES-REPORTS-BAD-ITEMS-1161B1` | workflow | Quarantines/reports bad items without advancing invalid state. | phase4_shell_test_sweep_installed_home |
| `WF-0627-OUTPUT-INCLUDES-SOURCE-REFS-745B54` | workflow | Output includes source refs, query/params, timestamps, and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `WF-0635-OUTPUT-INCLUDES-SOURCE-REFS-3CC0C2` | workflow | Output includes source refs, query/params, timestamps, and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `WF-0639-OUTPUT-INCLUDES-SOURCE-REFS-30B46B` | workflow | Output includes source refs, query/params, timestamps, and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `WF-0643-OUTPUT-INCLUDES-SOURCE-REFS-B35187` | workflow | Output includes source refs, query/params, timestamps, and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `WF-0647-OUTPUT-INCLUDES-SOURCE-REFS-C7E02C` | workflow | Output includes source refs, query/params, timestamps, and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `WF-0651-OUTPUT-INCLUDES-SOURCE-REFS-79555B` | workflow | Output includes source refs, query/params, timestamps, and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `WF-0652-ERRORS-PROPAGATED-FAILED-INCONCLUSIVE-671553` | workflow | Errors are propagated as failed/inconclusive evidence, not hidden success. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `FD-0148-OPERATOR-DECLARES-MATCHES-REQUIRED-935809` | foundations | Operator declares and matches required capability IDs. | D-022 |
| `FD-0202-OPERATOR-STATUS-MATCHES-SIDE-74D02E` | foundations | Operator status matches side-effect and provider boundaries. | D-002 |
| `FD-0520-EVIDENCE-MARKED-BEST-EFFORT-6F7221` | foundations | Evidence is marked best-effort and must not be claimed as strict full parity. | phase4_autosci_plugin_pytest_final |
| `FD-0575-PERFORMS-DOCUMENTED-LIST-QUERY-244AD1` | foundations | Performs documented list/query/score/sync/infer action deterministically. | evidence/codex-not-run-phase/audit-tests/capability-plane-direct-contracts-final.junit.xml |
| `FD-0579-PERFORMS-DOCUMENTED-LIST-QUERY-42343E` | foundations | Performs documented list/query/score/sync/infer action deterministically. | evidence/codex-not-run-phase/audit-tests/capability-plane-direct-contracts-final.junit.xml |
| `FD-0581-DUPLICATE-STALE-ENTRIES-DO-DD1FAB` | foundations | Duplicate or stale entries do not corrupt registry and are reported. | evidence/codex-not-run-phase/audit-tests/capability-plane-direct-contracts-final.junit.xml; tmp/pytest-capability-final2/test_capability_activation_pro0/home/.solar/harness/reports/capability-activation-evidence/latest/activation-proof.json |
| `FD-0583-PERFORMS-DOCUMENTED-LIST-QUERY-5F929C` | foundations | Performs documented list/query/score/sync/infer action deterministically. | evidence/codex-not-run-phase/audit-tests/capability-plane-direct-contracts-final.junit.xml |
| `FD-0591-PERFORMS-DOCUMENTED-LIST-QUERY-4B7E0A` | foundations | Performs documented list/query/score/sync/infer action deterministically. | phase4_shell_test_sweep_installed_home |
| `FD-0594-LOADS-CAPABILITY-CONFIG-REGISTRY-5EF037` | foundations | Loads capability config/registry data and handles missing/invalid config. | evidence/codex-not-run-phase/audit-tests/remaining-safe-atomic-contracts-final2.junit.xml |
| `FD-0595-PERFORMS-DOCUMENTED-LIST-QUERY-ED4D7C` | foundations | Performs documented list/query/score/sync/infer action deterministically. | evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml |
| `FD-0597-DUPLICATE-STALE-ENTRIES-DO-3E6217` | foundations | Duplicate or stale entries do not corrupt registry and are reported. | evidence/codex-not-run-phase/audit-tests/benchmark-capability-direct-contracts.junit.xml |
| `FD-0661-WRITES-EVIDENCE-PAYLOADS-SIDECARS-AB5066` | foundations | Writes evidence payloads, sidecars, and JSONL without path leakage or duplicates. | D-007 |
| `MISC-0077-COMMAND-PERFORMS-DOCUMENTED-BEHAVIOR-0537B7` | misc. | Command performs documented behavior with expected stdout/JSON/status. | evidence/codex-not-run-phase/audit-tests/cli-direct-contracts-remediation-final.junit.xml |
| `MISC-0235-PLATFORM-SPECIFIC-PATH-RUNS-7537D7` | misc. | Platform-specific path runs or reports unsupported/experimental status clearly. | phase4_shell_test_sweep_installed_home |
| `MISC-0248-FAILURES-STOP-CLEANLY-ACTIONABLE-853305` | misc. | Failures stop cleanly with actionable remedy and no partial hidden success. | evidence/codex-not-run-phase/audit-tests/pipx-wrapper-direct-contracts.junit.xml |
| `MISC-0279-ACCEPTED-FLAGS-ENV-CONFIG-F0A876` | misc. | Accepted flags/env/config are parsed and invalid/missing required values emit exact remedy. | evidence/codex-not-run-phase/release-package/dry-run.stderr.txt |
| `MISC-0282-DRY-RUN-WRITES-NOTHING-898484` | misc. | Dry-run writes nothing; repeated operations are idempotent or report drift safely. | evidence/codex-not-run-phase/release-package/dry-run.stderr.txt |
| `MISC-0288-FAILURES-STOP-CLEANLY-ACTIONABLE-A78A41` | misc. | Failures stop cleanly with actionable remedy and no partial hidden success. | evidence/codex-not-run-phase/audit-tests/pipx-wrapper-direct-contracts.junit.xml |
| `MISC-0305-HANDLES-SUPPORTED-SOURCE-REQUEST-0F0924` | misc. | Handles supported source/request inputs and rejects unsupported ones. | D-028 |
| `MISC-0307-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-5310ED` | misc. | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | D-028 |
| `MISC-0308-ANY-EXTERNAL-WRITE-BROWSER-F66FD9` | misc. | Any external write/browser/send action is approval-gated where applicable. | D-024 |
| `MISC-0309-INTEGRATION-SKILL-DISCOVERABLE-VALIDATES-0D3FAC` | misc. | Integration/skill is discoverable and validates required config/credentials. | evidence/codex-not-run-phase/audit-tests/integration-discovery-direct-contracts.junit.xml |
| `MISC-0313-ANY-EXTERNAL-WRITE-BROWSER-AEAD47` | misc. | Any external write/browser/send action is approval-gated where applicable. | D-024 |
| `MISC-0318-ANY-EXTERNAL-WRITE-BROWSER-DD521D` | misc. | Any external write/browser/send action is approval-gated where applicable. | D-024 |
| `MISC-0325-HANDLES-SUPPORTED-SOURCE-REQUEST-788570` | misc. | Handles supported source/request inputs and rejects unsupported ones. | evidence/codex-not-run-phase/audit-tests/integration-discovery-direct-contracts.junit.xml |
| `MISC-0337-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-2C2F4E` | misc. | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | D-029 |
| `MISC-0347-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-89ACF0` | misc. | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | D-028 |
| `MISC-0348-ANY-EXTERNAL-WRITE-BROWSER-417B43` | misc. | Any external write/browser/send action is approval-gated where applicable. | D-024 |
| `MISC-0370-HANDLES-SUPPORTED-SOURCE-REQUEST-DB51B6` | misc. | Handles supported source/request inputs and rejects unsupported ones. | evidence/codex-not-run-phase/audit-tests/gemini-integration-direct-contracts.junit.xml |
| `MISC-0371-OUTPUT-INCLUDES-SOURCE-PROVIDER-084CCC` | misc. | Output includes source/provider provenance and limitations. | evidence/codex-not-run-phase/audit-tests/gemini-integration-direct-contracts.junit.xml |
| `MISC-0391-OUTPUT-INCLUDES-SOURCE-PROVIDER-88DD5E` | misc. | Output includes source/provider provenance and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `MISC-0392-UNAVAILABLE-EXTERNAL-PROVIDER-YIELDS-BAAD93` | misc. | Unavailable external provider yields explicit failed/inconclusive state, not fake data. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `MISC-0396-OUTPUT-INCLUDES-SOURCE-PROVIDER-A63A22` | misc. | Output includes source/provider provenance and limitations. | evidence/codex-not-run-phase/audit-tests/remediation-direct-contracts-final.junit.xml |
| `MISC-0543-NO-OP-PATH-EXITS-DF3AF2` | misc. | No-op path exits cleanly without side effects. | phase4_pytest_matrix_installed_home |
| `MISC-0618-NO-OP-PATH-EXITS-B683BB` | misc. | No-op path exits cleanly without side effects. | phase4_pytest_matrix_installed_home |

## 9. Failures and defects

| Severity | Defect groups | Summary |
|---|---:|---|
| P0 | 0 | No destructive/credential/remote/data-loss event was observed during isolated execution. |
| P1 | 5 | Four original core failures plus the grouped approval-boundary defect D-024. |
| P2 | 24 | Core/important contract drift, missing executable integrations, provider evidence, browser/Codex failure handling, packaging, and semantic gaps. |
| P3 | 9 | CI/installer diagnostics, taxonomy portability, broad discovery/layout, status/documentation gaps. |
| P4 | 0 | None recorded. |

See `defects.md` and `evidence/codex-not-run-phase/codex-not-run-defects.md`. Feature FAIL count and defect-group count intentionally differ because multiple features share root causes.

## 10. Gated, skipped, inconclusive, and live-provider-only surfaces

The selected former-NOT_RUN subset has 0 remaining inconclusive rows. Its 105 SKIPPED_ENV rows still need real platform/toolchain/provider/runtime evidence; supplying one API key would not remove every SKIPPED_ENV because some require Windows/Linux, Playwright/renderer binaries, local corpora, or provider-specific runtimes.

The overall workbook still has 381 INCONCLUSIVE_EXPECTED rows that predated the 1,435-row NOT_RUN follow-up and were not silently promoted. AutoSci remains fixture/local evidence only. Optional live requirements and authorization boundaries are in `gated-and-live-test-plan.md`.

## 11. Missing tests and recommended additions

Current validated mapping classes: direct 249, gated 73, indirect 596, manual-only 16, missing 966, not-applicable 2, partial 215.

Audit-only direct contracts should be promoted into tracked regression tests. Highest priorities are approval enforcement for survey/integration writes, structured missing-Codex handling, executable office/browser integration boundaries, unified social capture provenance/artifacts, and method/gap semantic regressions. `missing-test-plan.csv` contains the row-level plan.

## 12. Final readiness verdict

**NOT READY.** The follow-up successfully removed silent `NOT_RUN` and selected-scope `INCONCLUSIVE_EXPECTED` blockers, but it also confirmed 72 failures in that selected subset and 112 failures overall. Full success requires fixing and directly retesting P1/P2 defects, resolving or accepting the 381 pre-existing inconclusive rows, and separately authorizing any live provider/platform phase. Fixture evidence must not be reported as live AutoSci parity.
