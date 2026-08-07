from __future__ import annotations

import datetime
import importlib.util
import json
import time
from pathlib import Path


HARNESS_ROOT = (Path(__file__).resolve().parents[2] / 'harness')
STATUS_SERVER = HARNESS_ROOT / "lib" / "symphony" / "status-server.py"


def _load_status_server(tmp_path: Path):
    harness = tmp_path / "harness"
    config = harness / "config"
    quota = harness / "state" / "quota-footer"
    config.mkdir(parents=True)
    quota.mkdir(parents=True)

    spec = importlib.util.spec_from_file_location(
        f"status_server_usage_{time.time_ns()}", STATUS_SERVER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HARNESS_DIR = harness
    module._USER_CONFIG_PATH = config / "solar-user-config.json"
    return module, config, quota


def test_codex_runtime_does_not_project_claude_quota_rows(tmp_path: Path) -> None:
    module, config, quota = _load_status_server(tmp_path)
    today = datetime.datetime.now().astimezone().date().isoformat()
    (config / "solar-user-config.json").write_text(
        json.dumps({"runtime": "codex"}), encoding="utf-8"
    )
    (quota / "claude-opus.json").write_text(
        json.dumps(
            {
                "date": today,
                "model_key": "claude-opus",
                "used_tokens": 0,
            }
        ),
        encoding="utf-8",
    )

    def forbidden_refresh():
        raise AssertionError("Codex mode must not scan Claude logs")

    module._refresh_quota_footer_cache = forbidden_refresh
    payload = module._usage_payload(refresh=True)

    assert payload["runtime"] == "codex"
    assert payload["availability"] == "unavailable"
    assert payload["reason"] == "codex_account_usage_not_exposed"
    assert payload["total_used_tokens"] is None
    assert payload["total_used_tokens_label"] == "unavailable"
    assert payload["models"] == []
    assert "Claude" not in payload["source"]


def test_claude_runtime_retains_real_quota_footer_rows(tmp_path: Path) -> None:
    module, config, quota = _load_status_server(tmp_path)
    today = datetime.datetime.now().astimezone().date().isoformat()
    (config / "solar-user-config.json").write_text(
        json.dumps({"runtime": "claude"}), encoding="utf-8"
    )
    (quota / "claude-sonnet.json").write_text(
        json.dumps(
            {
                "date": today,
                "model_key": "claude-sonnet",
                "used_tokens": 44100000,
            }
        ),
        encoding="utf-8",
    )

    payload = module._usage_payload(refresh=False)

    assert payload["runtime"] == "claude"
    assert payload["availability"] == "available"
    assert payload["source"] == "Claude log scan / quota-footer"
    assert payload["models"][0]["model_key"] == "claude-sonnet"
    assert payload["models"][0]["used_tokens_label"] == "44.1M"
