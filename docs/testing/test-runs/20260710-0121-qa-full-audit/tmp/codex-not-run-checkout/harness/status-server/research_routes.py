"""Research status route module for Solar Harness status-server.

Provides /research/<sid> endpoint that reads from research_eval.*.json files
and displays source_count, evidence_count, claim_count, unsupported_rate,
citation_accuracy, and overall status. No hardcoded fake data.

Usage:
    from status_server.research_routes import build_research_payload, generate_markdown_report
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
SPRINTS_DIR = HARNESS_DIR / "sprints"
REPORTS_DIR = HARNESS_DIR / "reports"


def discover_eval_files(sprints_dir: Path | str, sid: str) -> list[Path]:
    """Find research_eval.*.json files matching the given sprint ID prefix."""
    sprints_dir = Path(sprints_dir)
    patterns = [str(sprints_dir / f"{sid}*research_eval*.json")]
    if sid:
        patterns.append(str(REPORTS_DIR / sid / "*research_eval*.json"))
        patterns.append(str(REPORTS_DIR / f"{sid}*" / "*research_eval*.json"))
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p) for p in glob.glob(pattern))
    unique = sorted({str(path): path for path in paths}.values())
    return unique


def load_eval(path: Path) -> dict[str, Any]:
    """Load a single research_eval JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_artifact_path(raw: Any, base_dir: Path) -> str:
    if not raw:
        return ""
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path)


def _discover_artifacts_for_eval(eval_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    base_dir = eval_path.parent
    output_dir = _resolve_artifact_path(data.get("output_dir"), base_dir)
    output_root = Path(output_dir).expanduser() if output_dir else base_dir
    final_md = _resolve_artifact_path(data.get("final_md"), output_root)
    run_id = str(data.get("run_id") or eval_path.name.replace("-research_eval.json", ""))
    report_ast = output_root / "report_ast.json"
    bibliography = output_root / "final.bibliography.json"
    
    figures_json = output_root / "figures.json"
    figures_jsonl = output_root / "figures.jsonl"
    figures_path = figures_json if figures_json.exists() else figures_jsonl

    artifacts = {
        "eval_json": str(eval_path),
        "output_dir": str(output_root),
        "final_md": final_md,
        "report_ast": str(report_ast),
        "bibliography": str(bibliography),
        "figures": str(figures_path),
    }
    exists = {key: bool(value and Path(value).expanduser().exists()) for key, value in artifacts.items()}
    return {
        "run_id": run_id,
        "artifacts": artifacts,
        "exists": exists,
        "report_ast_sections": _report_ast_section_count(report_ast),
    }


def _report_ast_section_count(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return sum(len(ch.get("sections") or []) for ch in data.get("chapters") or [])
    except Exception:
        return 0


def _load_graph(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _graph_node_status(graph: dict[str, Any], node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    node_results = graph.get("node_results") or {}
    result = node_results.get(node_id) if isinstance(node_results, dict) else {}
    if isinstance(result, dict) and result.get("status"):
        return str(result.get("status"))
    if node.get("status"):
        return str(node.get("status"))
    human_search = node.get("human_search") if isinstance(node.get("human_search"), dict) else {}
    if human_search.get("status") == "waiting":
        return "waiting_human_search"
    return ""


def _node_requires_quality_gate(node: dict[str, Any]) -> bool:
    caps: set[str] = set()
    for key in ("required_capabilities", "capabilities"):
        raw = node.get(key, [])
        if isinstance(raw, str):
            caps.add(raw)
        elif isinstance(raw, list):
            caps.update(str(item) for item in raw if str(item))
    if any(cap.startswith("research.") for cap in caps):
        return True
    if caps & {"citation.verify", "factuality.evaluate", "report.compile", "evidence.extract", "claim.mine"}:
        return True
    haystack = " ".join(str(node.get(k, "")) for k in ("id", "goal", "description")).lower()
    return any(token in haystack for token in (
        "deepresearch",
        "research_eval",
        "report_ast",
        "citation",
        "factuality",
        "claim ledger",
        "evidence ledger",
        "report compiler",
    ))


def discover_quality_gates(sprints_dir: Path | str, sid: str = "", limit: int = 50) -> dict[str, Any]:
    """Project DeepResearch node-level deterministic quality gates from task_graph.json."""
    sprints_dir = Path(sprints_dir)
    pattern = str(sprints_dir / (f"{sid}*.task_graph.json" if sid else "*.task_graph.json"))
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for graph_path in sorted(Path(p) for p in glob.glob(pattern)):
        graph = _load_graph(graph_path)
        if not graph:
            errors.append({"graph": str(graph_path), "error": "invalid_or_empty_graph"})
            continue
        graph_sid = str(graph.get("sprint_id") or graph_path.name.removesuffix(".task_graph.json"))
        nodes = graph.get("nodes") or []
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict) or not _node_requires_quality_gate(node):
                continue
            gate = node.get("research_quality_gate") if isinstance(node.get("research_quality_gate"), dict) else {}
            ok = bool(gate.get("ok")) or str(gate.get("verdict") or "").upper() == "PASS"
            verdict = str(gate.get("verdict") or ("PASS" if ok else ("MISSING" if not gate else "FAIL")))
            status = "ok" if ok else ("missing" if not gate else "failed")
            items.append({
                "sprint_id": graph_sid,
                "node_id": str(node.get("id") or ""),
                "goal": str(node.get("goal") or ""),
                "node_status": _graph_node_status(graph, node) or str(node.get("status") or ""),
                "status": status,
                "ok": ok,
                "verdict": verdict,
                "auto_run": bool(gate.get("auto_run")),
                "errors": gate.get("errors") if isinstance(gate.get("errors"), list) else [],
                "warnings": gate.get("warnings") if isinstance(gate.get("warnings"), list) else [],
                "metrics": gate.get("metrics") if isinstance(gate.get("metrics"), dict) else {},
                "artifacts": gate.get("artifacts") if isinstance(gate.get("artifacts"), dict) else gate.get("discovered_artifacts") if isinstance(gate.get("discovered_artifacts"), dict) else {},
                "graph_path": str(graph_path),
            })

    ok_count = sum(1 for item in items if item.get("ok"))
    missing_count = sum(1 for item in items if item.get("status") == "missing")
    failed_count = sum(1 for item in items if item.get("status") == "failed")
    return {
        "ok": failed_count == 0 and missing_count == 0 and not errors,
        "status": "ok" if items and failed_count == 0 and missing_count == 0 else ("missing" if missing_count else ("failed" if failed_count else "idle")),
        "count": len(items),
        "ok_count": ok_count,
        "missing_count": missing_count,
        "failed_count": failed_count,
        "items": items[:limit],
        "truncated": len(items) > limit,
        "errors": errors,
    }


def discover_human_search_waiting(sprints_dir: Path | str, sid: str = "", limit: int = 20) -> dict[str, Any]:
    """Discover DeepResearch graph nodes waiting for human-provided search results.

    Human-in-loop search is represented in task_graph.json, not research_eval.json.
    This helper keeps /research/<sid> and the main status dashboard aligned with
    the real DAG state instead of forcing users to inspect graph files manually.
    """
    sprints_dir = Path(sprints_dir)
    pattern = str(sprints_dir / (f"{sid}*.task_graph.json" if sid else "*.task_graph.json"))
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for graph_path in sorted(Path(p) for p in glob.glob(pattern)):
        graph = _load_graph(graph_path)
        if not graph:
            errors.append({"graph": str(graph_path), "error": "invalid_or_empty_graph"})
            continue
        graph_sid = str(graph.get("sprint_id") or graph_path.name.removesuffix(".task_graph.json"))
        nodes = graph.get("nodes") or []
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            human_search = node.get("human_search") if isinstance(node.get("human_search"), dict) else {}
            status = _graph_node_status(graph, node)
            if status != "waiting_human_search" and human_search.get("status") != "waiting":
                continue

            handoff_md = str(human_search.get("handoff_md") or "")
            results_md = str(human_search.get("results_md") or "")
            handoff_path = Path(handoff_md).expanduser() if handoff_md else None
            results_path = Path(results_md).expanduser() if results_md else None
            items.append({
                "sprint_id": graph_sid,
                "node_id": str(node.get("id") or ""),
                "goal": str(node.get("goal") or ""),
                "status": "waiting_human_search",
                "provider": str(human_search.get("provider") or "human"),
                "run_id": str(human_search.get("run_id") or ""),
                "db_path": str(human_search.get("db_path") or ""),
                "handoff_md": handoff_md,
                "results_md": results_md,
                "import_command": str(human_search.get("import_command") or ""),
                "handoff_exists": bool(handoff_path and handoff_path.exists()),
                "results_exists": bool(results_path and results_path.exists()),
                "ready_to_import": bool(results_path and results_path.exists()),
                "graph_path": str(graph_path),
            })

    return {
        "ok": not errors,
        "status": "waiting" if items else "idle",
        "count": len(items),
        "items": items[:limit],
        "truncated": len(items) > limit,
        "errors": errors,
    }


def _derive_fallback_level(metrics: dict[str, Any]) -> str:
    """Map usage_source + estimated + fallback_reason to S02-FALLBACK levels L1-L4."""
    usage_source = metrics.get("usage_source") or metrics.get("token_usage_source") or ""
    estimated = metrics.get("estimated")
    if estimated is None:
        estimated = metrics.get("token_usage_is_estimated", False)
    fallback_reason = metrics.get("fallback_reason") or ""

    if usage_source == "provider_usage_ledger" and not estimated:
        return "L1"
    if usage_source == "hybrid":
        return "L2"
    if usage_source == "estimated" or usage_source.startswith("estimated_"):
        if fallback_reason in ("cli_no_usage", "cli_rate_limit"):
            return "L3"
        return "L4"
    return "unknown"


def _metric_bool(metrics: dict[str, Any], primary: str, legacy: str, default: bool | None = None) -> bool | None:
    if primary in metrics:
        return bool(metrics.get(primary))
    if legacy in metrics:
        return bool(metrics.get(legacy))
    return default


def _metric_int(metrics: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key not in metrics:
            continue
        try:
            return int(metrics.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_execution_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    if not metrics:
        return {
            "usage_source": None,
            "estimated": None,
            "fallback_reason": None,
            "state": "unknown",
            "fallback_level": None,
            "word_count": None,
            "total_tokens": None,
        }
    usage_source = metrics.get("usage_source") or metrics.get("token_usage_source")
    estimated = _metric_bool(metrics, "estimated", "token_usage_is_estimated", False)
    return {
        "usage_source": usage_source,
        "estimated": estimated,
        "fallback_reason": metrics.get("fallback_reason"),
        "state": metrics.get("state", "unknown"),
        "fallback_level": _derive_fallback_level(metrics),
        "word_count": _metric_int(metrics, "word_count", "document_word_count"),
        "total_tokens": _metric_int(metrics, "total_tokens", "total_token_consumption"),
    }


def _load_execution_metrics(sprints_dir: Path, sid: str, runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Load *execution_metrics*.json for sid; supports embedded, sprint-root, and report-dir outputs."""
    for run in reversed(runs or []):
        embedded = run.get("execution_metrics") if isinstance(run, dict) else None
        if isinstance(embedded, dict) and embedded:
            return embedded

    candidates = sorted(Path(p) for p in glob.glob(str(sprints_dir / f"{sid}*execution_metrics*.json")))
    for run in runs or []:
        artifacts = run.get("artifacts") if isinstance(run, dict) else {}
        if not isinstance(artifacts, dict):
            continue
        output_dir = artifacts.get("output_dir")
        if output_dir:
            candidates.append(Path(str(output_dir)).expanduser() / "research_execution_metrics.json")
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _figures_summary(figures_path_str: str, output_dir_str: str) -> dict[str, Any]:
    """Parse figures from figures.json or figures.jsonl and validate their grounding against claims and evidence."""
    if not figures_path_str or not Path(figures_path_str).exists():
        return {
            "count": 0,
            "grounded_count": 0,
            "ungrounded_count": 0,
            "items": []
        }
        
    path = Path(figures_path_str)
    figures_data = []
    try:
        if path.name.endswith(".jsonl"):
            # read JSONL
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    figures_data.append(json.loads(line))
        else:
            # read JSON array
            figures_data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "count": 0,
            "grounded_count": 0,
            "ungrounded_count": 0,
            "items": [],
            "error": "figures_file_corrupt"
        }

    if not isinstance(figures_data, list):
        return {
            "count": 0,
            "grounded_count": 0,
            "ungrounded_count": 0,
            "items": [],
            "error": "figures_format_invalid"
        }

    # Load claims
    claim_ids = set()
    claims_path = Path(output_dir_str) / "claims.jsonl"
    if claims_path.exists():
        try:
            for line in claims_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("id"):
                        claim_ids.add(row["id"])
                    elif row.get("claim_id"):
                        claim_ids.add(row["claim_id"])
        except Exception:
            pass

    # Load evidence
    evidence_ids = set()
    evidence_path = Path(output_dir_str) / "evidence.jsonl"
    if evidence_path.exists():
        try:
            for line in evidence_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("id"):
                        evidence_ids.add(row["id"])
                    elif row.get("evidence_id"):
                        evidence_ids.add(row["evidence_id"])
        except Exception:
            pass

    valid_ids = claim_ids | evidence_ids
    items = []
    grounded_count = 0
    ungrounded_count = 0

    for fig in figures_data:
        if not isinstance(fig, dict):
            continue
        fig_id = fig.get("figure_id") or fig.get("id") or "unknown"
        title = fig.get("title") or "Untitled"
        fig_type = fig.get("figure_type") or fig.get("type") or "unknown"
        grounding_ids = fig.get("grounding_ids") or []
        spec_data = fig.get("spec_data") or {}

        # Validate grounding
        errors = []
        if not fig.get("figure_id") and not fig.get("id"):
            errors.append("figure_id_missing")
        if not fig.get("title"):
            errors.append("figure_title_missing")
        if fig_type not in {"architecture_diagram", "timeline"}:
            errors.append(f"figure_type_invalid:{fig_type}")
        if not grounding_ids:
            errors.append("figure_grounding_empty")
        else:
            for gid in grounding_ids:
                if gid not in valid_ids:
                    errors.append(f"figure_grounding_unresolved:{gid}")
        
        if isinstance(spec_data, dict):
            if fig_type == "architecture_diagram":
                nodes = spec_data.get("nodes") or []
                edges = spec_data.get("edges") or []
                if not nodes:
                    errors.append("figure_architecture_nodes_missing")
                if not edges:
                    errors.append("figure_architecture_edges_missing")
                for node in nodes:
                    if isinstance(node, dict) and node.get("grounding_id"):
                        if node["grounding_id"] not in grounding_ids or node["grounding_id"] not in valid_ids:
                            errors.append(f"figure_component_grounding_invalid:{node['grounding_id']}")
                for edge in edges:
                    if isinstance(edge, dict) and edge.get("grounding_id"):
                        if edge["grounding_id"] not in grounding_ids or edge["grounding_id"] not in valid_ids:
                            errors.append(f"figure_component_grounding_invalid:{edge['grounding_id']}")
            elif fig_type == "timeline":
                events = spec_data.get("events") or []
                if not events:
                    errors.append("figure_timeline_events_missing")
                for event in events:
                    if isinstance(event, dict) and event.get("grounding_id"):
                        if event["grounding_id"] not in grounding_ids or event["grounding_id"] not in valid_ids:
                            errors.append(f"figure_component_grounding_invalid:{event['grounding_id']}")

        is_grounded = len(errors) == 0
        if is_grounded:
            grounded_count += 1
        else:
            ungrounded_count += 1

        items.append({
            "figure_id": fig_id,
            "title": title,
            "type": fig_type,
            "status": "grounded" if is_grounded else "ungrounded",
            "errors": errors
        })

    return {
        "count": len(figures_data),
        "grounded_count": grounded_count,
        "ungrounded_count": ungrounded_count,
        "items": items
    }


def build_research_payload(sprints_dir: Path | str | None, sid: str) -> dict[str, Any]:
    """Build JSON payload for GET /research/<sid>.

    Reads from research_eval.*.json files. Returns zeroed defaults if no files found.
    """
    sprints_dir = Path(sprints_dir) if sprints_dir else SPRINTS_DIR
    eval_files = discover_eval_files(sprints_dir, sid)

    total_sources = 0
    total_evidence = 0
    total_claims = 0
    total_unsupported = 0
    total_key_claims = 0
    total_span_matches = 0
    total_spans = 0
    overall_status = "no_data"
    eval_count = len(eval_files)
    runs: list[dict[str, Any]] = []

    for ef in eval_files:
        data = load_eval(ef)
        total_sources += data.get("source_count", 0)
        total_evidence += data.get("evidence_count", 0)
        total_claims += data.get("claim_count", 0)
        total_unsupported += data.get("unsupported_claims", 0)
        total_key_claims += data.get("total_key_claims", 0)
        total_span_matches += data.get("span_matches", 0)
        total_spans += data.get("total_spans", 0)

        status = data.get("status", "")
        if status == "failed":
            overall_status = "failed"
        elif status == "running" and overall_status != "failed":
            overall_status = "running"
        elif status == "passed" and overall_status not in ("failed", "running"):
            overall_status = "passed"
        elif status == "partial" and overall_status not in ("failed", "running", "passed"):
            overall_status = "partial"
        discovered = _discover_artifacts_for_eval(ef, data)
        embedded_metrics = data.get("execution_metrics") if isinstance(data.get("execution_metrics"), dict) else {}
        run_metrics = _normalize_execution_metrics(embedded_metrics)
        fig_summary = _figures_summary(discovered["artifacts"].get("figures"), discovered["artifacts"].get("output_dir"))
        runs.append({
            "run_id": discovered["run_id"],
            "status": status or "unknown",
            "source_count": data.get("source_count", 0),
            "evidence_count": data.get("evidence_count", 0),
            "claim_count": data.get("claim_count", 0),
            "section_count": data.get("section_count", 0),
            "check_count": data.get("check_count", 0),
            "unsupported_rate": data.get("unsupported_rate", 0.0),
            "citation_accuracy": data.get("citation_accuracy", 0.0),
            "artifacts": discovered["artifacts"],
            "artifact_exists": discovered["exists"],
            "report_ast_sections": discovered["report_ast_sections"],
            "execution_metrics": embedded_metrics,
            "figures_summary": fig_summary,
            **run_metrics,
        })

    if eval_count > 0 and overall_status == "no_data":
        overall_status = "data_loaded"

    unsupported_rate = round(total_unsupported / total_key_claims, 4) if total_key_claims > 0 else 0.0
    citation_accuracy = round(total_span_matches / total_spans, 4) if total_spans > 0 else 0.0
    metrics_summary = _normalize_execution_metrics(_load_execution_metrics(sprints_dir, sid, runs))

    return {
        "sid": sid,
        "source_count": total_sources,
        "evidence_count": total_evidence,
        "claim_count": total_claims,
        "unsupported_rate": unsupported_rate,
        "citation_accuracy": citation_accuracy,
        "status": overall_status,
        "eval_files": eval_count,
        "runs": runs,
        "latest": runs[-1] if runs else {},
        "human_search": discover_human_search_waiting(sprints_dir, sid),
        "quality_gates": discover_quality_gates(sprints_dir, sid),
        "figures_summary": runs[-1].get("figures_summary") if runs else {
            "count": 0,
            "grounded_count": 0,
            "ungrounded_count": 0,
            "items": []
        },
        **metrics_summary,
    }


def render_html_report(sprints_dir: Path | str | None, sid: str) -> str:
    """Render human-readable HTML for /research/<sid>?format=html."""
    data = build_research_payload(sprints_dir, sid)
    template = (Path(__file__).parent / "templates" / "research.html").read_text(encoding="utf-8")
    values = dict(data)
    values["unsupported_rate_pct"] = f"{data.get('unsupported_rate', 0.0) * 100:.1f}"
    values["citation_accuracy_pct"] = f"{data.get('citation_accuracy', 0.0) * 100:.1f}"
    for key in ("word_count", "total_tokens", "usage_source", "estimated", "state", "fallback_level"):
        if values.get(key) is None:
            values[key] = "N/A"
    for key, value in values.items():
        template = template.replace("{" + str(key) + "}", str(value))
    return template


def generate_markdown_report(sprints_dir: Path | str | None, sid: str) -> str:
    """Generate markdown report for activation-proof --research <sid>."""
    data = build_research_payload(sprints_dir, sid)
    lines = [
        f"# Research Status Report: {sid}",
        "",
        f"**Status**: {data['status']}",
        f"**Eval Files**: {data['eval_files']}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Source Count | {data['source_count']} |",
        f"| Evidence Count | {data['evidence_count']} |",
        f"| Claim Count | {data['claim_count']} |",
        f"| Unsupported Rate | {data['unsupported_rate']:.2%} |",
        f"| Citation Accuracy | {data['citation_accuracy']:.2%} |",
        "",
    ]
    runs = data.get("runs") or []
    if runs:
        lines.extend([
            "## Research Artifacts",
            "",
            "| Run | Status | Final | ReportAST | Eval |",
            "|-----|--------|-------|-----------|------|",
        ])
        for run in runs:
            artifacts = run.get("artifacts") or {}
            exists = run.get("artifact_exists") or {}
            lines.append(
                f"| `{run.get('run_id', '')}` | {run.get('status', '')} | "
                f"`{artifacts.get('final_md', '')}` ({exists.get('final_md')}) | "
                f"`{artifacts.get('report_ast', '')}` ({exists.get('report_ast')}) | "
                f"`{artifacts.get('eval_json', '')}` ({exists.get('eval_json')}) |"
            )
        lines.append("")
    quality_gates = data.get("quality_gates") or {}
    gate_items = quality_gates.get("items") or []
    if gate_items:
        lines.extend([
            "## DeepDive Quality Gates",
            "",
            "| Node | Status | Verdict | Auto Run | Errors |",
            "|------|--------|---------|----------|--------|",
        ])
        for item in gate_items:
            errors = ", ".join(str(e) for e in (item.get("errors") or []))
            lines.append(
                f"| {item.get('node_id', '')} | {item.get('status', '')} | "
                f"{item.get('verdict', '')} | {item.get('auto_run', False)} | {errors} |"
            )
        lines.append("")
    human_search = data.get("human_search") or {}
    items = human_search.get("items") or []
    if items:
        lines.extend([
            "## Human Search Waiting",
            "",
            "| Node | Handoff | Results | Import Command |",
            "|------|---------|---------|----------------|",
        ])
        for item in items:
            lines.append(
                f"| {item.get('node_id', '')} | `{item.get('handoff_md', '')}` | "
                f"`{item.get('results_md', '')}` | `{item.get('import_command', '')}` |"
            )
        lines.append("")

    figures_summary = data.get("figures_summary") or {}
    if figures_summary.get("count", 0) > 0:
        lines.extend([
            "## Research Figures Summary",
            "",
            "| Figure ID | Title | Type | Grounding Status | Errors |",
            "|-----------|-------|------|------------------|--------|",
        ])
        for fig in figures_summary.get("items", []):
            err_str = ", ".join(fig.get("errors", [])) or "None"
            lines.append(
                f"| {fig.get('figure_id')} | {fig.get('title')} | "
                f"{fig.get('type')} | {fig.get('status')} | {err_str} |"
            )
        lines.append("")

    return "\n".join(lines)
