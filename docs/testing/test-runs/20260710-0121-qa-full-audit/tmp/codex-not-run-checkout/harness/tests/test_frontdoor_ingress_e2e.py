"""N4 E2E — frontdoor ingress convergence regression.

Asserts the three acceptance criteria for sprint
sprint-20260526-p0-browser-agent-chatgpt-frontdoor-requirement-research / N4:

1. Codex, PM pane, and Antigravity all hit the same frontdoor.
2. Planner handoff still occurs after research complete.
3. No ingress path bypasses research and jumps directly into compile.

Tests drive the real ``intent_gateway.py`` and ``intent_consumer.py`` CLIs
via subprocess (same pattern as ``test_intent_consumer.py``) so the verified
surface is the production call chain, not a stub.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "lib" / "intent_gateway.py"
CONSUMER = ROOT / "lib" / "intent_consumer.py"

INGRESS_CHANNELS = ("codex_bridge", "pm_dispatch", "antigravity")
TRUSTED_AUTO = ("codex_bridge", "pm_dispatch")
EXPLICIT_ONLY = ("antigravity",)


def _env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["SOLAR_HARNESS_DIR"] = str(ROOT)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"] = str(tmp_path / "workspace")
    return env


def _capture(env: dict[str, str], *, channel: str, text: str, research: dict | None = None,
             require_research: bool = False) -> str:
    cmd = [
        sys.executable, str(GATEWAY), "capture",
        "--text", text,
        "--source-channel", channel,
        "--source-trust", channel,
        "--json",
    ]
    if research is not None:
        cmd += [
            "--research-artifact", research["path"],
            "--research-project-name", research["project_name"],
            "--research-conversation-id", research["conversation_id"],
            "--research-source-url", research["source_url"],
        ]
    if require_research:
        cmd.append("--require-research-artifact")
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env, check=True)
    return json.loads(proc.stdout)["intent_id"]


def _consume(env: dict[str, str], intent_id: str, *, dry_run: bool = True,
             dispatch_planner: bool = False, expect_returncode: int = 0) -> dict:
    cmd = [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--json"]
    if dry_run:
        cmd.append("--dry-run")
    if dispatch_planner:
        cmd.append("--dispatch-planner")
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
    assert proc.returncode == expect_returncode, (
        f"consume exit={proc.returncode} stderr={proc.stderr[-400:]}"
    )
    return json.loads(proc.stdout)["results"][0]


# --------------------------------------------------------------------------- #
# Acceptance 1: all three ingresses route through the same frontdoor
# --------------------------------------------------------------------------- #

def test_three_ingresses_share_frontdoor_artifact_shape(tmp_path):
    """Codex, PM pane, and Antigravity all hit the same RawIntent gateway and
    emit the identical four-file shape under INTENTS_DIR/<intent_id>/."""
    env = _env(tmp_path)
    research = {
        "path": str(tmp_path / "research-artifact.json"),
        "project_name": "需求研究-2026-05",
        "conversation_id": "conv-shared-001",
        "source_url": "https://chatgpt.com/c/conv-shared-001",
    }
    intent_ids: dict[str, str] = {}
    for channel in INGRESS_CHANNELS:
        intent_ids[channel] = _capture(
            env,
            channel=channel,
            text=f"{channel} ingress 必须通过 frontdoor 完成需求研究后才能 compile。",
            research=research,
        )

    # All three intents materialize the exact same artifact set on disk.
    for channel, intent_id in intent_ids.items():
        base = tmp_path / "intents" / intent_id
        for filename in ("raw_intent.json", "rewritten_intent.json",
                         "requirement_ir.json", "requirement_trace.json"):
            assert (base / filename).exists(), (
                f"missing {filename} for ingress channel={channel}"
            )

    # Source channel is preserved per ingress, but the shared frontdoor metadata
    # (research_artifact, require_research_artifact routing hint) is identical.
    for channel, intent_id in intent_ids.items():
        raw = json.loads((tmp_path / "intents" / intent_id / "raw_intent.json").read_text())
        ir = json.loads((tmp_path / "intents" / intent_id / "requirement_ir.json").read_text())
        assert raw["source"]["channel"] == channel
        assert raw["routing_hints"]["require_research_artifact"] is True, (
            "Frontdoor MUST flip require_research_artifact to True whenever research metadata is provided"
        )
        assert raw["research"]["project_name"] == "需求研究-2026-05"
        assert raw["research"]["conversation_id"] == "conv-shared-001"
        assert ir["source_inputs"]["research_artifact"]["conversation_id"] == "conv-shared-001"
        assert ir["source_inputs"]["research_artifact"]["project_name"] == "需求研究-2026-05"


# --------------------------------------------------------------------------- #
# Acceptance 2: planner handoff still occurs after research complete
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("channel", TRUSTED_AUTO)
def test_planner_handoff_auto_dispatched_for_trusted_channel(tmp_path, channel):
    """Trusted channels (codex_bridge, pm_dispatch) auto-request planner handoff
    once research is complete — no explicit flag needed."""
    env = _env(tmp_path)
    research = {
        "path": str(tmp_path / f"research-{channel}.json"),
        "project_name": "需求研究-2026-05",
        "conversation_id": f"conv-{channel}",
        "source_url": f"https://chatgpt.com/c/conv-{channel}",
    }
    intent_id = _capture(
        env,
        channel=channel,
        text=f"{channel} 研究完成后必须接 Planner handoff，不允许停在 compile。",
        research=research,
    )
    result = _consume(env, intent_id, dry_run=True)
    handoff = result["planner_handoff"]
    assert handoff["requested"] is True, (
        f"trusted channel {channel} must auto-request planner handoff; reason={handoff.get('reason')}"
    )
    assert handoff["reason"] == "trusted_channel"
    assert handoff["source_channel"] == channel


@pytest.mark.parametrize("channel", EXPLICIT_ONLY)
def test_planner_handoff_reachable_for_untrusted_channel_via_explicit_flag(tmp_path, channel):
    """Antigravity (untrusted by default) MUST still be able to reach planner
    handoff by passing --dispatch-planner explicitly. This proves no ingress
    becomes a planner dead-end after research."""
    env = _env(tmp_path)
    research = {
        "path": str(tmp_path / f"research-{channel}.json"),
        "project_name": "需求研究-2026-05",
        "conversation_id": f"conv-{channel}",
        "source_url": f"https://chatgpt.com/c/conv-{channel}",
    }
    intent_id = _capture(
        env,
        channel=channel,
        text=f"{channel} ingress 必须能显式触发 Planner handoff。",
        research=research,
    )

    # Without --dispatch-planner: handoff is policy-skipped (untrusted_channel).
    skipped = _consume(env, intent_id, dry_run=True, dispatch_planner=False)["planner_handoff"]
    assert skipped["requested"] is False
    assert skipped["reason"] == "untrusted_channel"

    # With --dispatch-planner: handoff is requested via explicit_cli — the
    # planner chain remains reachable.
    forced = _consume(env, intent_id, dry_run=True, dispatch_planner=True)["planner_handoff"]
    assert forced["requested"] is True
    assert forced["reason"] == "explicit_cli"
    assert forced["source_channel"] == channel


# --------------------------------------------------------------------------- #
# Acceptance 3: no ingress path bypasses research and jumps to compile
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("channel", INGRESS_CHANNELS)
def test_consumer_blocks_compile_when_required_research_is_missing(tmp_path, channel):
    """For every ingress channel, capturing an intent with
    --require-research-artifact but no research metadata MUST block compile.
    This is the workflow-guard enforcement for D7 / REQ-GUARD-001."""
    env = _env(tmp_path)
    intent_id = _capture(
        env,
        channel=channel,
        text=f"{channel} 入口标记 require-research-artifact 但缺研究输入，必须被前门拦下。",
        research=None,
        require_research=True,
    )
    # consume must return non-zero exit and explicit block status — and the
    # compiled sprint package MUST NOT have been created.
    result = _consume(env, intent_id, dry_run=False, expect_returncode=1)
    assert result["ok"] is False
    assert result["status"] == "blocked_missing_research_artifact"
    sprint_id = result["sprint_id"]
    for ext in (".product-brief.md", ".prd.md", ".contract.md", ".task_graph.json"):
        artifact = tmp_path / "sprints" / f"{sprint_id}{ext}"
        assert not artifact.exists(), (
            f"compile artifact {artifact.name} must NOT exist for blocked ingress {channel}"
        )


@pytest.mark.parametrize("channel", INGRESS_CHANNELS)
def test_research_artifact_round_trips_to_compiled_package(tmp_path, channel):
    """For every ingress channel, providing real research metadata at capture
    time must surface that metadata in the compiled sprint package's
    requirement_ir, product-brief, and PRD. This proves the frontdoor research
    is actually consumed by compile (D5) rather than dropped between layers."""
    env = _env(tmp_path)
    research = {
        "path": str(tmp_path / f"research-{channel}.json"),
        "project_name": "需求研究-2026-05",
        "conversation_id": f"conv-frontdoor-{channel}",
        "source_url": f"https://chatgpt.com/c/conv-frontdoor-{channel}",
    }
    intent_id = _capture(
        env,
        channel=channel,
        text=f"{channel} 入口的研究 artifact 必须出现在 compiled package。",
        research=research,
    )
    result = _consume(env, intent_id, dry_run=False, expect_returncode=0)
    sprint_id = result["sprint_id"]
    assert result["status"] == "consumed", (
        f"{channel} ingest with research must consume successfully; got status={result['status']}"
    )

    ir = json.loads((tmp_path / "sprints" / f"{sprint_id}.requirement_ir.json").read_text())
    assert ir["source_inputs"]["research_artifact"]["conversation_id"] == research["conversation_id"]
    assert ir["source_inputs"]["research_artifact"]["project_name"] == research["project_name"]

    product_brief = (tmp_path / "sprints" / f"{sprint_id}.product-brief.md").read_text()
    prd = (tmp_path / "sprints" / f"{sprint_id}.prd.md").read_text()
    for doc_name, doc in (("product-brief.md", product_brief), ("prd.md", prd)):
        assert "## Research Artifact Inputs" in doc, (
            f"{channel}: {doc_name} missing Research Artifact Inputs section"
        )
        assert research["conversation_id"] in doc, (
            f"{channel}: {doc_name} did not surface conversation_id"
        )


# --------------------------------------------------------------------------- #
# Cross-cutting: no ingress can produce a compiled package without going
# through the gateway first (the gateway is the only producer of intent_id).
# --------------------------------------------------------------------------- #

def test_consumer_refuses_unknown_intent_id(tmp_path):
    """The consumer must fail when handed an intent_id that was never created
    by the gateway. This proves there is no side-door into compile that
    skips RawIntent capture."""
    env = _env(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume",
         "--intent-id", "intent-does-not-exist-deadbeef", "--json"],
        text=True, capture_output=True, env=env,
    )
    assert proc.returncode != 0
    combined = (proc.stderr or "") + (proc.stdout or "")
    assert "intent artifacts incomplete" in combined
