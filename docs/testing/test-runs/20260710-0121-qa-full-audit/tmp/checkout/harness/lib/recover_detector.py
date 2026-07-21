#!/usr/bin/env python3
"""RecoverDetector — classify stuck Claude Code prompts in tmux panes.

Three detection patterns per architecture.md §5.1:
  DET-PROCEED:   "Do you want to proceed?" class
  DET-QUEUED:    "Press up to edit queued messages" class
  DET-PERMISSION: tool/file permission confirmation class
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class PromptType(str, Enum):
    PROCEED = "DET-PROCEED"
    QUEUED = "DET-QUEUED"
    PERMISSION = "DET-PERMISSION"
    NONE = "DET-NONE"


@dataclass
class DetectResult:
    pane_id: str
    prompt_type: PromptType
    matched_line: Optional[str] = None
    captured_at: str = ""

    @property
    def detected(self) -> bool:
        return self.prompt_type != PromptType.NONE


# Per architecture.md §5.1
DET_PROCEED = re.compile(r"(?i)(do you want|proceed\?)")
DET_QUEUED = re.compile(r"(?i)(press up to edit|queued messages)")
DET_PERMISSION = re.compile(r"(?i)(allow|deny|permission|Do you want to allow)")

DETECTORS: list[tuple[PromptType, re.Pattern[str]]] = [
    (PromptType.PROCEED, DET_PROCEED),
    (PromptType.QUEUED, DET_QUEUED),
    (PromptType.PERMISSION, DET_PERMISSION),
]

DEFAULT_CAPTURE_LINES = 50


def _utc_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tmux_capture(pane_id: str, lines: int = DEFAULT_CAPTURE_LINES,
                  tmux_binary: str = "tmux") -> str:
    try:
        result = subprocess.run(
            [tmux_binary, "capture-pane", "-t", pane_id, "-p", "-S", f"-{lines}"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


class RecoverDetector:
    """Detect and classify stuck prompts in tmux panes."""

    def __init__(
        self,
        *,
        capture_fn: Optional[Callable[[str], str]] = None,
        lines: int = DEFAULT_CAPTURE_LINES,
    ) -> None:
        self._capture = capture_fn or (lambda pid: _tmux_capture(pid, lines))
        self._lines = lines

    def detect_proceed_prompt(self, pane_id: str) -> DetectResult:
        output = self._capture(pane_id)
        return self._scan(output, pane_id, PromptType.PROCEED, DET_PROCEED)

    def detect_queued_message(self, pane_id: str) -> DetectResult:
        output = self._capture(pane_id)
        return self._scan(output, pane_id, PromptType.QUEUED, DET_QUEUED)

    def detect_permission_prompt(self, pane_id: str) -> DetectResult:
        output = self._capture(pane_id)
        return self._scan(output, pane_id, PromptType.PERMISSION, DET_PERMISSION)

    def classify_prompt(self, pane_id: str) -> DetectResult:
        output = self._capture(pane_id)
        for prompt_type, pattern in DETECTORS:
            result = self._scan(output, pane_id, prompt_type, pattern)
            if result.detected:
                return result
        return DetectResult(pane_id=pane_id, prompt_type=PromptType.NONE,
                           captured_at=_utc_now())

    @staticmethod
    def _scan(output: str, pane_id: str, ptype: PromptType,
              pattern: re.Pattern[str]) -> DetectResult:
        for line in output.splitlines():
            if pattern.search(line):
                return DetectResult(
                    pane_id=pane_id,
                    prompt_type=ptype,
                    matched_line=line.strip(),
                    captured_at=_utc_now(),
                )
        return DetectResult(pane_id=pane_id, prompt_type=PromptType.NONE,
                           captured_at=_utc_now())


if __name__ == "__main__":
    import json
    d = RecoverDetector()
    print(json.dumps({"module": "recover_detector", "classes": ["RecoverDetector", "DetectResult", "PromptType"]}))
