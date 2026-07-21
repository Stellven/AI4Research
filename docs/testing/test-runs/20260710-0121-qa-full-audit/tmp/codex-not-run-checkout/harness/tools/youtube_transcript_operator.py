#!/usr/bin/env python3
"""Command backend adapter for YouTube Transcript Extractor browser-agent logical operator tasks.

Follows the same pattern as gemini_deep_research_operator.py:
  main() → _load_envelope() → build_request() → _rate_control_settings() → run_request() → flow_control
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

import operator_flow_control as ofc  # noqa: E402

DEFAULT_OPERATOR_ID = "mini-youtube-transcript-extractor"
DEFAULT_WRAPPER = ROOT / "scripts" / "browser_agent_youtube_transcript_wrapper.py"
DEFAULT_BROWSER_USE_PYTHON = Path.home() / ".claude" / "mcp-servers" / "browser-use" / ".venv" / "bin" / "python"


def _load_envelope() -> dict[str, Any]:
    path = str(os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
    if not path:
        raise RuntimeError("SOLAR_OPERATOR_ENVELOPE_JSON missing")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("operator envelope must be a JSON object")
    return payload


def _task_dir() -> Path:
    raw = str(os.environ.get("TASK_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path.cwd()


def _wrapper_cmd() -> list[str]:
    raw = (
        os.environ.get("BROWSER_AGENT_YT_TRANSCRIPT_CMD")
        or ""
    ).strip()
    if raw:
        return shlex.split(raw)
    if DEFAULT_WRAPPER.exists() and DEFAULT_BROWSER_USE_PYTHON.exists():
        return [str(DEFAULT_BROWSER_USE_PYTHON), str(DEFAULT_WRAPPER)]
    if DEFAULT_WRAPPER.exists():
        return [sys.executable, str(DEFAULT_WRAPPER)]
    return []


def _operator_id(envelope: dict[str, Any]) -> str:
    return str(envelope.get("operator_id") or "").strip() or DEFAULT_OPERATOR_ID


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return ""


def build_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    """Build a transcript extraction request from the operator envelope.

    Envelope may contain:
      - youtube_url: the video URL
      - url: alias for youtube_url
      - timeout_seconds: overall timeout (default: 300s)
      - max_retries: retry count (default: 3)
      - output_format: "timestamped" (default) | "plain"
    """
    raw = envelope.get("youtube_transcript_request")
    if isinstance(raw, dict):
        request = deepcopy(raw)
    else:
        request = {}
        for key in (
            "youtube_url",
            "url",
            "timeout_seconds",
            "max_retries",
            "output_format",
        ):
            if key in envelope:
                request[key] = deepcopy(envelope[key])

    # Normalize URL field
    youtube_url = str(request.get("youtube_url") or request.get("url") or "").strip()
    if not youtube_url:
        # Try top-level prompt as URL
        youtube_url = str(envelope.get("prompt") or "").strip()
    request["youtube_url"] = youtube_url
    request["video_id"] = _extract_video_id(youtube_url)

    if task_dir is not None:
        request.setdefault("request_dir", str((task_dir / "youtube-transcript-request").resolve()))
    request.setdefault("timeout_seconds", 300)
    request.setdefault("max_retries", 3)
    request.setdefault("output_format", "timestamped")
    return request


def _rate_control_settings(envelope: dict[str, Any]) -> dict[str, Any]:
    operator_id = _operator_id(envelope)
    flow_control: dict[str, Any] = {}
    try:
        import operator_runtime  # type: ignore
        config = operator_runtime.get_operator_config(operator_id) or {}
        if isinstance(config.get("flow_control"), dict):
            flow_control = dict(config["flow_control"])
    except Exception:
        flow_control = {}
    return {
        "operator_id": operator_id,
        "success_cooldown_seconds": ofc.int_value(
            envelope.get("yt_success_cooldown_seconds")
            or os.environ.get("SOLAR_YT_SUCCESS_COOLDOWN_SECONDS")
            or flow_control.get("success_cooldown_seconds"),
            60,
        ),
        "rate_limit_cooldown_seconds": ofc.int_value(
            envelope.get("yt_rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_YT_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            600,
        ),
        "auth_cooldown_seconds": ofc.int_value(
            envelope.get("yt_auth_cooldown_seconds")
            or os.environ.get("SOLAR_YT_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            3600,
        ),
        "defer_on_cooldown": ofc.bool_value(
            envelope.get("yt_defer_on_cooldown")
            or os.environ.get("SOLAR_YT_DEFER_ON_COOLDOWN")
            or flow_control.get("defer_on_cooldown"),
            True,
        ),
        "defer_on_auth": ofc.bool_value(
            envelope.get("yt_defer_on_auth")
            or os.environ.get("SOLAR_YT_DEFER_ON_AUTH")
            or flow_control.get("defer_on_auth"),
            True,
        ),
    }


def _summary_markdown(response: dict[str, Any]) -> str:
    return "\n".join([
        "# YouTube Transcript Extraction Result",
        "",
        "## 已完成",
        f"- video_id: {response.get('video_id') or 'N/A'}",
        f"- video_title: {response.get('video_title') or 'N/A'}",
        f"- channel: {response.get('channel') or 'N/A'}",
        f"- segment_count: {response.get('segment_count') or 0}",
        f"- text_length: {response.get('text_length') or 0}",
        "",
        "## 说明",
        "- 详细的 YouTube 转写文稿已写入结果工件目录。",
    ])


def run_request(request: dict[str, Any], *, task_dir: Path) -> dict[str, Any]:
    youtube_url = str(request.get("youtube_url") or "").strip()
    if not youtube_url:
        raise RuntimeError("YouTube Transcript operator requires youtube_url")
    cmd = _wrapper_cmd()
    if not cmd:
        raise RuntimeError("YouTube Transcript browser-agent wrapper command is not configured")
    task_dir.mkdir(parents=True, exist_ok=True)
    request_dir = Path(str(request.get("request_dir") or (task_dir / "youtube-transcript-request"))).expanduser()
    request_dir.mkdir(parents=True, exist_ok=True)

    (task_dir / "youtube-transcript-request.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    if "BROWSER_AGENT_HEADLESS" not in env:
        env["BROWSER_AGENT_HEADLESS"] = "false"
    env.setdefault("BROWSER_AGENT_PROFILE_DIRECTORY", "Default")
    env.setdefault("BROWSER_AGENT_TARGET_ACCOUNT_EMAIL", "browser-agent@example.com")
    env.update({
        "BROWSER_AGENT_REQUEST_DIR": str(request_dir),
        "BROWSER_AGENT_YT_TIMEOUT": str(request.get("timeout_seconds") or 300),
    })

    timeout = ofc.int_value(request.get("timeout_seconds"), 300)
    max_retries = ofc.int_value(request.get("max_retries"), 3)

    last_exc = None
    for attempt in range(1, max_retries + 1):
        print(f"[YT Transcript Operator] Starting execution attempt {attempt} of {max_retries}...", flush=True)
        try:
            proc = subprocess.run(
                cmd,
                input=youtube_url,
                text=True,
                capture_output=True,
                env=env,
                timeout=timeout,
            )
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            (task_dir / f"youtube-transcript-output-attempt{attempt}.txt").write_text(
                combined + ("\n" if combined else ""),
                encoding="utf-8",
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Wrapper exited with code {proc.returncode}. Log snippet:\n{combined[-1000:]}")

            # Read output artifacts generated by wrapper
            assistant_response_path = request_dir / "assistant-response.txt"
            page_json_path = request_dir / "page.json"
            transcript_json_path = request_dir / "transcript.json"

            if not assistant_response_path.exists():
                raise FileNotFoundError(f"assistant-response.txt was not generated in {request_dir}")

            text = assistant_response_path.read_text(encoding="utf-8").strip()
            if not text:
                raise RuntimeError("assistant-response.txt was generated but is empty")

            page_data = {}
            if page_json_path.exists():
                try:
                    page_data = json.loads(page_json_path.read_text(encoding="utf-8"))
                except Exception as parse_err:
                    print(f"Warning: Failed to parse page.json: {parse_err}", flush=True)

            transcript_detail = {}
            if transcript_json_path.exists():
                try:
                    transcript_detail = json.loads(transcript_json_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            result = {
                "ok": True,
                "video_id": page_data.get("video_id", request.get("video_id", "")),
                "video_title": page_data.get("title", ""),
                "channel": page_data.get("channel", ""),
                "youtube_url": youtube_url,
                "request_dir": str(request_dir),
                "text": text,
                "segment_count": page_data.get("segment_count", 0),
                "text_length": len(text),
                "output_format": request.get("output_format", "timestamped"),
            }

            # Save final results
            (task_dir / "youtube-transcript-result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            # Write transcript file for easy readability
            (task_dir / "transcript.txt").write_text(text + "\n", encoding="utf-8")

            print(_summary_markdown(result))
            return result
        except Exception as exc:
            last_exc = exc
            print(f"[YT Transcript Operator] Attempt {attempt} failed: {exc}", file=sys.stderr, flush=True)
            if attempt < max_retries:
                time.sleep(5)

    raise RuntimeError(f"YouTube Transcript operator failed after {max_retries} attempts: {last_exc}")


def main() -> int:
    try:
        envelope = _load_envelope()
    except Exception as exc:
        print(f"Failed to load envelope: {exc}", file=sys.stderr)
        return 1

    task_dir = _task_dir()
    ofc.clear_task_control(task_dir)
    request = build_request(envelope, task_dir=task_dir)
    rate_control = _rate_control_settings(envelope)
    operator_id = str(rate_control["operator_id"])
    try:
        ofc.ensure_operator_available(operator_id)
        run_request(request, task_dir=task_dir)
        ofc.apply_success_cooldown(
            operator_id,
            success_cooldown_seconds=int(rate_control.get("success_cooldown_seconds") or 0),
        )
        return 0
    except Exception as exc:
        ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=str(exc),
            rate_limit_cooldown_seconds=int(rate_control.get("rate_limit_cooldown_seconds") or 0),
            auth_cooldown_seconds=int(rate_control.get("auth_cooldown_seconds") or 0),
            defer_on_cooldown=bool(rate_control.get("defer_on_cooldown")),
            defer_on_auth=bool(rate_control.get("defer_on_auth")),
        )
        print(f"youtube_transcript_operator failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
