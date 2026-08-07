from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
PYTHON = CHECKOUT / ".venv/bin/python"
BRIDGE = CHECKOUT / "harness/plugins/autosci/bin/autosci_bridge.py"
SHIM = CHECKOUT / "harness/plugins/autosci/bin/autosci_skill_shim.py"
PROJECT = CHECKOUT / "harness/plugins/autosci/bin/project_autosci_codex_skills.py"
ROUTES = CHECKOUT / "harness/plugins/autosci/config/feature_parity_routes.v1.json"
BINDINGS = CHECKOUT / "harness/plugins/autosci/config/feature_operator_bindings.v1.json"


def safe_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "SOLAR_HOME": str(home / ".solar"),
            "HARNESS_DIR": str(tmp_path),
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
        }
    )
    return env


def run(command: list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=CHECKOUT / "harness",
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )


def test_route_and_binding_configs_are_complete_and_cross_referenced() -> None:
    routes = json.loads(ROUTES.read_text(encoding="utf-8"))["routes"]
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))["bindings"]
    route_by_skill = {row["native_skill"]: row for row in routes}
    binding_by_skill = {row["native_skill"]: row for row in bindings}
    assert len(route_by_skill) == len(routes) == 28
    assert len(binding_by_skill) == len(bindings) == 28
    assert set(route_by_skill) == set(binding_by_skill)
    for skill, route in route_by_skill.items():
        assert route["autosci_command"]
        assert route["solar_backend_action"]
        assert route["evidence_schema"]
        assert binding_by_skill[skill]["physical_operator"]


def test_skill_shim_lists_routes_and_missing_route_is_typed(tmp_path: Path) -> None:
    listed = run(
        [str(PYTHON), str(SHIM), "skills", "list", "--route-config", str(ROUTES), "--binding-config", str(BINDINGS)],
        tmp_path,
    )
    assert listed.returncode == 0, listed.stdout + listed.stderr
    payload = json.loads(listed.stdout)
    assert payload["ok"] is True and payload["count"] == 28
    assert {row["skill"] for row in payload["skills"]} >= {"research", "check", "poster", "reset"}

    missing = run(
        [
            str(PYTHON), str(SHIM), "skill", "qa-missing-route", "--route-config", str(ROUTES),
            "--binding-config", str(BINDINGS), "--run-id", "qa-missing-route",
        ],
        tmp_path,
    )
    assert missing.returncode != 0
    missing_payload = json.loads(missing.stdout)
    assert missing_payload["status"] == "failed"
    evidence = json.loads(Path(missing_payload["evidence_path"]).read_text(encoding="utf-8"))
    assert "No Solar AutoSci route is configured" in " ".join(evidence["limitations"])


def test_bridge_smoke_and_validate_return_typed_status(tmp_path: Path) -> None:
    smoke = run([str(PYTHON), str(BRIDGE), "smoke"], tmp_path)
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    payload = json.loads(smoke.stdout)
    assert payload["ok"] is True
    assert payload["schema"]
    result_path = Path(payload["result_path"])
    if not result_path.is_absolute():
        result_path = tmp_path / result_path
    assert result_path.is_file()

    validated = run([str(PYTHON), str(BRIDGE), "validate", "--result", str(result_path)], tmp_path)
    assert validated.returncode == 0, validated.stdout + validated.stderr
    result = json.loads(validated.stdout)
    assert result["ok"] is True


def test_codex_skill_projection_is_scoped_and_repeatable(tmp_path: Path) -> None:
    output = tmp_path / "codex-skills"
    command = [
        str(PYTHON), str(PROJECT), "--route-config", str(ROUTES), "--output-dir", str(output),
    ]
    first = run(command, tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    before = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    assert before and all(path.name == "SKILL.md" for path in before)
    second = run(command, tmp_path)
    assert second.returncode == 0, second.stdout + second.stderr
    after = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    assert after == before
