# Legacy Fix Integration and Correctness Repair

Date: 2026-08-07

Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

Branch: `codex/legacy-fix-integration-repair`

Worktree: `C:\Users\j50058254\Desktop\Github repo\.legacy-fix-worktrees\legacy-fix-integration`

## Inputs and integration order

The requested commits were cherry-picked in order, without an `ours` or
`theirs` whole-file resolution:

1. R1 `8b8acb7397496e62b48e5b781e933339445774b0`
2. R2 `3bc9f20e2b675f9285b7720fd24cdaf3aafb5997`
3. R3 `c88680e49257cfd02fd520c4324cdd72a4f59fdd`
4. R4 `182df830eb50e88e4e84f48fdda3822ce1b1afb1`
5. R5 committed portion `96a9097bd23c247011ed8d042fc153a77923143d`
6. R5 supplemental `dead34b7e1f88bdc42fed68f3d80568cccfdd1e7`
7. R6 `9a5e1390f2291bcaf5c1cbcf5a9f1bf85aed92e8`
8. R7 `34f5cb017c68690bd6930eaaa1f3d895005ad091`
9. R8 `2a7aeb9af6bd83db7c149be95a303100fe9dd307`

R5's 17 tracked dirty files were reviewed before commit. They were all within
the assigned Windows/WSL installer, sandbox-home, J01, and status scope.
Untracked `outputs/` was not included. The R5 tracked worktree was clean after
the supplemental commit.

## Conflicts resolved

Two textual conflicts were resolved paragraph by paragraph:

- `harness/lib/research_orchestration/runtime.py`: retained R1 prompt,
  requirements, readiness, and JSON contract behavior; retained R3 lifecycle,
  resume, exact-checkout, and Windows-safe evidence behavior. Non-checkout
  roots fail closed rather than inheriting a parent repository identity.
- `tests/journeys/phase22/code/journey_runner.py`: retained R2 Windows
  sidecar/path behavior and R4 cache/copytree portability. Cache directories
  are always ignored; plugin tests are ignored only in the plugin-directory
  fallback copy.

No conflict occurred in `autosci_bridge.py` or `bin/solar`; their R2/R3/R4 and
R5/R6 semantics composed cleanly and were then covered by combined tests.

## Correctness repairs after integration

### Benchmark result semantics

- Preserved public mock compatibility by accepting the optional agent at the
  doctor boundary while running per-agent readiness from `run()`.
- Kept process completion separate from target quality:
  `benchmark_execution_verdict=PASS`, low target quality
  `target_quality_verdict=FAIL`, and no real run
  `target_quality_verdict=NOT_TESTED`.
- Updated library/tool schemas, JSON, Markdown, and plain CLI output together.

### Status, platform, and privacy lifecycle

- `/status` exceptions return `ok=false`, `status=degraded`, and stable code
  `status_payload_unavailable`; exception text, paths, and secrets are not
  returned and the server remains alive.
- Added a production-route regression test.
- Repaired Windows `solar backup`/`restore` so a `C:\...` path is converted for
  Git Bash `tar`; restored compatible top-level `status` and `ok` fields.
- J24 changed from a real backup failure to a passing privacy lifecycle.

### Token channels

- Session, logout, profile, privacy export, and privacy delete read the token
  from stdin by default; `--token-stdin` is explicit and `--token` remains only
  as a documented deprecated compatibility path.
- Tests assert the raw token is absent from subprocess argv, stdout/stderr,
  identity stores, and exported artifacts. Tokens are not placed in an
  environment artifact. Authentication errors remain non-enumerating.

### Advanced optimizer product binding

- Registered `autosci-advanced-ai4rnd-worker` in the physical operator
  registry and exposed `solar advanced --envelope FILE|-`.
- Product-entrypoint subprocess tests execute the Bayesian reference optimizer
  and CPU-safe SFT adapter without importing `execute_operator` as the proof.
- TaskGraph/evidence/model/artifact identifiers remain in the output. Other
  algorithms continue to return explicit `unsupported`.

### Repository governance and sandbox truthfulness

- Removed pre-existing unresolved merge markers from
  `skills/obsidian-daily/SKILL.md` while retaining its upstream metadata.
- Wired safe staging, secret scan, filename validation, and their unit tests
  into `.github/workflows/solar-ci.yml`.
- Secret scanning reads tracked files, exact staged index blobs, and untracked
  commit candidates. Output contains rule/path/line only.
- Forty-four pre-existing fixture/example lines are reviewed through
  `.secret-scan-allowlist`, pinned by rule, path, and SHA-256 of the exact line.
  Any content change fails closed and is scanned again; there is no directory
  exemption.
- Fixed the Windows registry-root parent index. The sandbox test launches a
  real subprocess and verifies allowed-write success and outside-write denial
  where an OS sandbox is available. Native Windows remains an explicit S01
  skip; transport metadata is not treated as OS enforcement.

### Upstream parity and scientific claim scope

- Preserved the captured parity fixture and added configurable
  `harness/tools/autosci_upstream_parity.py`. It passes the same prompt to the
  Solar production bridge and a configured upstream JSON-argv command, then
  compares intent, workflow stages, input type, language, deliverable type,
  and required evidence. Missing/unavailable upstream returns `PARTIAL` with
  exit 2, never PASS.
- No executable repository upstream AutoSci entrypoint was available in this
  environment, so A09/T06 remain `PARTIAL`.
- Claim verification now compares structured population, environment, time
  range, input domain, metric, and confidence/uncertainty scope. English and
  Chinese broad-language regexes are guardrails only. Tests cover bounded
  support, universal overclaim, insufficient evidence, contradiction, and
  Chinese terms including `所有`, `任何环境`, `始终`, and `百分之百`.

### Live journey evidence

- J05 final product status: `ENVIRONMENT_BLOCKED`. Both provider-backed
  discovery calls timed out after 60 seconds and produced an incomplete
  provider boundary; this is not recorded as product FAIL. Evidence:
  `outputs/phase22-real-journeys/p22j05-20260807T050859Z-5500/journey-result.json`.
- J20 final product status: `ENVIRONMENT_BLOCKED`. Discover used three bounded
  attempts with delays 0/2/5 seconds and ended `provider_incomplete`; survey
  and research each ran once and ended `provider_inconclusive`. Evidence:
  `outputs/phase22-real-journeys/p22-j20-20260807T051219Z/journey-result.json`.
- Provider environment variables were inherited/injected only into test
  processes and were never printed, copied to evidence, or committed.
- Writer/reviewer independence remains limited: reloaded artifact hashes and a
  distinct invocation context are proven, but no separate live reviewer
  provider completed in this run. Metadata alone is not claimed as proof.

## Test execution

Every pytest command used the repository `.venv`, an isolated basetemp, and an
isolated cache. Logs were not redirected into basetemp.

| Scope | Exact selector summary | Exit | Outcome |
|---|---|---:|---|
| R1 | `pytest test_research_control_plane_contract.py test_research_intent.py test_research_workflow_selection.py test_research_production_routing.py test_research_production_runtime.py test_autosci_intake_contract.py` | 0 | 65 passed |
| R3 core | `pytest test_phase5_lifecycle_recovery.py test_research_runtime_lease.py test_j21_experiment_build_handoff.py` | 0 | 30 passed |
| R2 operators | `pytest test_research_synthesis_operators.py test_action_delivery_operators.py test_paper_prepare.py test_source_cli_tools.py` | 0 | 102 passed |
| R4 runtime/benchmark | `pytest test_task_graph_runtime_planes.py test_graph_scheduler_external_deps.py test_claim_verdict_gate.py test_benchmark_report_schema.py test_terminal_bench_adapter.py test_platform_workflow_benchmark.py` | 0 | 38 passed, 15 warnings |
| R4 journeys | `pytest test_j03_platform_benchmark.py test_j08_claim_verification.py test_j09_report_delivery.py test_j22_evidence_review_followup.py` | 0 | 4 passed |
| R5/R6/R7 direct | `pytest` status-route group, local identity privacy/security, advanced operator unit and product entrypoint | 0 | 24 passed |
| R7 regression | `pytest` GEPA integration, TaskGraph state, model registry aliases, logical router | 0 | 170 passed, 24 warnings |
| R8 | `pytest test-safe-staging.py test-secret-scan.py test-windows-filenames.py test_sandbox_fallback_matrix.py test_research_transport_coverage.py` | 0 | 127 passed, 1 skipped |
| R2/R3/R5/R6 journeys | J04, J06, J07, J01, J15, J18, J24 | 1 | 5 passed, 1 skipped, J24 failed before repair |
| J24 repair rerun | `pytest test_j24_privacy_lifecycle.py` | 0 | 1 passed |
| R3 combined | J07, J21, state store, result validation, orchestrator, production runtime | 0 | 121 passed |
| Status final | four status-server files | 0 | 14 passed |
| J05/J20 live diagnostics | two combined runs before evidence/path repairs | 1 | 2 failed each; causes repaired |
| J05/J20 live classification | combined final classification run | 1 | J05 skipped as `ENVIRONMENT_BLOCKED`; J20 classification defect remained |
| J20 final | `pytest test_j20_research_synthesis.py -m live_provider` | 0 | 1 passed; product status `ENVIRONMENT_BLOCKED` |

Final successful pytest-command totals are non-deduplicated because the
combined regression intentionally repeats high-risk selectors: 697 passed,
0 failed, 1 skipped. Separately, J05 has one accepted environment-blocked skip
and J18 has one explicit serial-TMUX authorization skip.

Additional executable checks:

- `bash harness/tests/installer/test-s1-installer.sh`: exit 0, 38/38 checks.
- `bash harness/tests/installer/test-tvs-doctor.sh`: exit 0, test skipped because
  `/home/james/TVS` is absent.
- `bash tests/test-repo-hygiene.sh`: exit 0.
- PyYAML parse of `.github/workflows/solar-ci.yml`: exit 0.
- `scripts/check-windows-filenames.py`: exit 0; final staged-tree rerun scanned
  4,444 files.
- `scripts/check-safe-staging.py`: exit 0.
- `scripts/check-secret-scan.py`: exit 0, 4,444 tracked/staged/untracked
  candidates scanned, no secrets found.

## Open items and source gaps

The requested canonical ledger
`docs/integrations/autosci/legacy-issue-closure-ledger.md` and issue map
`.codex-tmp/legacy-issue-audit-20260806/github-issue-map.json` do not exist in
the baseline, current worktrees, or reachable Git history. This repair does not
invent mappings and does not modify the workbook, brief report, ledger, or
GitHub Issues.

- Legacy IDs fully fixed with explicit local evidence: G01, G04, G05, G06,
  S02, S05.
- Legacy IDs still partial/open: A09 and T06 (`PARTIAL`, real upstream not
  executable here); S01 (native Windows OS-level sandbox enforcement not
  available).
- Other Legacy ID closure cannot be asserted without the missing canonical
  ledger/map.
- L2 fully fixed: not asserted without the missing canonical closure mapping.
- L2 partial/open/not available: `Workflow :: Search Strategy Formation`,
  `Workflow :: Technical Signal Extraction`, and `Workflow :: Trend & Gap
  Analysis` remain provider-environment-blocked in J05/J20. Separate live
  reviewer-provider independence remains unproven. Non-reference R7 algorithms
  remain explicitly unsupported.

## Final quality gates

- `git diff --check`: passed before commit.
- Merge-marker scan: required after report creation and before commit.
- Secret scan: passed with no secret value output.
- Shared Phase 22 workbook, brief report, progress ledger, closure ledger, and
  GitHub Issues were not modified.
- The integration branch is not pushed. Final commit and clean post-commit
  status are recorded in the ignored result JSON and final delivery response.
