import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = (Path(__file__).resolve().parents[2] / 'harness')
GATEWAY = ROOT / "lib" / "intent_gateway.py"
CONSUMER = ROOT / "lib" / "intent_consumer.py"
REPO = ROOT.parent


def test_default_artifact_dirs_follow_runtime_harness(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime-harness"
    monkeypatch.setenv("HARNESS_DIR", str(runtime))
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(tmp_path / "stale-harness"))
    monkeypatch.delenv("SOLAR_INTENT_GATEWAY_DIR", raising=False)
    monkeypatch.delenv("SOLAR_HARNESS_SPRINTS_DIR", raising=False)

    spec = __import__("importlib.util").util.spec_from_file_location(
        "intent_consumer_runtime_defaults", CONSUMER
    )
    assert spec and spec.loader
    consumer = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(consumer)

    assert consumer.HARNESS_DIR == runtime
    assert consumer.INTENTS_DIR == runtime / "intents"
    assert consumer.SPRINTS_DIR == runtime / "sprints"


def _env(tmp_path):
    env = dict(os.environ)
    env["SOLAR_HARNESS_DIR"] = str(ROOT)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"] = str(tmp_path / "workspace")
    return env


def _capture(env, text="新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。", channel="test"):
    cap = subprocess.run(
        [
            sys.executable,
            str(GATEWAY),
            "capture",
            "--text",
            text,
            "--source-channel",
            channel,
            "--source-trust",
            channel,
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    return json.loads(cap.stdout)["intent_id"]


def test_consumer_compiles_rawintent_to_sprint_package(tmp_path):
    env = _env(tmp_path)
    intent_id = _capture(env)

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    result = payload["results"][0]
    sprint_id = result["sprint_id"]

    assert result["status"] == "consumed"
    assert result["direct_pane_dispatch"] is False
    assert result["planner_runtime_submit"] is False
    assert result["planner_handoff"]["requested"] is False
    assert result["planner_handoff"]["reason"] == "untrusted_channel"
    assert (tmp_path / "intents" / intent_id / "consumer.json").exists()
    assert (tmp_path / "intents" / intent_id / "binding.json").exists()
    assert (tmp_path / "sprints" / f"{sprint_id}.status.json").exists()
    assert (tmp_path / "sprints" / f"{sprint_id}.product-brief.md").exists()
    assert (tmp_path / "sprints" / f"{sprint_id}.prd.md").exists()
    assert (tmp_path / "sprints" / f"{sprint_id}.contract.md").exists()
    assert (tmp_path / "sprints" / f"{sprint_id}.task_graph.json").exists()
    ir = json.loads(
        (tmp_path / "sprints" / f"{sprint_id}.requirement_ir.json").read_text(encoding="utf-8")
    )
    workspace_ir = json.loads(
        (tmp_path / "workspace" / ".pm" / "requirement_ir.json").read_text(encoding="utf-8")
    )
    trace = json.loads(
        (tmp_path / "sprints" / f"{sprint_id}.requirement_trace.json").read_text(encoding="utf-8")
    )
    assert ir["intent_id"] == intent_id
    assert ir["sprint_id"] == sprint_id
    assert ir["id"] == workspace_ir["id"]
    assert ir["requirements"] == workspace_ir["requirements"]
    assert len(ir["requirements"]) >= 4
    assert ir["requirements"][0]["source_text"] != "N/A"
    assert trace["requirement_ir_id"] == ir["id"]
    assert len(trace["items"]) == len(ir["requirements"])


def test_consumer_preserves_direct_answer_route_without_dispatchable_dag(tmp_path):
    env = _env(tmp_path)
    intent_id = _capture(
        env,
        text="explain photosynthesis to a 5 year old",
        channel="test",
    )

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    result = json.loads(proc.stdout)["results"][0]
    sprint_id = result["sprint_id"]
    requirement_ir = json.loads(
        (tmp_path / "sprints" / f"{sprint_id}.requirement_ir.json").read_text(encoding="utf-8")
    )
    graph = json.loads(
        (tmp_path / "sprints" / f"{sprint_id}.task_graph.json").read_text(encoding="utf-8")
    )

    assert requirement_ir["request_type"] == "direct_answer"
    assert requirement_ir["planner_hints"]["preferred_outcome"] == "direct_answer"
    assert requirement_ir["planner_hints"]["runtime_handoff_allowed"] is False
    assert graph["proposal_only"] is True
    assert graph["runtime_handoff_allowed"] is False
    assert result["planner_handoff"]["requested"] is False


def test_consumer_accepts_native_intent_ir_bundle_without_rewritten_artifact(tmp_path):
    env = _env(tmp_path)
    intent_id = "intent-native-bundle"
    base = tmp_path / "intents" / intent_id
    semantic_dir = base / "intent"
    semantic_dir.mkdir(parents=True)
    fixture_dir = (
        REPO
        / "harness"
        / "metadata"
        / "2-intent compiler output"
        / "requirement-compiler-input-fixtures"
        / "01-research-scientific-reproducibility"
    )
    requirement_dir = (
        REPO
        / "harness"
        / "metadata"
        / "3-requirements compiler output"
        / "native-intent-ir-compiler-evaluation-20260825"
        / "01-research-scientific-reproducibility"
    )
    intent_ir = json.loads((fixture_dir / "intent_ir.json").read_text(encoding="utf-8"))
    requirement_ir = json.loads((requirement_dir / "requirement_ir.json").read_text(encoding="utf-8"))
    raw = {
        "schema_version": "solar.raw_intent.v1",
        "intent_id": intent_id,
        "source": {"channel": "test", "actor": "user"},
        "raw": {
            "text": (
                "Investigate the main causes of irreproducible results in machine-learning "
                "research and propose five testable improvements."
            )
        },
        "routing_hints": {"allow_autodispatch": False},
        "trust": {"source_trust": "test"},
    }
    (base / "raw_intent.json").write_text(json.dumps(raw), encoding="utf-8")
    (semantic_dir / "intent_ir.json").write_text(json.dumps(intent_ir), encoding="utf-8")
    (base / "requirement_ir.json").write_text(json.dumps(requirement_ir), encoding="utf-8")

    assert not (base / "rewritten_intent.json").exists()
    proc = subprocess.run(
        [
            sys.executable,
            str(CONSUMER),
            "consume",
            "--intent-id",
            intent_id,
            "--sprint-id",
            "sprint-native-bundle",
            "--dry-run",
            "--no-auto-dispatch-planner",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )

    result = json.loads(proc.stdout)["results"][0]
    assert result["status"] == "dry_run"
    assert result["sprint_id"] == "sprint-native-bundle"
    assert result["planner_handoff"]["reason"] == "auto_dispatch_disabled"


def test_cli_intake_preserves_research_when_software_artifacts_are_explicit_non_goals(tmp_path):
    env = _env(tmp_path)
    prompt = (
        "Create a deep research report comparing GitHub Copilot, Cursor, and Claude Code. "
        "Use current official and independent sources, distinguish contradictory evidence, "
        "and cite every material claim. Deliver Markdown, not a CLI or JSON tool."
    )
    intent_id = _capture(env, text=prompt, channel="cli_intake")

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    result = json.loads(proc.stdout)["results"][0]
    sprint_id = result["sprint_id"]
    raw = json.loads(
        (tmp_path / "intents" / intent_id / "raw_intent.json").read_text(encoding="utf-8")
    )
    ir = json.loads(
        (tmp_path / "sprints" / f"{sprint_id}.requirement_ir.json").read_text(encoding="utf-8")
    )
    graph = json.loads(
        (tmp_path / "sprints" / f"{sprint_id}.task_graph.json").read_text(encoding="utf-8")
    )
    roles = {node["logical_operator"] for node in graph["nodes"]}

    assert raw["routing_hints"]["mode"] == "research"
    assert ir["request_type"] == "research"
    assert {"ResearchScout", "ResearchSynthesizer"}.issubset(roles)


def test_consumer_dry_run_marks_trusted_pm_dispatch_for_planner_handoff(tmp_path):
    env = _env(tmp_path)
    intent_id = _capture(env, text="可信 PM 入口应该自动进入 Planner handoff。", channel="pm_dispatch")

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--dry-run", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    result = json.loads(proc.stdout)["results"][0]
    handoff = result["planner_handoff"]
    assert handoff["requested"] is True
    assert handoff["reason"] == "trusted_channel"
    assert handoff["source_channel"] == "pm_dispatch"


def test_consumer_codex_runtime_suppresses_trusted_pm_operator_handoff(tmp_path):
    env = _env(tmp_path)
    env["SOLAR_PANE_RUNTIME"] = "codex"
    intent_id = _capture(env, text="Codex runtime should use the cockpit planner pane.", channel="pm_dispatch")

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--dry-run", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    handoff = json.loads(proc.stdout)["results"][0]["planner_handoff"]
    assert handoff["requested"] is False
    assert handoff["suppressed_requested"] is True
    assert handoff["suppressed_reason"] == "trusted_channel"
    assert handoff["reason"] == "codex_pane_runtime_uses_coordinator_planner_pane"


def test_consumer_codex_runtime_suppresses_explicit_pm_operator_handoff(tmp_path):
    env = _env(tmp_path)
    env["SOLAR_PANE_RUNTIME"] = "codex"
    intent_id = _capture(env, text="Even explicit CLI handoff must not launch Claude under Codex.", channel="test")

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--dry-run", "--dispatch-planner", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    handoff = json.loads(proc.stdout)["results"][0]["planner_handoff"]
    assert handoff["requested"] is False
    assert handoff["suppressed_requested"] is True
    assert handoff["suppressed_reason"] == "explicit_cli"
    assert handoff["reason"] == "codex_pane_runtime_uses_coordinator_planner_pane"


def test_consumer_codex_runtime_can_opt_into_pm_operator_handoff(tmp_path):
    env = _env(tmp_path)
    env["SOLAR_PANE_RUNTIME"] = "codex"
    env["SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH"] = "1"
    intent_id = _capture(env, text="Codex runtime operator dispatch remains explicit opt-in.", channel="pm_dispatch")

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--dry-run", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    handoff = json.loads(proc.stdout)["results"][0]["planner_handoff"]
    assert handoff["requested"] is True
    assert handoff["reason"] == "trusted_channel"
    assert "suppressed_requested" not in handoff


def test_consumer_no_auto_dispatch_planner_disables_trusted_handoff(tmp_path):
    env = _env(tmp_path)
    intent_id = _capture(env, text="显式关闭 auto handoff 时只编译。", channel="pm_dispatch")

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--dry-run", "--no-auto-dispatch-planner", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    handoff = json.loads(proc.stdout)["results"][0]["planner_handoff"]
    assert handoff["requested"] is False
    assert handoff["reason"] == "auto_dispatch_disabled"


def test_consumer_status_lists_pending(tmp_path):
    env = _env(tmp_path)
    subprocess.run(
        [sys.executable, str(GATEWAY), "capture", "--text", "pending intent", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "status", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["pending_count"] == 1


def test_consumer_blocks_when_research_artifact_is_required_but_missing(tmp_path):
    env = _env(tmp_path)
    cap = subprocess.run(
        [
            sys.executable,
            str(GATEWAY),
            "capture",
            "--text",
            "前门研究必须存在，否则不得 compile-ready。",
            "--require-research-artifact",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    intent_id = json.loads(cap.stdout)["intent_id"]
    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--json"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 1
    result = json.loads(proc.stdout)["results"][0]
    assert result["ok"] is False
    assert result["status"] == "blocked_missing_research_artifact"


def test_consumer_injects_research_artifact_refs_into_compiled_package(tmp_path):
    env = _env(tmp_path)
    cap = subprocess.run(
        [
            sys.executable,
            str(GATEWAY),
            "capture",
            "--text",
            "通过 Browser Agent 前门研究后再编译 requirement package。",
            "--source-channel",
            "pm_dispatch",
            "--source-trust",
            "pm_dispatch",
            "--research-artifact",
            "/tmp/frontdoor-research.json",
            "--research-project-name",
            "需求研究-2026-05",
            "--research-conversation-id",
            "conv-frontdoor-002",
            "--research-source-url",
            "https://chatgpt.com/c/conv-frontdoor-002",
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    intent_id = json.loads(cap.stdout)["intent_id"]
    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    result = json.loads(proc.stdout)["results"][0]
    sprint_id = result["sprint_id"]
    ir = json.loads(
        (tmp_path / "sprints" / f"{sprint_id}.requirement_ir.json").read_text(encoding="utf-8")
    )
    product_brief = (
        tmp_path / "sprints" / f"{sprint_id}.product-brief.md"
    ).read_text(encoding="utf-8")
    prd = (tmp_path / "sprints" / f"{sprint_id}.prd.md").read_text(encoding="utf-8")
    assert ir["source_inputs"]["research_artifact"]["path"] == "/tmp/frontdoor-research.json"
    assert "## Research Artifact Inputs" in product_brief
    assert "conv-frontdoor-002" in product_brief
    assert "## Research Artifact Inputs" in prd
