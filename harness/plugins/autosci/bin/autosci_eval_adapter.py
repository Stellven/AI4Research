#!/usr/bin/env python3
"""AutoSci evaluator adapter for Solar DAG nodes.

The AutoSci bridge emits typed scientific evidence. The graph runtime gates
nodes through ``solar.eval.v1`` sidecars. This adapter is the deterministic
translator between those two contracts: find the node evidence, run the
matching scientific gate, write eval.md/eval.json, and return the verdict in
the shape consumed by ``graph_node_dispatcher.node_verdict``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def _default_harness_dir() -> Path:
    raw = os.environ.get("HARNESS_DIR") or os.environ.get("SOLAR_HARNESS_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


HARNESS_DIR = _default_harness_dir()
REPO_HARNESS_DIR = Path(__file__).resolve().parents[3]
OPERATOR_ID = "autosci-evaluator-worker"
WORKFLOW_CONTRACT_ID = "research.autosci.v1"

GATE_FILE_BY_SCHEMA: dict[str, str] = {
    "literature_discovery.v1": "literature_discovery_gate.py",
    "research_paper.v1": "paper_gate.py",
    "research_memory_update.v1": "memory_update_gate.py",
    "research_graph_update.v1": "graph_update_gate.py",
    "research_claims.v1": "claims_gate.py",
    "research_method.v1": "method_gate.py",
    "code_evidence_map.v1": "code_evidence_gate.py",
    "idea_candidate.v1": "idea_gate.py",
    "idea_evaluation.v1": "idea_gate.py",
    "experiment_plan.v1": "experiment_plan_gate.py",
    "experiment_result.v1": "experiment_result_gate.py",
    "experiment_status.v1": "experiment_status_gate.py",
    "claim_verdict.v1": "claim_verdict_gate.py",
    "artifact_review.v1": "artifact_review_gate.py",
    "scientific_report.v1": "report_gate.py",
    "publication_bundle.v1": "publication_gate.py",
    "workflow_evolution.v1": "workflow_evolution_gate.py",
}

DIRECT_PATH_KEYS = {
    "artifact",
    "artifact_path",
    "bridge_result_path",
    "evidence",
    "evidence_json",
    "evidence_path",
    "evidence_payload_path",
    "output_path",
    "path",
    "result_path",
}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object expected at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(HARNESS_DIR.resolve()))
    except Exception:
        return str(path)


def _resolve_path(raw: str | Path, *, graph_path: Path | None = None) -> Path:
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    candidates = [
        HARNESS_DIR / path,
        Path.cwd() / path,
        HARNESS_DIR.parent / path,
    ]
    if graph_path is not None:
        candidates.insert(1, graph_path.parent / path)
    parts = path.parts
    if parts and parts[0] == "harness":
        candidates.insert(0, HARNESS_DIR / Path(*parts[1:]))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _append_candidate(
    candidates: list[dict[str, str]],
    seen: set[str],
    raw: Any,
    source: str,
    *,
    graph_path: Path,
) -> None:
    if raw is None:
        return
    if isinstance(raw, Path):
        text = str(raw)
    elif isinstance(raw, str):
        text = raw.strip()
    else:
        return
    if not text or not text.endswith(".json"):
        return
    path = _resolve_path(text, graph_path=graph_path)
    key = str(path)
    if key in seen:
        return
    seen.add(key)
    candidates.append({"path": key, "source": source, "raw": text})


def _append_from_artifacts(
    candidates: list[dict[str, str]],
    seen: set[str],
    value: Any,
    source: str,
    *,
    graph_path: Path,
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key or "").lower()
            if key_text in DIRECT_PATH_KEYS or key_text.endswith("_path") or "evidence" in key_text:
                if isinstance(item, str):
                    _append_candidate(candidates, seen, item, f"{source}.{key}", graph_path=graph_path)
                elif isinstance(item, list):
                    _append_from_artifacts(candidates, seen, item, f"{source}.{key}", graph_path=graph_path)
                elif isinstance(item, dict):
                    _append_from_artifacts(candidates, seen, item, f"{source}.{key}", graph_path=graph_path)
            elif isinstance(item, (dict, list)):
                _append_from_artifacts(candidates, seen, item, f"{source}.{key}", graph_path=graph_path)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            if isinstance(item, str):
                _append_candidate(candidates, seen, item, f"{source}[{idx}]", graph_path=graph_path)
            elif isinstance(item, dict):
                for key in ("path", "evidence_path", "evidence_payload_path", "result_path"):
                    _append_candidate(candidates, seen, item.get(key), f"{source}[{idx}].{key}", graph_path=graph_path)
                _append_from_artifacts(candidates, seen, item.get("artifacts"), f"{source}[{idx}].artifacts", graph_path=graph_path)


def _bridge_result_evidence_refs(candidate: dict[str, str], *, graph_path: Path) -> list[dict[str, str]]:
    path = Path(candidate["path"])
    if not path.exists():
        return []
    try:
        payload = _load_json(path)
    except Exception:
        return []
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for key in ("evidence_path", "evidence_payload_path", "evidence_json", "result_path"):
        _append_candidate(refs, seen, payload.get(key), f"{candidate['source']}.{key}", graph_path=graph_path)
    outputs = payload.get("outputs")
    if isinstance(outputs, dict):
        _append_from_artifacts(refs, seen, outputs, f"{candidate['source']}.outputs", graph_path=graph_path)
    return refs


def _candidate_evidence_paths(graph: dict[str, Any], node: dict[str, Any], *, graph_path: Path) -> list[dict[str, str]]:
    node_id = str(node.get("id") or "")
    result = (graph.get("node_results") or {}).get(node_id)
    if not isinstance(result, dict):
        result = {}

    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for container_name, container in (("node", node), ("node_result", result)):
        for key in DIRECT_PATH_KEYS:
            _append_candidate(candidates, seen, container.get(key), f"{container_name}.{key}", graph_path=graph_path)
        _append_from_artifacts(candidates, seen, container.get("artifacts"), f"{container_name}.artifacts", graph_path=graph_path)
        _append_from_artifacts(candidates, seen, container.get("outputs"), f"{container_name}.outputs", graph_path=graph_path)

    for idx, item in enumerate(node.get("write_scope") or []):
        _append_candidate(candidates, seen, item, f"node.write_scope[{idx}]", graph_path=graph_path)

    resume_policy = node.get("resume_policy") if isinstance(node.get("resume_policy"), dict) else {}
    _append_candidate(candidates, seen, resume_policy.get("artifact"), "node.resume_policy.artifact", graph_path=graph_path)

    expanded = list(candidates)
    for candidate in candidates:
        for ref in _bridge_result_evidence_refs(candidate, graph_path=graph_path):
            if ref["path"] not in seen:
                seen.add(ref["path"])
                expanded.append(ref)
    return expanded


def _expected_schema(node: dict[str, Any]) -> str:
    evidence_policy = node.get("evidence_policy") if isinstance(node.get("evidence_policy"), dict) else {}
    resume_policy = node.get("resume_policy") if isinstance(node.get("resume_policy"), dict) else {}
    return str(evidence_policy.get("expected_schema") or resume_policy.get("expected_schema") or "").strip()


def _select_evidence(
    graph: dict[str, Any],
    node: dict[str, Any],
    *,
    graph_path: Path,
) -> tuple[Path | None, dict[str, Any], str, list[dict[str, str]], list[str]]:
    expected = _expected_schema(node)
    candidates = _candidate_evidence_paths(graph, node, graph_path=graph_path)
    load_errors: list[str] = []
    loaded: list[tuple[Path, dict[str, Any], dict[str, str]]] = []
    for candidate in candidates:
        path = Path(candidate["path"])
        if not path.exists():
            continue
        try:
            payload = _load_json(path)
        except Exception as exc:
            load_errors.append(f"{_rel(path)} unreadable: {type(exc).__name__}: {exc}")
            continue
        loaded.append((path, payload, candidate))
        schema = str(payload.get("schema") or "").strip()
        if expected and schema == expected:
            return path, payload, expected, candidates, load_errors
        if not expected and schema in GATE_FILE_BY_SCHEMA:
            return path, payload, schema, candidates, load_errors
    if loaded:
        path, payload, _candidate = loaded[0]
        return path, payload, expected or str(payload.get("schema") or ""), candidates, load_errors
    return None, {}, expected, candidates, load_errors


def _gate_evidence(evidence_path: Path, expected_schema: str) -> dict[str, Any]:
    gate_file = GATE_FILE_BY_SCHEMA.get(expected_schema)
    if not gate_file:
        return {
            "ok": False,
            "status": "failed",
            "schema": expected_schema,
            "path": _rel(evidence_path),
            "reasons": [f"no scientific evidence gate configured for schema {expected_schema or 'missing'}"],
            "warnings": [],
        }
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    proc = subprocess.run(
        [sys.executable, str(REPO_HARNESS_DIR / "evaluators" / "scientific" / gate_file), str(evidence_path)],
        cwd=str(HARNESS_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
        if not isinstance(payload, dict):
            raise ValueError("gate output was not an object")
    except Exception as exc:
        payload = {
            "ok": False,
            "status": "failed",
            "schema": expected_schema,
            "path": _rel(evidence_path),
            "reasons": [f"scientific gate emitted invalid JSON: {type(exc).__name__}: {exc}"],
            "warnings": [proc.stdout.strip()] if proc.stdout.strip() else [],
        }
    payload["exit_code"] = proc.returncode
    if proc.stderr.strip():
        payload.setdefault("warnings", []).append(proc.stderr.strip())
    if proc.returncode != 0 and payload.get("ok"):
        payload["ok"] = False
        payload["status"] = "failed"
        payload.setdefault("reasons", []).append(f"gate process exited {proc.returncode}")
    return payload


def _command_line() -> str:
    return " ".join(shlex.quote(part) for part in sys.argv)


def _workspace_root() -> str:
    return str(Path(os.environ.get("SOLAR_WORKSPACE_ROOT") or Path.cwd()).expanduser())


def _eval_payload(
    *,
    graph: dict[str, Any],
    node: dict[str, Any],
    graph_path: Path,
    evidence_path: Path | None,
    evidence_payload: dict[str, Any],
    expected_schema: str,
    gate_result: dict[str, Any],
    verdict: str,
    reason: str,
    candidates: list[dict[str, str]],
    load_errors: list[str],
) -> dict[str, Any]:
    sid = str(graph.get("sprint_id") or graph_path.stem.replace(".task_graph", ""))
    node_id = str(node.get("id") or "")
    ok = verdict.upper() == "PASS"
    gate_reasons = [str(item) for item in gate_result.get("reasons") or [] if str(item).strip()]
    failed_conditions: list[str] = []
    passed_conditions: list[str] = []
    if ok:
        passed_conditions.append(f"AutoSci evidence gate passed for {expected_schema or evidence_payload.get('schema') or 'unknown schema'}")
    else:
        failed_conditions.extend(gate_reasons or [reason or "AutoSci verification failed"])
        failed_conditions.extend(load_errors)
    evidence_refs = [_rel(evidence_path)] if evidence_path else []
    summary = reason.strip() if reason.strip() else (
        "AutoSci scientific evidence gate passed."
        if ok
        else "AutoSci scientific evidence gate failed."
    )
    return {
        "schema_version": "solar.eval.v1",
        "sprint_id": sid,
        "node_id": node_id,
        "verdict": verdict.upper(),
        "status": "passed" if ok else "failed",
        "summary": summary,
        "generated_by": OPERATOR_ID,
        "generation_mode": "autosci_eval_adapter",
        "proof_level": "independent_verification",
        "independent_author": OPERATOR_ID,
        "command_line": _command_line(),
        "workspace_root": _workspace_root(),
        "passed_conditions": passed_conditions,
        "failed_conditions": failed_conditions,
        "errors": [
            {
                "cond": "autosci_scientific_gate",
                "severity": "high",
                "evidence": "; ".join(gate_reasons or load_errors or [reason])[:1200],
                "fix_hint": "Inspect the AutoSci evidence payload and rerun the producing Scientific* node.",
            }
        ] if not ok else [],
        "warnings": [str(item) for item in gate_result.get("warnings") or [] if str(item).strip()],
        "evidence": {
            "adapter": "autosci_eval_adapter.py",
            "workflow_contract": str(graph.get("workflow_contract") or node.get("workflow_contract") or ""),
            "logical_operator": str(node.get("logical_operator") or ""),
            "capability_capsule_id": str(node.get("capability_capsule_id") or ""),
            "expected_schema": expected_schema,
            "observed_schema": str(evidence_payload.get("schema") or ""),
            "evidence_paths": evidence_refs,
            "candidate_paths": candidates,
            "gate_result": gate_result,
        },
        "provenance": {
            "operator_id": OPERATOR_ID,
            "implementation_package": "harness.plugins.autosci",
            "timestamp": _utc_now(),
            "graph_path": str(graph_path),
            "evidence_path": str(evidence_path) if evidence_path else "",
        },
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    gate = evidence.get("gate_result") if isinstance(evidence.get("gate_result"), dict) else {}
    failed = payload.get("failed_conditions") if isinstance(payload.get("failed_conditions"), list) else []
    passed = payload.get("passed_conditions") if isinstance(payload.get("passed_conditions"), list) else []
    lines = [
        f"# AutoSci Evaluation - {payload.get('sprint_id')} / {payload.get('node_id')}",
        "",
        "## Verdict",
        str(payload.get("verdict") or "FAIL"),
        "",
        "## Summary",
        str(payload.get("summary") or ""),
        "",
        "## Evidence",
        f"- Expected schema: `{evidence.get('expected_schema') or 'N/A'}`",
        f"- Observed schema: `{evidence.get('observed_schema') or 'N/A'}`",
        f"- Evidence paths: {', '.join(evidence.get('evidence_paths') or []) or 'N/A'}",
        f"- Gate status: `{gate.get('status') or 'N/A'}`",
        f"- Gate ok: `{bool(gate.get('ok'))}`",
        "",
        "## Passed Conditions",
        *(f"- {item}" for item in passed),
        "",
        "## Failed Conditions",
        *(f"- {item}" for item in failed),
        "",
        "## Provenance",
        f"- generated_by: `{payload.get('generated_by')}`",
        f"- generation_mode: `{payload.get('generation_mode')}`",
        f"- proof_level: `{payload.get('proof_level')}`",
        f"- independent_author: `{payload.get('independent_author')}`",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _apply_envelope_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if not args.envelope:
        return args
    envelope = _load_json(_resolve_path(args.envelope))
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    outputs = envelope.get("outputs") if isinstance(envelope.get("outputs"), dict) else {}
    args.graph = args.graph or envelope.get("graph_path") or inputs.get("graph_path")
    args.node = args.node or envelope.get("node_id") or inputs.get("node_id")
    args.eval_json = args.eval_json or outputs.get("eval_json_path") or inputs.get("eval_json_path")
    args.eval_md = args.eval_md or outputs.get("eval_md_path") or inputs.get("eval_md_path")
    args.instruction_file = args.instruction_file or inputs.get("instruction_file")
    args.verdict_mode = args.verdict_mode or inputs.get("verdict_mode") or "auto"
    args.reason = args.reason or inputs.get("reason") or ""
    return args


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    args = _apply_envelope_defaults(args)
    if not args.graph or not args.node or not args.eval_json or not args.eval_md:
        return 2, {
            "ok": False,
            "reason": "missing_required_args",
            "required": ["--graph", "--node", "--eval-json", "--eval-md"],
        }

    graph_path = _resolve_path(args.graph)
    graph = _load_json(graph_path)
    node_id = str(args.node)
    node = next((item for item in graph.get("nodes") or [] if isinstance(item, dict) and str(item.get("id") or "") == node_id), None)
    if not isinstance(node, dict):
        return 2, {"ok": False, "reason": "unknown_node", "node": node_id, "graph": str(graph_path)}

    evidence_path, evidence_payload, expected_schema, candidates, load_errors = _select_evidence(
        graph,
        node,
        graph_path=graph_path,
    )

    mode = str(args.verdict_mode or "auto").strip().lower()
    gate_result: dict[str, Any]
    if mode in {"pass", "passed"}:
        verdict = "PASS"
        gate_result = {"ok": True, "status": "passed", "reasons": [], "warnings": [], "forced": True}
        reason = args.reason or "AutoSci evaluator forced PASS by caller."
    elif mode in {"fail", "failed"}:
        verdict = "FAIL"
        gate_result = {"ok": False, "status": "failed", "reasons": [args.reason or "forced AutoSci evaluator failure"], "warnings": [], "forced": True}
        reason = args.reason or "AutoSci evaluator forced FAIL by caller."
    elif evidence_path is None:
        verdict = "FAIL"
        gate_result = {
            "ok": False,
            "status": "failed",
            "schema": expected_schema,
            "path": "",
            "reasons": ["missing AutoSci evidence payload for node"],
            "warnings": load_errors,
        }
        reason = args.reason or "AutoSci evaluator could not find node evidence."
    else:
        schema = expected_schema or str(evidence_payload.get("schema") or "")
        gate_result = _gate_evidence(evidence_path, schema)
        verdict = "PASS" if gate_result.get("ok") else "FAIL"
        reason = args.reason or (
            "AutoSci scientific evidence gate passed."
            if verdict == "PASS"
            else "AutoSci scientific evidence gate failed."
        )

    eval_payload = _eval_payload(
        graph=graph,
        node=node,
        graph_path=graph_path,
        evidence_path=evidence_path,
        evidence_payload=evidence_payload,
        expected_schema=expected_schema,
        gate_result=gate_result,
        verdict=verdict,
        reason=reason,
        candidates=candidates,
        load_errors=load_errors,
    )
    eval_json_path = _resolve_path(args.eval_json, graph_path=graph_path)
    eval_md_path = _resolve_path(args.eval_md, graph_path=graph_path)
    _write_json(eval_json_path, eval_payload)
    _write_markdown(eval_md_path, eval_payload)

    result = {
        "ok": True,
        "schema": "autosci_eval_adapter_result.v1",
        "status": "completed",
        "verdict": verdict,
        "node_id": node_id,
        "graph": str(graph_path),
        "eval_json": str(eval_json_path),
        "eval_md": str(eval_md_path),
        "evidence_path": str(evidence_path) if evidence_path else "",
        "expected_schema": expected_schema,
        "gate_result": gate_result,
    }
    return 0, result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", help="Operator envelope JSON carrying graph/node/eval paths.")
    parser.add_argument("--graph")
    parser.add_argument("--node")
    parser.add_argument("--eval-json")
    parser.add_argument("--eval-md")
    parser.add_argument("--instruction-file")
    parser.add_argument("--verdict-mode", default="auto", choices=["auto", "pass", "fail"])
    parser.add_argument("--reason", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    code, result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
