#!/usr/bin/env python3
"""Command backend adapter for NotebookLM logical operator tasks."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import operator_flow_control as ofc


HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
DEFAULT_WRAPPER = HARNESS_DIR / "scripts" / "browser_agent_notebooklm_wrapper.py"
DEFAULT_BROWSER_USE_PYTHON = HOME / ".claude" / "mcp-servers" / "browser-use" / ".venv" / "bin" / "python"
DEFAULT_OPERATOR_ID = "mini-browser-notebooklm"
JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.S | re.I)


class NotebookLMOperatorError(RuntimeError):
    """Raised when the NotebookLM wrapper fails after emitting useful diagnostics."""

    def __init__(self, message: str, *, combined_output: str = "") -> None:
        super().__init__(message)
        self.combined_output = combined_output


def notebooklm_wrapper_cmd() -> list[str]:
    raw = (
        os.environ.get("TECH_HOTSPOT_BROWSER_NOTEBOOKLM_CMD")
        or os.environ.get("BROWSER_AGENT_NOTEBOOKLM_CMD")
        or ""
    ).strip()
    if raw:
        return shlex.split(raw)
    if DEFAULT_WRAPPER.exists() and DEFAULT_BROWSER_USE_PYTHON.exists():
        return [str(DEFAULT_BROWSER_USE_PYTHON), str(DEFAULT_WRAPPER)]
    return []


def _operator_runtime_module():
    lib_dir = HARNESS_DIR / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import operator_runtime  # type: ignore

    return operator_runtime


def _load_envelope() -> dict[str, Any]:
    path = str(os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
    if not path:
        raise RuntimeError("SOLAR_OPERATOR_ENVELOPE_JSON missing")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("operator envelope must be a JSON object")
    return payload


def _extract_json_payload_lenient(text: str) -> dict[str, Any]:
    fenced = JSON_FENCE_RE.search(text or "")
    if fenced:
        payload = json.loads(fenced.group(1))
        if isinstance(payload, dict):
            return payload
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    match = re.search(r"\{.*\}", text or "", re.S)
    if match:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("NotebookLM wrapper did not return a JSON object")


def _int_value(value: Any, default: int) -> int:
    return ofc.int_value(value, default)


def _bool_value(value: Any, default: bool = False) -> bool:
    return ofc.bool_value(value, default)


def _operator_id(envelope: dict[str, Any]) -> str:
    value = str(envelope.get("operator_id") or "").strip()
    return value or DEFAULT_OPERATOR_ID


def _rate_control_settings(envelope: dict[str, Any]) -> dict[str, Any]:
    operator_id = _operator_id(envelope)
    flow_control: dict[str, Any] = {}
    try:
        config = _operator_runtime_module().get_operator_config(operator_id) or {}
        if isinstance(config.get("flow_control"), dict):
            flow_control = dict(config["flow_control"])
    except Exception:
        flow_control = {}
    return {
        "operator_id": operator_id,
        "success_cooldown_seconds": _int_value(
            envelope.get("notebooklm_success_cooldown_seconds")
            or os.environ.get("SOLAR_NOTEBOOKLM_SUCCESS_COOLDOWN_SECONDS")
            or flow_control.get("success_cooldown_seconds"),
            600,
        ),
        "rate_limit_cooldown_seconds": _int_value(
            envelope.get("notebooklm_rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_NOTEBOOKLM_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            3600,
        ),
        "auth_cooldown_seconds": _int_value(
            envelope.get("notebooklm_auth_cooldown_seconds")
            or os.environ.get("SOLAR_NOTEBOOKLM_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            21600,
        ),
        "defer_on_cooldown": _bool_value(
            envelope.get("notebooklm_defer_on_cooldown")
            or os.environ.get("SOLAR_NOTEBOOKLM_DEFER_ON_COOLDOWN")
            or flow_control.get("defer_on_cooldown"),
            True,
        ),
        "defer_on_auth": _bool_value(
            envelope.get("notebooklm_defer_on_auth")
            or os.environ.get("SOLAR_NOTEBOOKLM_DEFER_ON_AUTH")
            or flow_control.get("defer_on_auth"),
            True,
        ),
    }


def _load_request_from_file(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"NotebookLM request file must contain JSON object: {path}")
    return payload


def _derive_notebook_name(request_payload: dict[str, Any], envelope: dict[str, Any]) -> str:
    explicit = str(request_payload.get("notebook_name") or "").strip()
    if explicit:
        return explicit
    metadata = request_payload.get("metadata") if isinstance(request_payload.get("metadata"), dict) else {}
    group = (
        str(request_payload.get("notebook_group") or "").strip()
        or str(metadata.get("notebook_group") or "").strip()
        or str(envelope.get("notebook_group") or "").strip()
        or "NotebookLM"
    )
    date_str = (
        str(metadata.get("date") or "").strip()
        or str(envelope.get("date") or "").strip()
    )
    if date_str:
        return f"{group} {date_str[:10]}"
    return group


def build_notebooklm_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    raw_request = envelope.get("notebooklm_request")
    if isinstance(raw_request, dict):
        request_payload = deepcopy(raw_request)
    else:
        file_ref = (
            str(envelope.get("notebooklm_request_file") or "").strip()
            or str(envelope.get("request_file") or "").strip()
        )
        if file_ref:
            request_payload = _load_request_from_file(file_ref)
        else:
            request_payload = {}
            for key in (
                "source_files",
                "mindmap",
                "infographics",
                "allow_text_fallback",
                "notebook_name",
                "metadata",
                "output_dir",
            ):
                if key in envelope:
                    request_payload[key] = deepcopy(envelope[key])
    metadata = request_payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    request_payload["metadata"] = metadata
    if envelope.get("sprint_id") and not metadata.get("sprint_id"):
        metadata["sprint_id"] = str(envelope["sprint_id"])
    if envelope.get("node_id") and not metadata.get("node_id"):
        metadata["node_id"] = str(envelope["node_id"])
    if envelope.get("logical_operator") and not metadata.get("logical_operator"):
        metadata["logical_operator"] = str(envelope["logical_operator"])
    if envelope.get("task_id") and not metadata.get("task_id"):
        metadata["task_id"] = str(envelope["task_id"])
    if envelope.get("objective") and not metadata.get("objective"):
        metadata["objective"] = str(envelope["objective"])
    if task_dir is not None and not str(request_payload.get("output_dir") or "").strip():
        request_payload["output_dir"] = str((task_dir / "notebooklm-output").resolve())
    request_payload["notebook_name"] = _derive_notebook_name(request_payload, envelope)
    return request_payload


def _task_dir() -> Path:
    raw = str(os.environ.get("TASK_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path.cwd()


def _summary_markdown(response: dict[str, Any]) -> str:
    lines = [
        "# NotebookLM Operator Result",
        "",
        "## 已完成",
        f"- notebook_name: {response.get('notebook_name') or 'N/A'}",
        f"- notebook_title: {response.get('notebook_title') or 'N/A'}",
        f"- source_count: {response.get('source_count') or 0}",
    ]
    mindmap = response.get("mindmap") or {}
    if isinstance(mindmap, dict) and mindmap:
        lines.append(f"- mindmap_status: {mindmap.get('status') or 'N/A'}")
    infographics = response.get("infographics") or []
    if isinstance(infographics, list):
        lines.append(f"- infographic_count: {len(infographics)}")
    lines.extend(
        [
            "",
            "## 说明",
            "- 本输出来自 NotebookLM command operator wrapper。",
            "- 详细 JSON 已写入任务目录工件，供后续流程读取。",
        ]
    )
    return "\n".join(lines)


def run_notebooklm_request(request_payload: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    task_dir = task_dir or _task_dir()
    task_dir.mkdir(parents=True, exist_ok=True)
    cmd = notebooklm_wrapper_cmd()
    if not cmd:
        raise NotebookLMOperatorError("NotebookLM wrapper command is not configured")
    request_dir = task_dir / "notebooklm-browser-agent-request"
    request_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "notebooklm-request.json").write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["BROWSER_AGENT_REQUEST_DIR"] = str(request_dir)
    timeout = int(
        request_payload.get("timeout_seconds")
        or os.environ.get("BROWSER_AGENT_NOTEBOOKLM_TIMEOUT")
        or 1800
    )
    env["BROWSER_AGENT_NOTEBOOKLM_TIMEOUT"] = str(timeout)
    proc = subprocess.run(
        cmd,
        input=json.dumps(request_payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
    )
    combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    (task_dir / "notebooklm-wrapper-output.txt").write_text(
        combined + ("\n" if combined else ""),
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise NotebookLMOperatorError(
            f"NotebookLM wrapper failed rc={proc.returncode}: {combined[-1000:]}",
            combined_output=combined,
        )
    try:
        response = _extract_json_payload_lenient(combined)
    except Exception as exc:
        raise NotebookLMOperatorError(
            f"NotebookLM wrapper returned invalid JSON: {exc}",
            combined_output=combined,
        ) from exc
    (task_dir / "notebooklm-result.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(_summary_markdown(response))
    return response


def main() -> int:
    envelope = _load_envelope()
    task_dir = _task_dir()
    ofc.clear_task_control(task_dir)
    request_payload = build_notebooklm_request(envelope, task_dir=task_dir)
    rate_control = _rate_control_settings(envelope)
    operator_id = str(rate_control["operator_id"])
    source_files = request_payload.get("source_files") or []
    if not isinstance(source_files, list) or not source_files:
        raise SystemExit("NotebookLM operator requires source_files")
    try:
        ofc.ensure_operator_available(operator_id)
        run_notebooklm_request(request_payload, task_dir=task_dir)
        ofc.apply_success_cooldown(
            operator_id,
            success_cooldown_seconds=int(rate_control.get("success_cooldown_seconds") or 0),
        )
        return 0
    except Exception as exc:
        combined_output = exc.combined_output if isinstance(exc, NotebookLMOperatorError) else str(exc)
        ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=combined_output,
            rate_limit_cooldown_seconds=int(rate_control.get("rate_limit_cooldown_seconds") or 0),
            auth_cooldown_seconds=int(rate_control.get("auth_cooldown_seconds") or 0),
            defer_on_cooldown=bool(rate_control.get("defer_on_cooldown")),
            defer_on_auth=bool(rate_control.get("defer_on_auth")),
        )
        print(f"notebooklm_operator failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
