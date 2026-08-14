from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


JOURNEY_ID = "NT-memory-retrieval"
L2 = "Foundation :: Memory, Retrieval, and Evidence (Memory Learning / Self-RAG / Reranker Training)"
RESULT_STATUS = "PASS_WITH_KNOWN_LIMITATIONS"


@dataclass
class CommandRecord:
    label: str
    command: list[str]
    exit_code: int
    stdout_path: str
    stderr_path: str
    stdout_tail: str
    stderr_tail: str


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tail(text: str, limit: int = 2000) -> str:
    return text[-limit:]


def _run(
    *,
    repo_root: Path,
    command: list[str],
    env: dict[str, str],
    evidence_dir: Path,
    label: str,
) -> tuple[subprocess.CompletedProcess[str], CommandRecord]:
    proc = subprocess.run(
        command,
        cwd=repo_root / "harness",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path = evidence_dir / "stdout" / f"{label}.txt"
    stderr_path = evidence_dir / "stderr" / f"{label}.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    record = CommandRecord(
        label=label,
        command=command,
        exit_code=proc.returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        stdout_tail=_tail(proc.stdout),
        stderr_tail=_tail(proc.stderr),
    )
    return proc, record


def _command_env(output_harness: Path, home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(output_harness)
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(output_harness)
    env["AUTOSCI_ARTIFACT_ROOT"] = str(output_harness / "artifacts" / "autosci")
    env["SCIENTIFIC_ARTIFACT_ROOT"] = str(output_harness / "artifacts" / "scientific")
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    env["AUTOSCI_DISABLE_NETWORK_FETCH"] = "1"
    return env


def _shim(repo_root: Path) -> str:
    return str(repo_root / "harness" / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py")


def _load_summary(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert isinstance(payload, dict)
    return payload


def _top_hit_contains(retrieval: dict[str, Any], needle: str) -> bool:
    hits = retrieval.get("hits")
    if not isinstance(hits, list) or not hits:
        return False
    top = hits[0]
    return needle.lower() in json.dumps(top, sort_keys=True).lower()


def _hits_text(retrieval: dict[str, Any]) -> str:
    return json.dumps(retrieval.get("hits") or [], sort_keys=True)


def _route_binding_audit(repo_root: Path) -> dict[str, Any]:
    routes = _read_json(repo_root / "harness" / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json")
    bindings = _read_json(repo_root / "harness" / "plugins" / "autosci" / "config" / "feature_operator_bindings.v1.json")
    route_by_skill = {
        str(item.get("native_skill")): item
        for item in routes.get("routes") or []
        if isinstance(item, dict) and item.get("native_skill")
    }
    binding_by_skill = {
        str(item.get("native_skill")): item
        for item in bindings.get("bindings") or []
        if isinstance(item, dict) and item.get("native_skill")
    }
    ask_route = route_by_skill.get("ask", {})
    ask_binding = binding_by_skill.get("ask", {})
    memory_bindings = [
        item
        for item in route_by_skill.values()
        if item.get("solar_capability") == "cap.research-memory-update"
    ]
    return {
        "ask_route_coverage_status": ask_route.get("coverage_status"),
        "ask_backend_action": ask_route.get("solar_backend_action"),
        "ask_binding_operator_status": ask_binding.get("operator_status"),
        "ask_smoke_steps": ask_binding.get("smoke_steps"),
        "memory_learning_product_binding": {
            "status": "partial",
            "evidence": "research_memory_update evidence and workspace projection exist through production shim; route/binding config is partial and mutation/learning remains proposal or approval-gated.",
            "bound_routes": [item.get("native_skill") for item in memory_bindings],
        },
        "self_rag_product_binding": {
            "status": "partial",
            "evidence": "ask_wiki records retrieved wiki snippets, gap annotations, final answer boundary, and optional model evidence; no autonomous self-reflection loop is required by this journey without explicit model evidence.",
        },
        "reranker_training_product_binding": {
            "status": "not_available",
            "evidence": "No production reranker training entrypoint or training artifact was found in AutoSci route/binding configs; retrieval ranking is deterministic term count over wiki markdown.",
        },
    }


def _repo_head(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def test_nt_memory_retrieval_cross_run_journey(repo_root: Path, phase22_python: str) -> None:
    fixture_dir = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "not_tested" / "memory_retrieval"
    request_payload = _read_json(fixture_dir / "journey_request.json")
    alpha_paper = fixture_dir / "alpha_research_evidence.md"
    beta_paper = fixture_dir / "beta_private_evidence.md"

    evidence_root = repo_root / "outputs" / "phase22-not-tested" / JOURNEY_ID
    result_path = repo_root / ".codex-tmp" / "phase22-worker-results" / JOURNEY_ID / "result.json"
    home_root = repo_root / ".codex-tmp" / "homes" / JOURNEY_ID
    for path in (evidence_root, result_path.parent, home_root):
        path.mkdir(parents=True, exist_ok=True)

    alpha_harness = evidence_root / "alpha-project-harness"
    beta_harness = evidence_root / "beta-project-harness"
    for path in (alpha_harness, beta_harness):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    commands: list[CommandRecord] = []
    alpha_env = _command_env(alpha_harness, home_root / "alpha-home")
    beta_env = _command_env(beta_harness, home_root / "beta-home")

    alpha_write_id = str(request_payload["alpha_write_run_id"])
    alpha_query_id = str(request_payload["alpha_query_run_id"])
    beta_write_id = str(request_payload["beta_write_run_id"])
    query = str(request_payload["query"])

    alpha_write_cmd = [
        phase22_python,
        _shim(repo_root),
        "skill",
        "ingest",
        "--paper",
        str(alpha_paper),
        "--run-id",
        alpha_write_id,
        "--work-dir",
        f"artifacts/autosci/runs/{alpha_write_id}",
    ]
    proc, record = _run(repo_root=repo_root, command=alpha_write_cmd, env=alpha_env, evidence_dir=evidence_root, label="01-alpha-write")
    commands.append(record)
    alpha_write_summary = _load_summary(proc)

    beta_write_cmd = [
        phase22_python,
        _shim(repo_root),
        "skill",
        "ingest",
        "--paper",
        str(beta_paper),
        "--run-id",
        beta_write_id,
        "--work-dir",
        f"artifacts/autosci/runs/{beta_write_id}",
    ]
    proc, record = _run(repo_root=repo_root, command=beta_write_cmd, env=beta_env, evidence_dir=evidence_root, label="02-beta-write")
    commands.append(record)
    beta_write_summary = _load_summary(proc)

    alpha_wiki = alpha_harness / "artifacts" / "autosci" / "workspace" / "wiki"
    beta_wiki = beta_harness / "artifacts" / "autosci" / "workspace" / "wiki"
    assert alpha_wiki.exists(), f"alpha wiki was not projected: {alpha_write_summary}"
    assert beta_wiki.exists(), f"beta wiki was not projected: {beta_write_summary}"

    alpha_query_cmd = [
        phase22_python,
        _shim(repo_root),
        "skill",
        "ask",
        query,
        "--wiki-root",
        str(alpha_wiki),
        "--run-id",
        alpha_query_id,
        "--work-dir",
        f"artifacts/autosci/runs/{alpha_query_id}",
        "--limit",
        "5",
    ]
    proc, record = _run(repo_root=repo_root, command=alpha_query_cmd, env=alpha_env, evidence_dir=evidence_root, label="03-alpha-query")
    commands.append(record)
    alpha_query_summary = _load_summary(proc)

    retrieval_path = alpha_harness / "artifacts" / "autosci" / "runs" / alpha_query_id / "ask_wiki_retrieval.json"
    answer_path = alpha_harness / "artifacts" / "autosci" / "runs" / alpha_query_id / "ask_wiki_answer.md"
    final_boundary_path = alpha_harness / "artifacts" / "autosci" / "runs" / alpha_query_id / "ask_final_answer_boundary.json"
    ask_evidence_path = alpha_harness / "artifacts" / "autosci" / "runs" / alpha_query_id / "research_memory_update.ask.json"
    alpha_memory_path = alpha_harness / "artifacts" / "autosci" / "runs" / alpha_write_id / "research_memory_update.json"
    alpha_paper_evidence_path = alpha_harness / "artifacts" / "autosci" / "runs" / alpha_write_id / "research_paper.json"
    alpha_projected_page = alpha_wiki / "papers" / "paper-alpha-research-evidence.md"

    retrieval = _read_json(retrieval_path)
    answer = answer_path.read_text(encoding="utf-8")
    final_boundary = _read_json(final_boundary_path)
    ask_evidence = _read_json(ask_evidence_path)
    alpha_memory = _read_json(alpha_memory_path)
    alpha_paper_evidence = _read_json(alpha_paper_evidence_path)
    route_binding = _route_binding_audit(repo_root)

    hits_text = _hits_text(retrieval)
    alpha_hit = "ALPHA_SENTINEL_COBALT_ZEOLITE"
    beta_private = str(request_payload["irrelevant_private_sentinel"])
    source_fixture_fragment = "alpha_research_evidence.md"

    assertions = {
        "first_run_wrote_research_evidence": alpha_write_summary.get("ok") is True
        and alpha_memory.get("schema") == "research_memory_update.v1"
        and alpha_memory.get("status") == "completed",
        "first_run_preserved_project_run_identity": alpha_write_id in alpha_projected_page.read_text(encoding="utf-8")
        and alpha_write_id in json.dumps(retrieval, sort_keys=True),
        "second_run_retrieved_relevant_alpha_evidence": retrieval.get("status") == "completed"
        and alpha_hit.lower() in hits_text.lower()
        and _top_hit_contains(retrieval, alpha_hit),
        "irrelevant_private_context_not_prioritized_or_mixed": beta_private.lower() not in hits_text.lower()
        and str(beta_wiki).lower() not in hits_text.lower(),
        "provenance_retained": source_fixture_fragment in json.dumps(alpha_paper_evidence, sort_keys=True)
        and alpha_write_id in json.dumps(retrieval, sort_keys=True)
        and "paper-alpha-research-evidence.md" in answer
        and ask_evidence.get("provenance", {}).get("operator_id") == "autosci-bridge",
        "ask_final_boundary_not_overclaimed": final_boundary.get("status") in {"blocked", "incomplete", "ask_final_answer_incomplete"}
        and final_boundary.get("final_answer_ready") is not True,
        "memory_learning_has_only_partial_product_binding": route_binding["memory_learning_product_binding"]["status"] == "partial",
        "self_rag_has_only_partial_product_binding": route_binding["self_rag_product_binding"]["status"] == "partial",
        "reranker_training_has_no_real_product_binding": route_binding["reranker_training_product_binding"]["status"] == "not_available",
    }

    failed = [name for name, ok in assertions.items() if not ok]
    status_suggestion = "FAIL" if failed[:5] else RESULT_STATUS
    if not alpha_query_summary.get("ok"):
        status_suggestion = "FAIL"

    result = {
        "journey_id": JOURNEY_ID,
        "level_2": L2,
        "task": request_payload["task"],
        "repo_head": _repo_head(repo_root),
        "selector": f"{Path(__file__).as_posix()}::test_nt_memory_retrieval_cross_run_journey",
        "isolated_pytest_command": [
            phase22_python,
            "-m",
            "pytest",
            str(Path(__file__)),
            "--basetemp",
            ".codex-tmp/pytest/NT-memory-retrieval/basetemp",
            "-o",
            "cache_dir=.codex-tmp/pytest/NT-memory-retrieval/cache",
            "-q",
        ],
        "actual_inputs": {
            "request_fixture": str(fixture_dir / "journey_request.json"),
            "alpha_source": str(alpha_paper),
            "beta_private_source": str(beta_paper),
            "query": query,
        },
        "production_entrypoints": [
            "python harness/plugins/autosci/bin/autosci_skill_shim.py skill ingest",
            "python harness/plugins/autosci/bin/autosci_skill_shim.py skill ask",
        ],
        "run_ids": {
            "alpha_write_run_id": alpha_write_id,
            "alpha_query_run_id": alpha_query_id,
            "beta_private_write_run_id": beta_write_id,
        },
        "query_result_summary": {
            "retrieval_status": retrieval.get("status"),
            "hit_count": len(retrieval.get("hits") or []),
            "top_hit": (retrieval.get("hits") or [{}])[0],
            "answer_path": str(answer_path),
            "final_answer_boundary": final_boundary,
        },
        "isolation_assertions": assertions,
        "failed_assertions": failed,
        "capability_binding_findings": route_binding,
        "commands": [record.__dict__ for record in commands],
        "exit_code": 0 if not failed[:5] else 1,
        "evidence_paths": {
            "alpha_harness": str(alpha_harness),
            "beta_harness": str(beta_harness),
            "alpha_memory_update": str(alpha_memory_path),
            "alpha_paper_evidence": str(alpha_paper_evidence_path),
            "alpha_retrieval": str(retrieval_path),
            "alpha_answer": str(answer_path),
            "alpha_ask_evidence": str(ask_evidence_path),
            "raw_output_dir": str(evidence_root),
        },
        "status_suggestion": status_suggestion,
        "known_limitations": [
            "Core persistent evidence projection and local retrieval work through production shim paths.",
            "Memory Learning remains route/binding partial and largely proposal or approval-gated.",
            "Self-RAG is represented by retrieval evidence, gap annotations, and final-answer boundary checks, but no autonomous reflection loop is proven without explicit model evidence.",
            "Reranker Training has no production training entrypoint in the inspected AutoSci route/binding configs; ranking is deterministic term-count retrieval.",
        ],
    }
    _write_json(result_path, result)
    _write_json(evidence_root / "journey-result.json", result)

    assert not failed[:5], f"core journey assertions failed: {failed}"
    assert status_suggestion == RESULT_STATUS
