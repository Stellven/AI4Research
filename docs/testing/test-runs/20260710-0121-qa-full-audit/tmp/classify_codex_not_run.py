from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


CLAUDE_PATTERNS = (
    r"\bclaude\b",
    r"claude code",
    r"claude cli",
    r"claude[_ -]?(?:auth|quota|trust|hook|session|pane|kernel|overlay|runtime)",
    r"\.claude(?:/|\\)",
    r"claude\.md",
)

SCIDAG_PATTERNS = (
    r"\bscidag\b",
    r"scientific (?:dag|graph|lifecycle|workflow runner|node runtime)",
    r"research graph",
    r"graph_update(?:\.v1)?",
    r"scientific_workflow",
    r"scientific_lifecycle",
)

SCIMEM_PATTERNS = (
    r"\bscimem\b",
    r"research memory",
    r"research_memory(?:_update)?(?:\.v1)?",
    r"scientific memory",
    r"paper memory",
)

CLAUDE_SURFACE_PATTERNS = (
    r"^Hook/runtime support surface:",
    r"^Installable component: (?:kernel|skills-md|skills-office|skills-obsidian|skills-calendar|skills-browser|solar-max)$",
)

SCIDAG_SURFACE_PATTERNS = (
    r"^Scientific research lifecycle node:",
    r"^Logical operator: Scientific",
    r"^Physical operator:",
    r"^AutoSci capability ID:",
    r"^AutoSci route action workflow: run_research_lifecycle\b",
    r"^Scientific evaluator surface: lifecycle",
    r"^AutoSci bridge action workflow: update_graph\b",
)

SCIMEM_SURFACE_PATTERNS = (
    r"^AutoSci bridge action workflow: update_memory\b",
    r"^Logical operator: ScientificMemoryUpdater\b",
    r"^AutoSci capability ID: cap\.research-memory-update\b",
    r"^Evidence schema: research_memory",
    r"^Scientific evaluator gate: memory_update_gate\.py$",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def match_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def hierarchy_bucket(feature_path: str) -> str:
    pieces = [part.strip() for part in feature_path.split(">")]
    if len(pieces) >= 2:
        return pieces[1]
    return pieces[0] if pieces else ""


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    feature_rows = read_csv(root / "feature-results.csv")
    not_run = [row for row in feature_rows if row["final_result_status"] == "NOT_RUN"]

    classified: list[dict[str, str]] = []
    for row in not_run:
        contract_corpus = "\n".join(
            row.get(field, "")
            for field in (
                "atomic_feature",
                "feature_path",
                "entrypoints",
                "implementation_files_functions",
                "happy_path_pass_criteria",
                "negative_failure_pass_criteria",
            )
        )
        surface = row["feature_path"].split(">", 1)[0].strip()
        claude = match_patterns(contract_corpus, CLAUDE_PATTERNS) + match_patterns(surface, CLAUDE_SURFACE_PATTERNS)
        scidag = match_patterns(contract_corpus, SCIDAG_PATTERNS) + match_patterns(surface, SCIDAG_SURFACE_PATTERNS)
        scimem = match_patterns(contract_corpus, SCIMEM_PATTERNS) + match_patterns(surface, SCIMEM_SURFACE_PATTERNS)
        excluded = []
        if claude:
            excluded.append("claude")
        if scidag:
            excluded.append("scidag")
        if scimem:
            excluded.append("scimem")
        scope = "EXCLUDED_" + "+".join(item.upper() for item in excluded) if excluded else "INCLUDED_CODEX_RELEVANT"
        classified.append(
            {
                "feature_id": row["feature_id"],
                "parts": row["parts"],
                "atomic_feature": row["atomic_feature"],
                "feature_path": row["feature_path"],
                "hierarchy_bucket": hierarchy_bucket(row["feature_path"]),
                "scope_classification": scope,
                "excluded_elements": ";".join(excluded),
                "matched_claude_patterns": ";".join(claude),
                "matched_scidag_patterns": ";".join(scidag),
                "matched_scimem_patterns": ";".join(scimem),
                "coverage_status": row["coverage_status"],
                "eligible_phase_scope": row.get("eligible_phase_scope", ""),
                "eligible_phase_execution_result": row.get("eligible_phase_execution_result", ""),
                "existing_tests": row["existing_tests"],
                "entrypoints": row["entrypoints"],
                "implementation_files_functions": row["implementation_files_functions"],
            }
        )

    out_dir = root / "evidence" / "codex-not-run-phase"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(classified[0])
    with (out_dir / "not-run-scope-classification.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(classified)

    scope_counts = Counter(row["scope_classification"] for row in classified)
    part_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_counts: dict[str, Counter[str]] = defaultdict(Counter)
    coverage_counts: dict[str, Counter[str]] = defaultdict(Counter)
    included_l12_counts: Counter[str] = Counter()
    included_entrypoint_roots: Counter[str] = Counter()
    included_implementation_roots: Counter[str] = Counter()
    for row in classified:
        part_counts[row["parts"]][row["scope_classification"]] += 1
        bucket_counts[row["hierarchy_bucket"]][row["scope_classification"]] += 1
        coverage_counts[row["coverage_status"]][row["scope_classification"]] += 1
        if row["scope_classification"] == "INCLUDED_CODEX_RELEVANT":
            pieces = [piece.strip() for piece in row["feature_path"].split(">")]
            included_l12_counts[" > ".join(pieces[:2])] += 1
            for item in filter(None, (item.strip() for item in row["entrypoints"].split(";"))):
                included_entrypoint_roots[item.split("/", 1)[0]] += 1
            for item in filter(None, (item.strip() for item in row["implementation_files_functions"].split(";"))):
                included_implementation_roots[item.split("/", 1)[0]] += 1

    summary = {
        "schema": "qa.codex_not_run_scope.v1",
        "source_not_run_count": len(not_run),
        "scope_counts": dict(sorted(scope_counts.items())),
        "by_part": {key: dict(sorted(value.items())) for key, value in sorted(part_counts.items())},
        "by_coverage": {key: dict(sorted(value.items())) for key, value in sorted(coverage_counts.items())},
        "included_hierarchy_buckets": {
            key: value["INCLUDED_CODEX_RELEVANT"]
            for key, value in sorted(bucket_counts.items())
            if value["INCLUDED_CODEX_RELEVANT"]
        },
        "included_level_1_2_groups": dict(included_l12_counts.most_common()),
        "included_entrypoint_roots": dict(included_entrypoint_roots.most_common()),
        "included_implementation_roots": dict(included_implementation_roots.most_common()),
        "classification_note": (
            "Explicit Claude runtime/auth/hook/config surfaces are excluded. Generic tmux/task-graph surfaces are retained "
            "unless their feature contract explicitly names Claude. SciDAG/SciMem exclusions are limited to scientific "
            "graph/lifecycle and research-memory contracts."
        ),
    }
    (out_dir / "scope-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
