from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parents[3]
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"


def run_shim(tmp_path: Path, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SHIM), *args],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=int(env.get("AUTOSCI_LIVE_PROVIDER_TEST_TIMEOUT", "120")),
    )


def require_live_flag(flag: str) -> None:
    if os.environ.get("AUTOSCI_LIVE_PROVIDER_TESTS") != "1" or os.environ.get(flag) != "1":
        pytest.skip(f"Set AUTOSCI_LIVE_PROVIDER_TESTS=1 and {flag}=1 to run this live provider test.")


def load_action_evidence(tmp_path: Path, proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    return json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))


def test_autosci_live_review_llm_provider_produces_runtime_proof(tmp_path: Path) -> None:
    require_live_flag("AUTOSCI_LIVE_REVIEW_LLM_TEST")
    if not (
        os.environ.get("AUTOSCI_REVIEW_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    ):
        pytest.skip("Live Review LLM provider test requires AUTOSCI_REVIEW_LLM_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY.")

    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "outputs").mkdir(parents=True)
    target = wiki_root / "outputs/live-review-provider-target.md"
    target.write_text(
        "---\ntitle: Live Provider Review Target\n---\n"
        "# Live Provider Review Target\n\n"
        "The method claim cites a dataset, baseline, metric, and evidence artifact. "
        "Review whether the evidence is sufficient for a cautious research claim.\n",
        encoding="utf-8",
    )
    provider = os.environ.get("AUTOSCI_LIVE_REVIEW_LLM_PROVIDER") or os.environ.get("AUTOSCI_REVIEW_LLM_PROVIDER") or "openai"
    model = os.environ.get("AUTOSCI_LIVE_REVIEW_LLM_MODEL") or os.environ.get("AUTOSCI_REVIEW_LLM_MODEL") or "gpt-5.5"
    endpoint = os.environ.get("AUTOSCI_LIVE_REVIEW_LLM_ENDPOINT") or os.environ.get("AUTOSCI_REVIEW_LLM_ENDPOINT") or ""
    args = [
        "$review",
        "live-review-provider-target",
        "--from-wiki",
        "--review",
        "--difficulty",
        "hard",
        "--focus",
        "method",
        "--review-llm-provider",
        provider,
        "--review-llm-model",
        model,
        "--run-id",
        "live-review-llm-provider",
    ]
    if endpoint:
        args.extend(["--review-llm-endpoint", endpoint])

    evidence = load_action_evidence(tmp_path, run_shim(tmp_path, *args))
    review = evidence["outputs"]["review"]
    review_llm = review["review_llm"]
    assert review["review_mode"] == "review_llm"
    assert review["review_available"] is True
    assert review_llm["status"] == "completed"
    assert review_llm["invocation_mode"] == "provider"
    assert review_llm["provider"] in {"openai", "openrouter", "openai_compatible"}
    proof_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "review_model_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["collection_mode"] == "live_provider"
    assert proof_entry["categories"] == [
        "review_llm_or_model_evidence",
        "external_runtime_evidence",
        "provider_source_evidence",
    ]


def test_autosci_live_semantic_scholar_novelty_provider_produces_runtime_proof(tmp_path: Path) -> None:
    require_live_flag("AUTOSCI_LIVE_NOVELTY_PROVIDER_TEST")
    query = os.environ.get("AUTOSCI_LIVE_NOVELTY_QUERY") or "large language model agents scientific discovery"
    evidence = load_action_evidence(
        tmp_path,
        run_shim(
            tmp_path,
            "$novelty",
            query,
            "--online",
            "--run-id",
            "live-novelty-semantic-scholar",
            extra_env={
                "AUTOSCI_DISABLE_NETWORK_FETCH": "0",
                "AUTOSCI_NOVELTY_PROVIDERS": os.environ.get("AUTOSCI_LIVE_NOVELTY_PROVIDERS", "semantic_scholar"),
                "AUTOSCI_NOVELTY_FETCH_TIMEOUT": os.environ.get("AUTOSCI_LIVE_NOVELTY_FETCH_TIMEOUT", "30"),
            },
        ),
    )
    evaluation = evidence["outputs"]["evaluations"][0]
    external = evaluation["external_novelty"]
    assert external["status"] == "completed"
    assert external["source_count"] >= 1
    provider_status = next(item for item in external["provider_statuses"] if item.get("status") == "completed")
    assert provider_status["raw_payload_ref"].startswith(("http://", "https://"))
    assert provider_status["raw_payload_archive_status"] == "completed"
    proof_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["collection_mode"] == "live_provider"
    assert proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]


def test_autosci_live_remote_status_provider_produces_runtime_proof(tmp_path: Path) -> None:
    require_live_flag("AUTOSCI_LIVE_REMOTE_STATUS_TEST")
    status_command = os.environ.get("AUTOSCI_LIVE_REMOTE_STATUS_COMMAND", "").strip()
    session_id = os.environ.get("AUTOSCI_LIVE_REMOTE_SESSION_ID", "").strip()
    if not status_command:
        pytest.skip("Live remote status test requires AUTOSCI_LIVE_REMOTE_STATUS_COMMAND.")
    if not session_id:
        pytest.skip("Live remote status test requires AUTOSCI_LIVE_REMOTE_SESSION_ID.")

    experiment = os.environ.get("AUTOSCI_LIVE_REMOTE_EXPERIMENT", "live-remote-status")
    transport = os.environ.get("AUTOSCI_LIVE_REMOTE_TRANSPORT", "ssh")
    timeout = os.environ.get("AUTOSCI_LIVE_REMOTE_STATUS_TIMEOUT", "60")
    remote_run_dir = os.environ.get("AUTOSCI_LIVE_REMOTE_RUN_DIR", "").strip()

    before = tmp_path / "live-remote-status-before.json"
    before.write_text(json.dumps({"state": "before-live-remote-status"}), encoding="utf-8")
    inner_allowlist = tmp_path / "live-remote-status-inner-allowlist.json"
    inner_allowlist.write_text(json.dumps({"commands": [status_command]}), encoding="utf-8")

    remote_check_tokens = [
        sys.executable,
        str(HARNESS.parent / "tools" / "remote.py"),
        "check",
        "--experiment",
        experiment,
        "--approval-ref",
        "approval-live-remote-status",
        "--allowlist-evidence",
        str(inner_allowlist),
        "--status-command",
        status_command,
        "--transport",
        transport,
        "--session-id",
        session_id,
        "--timeout-seconds",
        timeout,
        "--execute-approved",
    ]
    if remote_run_dir:
        remote_check_tokens.extend(["--run-dir", remote_run_dir])
    remote_check_command = shlex.join(remote_check_tokens)

    outer_allowlist = tmp_path / "live-remote-status-outer-allowlist.json"
    outer_allowlist.write_text(json.dumps({"commands": [" ".join(remote_check_tokens)]}), encoding="utf-8")

    evidence = load_action_evidence(
        tmp_path,
        run_shim(
            tmp_path,
            "$exp-status",
            experiment,
            "--env",
            "remote",
            "--approval-ref",
            "approval-live-remote-status",
            "--allowlist-evidence",
            str(outer_allowlist),
            "--before-artifact",
            str(before),
            "--remote-check-command",
            remote_check_command,
            "--execute-approved",
            "--run-id",
            "live-remote-status-provider",
        ),
    )
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == experiment
    assert report["state"] in {"completed", "failed", "running"}
    assert any("remote_poll_boundary_status=live_remote_poll" in item for item in report["observations"])
    proof_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "exp-status"
    assert proof_entry["collection_mode"] == "live_provider"
    assert proof_entry["categories"] == ["external_runtime_evidence", "provider_source_evidence"]


def test_autosci_live_remote_launch_provider_produces_runtime_evidence(tmp_path: Path) -> None:
    require_live_flag("AUTOSCI_LIVE_REMOTE_LAUNCH_TEST")
    launch_command = os.environ.get("AUTOSCI_LIVE_REMOTE_LAUNCH_COMMAND", "").strip()
    if not launch_command:
        pytest.skip("Live remote launch test requires AUTOSCI_LIVE_REMOTE_LAUNCH_COMMAND.")

    experiment = os.environ.get("AUTOSCI_LIVE_REMOTE_LAUNCH_EXPERIMENT", "live-remote-launch")
    timeout = os.environ.get("AUTOSCI_LIVE_REMOTE_LAUNCH_TIMEOUT", "120")
    run_dir = Path(os.environ.get("AUTOSCI_LIVE_REMOTE_LAUNCH_RUN_DIR", "") or tmp_path / "live-remote-launch-run")
    runtime_out = tmp_path / "live-remote-launch-runtime.json"

    before = tmp_path / "live-remote-launch-before.json"
    after = tmp_path / "live-remote-launch-after.json"
    before.write_text(json.dumps({"state": "before-live-remote-launch"}), encoding="utf-8")
    after.write_text(json.dumps({"state": "after-live-remote-launch"}), encoding="utf-8")
    inner_allowlist = tmp_path / "live-remote-launch-inner-allowlist.json"
    inner_allowlist.write_text(json.dumps({"commands": [launch_command]}), encoding="utf-8")

    launch_tokens = [
        sys.executable,
        str(HARNESS.parent / "tools" / "remote.py"),
        "launch",
        "--experiment",
        experiment,
        "--approval-ref",
        "approval-live-remote-launch",
        "--allowlist-evidence",
        str(inner_allowlist),
        "--command",
        launch_command,
        "--run-dir",
        str(run_dir),
        "--runtime-evidence-out",
        str(runtime_out),
        "--timeout-seconds",
        timeout,
        "--execute-approved",
    ]
    launch_wrapper_command = shlex.join(launch_tokens)

    outer_allowlist = tmp_path / "live-remote-launch-outer-allowlist.json"
    outer_allowlist.write_text(json.dumps({"commands": [launch_wrapper_command]}), encoding="utf-8")

    evidence = load_action_evidence(
        tmp_path,
        run_shim(
            tmp_path,
            "$exp-run",
            experiment,
            "--review",
            "--env",
            "remote",
            "--approval-ref",
            "approval-live-remote-launch",
            "--allowlist-evidence",
            str(outer_allowlist),
            "--before-artifact",
            str(before),
            "--after-artifact",
            str(after),
            "--execute-approved",
            "--run-id",
            "live-remote-launch-provider",
        ),
    )
    result = evidence["outputs"]["result"]
    assert evidence["status"] == "completed"
    assert result["experiment_id"] == experiment
    assert result["execution_mode"] == "human_approved"
    assert result["outcome"] in {"supports", "partially_supports", "refutes", "inconclusive"}
    assert f"remote-runtime:{experiment}" in result["evidence_ids"]
    assert runtime_out.exists()
    runtime = json.loads(runtime_out.read_text(encoding="utf-8"))
    runtime_payload = runtime["outputs"]["runtime"]
    assert runtime["schema"] == "autosci_runtime_evidence.v1"
    assert runtime["status"] == "completed"
    assert runtime_payload["action"] == "run_experiment"
    assert runtime_payload["result_collected"] is True
    assert runtime_payload["run_dir"] == str(run_dir.resolve())


def test_autosci_live_remote_pull_results_provider_produces_final_runtime_proof(tmp_path: Path) -> None:
    require_live_flag("AUTOSCI_LIVE_REMOTE_COLLECT_TEST")
    pull_command = os.environ.get("AUTOSCI_LIVE_REMOTE_PULL_COMMAND", "").strip()
    session_id = (
        os.environ.get("AUTOSCI_LIVE_REMOTE_COLLECT_SESSION_ID")
        or os.environ.get("AUTOSCI_LIVE_REMOTE_SESSION_ID")
        or ""
    ).strip()
    if not pull_command:
        pytest.skip("Live remote collect test requires AUTOSCI_LIVE_REMOTE_PULL_COMMAND.")
    if not session_id:
        pytest.skip("Live remote collect test requires AUTOSCI_LIVE_REMOTE_COLLECT_SESSION_ID or AUTOSCI_LIVE_REMOTE_SESSION_ID.")

    experiment = os.environ.get("AUTOSCI_LIVE_REMOTE_COLLECT_EXPERIMENT", "live-remote-collect")
    transport = os.environ.get("AUTOSCI_LIVE_REMOTE_COLLECT_TRANSPORT") or os.environ.get("AUTOSCI_LIVE_REMOTE_TRANSPORT", "ssh")
    timeout = os.environ.get("AUTOSCI_LIVE_REMOTE_COLLECT_TIMEOUT", "120")
    result_dir = Path(os.environ.get("AUTOSCI_LIVE_REMOTE_RESULT_DIR", "") or tmp_path / "live-remote-results")

    before = tmp_path / "live-remote-collect-before.json"
    before.write_text(json.dumps({"state": "before-live-remote-collect"}), encoding="utf-8")
    inner_allowlist = tmp_path / "live-remote-collect-inner-allowlist.json"
    inner_allowlist.write_text(json.dumps({"commands": [pull_command]}), encoding="utf-8")

    pull_results_tokens = [
        sys.executable,
        str(HARNESS.parent / "tools" / "remote.py"),
        "pull-results",
        "--result-dir",
        str(result_dir),
        "--approval-ref",
        "approval-live-remote-collect",
        "--allowlist-evidence",
        str(inner_allowlist),
        "--pull-command",
        pull_command,
        "--transport",
        transport,
        "--session-id",
        session_id,
        "--timeout-seconds",
        timeout,
        "--execute-approved",
    ]
    pull_results_command = shlex.join(pull_results_tokens)

    outer_allowlist = tmp_path / "live-remote-collect-outer-allowlist.json"
    outer_allowlist.write_text(json.dumps({"commands": [pull_results_command]}), encoding="utf-8")

    evidence = load_action_evidence(
        tmp_path,
        run_shim(
            tmp_path,
            "$exp-run",
            experiment,
            "--collect",
            "--approval-ref",
            "approval-live-remote-collect",
            "--allowlist-evidence",
            str(outer_allowlist),
            "--before-artifact",
            str(before),
            "--execute-approved",
            "--run-id",
            "live-remote-collect-provider",
        ),
    )
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == experiment
    assert report["state"] == "completed"
    assert any("remote_collection_boundary_status=live_remote_collection" in item for item in report["observations"])
    runtime_audit = report["final_runtime_audit_boundary"]
    assert runtime_audit["final_runtime_audit_ready"] is True
    assert runtime_audit["live_remote_collection_verified"] is True
    proof_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "exp-run"
    assert proof_entry["collection_mode"] == "live_provider"
    assert proof_entry["categories"] == [
        "external_runtime_evidence",
        "approval_boundary_evidence",
        "side_effect_execution_evidence",
        "provider_source_evidence",
        "wiki_mutation_evidence",
    ]


def test_autosci_live_tex_compile_executor_produces_runtime_proof(tmp_path: Path) -> None:
    require_live_flag("AUTOSCI_LIVE_TEX_COMPILE_TEST")
    available = [name for name in ("latexmk", "pdflatex", "xelatex", "lualatex") if shutil.which(name)]
    if not available:
        pytest.skip("Live TeX compile test requires latexmk, pdflatex, xelatex, or lualatex on PATH.")

    paper_dir = tmp_path / "live-tex-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Live approved AutoSci paper compile smoke.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    before = tmp_path / "live-tex-compile-before.json"
    before.write_text(json.dumps({"paper_dir": str(paper_dir), "pdf_exists": False}), encoding="utf-8")
    allowlist = tmp_path / "live-tex-compile-allowlist.json"
    allowlist.write_text(json.dumps({"executables": available}), encoding="utf-8")

    evidence = load_action_evidence(
        tmp_path,
        run_shim(
            tmp_path,
            "$paper-compile",
            str(paper_dir),
            "--checklist",
            "--approval-ref",
            "approval-live-tex-compile",
            "--allowlist-evidence",
            str(allowlist),
            "--before-artifact",
            str(before),
            "--execute-approved",
            "--run-id",
            "live-tex-compile",
            extra_env={"AUTOSCI_LIVE_TEX_COMPILE_TEST": os.environ["AUTOSCI_LIVE_TEX_COMPILE_TEST"]},
        ),
    )
    bundle = evidence["outputs"]["bundle"]
    bundle_files = bundle["files"]
    assert evidence["status"] == "completed"
    assert any(item["type"] == "compiled_pdf" and item["path"].endswith("main.pdf") for item in bundle_files)
    assert any(item["type"] == "compile_runtime_evidence_json" for item in bundle_files)
    checklist_artifact = next(item for item in bundle_files if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    assert checklist["runtime_semantic"]["verified"] is True
    assert checklist["approval_contract"]["semantic_runtime"]["verified"] is True
    proof_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "paper-compile"
    assert proof_entry["collection_mode"] == "approved_side_effect"
    assert proof_entry["categories"] == [
        "external_runtime_evidence",
        "approval_boundary_evidence",
        "side_effect_execution_evidence",
        "provider_source_evidence",
    ]
