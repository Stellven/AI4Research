"""Pluggable writer backends for survey section production."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from research.report_metrics import append_model_usage_event, build_model_usage_event, parse_model_cli_output


class SurveyWriterBackend(Protocol):
    """Minimal interface for section writer implementations."""

    name: str

    def write(self, prompt_packet: dict, fallback_text: str) -> str:
        """Return a section draft from a prompt packet."""


class HumanResponseMissingError(RuntimeError):
    """Raised when a human-packet backend has no response artifact yet."""

    def __init__(self, response_path: str) -> None:
        super().__init__(f"human_response_missing:{response_path}")
        self.response_path = response_path


class LocalCommandWriterError(RuntimeError):
    """Raised when a local command writer cannot produce a draft."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"local_command_writer_failed:{reason}")
        self.reason = reason


class PanePacketPendingError(RuntimeError):
    """Raised when a pane packet has been prepared but no response exists yet."""

    def __init__(self, response_path: str, dispatch_path: str, pane_target: str = "", submitted: bool = False) -> None:
        super().__init__(f"pane_response_missing:{response_path}")
        self.response_path = response_path
        self.dispatch_path = dispatch_path
        self.pane_target = pane_target
        self.submitted = submitted


@dataclass
class DeterministicSurveyWriterBackend:
    """Built-in backend used for local/offline verification."""

    name: str = "deterministic"

    def write(self, prompt_packet: dict, fallback_text: str) -> str:
        return fallback_text


@dataclass
class HumanPacketSurveyWriterBackend:
    """Backend that consumes an externally written Markdown response."""

    name: str = "human-packet"
    allow_fallback: bool = False

    def write(self, prompt_packet: dict, fallback_text: str) -> str:
        response_path = str((prompt_packet.get("artifact_paths") or {}).get("human_response") or "")
        if not response_path:
            raise HumanResponseMissingError("N/A")
        path = Path(response_path).expanduser()
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            if self.allow_fallback:
                return fallback_text
            raise HumanResponseMissingError(str(path))
        return path.read_text(encoding="utf-8")


@dataclass
class LocalCommandSurveyWriterBackend:
    """Backend that pipes prompt packet JSON to a local command."""

    command: str
    timeout_seconds: int = 120
    name: str = "local-command"

    def write(self, prompt_packet: dict, fallback_text: str) -> str:
        if not self.command.strip():
            raise LocalCommandWriterError("missing_command")
        payload = json.dumps(prompt_packet, ensure_ascii=False)
        try:
            result = subprocess.run(
                self.command,
                input=payload,
                text=True,
                shell=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LocalCommandWriterError(f"timeout:{self.timeout_seconds}") from exc
        if result.returncode != 0:
            stderr = (result.stderr or "").strip().replace("\n", " ")[:500]
            raise LocalCommandWriterError(f"exit_{result.returncode}:{stderr}")
        output, usage, _ = parse_model_cli_output(result.stdout or "", result.stderr or "")
        if not output:
            raise LocalCommandWriterError("empty_stdout")
        usage_path = str((prompt_packet.get("artifact_paths") or {}).get("model_usage") or "")
        if usage_path:
            append_model_usage_event(
                usage_path,
                build_model_usage_event(
                    backend=self.name,
                    model=self.command,
                    prompt=payload,
                    output=output,
                    usage=usage,
                    metadata={
                        "stage": "survey_section_writer",
                        "section_id": prompt_packet.get("section_id"),
                        "round_index": prompt_packet.get("round_index"),
                    },
                ),
            )
        return output + "\n"


@dataclass
class PanePacketSurveyWriterBackend:
    """Backend that prepares a pane dispatch packet and consumes its response."""

    pane_target: str = ""
    send: bool = False
    allow_fallback: bool = False
    timeout_seconds: int = 120
    name: str = "pane-packet"

    def write(self, prompt_packet: dict, fallback_text: str) -> str:
        paths = prompt_packet.get("artifact_paths") or {}
        response_path = str(paths.get("human_response") or "")
        dispatch_path = str(paths.get("pane_dispatch") or "")
        if not response_path or not dispatch_path:
            raise PanePacketPendingError(response_path or "N/A", dispatch_path or "N/A", self.pane_target, False)
        response = Path(response_path).expanduser()
        if response.exists() and response.read_text(encoding="utf-8").strip():
            return response.read_text(encoding="utf-8")
        dispatch = Path(dispatch_path).expanduser()
        dispatch.parent.mkdir(parents=True, exist_ok=True)
        self._write_dispatch(dispatch, prompt_packet, response)
        submitted = False
        if self.send:
            submitted = self._send_to_pane(dispatch, response)
        if self.allow_fallback:
            return fallback_text
        raise PanePacketPendingError(str(response), str(dispatch), self.pane_target, submitted)

    def _write_dispatch(self, dispatch: Path, prompt_packet: dict, response: Path) -> None:
        lines = [
            f"# Pane Survey Writer Dispatch: {prompt_packet.get('section_id')}",
            "",
            "## Goal",
            "",
            "Write the survey section using only the prompt packet constraints and evidence identifiers.",
            "",
            "## Prompt Packet",
            "",
            str((prompt_packet.get("artifact_paths") or {}).get("prompt_packet_md") or "N/A"),
            "",
            "## Response Path",
            "",
            str(response),
            "",
            "## Rules",
            "",
            "- Write only the completed Markdown section to the response path.",
            "- Preserve [claim:<id>] and [evidence:<id>] tags.",
            "- Do not invent sources, URLs, papers, metrics, or benchmark results.",
            "- Include Architecture Synthesis, Evaluation And Risk Boundary, Contradiction Slots, Source Map, Claim Map, and Open Problems.",
        ]
        dispatch.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _send_to_pane(self, dispatch: Path, response: Path) -> bool:
        if not self.pane_target.strip():
            raise LocalCommandWriterError("pane_target_missing")
        self._guard_pane_target()
        prompt = f"读取并执行 {dispatch}; 完成后只把正文写入 {response}"
        try:
            result = subprocess.run(
                ["tmux", "send-keys", "-t", self.pane_target, prompt, "Enter"],
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LocalCommandWriterError(f"pane_send_timeout:{self.timeout_seconds}") from exc
        if result.returncode != 0:
            stderr = (result.stderr or "").strip().replace("\n", " ")[:500]
            raise LocalCommandWriterError(f"pane_send_exit_{result.returncode}:{stderr}")
        return True

    def _guard_pane_target(self) -> None:
        if os.environ.get("SOLAR_ALLOW_MAIN_PANE_SURVEY_SEND") == "1":
            return
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "-t", self.pane_target, "#{session_name}\t#{pane_title}"],
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LocalCommandWriterError(f"pane_target_probe_timeout:{self.timeout_seconds}") from exc
        if result.returncode != 0:
            stderr = (result.stderr or "").strip().replace("\n", " ")[:500]
            raise LocalCommandWriterError(f"pane_target_probe_exit_{result.returncode}:{stderr}")
        raw = (result.stdout or "").strip()
        session, _, title = raw.partition("\t")
        title = title.strip()
        if session == "solar-harness" and not re.search(r"\b(lab-builder|Builder [1-4])\b", title):
            raise LocalCommandWriterError(
                f"pane_target_role_forbidden:{self.pane_target}:"
                "survey pane-send must use lab-builder panes; "
                "set SOLAR_ALLOW_MAIN_PANE_SURVEY_SEND=1 only for explicit manual override"
            )


def get_writer_backend(
    name: str | None = None,
    *,
    local_command: str = "",
    timeout_seconds: int = 120,
    pane_target: str = "",
    pane_send: bool = False,
) -> SurveyWriterBackend:
    normalized = (name or "deterministic").strip().lower()
    if normalized == "deterministic":
        return DeterministicSurveyWriterBackend()
    if normalized == "human-packet":
        return HumanPacketSurveyWriterBackend()
    if normalized in {"human-packet-fallback", "human-fallback"}:
        return HumanPacketSurveyWriterBackend(name="human-packet-fallback", allow_fallback=True)
    if normalized in {"local-command", "local-llm-command", "command"}:
        return LocalCommandSurveyWriterBackend(command=local_command, timeout_seconds=timeout_seconds)
    if normalized == "pane-packet":
        return PanePacketSurveyWriterBackend(pane_target=pane_target, send=pane_send, timeout_seconds=timeout_seconds)
    if normalized in {"pane-packet-fallback", "pane-fallback"}:
        return PanePacketSurveyWriterBackend(
            pane_target=pane_target,
            send=pane_send,
            allow_fallback=True,
            timeout_seconds=timeout_seconds,
            name="pane-packet-fallback",
        )
    raise ValueError(f"unsupported_survey_writer_backend:{normalized}")
