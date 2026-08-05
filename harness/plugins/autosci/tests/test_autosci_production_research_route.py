from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[3]
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"


def test_research_opt_in_preserves_complete_prompt_run_id_and_uses_solar_route(tmp_path: Path) -> None:
    prompt_parts = [
        "请深入分析",
        "https://example.test/research",
        "并用中文输出完整技术报告",
    ]
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(SHIM),
            "$research",
            *prompt_parts,
            "--solar-orchestrator",
            "--run-id",
            "shim-route-001",
        ],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["run_id"] == "shim-route-001"
    assert payload["prompt"] == " ".join(prompt_parts)
    assert payload["route"]["start_stage"] == "web_fetch"
    assert payload["start_node"] == "seed_fetch"
    assert payload["route"]["workflow_kind"] != "workflow_evolution"
    assert "real_data_research" not in proc.stdout
