"""Artifact-only automation for survey pane response watching."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .writing_loop import watch_pane_responses

SCHEMA_VERSION = "solar.research.survey.watch.v1"
DEFAULT_CONFIG_PATH = Path.home() / ".solar" / "harness" / "run" / "research-survey-watch.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_config_path() -> Path:
    return DEFAULT_CONFIG_PATH


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": SCHEMA_VERSION, "enabled": False, "runs": [], "error": "config_json_invalid"}
    return data if isinstance(data, dict) else {}


def load_watch_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path).expanduser() if str(config_path or "") else default_config_path()
    data = _read_json(path)
    if not data:
        return {"schema_version": SCHEMA_VERSION, "enabled": True, "runs": [], "config_path": str(path)}
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("enabled", True)
    data.setdefault("runs", [])
    data["config_path"] = str(path)
    return data


def register_watch_run(
    output_dir: str | Path,
    *,
    config_path: str | Path | None = None,
    enabled: bool = True,
    min_chars: int = 1200,
    round_index: int = 0,
    limit: int = 0,
    append: bool = True,
) -> dict[str, Any]:
    path = Path(config_path).expanduser() if str(config_path or "") else default_config_path()
    output = str(Path(output_dir).expanduser())
    config = load_watch_config(path) if append else {"schema_version": SCHEMA_VERSION, "enabled": True, "runs": []}
    runs = [item for item in config.get("runs", []) if isinstance(item, dict) and str(item.get("output_dir") or "") != output]
    run = {
        "output_dir": output,
        "enabled": bool(enabled),
        "min_chars": int(min_chars),
        "round_index": int(round_index),
        "limit": int(limit),
        "registered_at": utc_now(),
    }
    runs.append(run)
    config.update({
        "schema_version": SCHEMA_VERSION,
        "enabled": bool(config.get("enabled", True)),
        "runs": runs,
        "updated_at": utc_now(),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "config_path": str(path), "registered": run, "run_count": len(runs)}


def tick_watch_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path).expanduser() if str(config_path or "") else default_config_path()
    config = load_watch_config(path)
    state_path = path.with_suffix(".state.json")
    if config.get("enabled") is False:
        payload = {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "config_path": str(path),
            "state_path": str(state_path),
            "disabled": True,
            "run_count": 0,
            "processed_total": 0,
            "passed_total": 0,
            "failed_total": 0,
            "pending_total": 0,
            "runs": [],
            "checked_at": utc_now(),
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload

    results: list[dict[str, Any]] = []
    for item in config.get("runs", []):
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        output_dir = item.get("output_dir")
        if not output_dir:
            results.append({"ok": False, "reason": "output_dir_missing", "config_item": item})
            continue
        try:
            result = watch_pane_responses(
                output_dir,
                limit=int(item.get("limit") or 0),
                min_chars=int(item.get("min_chars") or 1200),
                round_index=int(item.get("round_index") or 0),
            )
            result["output_dir"] = str(Path(output_dir).expanduser())
            results.append(result)
        except Exception as exc:  # pragma: no cover - defensive status surface
            results.append({"ok": False, "output_dir": str(output_dir), "reason": type(exc).__name__, "error": str(exc)})

    processed = sum(int(item.get("processed") or 0) for item in results)
    failed = sum(int(item.get("failed") or 0) for item in results)
    payload = {
        "ok": failed == 0,
        "schema_version": SCHEMA_VERSION,
        "config_path": str(path),
        "state_path": str(state_path),
        "disabled": False,
        "run_count": len(results),
        "processed_total": processed,
        "passed_total": sum(int(item.get("passed") or 0) for item in results),
        "failed_total": failed,
        "pending_total": sum(int(item.get("pending_responses") or 0) for item in results),
        "runs": results,
        "checked_at": utc_now(),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
