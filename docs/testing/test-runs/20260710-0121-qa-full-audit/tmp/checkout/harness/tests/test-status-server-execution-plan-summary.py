#!/usr/bin/env python3
"""Regression test for status-server execution plan summary exposure."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_execution_plan_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory(prefix="solar-status-execution-plan-") as td:
        base = Path(td)
        harness = base / "harness"
        sprints = harness / "sprints"
        sid = "sprint-test-execution-plan"

        write(
            sprints / f"{sid}.status.json",
            json.dumps(
                {
                    "sprint_id": sid,
                    "status": "active",
                    "phase": "implementation_complete",
                    "title": "Execution Plan Summary Test",
                    "lane": "delivery",
                    "priority": "P0",
                }
            ),
        )
        write(
            sprints / f"{sid}.N2-physical-plan.json",
            json.dumps(
                {
                    "schema_version": "solar.physical_plan_node.v1",
                    "node_id": "N2",
                    "capability_capsule_id": "cap.requirement-compiler-implementation",
                    "selected_operator_id": "mini-claude-sonnet-builder",
                }
            ),
        )
        write(
            sprints / f"{sid}.N2-capsule-plan.json",
            json.dumps(
                {
                    "schema_version": "solar.capsule_plan_node.v1",
                    "node_id": "N2",
                    "capability_capsule_id": "cap.requirement-compiler-implementation",
                    "selected_skills": ["skill.nano-pdf", "skill.content-research-writer"],
                    "runtime_preferences": {"execution_surface": "prompt_guided_cli"},
                    "skill_bridge": {
                        "mode": "auto_discovered_installed_skills",
                        "template_profile": "cli_tooling",
                        "delivery_expectation": "command_log_and_artifact_delta",
                        "specialization_family": "pdf_cli_artifact",
                    },
                }
            ),
        )

        mod.HARNESS_DIR = harness
        mod.SPRINTS_DIR = sprints

        current = mod._current_sprint()
        assert current["sprint_id"] == sid
        assert current["execution_plan_artifacts"]["count"] == 1
        assert current["execution_plan_artifacts"]["items"][0]["node_id"] == "N2"
        assert current["execution_plan_artifacts"]["items"][0]["selected_operator_id"] == "mini-claude-sonnet-builder"
        assert current["execution_plan_artifacts"]["items"][0]["selected_skills"] == ["skill.nano-pdf", "skill.content-research-writer"]
        assert current["execution_plan_artifacts"]["items"][0]["execution_surface"] == "prompt_guided_cli"
        assert current["execution_plan_artifacts"]["items"][0]["skill_bridge_mode"] == "auto_discovered_installed_skills"
        assert current["execution_plan_artifacts"]["items"][0]["skill_template_profile"] == "cli_tooling"
        assert current["execution_plan_artifacts"]["items"][0]["skill_delivery_expectation"] == "command_log_and_artifact_delta"
        assert current["execution_plan_artifacts"]["items"][0]["skill_specialization_family"] == "pdf_cli_artifact"
        assert "N2->mini-claude-sonnet-builder" in current["execution_plan_summary"]
        assert "skill.nano-pdf/cli:pdf_cli_artifact +1" in current["execution_plan_summary"]

    print("PASS status-server execution plan summary")


if __name__ == "__main__":
    main()
