from pathlib import Path

import pytest


def test_diagnose_missing_runtime_marks_needs_recover(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry = pd.PaneHygieneRegistry(str(tmp_path / "pane-hygiene.json"))
    registry.register_pane("solar-harness-lab:0.2", "builder")

    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯ Try \"help\"\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "worker_runtime_not_running")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    finding = pd.diagnose_pane("solar-harness-lab:0.2", "Builder | idle/no active sprint", registry)

    assert finding["status"] == "runtime_missing"
    assert finding["desired_hygiene_state"] == "needs_recover"
    assert finding["recommended_action"] == "mark_needs_recover"


def test_diagnose_idle_huge_context_requires_respawn(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry = pd.PaneHygieneRegistry(str(tmp_path / "pane-hygiene.json"))
    registry.register_pane("solar-harness:0.0", "pm")

    monkeypatch.setattr(pd, "CONTEXT_TOKEN_RESPAWN_THRESHOLD", 100)
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n581,000 tokens\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    finding = pd.diagnose_pane("solar-harness:0.0", "PM", registry)

    assert finding["status"] == "respawn_required"
    assert finding["reason"] == "idle_huge_context"
    assert finding["desired_hygiene_state"] == "needs_respawn"


def test_repair_all_transitions_registry_without_respawn(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.3", "builder")

    monkeypatch.setattr(pd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.3", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯ half typed task\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "unsubmitted_prompt_residue")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: False)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.3")

    assert result["ok"] is True
    assert result["repairs"][0]["to"] == "dirty"
    assert entry.state == pd.PaneState.dirty


def test_repair_all_skips_protected_panes_by_default(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness:0.0", "pm")

    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness:0.0", "PM")])
    monkeypatch.setattr(pd, "CONTEXT_TOKEN_RESPAWN_THRESHOLD", 100)
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n581,000 tokens\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness:0.0")

    assert result["repairs"][0]["skipped"] is True
    assert result["repairs"][0]["skip_reason"] == "protected_pane"
    assert entry.state == pd.PaneState.clean


def test_repair_all_does_not_downgrade_more_severe_state(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.0", "builder", initial_state=pd.PaneState.needs_respawn)

    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.0", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "pane_recover_cooldown:send_failed_retry_later")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.0")

    assert result["repairs"][0]["skipped"] is True
    assert result["repairs"][0]["skip_reason"] == "existing_state_more_severe"
    assert entry.state == pd.PaneState.needs_respawn


def test_repair_all_clears_stale_needs_respawn_when_pane_is_clean(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.0", "builder", initial_state=pd.PaneState.needs_respawn)

    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.0", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.0")

    assert result["repairs"][0]["to"] == "clean"
    assert result["repairs"][0]["result"]["ok"] is True
    assert entry.state == pd.PaneState.clean


def test_repair_all_clears_idle_recover_cooldown_even_from_needs_respawn(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness:0.3", "evaluator", initial_state=pd.PaneState.needs_respawn)
    cooldown_path = tmp_path / "run" / "graph-dispatch-pane-cooldowns.json"
    cooldown_path.parent.mkdir(parents=True, exist_ok=True)
    cooldown_path.write_text(
        '{"solar-harness:0.3": {"reason": "pane_recover_cooldown:clear_gate_failed:exhausted"}}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(pd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness:0.3", "Evaluator")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "pane_recover_cooldown:clear_gate_failed:exhausted")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False, include_protected=True)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness:0.3")
    cooldowns = cooldown_path.read_text(encoding="utf-8")

    assert result["repairs"][0]["to"] == "clean"
    assert result["repairs"][0]["cooldown_cleared"] is True
    assert result["repairs"][0]["result"]["ok"] is True
    assert entry.state == pd.PaneState.clean
    assert "solar-harness:0.3" not in cooldowns


def test_repair_all_clears_stale_title_active_cooldown_when_idle(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.2", "builder", initial_state=pd.PaneState.needs_recover)
    cooldown_path = tmp_path / "run" / "graph-dispatch-pane-cooldowns.json"
    cooldown_path.parent.mkdir(parents=True, exist_ok=True)
    cooldown_path.write_text(
        '{"solar-harness-lab:0.2": {"reason": "pane_recover_cooldown:assigned_pane_unavailable:pane_title_active_work"}}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(pd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.2", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "────────────────\n❯\u00a0\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(
        pd.gnd,
        "_pane_cooldown_reason",
        lambda *_: "pane_recover_cooldown:assigned_pane_unavailable:pane_title_active_work",
    )
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.2")

    assert result["repairs"][0]["to"] == "clean"
    assert result["repairs"][0]["cooldown_cleared"] is True
    assert entry.state == pd.PaneState.clean


def test_repair_all_marks_stale_title_active_lab_pane_for_respawn_when_not_idle(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.2", "builder", initial_state=pd.PaneState.clean)
    cooldown_path = tmp_path / "run" / "graph-dispatch-pane-cooldowns.json"
    cooldown_path.parent.mkdir(parents=True, exist_ok=True)
    cooldown_path.write_text(
        '{"solar-harness-lab:0.2": {"reason": "pane_recover_cooldown:assigned_pane_unavailable:pane_title_active_work"}}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(pd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.2", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯ evaluate N4\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(
        pd.gnd,
        "_pane_cooldown_reason",
        lambda *_: "pane_recover_cooldown:assigned_pane_unavailable:pane_title_active_work",
    )
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: False)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.2")

    assert result["repairs"][0]["to"] == "needs_respawn"
    assert result["repairs"][0]["result"]["ok"] is True
    assert entry.state == pd.PaneState.needs_respawn


def test_repair_all_allows_running_to_clean_when_visibly_idle(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.2", "builder", initial_state=pd.PaneState.running)

    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.2", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.2")

    assert result["repairs"][0]["to"] == "clean"
    assert result["repairs"][0]["result"]["ok"] is True
    assert entry.state == pd.PaneState.clean


def test_respawn_lab_dry_run_selects_only_safe_needs_respawn_lab(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.0", "builder", initial_state=pd.PaneState.needs_respawn)
    registry.register_pane("solar-harness-lab:0.1", "builder", initial_state=pd.PaneState.running)
    registry.register_pane("solar-harness:0.0", "pm", initial_state=pd.PaneState.needs_respawn)

    monkeypatch.setattr(pd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [
        ("solar-harness-lab:0.0", "Builder"),
        ("solar-harness-lab:0.1", "Builder"),
        ("solar-harness:0.0", "PM"),
    ])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)
    monkeypatch.setattr(pd, "_tmux_pane_id", lambda pane: "%1" if pane == "solar-harness-lab:0.0" else "")
    monkeypatch.setattr(pd, "_lab_model_matrix", lambda: "claude-sonnet")
    monkeypatch.setattr(pd, "_lab_work_dir", lambda: tmp_path)

    result = pd.respawn_lab(dry_run=True, max_items=1)
    eligible = [item for item in result["actions"] if item["eligible"]]

    assert result["ok"] is True
    assert [item["pane"] for item in eligible] == ["solar-harness-lab:0.0"]
    assert eligible[0]["skipped"] is False
    assert "pane-launcher.sh" in eligible[0]["command"]


def test_respawn_lab_allows_busy_needs_respawn_but_skips_leased_panes(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.0", "builder", initial_state=pd.PaneState.needs_respawn)
    registry.register_pane("solar-harness-lab:0.1", "builder", initial_state=pd.PaneState.needs_respawn)

    monkeypatch.setattr(pd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [
        ("solar-harness-lab:0.0", "Builder"),
        ("solar-harness-lab:0.1", "Builder"),
    ])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda pane: pane.endswith(".0"))
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda pane: {"expires_at": "2999-01-01T00:00:00Z"} if pane.endswith(".1") else None)
    monkeypatch.setattr(pd, "_tmux_pane_id", lambda pane: "%0" if pane.endswith(".0") else "%1")

    result = pd.respawn_lab(dry_run=True, max_items=2)

    assert result["actions"][0]["skipped"] is False
    assert result["actions"][0]["reason"] == "needs_respawn"
    assert result["actions"][1]["skipped"] is True
    assert result["actions"][1]["reason"] == "live_lease"


def test_respawn_lab_executes_single_pane_and_clears_cooldown(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.2", "builder", initial_state=pd.PaneState.needs_respawn)
    cooldown_path = tmp_path / "run" / "graph-dispatch-pane-cooldowns.json"
    cooldown_path.parent.mkdir(parents=True, exist_ok=True)
    cooldown_path.write_text('{"solar-harness-lab:0.2": {"reason": "send_failed"}}\n', encoding="utf-8")
    calls = []

    monkeypatch.setattr(pd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.2", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: "❯\n")
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "pane_recover_cooldown:send_failed")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: False)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: True)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)
    monkeypatch.setattr(pd, "_tmux_pane_id", lambda *_: "%3")
    monkeypatch.setattr(pd, "_lab_model_matrix", lambda: "claude-sonnet")
    monkeypatch.setattr(pd, "_lab_work_dir", lambda: tmp_path)
    monkeypatch.setattr(pd, "_record_respawn", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(pd.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    result = pd.respawn_lab(dry_run=False, max_items=1)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.2")
    cooldowns = cooldown_path.read_text(encoding="utf-8")

    assert result["actions"][0]["ok"] is True
    assert entry.state == pd.PaneState.running
    assert "solar-harness-lab:0.2" not in cooldowns
    assert calls


def test_repair_all_marks_unleased_lab_tui_residue_for_respawn(tmp_path, monkeypatch):
    import pane_doctor as pd

    registry_path = tmp_path / "pane-hygiene.json"
    registry = pd.PaneHygieneRegistry(str(registry_path))
    registry.register_pane("solar-harness-lab:0.2", "builder", initial_state=pd.PaneState.running)

    tail = "\n".join([
        "⎿  Interrupted · What should Claude do instead?",
        "❯ yy",
        "  ⏵⏵ accept edits on (shift+tab to cycle)",
    ])
    monkeypatch.setattr(pd, "_registry", lambda path=None: pd.PaneHygieneRegistry(str(registry_path)))
    monkeypatch.setattr(pd, "_pane_rows", lambda: [("solar-harness-lab:0.2", "Builder")])
    monkeypatch.setattr(pd.gnd, "_pane_tail", lambda *_args, **_kwargs: tail)
    monkeypatch.setattr(pd.gnd, "_pane_current_command", lambda *_: "bash")
    monkeypatch.setattr(pd.gnd, "_pane_cooldown_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(pd.gnd, "_pane_unavailable_reason", lambda *_: "")
    monkeypatch.setattr(pd.gnd, "_pane_tui_busy", lambda *_: True)
    monkeypatch.setattr(pd, "_pane_visibly_idle", lambda *_: False)
    monkeypatch.setattr(pd, "read_lease", lambda *_: None)

    result = pd.repair_all(dry_run=False)
    entry = pd.PaneHygieneRegistry(str(registry_path)).get_pane_state("solar-harness-lab:0.2")

    assert result["ok"] is True
    assert result["repairs"][0]["to"] == "needs_respawn"
    assert entry.state == pd.PaneState.needs_respawn
