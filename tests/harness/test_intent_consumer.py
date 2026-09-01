import json
import os
import subprocess
import sys
import importlib.util
import datetime as dt
from pathlib import Path

ROOT = (Path(__file__).resolve().parents[2] / 'harness')
GATEWAY = ROOT / "lib" / "intent_gateway.py"
CONSUMER = ROOT / "lib" / "intent_consumer.py"
REPO = ROOT.parent


def _env(tmp_path):
    env = dict(os.environ)
    env["SOLAR_HARNESS_DIR"] = str(ROOT)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"] = str(tmp_path / "workspace")
    return env


def _capture(env, text="新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。", channel="test"):
    workspace = Path(env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"])
    workspace.mkdir(parents=True, exist_ok=True)
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
            "--repo",
            str(workspace),
            "--cwd",
            str(workspace),
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


def test_dashboard_dry_run_selects_native_elastic_planner_not_legacy_planner(tmp_path):
    env = _env(tmp_path)
    intent_id = _capture(
        env,
        text="Explain photosynthesis clearly.",
        channel="dashboard",
    )

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--dry-run", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    result = json.loads(proc.stdout)["results"][0]

    assert result["planner_handoff"]["requested"] is True
    assert result["planner_handoff"]["planner_kind"] == "native_elastic_planner"
    assert result["cmd"][result["cmd"].index("--role") + 1] == "elastic-planner"
    assert "--operator" not in result["cmd"]
    assert "compile-request" not in result["cmd"]


def test_dashboard_native_intake_claims_before_planning_without_rough_graph(tmp_path, monkeypatch):
    env = _env(tmp_path)
    binding_harness = tmp_path / "binding-harness"
    binding_harness.mkdir()
    env["SOLAR_WORKSPACE_BINDING_HARNESS_DIR"] = str(binding_harness)
    intent_id = _capture(env, text="Explain photosynthesis clearly.", channel="dashboard")
    intent_bundle = tmp_path / "intents" / intent_id
    semantic_dir = intent_bundle / "intent"
    semantic_dir.mkdir()
    (semantic_dir / "intent_ir.json").write_text(
        json.dumps(
            {
                "schema_version": "solar.intent_ir.v3",
                "intent_ir_id": f"intent-ir-{intent_id}",
                "goals": [
                    {
                        "goal_id": "G1",
                        "statement": "Explain photosynthesis clearly.",
                        "source_spans": [[0, 31]],
                    }
                ],
                "outcomes": [
                    {
                        "outcome_id": "D1",
                        "class": "information",
                        "description": "A clear direct explanation.",
                        "source_spans": [[0, 31]],
                    }
                ],
                "constraints": [],
                "ambiguities": [],
                "conflicts": [],
                "unknowns": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for key, value in env.items():
        if key.startswith("SOLAR_") or key == "HARNESS_DIR":
            monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("intent_consumer_native_test", CONSUMER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    import workspace_binding

    workspace_binding.bind_active_workspace(
        binding_harness,
        Path(env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"]),
        source="test",
    )
    module.submit_elastic_planner = lambda sprint_id, requirement_ir_path: {
        "status": "submitted",
        "task_id": "pm-native-test",
    }

    result = module.consume_one(intent_id)
    sid = result["sprint_id"]
    captured_requirement = json.loads(
        (tmp_path / "intents" / intent_id / "requirement_ir.json").read_text(
            encoding="utf-8"
        )
    )
    bound_requirement = json.loads(
        (tmp_path / "sprints" / f"{sid}.requirement_ir.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["status"] == "consumed"
    assert result["planner_handoff"]["planner_kind"] == "native_elastic_planner"
    assert not (tmp_path / "sprints" / f"{sid}.task_graph.json").exists()
    assert not (tmp_path / "sprints" / f"{sid}.prd.md").exists()
    owner = json.loads(
        (tmp_path / "sprints" / sid / "elastic-planner" / "owner.json").read_text(encoding="utf-8")
    )
    status = json.loads(
        (tmp_path / "sprints" / f"{sid}.status.json").read_text(encoding="utf-8")
    )
    assert owner["state"] == "claimed"
    assert status["phase"] == "elastic_planning"
    assert "photosynthesis" in status["title"].lower()
    assert captured_requirement["id"] == f"requirement-ir-{intent_id}"
    assert bound_requirement["id"] == captured_requirement["id"]
    assert [row["id"] for row in bound_requirement["requirements"]] == ["REQ-001"]
    assert bound_requirement["requirements"][0]["source_text"] == "Explain photosynthesis clearly."
    from elastic_planner import requirement_ir_id, requirements

    assert requirement_ir_id(bound_requirement) == captured_requirement["id"]
    assert [row["id"] for row in requirements(bound_requirement)] == ["REQ-001"]
    authority_path = tmp_path / "sprints" / f"{sid}.workspace_authority.json"
    authority = workspace_binding.verify_sprint_workspace_authority(
        authority_path,
        sprints_dir=tmp_path / "sprints",
        harness_dir=binding_harness,
    )
    assert authority["workspace_root"] == str(
        Path(env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"]).resolve()
    )
    assert set(authority["inputs"]) == {"raw_intent", "intent_ir", "requirement_ir"}
    assert authority["cwd"]["effective_relative"] == "."


def test_elastic_planner_failed_capacity_record_allows_bounded_resubmission(
    tmp_path,
    monkeypatch,
):
    env = _env(tmp_path)
    for key, value in env.items():
        if key.startswith("SOLAR_") or key == "HARNESS_DIR":
            monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("intent_consumer_elastic_retry_test", CONSUMER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.HARNESS_DIR = tmp_path / "harness"
    module.SPRINTS_DIR = tmp_path / "sprints"
    inbox = module.HARNESS_DIR / "run" / "pm-inbox"
    inbox.mkdir(parents=True)
    sprint_id = "sprint-third-request-retry"
    requirement = module.SPRINTS_DIR / f"{sprint_id}.requirement_ir.json"
    requirement.parent.mkdir(parents=True)
    requirement.write_text('{"schema_version":"solar.requirement_ir.v2"}\n', encoding="utf-8")
    if str(ROOT / "lib") not in sys.path:
        sys.path.insert(0, str(ROOT / "lib"))
    import elastic_planner_runtime

    elastic_planner_runtime.claim_owner(
        module.SPRINTS_DIR,
        sprint_id,
        "intent-third-request-retry",
        requirement,
    )
    failed_task_id = "pm-both-elastic-operators-busy"
    (inbox / f"{failed_task_id}.json").write_text(
        json.dumps(
            {
                "task_id": failed_task_id,
                "sprint_id": sprint_id,
                "node_id": "elastic-planner",
                "closeout_kind": "elastic_planner",
                "status": "failed_backpressure",
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def successful_retry(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="task_id = pm-elastic-retry\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", successful_retry)
    result = module.submit_elastic_planner(sprint_id, requirement)

    assert result["status"] == "submitted"
    assert result["task_id"] == "pm-elastic-retry"
    assert len(calls) == 1
    owner = json.loads(
        (module.SPRINTS_DIR / sprint_id / "elastic-planner" / "owner.json").read_text(
            encoding="utf-8"
        )
    )
    assert owner["state"] == "submitted"
    assert owner["planner_attempts"][-1]["prior_failed_task_ids"] == [failed_task_id]

    active = {
        "task_id": "pm-elastic-retry",
        "sprint_id": sprint_id,
        "node_id": "elastic-planner",
        "closeout_kind": "elastic_planner",
        "status": "submitted",
    }
    (inbox / "pm-elastic-retry.json").write_text(json.dumps(active), encoding="utf-8")
    deduped = module.submit_elastic_planner(sprint_id, requirement)
    assert deduped["status"] == "already_submitted"
    assert len(calls) == 1


def test_elastic_planner_terminal_failure_is_not_auto_resubmitted(tmp_path, monkeypatch):
    env = _env(tmp_path)
    for key, value in env.items():
        if key.startswith("SOLAR_") or key == "HARNESS_DIR":
            monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("intent_consumer_elastic_terminal_test", CONSUMER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.SPRINTS_DIR = tmp_path / "sprints"
    sprint_id = "sprint-terminal-no-resubmit"
    requirement = module.SPRINTS_DIR / f"{sprint_id}.requirement_ir.json"
    requirement.parent.mkdir(parents=True)
    requirement.write_text(
        json.dumps(
            {
                "id": "requirement-ir-terminal-no-resubmit",
                "requirements": [{"id": "REQ-001", "statement": "Answer the request."}],
            }
        ),
        encoding="utf-8",
    )
    if str(ROOT / "lib") not in sys.path:
        sys.path.insert(0, str(ROOT / "lib"))
    import elastic_planner_runtime

    elastic_planner_runtime.claim_owner(
        module.SPRINTS_DIR,
        sprint_id,
        "intent-terminal-no-resubmit",
        requirement,
    )
    elastic_planner_runtime.update_owner(
        module.SPRINTS_DIR,
        sprint_id,
        state="failed",
        planner_task_id="pm-terminal-failed",
        failure={
            "task_id": "pm-terminal-failed",
            "status": "failed_contract_closeout",
            "retryable": False,
        },
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("terminal Planner failure was resubmitted")
        ),
    )

    result = module.submit_elastic_planner(sprint_id, requirement)

    assert result["status"] == "terminal_failed"
    assert result["task_id"] == "pm-terminal-failed"


def test_fresh_capacity_failure_is_projected_and_remains_retryable(tmp_path, monkeypatch):
    env = _env(tmp_path)
    for key, value in env.items():
        if key.startswith("SOLAR_") or key == "HARNESS_DIR":
            monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("intent_consumer_elastic_capacity_test", CONSUMER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.HARNESS_DIR = tmp_path / "harness"
    module.SPRINTS_DIR = tmp_path / "sprints"
    sprint_id = "sprint-fresh-capacity-retry"
    task_id = "pm-fresh-capacity-retry"
    requirement = module.SPRINTS_DIR / f"{sprint_id}.requirement_ir.json"
    requirement.parent.mkdir(parents=True)
    requirement.write_text(
        json.dumps(
            {
                "id": "requirement-ir-fresh-capacity-retry",
                "requirements": [{"id": "REQ-001", "statement": "Answer the request."}],
            }
        ),
        encoding="utf-8",
    )
    if str(ROOT / "lib") not in sys.path:
        sys.path.insert(0, str(ROOT / "lib"))
    import elastic_planner_runtime

    elastic_planner_runtime.claim_owner(
        module.SPRINTS_DIR,
        sprint_id,
        "intent-fresh-capacity-retry",
        requirement,
    )
    elastic_planner_runtime.initialize_status(
        module.SPRINTS_DIR,
        sprint_id,
        "intent-fresh-capacity-retry",
    )

    def capacity_failure(cmd, **_kwargs):
        inbox = module.HARNESS_DIR / "run" / "pm-inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / f"{task_id}.json").write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "sprint_id": sprint_id,
                    "node_id": "elastic-planner",
                    "closeout_kind": "elastic_planner",
                    "status": "failed_backpressure",
                    "failure_reason": "bounded Planner workers are busy",
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="busy")

    monkeypatch.setattr(module.subprocess, "run", capacity_failure)
    result = module.submit_elastic_planner(sprint_id, requirement)

    assert result["status"] == "retryable_failure"
    assert result["task_id"] == task_id
    owner = json.loads(
        elastic_planner_runtime.owner_path(module.SPRINTS_DIR, sprint_id).read_text(
            encoding="utf-8"
        )
    )
    status = json.loads(
        (module.SPRINTS_DIR / f"{sprint_id}.status.json").read_text(encoding="utf-8")
    )
    assert owner["state"] == "retryable_failure"
    assert owner["failure"]["retryable"] is True
    assert status["status"] == "active"


def test_retryable_planner_capacity_failure_is_reconciled_after_backoff(
    tmp_path, monkeypatch
):
    env = _env(tmp_path)
    for key, value in env.items():
        if key.startswith("SOLAR_") or key == "HARNESS_DIR":
            monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location(
        "intent_consumer_elastic_reconciler_test", CONSUMER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.HARNESS_DIR = tmp_path / "harness"
    module.SPRINTS_DIR = tmp_path / "sprints"
    sprint_id = "sprint-capacity-reconciler"
    requirement = module.SPRINTS_DIR / f"{sprint_id}.requirement_ir.json"
    requirement.parent.mkdir(parents=True)
    requirement.write_text(
        json.dumps(
            {
                "id": "requirement-ir-capacity-reconciler",
                "requirements": [{"id": "REQ-001", "statement": "Research it."}],
            }
        ),
        encoding="utf-8",
    )
    if str(ROOT / "lib") not in sys.path:
        sys.path.insert(0, str(ROOT / "lib"))
    import elastic_planner_runtime

    elastic_planner_runtime.claim_owner(
        module.SPRINTS_DIR,
        sprint_id,
        "intent-capacity-reconciler",
        requirement,
    )
    elastic_planner_runtime.update_owner(
        module.SPRINTS_DIR,
        sprint_id,
        state="retryable_failure",
        planner_task_id="pm-capacity-first",
        failure={
            "task_id": "pm-capacity-first",
            "status": "failed_no_dispatchable_operator",
            "retryable": True,
            "failed_at": "2026-08-28T12:00:00Z",
        },
    )
    calls = []

    def submit(sid, path):
        calls.append((sid, path))
        return {"status": "submitted", "task_id": "pm-capacity-second"}

    monkeypatch.setattr(module, "submit_elastic_planner", submit)
    result = module.reconcile_retryable_elastic_planners(
        now=dt.datetime(2026, 8, 28, 12, 1, tzinfo=dt.timezone.utc)
    )

    assert result["ok"] is True
    assert result["attempted"] == 1
    assert calls == [(sprint_id, requirement.resolve())]
    assert result["rows"][-1]["status"] == "submitted"


def test_retryable_planner_capacity_failure_respects_backoff(tmp_path, monkeypatch):
    env = _env(tmp_path)
    for key, value in env.items():
        if key.startswith("SOLAR_") or key == "HARNESS_DIR":
            monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location(
        "intent_consumer_elastic_backoff_test", CONSUMER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.HARNESS_DIR = tmp_path / "harness"
    module.SPRINTS_DIR = tmp_path / "sprints"
    sprint_id = "sprint-capacity-backoff"
    requirement = module.SPRINTS_DIR / f"{sprint_id}.requirement_ir.json"
    requirement.parent.mkdir(parents=True)
    requirement.write_text(
        json.dumps(
            {
                "id": "requirement-ir-capacity-backoff",
                "requirements": [{"id": "REQ-001", "statement": "Research it."}],
            }
        ),
        encoding="utf-8",
    )
    if str(ROOT / "lib") not in sys.path:
        sys.path.insert(0, str(ROOT / "lib"))
    import elastic_planner_runtime

    elastic_planner_runtime.claim_owner(
        module.SPRINTS_DIR,
        sprint_id,
        "intent-capacity-backoff",
        requirement,
    )
    elastic_planner_runtime.update_owner(
        module.SPRINTS_DIR,
        sprint_id,
        state="retryable_failure",
        planner_task_id="pm-capacity-first",
        failure={
            "task_id": "pm-capacity-first",
            "status": "failed_no_dispatchable_operator",
            "retryable": True,
            "failed_at": "2026-08-28T12:00:00Z",
        },
    )
    monkeypatch.setattr(
        module,
        "submit_elastic_planner",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Planner retried before backoff elapsed")
        ),
    )

    result = module.reconcile_retryable_elastic_planners(
        now=dt.datetime(2026, 8, 28, 12, 0, 2, tzinfo=dt.timezone.utc)
    )

    assert result["ok"] is True
    assert result["attempted"] == 0
    assert result["rows"] == [
        {
            "sprint_id": sprint_id,
            "status": "backoff",
            "failure_status": "failed_no_dispatchable_operator",
            "retry_in_seconds": 3.0,
        }
    ]


def test_elastic_planner_input_preflight_rejects_missing_identity_and_requirements(
    tmp_path,
    monkeypatch,
):
    env = _env(tmp_path)
    intent_id = _capture(env, text="Explain photosynthesis clearly.", channel="dashboard")
    for key, value in env.items():
        if key.startswith("SOLAR_") or key == "HARNESS_DIR":
            monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("intent_consumer_elastic_preflight_test", CONSUMER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def bind_invalid(cmd, **kwargs):
        if "intent_gateway.py" in " ".join(map(str, cmd)) and "bind" in cmd:
            sid = cmd[cmd.index("--sprint-id") + 1]
            path = module.SPRINTS_DIR / f"{sid}.requirement_ir.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"schema_version":"solar.requirement_ir.v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        raise AssertionError("Planner submission ran after incompatible input")

    monkeypatch.setattr(module.subprocess, "run", bind_invalid)
    result = module.consume_one(intent_id)

    assert result["status"] == "planner_input_invalid"
    assert result["planner_input_preflight"]["error"]["code"] == "ELASTIC_PLANNER_INPUT_INCOMPATIBLE"
    assert not (
        module.SPRINTS_DIR
        / result["sprint_id"]
        / "elastic-planner"
        / "owner.json"
    ).exists()


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
