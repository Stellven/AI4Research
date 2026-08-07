import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = (Path(__file__).resolve().parents[3] / 'harness')
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import model_call_runtime  # noqa: E402


def test_named_tmux_target_resolves_immutable_pane_runtime_metadata(tmp_path, monkeypatch):
    """Cockpit targets must resolve the launch marker written under tmux's pane id."""
    pane_env = tmp_path / "run" / "pane-env"
    pane_env.mkdir(parents=True)
    (pane_env / "_2.json").write_text(
        json.dumps(
            {
                "pane": "%2",
                "persona": "builder",
                "pane_runtime": "claude",
                "runtime_bin": "/usr/local/bin/claude",
                "model_flag": "--model claude-opus-4-8",
                "base_url_host": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(model_call_runtime, "HARNESS_DIR", tmp_path)

    def fake_run(command, **_kwargs):
        assert command == [
            "tmux",
            "display-message",
            "-p",
            "-t",
            "solar-harness:0.2",
            "#{pane_id}",
        ]
        return SimpleNamespace(returncode=0, stdout="%2\n", stderr="")

    monkeypatch.setattr(model_call_runtime.subprocess, "run", fake_run)

    metadata = model_call_runtime.pane_runtime_metadata("solar-harness:0.2")

    assert metadata["pane"] == "%2"
    assert metadata["persona"] == "builder"
    assert metadata["pane_runtime"] == "claude"
    assert metadata["provider"] == "anthropic"
    assert metadata["model"] == "claude-opus-4-8"
    assert metadata["metadata_source"].endswith("run/pane-env/_2.json")
