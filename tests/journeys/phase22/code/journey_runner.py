from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from evidence import JourneyRecorder, utc_now


def repo_root_from(path: Path) -> Path:
    return path.resolve().parents[4]


def python_executable(repo_root: Path) -> str:
    candidates = [
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if os.name != "nt" and candidate.suffix.lower() == ".exe":
            continue
        if candidate.exists():
            return str(candidate)
    return sys.executable


def base_env(repo_root: Path, sandbox: Path, *, allow_live: bool = False) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(sandbox / "home"),
            "USERPROFILE": str(sandbox / "home"),
            "SOLAR_HOME": str(sandbox / "home" / ".solar"),
            "CLAUDE_DIR": str(sandbox / "home" / ".claude"),
            "HARNESS_DIR": str(sandbox / "harness"),
            "AUTOSCI_ARTIFACT_ROOT": str(sandbox / "harness" / "artifacts" / "autosci"),
            "SCIENTIFIC_ARTIFACT_ROOT": str(sandbox / "harness" / "artifacts" / "scientific"),
            "SOLAR_AUTOSCI_OUTPUT_HARNESS": str(sandbox / "harness"),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    if allow_live:
        env.pop("AUTOSCI_DISABLE_NETWORK_FETCH", None)
    else:
        env["AUTOSCI_DISABLE_NETWORK_FETCH"] = "1"
        env.pop("OPENAI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENROUTER_API_KEY", None)
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    (sandbox / "home").mkdir(parents=True, exist_ok=True)
    (sandbox / "harness").mkdir(parents=True, exist_ok=True)
    return env


def copy_or_link(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        dst.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def prepare_isolated_harness(repo_root: Path, sandbox: Path) -> Path:
    source = repo_root / "harness"
    harness_dir = sandbox / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "bin",
        "config",
        "personas",
        "tools",
        "plugins",
        "evaluators",
        "schemas",
        "lib",
        "workflows",
        "solar-harness.sh",
    ):
        src = source / name
        if src.exists():
            copy_or_link(src, harness_dir / name)
    (harness_dir / "run").mkdir(exist_ok=True)
    (harness_dir / "artifacts").mkdir(exist_ok=True)
    return harness_dir


def run_autosci(
    recorder: JourneyRecorder,
    sandbox: Path,
    skill: str,
    args: list[str],
    *,
    timeout: float = 60,
    extra_env: dict[str, str] | None = None,
    allow_live: bool = False,
) -> tuple[dict[str, Any], Path]:
    harness_dir = prepare_isolated_harness(recorder.repo_root, sandbox)
    env = base_env(recorder.repo_root, sandbox, allow_live=allow_live)
    env["HARNESS_DIR"] = str(harness_dir)
    env["AUTOSCI_ARTIFACT_ROOT"] = str(harness_dir / "artifacts" / "autosci")
    env["SCIENTIFIC_ARTIFACT_ROOT"] = str(harness_dir / "artifacts" / "scientific")
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(harness_dir)
    if extra_env:
        env.update(extra_env)
    argv = [
        python_executable(recorder.repo_root),
        str(recorder.repo_root / "harness" / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"),
        "skill",
        skill,
        *args,
    ]
    proc = recorder.run(f"autosci-{skill}", argv, cwd=recorder.repo_root, env=env, timeout=timeout)
    if proc.returncode != 0:
        return {"_error": proc.stderr or proc.stdout, "_returncode": proc.returncode}, harness_dir
    try:
        return json.loads(proc.stdout), harness_dir
    except json.JSONDecodeError as exc:
        return {"_error": str(exc), "_stdout": proc.stdout}, harness_dir


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def action_evidence(summary: dict[str, Any], action: str) -> Path | None:
    evidence_path = summary.get("evidence_path")
    if not evidence_path:
        return None
    payload = load_json(Path(evidence_path))
    actions = payload.get("outputs", {}).get("skill_run", {}).get("actions", [])
    for item in actions:
        if item.get("action") == action and item.get("evidence_path"):
            return Path(item["evidence_path"])
    return None


def write_demo_paper(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Verifier-Guided Skill Learning for LLM Agents",
                "",
                "## Abstract",
                "This local paper studies verifier-guided skill learning for LLM agents.",
                "",
                "## Method",
                "The method normalizes agent outputs before exact-match verification and records verifier feedback.",
                "",
                "## Results",
                "A small controlled benchmark improves exact-match accuracy from 0.50 to 0.83.",
                "",
                "## Limitations",
                "The evidence is local and small, so broad deployment claims require further validation.",
                "",
                "## References",
                "- Smith et al. 2026. Verifier feedback for agent skill synthesis.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_pdf(path: Path, text: str) -> Path:
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()
    return path


def write_experiment_assets(root: Path, python_cmd: str) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    data = root / "samples.csv"
    data.write_text(
        "\n".join(
            [
                "text,label",
                "Pass: normalized verifier feedback,positive",
                "PASS - verifier result,positive",
                "fail: missing evidence,negative",
                "FAIL - no citation,negative",
                "pass with caveat,positive",
                "failure without source,negative",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runner = root / "run_text_experiment.py"
    runner.write_text(
        "\n".join(
            [
                "import csv, json, statistics, sys, time",
                "from pathlib import Path",
                "data = Path(sys.argv[1])",
                "out = Path(sys.argv[2])",
                "rows = list(csv.DictReader(data.open(encoding='utf-8')))",
                "details = []",
                "for mode in ('baseline', 'variant'):",
                "    correct = 0",
                "    latencies = []",
                "    for row in rows:",
                "        start = time.perf_counter()",
                "        text = row['text']",
                "        probe = text if mode == 'baseline' else text.lower().replace(' - ', ': ').replace('-', ':')",
                "        pred = 'positive' if probe.startswith('pass:') or probe.startswith('pass with') else 'negative'",
                "        elapsed = (time.perf_counter() - start) * 1000",
                "        latencies.append(elapsed)",
                "        correct += int(pred == row['label'])",
                "        details.append({'mode': mode, 'text': text, 'label': row['label'], 'prediction': pred, 'latency_ms': elapsed})",
                "    acc = correct / len(rows)",
                "    if mode == 'baseline':",
                "        baseline = {'accuracy': acc, 'median_latency_ms': statistics.median(latencies)}",
                "    else:",
                "        variant = {'accuracy': acc, 'median_latency_ms': statistics.median(latencies)}",
                "payload = {",
                "  'schema': 'phase22.local_text_experiment.v1',",
                "  'baseline': baseline,",
                "  'variant': variant,",
                "  'accuracy_uplift': variant['accuracy'] - baseline['accuracy'],",
                "  'details': details,",
                "}",
                "out.parent.mkdir(parents=True, exist_ok=True)",
                "out.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')",
                "print(json.dumps(payload))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    allowlist = root / "allowlist.json"
    result = root / "experiment-result.json"
    write_json(
        allowlist,
        {
            "commands": [
                " ".join([python_cmd, str(runner), str(data), "{after_artifact}"]),
            ],
        },
    )
    return {"data": data, "runner": runner, "allowlist": allowlist, "result": result}


def runtime_evidence(path: Path, command: list[str], result_path: Path, result_payload: dict[str, Any]) -> Path:
    payload = {
        "schema": "autosci_runtime_evidence.v1",
        "task_id": "phase22-j07-local-experiment",
        "sprint_id": "phase22-j07-local-experiment",
        "node_id": "run_experiment",
        "status": "completed",
        "inputs": {"approval_ref": "phase22-local-approval"},
        "outputs": {
            "runtime": {
                "action": "run_experiment",
                "status": "completed",
                "approval_ref": "phase22-local-approval",
                "exit_code": 0,
                "command_run": " ".join(command),
                "outcome": "supports" if result_payload["accuracy_uplift"] >= 0.2 else "does_not_support",
                "result_collected": True,
                "metrics": [
                    {"name": "baseline_accuracy", "value": result_payload["baseline"]["accuracy"]},
                    {"name": "variant_accuracy", "value": result_payload["variant"]["accuracy"]},
                    {"name": "accuracy_uplift", "value": result_payload["accuracy_uplift"]},
                    {"name": "variant_median_latency_ms", "value": result_payload["variant"]["median_latency_ms"]},
                ],
                "evidence_ids": ["runtime:phase22-j07-local-python"],
                "logs": ["phase22 local Python subprocess completed"],
            }
        },
        "artifacts": [{"type": "local_experiment_result", "path": str(result_path)}],
        "provenance": {
            "operator_id": "phase22-journey-test",
            "implementation_package": "tests.journeys.phase22.code",
            "timestamp": utc_now(),
        },
        "limitations": ["Small deterministic local dataset; not a broad external benchmark."],
    }
    return write_json(path, payload)


def has_live_authorization() -> bool:
    return os.environ.get("PHASE22_ENABLE_LIVE_JOURNEYS") == "1"


def has_network_authorization() -> bool:
    return os.environ.get("PHASE22_ENABLE_NETWORK_JOURNEYS") == "1"


def find_bash(repo_root: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    for key in ("PHASE22_BASH", "BASH_EXE", "GIT_BASH"):
        raw = os.environ.get(key)
        if raw:
            candidates.append(Path(raw))
    if repo_root is not None:
        config = repo_root / ".codex" / "phase22-bash.txt"
        if config.exists() and config.is_file():
            raw = config.read_text(encoding="utf-8", errors="replace").strip()
            if raw:
                candidates.append(Path(raw))
    which_bash = shutil.which("bash")
    if which_bash:
        candidates.append(Path(which_bash))
    candidates.extend(
        [
            Path("C:/Program Files/Git/bin/bash.exe"),
            Path("C:/Program Files/Git/usr/bin/bash.exe"),
            Path("C:/Program Files (x86)/Git/bin/bash.exe"),
            Path("C:/Program Files (x86)/Git/usr/bin/bash.exe"),
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def bash_argv(repo_root: Path, *args: str) -> list[str]:
    bash = find_bash(repo_root)
    if bash is None:
        return ["bash", *args]
    return [str(bash), *args]


def bash_blocker(repo_root: Path | None = None) -> str | None:
    if find_bash(repo_root) is not None:
        return None
    return (
        "bash is not available via PHASE22_BASH/BASH_EXE/GIT_BASH, project .codex/phase22-bash.txt, "
        "PATH, or common Git for Windows locations."
    )


def write_research_claims(path: Path, claims: list[dict[str, Any]], *, task_id: str) -> Path:
    payload = {
        "schema": "research_claims.v1",
        "task_id": task_id,
        "sprint_id": "phase22-real-journeys",
        "node_id": "phase22-claim-fixture",
        "status": "completed",
        "inputs": {"source": "phase22 local journey handoff fixture"},
        "outputs": {"claims": claims},
        "artifacts": [],
        "provenance": {
            "operator_id": "phase22-journey-test",
            "implementation_package": "tests.journeys.phase22.code",
            "timestamp": utc_now(),
        },
        "limitations": ["Local handoff fixture; not external scientific validation."],
    }
    return write_json(path, payload)


def write_experiment_result_evidence(
    path: Path,
    *,
    task_id: str,
    experiment_id: str,
    outcome: str,
    metrics: list[dict[str, Any]],
    evidence_ids: list[str],
) -> Path:
    payload = {
        "schema": "experiment_result.v1",
        "task_id": task_id,
        "sprint_id": "phase22-real-journeys",
        "node_id": "phase22-experiment-result",
        "status": "completed",
        "inputs": {"source": "phase22 local runtime evidence"},
        "outputs": {
            "result": {
                "experiment_id": experiment_id,
                "outcome": outcome,
                "metrics": metrics,
                "evidence_ids": evidence_ids,
            }
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "phase22-journey-test",
            "implementation_package": "tests.journeys.phase22.code",
            "timestamp": utc_now(),
        },
        "limitations": ["Small deterministic local dataset; not a broad external benchmark."],
    }
    return write_json(path, payload)


def write_code_evidence(path: Path, *, claim_id: str, files: list[str]) -> Path:
    return write_json(
        path,
        {
            "schema": "code_evidence_map.v1",
            "task_id": f"phase22-code-evidence-{claim_id}",
            "sprint_id": "phase22-real-journeys",
            "node_id": "phase22-code-map",
            "status": "completed",
            "inputs": {"source": "phase22 local experiment runner"},
            "outputs": {
                "mappings": [
                    {
                        "mapping_id": f"phase22-code-map-{claim_id}",
                        "claim_id": claim_id,
                        "files": files,
                        "evidence_ids": [f"code:{claim_id}"],
                    }
                ]
            },
            "artifacts": [],
            "provenance": {
                "operator_id": "phase22-journey-test",
                "implementation_package": "tests.journeys.phase22.code",
                "timestamp": utc_now(),
            },
            "limitations": ["Code evidence map points to the deterministic local journey runner."],
        },
    )
