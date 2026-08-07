from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
GENERATOR = HARNESS / "plugins" / "autosci" / "bin" / "project_autosci_codex_skills.py"


def test_autosci_codex_skill_projection_generates_solar_wrappers(tmp_path: Path) -> None:
    output_dir = tmp_path / ".agents" / "skills"
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--output-dir", str(output_dir)],
        cwd=HARNESS.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["ok"] is True
    assert summary["count"] == 28

    skill_files = sorted(output_dir.glob("*/SKILL.md"))
    assert len(skill_files) == 28
    ingest = (output_dir / "ingest" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: ingest" in ingest
    assert "$ingest" in ingest
    assert '"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" \'$ingest\' <user args>' in ingest
    assert "Do not run native AutoSci repo tools directly" in ingest
    assert "harness/artifacts/autosci/workspace/wiki/" in ingest
