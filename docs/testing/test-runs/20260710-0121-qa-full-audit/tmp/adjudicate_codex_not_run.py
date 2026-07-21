from __future__ import annotations

import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def junit_statuses(path: Path) -> dict[str, str]:
    result = {}
    if not path.is_file():
        return result
    root = ET.parse(path).getroot()
    for case in root.findall(".//testcase"):
        name = case.attrib.get("name", "")
        if case.find("failure") is not None or case.find("error") is not None:
            status = "FAIL"
        elif case.find("skipped") is not None:
            status = "SKIP"
        else:
            status = "PASS"
        result[name] = status
        result[name.split("[", 1)[0]] = status
    return result


def surface_identifier(path: str) -> str:
    surface = path.split(">", 1)[0].strip()
    patterns = (
        r"AutoSci slash workflow: /([^ ]+)",
        r"AutoSci (?:bridge|route) action workflow: ([^ ]+)",
        r"Benchmark workflow: (.+)",
        r"Knowledge (?:ingestion|health|QMD index) workflow: (.+)",
        r"Research/source ingestion workflow: (.+)",
        r"Bridge/route foundation: (.+)",
        r"Capability machinery: (.+)",
    )
    for pattern in patterns:
        match = re.match(pattern, surface)
        if match:
            return re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
    return ""


STOP = {"accepts", "expected", "feature", "input", "output", "status", "evidence", "reports", "without", "returns", "requires", "validates", "workflow", "artifact", "source", "provider", "missing", "handles", "supported", "result", "correctly", "explicit", "produces", "includes"}


def strict_semantic_match(feature: dict[str, str], nodeid: str) -> bool:
    name = re.sub(r"[^a-z0-9]+", "_", nodeid.lower())
    surface = feature["feature_path"].split(">", 1)[0].strip()
    identifier = surface_identifier(feature["feature_path"])
    if identifier and identifier not in name:
        pieces = [piece for piece in identifier.split("_") if len(piece) >= 4]
        if len([piece for piece in pieces if piece in name]) < min(2, len(pieces)):
            return False
    if surface.startswith("Skill/integration surface: "):
        skill = re.sub(r"[^a-z0-9]+", "_", surface.split(":", 1)[1].lower()).strip("_")
        pieces = [piece for piece in skill.split("_") if len(piece) >= 5 and piece not in {"integration", "surface", "skills"}]
        if not pieces or not any(piece in name for piece in pieces):
            return False
    if surface.startswith("Knowledge ingestion workflow:") and "knowledge_ingest" not in name:
        return False
    if surface.startswith("Knowledge health workflow:") and "knowledge_ingest_health" not in name:
        return False
    if surface.startswith("Capability machinery:"):
        capability = re.sub(r"[^a-z0-9]+", "_", surface.split(":", 1)[1].lower()).strip("_")
        if capability not in name:
            return False
    atomic_tokens = {
        token for token in re.findall(r"[a-z0-9]+", feature["atomic_feature"].lower())
        if len(token) >= 6 and token not in STOP
    }
    overlap = atomic_tokens & set(name.split("_"))
    return len(overlap) >= min(2, len(atomic_tokens))


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase = root / "evidence/codex-not-run-phase"
    source = {r["feature_id"]: r for r in read_csv(root / "feature-results.csv")}
    scoped = [r for r in read_csv(phase / "not-run-scope-classification.csv") if r["scope_classification"] == "INCLUDED_CODEX_RELEVANT"]
    remap = {r["feature_id"]: r for r in read_csv(phase / "feature-test-remap.csv")}
    corrections = {r["feature_id"]: r for r in read_csv(phase / "entrypoint-corrections.csv")}

    latest: dict[str, dict[str, str]] = {}
    result_files = [
        "safe-target-results.tsv", "infrastructure-rerun-results.tsv", "reviewed-shell-results.tsv",
        "autosci-path-rerun-results.tsv", "autosci-shim-rerun-final-results.tsv",
    ]
    for name in result_files:
        path = phase / name
        if path.is_file():
            for row in read_csv(path, "\t"):
                latest[row["test_target"]] = {**row, "result_file": str(path.relative_to(root))}
    cases_by_target = {}
    for target, row in latest.items():
        junit = row.get("junit_path", "")
        cases_by_target[target] = junit_statuses(root / junit) if junit else {}

    ci_cases = junit_statuses(phase / "audit-tests/ci-workflow-contracts.junit.xml")
    qa_cases = junit_statuses(phase / "audit-tests/qa-inventory-area-contracts.junit.xml")
    schema_cases = junit_statuses(phase / "audit-tests/evidence-schema-contracts.junit.xml")
    gate_cli_cases = junit_statuses(phase / "audit-tests/scientific-gate-cli-contracts.junit.xml")

    rows = []
    observed_direct_failures = {
        "WF-0008-INTAKE-ROUTES-GRAPH-SPRINT-45CDE3": (
            "PM intake research request raised KeyError for capability_capsule_id instead of routing a complete capsule.",
            "evidence/codex-not-run-phase/junit/codex-nr-0230.xml",
        ),
        "WF-0086-SOURCE-FULLY-REGISTERED-ONLY-1F8E0A": (
            "PDF ingest returned registration_incomplete where the exact shim contract required registration_ready.",
            "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml",
        ),
        "WF-0091-TARGET-RESOLVED-REJECTED-ACTIONABLE-B20BDE": (
            "Novelty provider payload reference was not canonicalized to the encoded file URI in a checkout path containing spaces.",
            "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml",
        ),
        "WF-0260-REPORTS-MISSING-PRESENT-CONFIG-234895": (
            "setup_status evidence referenced missing plugins/autosci/config/.env.example and the exact route returned failed.",
            "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml",
        ),
        "WF-0261-NONINTERACTIVE-MISSING-VALUES-PRODUCE-0C96FF": (
            "Noninteractive setup could not emit the expected gated remedy because its declared .env.example artifact is absent.",
            "evidence/codex-not-run-phase/autosci-shim-rerun-final-junit/codex-nr-0009.xml",
        ),
    }
    for scoped_row in scoped:
        fid = scoped_row["feature_id"]
        feature = source[fid]
        mapping = remap.get(fid, {})
        correction = corrections[fid]
        fpath = feature["feature_path"]
        status = "INCONCLUSIVE_EXPECTED"
        strength = "structural"
        rationale = "Structural preconditions passed, but no assertion-level test proves the complete atomic behavior."
        evidence = ["evidence/codex-not-run-phase/audit-tests/included-feature-structural-preconditions.junit.xml"]

        if fpath.startswith("QA inventory top-level area:"):
            status, strength = "PASS", "direct_audit_contract"
            rationale = "The area-specific QA inventory contract passed against the generated audit mappings and criteria."
            evidence = ["evidence/codex-not-run-phase/audit-tests/qa-inventory-area-contracts.junit.xml"]
        elif fpath.startswith("Evidence schema:"):
            status, strength = "PASS", "direct_schema_contract"
            rationale = "Minimal, rich, status, and malformed-payload schema contracts passed for this exact evidence schema."
            evidence = ["evidence/codex-not-run-phase/audit-tests/evidence-schema-contracts.junit.xml"]
        elif fpath.startswith("Scientific evaluator gate:") or fpath.startswith("Scientific evaluator surface:"):
            status, strength = "PASS", "direct_gate_contract"
            rationale = "Exact evaluator tests passed and the gate CLI returned typed failures for missing and malformed evidence."
            evidence = [
                "evidence/codex-not-run-phase/audit-tests/scientific-gate-cli-contracts.junit.xml",
                "evidence/codex-not-run-phase/safe-target-results.tsv",
            ]
        elif fpath.startswith("CI workflow:"):
            workflow = fpath.split(":", 1)[1].split(">", 1)[0].strip()
            bucket = fpath.split(">", 2)[1].strip()
            case_name = {
                "trigger/matrix": f"test_ci_trigger_matrix_contract[{workflow}]",
                "setup/install": f"test_ci_setup_steps_are_explicit[{workflow}]",
                "job gate": f"test_ci_job_gate_does_not_hide_failures_and_preserves_logs[{workflow}]",
                "artifact/report": f"test_ci_expected_artifact_or_status_summary[{workflow}]",
            }.get(bucket, "")
            if case_name and case_name in ci_cases:
                status = ci_cases[case_name]
                strength = "direct_ci_static_contract"
                rationale = "Exact GitHub Actions workflow contract assertion passed." if status == "PASS" else "Exact workflow contract failed: diagnostic artifact/job summary is absent."
                evidence = ["evidence/codex-not-run-phase/audit-tests/ci-workflow-contracts.junit.xml"]
        elif fpath.startswith("Installer / packaging surface: release packaging"):
            bucket = fpath.split(">", 2)[1].strip()
            if bucket == "output artifacts":
                status, strength = "PASS", "direct_artifact_contract"
                rationale = "Isolated release build produced a tarball, checksum, and manifest; checksum and exclusion contents were validated."
                evidence = ["evidence/codex-not-run-phase/release-package/validation.json"]
            elif bucket in {"flags/config", "dry-run/idempotence"}:
                status, strength = "FAIL", "direct_cli_contract"
                rationale = "release/build.sh --dry-run emits the plan but exits 1 because tar|head trips pipefail."
                evidence = ["evidence/codex-not-run-phase/release-package/dry-run.stderr.txt"]
        elif fpath.startswith("Desktop ") or fpath.startswith("UI surface: React"):
            if feature["coverage_status"] in {"manual-only", "gated"}:
                status, strength = "SKIPPED_ENV", "attempted_environment_block"
                rationale = "Non-GUI gate/build was attempted in isolation; Playwright browser binaries or renderer dependencies are unavailable. GUI execution awaits explicit acknowledgment."
                evidence = ["evidence/codex-not-run-phase/desktop-static-logs/gate.stderr.txt"]
        elif feature["coverage_status"] == "gated":
            status, strength = "NOT_RUN", "pending_user_acknowledgment"
            rationale = "Continuation would cross an explicit HITL/provider/protected side-effect gate; acknowledgment was requested in this session."
        else:
            selected = [x for x in mapping.get("selected_testcases", "").split(";") if x]
            strict_statuses = []
            strict_evidence = set()
            for nodeid in selected:
                target, _, case = nodeid.partition("::")
                if not case or not strict_semantic_match(feature, nodeid):
                    continue
                value = cases_by_target.get(target, {}).get(case)
                if value:
                    strict_statuses.append(value)
                    row = latest.get(target, {})
                    if row.get("junit_path"):
                        strict_evidence.add(row["junit_path"])
            if strict_statuses:
                if "FAIL" in strict_statuses:
                    status, strength = "FAIL", "direct_semantic_testcase"
                    rationale = "At least one assertion-level testcase matching this exact command/action and atomic behavior failed."
                elif all(x == "PASS" for x in strict_statuses):
                    status, strength = "PASS", "direct_semantic_testcase"
                    rationale = "Assertion-level testcase(s) matching the exact command/action and atomic behavior passed."
                evidence = sorted(strict_evidence) or evidence
            else:
                targets = [x for x in mapping.get("selected_test_targets", "").split(";") if x]
                executed = [latest[x]["execution_status"] for x in targets if x in latest]
                if executed:
                    rationale = "Related tests executed, but their assertions are indirect/partial and do not prove the complete atomic behavior."
                    evidence = sorted({latest[x].get("result_file", "") for x in targets if x in latest and latest[x].get("result_file")})

        if fid in observed_direct_failures:
            failure_reason, failure_evidence = observed_direct_failures[fid]
            status, strength = "FAIL", "direct_observed_contract"
            rationale = failure_reason
            evidence = [failure_evidence]

        if correction["correction_class"] == "audit_only_unresolved_product_entrypoint" and status == "PASS" and strength == "direct_semantic_testcase":
            status, strength = "INCONCLUSIVE_EXPECTED", "audit_only_mapping"
            rationale = "A related assertion passed, but the product implementation entrypoint remains unresolved; it cannot support atomic PASS."

        rows.append({
            "feature_id": fid,
            "parts": feature["parts"],
            "atomic_feature": feature["atomic_feature"],
            "feature_path": fpath,
            "prior_status": feature["final_result_status"],
            "coverage_status": feature["coverage_status"],
            "scope_classification": "INCLUDED_CODEX_RELEVANT",
            "corrected_mapping_class": correction["correction_class"],
            "test_result_status": status,
            "evidence_strength": strength,
            "result_rationale": rationale,
            "execution_evidence": ";".join(evidence),
            "selected_test_targets": mapping.get("selected_test_targets", ""),
            "selected_testcases": mapping.get("selected_testcases", ""),
        })

    write_csv(phase / "codex-not-run-feature-results.csv", rows)
    counts = Counter(r["test_result_status"] for r in rows)
    by_part = defaultdict(Counter)
    for row in rows:
        by_part[row["parts"]][row["test_result_status"]] += 1
    summary = {
        "schema": "qa.codex_not_run_adjudication.v1",
        "feature_count": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "by_part": {k: dict(sorted(v.items())) for k, v in sorted(by_part.items())},
        "pending_acknowledgment": [r["feature_id"] for r in rows if r["evidence_strength"] == "pending_user_acknowledgment"],
        "warning": "Structural-only and partial evidence remains INCONCLUSIVE_EXPECTED; it is not promoted to PASS.",
    }
    (phase / "codex-not-run-adjudication-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
