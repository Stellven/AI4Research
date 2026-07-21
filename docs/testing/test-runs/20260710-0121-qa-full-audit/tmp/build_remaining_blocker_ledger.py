from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        if not rows:
            raise ValueError(f"fieldnames required for empty CSV: {path}")
        fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def classify(row: dict[str, str]) -> tuple[str, str, str]:
    surface = row["feature_path"].split(">", 1)[0].strip()
    atomic = row["atomic_feature"].lower()

    gate_markers = (
        "approval", "approved", "writeback", "mutation", "mutating", "delete",
        "browser/png", "serving", "portal submission", "explicit confirmation",
    )
    manual_markers = (
        "avoid fabricated", "overpromises", "every analytical statement", "suggestions are concrete",
        "match domain", "rationale", "review evidence", "disagreement", "not silently assumed",
        "source-linked", "cite source", "limitations explain", "not-testable", "without inventing",
    )

    if any(marker in atomic for marker in gate_markers):
        return (
            "ACK_REQUIRED_GATE_OR_HITL",
            "Requires an explicit in-session approval scope before a real mutation/browser/send path can be exercised; synthetic block-path evidence alone is already recorded.",
            "Ask the user to name the allowed side effect, target fixture/app/profile, and rollback boundary; then run one approved positive-path test plus the existing blocked negative path.",
        )
    if any(marker in atomic for marker in manual_markers):
        return (
            "MANUAL_OR_ORACLE_REVIEW",
            "The remaining acceptance criterion is semantic/quality judgment and is not proven by schema or exit status alone.",
            "Prepare the generated artifact and a feature-specific rubric, then obtain human/oracle adjudication without treating fixture generation as full parity.",
        )
    if surface.startswith("Skill/integration surface:"):
        if any(name in surface for name in ("skills-md", "skills-office", "skills-obsidian", "skills-calendar")):
            return (
                "ACK_REQUIRED_APP_DATA",
                "Behavioral verification needs an installed desktop app or user-owned document/vault/calendar target and may mutate it.",
                "Use a disposable document/vault/calendar fixture after the user explicitly authorizes the app and permitted read/write operation.",
            )
        return (
            "LIVE_ENV_OR_PROVIDER",
            "The remaining contract needs provider credentials, a live browser/profile, a vault endpoint, or an integration runtime not available in the offline phase.",
            "User supplies the environment locally and explicitly authorizes a live phase; validate provenance, limitations, and negative provider behavior without pasting secrets into chat.",
        )
    if surface.startswith(("Browser workflow:", "UI surface:")):
        return (
            "PLATFORM_OR_BROWSER_ENV",
            "A real browser/UI runtime or installed renderer is needed for the remaining positive path.",
            "Authorize a disposable browser profile/headless runtime and run the positive path while preserving the existing no-profile negative evidence.",
        )
    if surface.startswith("Installer / packaging surface:"):
        if "GitHub release" in surface:
            return (
                "ACK_REQUIRED_RELEASE_BOUNDARY",
                "Local packaging evidence exists, but a real GitHub release must not be created without explicit authorization.",
                "First add/execute a strictly local no-upload dry-run assertion; request separate approval only for any real release API call.",
            )
        return (
            "NEEDS_NEW_DIRECT_ASSERTION",
            "Related installer/package tests are indirect or do not assert this exact flags/platform/artifact/idempotence/failure contract.",
            "Add an audit-only isolated-HOME fixture that snapshots paths before/after and validates the exact artifact schema or actionable failure.",
        )
    if surface.startswith("Status service:"):
        return (
            "NEEDS_NEW_DIRECT_ASSERTION",
            "The remaining port-conflict/dead-process branch was not directly forced by the 24-test status suite.",
            "Bind a disposable local port with a fixture process, invoke status-server startup/status, and assert typed conflict/stale-PID guidance.",
        )
    if surface.startswith("Capability machinery:"):
        return (
            "NEEDS_NEW_DIRECT_ASSERTION",
            "Existing capability tests cover adjacent actions but not this exact config-validation or duplicate/stale-state contract.",
            "Create a temporary registry/config with malformed, duplicate, and stale entries and assert typed rejection plus byte-stable source data.",
        )
    if surface.startswith("Solar harness workflow: human approval gates"):
        return (
            "ACK_REQUIRED_GATE_OR_HITL",
            "The plan-verdict positive path records a human decision and must not be silently synthesized as user approval.",
            "Ask for a synthetic fixture approval in this session, then assert sprint state and the recorded human reason in a temporary harness root.",
        )
    if surface.startswith("AutoSci"):
        return (
            "NEEDS_NEW_DIRECT_ASSERTION",
            "Existing AutoSci tests are adjacent/partial; no assertion currently proves the full atomic input, output, provenance, and failure contract.",
            "Add a feature-specific audit-only fixture test against the concrete bridge/route entrypoint; keep any provider output explicitly fixture-only.",
        )
    return (
        "NEEDS_NEW_DIRECT_ASSERTION",
        "The implementation is local, but existing executed tests are indirect or the exact entrypoint remains unresolved.",
        "Resolve the concrete entrypoint and add an audit-only before/after contract assertion for the complete atomic behavior.",
    )


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    phase = root / "evidence/codex-not-run-phase"
    rows = read_csv(phase / "codex-not-run-feature-results.csv")
    remaining = []
    for row in rows:
        if row["test_result_status"] != "INCONCLUSIVE_EXPECTED":
            continue
        category, blocker, action = classify(row)
        remaining.append(
            {
                "feature_id": row["feature_id"],
                "feature_path": row["feature_path"],
                "atomic_feature": row["atomic_feature"],
                "current_status": row["test_result_status"],
                "blocker_category": category,
                "blocker_detail": blocker,
                "required_next_action": action,
                "existing_evidence": row["execution_evidence"],
            }
        )
    write_csv(
        phase / "remaining-inconclusive-blocker-classification.csv",
        remaining,
        fieldnames=[
            "feature_id",
            "feature_path",
            "atomic_feature",
            "current_status",
            "blocker_category",
            "blocker_detail",
            "required_next_action",
            "existing_evidence",
        ],
    )

    scope_rows = read_csv(phase / "not-run-scope-classification.csv")
    excluded = [row for row in scope_rows if row.get("scope_classification", "").startswith("EXCLUDED")]
    phase_by_id = {row["feature_id"]: row for row in rows}
    for fid in ("FD-0618-LOADS-CAPABILITY-CONFIG-REGISTRY-2236C4", "FD-0619-PERFORMS-DOCUMENTED-LIST-QUERY-42DF2A"):
        row = phase_by_id[fid]
        excluded.append(
            {
                "feature_id": fid,
                "parts": row["parts"],
                "atomic_feature": row["atomic_feature"],
                "feature_path": row["feature_path"],
                "hierarchy_bucket": "capability scorer",
                "scope_classification": "EXCLUDED_CLAUDE",
                "excluded_elements": "claude",
                "matched_claude_patterns": "harness/hooks/claude/capability-scorer.sh",
                "matched_scidag_patterns": "",
                "matched_scimem_patterns": "",
                "coverage_status": row["coverage_status"],
                "eligible_phase_scope": "excluded:corrected_claude_only_surface",
                "eligible_phase_execution_result": "SKIPPED_NA",
                "existing_tests": row["selected_testcases"],
                "entrypoints": "harness/hooks/claude/capability-scorer.sh",
                "implementation_files_functions": "harness/hooks/claude/capability-scorer.sh",
            }
        )
    seen: set[str] = set()
    unique = []
    for row in excluded:
        if row["feature_id"] in seen:
            continue
        seen.add(row["feature_id"])
        unique.append(row)
    write_csv(phase / "excluded-feature-ledger.csv", unique)

    summary = {
        "remaining_inconclusive": len(remaining),
        "blocker_counts": dict(sorted(Counter(row["blocker_category"] for row in remaining).items())),
        "excluded_feature_count": len(unique),
        "excluded_scope_counts": dict(sorted(Counter(row["scope_classification"] for row in unique).items())),
    }
    (phase / "remaining-blocker-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
