import os
import subprocess
import sys
from pathlib import Path


def test_multi_task_runner_noninteractive_help_survives_missing_en_us_locale():
    harness_dir = (Path(__file__).resolve().parents[3] / 'harness')
    runner = harness_dir / "lib" / "multi_task_runner.py"
    env = dict(os.environ)
    env.update(
        {
            "LC_ALL": "en_US.UTF-8",
            "LANG": "en_US.UTF-8",
            "PYTHONFAULTHANDLER": "1",
        }
    )

    proc = subprocess.run(
        [sys.executable, str(runner), "--help"],
        text=True,
        capture_output=True,
        env=env,
        timeout=20,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Segmentation fault" not in proc.stderr
    assert "solar-harness multi-task" in proc.stdout
