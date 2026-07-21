from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


MANUAL_GUI = re.compile(
    r"desktop/(?:screens|functional|frontend-scenarios|overhaul-visual|rapid-switch)\.test\.js$"
)
EXCLUDED_SCOPE = re.compile(
    r"(?:claude|scientific_lifecycle|scientific_node_runtime|human_search_dag)", re.IGNORECASE
)
AGGREGATORS = {
    "scripts/test-local.sh",
    "harness/tests/regression/run-vnext-regression-suite.sh",
}
DANGEROUS = re.compile(
    r"\b(?:ssh|scp|rsync|git\s+push|gh\s+release|curl|wget|launchctl|systemctl|osascript|sendmail|mailx)\b"
    r"|\brm\s+-rf\b",
    re.IGNORECASE,
)
MOCK_SIGNAL = re.compile(
    r"(?:mock[_ -]?bin|fake[_ -]?(?:bin|ssh|curl|tmux)|PATH=.*tmp|mktemp|monkeypatch|unittest\.mock|patch\()",
    re.IGNORECASE,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def runner_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "pytest"
    if suffix in {".sh", ".bash", ".zsh"}:
        return "shell"
    if suffix in {".js", ".cjs", ".mjs"}:
        return "node"
    if suffix in {".ts", ".tsx", ".jsx"}:
        return "bun"
    return "unsupported"


def main() -> int:
    audit_root = Path(sys.argv[1]).resolve()
    checkout = Path(sys.argv[2]).resolve()
    remap = read_csv(audit_root / "evidence/codex-not-run-phase/feature-test-remap.csv")
    feature_by_id = {row["feature_id"]: row for row in remap}
    links: dict[str, set[str]] = defaultdict(set)
    classifications: dict[str, set[str]] = defaultdict(set)
    nodeids: dict[str, set[str]] = defaultdict(set)
    for row in remap:
        for target in filter(None, row["selected_test_targets"].split(";")):
            links[target].add(row["feature_id"])
            classifications[target].add(row["remap_classification"])
        for nodeid in filter(None, row["selected_testcases"].split(";")):
            target = nodeid.split("::", 1)[0]
            nodeids[target].add(nodeid)

    rows: list[dict[str, object]] = []
    category_counts: Counter[str] = Counter()
    for index, target in enumerate(sorted(links), start=1):
        path = checkout / target
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        kind = runner_kind(target)
        if not path.is_file():
            category = "missing_target"
            reason = "candidate target is not present at the locked SHA"
        elif EXCLUDED_SCOPE.search(target):
            category = "excluded_scope_test"
            reason = "test target itself exercises a Claude/SciDAG runtime surface excluded by the user"
        elif target in AGGREGATORS:
            category = "aggregator_not_atomic"
            reason = "suite aggregator is not atomic proof; its leaf tests are planned separately"
        elif MANUAL_GUI.search(target):
            category = "manual_gui_pending_ack"
            reason = "launches Electron/GUI and requires explicit HITL acknowledgement for this phase"
        elif kind == "shell" and DANGEROUS.search(text) and not MOCK_SIGNAL.search(text):
            category = "shell_safety_review"
            reason = "shell test contains a potentially external/destructive command without an obvious local mock"
        elif kind == "unsupported":
            category = "unsupported_runner"
            reason = "no deterministic local runner selected"
        else:
            category = "safe_deterministic"
            reason = "isolated HOME/TMP, credentials stripped, outbound proxies blocked"
        category_counts[category] += 1
        linked = sorted(links[target])
        rows.append(
            {
                "target_id": f"codex-nr-{index:04d}",
                "runner_kind": kind,
                "test_target": target,
                "plan_category": category,
                "plan_reason": reason,
                "linked_feature_count": len(linked),
                "linked_feature_ids": ";".join(linked),
                "mapping_classifications": ";".join(sorted(classifications[target])),
                "selected_testcases": ";".join(sorted(nodeids[target])),
                "prior_blockers": ";".join(sorted({feature_by_id[item]["prior_blocker"] for item in linked})),
            }
        )

    out_dir = audit_root / "evidence/codex-not-run-phase"
    fields = list(rows[0])
    write_csv(out_dir / "execution-plan.csv", rows, fields)
    write_csv(
        out_dir / "safe-target-feature-map.csv",
        [row for row in rows if row["plan_category"] == "safe_deterministic"],
        fields,
    )
    summary = {
        "schema": "qa.codex_not_run_execution_plan.v1",
        "candidate_target_count": len(rows),
        "category_counts": dict(sorted(category_counts.items())),
        "safe_linked_feature_count": len({
            feature_id
            for row in rows if row["plan_category"] == "safe_deterministic"
            for feature_id in str(row["linked_feature_ids"]).split(";") if feature_id
        }),
    }
    (out_dir / "execution-plan-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
