from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _reference_path(reference: str) -> str:
    """Return the tracked-file part of a ``path::symbol`` inventory reference."""
    return reference.strip().split("::", 1)[0].strip()


def _is_test_or_generated_path(path: str) -> bool:
    normalized = f"/{path.strip('/')}"
    name = Path(path).name.lower()
    return (
        "/tests/" in normalized
        or "/test/" in normalized
        or path.startswith("tests/")
        or path.startswith("docs/testing/")
        or path.startswith("evidence/")
        or name.startswith("test_")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".status.json")
    )


def product_references(row: dict[str, str], checkout: Path) -> list[str]:
    """Keep only existing locked-checkout implementation references, excluding tests."""
    references = []
    for reference in row.get("implementation_files_functions", "").split(";"):
        reference = reference.strip()
        path = _reference_path(reference)
        if not path or _is_test_or_generated_path(path):
            continue
        if (checkout / path).exists():
            references.append(reference)
    return _unique(references)


def exact_paths(feature_path: str) -> list[str]:
    surface = feature_path.split(">", 1)[0].strip()
    if surface.startswith("Evidence schema: "):
        schema = surface.removeprefix("Evidence schema: ")
        return [f"harness/schemas/evidence/{schema}.schema.json"]
    if surface.startswith("Scientific evaluator gate: "):
        return [f"harness/evaluators/scientific/{surface.removeprefix('Scientific evaluator gate: ')}"]
    if surface.startswith("Scientific evaluator surface: "):
        name = surface.removeprefix("Scientific evaluator surface: ")
        return [f"harness/evaluators/scientific/{name}.py"]
    if surface.startswith("CI workflow: "):
        name = surface.removeprefix("CI workflow: ")
        return [f".github/workflows/{name}.yml"]
    if surface.startswith("Desktop package script: ") or surface.startswith("Desktop surface: "):
        return ["desktop/package.json"]
    if surface.startswith("QA inventory top-level area: "):
        return [
            "docs/testing/qa_feature_inventory.csv",
            "docs/testing/qa_feature_list.csv",
            "tools/qa_inventory.py",
        ]
    if surface.startswith("Bridge/route foundation: ") or surface.startswith("AutoSci "):
        return [
            "harness/plugins/autosci/bin/autosci_skill_shim.py",
            "harness/plugins/autosci/bin/autosci_bridge.py",
            "harness/plugins/autosci/config/feature_parity_routes.v1.json",
        ]
    if surface.startswith("Capability machinery: "):
        return ["harness/lib/capability_registry.py", "harness/lib/capability_inference.py"]
    if surface.startswith("Graph orchestration workflow: "):
        return [
            "harness/lib/graph_scheduler.py",
            "harness/lib/graph_node_dispatcher.py",
            "harness/tools/graph_scheduler.py",
            "harness/tools/graph_node_dispatcher.py",
        ]
    if surface.startswith("Knowledge ingestion workflow: "):
        return ["harness/tools/knowledge_ingest_dispatcher.py"]
    if surface.startswith("Knowledge health workflow: "):
        return ["harness/tools/knowledge_ingest_health.py"]
    if surface.startswith("Knowledge QMD index workflow: "):
        return ["harness/tools/knowledge_qmd_indexer.py"]
    if surface.startswith("Installer / packaging surface: "):
        return ["install.sh", "get-solar.sh", "install.ps1", "lib/installer/components.sh"]
    if surface.startswith("CLI lifecycle command: ") or surface.startswith("UI surface: solar ui"):
        return ["bin/solar", "lib/installer/doctor.sh"]
    if surface.startswith("Status service: "):
        return [
            "harness/lib/symphony/status-server.py",
            "harness/status-server/routes/orchestration_routes.py",
            "harness/status-server/routes/livework_routes.py",
            "components.d/status-daemon/component.sh",
        ]
    if surface.startswith("Benchmark workflow: "):
        return [
            "harness/tools/benchmark/runner.py",
            "harness/tools/benchmark/reports.py",
            "harness/tools/benchmark/solar_solver.py",
            "harness/tools/benchmark/orchestration/status_banner.py",
        ]
    if surface.startswith("Research/source ingestion workflow: daily_arxiv"):
        return ["tools/daily_arxiv.py"]
    if surface.startswith("Solar harness workflow: "):
        return ["harness/solar-harness.sh"]
    if surface.startswith("Browser job/runtime surface: "):
        return ["harness/lib/browser_job_runtime.py", "harness/tools/browser_job_runtime.py"]
    if surface.startswith("Browser workflow: social browser backend CLI"):
        return [
            "harness/lib/social_browser_backend_x/cli.py",
            "harness/lib/social_browser_backend_x/pipeline.py",
            "harness/lib/social_browser_backend_x/operator_lease_manager.py",
        ]
    if surface.startswith("Side-effect class: ") or surface.startswith("HITL/gate mode: "):
        return ["harness/plugins/autosci/policy/gate_policy.py"]
    if surface.startswith("TaskGraph architecture constraint: "):
        return [
            "harness/lib/architecture_guard.py",
            "harness/tools/architecture_guard.py",
            "harness/schemas/task-graph.schema.json",
        ]
    if surface.startswith("TaskGraph resume surface: "):
        return [
            "harness/schemas/task-graph.schema.json",
            "harness/schemas/task-lifecycle.schema.json",
            "harness/lib/graph_scheduler.py",
        ]
    if surface.startswith("UI surface: React status dashboard"):
        return ["harness/status-server/react-app/package.json"]
    if surface.startswith("Installable component: "):
        component = surface.removeprefix("Installable component: ").strip()
        return [f"components.d/{component}/component.sh", "lib/installer/components.sh"]
    fetch_map = {
        "fetch_deepxiv": "tools/fetch_deepxiv.py",
        "fetch_s2": "tools/fetch_s2.py",
        "fetch_wikipedia": "tools/fetch_wikipedia.py",
        "fetch_arxiv": "tools/fetch_arxiv.py",
        "rasterize_latex": "tools/rasterize_latex.py",
    }
    for marker, path in fetch_map.items():
        if marker in surface:
            return [path]
    skill_map = {
        "skills-md": "skills/solar/SKILL.md",
        "skills-office": "skills/office/SKILL.md",
        "skills-obsidian": "skills/obsidian-direct/SKILL.md",
        "skills-calendar": "skills/apple-calendar/SKILL.md",
        "skills-browser": "skills/browser-automation/SKILL.md",
        "Obsidian wiki integration": "harness/tools/obsidian-vault-indexer.py",
        "RAGFlow adapter": "harness/tools/ragflow_adapter.py",
        "Codex bridge": "harness/tools/codex_operator.py",
        "Mempalace semantic memory MCP server": "mempalace/mempalace_mcp_server.py",
        "browser automation": "skills/browser-automation/SKILL.md",
        "social browser backend": "harness/lib/social_browser_backend_x/cli.py",
        "Apple Notes ingest": "harness/tools/apple_notes_ingest.py",
        "ChatGPT conversation ingest": "harness/tools/chatgpt-conversation-ingest.py",
        "Gemini adapter": "harness/tools/gemini_adapter.py",
        "Gemini enhanced search": "harness/tools/gemini_enhanced_search_operator.py",
        "Gemini Deep Research capability": "harness/tools/gemini_deep_research_operator.py",
        "Semantic Scholar fetch": "tools/fetch_s2.py",
        "DeepXiv fetch": "tools/fetch_deepxiv.py",
        "arXiv fetch / daily arXiv": "tools/fetch_arxiv.py",
        "Wikipedia fetch": "tools/fetch_wikipedia.py",
        "LaTeX rasterization / paper compile support": "tools/rasterize_latex.py",
    }
    for marker, path in skill_map.items():
        if surface == f"Skill/integration surface: {marker}":
            return [path]
    return []


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    checkout = Path(sys.argv[2]).resolve()
    source = read_csv(root / "feature-entrypoint-map.csv")
    scope = {r["feature_id"]: r["scope_classification"] for r in read_csv(root / "evidence/codex-not-run-phase/not-run-scope-classification.csv")}
    audit_entrypoint = "evidence/codex-not-run-phase/audit-tests/test_included_feature_structural_preconditions.py"
    corrections = []
    for row in source:
        if scope.get(row["feature_id"]) != "INCLUDED_CODEX_RELEVANT":
            continue
        references = product_references(row, checkout)
        referenced_paths = _unique([_reference_path(reference) for reference in references])
        candidates = _unique(
            referenced_paths
            + [p for p in exact_paths(row["feature_path"]) if (checkout / p).exists()]
        )
        if candidates:
            row["discovered_entrypoints"] = "; ".join(candidates)
            row["implementation_files_functions"] = "; ".join(
                _unique(references + candidates)
            )
            row["mapping_confidence"] = "high"
            row["mapping_basis"] = (
                "validated existing implementation references against locked checkout; "
                "supplemented by exact feature-surface paths"
            )
            correction = "exact_repo_surface"
        else:
            row["discovered_entrypoints"] = audit_entrypoint
            row["mapping_confidence"] = "low"
            row["mapping_basis"] = "audit-only structural precondition; behavioral product entrypoint still requires human mapping"
            correction = "audit_only_unresolved_product_entrypoint"
        corrections.append({
            "feature_id": row["feature_id"],
            "feature_path": row["feature_path"],
            "correction_class": correction,
            "corrected_entrypoints": row["discovered_entrypoints"],
            "corrected_implementation": row["implementation_files_functions"],
            "mapping_confidence": row["mapping_confidence"],
            "mapping_basis": row["mapping_basis"],
        })
    out = root / "evidence/codex-not-run-phase"
    write_csv(out / "corrected-feature-entrypoint-map.csv", source, list(source[0]))
    write_csv(out / "entrypoint-corrections.csv", corrections, list(corrections[0]))
    exact = sum(r["correction_class"] == "exact_repo_surface" for r in corrections)
    print(f"included={len(corrections)} exact={exact} audit_only={len(corrections)-exact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
