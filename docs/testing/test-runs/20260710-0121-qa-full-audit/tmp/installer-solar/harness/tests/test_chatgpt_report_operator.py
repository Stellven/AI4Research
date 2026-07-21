import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "chatgpt_report_operator.py"


def run_operator(
    tmp_path,
    *,
    purpose="",
    kind="",
    expected="markdown",
    write_deep_proof=False,
    write_mode_proof=True,
    sleep_seconds=0,
    action="run",
    stdin_text="write from this material",
    env_extra=None,
    check=True,
):
    wrapper = tmp_path / "fake_wrapper.py"
    wrapper.write_text(
        "import os, sys, json\n"
        "import time\n"
        "from pathlib import Path\n"
        f"sleep_seconds={int(sleep_seconds)}\n"
        "if sleep_seconds:\n"
        "    time.sleep(sleep_seconds)\n"
        "prompt=sys.stdin.read()\n"
        f"write_deep_proof={str(write_deep_proof)!r} == 'True'\n"
        "request_dir=os.environ.get('BROWSER_AGENT_REQUEST_DIR')\n"
        "if write_deep_proof and request_dir:\n"
        "    Path(request_dir).mkdir(parents=True, exist_ok=True)\n"
        "    (Path(request_dir)/'deep-research-state.json').write_text(json.dumps({'ok': True, 'test': True}), encoding='utf-8')\n"
        f"write_mode_proof={str(write_mode_proof)!r} == 'True'\n"
        "if write_mode_proof and request_dir:\n"
        "    Path(request_dir).mkdir(parents=True, exist_ok=True)\n"
        "    (Path(request_dir)/'chatgpt-mode-state.json').write_text(json.dumps({'ok': True, 'test': True}), encoding='utf-8')\n"
        "out={'model':os.environ.get('CHATGPT_MODEL'),"
        "'effort':os.environ.get('CHATGPT_REASONING_EFFORT'),"
        "'model_mode':os.environ.get('BROWSER_AGENT_CHATGPT_MODEL_MODE'),"
        "'tool_mode':os.environ.get('BROWSER_AGENT_CHATGPT_TOOL_MODE'),"
        "'require_deep_research':os.environ.get('BROWSER_AGENT_CHATGPT_REQUIRE_DEEP_RESEARCH'),"
        "'require_ui_mode':os.environ.get('BROWSER_AGENT_CHATGPT_REQUIRE_UI_MODE'),"
        "'action':os.environ.get('BROWSER_AGENT_CHATGPT_ACTION'),"
        "'project':os.environ.get('BROWSER_AGENT_CHATGPT_PROJECT_NAME'),"
        "'profile_directory':os.environ.get('BROWSER_AGENT_PROFILE_DIRECTORY'),"
        "'target_account_email':os.environ.get('BROWSER_AGENT_TARGET_ACCOUNT_EMAIL'),"
        "'chatgpt_account_email':os.environ.get('BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL'),"
        "'prompt':prompt[:1000]}\n"
        "print(json.dumps(out, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "BROWSER_AGENT_CHATGPT_WRAPPER_CMD": f"{sys.executable} {wrapper}",
            "BROWSER_AGENT_REQUEST_DIR": str(tmp_path / "request"),
            "BROWSER_AGENT_PURPOSE": purpose,
            "BROWSER_AGENT_EXPECTED_OUTPUT": expected,
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_DISABLED": "1",
        }
    )
    if env_extra:
        env.update(env_extra)
    if kind:
        env["CHATGPT_REPORT_OPERATOR_KIND"] = kind
    env["CHATGPT_REPORT_ACTION"] = action
    if sleep_seconds:
        env["BROWSER_AGENT_CHATGPT_TIMEOUT"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=check,
    )


def test_planner_sets_thinking_high_and_project(tmp_path):
    proc = run_operator(tmp_path, purpose="ai-influence-report-plan-2026-05-31", expected="json")
    payload = json.loads(proc.stdout)
    assert payload["model_mode"] == "thinking"
    assert payload["effort"] == "high"
    assert payload["tool_mode"] == "none"
    assert payload["require_ui_mode"] == "true"
    assert payload["project"] == "杂项"
    assert "ChatGPT Report Planner" in payload["prompt"]
    meta = json.loads((tmp_path / "request" / "report-operator-request.json").read_text())
    assert meta["operator_kind"] == "planner"
    assert meta["profile_directory"] == ""
    assert meta["target_account_email"] == ""
    assert meta["account_email_hint_present"] is False


def test_explicit_profile_and_account_hints_are_forwarded(tmp_path):
    proc = run_operator(
        tmp_path,
        purpose="hf-paper-l7-high-reasoning-demo",
        env_extra={
            "BROWSER_AGENT_PROFILE_DIRECTORY": "Default",
            "BROWSER_AGENT_TARGET_ACCOUNT_EMAIL": "browser-agent@example.com",
            "BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL": "browser-agent@example.com",
        },
    )
    payload = json.loads(proc.stdout)
    assert payload["profile_directory"] == "Default"
    assert payload["target_account_email"] == "browser-agent@example.com"
    assert payload["chatgpt_account_email"] == "browser-agent@example.com"
    meta = json.loads((tmp_path / "request" / "report-operator-request.json").read_text())
    assert meta["profile_directory"] == "Default"
    assert meta["target_account_email"] == "browser-agent@example.com"
    assert meta["account_email_hint_present"] is True


def test_local_profile_policy_can_fill_account_and_choose_from_pool(tmp_path):
    policy = tmp_path / "browser-agent-chatgpt-local.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "policies": {
                    "default": {
                        "expected_account_email": "browser-agent@example.com",
                        "allowed_profiles": ["Profile 1", "Profile 2"],
                        "selection": "first",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    proc = run_operator(
        tmp_path,
        purpose="hf-paper-l7-high-reasoning-demo",
        env_extra={
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_DISABLED": "0",
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE": str(policy),
        },
    )
    payload = json.loads(proc.stdout)
    assert payload["profile_directory"] == "Profile 1"
    assert payload["target_account_email"] == "browser-agent@example.com"
    assert payload["chatgpt_account_email"] == "browser-agent@example.com"
    meta = json.loads((tmp_path / "request" / "report-operator-request.json").read_text())
    assert meta["profile_policy"]["enabled"] is True
    assert meta["profile_policy"]["policy_key"] == "hf_paper_insight"
    assert meta["profile_policy"]["selected_profile_directory"] == "Profile 1"
    assert meta["profile_policy"]["selected_account_email"] == "browser-agent@example.com"


def test_hf_report_planner_uses_hf_profile_policy_key(tmp_path):
    policy = tmp_path / "browser-agent-chatgpt-local.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "policies": {
                    "default": {
                        "expected_account_email": "someone@example.com",
                        "allowed_profiles": ["Profile X"],
                        "selection": "first",
                    },
                    "hf_paper_insight": {
                        "expected_account_email": "browser-agent@example.com",
                        "allowed_profiles": ["Profile 1"],
                        "selection": "first",
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    proc = run_operator(
        tmp_path,
        purpose="hf-paper-report-plan-2026-06-01",
        expected="json",
        env_extra={
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_DISABLED": "0",
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE": str(policy),
        },
    )
    payload = json.loads(proc.stdout)
    assert payload["profile_directory"] == "Profile 1"
    assert payload["target_account_email"] == "browser-agent@example.com"
    meta = json.loads((tmp_path / "request" / "report-operator-request.json").read_text())
    assert meta["profile_policy"]["policy_key"] == "hf_paper_insight"


def test_hf_report_section_uses_hf_profile_policy_key(tmp_path):
    policy = tmp_path / "browser-agent-chatgpt-local.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "policies": {
                    "default": {
                        "expected_account_email": "someone@example.com",
                        "allowed_profiles": ["Profile X"],
                        "selection": "first",
                    },
                    "hf_paper_insight": {
                        "expected_account_email": "browser-agent@example.com",
                        "allowed_profiles": ["Profile 1"],
                        "selection": "first",
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    proc = run_operator(
        tmp_path,
        purpose="hf-paper-report-section-2026-06-01-doc-intel",
        expected="json",
        env_extra={
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_DISABLED": "0",
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE": str(policy),
        },
    )
    payload = json.loads(proc.stdout)
    assert payload["profile_directory"] == "Profile 1"
    assert payload["target_account_email"] == "browser-agent@example.com"
    meta = json.loads((tmp_path / "request" / "report-operator-request.json").read_text())
    assert meta["profile_policy"]["policy_key"] == "hf_paper_insight"


def test_local_profile_policy_rejects_profile_outside_allowed_pool(tmp_path):
    policy = tmp_path / "browser-agent-chatgpt-local.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "policies": {
                    "default": {
                        "expected_account_email": "browser-agent@example.com",
                        "allowed_profiles": ["Default", "Profile 2"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    proc = run_operator(
        tmp_path,
        purpose="hf-paper-l7-high-reasoning-demo",
        env_extra={
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_DISABLED": "0",
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE": str(policy),
            "BROWSER_AGENT_PROFILE_DIRECTORY": "Profile 1",
        },
        check=False,
    )
    assert proc.returncode == 2
    assert "browser_agent_profile_policy_profile_mismatch" in proc.stderr


def test_local_profile_policy_rejects_account_mismatch(tmp_path):
    policy = tmp_path / "browser-agent-chatgpt-local.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "policies": {
                    "default": {
                        "expected_account_email": "browser-agent@example.com",
                        "allowed_profiles": ["Default"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    proc = run_operator(
        tmp_path,
        purpose="hf-paper-l7-high-reasoning-demo",
        env_extra={
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_DISABLED": "0",
            "BROWSER_AGENT_CHATGPT_PROFILE_POLICY_FILE": str(policy),
            "BROWSER_AGENT_TARGET_ACCOUNT_EMAIL": "someone@example.com",
        },
        check=False,
    )
    assert proc.returncode == 2
    assert "browser_agent_profile_policy_account_mismatch" in proc.stderr


def test_chapter_writer_prompt_hides_internal_fields_instruction(tmp_path):
    proc = run_operator(tmp_path, purpose="ai-influence-report-foo")
    payload = json.loads(proc.stdout)
    assert payload["model_mode"] == "thinking"
    assert payload["require_ui_mode"] == "true"
    assert "ChatGPT Report Chapter Writer" in payload["prompt"]
    assert "不要输出内部处理字段" in payload["prompt"]


def test_planner_requires_thinking_high_mode_proof(tmp_path):
    proc = run_operator(
        tmp_path,
        purpose="ai-influence-report-plan-2026-05-31",
        expected="json",
        write_mode_proof=False,
        check=False,
    )
    assert proc.returncode == 1
    assert "chatgpt-mode-state.json" in proc.stderr


def test_chapter_requires_thinking_high_mode_proof(tmp_path):
    proc = run_operator(tmp_path, purpose="ai-influence-report-foo", write_mode_proof=False, check=False)
    assert proc.returncode == 1
    assert "chatgpt-mode-state.json" in proc.stderr


def test_deep_writer_requires_deep_research_proof(tmp_path):
    proc = run_operator(tmp_path, kind="deep_writer", check=False)
    assert proc.returncode == 1
    assert "deep-research-state.json" in proc.stderr


def test_deep_writer_uses_pro_deep_research_with_proof(tmp_path):
    proc = run_operator(tmp_path, kind="deep_writer", write_deep_proof=True)
    payload = json.loads(proc.stdout)
    assert payload["model_mode"] == "pro"
    assert payload["effort"] == "deep_research"
    assert payload["tool_mode"] == "deep_research"
    assert payload["require_deep_research"] == "true"


def test_deep_writer_submit_action_does_not_require_final_answer(tmp_path):
    proc = run_operator(tmp_path, kind="deep_writer", write_deep_proof=True, action="submit")
    payload = json.loads(proc.stdout)
    assert payload["action"] == "submit"
    assert payload["require_deep_research"] == "true"


def test_deep_writer_collect_allows_empty_stdin(tmp_path):
    proc = run_operator(
        tmp_path,
        kind="deep_writer",
        write_deep_proof=True,
        action="collect",
        stdin_text="",
    )
    payload = json.loads(proc.stdout)
    assert payload["action"] == "collect"


def test_wrapper_timeout_returns_controlled_error(tmp_path):
    proc = run_operator(tmp_path, kind="deep_writer", write_deep_proof=True, sleep_seconds=5, check=False)
    assert proc.returncode == 124
    assert "wrapper timed out after 1s" in proc.stderr
