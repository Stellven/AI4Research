from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


def cell(value: object, limit: int = 160) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    env = json.loads((root / "environment.json").read_text())
    inv = json.loads((root / "evidence/inventory/inventory-summary.json").read_text())
    test_summary = json.loads((root / "evidence/test-execution-summary.json").read_text())
    feature_summary = json.loads((root / "evidence/feature-results-summary.json").read_text())
    eligible_summary = json.loads((root / "evidence/eligible-full-phase-v3/execution-summary.json").read_text())
    eligible_reconciliation = json.loads((root / "evidence/eligible-full-phase-v3/reconciliation-summary.json").read_text())
    shell = json.loads((root / "evidence/shell-sweep-installed-home/shell-sweep-summary.json").read_text())
    features = list(csv.DictReader((root / "feature-results.csv").open()))
    fails = [row for row in features if row["final_result_status"] == "FAIL"]
    status_order = ["PASS", "FAIL", "BLOCKED_EXPECTED", "INCONCLUSIVE_EXPECTED", "SKIPPED_NA", "SKIPPED_ENV", "FLAKY", "NOT_RUN"]
    status_counts = Counter(feature_summary["status_counts"])
    severity_counts = {"P0": 0, "P1": 4, "P2": 13, "P3": 6, "P4": 0}

    lines: list[str] = []
    lines += [
        "# AI4Research Full QA Audit",
        "",
        "## 1. Executive summary",
        "",
        "**Final verdict: NOT READY for a full-success or live-parity claim.** The locked commit has four P1 defects, including a syntactically broken workflow script, an uncollectable graph-status suite, broken approved AutoSci command execution in paths containing spaces, and unresolved root TVS imports. No P0 defect or unauthorized external side effect was observed.",
        "",
        f"The control taxonomy contains {feature_summary['feature_count']} atomic features. Conservative feature-level reconciliation produced **{status_counts['PASS']} PASS, {status_counts['FAIL']} FAIL, {status_counts['BLOCKED_EXPECTED']} BLOCKED_EXPECTED, {status_counts['INCONCLUSIVE_EXPECTED']} INCONCLUSIVE_EXPECTED, {status_counts['SKIPPED_ENV']} SKIPPED_ENV, and {status_counts['NOT_RUN']} NOT_RUN**. Passing indirect, partial, or lower-confidence tests were executed but were not promoted to full atomic-feature PASS.",
        "",
        "All control files in the ZIP were read before testing. Production source was not modified. Tests ran from a detached, local isolated checkout with an audit-only HOME and blocked external side-effect commands.",
        "",
        "## 2. Tested repo, branch, and commit",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Source | `https://github.com/Stellven/AI4Research.git` |",
        "| Requested branch | `openJiuwen-Solar` |",
        "| Locked/tested SHA | `fb3f589b08e4167ac3cb0043fb3d59801a0f110b` |",
        f"| Final real-repo SHA | `{env['real_repo_final_sha']}` |",
        f"| Final isolated-checkout SHA | `{env['isolated_checkout_final_sha']}` |",
        f"| Lock retained | `{str(env['locked_sha_unchanged_in_isolated_checkout']).lower()}` |",
        "| Initial worktree | Dirty with pre-existing user-owned deletions; preserved and not restored |",
        "",
        "## 3. Environment",
        "",
        f"- Platform: {env['platform']['platform']} (`{env['platform']['machine']}`)",
        f"- Shell: `{env['shell']}`; Bash: `{env['tools']['bash']['version']}`",
        f"- Python: `{env['tools']['python3']['version']}`; Node: `{env['tools']['node']['version']}`; Bun: `{env['tools']['bun']['version']}`",
        f"- Git: `{env['tools']['git']['version']}`; tmux: `{env['tools']['tmux']['version']}`; jq: `{env['tools']['jq']['version']}`",
        f"- Isolated test HOME: `{env['authoritative_test_home']}`",
        f"- Isolated installed SOLAR_HOME: `{env['authoritative_solar_home']}`",
        "- Network/live providers: disabled by audit policy; credential variables empty; Python non-loopback sockets and common side-effect commands blocked.",
        "",
        "## 4. Inventory validation result",
        "",
        f"The workbook supplied {inv['features']} atomic rows: workflow {inv['part_counts']['workflow']}, foundations {inv['part_counts']['foundations']}, and misc. {inv['part_counts']['misc.']}. Repo validation scanned {inv['tracked_files']} tracked files and {inv['source_files']} source/config/spec files.",
        "",
        f"The generated inventory contains {inv['inventory_items']} functions/modules/routes/scripts/config/spec rows and {inv['test_files']} test files. Reconciliation found {inv['unmapped_public_entrypoints']} public production entrypoints classified `missing-feature-row`, {inv['features_without_mapped_items']} taxonomy rows without a static implementation candidate, no duplicate feature paths, and {inv['duplicate_atomic_labels']} repeated atomic labels across otherwise distinct paths.",
        "",
        "Static test-coverage classifications: " + ", ".join(f"{key} {value}" for key, value in inv["coverage_counts"].items()) + ". These are mapping classifications, not execution verdicts.",
        "",
        "## 5. Feature coverage summary by part",
        "",
        "| Part | PASS | FAIL | BLOCKED_EXPECTED | INCONCLUSIVE_EXPECTED | SKIPPED_ENV | NOT_RUN | Total |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for part in ("workflow", "foundations", "misc."):
        counts = Counter(feature_summary["by_part"][part])
        total = sum(counts.values())
        lines.append(f"| {part} | {counts['PASS']} | {counts['FAIL']} | {counts['BLOCKED_EXPECTED']} | {counts['INCONCLUSIVE_EXPECTED']} | {counts['SKIPPED_ENV']} | {counts['NOT_RUN']} | {total} |")
    lines += [
        "",
        "The 381 INCONCLUSIVE_EXPECTED rows have executed evidence but insufficient direct/high-confidence proof for a full atomic contract. SKIPPED_NA and FLAKY remain zero. Full row-level rationale and exact selected testcase counts are in `feature-results.csv`.",
        "",
        "## 6. Function inventory summary",
        "",
        f"- Inventory rows: {inv['inventory_items']}",
        "- Classifications: " + ", ".join(f"{key} {value}" for key, value in inv["classification_counts"].items()),
        f"- Unmapped public entrypoints: {inv['unmapped_public_entrypoints']}",
        "- Unmapped entries were explicitly classified as mapped, test-only, support-only, generated, or missing-feature-row. No item was silently discarded.",
        "",
        "## 7. Test execution summary",
        "",
        "| Execution surface | Result | Contract interpretation |",
        "|---|---|---|",
        f"| Strict eligible-feature phase | {eligible_summary['status_counts'].get('PASS', 0)} target pass, {eligible_summary['status_counts'].get('FAIL', 0)} target fail; {eligible_summary['testcase_counts']['testcase_pass']} testcase pass, {eligible_summary['testcase_counts']['testcase_fail']} fail, {eligible_summary['testcase_counts']['testcase_error']} error, {eligible_summary['testcase_counts']['testcase_skip']} skip | All {eligible_reconciliation['eligible_features']} eligible atomic features have exact execution evidence; interpretation is {eligible_reconciliation['feature_interpretation_counts']}. |",
        f"| Authoritative JUnit aggregate | {test_summary['totals'].get('PASS', 0)} pass, {test_summary['totals'].get('FAIL', 0)} fail, {test_summary['totals'].get('ERROR', 0)} error, {test_summary['totals'].get('SKIPPED', 0)} skip | Raw testcase counts; environment-only failures are separately classified. |",
        "| Scientific evaluators | 103 pass, 1 fail | The one failure was reproduced and is D-003. |",
        "| AutoSci plugin | 265 pass, 17 fail, 6 skip | Fixture/local contract coverage only; no live parity claim. |",
        "| Python domain matrix | 9 suites pass, 11 suites fail | Installed isolated home; includes 20 collection errors and data-plane environment failures. |",
        f"| Shell sweep | {shell['passed']} pass, {shell['failed']} fail, {shell['flaky_timeout']} timeout of {shell['test_count']} | Final installed-home sweep; raw failures include product, missing optional integration, and test-environment contracts. |",
        "| Root Bun | overall FAIL; UI engine 18 pass | Root discovery exits 2 on unresolved TVS imports (D-004). |",
        "| Static parse/syntax | 5 failures | Four empty JSON files and `auto-chain.sh` syntax error. |",
        "| Evidence schema fixtures | 21/21 positive accepted; 21/21 empty-object negatives rejected | Schema-only deterministic proof. |",
        "| Isolated install/doctor | PASS | Components kernel/harness/autosci; doctor verdict `ok`, empty drift; deps-light install with `--skip-py-deps`. |",
        "| Desktop prepackage | PASS | No harness symlinks. |",
        "| Desktop browser gate | SKIPPED_ENV | Playwright Chromium absent; no network download attempted. |",
        "",
        "Earlier confounded and permissive eligibility runs remain in `command-log.tsv` for auditability but are not used as authoritative feature evidence. The final strict v3 run uses an isolated home, exact testcase reconciliation, no live/provider access, and the locked SHA. One pipx target was rerun without inherited audit `SOLAR_HOME`; its original environment-confounded failure was replaced.",
        "",
        "## 8. Detailed feature results",
        "",
        f"`feature-results.csv` is the authoritative 2,117-row result set. The {len(fails)} rows classified FAIL are summarized below; rows may share one root defect.",
        "",
        "| Feature ID | Part | Atomic feature | Defect/evidence |",
        "|---|---|---|---|",
    ]
    for row in fails:
        reference = row["defect_ids"] or row["execution_evidence"] or "mapped direct failure"
        lines.append(f"| `{cell(row['feature_id'])}` | {cell(row['parts'])} | {cell(row['atomic_feature'], 130)} | {cell(reference)} |")
    lines += [
        "",
        "## 9. Failures and defects",
        "",
        "| Severity | Count | Summary |",
        "|---|---:|---|",
        f"| P0 | {severity_counts['P0']} | No destructive, credential, unauthorized remote, or install-at-all failure observed. |",
        f"| P1 | {severity_counts['P1']} | Auto-chain syntax, graph collection, approved AutoSci path/status handling, root TVS imports. |",
        f"| P2 | {severity_counts['P2']} | Survey/API drift, local-command quoting, setup/parity, ingest/provider proof, browser APIs, operator/actor schemas, graph hygiene/reuse, intake capsule output, benchmark, install scaffold, livework hooks, knowledge alias health. |",
        f"| P3 | {severity_counts['P3']} | Status rendering, URI encoding, pytest layout, empty JSON, approval taxonomy, environment-aware skipping. |",
        f"| P4 | {severity_counts['P4']} | None recorded. |",
        "",
        "See `defects.md` for reproductions, impact, and evidence references. The audit does not equate every raw test failure with a distinct defect.",
        "",
        "## 10. Gated, skipped, inconclusive, and live-provider-only surfaces",
        "",
        "No real email, GitHub mutation, release, remote execution, browser profile, credential write, package publication, or provider call was attempted. Approval-gated tests count only when their mapped deterministic test retained the gate/continuation contract. Data-plane tests requiring a real Knowledge/QMD/MinerU corpus and the desktop Playwright gate are SKIPPED_ENV.",
        "",
        "AutoSci results are fixture/local evidence only. Full runtime parity remains unproven because no non-fixture provider-backed lifecycle was authorized. See `gated-and-live-test-plan.md` for the separate approval requirements.",
        "",
        "## 11. Missing tests and recommended additions",
        "",
        f"After semantic/executable validation, mapping classifies {inv['coverage_counts']['missing']} atomic features as missing, {inv['coverage_counts']['partial']} as partial, {inv['coverage_counts']['indirect']} as indirect, and {inv['coverage_counts']['manual-only']} as manual-only. This includes {eligible_reconciliation['reclassified_missing_features']} heuristic candidates reclassified to missing. `missing-test-plan.csv` provides a feature-specific recommendation for every row.",
        "",
        "Highest-priority additions are: a root package/TVS install contract; spaced-path tests for every local-command/allowlist route; graph-suite collection and hygiene/reuse smoke; research-intake capsule assertions; actor/logical-operator registry consistency tests; installer runtime-directory assertions; explicit BLOCKED_EXPECTED approval schema assertions; self-skipping data-plane/live-provider tests; and one authoritative repository-wide pytest configuration that avoids module-name collisions.",
        "",
        "## 12. Final readiness verdict",
        "",
        f"**NOT READY.** The commit is not sufficiently or correctly tested for a full-repo success claim, and several core surfaces are presently broken. It must not be described as AutoSci full runtime parity. Readiness requires all P1 defects fixed, direct retests passing on the locked/fixed SHA, P2 contract drift resolved or explicitly accepted, and the {status_counts['NOT_RUN']} NOT_RUN plus {status_counts['INCONCLUSIVE_EXPECTED']} INCONCLUSIVE_EXPECTED atomic rows reduced through direct evidence or justified scope decisions.",
        "",
        "The isolated installer/doctor, many unit contracts, schema negatives, and multiple deterministic sub-suites do pass. Those successes are retained in the feature workbook and CSVs without being generalized into a repo-wide pass.",
    ]
    (root / "final-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": "final-report.md", "feature_fail_rows": len(fails), "verdict": "NOT READY"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
