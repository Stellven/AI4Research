from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
PYTHON = CHECKOUT / ".venv/bin/python"


def safe_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "SOLAR_HOME": str(home / ".solar"),
            "HARNESS_DIR": str(CHECKOUT / "harness"),
            "HARNESS_STATE_DB": str(tmp_path / "state.db"),
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
        }
    )
    for key in list(env):
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            env.pop(key, None)
    return env


@pytest.mark.parametrize(
    "script",
    [
        "harness/tests/test-capability-prefix-visibility.sh",
        "harness/tests/integrations/test-capability-plane-e2e.sh",
        "harness/tests/integrations/test-expanded-capability-plane-e2e.sh",
        "harness/tests/integrations/test-capability-fusion-benchmark.sh",
    ],
)
def test_capability_plane_tracked_contract(script: str, tmp_path: Path) -> None:
    proc = subprocess.run(
        ["bash", str(CHECKOUT / script)],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_capability_activation_proof_help_is_read_only(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = safe_env(tmp_path)
    env.pop("HARNESS_DIR", None)
    proc = subprocess.run(
        [str(PYTHON), str(CHECKOUT / "harness/tools/capability_activation_proof.py"), "--help"],
        cwd=CHECKOUT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "usage:" in proc.stdout.lower()
    assert not (home / ".solar").exists(), "--help created runtime/report state in HOME"


@pytest.mark.parametrize(
    "tool,expected",
    [
        ("capability_certification_suite.py", "--mode"),
        ("capability_effects.py", "dispatch_file"),
        ("capability_fusion_benchmark.py", "--threshold"),
        ("capability_inference.py", "enrich-graph"),
        ("capability_registry.py", "scorecard"),
    ],
)
def test_capability_cli_help_is_deterministic_and_read_only(tool: str, expected: str, tmp_path: Path) -> None:
    home = tmp_path / "home"
    proc = subprocess.run(
        [str(PYTHON), str(CHECKOUT / "harness/tools" / tool), "--help"],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert expected in proc.stdout
    assert not (home / ".solar").exists()


def test_capability_registry_sync_list_query_scorecard_and_idempotence(tmp_path: Path) -> None:
    tool = CHECKOUT / "harness/tools/capability_registry.py"
    env = safe_env(tmp_path)

    def invoke(*args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = subprocess.run(
            [str(PYTHON), str(tool), *args], cwd=CHECKOUT, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
        )
        return proc, json.loads(proc.stdout)

    first, first_payload = invoke("sync", "--json")
    assert first.returncode == 0 and first_payload["ok"] is True
    assert first_payload["synced_capabilities"] > 0 and first_payload["errors"] == []

    listed, listed_payload = invoke("list", "--json")
    assert listed.returncode == 0 and listed_payload["total"] == first_payload["synced_capabilities"]
    assert listed_payload["capabilities"]

    query, query_payload = invoke("query", "multi_agent.research", "--json")
    assert query.returncode == 0 and query_payload["found"] is True
    missing, missing_payload = invoke("query", "__qa_missing_capability__", "--json")
    assert missing.returncode != 0 and missing_payload["found"] is False

    score, score_payload = invoke("scorecard", "--json")
    assert score.returncode == 0 and score_payload["total_capabilities"] == listed_payload["total"]
    assert 0 <= score_payload["weighted_score"] <= score_payload["max_score"]

    second, second_payload = invoke("sync", "--json")
    assert second.returncode == 0 and second_payload["synced_capabilities"] == first_payload["synced_capabilities"]
    listed_again, listed_again_payload = invoke("list", "--json")
    assert listed_again.returncode == 0 and listed_again_payload["total"] == listed_payload["total"]


def test_capability_effects_scan_is_typed_and_idempotent(tmp_path: Path) -> None:
    dispatch = tmp_path / "dispatch.md"
    dispatch.write_text("# Dispatch\n", encoding="utf-8")
    sidecar = dispatch.with_name(dispatch.name + ".intent.json")
    sidecar.write_text(
        json.dumps(
            {
                "capabilities": [
                    {"provider": "qa-provider", "capabilities": ["document.convert"]}
                ]
            }
        ),
        encoding="utf-8",
    )
    handoff = tmp_path / "handoff.md"
    handoff.write_text("Used qa-provider for document.convert.\n", encoding="utf-8")
    tool = CHECKOUT / "harness/tools/capability_effects.py"

    command = [
        str(PYTHON), str(tool), str(dispatch), "--handoff", str(handoff),
        "--verdict", "pass", "--no-db", "--json",
    ]
    first = subprocess.run(
        command, cwd=CHECKOUT, env=safe_env(tmp_path), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    first_payload = json.loads(first.stdout)
    assert first_payload["effect"]["status"] == "eval_passed_with_worker_evidence"
    assert first_payload["effect"]["used_providers"] == ["qa-provider"]
    first_sidecar = sidecar.read_bytes()

    second = subprocess.run(
        command, cwd=CHECKOUT, env=safe_env(tmp_path), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert second.returncode == 0
    assert sidecar.read_bytes() == first_sidecar

    missing = subprocess.run(
        [str(PYTHON), str(tool), str(tmp_path / "missing.md"), "--no-db", "--json"],
        cwd=CHECKOUT, env=safe_env(tmp_path), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert missing.returncode != 0
    assert json.loads(missing.stdout)["reason"] == "intent_sidecar_missing_or_invalid"


def test_capability_certification_fast_suite_has_no_blocking_errors(tmp_path: Path) -> None:
    tool = CHECKOUT / "harness/tools/capability_certification_suite.py"
    report_json = tmp_path / "certification.json"
    report_md = tmp_path / "certification.md"
    evidence = tmp_path / "evidence"
    proc = subprocess.run(
        [
            str(PYTHON), str(tool), "--mode", "fast", "--json",
            "--out-json", str(report_json), "--out-md", str(report_md),
            "--evidence-dir", str(evidence),
        ],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )
    payload = json.loads(proc.stdout)
    assert report_json.is_file() and report_md.is_file() and evidence.is_dir()
    assert payload["mode"] == "fast" and payload["summary"]["total"] > 0
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["ok"] is True and payload["summary"]["blocking_ids"] == []
