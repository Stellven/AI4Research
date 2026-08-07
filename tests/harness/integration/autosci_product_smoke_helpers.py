from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
REPO = HARNESS.parent
SOLAR_HARNESS = HARNESS / "solar-harness.sh"


def prepare_isolated_harness(tmp_path: Path) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    for name in (
        "bin",
        "config",
        "personas",
        "tools",
        "plugins",
        "evaluators",
        "schemas",
        "lib",
        "templates",
        "workflows",
    ):
        target = HARNESS / name
        link = harness_dir / name
        if target.exists() and not link.exists():
            link.symlink_to(target, target_is_directory=target.is_dir())
    (harness_dir / "run").mkdir(exist_ok=True)
    (harness_dir / "artifacts").mkdir(exist_ok=True)
    return harness_dir


def env_for(harness_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS"] = "20"
    env.pop("AUTOSCI_ARTIFACT_ROOT", None)
    env.pop("SCIENTIFIC_ARTIFACT_ROOT", None)
    env.pop("SOLAR_AUTOSCI_OUTPUT_HARNESS", None)
    return env


def run_autosci(harness_dir: Path, command: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["bash", str(SOLAR_HARNESS), "autosci", command],
        cwd=REPO,
        env=env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check:
        assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc


def load_stdout_json(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    payload = json.loads(proc.stdout)
    assert isinstance(payload, dict)
    return payload


def unique_run_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def write_demo_paper(harness_dir: Path, name: str = "demo-paper.md") -> Path:
    paper = harness_dir / "raw" / name
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_text(
        "# Phase C AutoSci Demo Paper\n\n"
        "## Abstract\n"
        "This fixture checks product-level Solar AutoSci dispatch.\n\n"
        "## Method\n"
        "The workflow should produce typed evidence under the isolated harness root.\n\n"
        "## Results\n"
        "The test asserts artifact-root isolation rather than full provider parity.\n",
        encoding="utf-8",
    )
    return paper


def assert_under(path_text: str, root: Path) -> Path:
    path = Path(path_text).resolve()
    root = root.resolve()
    assert path == root or root in path.parents, f"{path} is outside {root}"
    return path


def repo_run_dir(run_id: str) -> Path:
    return HARNESS / "artifacts" / "autosci" / "runs" / run_id
