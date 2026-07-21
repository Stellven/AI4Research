"""Browser Agent wrapper contract for ChatGPT 5.5 Thinking high.

This module defines the seam and fake-provider behavior for tests. It does not
call ChatGPT directly; production integration is injected through provider.
"""

from __future__ import annotations

import time
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from .ledger import append_model_call_ledger


class BrowserAgentProvider(Protocol):
    def call(self, stage: str, payload: dict[str, Any], *, requested_model: str) -> dict[str, Any]: ...


class LocalModelSubstitutionError(RuntimeError):
    pass


class YoutubeTranscriptExtractor:
    """Production adapter for the YouTube transcript browser-agent operator.

    The report BrowserAgentClient below is for ChatGPT report planning/writing.
    Transcript capture is a separate logical operator; this adapter exposes it
    from the AI Influence YouTube module while reusing the existing operator
    implementation instead of duplicating browser automation.
    """

    def __init__(
        self,
        *,
        operator_script: str | Path | None = None,
        python_executable: str | Path | None = None,
        target_account_email: str | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        self.operator_script = Path(operator_script or root / "tools" / "youtube_transcript_operator.py")
        self.python_executable = str(python_executable or sys.executable)
        self.target_account_email = target_account_email

    def extract(
        self,
        youtube_url: str,
        *,
        task_dir: str | Path,
        timeout_seconds: int = 300,
        max_retries: int = 1,
        output_format: str = "timestamped",
        headless: bool = True,
    ) -> dict[str, Any]:
        url = str(youtube_url or "").strip()
        if not url:
            raise RuntimeError("YoutubeTranscriptExtractor requires youtube_url")
        if not self.operator_script.exists():
            raise RuntimeError(f"YouTube transcript operator not found: {self.operator_script}")

        run_dir = Path(task_dir).expanduser()
        run_dir.mkdir(parents=True, exist_ok=True)
        envelope_path = run_dir / "envelope.json"
        envelope_path.write_text(
            json.dumps(
                {
                    "operator_id": "mini-youtube-transcript-extractor",
                    "youtube_url": url,
                    "timeout_seconds": max(int(timeout_seconds), 300),
                    "max_retries": int(max_retries),
                    "output_format": output_format,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["SOLAR_OPERATOR_ENVELOPE_JSON"] = str(envelope_path)
        env["TASK_DIR"] = str(run_dir)
        env.setdefault("BROWSER_AGENT_HEADLESS", "true" if headless else "false")
        if self.target_account_email:
            env["BROWSER_AGENT_TARGET_ACCOUNT_EMAIL"] = self.target_account_email

        proc = subprocess.run(
            [self.python_executable, str(self.operator_script)],
            env=env,
            text=True,
            capture_output=True,
            timeout=max(int(timeout_seconds), 300) + 60,
        )
        (run_dir / "operator.stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
        (run_dir / "operator.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
        result_path = run_dir / "youtube-transcript-result.json"
        if proc.returncode != 0 or not result_path.exists():
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            raise RuntimeError(f"browser transcript operator failed rc={proc.returncode}: {combined[-1200:]}")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("youtube-transcript-result.json must contain a JSON object")
        return payload


class BrowserAgentClient:
    def __init__(self, provider: BrowserAgentProvider, *, ledger_path: str | Path, sprint_id: str) -> None:
        self.provider = provider
        self.ledger_path = Path(ledger_path)
        self.sprint_id = sprint_id
        self._chapter_calls: set[str] = set()

    def _call(self, stage: str, payload: dict[str, Any], *, requested_model: str, run_id: str, chapter_id: str = "") -> dict[str, Any]:
        if requested_model.lower() in {"qwen", "qwen3.6", "thunderomlx", "local"}:
            raise LocalModelSubstitutionError("local model substitution is forbidden for judgment-bearing phases")
        started = time.time()
        result = self.provider.call(stage, payload, requested_model=requested_model)
        latency_ms = int((time.time() - started) * 1000)
        call_id = str(result.get("model_call_id") or f"call_{uuid4().hex}")
        append_model_call_ledger(self.ledger_path, {
            "schema_version": "model_call_ledger.v1",
            "call_id": call_id,
            "stage": stage,
            "cost_estimate_usd": float(result.get("cost_estimate_usd", 0.0)),
            "sprint_id": self.sprint_id,
            "browser_session_id": str(result.get("browser_session_id", "fake-session")),
            "chatgpt_url": str(result.get("chatgpt_url", "about:blank")),
            "latency_ms": latency_ms,
            "run_id": run_id,
            "chapter_id": chapter_id,
            "requested_model": requested_model,
            "resolved_model": str(result.get("resolved_model", requested_model)),
            "status": str(result.get("status", "succeeded")),
        })
        result["model_call_id"] = call_id
        return result

    def plan(self, corpus: dict[str, Any], *, requested_model: str, run_id: str) -> dict[str, Any]:
        return self._call("phase1", corpus, requested_model=requested_model, run_id=run_id)

    def write_chapter(self, chapter_spec: dict[str, Any], *, requested_model: str, run_id: str, chapter_id: str) -> dict[str, Any]:
        if chapter_id in self._chapter_calls:
            raise ValueError(f"duplicate phase2 chapter call: {chapter_id}")
        self._chapter_calls.add(chapter_id)
        return self._call("phase2", chapter_spec, requested_model=requested_model, run_id=run_id, chapter_id=chapter_id)

    def synthesize(self, chapter_outputs: list[dict[str, Any]], *, requested_model: str, run_id: str) -> dict[str, Any]:
        return self._call("phase3", {"chapters": chapter_outputs}, requested_model=requested_model, run_id=run_id)
