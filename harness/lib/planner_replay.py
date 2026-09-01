"""Replay retained planner model calls without a live provider.

Every planner model call retains ``model_output.json``, ``model_output.schema.json``
and ``model_call_receipt.json`` under a call directory whose path relative to
the planner output root identifies the call. A retained run therefore contains
everything needed to re-run the deterministic pipeline against the exact model
answers it saw, without quota.

This is not a mock: it is explicit opt-in, replays retained provider failures,
and fails closed when the retained run did not make a requested call.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intent_compiler import IntentCompilerError, write_json


REPLAY_ROOT_ENV = "SOLAR_PLANNER_REPLAY_ROOT"
REPLAY_FALLBACK_ENV = "SOLAR_PLANNER_REPLAY_FALLBACK"


def replay_fallback_live(env: dict[str, str] | None = None) -> bool:
    """Allow only replay misses to use a configured live model."""

    value = (env if env is not None else os.environ).get(REPLAY_FALLBACK_ENV)
    return str(value or "").strip().lower() == "live"


def replay_root_from_environment(env: dict[str, str] | None = None) -> Path | None:
    value = str((env if env is not None else os.environ).get(REPLAY_ROOT_ENV) or "").strip()
    if not value:
        return None
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise IntentCompilerError(f"replay root is not a directory: {root}")
    return root


@dataclass
class ReplayJsonModel:
    """JsonModel that answers from a retained planner output root."""

    replay_root: Path
    output_root: Path
    provider: str = "replay"
    model: str = "retained"
    calls: list[str] = field(default_factory=list)
    fallback: Any = None

    def _relative_call_dir(self, work_dir: Path) -> Path:
        work_dir = Path(work_dir).resolve()
        try:
            return work_dir.relative_to(Path(self.output_root).resolve())
        except ValueError as exc:
            raise IntentCompilerError(
                f"replay model call directory is outside the output root: {work_dir}"
            ) from exc

    def generate(self, prompt: str, schema_path: Path, work_dir: Path) -> dict[str, Any]:
        relative = self._relative_call_dir(work_dir)
        self.calls.append(str(relative))
        source_dir = Path(self.replay_root) / relative
        work_dir = Path(work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        retained_receipt = source_dir / "model_call_receipt.json"
        retained_output = source_dir / "model_output.json"
        retained_schema = source_dir / "model_output.schema.json"
        receipt: dict[str, Any] = {
            "schema_version": "solar.model_call_receipt.v1",
            "provider": self.provider,
            "model": self.model,
            "status": "failed",
            "exit_code": None,
            "duration_ms": 0.0,
            "provider_events": {
                "complete": False,
                "event_count": 0,
                "terminal_event_type": "",
            },
            "error": None,
            "replay_source": str(source_dir),
        }
        if not retained_receipt.is_file() and self.fallback is not None:
            self.calls[-1] = f"{relative} (live)"
            return self.fallback.generate(prompt, schema_path, work_dir)
        if not retained_receipt.is_file():
            receipt["error"] = {
                "code": "replay_miss",
                "detail": f"The retained run made no call at {relative}.",
            }
            write_json(work_dir / "model_call_receipt.json", receipt)
            raise IntentCompilerError(f"{self.provider} model call failed [replay_miss]")
        retained = json.loads(retained_receipt.read_text(encoding="utf-8"))
        if retained_schema.is_file():
            shutil.copyfile(retained_schema, work_dir / "model_output.schema.json")
        if str(retained.get("status") or "") != "succeeded" or not retained_output.is_file():
            error = retained.get("error") if isinstance(retained.get("error"), dict) else {}
            code = str(error.get("code") or "provider_error")
            receipt["error"] = {
                "code": code,
                "detail": str(error.get("detail") or ""),
            }
            write_json(work_dir / "model_call_receipt.json", receipt)
            raise IntentCompilerError(f"{self.provider} model call failed [{code}]")
        payload = json.loads(retained_output.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            receipt["error"] = {
                "code": "provider_output_invalid",
                "detail": "Retained model output was not a JSON object.",
            }
            write_json(work_dir / "model_call_receipt.json", receipt)
            raise IntentCompilerError(
                f"{self.provider} model call failed [provider_output_invalid]"
            )
        shutil.copyfile(retained_output, work_dir / "model_output.json")
        receipt["status"] = "succeeded"
        receipt["exit_code"] = 0
        write_json(work_dir / "model_call_receipt.json", receipt)
        return payload
