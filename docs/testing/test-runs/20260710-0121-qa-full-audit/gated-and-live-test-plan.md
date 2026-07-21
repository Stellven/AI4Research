# Gated and Live Test Plan

## Audit boundary

This first audit used static inspection, local fixtures, isolated install paths, and loopback-only deterministic execution. It did **not** authorize provider/network calls, browser-profile access, email, remote machines, GitHub mutation, release publishing, credential writes, or destructive state changes. Fixture proof is not live parity.

## Gated surfaces exercised locally

| Surface | First-audit result | Evidence | Interpretation |
|---|---|---|---|
| AutoSci policy/gate unit contracts | PASS for mapped passing cases; affected run/setup cases FAIL | `phase4_autosci_plugin_pytest_final` | Most policy decisions and approval artifacts validate. Approved local experiment execution is affected by D-003; setup by D-007. |
| Scientific lifecycle external nodes | BLOCKED_EXPECTED for unapproved nodes in passing cases | `phase4_scientific_evaluator_pytest_final` | Bounded fixture lifecycle keeps human/remote nodes visible and does not claim production parity. |
| Approved experiment continuation | FAIL | `phase4_scientific_experiment_inconclusive_repro` | A local allowlisted command in a spaced path is not propagated through the expected typed blocked/inconclusive lifecycle exit (D-003). |
| Evidence schemas | PASS for 21 positive/negative fixture pairs | `fixtures/evidence/schema-fixture-validation.json` | All 21 valid fixtures validate and all 21 empty-object negatives are rejected. This proves schema behavior only. |
| Isolated install and doctor | PASS with limitations | `phase5_install_isolated`, `phase5_doctor_json`, `phase5_validate_install_doctor_contract` | Kernel/harness/autosci installed into audit-only paths. Provider/Claude warnings are expected; dependency download/bootstrap was not tested. |
| Desktop browser gate | SKIPPED_ENV | `phase4_desktop_gate` | Playwright Chromium is not installed in the isolated cache. No download was attempted. |
| Desktop prepackage symlink guard | PASS | `phase4_desktop_prepackage` | Packaged harness contains no symlinks. |
| Data-plane canonical Knowledge/QMD/MinerU checks | SKIPPED_ENV | `phase4_pytest_matrix_installed_home` | Real Knowledge roots and indices were not provisioned. Raw pytest failures are not product verdicts. |

## Strict no-gate/no-provider execution phase

The follow-up phase validated candidate mappings before execution and selected 448 atomic features across 107 unique targets. It excluded 513 features whose atomic boundary mentioned approval/authorization gates, 94 requiring external environment/credentials, 73 already classified gated, 16 manual-only, 618 already missing, and 355 whose heuristic test candidates were not semantically relevant executable tests. All 448 selected features received terminal execution evidence. See `evidence/eligible-full-phase-v3/execution-report.md`.

No strict-phase passing result changes this live plan: local fixtures, mocks, loopback probes, and schema tests remain non-live evidence.

## Optional live phases requiring explicit approval

None of the following should be run as a continuation of this audit without a separate approval that names the credentials, target, allowed mutations, cleanup expectation, and evidence-retention location.

### Provider/runtime parity

- AutoSci `/research`, `/ask`, `/discover`, `/novelty`, `/review`, and Review-LLM boundaries with a real configured provider.
- Non-fixture end-to-end scientific lifecycle with durable scheduler resume, monitor/collect, claim verification, report, and publication evidence.
- Real embedding, QMD, MinerU, RAGFlow, NotebookLM, OpenAI-compatible, Anthropic/Claude, Zhipu/GLM, or other configured provider execution.
- Required approval: network destinations, provider identity, credential source, cost/budget cap, data-retention policy, and permission to write only to a named isolated project.
- Required evidence: provider request/response IDs or redacted hashes, usage/cost, runtime manifests, source provenance, typed limitations, and proof that no fixture was promoted to live.

### Browser and desktop

- Playwright/Chromium dashboard gate and screenshot assertions.
- Browser research, authenticated sites, browser profiles, or CAPTCHA/manual handoff.
- Required approval: browser binary download, profile path, allowed domains, whether authentication is permitted, and screenshot retention.
- Required evidence: browser/runtime version, asserted selectors, screenshots, network-domain list, and session cleanup proof.

### Remote execution and machines

- SSH/SCP, tmux on a remote host, experiment launch/monitor/collect, GPU/cluster/cloud runtime, or remote filesystem mutation.
- Required approval: exact host, account, command allowlist, working directory, resource/budget limits, and cleanup/termination rules.
- Required evidence: approval reference, before/after state, remote command transcript, exit status, logs, artifact hashes, and termination proof.

### Email, calendar, GitHub, and publishing

- Sending email, calendar changes, GitHub release/issue/PR mutation, package publish, tag creation, or artifact upload.
- Required approval: target recipients/repository/release, exact content/artifacts, dry-run review, and rollback/cancellation plan.
- Required evidence: typed approval, immutable target identifier, before/after state, provider response ID, and proof no additional recipients or assets were affected.

### Installer/bootstrap matrix

- Dependency downloads, clean-machine bootstrap, Linux/WSL2, unsigned/signed desktop builds, service installation, and uninstall/restore on non-ephemeral hosts.
- Required approval: disposable VM/container targets, package-manager/network use, service-manager use, and snapshot/rollback permission.
- Required evidence: fresh image identity, full dependency transcript, receipt, doctor JSON, filesystem diff, service state, uninstall/restore proof, and platform-specific logs.

## Required retest order after fixes

1. Fix and rerun P1 defects D-001 through D-004 in the same spaced path.
2. Rerun the authoritative Python, AutoSci, scientific, Bun, and shell suites in an isolated installed home.
3. Resolve P2 contract/API drift and verify feature-level evidence links.
4. Only then request a separate live phase. A live phase must retain fixture and live results as distinct evidence classes.

## Approved isolated gated follow-up

The user explicitly authorized bounded gated tests in this session. The authorization was applied only to disposable HOME, sprint, wiki/vault, raw-source, SQLite, fake provider, and fake CLI/browser fixtures. It did not authorize real email, Calendar.app mutation, browser profiles, provider calls, credentials, GitHub/release mutation, or remote execution.

- AutoSci approved gate selection: 8 passed.
- Control-plane approved plan verdict: 13 assertions passed.
- Obsidian integration safety: 3 passed.
- Approved atomic gate contracts: 2 passed, 1 failed (survey archive mutated without approval).
- Miscellaneous side-effect gate contracts: 1 passed, 4 failed.
- Semantic/manual-oracle contracts: 11 passed, 2 failed.
- Remaining app/browser/provider contracts: 13 passed, 5 failed; two nonexistent `skills-md` rows were `SKIPPED_NA`.
- The 861-row selected follow-up now has zero NOT_RUN and zero INCONCLUSIVE_EXPECTED.

The 105 selected `SKIPPED_ENV` rows still require an actual platform/toolchain/provider/runtime and are not converted to PASS from fixture evidence. Any optional live phase still requires a new, target-specific approval and locally supplied credentials; secrets should not be pasted into chat.
