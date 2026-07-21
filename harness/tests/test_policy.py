"""N4 acceptance tests for harness/lib/policy/.

Each of the 18 RISK_CLASS_TABLE rows has at least one dedicated assertion
(row-pinned by rule_id + risk_class + approval_required). Additionally:
  - unscoped file_write is blocked by write_scope_policy
  - high-risk shell action triggers approval_policy.check == True
  - approval_policy edge cases (unknown / None)
  - classify_action returns None for unknown kinds (POLICY_WARN)
"""

from __future__ import annotations

import pytest

from policy.action_policy import (
    RISK_CLASS_TABLE,
    classify_action,
)
from policy.approval_policy import check as check_approval_required
from policy.write_scope_policy import check as check_write_scope


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------

def test_risk_class_table_has_18_rows():
    assert len(RISK_CLASS_TABLE) == 18
    assert [r.rule_id for r in RISK_CLASS_TABLE] == list(range(1, 19))


def test_risk_class_values_are_canonical():
    allowed = {"low", "medium", "high"}
    for rule in RISK_CLASS_TABLE:
        assert rule.risk_class in allowed, rule


def test_approval_required_aligned_with_risk_class():
    # All "high" rows must mark approval_required=True (S02 §2.3 default)
    for rule in RISK_CLASS_TABLE:
        if rule.risk_class == "high":
            assert rule.approval_required is True, rule
        if rule.risk_class in ("low", "medium"):
            assert rule.approval_required is False, rule


# ---------------------------------------------------------------------------
# Row 1 — shell read-only filters
# ---------------------------------------------------------------------------

def test_row1_shell_grep_low():
    rule = classify_action({"kind": "shell", "command": "grep foo bar.txt"})
    assert rule is not None and rule.rule_id == 1
    assert rule.risk_class == "low"
    assert rule.approval_required is False


def test_row1_shell_jq_low():
    rule = classify_action({"kind": "shell", "command": "jq .foo data.json"})
    assert rule.rule_id == 1
    assert rule.risk_class == "low"


# ---------------------------------------------------------------------------
# Row 2 — shell static validation
# ---------------------------------------------------------------------------

def test_row2_shell_py_compile_low():
    rule = classify_action(
        {"kind": "shell", "command": "python3 -m py_compile harness/lib/policy/action_policy.py"}
    )
    assert rule.rule_id == 2
    assert rule.risk_class == "low"


def test_row2_shell_python_c_import_json_low():
    rule = classify_action(
        {"kind": "shell", "command": "python3 -c 'import json; json.loads(open(\"x.json\").read())'"}
    )
    assert rule.rule_id == 2


# ---------------------------------------------------------------------------
# Row 3 — pytest
# ---------------------------------------------------------------------------

def test_row3_shell_pytest_medium():
    rule = classify_action({"kind": "shell", "command": "pytest -q tests/"})
    assert rule.rule_id == 3
    assert rule.risk_class == "medium"
    assert rule.approval_required is False


def test_row3_shell_python_m_pytest_medium():
    rule = classify_action({"kind": "shell", "command": "python3 -m pytest harness/tests/test_policy.py -q"})
    assert rule.rule_id == 3


# ---------------------------------------------------------------------------
# Row 4 — pkg install
# ---------------------------------------------------------------------------

def test_row4_shell_pip_install_medium():
    rule = classify_action({"kind": "shell", "command": "pip install requests"})
    assert rule.rule_id == 4
    assert rule.risk_class == "medium"


def test_row4_shell_npm_install_medium():
    rule = classify_action({"kind": "shell", "command": "npm install lodash"})
    assert rule.rule_id == 4


# ---------------------------------------------------------------------------
# Row 5 — solar-harness graph-scheduler
# ---------------------------------------------------------------------------

def test_row5_shell_graph_scheduler_low():
    rule = classify_action(
        {"kind": "shell", "command": "solar-harness graph-scheduler mark --node N4 --status reviewing"}
    )
    assert rule.rule_id == 5
    assert rule.risk_class == "low"


# ---------------------------------------------------------------------------
# Row 6 — solar-harness context/intent
# ---------------------------------------------------------------------------

def test_row6_shell_context_inject_low():
    rule = classify_action(
        {"kind": "shell", "command": "solar-harness context inject --query 'risk policy'"}
    )
    assert rule.rule_id == 6
    assert rule.risk_class == "low"


def test_row6_shell_intent_match_low():
    rule = classify_action({"kind": "shell", "command": "solar-harness intent match --text 'do X'"})
    assert rule.rule_id == 6


# ---------------------------------------------------------------------------
# Row 7 — apply patch
# ---------------------------------------------------------------------------

def test_row7_shell_apply_high_requires_approval():
    rule = classify_action({"kind": "shell", "command": "apply /tmp/patch.diff"})
    assert rule.rule_id == 7
    assert rule.risk_class == "high"
    assert rule.approval_required is True


# ---------------------------------------------------------------------------
# Row 8 — git write
# ---------------------------------------------------------------------------

def test_row8_shell_git_commit_high():
    rule = classify_action({"kind": "shell", "command": "git commit -m 'feat: policy'"})
    assert rule.rule_id == 8
    assert rule.risk_class == "high"
    assert rule.approval_required is True


def test_row8_shell_git_push_high():
    rule = classify_action({"kind": "shell", "command": "git push origin main"})
    assert rule.rule_id == 8
    assert rule.risk_class == "high"


def test_row8_shell_git_reset_high():
    rule = classify_action({"kind": "shell", "command": "git reset --hard HEAD~1"})
    assert rule.rule_id == 8


# ---------------------------------------------------------------------------
# Row 9 — curl write
# ---------------------------------------------------------------------------

def test_row9_shell_curl_post_high():
    rule = classify_action(
        {"kind": "shell", "command": "curl -X POST -d '{\"x\":1}' https://example.com/api"}
    )
    assert rule.rule_id == 9
    assert rule.risk_class == "high"
    assert rule.approval_required is True


def test_row9_shell_curl_put_high():
    rule = classify_action(
        {"kind": "shell", "command": "curl --request PUT --data-binary @file https://example.com/api"}
    )
    assert rule.rule_id == 9


# ---------------------------------------------------------------------------
# Row 10 — file_write sprint dir
# ---------------------------------------------------------------------------

def test_row10_file_write_sprint_dir_medium():
    rule = classify_action(
        {"kind": "file_write", "path": "sprints/sprint-20260519-foo.N4-handoff.md"}
    )
    assert rule.rule_id == 10
    assert rule.risk_class == "medium"
    assert rule.approval_required is False


def test_row10_file_write_dot_solar_harness_medium():
    rule = classify_action(
        {"kind": "file_write", "path": "~/.solar/harness/sprints/foo.md"}
    )
    assert rule.rule_id == 10


# ---------------------------------------------------------------------------
# Row 11 — file_write Solar source repo
# ---------------------------------------------------------------------------

def test_row11_file_write_solar_repo_high():
    rule = classify_action(
        {"kind": "file_write", "path": "~/Solar/harness/lib/policy/action_policy.py"}
    )
    assert rule.rule_id == 11
    assert rule.risk_class == "high"
    assert rule.approval_required is True


# ---------------------------------------------------------------------------
# Row 12 — tool_call generic
# ---------------------------------------------------------------------------

def test_row12_tool_call_mcp_medium():
    rule = classify_action({"kind": "tool_call", "tool_name": "mcp__filesystem__read"})
    assert rule.rule_id == 12
    assert rule.risk_class == "medium"
    assert rule.approval_required is False


# ---------------------------------------------------------------------------
# Row 13 — python harness import
# ---------------------------------------------------------------------------

def test_row13_python_harness_import_medium():
    rule = classify_action(
        {"kind": "python", "source": "import harness.lib.event_ledger as el; el.append(...)"}
    )
    assert rule.rule_id == 13
    assert rule.risk_class == "medium"


# ---------------------------------------------------------------------------
# Row 14 — python subprocess.run
# ---------------------------------------------------------------------------

def test_row14_python_subprocess_run_high():
    rule = classify_action(
        {"kind": "python", "source": "subprocess.run(['ls', '-la'], check=True)"}
    )
    assert rule.rule_id == 14
    assert rule.risk_class == "high"
    assert rule.approval_required is True


# ---------------------------------------------------------------------------
# Row 15 — research_extract
# ---------------------------------------------------------------------------

def test_row15_research_extract_medium():
    rule = classify_action(
        {"kind": "research_extract", "source": "https://arxiv.org/abs/2305.12345"}
    )
    assert rule.rule_id == 15
    assert rule.risk_class == "medium"
    assert rule.approval_required is False


# ---------------------------------------------------------------------------
# Row 16 — human_approval
# ---------------------------------------------------------------------------

def test_row16_human_approval_high():
    rule = classify_action({"kind": "human_approval", "subject": "approve deploy"})
    assert rule.rule_id == 16
    assert rule.risk_class == "high"
    assert rule.approval_required is True


# ---------------------------------------------------------------------------
# Row 17 — destructive shell
# ---------------------------------------------------------------------------

def test_row17_shell_rm_high():
    rule = classify_action({"kind": "shell", "command": "rm -rf /tmp/scratch"})
    assert rule.rule_id == 17
    assert rule.risk_class == "high"
    assert rule.approval_required is True


def test_row17_shell_mv_high():
    rule = classify_action({"kind": "shell", "command": "mv /tmp/a /tmp/b"})
    assert rule.rule_id == 17


def test_row17_shell_cp_high():
    rule = classify_action({"kind": "shell", "command": "cp /etc/passwd /tmp/leak"})
    assert rule.rule_id == 17


# ---------------------------------------------------------------------------
# Row 18 — tool_call external messaging
# ---------------------------------------------------------------------------

def test_row18_tool_call_slack_high():
    rule = classify_action({"kind": "tool_call", "tool_name": "mcp__slack__send_message"})
    assert rule.rule_id == 18
    assert rule.risk_class == "high"
    assert rule.approval_required is True


def test_row18_tool_call_email_high():
    rule = classify_action({"kind": "tool_call", "tool_name": "mcp__gmail__send"})
    assert rule.rule_id == 18


# ---------------------------------------------------------------------------
# Unknown kinds → POLICY_WARN
# ---------------------------------------------------------------------------

def test_unknown_kind_returns_none():
    assert classify_action({"kind": "telepathy", "payload": "..."}) is None


def test_empty_submission_returns_none():
    assert classify_action({}) is None


# ---------------------------------------------------------------------------
# write_scope_policy — acceptance: unscoped file_write blocked
# ---------------------------------------------------------------------------

def test_write_scope_unscoped_path_denied():
    verdict, reason = check_write_scope(
        write_set=["/etc/passwd"],
        node_write_scope=["sprints/sprint-20260519-foo"],
    )
    assert verdict == "DENY"
    assert "not in" in reason.lower() or "scope" in reason.lower()


def test_write_scope_exact_path_match_pass():
    verdict, _ = check_write_scope(
        write_set=["harness/lib/policy/action_policy.py"],
        node_write_scope=["harness/lib/policy/action_policy.py"],
    )
    assert verdict == "PASS"


def test_write_scope_prefix_directory_pass():
    verdict, _ = check_write_scope(
        write_set=["harness/lib/policy/action_policy.py", "harness/lib/policy/__init__.py"],
        node_write_scope=["harness/lib/policy"],
    )
    assert verdict == "PASS"


def test_write_scope_one_of_many_unscoped_denies():
    verdict, reason = check_write_scope(
        write_set=["harness/lib/policy/x.py", "harness/lib/other/y.py"],
        node_write_scope=["harness/lib/policy"],
    )
    assert verdict == "DENY"
    assert "other" in reason


def test_write_scope_empty_scope_with_writes_denies():
    verdict, _ = check_write_scope(
        write_set=["harness/lib/policy/x.py"],
        node_write_scope=[],
    )
    assert verdict == "DENY"


def test_write_scope_empty_writes_passes_trivially():
    verdict, _ = check_write_scope(write_set=[], node_write_scope=[])
    assert verdict == "PASS"


# ---------------------------------------------------------------------------
# approval_policy — acceptance: high-risk shell requires approval
# ---------------------------------------------------------------------------

def test_approval_high_requires():
    assert check_approval_required("high") is True


def test_approval_medium_not_required():
    assert check_approval_required("medium") is False


def test_approval_low_not_required():
    assert check_approval_required("low") is False


def test_approval_unknown_defaults_to_required():
    assert check_approval_required("plaid") is True
    assert check_approval_required("") is True
    assert check_approval_required(None) is True


def test_acceptance_high_risk_shell_requires_approval():
    """Acceptance row: high-risk shell approval_required=True."""
    rule = classify_action({"kind": "shell", "command": "git push origin main"})
    assert rule is not None
    assert rule.risk_class == "high"
    assert check_approval_required(rule.risk_class) is True
    assert rule.approval_required is True


def test_acceptance_low_risk_shell_no_approval():
    rule = classify_action({"kind": "shell", "command": "grep TODO src/main.py"})
    assert rule.risk_class == "low"
    assert check_approval_required(rule.risk_class) is False
