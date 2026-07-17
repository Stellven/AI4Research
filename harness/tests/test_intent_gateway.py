import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "lib" / "intent_gateway.py"
TOOLS_SCRIPT = ROOT / "tools" / "intent_gateway.py"


def _load_gateway(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_capture_writes_raw_rewritten_ir_and_trace(tmp_path):
    env = dict(os.environ)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "capture",
            "--text",
            "修复 Solar-Harness intake 入口，让所有用户原始需求先进入 RawIntent Gateway。",
            "--source-channel",
            "codex_macbook",
            "--repo",
            "/tmp/Solar",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    intent_id = payload["intent_id"]
    base = tmp_path / "intents" / intent_id

    raw = json.loads((base / "raw_intent.json").read_text())
    rewritten = json.loads((base / "rewritten_intent.json").read_text())
    ir = json.loads((base / "requirement_ir.json").read_text())
    trace = json.loads((base / "requirement_trace.json").read_text())

    assert raw["schema_version"] == "solar.raw_intent.v1"
    assert raw["source"]["channel"] == "codex_macbook"
    assert rewritten["schema_version"] == "solar.rewritten_intent.v1"
    assert ir["schema_version"] == "solar.requirement_ir.v1"
    assert ir["compiler_next"] == "pm_planner_task_graph"
    assert trace["stages"][-1]["stage"] == "requirement_ir_compile"


def test_bind_copies_intent_artifacts_to_sprint(tmp_path):
    env = dict(os.environ)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    capture = subprocess.run(
        [sys.executable, str(SCRIPT), "capture", "--text", "新增统一入口。", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    intent_id = json.loads(capture.stdout)["intent_id"]
    sprint_id = "sprint-20990101-000000"
    subprocess.run(
        [sys.executable, str(SCRIPT), "bind", "--intent-id", intent_id, "--sprint-id", sprint_id, "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )

    sprints = tmp_path / "sprints"
    assert (sprints / f"{sprint_id}.raw_intent.json").exists()
    ir = json.loads((sprints / f"{sprint_id}.requirement_ir.json").read_text())
    assert ir["intent_id"] == intent_id
    assert ir["sprint_id"] == sprint_id


def test_browser_agent_operator_intent_mode_prefers_strategy_over_research(tmp_path):
    env = dict(os.environ)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "capture",
            "--text",
            "实现 Browser Agent 物理执行算子，调用 ChatGPT Deep Research 和 Gemini Deep Research，但必须接入 operator runtime/schema。",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    ir = json.loads((tmp_path / "intents" / payload["intent_id"] / "requirement_ir.json").read_text())
    assert ir["lane"] == "strategy"


def test_capture_embeds_research_artifact_into_requirement_ir(tmp_path):
    env = dict(os.environ)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "capture",
            "--text",
            "通过 Browser Agent 前门做需求研究并继续编译。",
            "--require-research-artifact",
            "--research-artifact",
            "/tmp/frontdoor-research.json",
            "--research-project-name",
            "需求研究-2026-05",
            "--research-conversation-id",
            "conv-frontdoor-001",
            "--research-source-url",
            "https://chatgpt.com/c/conv-frontdoor-001",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    intent_id = payload["intent_id"]
    base = tmp_path / "intents" / intent_id
    raw = json.loads((base / "raw_intent.json").read_text())
    ir = json.loads((base / "requirement_ir.json").read_text())
    assert raw["routing_hints"]["require_research_artifact"] is True
    assert raw["research"]["path"] == "/tmp/frontdoor-research.json"
    assert ir["source_inputs"]["research_artifact"]["conversation_id"] == "conv-frontdoor-001"


@pytest.mark.parametrize(
    "prompt",
    [
        "Build me a deep research report comparing GitHub Copilot, Cursor, and Claude Code for a startup team.",
        "Give me a summary of websites and videos that discuss recursive self-improvement (RSI).",
        "Which AI provider is best right now between Anthropic, OpenAI, and Grok? Compare evidence and cite sources.",
        "Compare current AI coding assistants and cite the evidence behind each material claim.",
        "Research current runtime architectures for AI coding agents and cite official sources.",
        "Write a sourced report comparing API schemas across three providers.",
        "Compare package managers using current documentation and independent benchmarks.",
        "Review security controls across IDE assistants using official documentation.",
    ],
)
def test_general_user_research_requests_get_research_lane_and_roles(prompt):
    gateway = _load_gateway(f"intent_gateway_research_{abs(hash(prompt))}")

    rewritten = gateway.deterministic_rewrite(prompt)

    assert rewritten["suggested_lane"] == "research"
    assert rewritten["suggested_logical_operators"] == [
        "RequirementCompiler",
        "Planner",
        "ResearchScout",
        "ResearchSynthesizer",
        "Verifier",
    ]


@pytest.mark.parametrize(
    "prompt",
    [
        (
            "Create a deep research report comparing GitHub Copilot, Cursor, and Claude Code. "
            "Use current sources and cite every material claim. Deliver Markdown, not a CLI or JSON tool."
        ),
        "Compare the current evidence and produce a report, not a web app or command-line application.",
        "Summarize these websites with citations; do not build a script, package, or plugin.",
        "I need an evidence review rather than a CLI tool or software service.",
    ],
)
def test_negated_technical_artifacts_do_not_override_research_intent(prompt):
    gateway = _load_gateway(f"intent_gateway_negated_artifact_{abs(hash(prompt))}")

    assert gateway.infer_mode(prompt) == "research"


@pytest.mark.parametrize(
    ("prompt", "expected_lane"),
    [
        ("Implement the Deep Research runtime operator and schema.", "strategy"),
        ("Build a Python CLI that compares two JSON files.", "delivery"),
        ("Build a CLI that produces research reports from local JSON files.", "delivery"),
        ("Build a web app, not a CLI, that displays research reports.", "delivery"),
        ("Write a script without external packages that summarizes a list of websites.", "delivery"),
        ("Write a Python script that summarizes a list of websites.", "delivery"),
        ("Find and repair broken symlinks in the package.", "delivery"),
        ("Fix the deep-research scheduler bug.", "debug"),
        ("Build a runtime scheduler for the research operator.", "strategy"),
    ],
)
def test_engineering_comparison_requests_do_not_become_research(prompt, expected_lane):
    gateway = _load_gateway(f"intent_gateway_negative_{abs(hash(prompt))}")

    assert gateway.infer_mode(prompt) == expected_lane


def test_legacy_tool_entrypoint_delegates_to_canonical_gateway():
    canonical = _load_gateway("intent_gateway_canonical_parity")
    spec = importlib.util.spec_from_file_location("intent_gateway_tool_parity", TOOLS_SCRIPT)
    assert spec and spec.loader
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    prompts = [
        "Build me a deep research report comparing GitHub Copilot, Cursor, and Claude Code.",
        "Write a Python script that summarizes a list of websites.",
        "Implement the Deep Research runtime operator and schema.",
    ]
    assert [tool.infer_mode(prompt) for prompt in prompts] == [
        canonical.infer_mode(prompt) for prompt in prompts
    ]
    assert Path(tool.extract_research_artifact.__code__.co_filename).resolve() == SCRIPT.resolve()
    assert tool.extract_research_artifact.__code__.co_code == canonical.extract_research_artifact.__code__.co_code
    assert tool.bind_intent_artifacts.__code__.co_code == canonical.bind_intent_artifacts.__code__.co_code
