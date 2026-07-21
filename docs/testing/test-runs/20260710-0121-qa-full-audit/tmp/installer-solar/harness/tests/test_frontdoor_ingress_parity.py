#!/usr/bin/env python3
"""Regression tests for unified frontdoor ingress routing."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOLAR_HARNESS = ROOT / "solar-harness.sh"
CHAIN_WATCHER = ROOT / "chain-watcher.sh"
PM_DISPATCH = ROOT / "tools" / "pm_dispatch.py"


def _function_body(script: Path, name: str) -> str:
    text = script.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(name)}\(\) \{{\n(.*?)\n\}}", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    assert match, f"function {name} not found in {script}"
    return match.group(1)


def test_cli_intake_uses_intent_consumer_instead_of_legacy_new_sprint_path():
    body = _function_body(SOLAR_HARNESS, "intake_request")
    assert 'intent_gateway.py" capture' in body
    assert 'intent_consumer.py" consume' in body
    consumer_idx = body.index('intent_consumer.py" consume')
    fallback_idx = body.index('out=$(new_sprint "$req" 2>&1)')
    assert consumer_idx < fallback_idx


def test_chain_watcher_routes_codex_ingress_through_gateway_and_consumer():
    body = _function_body(CHAIN_WATCHER, "capture_codex_raw_intent_file")
    assert 'intent_gateway.py" capture' in body
    assert 'intent_consumer.py" consume' in body


def test_pm_dispatch_routes_submit_entrypoint_through_gateway_and_consumer():
    text = PM_DISPATCH.read_text(encoding="utf-8")
    assert 'intent_gateway.py"),\n        "capture"' in text
    assert 'intent_consumer.py"),\n            "consume"' in text
