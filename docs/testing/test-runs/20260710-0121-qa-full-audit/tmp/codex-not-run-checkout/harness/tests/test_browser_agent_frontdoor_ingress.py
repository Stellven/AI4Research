from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTENT_GATEWAY = ROOT / "lib" / "intent_gateway.py"
INTENT_CONSUMER = ROOT / "lib" / "intent_consumer.py"
PM_DISPATCH_PATH = ROOT / "tools" / "pm_dispatch.py"
CODEX_PM_ROUTER_PATH = ROOT / "tools" / "codex_pm_router.py"
ANTIGRAVITY_PATH = ROOT / "tools" / "antigravity_multimodal_agent.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _intent_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["SOLAR_HARNESS_DIR"] = str(ROOT)
    env["HARNESS_DIR"] = str(ROOT)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"] = str(tmp_path / "workspace")
    return env


def test_codex_router_defaults_to_rawintent_gateway_then_consumer(monkeypatch):
    router = _load_module("codex_pm_router_frontdoor", CODEX_PM_ROUTER_PATH)
    calls: list[list[str]] = []

    def fake_run(cmd, text=True, capture_output=True, env=None, timeout=None):
        calls.append(list(cmd))
        if str(cmd[1]).endswith("intent_gateway.py"):
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"intent_id": "intent-frontdoor-codex"}) + "\n",
                stderr="",
            )
        if str(cmd[1]).endswith("intent_consumer.py"):
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"results": [{"status": "consumed"}]}) + "\n",
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess command: {cmd}")

    monkeypatch.setattr(router.subprocess, "run", fake_run)
    args = argparse.Namespace(
        emit_dir="",
        sprint_id="",
        auto_dispatch_planner=True,
        format="json",
    )

    assert router._capture_and_consume_rawintent(args, "统一 Codex 入口前门") == 0
    assert len(calls) == 2
    assert str(calls[0][1]).endswith("intent_gateway.py")
    assert calls[0][2] == "capture"
    assert "codex_pm_router" in calls[0]
    assert str(calls[1][1]).endswith("intent_consumer.py")
    assert calls[1][2] == "consume"
    assert "intent-frontdoor-codex" in calls[1]


def test_pm_compile_request_routes_to_rawintent_frontdoor_by_default(monkeypatch, tmp_path):
    pm_dispatch = _load_module("pm_dispatch_frontdoor", PM_DISPATCH_PATH)
    monkeypatch.delenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", raising=False)

    captured: dict[str, object] = {}

    def fake_capture_entrypoint_raw_intent(**kwargs):
        captured.update(kwargs)
        return {
            "intent_id": "intent-frontdoor-pm",
            "title": "frontdoor",
            "lane": "research",
            "raw_intent": "/tmp/raw.json",
            "requirement_ir": "/tmp/ir.json",
        }

    monkeypatch.setattr(pm_dispatch, "capture_entrypoint_raw_intent", fake_capture_entrypoint_raw_intent)
    monkeypatch.setattr(pm_dispatch, "print_intent_capture", lambda payload, entrypoint: captured.update({"entrypoint": entrypoint}))

    args = argparse.Namespace(
        text="必须先走前门研究，再进入 compile-request。",
        input_file="",
        sprint="sprint-frontdoor",
        workspace_root=str(tmp_path / "workspace"),
        paper=[],
        log=[],
        repo_context=[],
        target_system="solar-harness",
        dispatch_planner=False,
        dry_run=False,
    )

    assert pm_dispatch.cmd_compile_request(args) == 0
    assert captured["source_channel"] == "pm_compile_request"
    assert captured["sprint_id"] == "sprint-frontdoor"
    assert captured["role"] == "pm"
    assert captured["entrypoint"] == "pm_dispatch.compile-request"


def test_antigravity_rawintent_bridge_routes_to_gateway_then_consumer(monkeypatch):
    agy = _load_module("antigravity_frontdoor", ANTIGRAVITY_PATH)
    calls: list[list[str]] = []

    def fake_run(cmd, text=True, capture_output=True, timeout=None):
        calls.append(list(cmd))
        if str(cmd[1]).endswith("intent_gateway.py"):
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"intent_id": "intent-frontdoor-agy"}) + "\n",
                stderr="",
            )
        if str(cmd[1]).endswith("intent_consumer.py"):
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"results": [{"status": "consumed"}]}) + "\n",
                stderr="",
            )
        raise AssertionError(f"unexpected subprocess command: {cmd}")

    monkeypatch.setattr(agy.subprocess, "run", fake_run)

    assert agy.capture_raw_intent_entrypoint("Antigravity 入口必须和前门统一。") == 0
    assert len(calls) == 2
    assert str(calls[0][1]).endswith("intent_gateway.py")
    assert calls[0][2] == "capture"
    assert "antigravity_bridge" in calls[0]
    assert str(calls[1][1]).endswith("intent_consumer.py")
    assert calls[1][2] == "consume"
    assert "intent-frontdoor-agy" in calls[1]


def test_frontdoor_research_requirement_blocks_compile_without_artifact(tmp_path):
    env = _intent_env(tmp_path)
    capture = subprocess.run(
        [
            sys.executable,
            str(INTENT_GATEWAY),
            "capture",
            "--text",
            "前门研究未完成时，不允许直接进入 compile。",
            "--source-channel",
            "pm_dispatch",
            "--source-trust",
            "pm_dispatch",
            "--require-research-artifact",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    intent_id = json.loads(capture.stdout)["intent_id"]

    consume = subprocess.run(
        [sys.executable, str(INTENT_CONSUMER), "consume", "--intent-id", intent_id, "--json"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert consume.returncode == 1
    result = json.loads(consume.stdout)["results"][0]
    assert result["status"] == "blocked_missing_research_artifact"


def test_frontdoor_research_completion_still_requests_planner_handoff(tmp_path):
    env = _intent_env(tmp_path)
    capture = subprocess.run(
        [
            sys.executable,
            str(INTENT_GATEWAY),
            "capture",
            "--text",
            "前门研究完成后，应继续走 Planner handoff，而不是直接跳 Builder。",
            "--source-channel",
            "pm_dispatch",
            "--source-trust",
            "pm_dispatch",
            "--require-research-artifact",
            "--research-artifact",
            "/tmp/frontdoor-research.json",
            "--research-project-name",
            "需求研究-2026-05",
            "--research-conversation-id",
            "conv-frontdoor-003",
            "--research-source-url",
            "https://chatgpt.com/c/conv-frontdoor-003",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    intent_id = json.loads(capture.stdout)["intent_id"]

    consume = subprocess.run(
        [sys.executable, str(INTENT_CONSUMER), "consume", "--intent-id", intent_id, "--dry-run", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    result = json.loads(consume.stdout)["results"][0]
    assert result["planner_handoff"]["requested"] is True
    assert result["planner_handoff"]["reason"] == "trusted_channel"
