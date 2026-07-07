#!/usr/bin/env python3
"""Generate final reader-facing artifacts for the AutoSci native E2E run."""

from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[6]
HARNESS_ROOT = REPO_ROOT / "harness"
OLD_ROOT_REL = "artifacts/autosci/runs/e2e-doc-literature-20260707"
NEW_ROOT_REL = "artifacts/autosci/runs/e2e-doc-literature-20260707-idea-chain"
MAIN_BATCH_REL = f"{NEW_ROOT_REL}/autosci_native_batch"
PATCH_BATCH_REL = f"{NEW_ROOT_REL}/autosci_native_patch"
FINAL_REL = f"{NEW_ROOT_REL}/autosci_native_final"
FINAL_ROOT = HARNESS_ROOT / FINAL_REL
PATCH_IDS = {"cc-01", "cu-05", "ghc-01", "r17"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(rel_path: str, payload: Any) -> None:
    path = FINAL_ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(rel_path: str, body: str) -> None:
    path = FINAL_ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def copy_text_file(source: Path, rel_dest: str) -> bool:
    if not source.exists():
        return False
    dest = FINAL_ROOT / rel_dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return True


def rel_to_harness(rel: str) -> Path:
    return HARNESS_ROOT / rel


def item_sort_key(item_id: str) -> tuple[int, int, str]:
    prefixes = {"cc": 0, "cu": 1, "ghc": 2, "r": 3}
    if "-" in item_id:
        prefix, number = item_id.rsplit("-", 1)
    else:
        prefix, number = item_id[0], item_id[1:]
    try:
        numeric = int(number)
    except ValueError:
        numeric = 0
    return (prefixes.get(prefix, 99), numeric, item_id)


def discover_items() -> list[str]:
    source_dir = HARNESS_ROOT / OLD_ROOT_REL / "sources"
    return sorted((path.stem for path in source_dir.glob("*.md")), key=item_sort_key)


def batch_rel_for_item(item_id: str) -> str:
    return PATCH_BATCH_REL if item_id in PATCH_IDS else MAIN_BATCH_REL


def pick(path: Path) -> dict[str, Any]:
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def first_verdict(verdict_payload: dict[str, Any]) -> dict[str, Any]:
    verdicts = ((verdict_payload.get("outputs") or {}).get("verdicts") or [])
    return verdicts[0] if verdicts and isinstance(verdicts[0], dict) else {}


def idea_eval_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evaluations = ((payload.get("outputs") or {}).get("evaluations") or [])
    return {
        str(item.get("idea_id")): item
        for item in evaluations
        if isinstance(item, dict) and item.get("idea_id")
    }


def item_paths(item_id: str) -> dict[str, str]:
    base = f"{batch_rel_for_item(item_id)}/items/{item_id}"
    return {
        "base": base,
        "summary": f"{base}/batch_item_summary.json",
        "metadata": f"{OLD_ROOT_REL}/metadata/{item_id}.json",
        "source": f"{OLD_ROOT_REL}/sources/{item_id}.md",
        "ingest": f"{base}/ingest/autosci_skill_run.json",
        "research": f"{base}/research/autosci_skill_run.json",
        "review": f"{base}/review/artifact_review.json",
        "ideate_report": f"{base}/ideate/ideate_pipeline_report.json",
        "ideate_boundary": f"{base}/ideate/ideate_final_promotion_boundary.json",
        "model_ideas": f"{base}/ideate/generate_ideas_model_stdout.json",
        "idea_eval": f"{base}/ideate/idea_evaluation.json",
        "research_claims": f"{base}/ideate/research_claims.json",
        "research_method": f"{base}/ideate/research_method.json",
        "experiment_plan": f"{base}/experiment/experiment_plan.json",
        "experiment_result": f"{base}/experiment/experiment_result.json",
        "claim_verdict": f"{base}/experiment/claim_verdict.json",
        "code_evidence": f"{base}/experiment/code_evidence_map.json",
        "runtime_evidence": f"{base}/experiment/run_experiment_runtime_evidence.json",
        "experiment_status": f"{base}/status/experiment_status.json",
    }


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def potential_from_evidence(
    evaluation: dict[str, Any],
    *,
    selected: bool,
    experiment_outcome: Any,
) -> tuple[float, str, list[str]]:
    """Derive an explainable potential score from AutoSci evidence.

    This is not a probability. It is a bounded presentation score so the final
    report can rank ideas without inventing a stronger statistical claim than
    the run produced.
    """
    novelty = as_float(evaluation.get("novelty"))
    feasibility = as_float(evaluation.get("feasibility"))
    review_score = as_float(evaluation.get("review_score"))
    acceptance = evaluation.get("final_acceptance_boundary") or {}
    final_ready = bool(acceptance.get("final_acceptance_ready"))
    recommendation = str(evaluation.get("recommendation") or "").lower()
    outcome = str(experiment_outcome or "").lower()

    score = 0.0
    reasons: list[str] = []
    if final_ready:
        score += 0.20
        reasons.append("final_acceptance_ready")
    if novelty:
        score += min(max(novelty, 0.0), 1.0) * 0.20
        reasons.append(f"novelty={novelty:.2f}")
    if feasibility:
        score += min(max(feasibility, 0.0), 1.0) * 0.25
        reasons.append(f"feasibility={feasibility:.2f}")
    if review_score:
        score += min(max(review_score, 0.0), 1.0) * 0.15
        reasons.append(f"review_score={review_score:.2f}")
    if selected:
        score += 0.10
        reasons.append("selected_for_exp")
        if outcome == "supports":
            score += 0.15
            reasons.append("experiment_supports")
        elif outcome == "partially_supports":
            score += 0.08
            reasons.append("experiment_partially_supports")
        elif outcome == "inconclusive":
            score += 0.02
            reasons.append("experiment_inconclusive")
    if recommendation == "reject":
        score -= 0.15
        reasons.append("recommendation=reject")
    elif recommendation == "revise":
        score -= 0.05
        reasons.append("recommendation=revise")
    elif recommendation in {"accept", "promote"}:
        score += 0.05
        reasons.append(f"recommendation={recommendation}")

    score = round(min(max(score, 0.0), 1.0), 3)
    if score >= 0.70:
        label = "higher"
    elif score >= 0.45:
        label = "medium"
    else:
        label = "lower"
    return score, label, reasons


def clean_source_title(title: Any) -> str:
    text = str(title or "").strip()
    lower = text.lower()
    if lower == "overview - claude code docs":
        return "Claude Code overview documentation"
    if lower == "plans & pricing | claude by anthropic":
        return "Claude pricing and plan documentation"
    replacements = [
        " - Claude Code Docs",
        " - Claude Platform Docs",
        " | Claude by Anthropic",
        " | AI Coding Agent, Terminal, IDE",
    ]
    for token in replacements:
        text = text.replace(token, "")
    return " ".join(text.split()) or "source record"


def path_family(generation_path: Any) -> str:
    path = str(generation_path or "").lower()
    if "incremental" in path:
        return "incremental"
    if "combination" in path:
        return "combination"
    if "innovation" in path:
        return "innovation"
    if "cross-domain" in path or "transfer" in path:
        return "cross-domain"
    return "landscape"


def clean_idea_tail(title: Any) -> str:
    text = " ".join(str(title or "").strip().split())
    lower = text.lower()
    formula_terms = [
        "landscape-driven",
        "landscape driven",
        "landscape",
        "validate ",
        "validation",
    ]
    if not text or any(term in lower for term in formula_terms):
        return ""
    return text


def idea_display_title(meta_title: Any, idea_title: Any, generation_path: Any, selected: bool) -> str:
    """Create a reader-facing title while preserving raw AutoSci ids separately."""
    source = clean_source_title(meta_title)
    raw = str(idea_title or "").strip()
    family = path_family(generation_path)
    templates = {
        "landscape": f"{source} evidence check",
        "incremental": f"{source} related-source enrichment",
        "combination": f"{source} cross-source synthesis",
        "innovation": f"{source} validation use cases",
        "cross-domain": f"{source} transfer pattern",
    }
    title = templates[family]
    tail = clean_idea_tail(raw)
    if selected and tail:
        title = f"{title}: {tail}"
    return clip(title, 120)


def build() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    methods: list[dict[str, Any]] = []
    ideas: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    graph_nodes: dict[str, dict[str, Any]] = {}
    graph_edges: list[dict[str, str]] = []

    def add_node(node_id: str, label: str, kind: str, **extra: Any) -> None:
        graph_nodes[node_id] = {"id": node_id, "label": label, "kind": kind, **extra}

    def add_edge(source: str, target: str, edge_type: str, label: str | None = None) -> None:
        graph_edges.append({
            "source": source,
            "target": target,
            "type": edge_type,
            "label": label or edge_type.replace("_", " "),
        })

    for doc_id, doc_label in [
        ("doc:claude-cursor-copilot-2026", "Claude Code vs Cursor vs GitHub Copilot in 2026"),
        ("doc:loop-harness-resource-radar", "Loop & Harness Engineering Resource Radar"),
    ]:
        add_node(doc_id, doc_label, "document")

    for item_id in discover_items():
        paths = item_paths(item_id)
        meta = pick(rel_to_harness(paths["metadata"]))
        summary = pick(rel_to_harness(paths["summary"]))
        claims_payload = pick(rel_to_harness(paths["research_claims"]))
        methods_payload = pick(rel_to_harness(paths["research_method"]))
        model_payload = pick(rel_to_harness(paths["model_ideas"]))
        eval_payload = pick(rel_to_harness(paths["idea_eval"]))
        exp_result = pick(rel_to_harness(paths["experiment_result"]))
        verdict_payload = pick(rel_to_harness(paths["claim_verdict"]))
        code_payload = pick(rel_to_harness(paths["code_evidence"]))
        status_payload = pick(rel_to_harness(paths["experiment_status"]))
        boundary = pick(rel_to_harness(paths["ideate_boundary"]))
        verdict = first_verdict(verdict_payload)
        evaluations = idea_eval_by_id(eval_payload)
        item_doc = str(meta.get("doc_slug") or "unknown-doc")
        doc_node = f"doc:{item_doc}"
        paper_node = f"paper:{item_id}"
        add_node(
            paper_node,
            f"{item_id}: {clean_source_title(meta.get('title') or item_id)}",
            "paper",
            item_id=item_id,
            doc_slug=item_doc,
            source_title=meta.get("title"),
        )
        add_edge(doc_node, paper_node, "contains_source")

        item_record = {
            "item_id": item_id,
            "batch_rel": batch_rel_for_item(item_id),
            "title": meta.get("title"),
            "doc_slug": item_doc,
            "source_type": meta.get("source_type"),
            "expected_outcome": meta.get("expected_outcome"),
            "confidence": meta.get("confidence"),
            "credibility": meta.get("credibility"),
            "relevance": meta.get("relevance"),
            "ideate_final_promotion_ready": boundary.get("final_promotion_ready"),
            "selected_idea_id": summary.get("claim_id"),
            "experiment_id": summary.get("experiment_id"),
            "verdict": summary.get("verdict"),
            "experiment_outcome": summary.get("experiment_outcome"),
            "final_verdict_ready": summary.get("final_verdict_ready"),
            "final_verdict_boundary_status": summary.get("final_verdict_boundary_status"),
            "artifact_paths": paths,
        }
        items.append(item_record)

        for claim in ((claims_payload.get("outputs") or {}).get("claims") or []):
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or f"{item_id}-claim")
            record = {"item_id": item_id, **claim}
            claims.append(record)
            claim_node = f"claim:{item_id}:{claim_id}"
            add_node(claim_node, claim_id, "claim", item_id=item_id, text=str(claim.get("text") or "")[:220])
            add_edge(paper_node, claim_node, "extracts_claim")

        for method in ((methods_payload.get("outputs") or {}).get("methods") or []):
            if isinstance(method, dict):
                method_record = {"item_id": item_id, **method}
                methods.append(method_record)
                method_id = str(method.get("method_id") or f"{item_id}-method")
                method_node = f"method:{item_id}:{method_id}"
                add_node(
                    method_node,
                    f"{item_id}: {method.get('name') or method_id}",
                    "method",
                    item_id=item_id,
                    summary=str(method.get("summary") or "")[:240],
                )
                add_edge(paper_node, method_node, "extracts_method")

        for idea in ((model_payload.get("outputs") or {}).get("ideas") or []):
            if not isinstance(idea, dict):
                continue
            idea_id = str(idea.get("idea_id") or f"{item_id}-idea")
            eval_record = evaluations.get(idea_id, {})
            acceptance = eval_record.get("final_acceptance_boundary") or {}
            selected_for_experiment = idea_id == summary.get("claim_id")
            display_title = idea_display_title(
                meta.get("title"),
                idea.get("title"),
                idea.get("generation_path"),
                selected_for_experiment,
            )
            potential_score, potential_label, potential_reasons = potential_from_evidence(
                eval_record,
                selected=selected_for_experiment,
                experiment_outcome=summary.get("experiment_outcome") if selected_for_experiment else None,
            )
            idea_record = {
                "item_id": item_id,
                "idea_id": idea_id,
                "title": idea.get("title"),
                "display_title": display_title,
                "generation_path": idea.get("generation_path"),
                "hypothesis": idea.get("hypothesis"),
                "approach": idea.get("approach"),
                "origin_evidence_ids": idea.get("origin_evidence_ids") or [],
                "novelty": eval_record.get("novelty"),
                "novelty_label": eval_record.get("novelty_label"),
                "feasibility": eval_record.get("feasibility"),
                "review_score": eval_record.get("review_score"),
                "recommendation": eval_record.get("recommendation"),
                "final_acceptance_ready": acceptance.get("final_acceptance_ready"),
                "selected_for_experiment": selected_for_experiment,
                "experiment_outcome": summary.get("experiment_outcome") if selected_for_experiment else None,
                "verdict": summary.get("verdict") if selected_for_experiment else None,
                "potential_score": potential_score,
                "potential_label": potential_label,
                "potential_basis": potential_reasons,
                "artifact_paths": {
                    "model_stdout": paths["model_ideas"],
                    "idea_evaluation": paths["idea_eval"],
                },
            }
            ideas.append(idea_record)
            add_node(
                f"idea:{idea_id}",
                display_title,
                "idea",
                item_id=item_id,
                raw_title=idea.get("title"),
                generation_path=str(idea.get("generation_path") or ""),
                selected=selected_for_experiment,
                potential_score=potential_score,
                potential_label=potential_label,
                recommendation=str(eval_record.get("recommendation") or ""),
            )
            add_edge(paper_node, f"idea:{idea_id}", "grounds_idea")
            if selected_for_experiment:
                exp_id = str(summary.get("experiment_id") or f"exp-{idea_id}")
                exp_node = f"experiment:{exp_id}"
                verdict_node = f"verdict:{item_id}"
                code_node = f"code:{item_id}"
                add_node(exp_node, f"{item_id}: {summary.get('experiment_outcome')}", "experiment", item_id=item_id, outcome=summary.get("experiment_outcome"))
                add_node(code_node, f"{item_id} validation code", "code", item_id=item_id)
                add_node(verdict_node, f"{item_id}: {summary.get('verdict')}", "verdict", item_id=item_id, final_ready=summary.get("final_verdict_ready"))
                add_edge(f"idea:{idea_id}", exp_node, "validated_by")
                add_edge(exp_node, code_node, "runs_code")
                add_edge(exp_node, verdict_node, "evaluates_to")

        run_result = (exp_result.get("outputs") or {}).get("result") or {}
        code_mappings = (code_payload.get("outputs") or {}).get("mappings") or []
        validations.append(
            {
                "item_id": item_id,
                "idea_id": summary.get("claim_id"),
                "experiment_id": summary.get("experiment_id"),
                "command_run": run_result.get("command_run"),
                "exit_code": run_result.get("exit_code"),
                "outcome": run_result.get("outcome"),
                "verdict": verdict.get("verdict"),
                "final_verdict_ready": verdict.get("final_verdict_ready"),
                "code_mappings": code_mappings,
                "artifact_paths": {
                    "validation_bundle": f"{FINAL_REL}/validation_code_bundle/items/{item_id}",
                    "runner_script": f"{FINAL_REL}/validation_code_bundle/items/{item_id}/run_validation.sh",
                    "validator_source": f"{FINAL_REL}/validation_code_bundle/validator/validate_literature_item.py",
                    "experiment_plan": paths["experiment_plan"],
                    "experiment_result": paths["experiment_result"],
                    "claim_verdict": paths["claim_verdict"],
                    "code_evidence_map": paths["code_evidence"],
                    "runtime_evidence": paths["runtime_evidence"],
                    "experiment_status": paths["experiment_status"],
                },
                "status_state": ((status_payload.get("outputs") or {}).get("status_report") or {}).get("state"),
            }
        )

    ideas_by_path: dict[str, list[str]] = defaultdict(list)
    for idea in ideas:
        ideas_by_path[str(idea.get("generation_path") or "unknown")].append(str(idea["idea_id"]))
    for path, idea_ids in ideas_by_path.items():
        hub = f"path:{path}"
        add_node(hub, path, "generation_path")
        for idea_id in idea_ids:
            add_edge(hub, f"idea:{idea_id}", "path_member")

    status = {
        "schema": "autosci_native_final_outputs.v1",
        "generated_at": now_iso(),
        "source_batches": {
            "main": MAIN_BATCH_REL,
            "patch": PATCH_BATCH_REL,
            "patch_item_ids": sorted(PATCH_IDS),
        },
        "item_count": len(items),
        "claim_count": len(claims),
        "method_count": len(methods),
        "idea_count": len(ideas),
        "selected_idea_count": sum(1 for item in ideas if item.get("selected_for_experiment")),
        "validation_count": len(validations),
        "ideate_final_promotion_ready_count": sum(1 for item in items if item.get("ideate_final_promotion_ready") is True),
        "final_verdict_ready_count": sum(1 for item in items if item.get("final_verdict_ready") is True),
        "verdict_counts": dict(Counter(str(item.get("verdict")) for item in items)),
        "experiment_outcome_counts": dict(Counter(str(item.get("experiment_outcome")) for item in items)),
    }
    graph = {
        "schema": "omegawiki_graph.v1",
        "nodes": list(graph_nodes.values()),
        "edges": graph_edges,
    }
    status["graph_node_count"] = len(graph["nodes"])
    status["graph_edge_count"] = len(graph["edges"])
    status["validation_code_bundle"] = f"{FINAL_REL}/validation_code_bundle"
    return {
        "status": status,
        "items": items,
        "claims": claims,
        "methods": methods,
        "ideas": ideas,
        "validations": validations,
        "graph": graph,
    }


def table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = [
        "| " + " | ".join(str(cell).replace("\n", " ").replace("|", "\\|") for cell in row) + " |"
        for row in rows[1:]
    ]
    return "\n".join([header, sep, *body])


def clip(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."


def render_validation_code_bundle(data: dict[str, Any]) -> None:
    validator_rel = f"{OLD_ROOT_REL}/tools/validate_literature_item.py"
    copy_text_file(rel_to_harness(validator_rel), "validation_code_bundle/validator/validate_literature_item.py")

    manifest: dict[str, Any] = {
        "schema": "autosci_validation_code_bundle.v1",
        "validator_source": "validation_code_bundle/validator/validate_literature_item.py",
        "runner_count": 0,
        "items": [],
        "notes": [
            "Each item directory contains the concrete runner and copied exp-* evidence used by the final report.",
            "Runner commands are the commands recorded by AutoSci exp-run runtime evidence.",
            "These are local attached-document validators; network_fetch=not_requested is preserved from runtime logs.",
        ],
    }
    copied_names = [
        "experiment_plan.json",
        "experiment_result.json",
        "claim_verdict.json",
        "code_evidence_map.json",
        "run_experiment_runtime_evidence.json",
        "run_experiment_result.json",
        "run_experiment_executor_stdout.txt",
        "run_experiment_executor_stderr.txt",
        "run_experiment_gate_policy_allowlist.json",
        "run_experiment_gate_policy_decision.json",
        "experiment_status.json",
    ]
    for validation in data["validations"]:
        item_id = str(validation["item_id"])
        paths = item_paths(item_id)
        item_dir = f"validation_code_bundle/items/{item_id}"
        command = str(validation.get("command_run") or "")
        runner = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"cd {json.dumps(str(HARNESS_ROOT))}\n"
            f"{command}\n"
        )
        runner_rel = f"{item_dir}/run_validation.sh"
        write_text(runner_rel, runner)
        (FINAL_ROOT / runner_rel).chmod(0o755)
        copy_text_file(rel_to_harness(paths["metadata"]), f"{item_dir}/input_metadata.json")
        copy_text_file(rel_to_harness(paths["source"]), f"{item_dir}/input_source.md")
        experiment_dir = rel_to_harness(paths["base"]) / "experiment"
        copied: list[str] = []
        for name in copied_names:
            source = experiment_dir / name
            if copy_text_file(source, f"{item_dir}/{name}"):
                copied.append(name)
        for source in sorted(experiment_dir.glob("*.allowlist.json")):
            if copy_text_file(source, f"{item_dir}/{source.name}"):
                copied.append(source.name)
        for source in sorted(experiment_dir.glob("exp-*.log")):
            if copy_text_file(source, f"{item_dir}/{source.name}"):
                copied.append(source.name)
        item_manifest = {
            "item_id": item_id,
            "idea_id": validation.get("idea_id"),
            "experiment_id": validation.get("experiment_id"),
            "outcome": validation.get("outcome"),
            "verdict": validation.get("verdict"),
            "exit_code": validation.get("exit_code"),
            "runner_script": f"{item_dir}/run_validation.sh",
            "command_run": command,
            "copied_artifacts": copied,
        }
        write_json(f"{item_dir}/manifest.json", item_manifest)
        manifest["items"].append(item_manifest)
        manifest["runner_count"] += 1

    write_json("validation_code_bundle/manifest.json", manifest)
    rows = [["Item", "Idea", "Experiment", "Outcome", "Exit", "Runner"]]
    for item in manifest["items"]:
        rows.append([
            item["item_id"],
            str(item.get("idea_id") or ""),
            str(item.get("experiment_id") or ""),
            str(item.get("outcome") or ""),
            str(item.get("exit_code")),
            item["runner_script"],
        ])
    readme = f"""# AutoSci Validation Code Bundle

This directory exposes the concrete validation code and exp-* byproducts used
by the final AutoSci native E2E report.

## Shared Validator

- `validator/validate_literature_item.py`

## Per-Item Runners

{table(rows)}

Each item folder also contains copied `experiment_plan.json`,
`experiment_result.json`, `claim_verdict.json`, `code_evidence_map.json`,
runtime evidence, executor stdout/stderr, allowlist evidence, metadata, and
source markdown.
"""
    write_text("validation_code_bundle/README.md", readme)


def render_markdown(data: dict[str, Any]) -> None:
    status = data["status"]
    item_rows = [["Item", "Doc", "Selected idea", "Verdict", "Outcome", "Final ready"]]
    for item in data["items"]:
        item_rows.append([
            item["item_id"],
            item["doc_slug"],
            item.get("selected_idea_id") or "",
            item.get("verdict") or "",
            item.get("experiment_outcome") or "",
            str(item.get("final_verdict_ready")),
        ])

    selected_idea_rows = [[
        "Item", "Selected idea", "Display title", "Potential", "Basis", "Verdict", "Outcome", "Recommendation"
    ]]
    for idea in [i for i in data["ideas"] if i.get("selected_for_experiment")]:
        selected_idea_rows.append([
            idea["item_id"],
            idea["idea_id"],
            clip(idea.get("display_title"), 120),
            f"{idea.get('potential_score')} ({idea.get('potential_label')})",
            ", ".join(idea.get("potential_basis") or []),
            str(idea.get("verdict") or ""),
            str(idea.get("experiment_outcome") or ""),
            str(idea.get("recommendation") or ""),
        ])

    all_idea_rows = [[
        "Item", "Idea", "Display title", "Path", "Potential", "Selected", "Novelty", "Feasibility", "Recommendation", "Raw title"
    ]]
    for idea in sorted(
        data["ideas"],
        key=lambda i: (item_sort_key(str(i["item_id"])), -as_float(i.get("potential_score")), str(i["idea_id"])),
    ):
        all_idea_rows.append([
            idea["item_id"],
            idea["idea_id"],
            clip(idea.get("display_title"), 120),
            str(idea.get("generation_path") or ""),
            f"{idea.get('potential_score')} ({idea.get('potential_label')})",
            str(idea.get("selected_for_experiment")),
            str(idea.get("novelty")),
            str(idea.get("feasibility")),
            str(idea.get("recommendation") or ""),
            clip(idea.get("title"), 90),
        ])

    validation_rows = [["Item", "Idea", "Experiment", "Outcome", "Exit", "Runner", "Command"]]
    for validation in data["validations"]:
        validation_rows.append([
            validation["item_id"],
            str(validation.get("idea_id") or ""),
            str(validation.get("experiment_id") or ""),
            str(validation.get("outcome") or ""),
            str(validation.get("exit_code")),
            str((validation.get("artifact_paths") or {}).get("runner_script") or ""),
            clip(validation.get("command_run"), 220),
        ])

    report = f"""# AutoSci Native E2E Literature Validation Report

Generated: {status['generated_at']}

## Scope

This report covers all 39 literature/source records extracted from the two supplied HTML files. The executed chain was:

`$ingest -> $research -> $review -> $ideate -> $exp-design -> $exp-run -> $exp-eval -> $exp-status -> $visualize`

All AutoSci actions were routed through `harness/solar-harness.sh autosci ...`. The final run used `--gate-mode autosci_native` for the wrapper chain and local Ollama `gemma3:4b` for model brainstorm/review evidence.

## Summary

- Items processed: {status['item_count']}
- Extracted claims: {status['claim_count']}
- Generated ideas: {status['idea_count']}
- Selected ideas validated through exp-* chain: {status['selected_idea_count']}
- Code/experiment validation records: {status['validation_count']}
- Ideate final-promotion-ready items: {status['ideate_final_promotion_ready_count']}
- Final-verdict-ready items: {status['final_verdict_ready_count']}
- OmegaWiki graph nodes: {status['graph_node_count']}
- OmegaWiki graph edges: {status['graph_edge_count']}
- Verdict counts: `{json.dumps(status['verdict_counts'], sort_keys=True)}`
- Experiment outcome counts: `{json.dumps(status['experiment_outcome_counts'], sort_keys=True)}`

The 8 non-final-ready verdicts are the items whose experiment outcome was `inconclusive`; the workflow still produced exp-design/run/eval/status artifacts for them.

## Boundary Notes

- This rerun used `--gate-mode autosci_native`, as approved, so side effects were auto-approved by the native gate policy.
- `$exp-run` executed the concrete local validator command recorded in runtime evidence; it was not a smoke-only pass.
- `$exp-design` records an execution-readiness limitation because design-specific Review LLM validation was not supplied. The later `$exp-run`/`$exp-eval` artifacts still include runtime evidence, code evidence, Review LLM evidence for verdicting, and wiki writeback evidence.
- The validator intentionally used local attached-document evidence only. Runtime logs preserve `network_fetch=not_requested`.

## Item Verdicts

{table(item_rows)}

## Selected Idea Potential

`potential_score` is not a calibrated probability. It is an explainable score derived from AutoSci evidence: final acceptance readiness, novelty, feasibility, review score, whether the idea entered exp-*, and the exp-eval outcome. It is included to show the relative possibility/usefulness of the generated ideas without overstating statistical certainty.

{table(selected_idea_rows)}

## All Generated Idea Potential

{table(all_idea_rows)}

## Validation Code And Exp Commands

{table(validation_rows)}

## Deliverables

- Extracted elements JSON: `extracted_elements.json`
- Extracted elements Markdown: `extracted_elements.md`
- Ideas JSON: `ideas.json`
- Ideas Markdown: `ideas.md`
- Idea display catalog: `idea_display_catalog.md`
- Validation code and exp-* index JSON: `validation_code_index.json`
- Validation code and exp-* index Markdown: `validation_code_index.md`
- Validation code bundle: `validation_code_bundle/`
- Omegawiki graph data: `omegawiki_ui/graph-data.json`
- Omegawiki web UI: `omegawiki_ui/index.html`
- Solar `$visualize` evidence: `{FINAL_REL}/visualize/autosci_skill_run.json`

## Source Batch Composition

- Main batch: `{MAIN_BATCH_REL}`
- Patch batch for corrected model-output normalization: `{PATCH_BATCH_REL}`
- Patch item ids: `{', '.join(sorted(PATCH_IDS))}`
"""
    write_text("final_report.md", report)

    extracted_rows = [["Item", "Title", "Claims", "Methods", "Doc"]]
    claims_by_item = Counter(claim["item_id"] for claim in data["claims"])
    methods_by_item = Counter(method["item_id"] for method in data["methods"])
    for item in data["items"]:
        extracted_rows.append([
            item["item_id"],
            str(item.get("title") or ""),
            str(claims_by_item[item["item_id"]]),
            str(methods_by_item[item["item_id"]]),
            item["doc_slug"],
        ])
    claim_rows = [["Item", "Claim", "Type", "Testability", "Status", "Text"]]
    for claim in data["claims"]:
        claim_rows.append([
            str(claim.get("item_id") or ""),
            str(claim.get("claim_id") or ""),
            str(claim.get("claim_type") or ""),
            str(claim.get("testability") or ""),
            str(claim.get("verification_status") or ""),
            clip(claim.get("text"), 260),
        ])
    method_rows = [["Item", "Method", "Name", "Summary", "Procedure"]]
    for method in data["methods"]:
        method_rows.append([
            str(method.get("item_id") or ""),
            str(method.get("method_id") or ""),
            str(method.get("name") or ""),
            clip(method.get("summary"), 220),
            clip("; ".join(method.get("procedure") or []), 260),
        ])
    extracted_md = (
        "# Extracted Elements\n\n"
        "## Item Counts\n\n"
        + table(extracted_rows)
        + "\n\n## Claims\n\n"
        + table(claim_rows)
        + "\n\n## Methods\n\n"
        + table(method_rows)
        + "\n"
    )
    write_text("extracted_elements.md", extracted_md)

    idea_rows = [[
        "Item", "Idea", "Display title", "Raw title", "Path", "Selected", "Potential", "Novelty", "Feasibility",
        "Review", "Recommendation", "Outcome", "Basis", "Hypothesis", "Approach"
    ]]
    for idea in data["ideas"]:
        idea_rows.append([
            idea["item_id"],
            idea["idea_id"],
            clip(idea.get("display_title"), 120),
            clip(idea.get("title"), 120),
            str(idea.get("generation_path") or ""),
            str(idea.get("selected_for_experiment")),
            f"{idea.get('potential_score')} ({idea.get('potential_label')})",
            str(idea.get("novelty")),
            str(idea.get("feasibility")),
            str(idea.get("review_score")),
            str(idea.get("recommendation") or ""),
            str(idea.get("experiment_outcome") or ""),
            clip(", ".join(idea.get("potential_basis") or []), 180),
            clip(idea.get("hypothesis"), 220),
            clip(idea.get("approach"), 220),
        ])
    write_text("ideas.md", "# Generated Ideas\n\n" + table(idea_rows) + "\n")

    catalog_rows = [["Item", "Raw idea id", "Display title", "Raw AutoSci title", "Path", "Selected"]]
    for idea in sorted(data["ideas"], key=lambda i: (item_sort_key(str(i["item_id"])), str(i["idea_id"]))):
        catalog_rows.append([
            idea["item_id"],
            idea["idea_id"],
            clip(idea.get("display_title"), 140),
            clip(idea.get("title"), 110),
            str(idea.get("generation_path") or ""),
            str(idea.get("selected_for_experiment")),
        ])
    write_text(
        "idea_display_catalog.md",
        "# Idea Display Catalog\n\n"
        "Raw `idea_id` values are preserved for provenance. `display_title` is the reader-facing title used in the OmegaWiki UI and report.\n\n"
        + table(catalog_rows)
        + "\n",
    )

    validation_rows = [["Item", "Idea", "Experiment", "Outcome", "Exit", "Final ready", "Runner", "Command"]]
    for validation in data["validations"]:
        validation_rows.append([
            validation["item_id"],
            str(validation.get("idea_id") or ""),
            str(validation.get("experiment_id") or ""),
            str(validation.get("outcome") or ""),
            str(validation.get("exit_code")),
            str(validation.get("final_verdict_ready")),
            str((validation.get("artifact_paths") or {}).get("runner_script") or ""),
            str(validation.get("command_run") or ""),
        ])
    validation_md = (
        "# Validation Code And Exp Artifacts\n\n"
        "The concrete validator source is copied into `validation_code_bundle/validator/validate_literature_item.py`; "
        "each item folder contains `run_validation.sh` plus the exp-design/run/eval/status byproducts used for the verdict.\n\n"
        + table(validation_rows)
        + "\n"
    )
    write_text("validation_code_index.md", validation_md)


def render_ui(graph: dict[str, Any], status: dict[str, Any]) -> None:
    write_json("omegawiki_ui/graph-data.json", graph)
    write_json("omegawiki_ui/run-status.json", status)
    template_path = Path(__file__).with_name("omegawiki_spa_template.html")
    if template_path.exists():
        write_text("omegawiki_ui/index.html", template_path.read_text(encoding="utf-8"))
        return
    data_json = json.dumps(graph, ensure_ascii=False)
    status_json = json.dumps(status, ensure_ascii=False)
    html_body = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OmegaWiki</title>
<style>
:root {
  color-scheme: light;
  --ink: #202124;
  --muted: #666b73;
  --line: #e5e7eb;
  --panel: #f5f5f6;
  --canvas: #f3f3f4;
  --accent: #4a90d9;
  --paper: #4a90d9;
  --claim: #ec4899;
  --idea: #f39c12;
  --experiment: #e74c3c;
  --method: #84cc16;
  --code: #95a5a6;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--ink);
  background: #fff;
}
.topnav {
  height: 56px;
  display: grid;
  grid-template-columns: auto auto 1fr auto auto;
  align-items: center;
  gap: 22px;
  padding: 0 24px;
  border-bottom: 1px solid var(--line);
  background: #fff;
}
.brand {
  font-size: 18px;
  font-weight: 700;
  text-decoration: none;
  color: #111;
  white-space: nowrap;
}
.badge {
  display: inline-flex;
  margin-left: 8px;
  padding: 2px 9px;
  border-radius: 4px;
  background: #4a90d9;
  color: #fff;
  font-size: 12px;
  vertical-align: middle;
}
nav { display: flex; gap: 26px; }
nav a {
  color: #333;
  text-decoration: none;
  font-size: 16px;
}
.jump {
  width: 235px;
  height: 30px;
  border: 1px solid #ddd;
  border-radius: 5px;
  padding: 0 10px;
  font-size: 14px;
  color: #555;
  background: #f8f8f8;
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #dce5ef;
}
.stats-line {
  color: #6b6f76;
  font-size: 13px;
  white-space: nowrap;
}
.graph-shell {
  width: min(1420px, calc(100vw - 48px));
  height: calc(100vh - 108px);
  margin: 24px auto 28px;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
}
.graph-sidebar {
  background: var(--panel);
  border-radius: 8px;
  padding: 18px;
  overflow-y: auto;
}
.graph-sidebar h3 {
  margin: 0 0 12px;
  font-size: 18px;
}
.graph-sidebar h4 {
  margin: 22px 0 8px;
  color: #666a72;
  font-size: 13px;
  letter-spacing: .04em;
  text-transform: uppercase;
}
#graph-search {
  width: 100%;
  height: 32px;
  border: 1px solid #ddd;
  border-radius: 5px;
  padding: 0 10px;
  font-size: 14px;
  background: #fff;
}
.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
button {
  border: 1px solid #d9dce1;
  border-radius: 4px;
  background: #fff;
  color: #202124;
  cursor: pointer;
  font: inherit;
}
.preset-btn {
  padding: 5px 8px;
  font-size: 12px;
}
.preset-btn.active {
  border-color: #4a90d9;
  background: #e9f2fd;
}
.filter-row {
  display: grid;
  grid-template-columns: 18px 12px 1fr auto;
  align-items: center;
  gap: 6px;
  padding: 5px 2px;
  font-size: 14px;
}
.filter-row input { accent-color: #4a90d9; }
.swatch {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.count {
  color: #777;
  font-size: 12px;
}
.edge-group summary {
  cursor: pointer;
  padding: 7px 0;
  font-weight: 650;
  font-size: 14px;
}
.edge-child {
  margin-left: 8px;
  color: #666;
}
.canvas-wrap {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border-radius: 8px;
  background: var(--canvas);
}
#graph {
  width: 100%;
  height: 100%;
  display: block;
}
.graph-info {
  position: absolute;
  right: 18px;
  bottom: 18px;
  width: min(360px, calc(100% - 36px));
  max-height: 46%;
  overflow: auto;
  padding: 14px 16px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: rgba(255,255,255,.95);
  box-shadow: 0 8px 28px rgba(0,0,0,.12);
  font-size: 13px;
}
.graph-info h4 {
  margin: 0 0 6px;
  font-size: 15px;
}
.muted { color: var(--muted); }
.mini-table {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 10px;
  margin-top: 10px;
  font-size: 12px;
}
.kbd {
  padding: 1px 5px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fff;
  color: #555;
}
@media (max-width: 900px) {
  .topnav { grid-template-columns: 1fr auto; height: auto; padding: 12px 16px; }
  nav, .jump, .live-dot { display: none; }
  .graph-shell { width: calc(100vw - 24px); grid-template-columns: 1fr; height: auto; }
  .graph-sidebar { max-height: 360px; }
  .canvas-wrap { height: 70vh; min-height: 520px; }
}
</style>
</head>
<body>
<header class="topnav">
  <a class="brand" href="#/">
    OmegaWiki <span class="badge">Phase 1</span>
  </a>
  <nav>
    <a href="#/">Reader</a>
    <a href="#/graph">Graph</a>
    <a href="#/idea-graph">Idea Graph</a>
    <a href="#/dashboard">Dashboard</a>
  </nav>
  <input id="jump-input" class="jump" type="search" placeholder="jump to slug... (Enter)">
  <span class="live-dot" title="static artifact"></span>
  <div class="stats-line" id="top-stats">loading graph...</div>
</header>
<main class="graph-shell">
  <aside class="graph-sidebar">
    <h3>Graph</h3>
    <input id="graph-search" type="search" placeholder="Search nodes..." autocomplete="off">

    <h4>Preset Views</h4>
    <div id="preset-row" class="preset-row"></div>

    <h4>Entity Types</h4>
    <div id="entity-filters"></div>

    <h4>Edge Types</h4>
    <div id="edge-filters"></div>

    <h4>Status</h4>
    <div id="status-table" class="mini-table"></div>
    <p class="muted">Click a node for evidence. Use <span class="kbd">Search</span> or presets to focus the graph.</p>
  </aside>
  <section class="canvas-wrap">
    <canvas id="graph"></canvas>
    <aside id="graph-info" class="graph-info" hidden></aside>
  </section>
</main>
<script>
const GRAPH = __GRAPH_JSON__;
const STATUS = __STATUS_JSON__;
const canvas = document.getElementById('graph');
const ctx = canvas.getContext('2d');
const search = document.getElementById('graph-search');
const jump = document.getElementById('jump-input');
const info = document.getElementById('graph-info');
const topStats = document.getElementById('top-stats');
const entityFilters = document.getElementById('entity-filters');
const edgeFilters = document.getElementById('edge-filters');
const presetRow = document.getElementById('preset-row');
const statusTable = document.getElementById('status-table');

const COLORS = {
  document: '#95a5a6',
  paper: '#4a90d9',
  claim: '#ec4899',
  idea: '#f39c12',
  experiment: '#e74c3c',
  method: '#84cc16',
  code: '#95a5a6',
  verdict: '#7b8ab8',
  generation_path: '#f39c12'
};
const KIND_LABELS = {
  document: 'Documents',
  paper: 'Papers',
  claim: 'Concepts / claims',
  idea: 'Ideas',
  experiment: 'Experiments',
  method: 'Methods',
  code: 'Code',
  verdict: 'Verdicts',
  generation_path: 'Idea paths'
};
const EDGE_GROUPS = {
  'Document sources': ['contains_source'],
  'Paper to concept': ['extracts_claim'],
  'Method genealogy': ['extracts_method'],
  'Workflow (ideas / experiments)': ['grounds_idea', 'validated_by', 'runs_code', 'evaluates_to', 'path_member']
};
const PRESETS = {
  'Selected Workflow': {
    kinds: ['paper', 'idea', 'experiment'],
    edges: ['grounds_idea', 'validated_by'],
    selectedOnly: true
  },
  'Ideas': {
    kinds: ['paper', 'idea'],
    edges: ['grounds_idea'],
    selectedOnly: false
  },
  'Experiments': {
    kinds: ['paper', 'idea', 'experiment', 'code', 'verdict'],
    edges: ['grounds_idea', 'validated_by', 'runs_code', 'evaluates_to'],
    selectedOnly: true
  },
  'Claims': {
    kinds: ['paper', 'claim'],
    edges: ['extracts_claim'],
    selectedOnly: false
  },
  'Methods': {
    kinds: ['paper', 'method'],
    edges: ['extracts_method'],
    selectedOnly: false
  },
  'All': {
    kinds: Object.keys(KIND_LABELS),
    edges: Object.values(EDGE_GROUPS).flat(),
    selectedOnly: false
  }
};
let activePreset = 'Selected Workflow';
let activeKinds = new Set(PRESETS[activePreset].kinds);
let activeEdges = new Set(PRESETS[activePreset].edges);
let selectedIdeasOnly = PRESETS[activePreset].selectedOnly;
let nodes = GRAPH.nodes.map((n, i) => ({...n, degree: 0, x: 0, y: 0, vx: 0, vy: 0, index: i}));
let nodeById = new Map(nodes.map(n => [n.id, n]));
let edges = GRAPH.edges
  .map((e, i) => ({...e, type: e.type || e.label || 'edge', index: i}))
  .filter(e => nodeById.has(e.source) && nodeById.has(e.target));
for (const e of edges) {
  nodeById.get(e.source).degree++;
  nodeById.get(e.target).degree++;
}
let selected = null;
let hover = null;
let settled = 0;
let currentVisibleCount = nodes.length;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function labelForKind(kind) { return KIND_LABELS[kind] || kind; }
function countBy(items, keyFn) {
  const out = new Map();
  for (const item of items) {
    const key = keyFn(item);
    out.set(key, (out.get(key) || 0) + 1);
  }
  return out;
}
function resize() {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, canvas.clientWidth * ratio);
  canvas.height = Math.max(1, canvas.clientHeight * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  initializePositions();
}
function itemRank(itemId) {
  const value = String(itemId || '');
  const match = value.match(/^(cc|cu|ghc)-?(\\d+)|^(r)(\\d+)$/);
  if (!match) return 9999;
  const prefix = match[1] || match[3];
  const number = Number(match[2] || match[4] || 0);
  const order = {cc: 0, cu: 1, ghc: 2, r: 3}[prefix] ?? 9;
  return order * 1000 + number;
}
function initializePositions() {
  const w = canvas.clientWidth || 1000;
  const h = canvas.clientHeight || 680;
  const visible = nodes.filter(visibleNode);
  if (activePreset !== 'All' && visible.length <= 190) {
    const itemIds = Array.from(new Set(visible.map(n => n.item_id).filter(Boolean))).sort((a, b) => itemRank(a) - itemRank(b));
    const rowByItem = new Map(itemIds.map((id, idx) => [id, idx]));
    const top = 36;
    const splitSelectedWorkflow = activePreset === 'Selected Workflow' || activePreset === 'Experiments';
    const rowsPerLane = splitSelectedWorkflow ? Math.ceil(itemIds.length / 2) : itemIds.length;
    const rowH = Math.max(16, Math.min(28, (h - top * 2) / Math.max(1, rowsPerLane)));
    for (const n of visible) {
      const fullRow = rowByItem.get(n.item_id) ?? (n.index % Math.max(1, itemIds.length));
      const lane = splitSelectedWorkflow && fullRow >= rowsPerLane ? 1 : 0;
      const row = splitSelectedWorkflow ? fullRow % rowsPerLane : fullRow;
      const laneX = splitSelectedWorkflow ? lane * (w * 0.50) : 0;
      const laneW = splitSelectedWorkflow ? w * 0.50 : w;
      const xByKind = {
        document: laneX + laneW * 0.07,
        paper: laneX + laneW * 0.10,
        claim: laneX + laneW * 0.42,
        method: laneX + laneW * 0.42,
        idea: laneX + laneW * 0.44,
        experiment: laneX + laneW * 0.91,
        code: laneX + laneW * 0.96,
        verdict: laneX + laneW * 0.99,
        generation_path: laneX + laneW * 0.08
      };
      n.x = xByKind[n.kind] || laneX + laneW * 0.50;
      n.y = top + row * rowH + rowH / 2;
      if (n.kind === 'idea' && !n.selected) n.x += 90;
      if (n.kind === 'claim') n.y += (n.index % 3 - 1) * 5;
      n.vx = 0;
      n.vy = 0;
    }
    for (const n of nodes.filter(n => !visibleNode(n))) {
      n.x = w / 2;
      n.y = h / 2;
      n.vx = 0;
      n.vy = 0;
    }
    settled = 999;
    return;
  }
  const centerX = w / 2;
  const centerY = h / 2;
  const radii = {document: 70, paper: 190, method: 280, claim: 360, idea: 470, experiment: 560, code: 635, verdict: 680, generation_path: 120};
  const groups = new Map();
  for (const n of nodes) {
    if (!groups.has(n.kind)) groups.set(n.kind, []);
    groups.get(n.kind).push(n);
  }
  for (const [kind, group] of groups) {
    const radius = Math.min(radii[kind] || 420, Math.min(w, h) * .46);
    group.forEach((n, i) => {
      const angle = (i / Math.max(1, group.length)) * Math.PI * 2 + (n.index % 17) * .011;
      n.x = centerX + Math.cos(angle) * radius + Math.sin(n.index * 13.37) * 22;
      n.y = centerY + Math.sin(angle) * radius * .72 + Math.cos(n.index * 7.91) * 22;
      n.vx = 0;
      n.vy = 0;
    });
  }
  settled = 0;
}
window.addEventListener('resize', resize);

function buildSidebar() {
  topStats.textContent = `${STATUS.item_count} pages · ${STATUS.graph_edge_count || edges.length} edges`;
  statusTable.innerHTML = [
    ['Claims', STATUS.claim_count],
    ['Ideas', STATUS.idea_count],
    ['Selected ideas', STATUS.selected_idea_count],
    ['Validations', STATUS.validation_count],
    ['Final-ready verdicts', STATUS.final_verdict_ready_count]
  ].map(([k, v]) => `<span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong>`).join('');

  for (const [name, config] of Object.entries(PRESETS)) {
    const btn = document.createElement('button');
    btn.className = `preset-btn ${name === activePreset ? 'active' : ''}`;
    btn.textContent = name;
    btn.onclick = () => {
      activePreset = name;
      activeKinds = new Set(config.kinds);
      activeEdges = new Set(config.edges);
      selectedIdeasOnly = !!config.selectedOnly;
      syncChecks();
      initializePositions();
    };
    presetRow.appendChild(btn);
  }

  const kindCounts = countBy(nodes, n => n.kind);
  for (const kind of Array.from(kindCounts.keys()).sort()) {
    const row = document.createElement('label');
    row.className = 'filter-row';
    row.innerHTML = `<input type="checkbox" ${activeKinds.has(kind) ? 'checked' : ''} data-kind="${escapeHtml(kind)}"><span class="swatch" style="background:${COLORS[kind] || '#999'}"></span><span>${escapeHtml(labelForKind(kind))}</span><span class="count">(${kindCounts.get(kind)})</span>`;
    row.querySelector('input').onchange = (ev) => {
      ev.target.checked ? activeKinds.add(kind) : activeKinds.delete(kind);
      activePreset = 'Custom';
      syncPresetButtons();
      initializePositions();
    };
    entityFilters.appendChild(row);
  }

  const edgeCounts = countBy(edges, e => e.type);
  for (const [group, types] of Object.entries(EDGE_GROUPS)) {
    const detail = document.createElement('details');
    detail.className = 'edge-group';
    detail.open = true;
    const total = types.reduce((sum, t) => sum + (edgeCounts.get(t) || 0), 0);
    detail.innerHTML = `<summary>${escapeHtml(group)} <span class="count">(${total})</span></summary>`;
    for (const type of types) {
      const row = document.createElement('label');
      row.className = 'filter-row edge-child';
      row.innerHTML = `<input type="checkbox" ${activeEdges.has(type) ? 'checked' : ''} data-edge="${escapeHtml(type)}"><span class="swatch" style="background:#7b8ab8"></span><span>${escapeHtml(type)}</span><span class="count">${edgeCounts.get(type) || 0}</span>`;
      row.querySelector('input').onchange = (ev) => {
        ev.target.checked ? activeEdges.add(type) : activeEdges.delete(type);
        activePreset = 'Custom';
        syncPresetButtons();
        initializePositions();
      };
      detail.appendChild(row);
    }
    edgeFilters.appendChild(detail);
  }
}
function syncPresetButtons() {
  document.querySelectorAll('#preset-row button').forEach(button => {
    button.classList.toggle('active', button.textContent === activePreset);
  });
}
function syncChecks() {
  syncPresetButtons();
  document.querySelectorAll('[data-kind]').forEach(input => {
    input.checked = activeKinds.has(input.dataset.kind);
  });
  document.querySelectorAll('[data-edge]').forEach(input => {
    input.checked = activeEdges.has(input.dataset.edge);
  });
}
function nodeMatchesSearch(n) {
  const q = search.value.trim().toLowerCase();
  if (!q) return true;
  return [n.id, n.label, n.kind, n.title, n.hypothesis, n.recommendation].some(v => String(v || '').toLowerCase().includes(q));
}
function visibleNode(n) {
  if (!activeKinds.has(n.kind)) return false;
  if (selectedIdeasOnly && n.kind === 'idea' && !n.selected) return false;
  return nodeMatchesSearch(n);
}
function visibleEdge(e) {
  const a = nodeById.get(e.source);
  const b = nodeById.get(e.target);
  return activeEdges.has(e.type) && a && b && visibleNode(a) && visibleNode(b);
}
function nodeRadius(n) {
  const base = n.kind === 'paper' ? 7 : n.kind === 'idea' ? 6 : n.kind === 'experiment' ? 5.5 : 4.5;
  return Math.min(22, base + Math.sqrt(n.degree || 0) * 1.2);
}
function tick() {
  if (settled > 240) return;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  const cx = w / 2;
  const cy = h / 2;
  const visible = nodes.filter(visibleNode);
  const sampleLimit = visible.length > 260 ? 260 : visible.length;
  for (const e of edges) {
    if (!visibleEdge(e)) continue;
    const a = nodeById.get(e.source);
    const b = nodeById.get(e.target);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.max(20, Math.hypot(dx, dy));
    const desired = e.type === 'path_member' ? 130 : 180;
    const force = (d - desired) * 0.0009;
    a.vx += dx * force;
    a.vy += dy * force;
    b.vx -= dx * force;
    b.vy -= dy * force;
  }
  for (let i = 0; i < sampleLimit; i++) {
    const a = visible[i];
    for (let j = i + 1; j < sampleLimit; j++) {
      const b = visible[j];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d2 = Math.max(100, dx * dx + dy * dy);
      const force = 85 / d2;
      a.vx -= dx * force;
      a.vy -= dy * force;
      b.vx += dx * force;
      b.vy += dy * force;
    }
  }
  for (const n of visible) {
    n.vx += (cx - n.x) * 0.0009;
    n.vy += (cy - n.y) * 0.0009;
    n.x += Math.max(-7, Math.min(7, n.vx));
    n.y += Math.max(-7, Math.min(7, n.vy));
    n.vx *= .86;
    n.vy *= .86;
    n.x = Math.max(18, Math.min(w - 18, n.x));
    n.y = Math.max(18, Math.min(h - 18, n.y));
  }
  settled++;
}
function drawEdge(e) {
  const a = nodeById.get(e.source);
  const b = nodeById.get(e.target);
  const color = e.type === 'validated_by' || e.type === 'evaluates_to' ? '#4a90d9' : e.type === 'path_member' ? '#f6c267' : '#c9cdd4';
  ctx.save();
  ctx.strokeStyle = color;
  ctx.globalAlpha = e.type === 'path_member' ? .35 : .62;
  ctx.lineWidth = e.type === 'validated_by' ? 1.8 : 1;
  if (e.type === 'path_member') ctx.setLineDash([5, 5]);
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
  ctx.restore();
}
function drawNode(n) {
  const r = nodeRadius(n);
  ctx.beginPath();
  ctx.fillStyle = COLORS[n.kind] || '#999';
  ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.lineWidth = selected && selected.id === n.id ? 3 : 1;
  ctx.strokeStyle = selected && selected.id === n.id ? '#2f6fd6' : 'rgba(255,255,255,.85)';
  ctx.stroke();
  const showLabel =
    (hover && hover.id === n.id) ||
    (selected && selected.id === n.id) ||
    (n.kind === 'idea' && (n.selected || currentVisibleCount < 120)) ||
    (n.kind === 'paper' && currentVisibleCount < 90) ||
    (n.kind === 'experiment' && currentVisibleCount < 70);
  if (showLabel) {
    const label = String(n.label || n.id).replace(/^[^:]+:/, '').trim().slice(0, 34);
    ctx.font = '10px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif';
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(243,243,244,.88)';
    ctx.fillStyle = '#29303a';
    ctx.strokeText(label, n.x + r + 5, n.y + 3);
    ctx.fillText(label, n.x + r + 5, n.y + 3);
  }
}
function draw() {
  tick();
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
  currentVisibleCount = nodes.filter(visibleNode).length;
  for (const e of edges) if (visibleEdge(e)) drawEdge(e);
  for (const n of nodes) if (visibleNode(n)) drawNode(n);
  requestAnimationFrame(draw);
}
function findHit(x, y) {
  let hit = null;
  let best = 999;
  for (const n of nodes) {
    if (!visibleNode(n)) continue;
    const d = Math.hypot(n.x - x, n.y - y);
    if (d < best && d < nodeRadius(n) + 7) {
      best = d;
      hit = n;
    }
  }
  return hit;
}
function showInfo(hit) {
  if (!hit) return;
    selected=hit;
  const linked = edges.filter(e => e.source === hit.id || e.target === hit.id).slice(0, 34);
  const fields = Object.entries(hit)
    .filter(([k]) => !['x','y','vx','vy','index','degree'].includes(k))
    .map(([k,v]) => `<div><strong>${escapeHtml(k)}</strong>: ${escapeHtml(typeof v === 'object' ? JSON.stringify(v) : v)}</div>`)
    .join('');
  info.hidden = false;
  info.innerHTML = `<h4>${escapeHtml(hit.label || hit.id)}</h4><div class="muted">${fields}</div><h4>Connections</h4><div class="muted">${linked.map(e => `${escapeHtml(e.type)}: ${escapeHtml(e.source)} -> ${escapeHtml(e.target)}`).join('<br>')}</div>`;
}
canvas.addEventListener('click', ev => {
  const rect = canvas.getBoundingClientRect();
  showInfo(findHit(ev.clientX - rect.left, ev.clientY - rect.top));
});
canvas.addEventListener('mousemove', ev => {
  const rect = canvas.getBoundingClientRect();
  hover = findHit(ev.clientX - rect.left, ev.clientY - rect.top);
  canvas.style.cursor = hover ? 'pointer' : 'default';
});
search.addEventListener('input', () => { settled = 0; });
jump.addEventListener('keydown', ev => {
  if (ev.key === 'Enter') {
    search.value = jump.value;
    settled = 0;
  }
});
resize();
buildSidebar();
draw();
</script>
</body>
</html>
"""
    html_body = html_body.replace("__GRAPH_JSON__", data_json).replace("__STATUS_JSON__", status_json)
    write_text("omegawiki_ui/index.html", html_body)


def main() -> int:
    data = build()
    FINAL_ROOT.mkdir(parents=True, exist_ok=True)
    write_json("run_status.json", data["status"])
    write_json("extracted_elements.json", {"items": data["items"], "claims": data["claims"], "methods": data["methods"]})
    write_json("ideas.json", {"ideas": data["ideas"]})
    write_json(
        "idea_display_catalog.json",
        {
            "schema": "autosci_idea_display_catalog.v1",
            "notes": [
                "Raw AutoSci idea_id values are preserved for provenance.",
                "display_title is the reader-facing title used in report and OmegaWiki UI.",
            ],
            "ideas": [
                {
                    "item_id": idea.get("item_id"),
                    "idea_id": idea.get("idea_id"),
                    "display_title": idea.get("display_title"),
                    "raw_title": idea.get("title"),
                    "generation_path": idea.get("generation_path"),
                    "selected_for_experiment": idea.get("selected_for_experiment"),
                }
                for idea in data["ideas"]
            ],
        },
    )
    write_json("validation_code_index.json", {"validations": data["validations"]})
    render_markdown(data)
    render_validation_code_bundle(data)
    render_ui(data["graph"], data["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
