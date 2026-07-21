from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def rows(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def junit(path: Path) -> tuple[int, int, int, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return tuple(sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped"))


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase = root / "evidence/codex-not-run-phase"
    summary = json.loads((phase / "codex-not-run-adjudication-summary.json").read_text())
    scope = json.loads((phase / "scope-summary.json").read_text())
    corrections = rows(phase / "entrypoint-corrections.csv")
    results = rows(phase / "codex-not-run-feature-results.csv")
    correction_counts = Counter(r["correction_class"] for r in corrections)
    audit_suites = {
        "Evidence schema": junit(phase / "audit-tests/evidence-schema-contracts.junit.xml"),
        "QA inventory": junit(phase / "audit-tests/qa-inventory-area-contracts.junit.xml"),
        "Scientific gate CLI": junit(phase / "audit-tests/scientific-gate-cli-contracts.junit.xml"),
        "CI workflow": junit(phase / "audit-tests/ci-workflow-contracts.junit.xml"),
        "Structural precondition": junit(phase / "audit-tests/included-feature-structural-preconditions.junit.xml"),
        "Installer/component": junit(phase / "audit-tests/installer-component-contracts.junit.xml"),
    }
    failures = [r for r in results if r["test_result_status"] == "FAIL"]
    pending = [r for r in results if r["test_result_status"] == "NOT_RUN"]
    skipped = [r for r in results if r["test_result_status"] == "SKIPPED_ENV"]

    suite_lines = ["| Suite | Tests | Failures | Errors | Skipped |", "|---|---:|---:|---:|---:|"]
    for name, values in audit_suites.items():
        suite_lines.append(f"| {name} | {values[0]} | {values[1]} | {values[2]} | {values[3]} |")

    fail_lines = ["| Feature | Status | Reason |", "|---|---|---|"]
    for row in failures:
        fail_lines.append(f"| `{row['feature_id']}` | FAIL | {row['result_rationale'].replace('|', '/')} |")

    report = f"""# Codex-relevant NOT_RUN remediation and execution report

## Scope

- Locked commit: `fb3f589b08e4167ac3cb0043fb3d59801a0f110b`
- Source NOT_RUN population: {scope['source_not_run_count']}
- Included as Codex-relevant: {summary['feature_count']}
- Excluded as Claude-related: {scope['scope_counts'].get('EXCLUDED_CLAUDE', 0)}
- Excluded as SciDAG-related: {scope['scope_counts'].get('EXCLUDED_SCIDAG', 0) + scope['scope_counts'].get('EXCLUDED_SCIDAG+SCIMEM', 0)}
- Excluded as SciMem-related: {scope['scope_counts'].get('EXCLUDED_SCIMEM', 0) + scope['scope_counts'].get('EXCLUDED_SCIDAG+SCIMEM', 0)}

The exclusions are feature-contract exclusions, not filename-only exclusions. Generic task graph and non-scientific memory surfaces remain in scope.

## Mapping remediation

- Exact locked-checkout product mappings: {correction_counts['exact_repo_surface']}
- Audit-only structural entrypoints with unresolved product behavior mapping: {correction_counts['audit_only_unresolved_product_entrypoint']}
- All {summary['feature_count']} included rows passed structural preconditions after correction.

Audit-only mappings do not promote a feature to PASS. They keep the row executable and expose the remaining behavioral mapping gap.

## Result summary

| Status | Count |
|---|---:|
""" + "\n".join(f"| {key} | {value} |" for key, value in summary["status_counts"].items()) + f"""

The {len(pending)} NOT_RUN rows are deliberately pending explicit user acknowledgment for HITL/provider/protected-side-effect gates. The {len(skipped)} SKIPPED_ENV rows are Desktop/platform cases blocked by unavailable Playwright browser binaries or renderer dependencies; no dependency download was performed.

## Executed audit suites

""" + "\n".join(suite_lines) + """

In addition, the existing target sweep attempted 282 isolated targets (1,903 pytest passes, 284 failures, 9 errors, 14 skips in the first sweep), followed by infrastructure-corrected reruns, reviewed shell tests, and the AutoSci shim rerun (162 pass, 11 fail). Raw target failure is not automatically an atomic feature failure.

## Direct failures

""" + "\n".join(fail_lines) + """

## Evidence boundaries

- PASS requires an exact schema/gate/CI/artifact contract or an assertion-level testcase that matches the same command/action and atomic behavior.
- Related or partial tests remain INCONCLUSIVE_EXPECTED.
- Fixture evidence is not reported as live provider or full runtime parity.
- No real email, remote execution, external provider, credential write, release publication, tag, push, or real-home mutation was performed.
- AutoSci SciDAG/SciMem and Claude-specific features are outside this phase by user direction.

## Remaining decision

The pending gate list is in `pending-acknowledgment-features.csv`. The phase cannot be declared complete until the user explicitly approves or declines those routes.
"""
    (phase / "codex-not-run-phase-report.md").write_text(report, encoding="utf-8")

    defect_text = """# Codex-relevant NOT_RUN defects

| ID | Severity | Surface | Finding |
|---|---|---|---|
| CNR-001 | P2 | Browser job runtime | `BrowserSessionPool` tests see only `BrowserSessionBroker`, and the real-browser probe does not create the expected daemon artifact directory. |
| CNR-002 | P2 | AutoSci setup / installer closure | Setup evidence declares `plugins/autosci/config/.env.example`, but that artifact is absent; setup routes and installer closure fail. |
| CNR-003 | P3 | CI diagnostics | `install-matrix`, `solar-ci`, and `windows-wsl2-install` provide neither upload-artifact diagnostics nor `GITHUB_STEP_SUMMARY`; six atomic CI contracts fail. |
| CNR-004 | P2 | Release packaging | `release/build.sh --dry-run` exits 1 because `tar ... | head -40` is executed under `set -o pipefail`; the real isolated build succeeds. |
| CNR-005 | P2 | PM intake | Research intake raises `KeyError: capability_capsule_id` instead of emitting a complete capsule/dispatch record. |
| CNR-006 | P2 | AutoSci PDF ingest | Exact PDF ingest contract returns `registration_incomplete` instead of `registration_ready`. |
| CNR-007 | P3 | AutoSci novelty provenance | A supplied `file://` payload reference is not canonicalized to the encoded URI when the checkout path contains spaces. |
| CNR-008 | P3 | Installer hygiene contract | Existing installer regression reports missing `.env.example` and missing `.gitignore` protection for `.env`, key/PEM, and runtime state patterns. |

No production fix was applied in this audit phase.
"""
    (phase / "codex-not-run-defects.md").write_text(defect_text, encoding="utf-8")

    pending_fields = ["feature_id", "parts", "atomic_feature", "feature_path", "test_result_status", "result_rationale"]
    with (phase / "pending-acknowledgment-features.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=pending_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(pending)

    command_rows = [
        ("CNR-001", "classify 1435 NOT_RUN rows", 0, "scope-summary.json"),
        ("CNR-002", "remap included rows to repository tests", 0, "remap-summary.json"),
        ("CNR-003", "isolated safe target sweep (282 targets)", 1, "safe-execution-summary.json"),
        ("CNR-004", "infrastructure-corrected reruns", 1, "infrastructure-rerun-results.tsv"),
        ("CNR-005", "reviewed safe shell tests", 1, "reviewed-shell-results.tsv"),
        ("CNR-006", "AutoSci shim corrected-PYTHONPATH rerun", 1, "autosci-shim-rerun-final-results.tsv"),
        ("CNR-007", "evidence schema contracts", 0, "audit-tests/evidence-schema-contracts.junit.xml"),
        ("CNR-008", "QA inventory area contracts", 0, "audit-tests/qa-inventory-area-contracts.junit.xml"),
        ("CNR-009", "scientific gate CLI contracts", 0, "audit-tests/scientific-gate-cli-contracts.junit.xml"),
        ("CNR-010", "CI workflow static contracts", 1, "audit-tests/ci-workflow-contracts.junit.xml"),
        ("CNR-011", "included feature structural preconditions", 0, "audit-tests/included-feature-structural-preconditions.junit.xml"),
        ("CNR-012", "installer/component contracts", 1, "audit-tests/installer-component-contracts.junit.xml"),
        ("CNR-013", "Desktop static gate/build attempt", 1, "desktop-static-logs/gate.stderr.txt"),
        ("CNR-014", "isolated release build and artifact validation", 0, "release-package/validation.json"),
        ("CNR-015", "release dry-run contract", 1, "release-package/dry-run.stderr.txt"),
        ("CNR-016", "feature-level adjudication", 0, "codex-not-run-adjudication-summary.json"),
    ]
    with (phase / "codex-not-run-command-log.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["command_id", "description", "exit_code", "evidence"])
        writer.writerows(command_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
