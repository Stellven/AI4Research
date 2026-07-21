"""Action risk classification.

RISK_CLASS_TABLE is the 18-row source of truth from
sprint-20260519-...-s02-architecture.policy-decisions.md §2.

classify_action(submission) walks the table in a deterministic order
(high-risk / destructive patterns first) and returns the first matching
RiskRule. Returning None means POLICY_WARN — the caller MUST treat
unknown kinds/commands as high-risk pending review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


HOME = Path.home()


@dataclass(frozen=True)
class RiskRule:
    rule_id: int
    kind: str
    description: str
    risk_class: str
    approval_required: bool
    matcher_tag: str


RISK_CLASS_TABLE: list[RiskRule] = [
    RiskRule(1,  "shell",            "grep/sed/jq/cat/head/tail/wc read-only filters",         "low",    False, "read_only_filter"),
    RiskRule(2,  "shell",            "py_compile / python -c 'import json' static validation", "low",    False, "static_validation"),
    RiskRule(3,  "shell",            "pytest test execution",                                  "medium", False, "pytest"),
    RiskRule(4,  "shell",            "npm/pip/bun install dependency install",                 "medium", False, "pkg_install"),
    RiskRule(5,  "shell",            "solar-harness graph-scheduler mark/validate",            "low",    False, "graph_scheduler"),
    RiskRule(6,  "shell",            "solar-harness context inject / intent match",            "low",    False, "harness_query"),
    RiskRule(7,  "shell",            "apply patch / code modification",                        "high",   True,  "apply_patch"),
    RiskRule(8,  "shell",            "git commit/push/reset external repo write",              "high",   True,  "git_write"),
    RiskRule(9,  "shell",            "curl POST/PUT external HTTP write",                      "high",   True,  "curl_write"),
    RiskRule(10, "file_write",       "write to sprint directory",                              "medium", False, "sprint_dir_write"),
    RiskRule(11, "file_write",       "write to ~/Solar/ source repo",                          "high",   True,  "solar_repo_write"),
    RiskRule(12, "tool_call",        "generic MCP / Claude tool call",                         "medium", False, "mcp_call"),
    RiskRule(13, "python",           "import harness.lib.* function call",                     "medium", False, "harness_import"),
    RiskRule(14, "python",           "subprocess.run arbitrary command",                       "high",   True,  "subprocess_run"),
    RiskRule(15, "research_extract", "DeepResearch claim extraction read-only",                "medium", False, "research_extract"),
    RiskRule(16, "human_approval",   "approval gate action itself",                            "high",   True,  "approval_gate"),
    RiskRule(17, "shell",            "rm/mv/cp destructive file ops",                          "high",   True,  "destructive_file_op"),
    RiskRule(18, "tool_call",        "Slack/email/external messaging",                         "high",   True,  "external_msg"),
]


def _rule(rule_id: int) -> RiskRule:
    return RISK_CLASS_TABLE[rule_id - 1]


_RE_DESTRUCTIVE = re.compile(r"(^|[\s;&|])\s*(rm|mv|cp)\s+")
_RE_GIT_WRITE = re.compile(r"\bgit\s+(commit|push|reset)\b")
_RE_CURL_WRITE = re.compile(
    r"\bcurl\b.*?(-X\s*(POST|PUT|DELETE|PATCH)|--request\s+(POST|PUT|DELETE|PATCH)"
    r"|--data(-binary|-raw)?\b|\s-d\s)",
    re.IGNORECASE,
)
_RE_APPLY = re.compile(r"^\s*apply(\s|$)")
_RE_PKG_INSTALL = re.compile(r"\b(npm|pip|bun|pip3)\s+install\b")
_RE_PYTEST = re.compile(r"\bpytest\b|python3?\s+-m\s+pytest\b")
_RE_PYCOMPILE = re.compile(r"py_compile\b|python3?\s+-c\s+['\"]?\s*import\s+json")
_RE_HARNESS_SCHED = re.compile(r"solar-harness(\.sh)?\s+graph-scheduler\b")
_RE_HARNESS_QUERY = re.compile(r"solar-harness(\.sh)?\s+(context|intent)\b")
_RE_READ_FILTERS = re.compile(r"\b(grep|sed|jq|cat|head|tail|wc)\b")
_RE_EXTERNAL_MSG = re.compile(r"slack|email|gmail|sms|webhook|smtp", re.IGNORECASE)


def _classify_shell(cmd: str) -> Optional[RiskRule]:
    if not cmd:
        return None
    if _RE_DESTRUCTIVE.search(cmd):
        return _rule(17)
    if _RE_GIT_WRITE.search(cmd):
        return _rule(8)
    if _RE_CURL_WRITE.search(cmd):
        return _rule(9)
    if _RE_APPLY.search(cmd):
        return _rule(7)
    if _RE_PKG_INSTALL.search(cmd):
        return _rule(4)
    if _RE_PYTEST.search(cmd):
        return _rule(3)
    if _RE_PYCOMPILE.search(cmd):
        return _rule(2)
    if _RE_HARNESS_SCHED.search(cmd):
        return _rule(5)
    if _RE_HARNESS_QUERY.search(cmd):
        return _rule(6)
    if _RE_READ_FILTERS.search(cmd):
        return _rule(1)
    return None


def _classify_file_write(path: str) -> Optional[RiskRule]:
    if not path:
        return None
    if path.startswith(str(HOME / "Solar") + "/"):
        return _rule(11)
    if "/sprints/" in path or path.startswith("sprints/") or "/.solar/harness/" in path:
        return _rule(10)
    return _rule(10)


def _classify_tool_call(tool_name: str) -> RiskRule:
    if tool_name and _RE_EXTERNAL_MSG.search(tool_name):
        return _rule(18)
    return _rule(12)


def _classify_python(submission: dict) -> RiskRule:
    src = submission.get("source") or submission.get("command") or ""
    if "subprocess.run" in src or "subprocess.Popen" in src or "subprocess.call" in src:
        return _rule(14)
    return _rule(13)


def classify_action(submission: dict) -> Optional[RiskRule]:
    """Classify an action submission against the 18-row RISK_CLASS_TABLE.

    Returns None when no rule matches (caller should emit POLICY_WARN
    and treat as high-risk pending guardian review).
    """
    kind = (submission or {}).get("kind", "")
    if kind == "shell":
        return _classify_shell(submission.get("command", "") or "")
    if kind == "file_write":
        return _classify_file_write(submission.get("path", "") or "")
    if kind == "tool_call":
        return _classify_tool_call(submission.get("tool_name", "") or "")
    if kind == "python":
        return _classify_python(submission)
    if kind == "research_extract":
        return _rule(15)
    if kind == "human_approval":
        return _rule(16)
    return None
