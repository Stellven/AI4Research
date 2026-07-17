"""RC9: skill lifecycle claims must be backed by real files and executed checks."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[2]
SOLAR_SKILLS = HARNESS / "lib" / "solar_skills.py"
TOOLS_SOLAR_SKILLS = HARNESS / "tools" / "solar_skills.py"


def _write_fixture(
    tmp_path: Path,
    *,
    status: str = "stable",
    write_entry: bool = True,
    eval_payload: dict | None = None,
    eval_text: str | None = None,
) -> Path:
    harness = tmp_path / "harness"
    fixture_lib = harness / "lib"
    registry = harness / "skills" / "registry.yaml"
    entry = harness / "skills" / "builtins" / "demo" / "SKILL.md"
    eval_pack = harness / "evals" / "skills" / (
        "demo.eval.json" if eval_payload is not None else "demo.eval.yaml"
    )
    fixture_lib.mkdir(parents=True)
    shutil.copy2(SOLAR_SKILLS, fixture_lib / "solar_skills.py")
    shutil.copy2(HARNESS / "lib" / "eval_runner.py", fixture_lib / "eval_runner.py")
    registry.parent.mkdir(parents=True)
    eval_pack.parent.mkdir(parents=True)
    if write_entry:
        entry.parent.mkdir(parents=True)
        entry.write_text("# Demo\n\nA real fixture skill.\n", encoding="utf-8")
    if eval_payload is not None:
        eval_pack.write_text(json.dumps(eval_payload), encoding="utf-8")
    else:
        eval_pack.write_text(eval_text or "cases: []\n", encoding="utf-8")
    registry.write_text(
        "\n".join(
            [
                "version: '1.0'",
                "skills:",
                "  - name: demo",
                "    namespace: builtin",
                f"    status: {status}",
                "    min_score: 0.8",
                f"    eval_pack: {eval_pack.relative_to(harness)}",
                "    entry: skills/builtins/demo/SKILL.md",
                "    promoted_at: null",
                "    promoted_by: null",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return harness


def _run(harness: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(harness / "lib" / "solar_skills.py"), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_declarative_cases_are_not_reported_as_executed_behavior(tmp_path: Path) -> None:
    harness = _write_fixture(
        tmp_path,
        eval_text="""\
skill: demo
min_score: 0.8
cases:
  - id: demo-01
    input: "say hello"
    expect:
      - says_hello: true
""",
    )

    proc = _run(harness, "eval", "--skill", "demo", "--json")
    payload = json.loads(proc.stdout)

    assert proc.returncode == 1
    assert payload["ok"] is False
    assert payload["passed"] is False
    assert payload["executed"] is False
    assert payload["reason"] == "behavioral_eval_not_executable"


def test_executable_eval_runs_its_real_command_before_passing(tmp_path: Path) -> None:
    marker = "behavior-ran.txt"
    command = (
        f"{shlex.quote(sys.executable)} -c \"from pathlib import Path; "
        f"Path('{marker}').write_text('ran', encoding='utf-8')\""
    )
    harness = _write_fixture(
        tmp_path,
        eval_payload={
            "id": "demo-behavior",
            "min_score": 1.0,
            "checks": [
                {
                    "name": "real behavior marker",
                    "cmd": command,
                    "expect_exit": 0,
                    "timeout_s": 10,
                }
            ],
        },
    )

    proc = _run(harness, "eval", "--skill", "demo", "--json")
    payload = json.loads(proc.stdout)

    assert proc.returncode == 0, proc.stderr
    assert payload["ok"] is True
    assert payload["executed"] is True
    assert payload["passed"] is True
    assert payload["checks"] == 1
    assert (harness / marker).read_text(encoding="utf-8") == "ran"


def test_registry_reports_invalid_stable_entry_instead_of_health(tmp_path: Path) -> None:
    harness = _write_fixture(tmp_path, write_entry=False)

    proc = _run(harness, "registry", "--json")
    payload = json.loads(proc.stdout)

    assert proc.returncode == 1
    assert payload["ok"] is False
    assert payload["declared_stable_count"] == 1
    assert payload["integrity_valid_stable_count"] == 0
    assert payload["stable_integrity_issues"][0]["skill"] == "demo"
    assert "entry_file_missing" in payload["stable_integrity_issues"][0]["issues"]


def test_promotion_rejects_explicit_gate_bypass(tmp_path: Path) -> None:
    harness = _write_fixture(tmp_path, status="candidate")

    proc = _run(
        harness,
        "promote",
        "--skill",
        "demo",
        "--skip-eval",
        "--skip-regression",
    )
    payload = json.loads(proc.stdout)

    assert proc.returncode == 2
    assert payload["ok"] is False
    assert payload["error"] == "unsafe_gate_bypass_rejected"
    assert "stable" not in (harness / "skills" / "registry.yaml").read_text(
        encoding="utf-8"
    ).split("status:", 1)[1].splitlines()[0]


def test_already_stable_skill_is_revalidated(tmp_path: Path) -> None:
    harness = _write_fixture(tmp_path, status="stable", write_entry=False)

    proc = _run(harness, "promote", "--skill", "demo")
    payload = json.loads(proc.stdout)

    assert proc.returncode == 1
    assert payload["ok"] is False
    assert payload["error"] == "skill_integrity_failed"
    assert "entry_file_missing" in payload["issues"]


def test_shipped_registry_does_not_call_missing_skills_stable() -> None:
    registry = (HARNESS / "skills" / "registry.yaml").read_text(encoding="utf-8")
    for name in ("brainstorm", "tdd", "debug"):
        block = registry.split(f"- name: {name}", 1)[1].split("- name:", 1)[0]
        assert "status: stable" not in block


def test_legacy_tools_entrypoint_forwards_to_canonical_skill_truth() -> None:
    canonical = subprocess.run(
        [sys.executable, str(SOLAR_SKILLS), "registry", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    legacy = subprocess.run(
        [sys.executable, str(TOOLS_SOLAR_SKILLS), "registry", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert legacy.returncode == canonical.returncode
    assert json.loads(legacy.stdout) == json.loads(canonical.stdout)
