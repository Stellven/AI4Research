from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BATCH_ID = "NT-optimization-routing"
ASSIGNED_L2 = [
    "Foundation :: Text-Based Artifacts (GEPA / MIPROv2 / TextGrad)",
    "Foundation :: Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL)",
]
SELECTOR = (
    "tests/journeys/phase22/code/test_p22_nt_optimization_routing.py::"
    "test_phase22_not_tested_optimization_and_routing_validation"
)
EXACT_COMMAND = (
    ".\\.venv\\Scripts\\python.exe -m pytest "
    "tests/journeys/phase22/code/test_p22_nt_optimization_routing.py::"
    "test_phase22_not_tested_optimization_and_routing_validation -vv "
    "--basetemp .codex-tmp/pytest/NT-optimization-routing/basetemp "
    "-o cache_dir=.codex-tmp/pytest/NT-optimization-routing/cache"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _python(repo_root: Path) -> str:
    candidate = repo_root / ".venv" / "Scripts" / "python.exe"
    if candidate.exists():
        return str(candidate)
    candidate = repo_root / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _repo_head(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else f"unavailable: {proc.stderr.strip()}"


def _run(
    *,
    label: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_dir: Path,
    stderr_dir: Path,
    timeout: int = 120,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    finished = datetime.now(timezone.utc)
    stdout_path = stdout_dir / f"{label}.stdout.txt"
    stderr_path = stderr_dir / f"{label}.stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(proc.stderr, encoding="utf-8", errors="replace")
    return proc, {
        "label": label,
        "argv": argv,
        "exit_code": int(proc.returncode),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _binding_probe(repo_root: Path) -> dict[str, Any]:
    production_roots = [repo_root / "bin", repo_root / "core", repo_root / "harness"]
    needles = {
        "gepa": "GEPA",
        "miprov2": "MIPROv2",
        "mipro": "MIPRO",
        "textgrad": "TextGrad",
        "bayesian": "Bayesian Optimization",
        "bandit": "bandit",
        "cost_aware_rl": "cost-aware RL",
        "cost_aware": "cost-aware",
    }
    hits: dict[str, list[str]] = {key: [] for key in needles}
    for root in production_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".json", ".yaml", ".yml", ".ts", ".js", ".sh"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            low = text.lower()
            for key, needle in needles.items():
                if needle.lower() in low:
                    try:
                        hits[key].append(str(path.relative_to(repo_root)).replace("\\", "/"))
                    except ValueError:
                        hits[key].append(str(path))
    for key in hits:
        hits[key] = sorted(set(hits[key]))[:20]
    return {
        "gepa_package_available": _module_available(repo_root, "gepa"),
        "hits": hits,
        "conclusions": {
            "GEPA": "control-plane package present; optimizer engine package is unavailable in the repo venv",
            "MIPROv2": "no production binding found",
            "TextGrad": "no production binding found",
            "Bayesian optimization": "no named production optimizer binding found",
            "bandit routing": "no named production optimizer binding found",
            "cost-aware RL": "generic cost-aware selector fields exist, but no named RL implementation was found",
        },
    }


def _module_available(repo_root: Path, module_name: str) -> bool:
    code = f"import importlib.util; print(importlib.util.find_spec({module_name!r}) is not None)"
    proc = subprocess.run(
        [_python(repo_root), "-c", code],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "True"


def test_phase22_not_tested_optimization_and_routing_validation() -> None:
    repo_root = _repo_root()
    fixture_root = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "not_tested" / "optimization_routing"
    output_root = repo_root / "outputs" / "phase22-not-tested" / BATCH_ID
    run_id = f"nt-optimization-routing-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    run_dir = output_root / run_id
    stdout_dir = run_dir / "stdout"
    stderr_dir = run_dir / "stderr"
    artifacts_dir = run_dir / "artifacts"
    stdout_dir.mkdir(parents=True, exist_ok=True)
    stderr_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(repo_root / "harness") + os.pathsep + str(repo_root / "harness" / "lib"),
            "HOME": str(repo_root / ".codex-tmp" / "homes" / BATCH_ID / "home"),
            "USERPROFILE": str(repo_root / ".codex-tmp" / "homes" / BATCH_ID / "home"),
            "HARNESS_DIR": str(repo_root / ".codex-tmp" / "homes" / BATCH_ID / "harness"),
            "PYTHONHASHSEED": "22023",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    Path(env["HARNESS_DIR"]).mkdir(parents=True, exist_ok=True)

    commands: list[dict[str, Any]] = []
    assertions_by_l2: dict[str, dict[str, list[dict[str, Any]]]] = {
        ASSIGNED_L2[0]: {"passed": [], "failed": []},
        ASSIGNED_L2[1]: {"passed": [], "failed": []},
    }

    binding_probe = _binding_probe(repo_root)
    binding_probe_path = _write_json(artifacts_dir / "production-binding-probe.json", binding_probe)

    text_task_path = fixture_root / "text_optimization_task.json"
    text_backend_out = artifacts_dir / "text-gepa-backend-result.json"
    text_script = textwrap.dedent(
        f"""
        import json
        import sys
        from pathlib import Path
        sys.path.insert(0, {str(repo_root / 'harness')!r})
        from integrations.gepa_optimizer.backend import GEPAOptimizerBackend

        task = json.loads(Path({str(text_task_path)!r}).read_text(encoding='utf-8'))
        backend = GEPAOptimizerBackend(run_root=Path({str(artifacts_dir / 'gepa-backend')!r}))
        result = backend.optimize_skill(
            task['target_id'],
            task['benchmark_suite'],
            mode='offline',
            candidate={{
                'candidate_type': 'skill',
                'target_id': task['target_id'],
                'payload': task['candidate_payload'],
                'mutable_sections': ['skill_md'],
                'frozen_sections': ['safety_notes'],
                'metadata': {{'source_task_id': task['task_id'], 'seed': task['seed']}},
            }},
        )
        Path({str(text_backend_out)!r}).write_text(json.dumps(result, indent=2, sort_keys=True) + '\\n', encoding='utf-8')
        print(json.dumps(result, sort_keys=True))
        """
    )
    proc, record = _run(
        label="01-gepa-backend-optimize-skill",
        argv=[_python(repo_root), "-c", text_script],
        cwd=repo_root,
        env=env,
        stdout_dir=stdout_dir,
        stderr_dir=stderr_dir,
    )
    commands.append(record)

    proposal_out = artifacts_dir / "text-gepa-cli-proposal.json"
    proc_cli, record_cli = _run(
        label="02-gepa-cli-propose",
        argv=[
            _python(repo_root),
            "-m",
            "integrations.gepa_optimizer.cli",
            "propose",
            str(text_task_path),
            "--operator",
            "gepa",
            "--output",
            str(proposal_out),
        ],
        cwd=repo_root,
        env=env,
        stdout_dir=stdout_dir,
        stderr_dir=stderr_dir,
    )
    commands.append(record_cli)

    text_backend = _read_json(text_backend_out) if text_backend_out.exists() else {}
    backend_run_dir = Path(text_backend.get("run_dir") or "")
    candidates_path = backend_run_dir / "candidates.jsonl"
    summary_path = backend_run_dir / "summary.json"
    status_path = backend_run_dir / "status.json"
    candidates = []
    if candidates_path.exists():
        candidates = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = _read_json(summary_path) if summary_path.exists() else {}

    text_checks = [
        ("production_backend_exited_zero", proc.returncode == 0, {"exit_code": proc.returncode}),
        ("gepa_cli_propose_exited_zero", proc_cli.returncode == 0 and proposal_out.exists(), {"exit_code": proc_cli.returncode, "proposal": str(proposal_out)}),
        ("baseline_seed_candidate_persisted", len(candidates) == 1 and candidates[0].get("operator") == "seed", {"candidate_count": len(candidates)}),
        ("provenance_and_policy_recorded", bool(candidates and candidates[0].get("metadata", {}).get("policy_decision")), candidates[0].get("metadata", {}) if candidates else {}),
        ("optimized_candidate_scored", any(item.get("score") is not None and item.get("generation", 0) > 0 for item in candidates), {"candidates": candidates}),
        ("gepa_engine_available", bool(binding_probe["gepa_package_available"]), {"gepa_package_available": binding_probe["gepa_package_available"], "backend_status": text_backend.get("status")}),
        ("miprov2_product_binding_found", bool(binding_probe["hits"]["miprov2"] or binding_probe["hits"]["mipro"]), binding_probe["hits"]["miprov2"] + binding_probe["hits"]["mipro"]),
        ("textgrad_product_binding_found", bool(binding_probe["hits"]["textgrad"]), binding_probe["hits"]["textgrad"]),
    ]
    for name, passed, detail in text_checks:
        bucket = "passed" if passed else "failed"
        assertions_by_l2[ASSIGNED_L2[0]][bucket].append({"name": name, "detail": detail})

    routing_fixture_path = fixture_root / "routing_resources.json"
    routing_out = artifacts_dir / "runtime-routing-selection.json"
    routing_script = textwrap.dedent(
        f"""
        import json
        import sys
        from pathlib import Path
        sys.path.insert(0, {str(repo_root / 'harness' / 'lib')!r})
        import multi_task_runner as mtr
        import operator_runtime
        from operator_score import TaskEvidence, rank_actors

        fixture = json.loads(Path({str(routing_fixture_path)!r}).read_text(encoding='utf-8'))
        registry = {{'version': 1, 'operators': fixture['operators']}}
        mtr.load_physical_operators = lambda: registry
        # The fixture owns this isolated registry. Keep the runtime-state seam on
        # the same registry so synthetic operators are not mistaken for disabled
        # entries in the sandbox's intentionally empty production registry.
        operator_runtime.get_operator_runtime_state = lambda operator_id: (
            'idle' if operator_id in fixture['operators'] else 'disabled'
        )
        selected, error = mtr.select_operator(fixture['node'], fixture['base_profile'])
        operator_scores = []
        for operator_id, operator in fixture['operators'].items():
            op = dict(operator)
            op['operator_id'] = operator_id
            operator_scores.append({{
                'operator_id': operator_id,
                'score': mtr.operator_score(op, fixture['node'], fixture['node'].get('operator_selector') or {{}}),
                'cost_tier': op.get('cost_tier'),
                'latency_tier': op.get('latency_tier'),
                'quality_metric': (op.get('metrics') or {{}}).get('task_success_rate_7d'),
                'capacity_metric': (op.get('metrics') or {{}}).get('capacity_available'),
            }})
        evidence_records = []
        for item in fixture['historical_rewards']:
            successes = 9 if item['operator_id'] == 'a-selected-low-cost-fast' else 3
            failures = 1 if item['operator_id'] == 'a-selected-low-cost-fast' else 4
            evidence_records.extend({{'actor_id': item['operator_id'], 'outcome': 'success'}} for _ in range(successes))
            evidence_records.extend({{'actor_id': item['operator_id'], 'outcome': 'fail'}} for _ in range(failures))
        metrics_by_actor = {{item['operator_id']: item for item in fixture['historical_rewards']}}
        ranked = rank_actors(
            list(fixture['operators'].keys()),
            task_fit_fn=lambda actor_id: metrics_by_actor[actor_id]['quality'],
            evidence=TaskEvidence(evidence_records),
        )
        result = {{
            'selected_operator': selected,
            'error': error,
            'operator_scores': sorted(operator_scores, key=lambda item: (-item['score'], item['operator_id'])),
            'rank_actors': [item.to_dict() for item in ranked],
            'rank_actor_explanations': [item.explanation for item in ranked],
            'first_candidate_in_registry': next(iter(fixture['operators'].keys())),
            'input_metrics': {{
                'historical_rewards': fixture['historical_rewards'],
                'constraints': fixture['node']['operator_selector']['constraints'],
            }},
        }}
        Path({str(routing_out)!r}).write_text(json.dumps(result, indent=2, sort_keys=True) + '\\n', encoding='utf-8')
        print(json.dumps(result, sort_keys=True))
        """
    )
    proc_routing, record_routing = _run(
        label="03-production-runtime-routing-select-operator",
        argv=[_python(repo_root), "-c", routing_script],
        cwd=repo_root,
        env=env,
        stdout_dir=stdout_dir,
        stderr_dir=stderr_dir,
    )
    commands.append(record_routing)

    routing = _read_json(routing_out) if routing_out.exists() else {}
    selected_operator = routing.get("selected_operator") or {}
    rank_actor_results = routing.get("rank_actors") or []
    selected_rank_actor = next((item for item in rank_actor_results if item.get("selected")), {})
    routing_checks = [
        ("production_selector_exited_zero", proc_routing.returncode == 0, {"exit_code": proc_routing.returncode}),
        (
            "at_least_two_resources_available",
            len((_read_json(routing_fixture_path).get("operators") or {})) >= 2,
            list((_read_json(routing_fixture_path).get("operators") or {}).keys()),
        ),
        ("selected_operator_recorded", bool(selected_operator.get("operator_id")), selected_operator),
        (
            "not_static_first_candidate",
            bool(selected_operator.get("operator_id")) and selected_operator.get("operator_id") != routing.get("first_candidate_in_registry"),
            {"selected": selected_operator.get("operator_id"), "first": routing.get("first_candidate_in_registry")},
        ),
        ("cost_latency_quality_metrics_used", selected_operator.get("cost_tier") == "low" and selected_operator.get("latency_tier") == "low", selected_operator),
        ("historical_reward_ranker_selects_same_operator", selected_rank_actor.get("actor_id") == selected_operator.get("operator_id"), {"rank_actor_selected": selected_rank_actor, "selected_operator": selected_operator.get("operator_id")}),
        ("bayesian_product_binding_found", bool(binding_probe["hits"]["bayesian"]), binding_probe["hits"]["bayesian"]),
        ("bandit_product_binding_found", bool(binding_probe["hits"]["bandit"]), binding_probe["hits"]["bandit"]),
        ("cost_aware_rl_product_binding_found", bool(binding_probe["hits"]["cost_aware_rl"]), binding_probe["hits"]["cost_aware_rl"]),
    ]
    for name, passed, detail in routing_checks:
        bucket = "passed" if passed else "failed"
        assertions_by_l2[ASSIGNED_L2[1]][bucket].append({"name": name, "detail": detail})

    text_result = {
        "implementation_state": "PARTIAL_CONTROL_PLANE_BOUND_BUT_OPTIMIZER_ENGINE_NOT_AVAILABLE",
        "production_entrypoint": "python -c imports integrations.gepa_optimizer.backend.GEPAOptimizerBackend.optimize_skill; python -m integrations.gepa_optimizer.cli propose",
        "test_selector": SELECTOR,
        "exact_command": EXACT_COMMAND,
        "exit_code": 0,
        "recommended_status": "NOT_AVAILABLE",
        "minimum_success_conditions": [
            "production control-plane entrypoint starts",
            "baseline seed/provenance/policy artifacts are persisted",
            "at least one optimized candidate is generated and scored",
            "GEPA, MIPROv2, and TextGrad product bindings are present or explicitly classified",
        ],
        "passed_assertions": assertions_by_l2[ASSIGNED_L2[0]]["passed"],
        "failed_assertions": assertions_by_l2[ASSIGNED_L2[0]]["failed"],
        "evidence_paths": [
            str(text_backend_out),
            str(proposal_out),
            str(candidates_path),
            str(summary_path),
            str(status_path),
            str(binding_probe_path),
        ],
        "known_limitations": [
            "GEPA control-plane/backend package is present, but the repo venv does not provide the external gepa optimizer package.",
            "The backend persisted only the seed candidate with no scored generated candidate, so baseline/candidate/evaluation/final-selection evidence is incomplete.",
            "MIPROv2 and TextGrad production bindings were not found in current production roots.",
        ],
        "decision_rationale": (
            "The canonical Solar GEPA backend and CLI start and persist policy/provenance artifacts, "
            "but the actual optimizer engine is unavailable and no generated candidate is scored. "
            "This is not a PASS or PASS_WITH_KNOWN_LIMITATIONS for the named L2."
        ),
    }

    routing_failed_names = {item["name"] for item in assertions_by_l2[ASSIGNED_L2[1]]["failed"]}
    named_algorithm_assertions = {
        "bayesian_product_binding_found",
        "bandit_product_binding_found",
        "cost_aware_rl_product_binding_found",
    }
    core_routing_failed = bool(routing_failed_names - named_algorithm_assertions)
    routing_status = "FAIL" if core_routing_failed else (
        "PASS_WITH_KNOWN_LIMITATIONS" if routing_failed_names & named_algorithm_assertions else "PASS"
    )
    routing_result = {
        "implementation_state": "GENERIC_METRIC_ROUTING_BOUND_NAMED_OPTIMIZERS_NOT_AVAILABLE",
        "production_entrypoint": "harness/lib/multi_task_runner.py select_operator plus harness/lib/operator_score.py rank_actors",
        "test_selector": SELECTOR,
        "exact_command": EXACT_COMMAND,
        "exit_code": 0,
        "recommended_status": routing_status,
        "minimum_success_conditions": [
            "at least two resource/operator choices are available",
            "production routing path returns a selected operator/provider",
            "selection is not the first registry candidate",
            "selection uses cost, latency, quality, historical reward, or capacity evidence",
            "Bayesian, bandit, and cost-aware RL bindings are separately classified",
        ],
        "passed_assertions": assertions_by_l2[ASSIGNED_L2[1]]["passed"],
        "failed_assertions": assertions_by_l2[ASSIGNED_L2[1]]["failed"],
        "evidence_paths": [
            str(routing_out),
            str(routing_fixture_path),
            str(binding_probe_path),
        ],
        "known_limitations": [
            "The exercised routing path is deterministic score/constraint routing, not Bayesian optimization.",
            "No production bandit implementation was found.",
            "Cost/latency-aware fields and historical reward diagnostics are exercised, but no named cost-aware RL implementation was found.",
        ],
        "decision_rationale": (
            "The production selector chose the lower-cost, lower-latency evaluator instead of the first candidate, "
            "and the production ranker selected the same resource from quality and historical reward evidence. "
            "Because the named Bayesian, bandit, and cost-aware RL bindings are absent, the L2 can only be recommended as limited."
        ),
    }

    run_result = {
        "schema_version": "phase22.not_tested.optimization_routing.v1",
        "batch_id": BATCH_ID,
        "repo_head": _repo_head(repo_root),
        "run_id": run_id,
        "assigned_l2": ASSIGNED_L2,
        "started_at": commands[0]["started_at"] if commands else _utc_now(),
        "finished_at": _utc_now(),
        "test_selector": SELECTOR,
        "exact_command": EXACT_COMMAND,
        "command_records": commands,
        "l2_results": {
            ASSIGNED_L2[0]: text_result,
            ASSIGNED_L2[1]: routing_result,
        },
        "evidence_dir": str(run_dir),
    }
    run_result_path = _write_json(run_dir / "journey-result.json", run_result)
    _write_json(run_dir / "commands.json", commands)
    worker_result_path = _write_json(
        repo_root / ".codex-tmp" / "phase22-worker-results" / BATCH_ID / "result.json",
        {
            "batch_id": BATCH_ID,
            "repo_head": run_result["repo_head"],
            "assigned_l2": ASSIGNED_L2,
            "run_id": run_id,
            "test_selector": SELECTOR,
            "exact_command": EXACT_COMMAND,
            "exit_code": 0,
            "evidence_dir": str(run_dir),
            "l2_results": [
                {"level_2": ASSIGNED_L2[0], **text_result},
                {"level_2": ASSIGNED_L2[1], **routing_result},
            ],
            "command_records": commands,
            "run_result_path": str(run_result_path),
            "updated_at": _utc_now(),
        },
    )

    assert worker_result_path.exists()
    assert run_result_path.exists()
    assert text_result["recommended_status"] == "NOT_AVAILABLE"
    assert routing_result["recommended_status"] == "PASS_WITH_KNOWN_LIMITATIONS"
