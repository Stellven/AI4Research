"""Tests for PaneHygieneRegistry — 6-state FSM + atomic write + flock."""
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pane_hygiene_registry import (
    IllegalTransitionError,
    PaneEntry,
    PaneHygieneRegistry,
    PaneState,
    _FORBIDDEN_TRANSITIONS,
    _LEGAL_TRANSITIONS,
)


@pytest.fixture
def registry(tmp_path):
    r = PaneHygieneRegistry(str(tmp_path / "test-pane-hygiene.json"))
    r.register_pane("solar-harness:0.3", "evaluator", model="anthropic-opus")
    r.register_pane("solar-harness-lab:0.0", "builder", model="glm-5.1")
    r.register_pane("solar-harness-lab:0.1", "builder", model="glm-5.1")
    r.register_pane("solar-harness-lab:0.2", "builder", model="glm-5.1")
    r.register_pane("solar-harness-lab:0.3", "builder", model="anthropic-sonnet")
    return r


def _count_legal_transitions():
    count = 0
    for targets in _LEGAL_TRANSITIONS.values():
        count += len(targets)
    return count


# ── FSM structure ──────────────────────────────────────────────────────


class TestFSMStructure:
    def test_six_states(self):
        assert len(PaneState) == 6
        names = {s.value for s in PaneState}
        assert names == {"clean", "running", "dirty", "cooling", "needs_recover", "needs_respawn"}

    def test_eleven_legal_transitions(self):
        assert _count_legal_transitions() == 11

    def test_four_forbidden_transitions(self):
        assert len(_FORBIDDEN_TRANSITIONS) == 4


# ── Legal transitions ─────────────────────────────────────────────────


class TestLegalTransitions:
    @pytest.mark.parametrize("from_s,to_s", [
        (PaneState.clean, PaneState.running),
        (PaneState.running, PaneState.dirty),
        (PaneState.running, PaneState.needs_recover),
        (PaneState.dirty, PaneState.clean),
        (PaneState.dirty, PaneState.cooling),
        (PaneState.dirty, PaneState.needs_recover),
        (PaneState.cooling, PaneState.needs_recover),
        (PaneState.cooling, PaneState.dirty),
        (PaneState.needs_recover, PaneState.running),
        (PaneState.needs_recover, PaneState.needs_respawn),
        (PaneState.needs_respawn, PaneState.running),
    ])
    def test_legal_transition_succeeds(self, registry, from_s, to_s):
        pid = "solar-harness-lab:0.0"
        entry = registry.get_pane_state(pid)
        entry.state = from_s
        entry.last_state_transition_at = "2026-01-01T00:00:00Z"
        registry._persist()
        result = registry.transition_state(pid, to_s)
        assert result.state == to_s

    def test_clean_to_running_via_dispatch(self, registry):
        result = registry.transition_state(
            "solar-harness:0.3", PaneState.running,
            reason="dispatch_selected", sprint_id="sprint-123",
        )
        assert result.state == PaneState.running
        assert result.last_task_sprint_id == "sprint-123"


# ── Forbidden transitions ─────────────────────────────────────────────


class TestForbiddenTransitions:
    @pytest.mark.parametrize("from_s,to_s", _FORBIDDEN_TRANSITIONS)
    def test_forbidden_raises(self, registry, from_s, to_s):
        pid = "solar-harness-lab:0.0"
        entry = registry.get_pane_state(pid)
        entry.state = from_s
        registry._persist()
        with pytest.raises(IllegalTransitionError) as exc_info:
            registry.transition_state(pid, to_s)
        assert exc_info.value.pane_id == pid
        assert exc_info.value.from_state == from_s
        assert exc_info.value.to_state == to_s

    def test_cooling_to_running_forbidden(self, registry):
        pid = "solar-harness-lab:0.0"
        e = registry.get_pane_state(pid)
        e.state = PaneState.cooling
        registry._persist()
        with pytest.raises(IllegalTransitionError):
            registry.transition_state(pid, PaneState.running)

    def test_self_transition_forbidden(self, registry):
        with pytest.raises(IllegalTransitionError):
            registry.transition_state("solar-harness:0.3", PaneState.clean)


# ── Register / Unregister ─────────────────────────────────────────────


class TestRegisterUnregister:
    def test_register_creates_entry(self, tmp_path):
        r = PaneHygieneRegistry(str(tmp_path / "r.json"))
        entry = r.register_pane("test:0.0", "builder")
        assert entry.pane_id == "test:0.0"
        assert entry.state == PaneState.clean
        assert entry.pane_role == "builder"

    def test_register_duplicate_raises(self, registry):
        with pytest.raises(ValueError, match="already registered"):
            registry.register_pane("solar-harness:0.3", "evaluator")

    def test_unregister_removes(self, registry):
        registry.unregister_pane("solar-harness-lab:0.3")
        with pytest.raises(KeyError):
            registry.get_pane_state("solar-harness-lab:0.3")

    def test_unregister_missing_raises(self, registry):
        with pytest.raises(KeyError):
            registry.unregister_pane("nonexistent:0.0")

    def test_get_missing_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get_pane_state("nonexistent:0.0")


# ── Query ──────────────────────────────────────────────────────────────


class TestQuery:
    def test_query_clean_returns_all_clean(self, registry):
        clean = registry.query_clean_panes()
        assert len(clean) == 5

    def test_query_clean_filters_role(self, registry):
        clean = registry.query_clean_panes(role="builder")
        assert all(e.pane_role == "builder" for e in clean)
        assert len(clean) == 4

    def test_query_clean_excludes(self, registry):
        clean = registry.query_clean_panes(exclude=["solar-harness-lab:0.0"])
        assert len(clean) == 4
        ids = {e.pane_id for e in clean}
        assert "solar-harness-lab:0.0" not in ids

    def test_query_clean_skips_non_clean(self, registry):
        registry.transition_state("solar-harness:0.3", PaneState.running)
        clean = registry.query_clean_panes()
        assert len(clean) == 4

    def test_list_all_panes(self, registry):
        all_panes = registry.list_all_panes()
        assert len(all_panes) == 5


# ── Fail counter ───────────────────────────────────────────────────────


class TestFailCounter:
    def test_increment_fail(self, registry):
        registry.transition_state("solar-harness:0.3", PaneState.running)
        registry.transition_state("solar-harness:0.3", PaneState.needs_recover)
        entry = registry.get_pane_state("solar-harness:0.3")
        assert entry.consecutive_fail_count == 0
        registry.transition_state("solar-harness:0.3", PaneState.running, increment_fail=True)
        assert registry.get_pane_state("solar-harness:0.3").consecutive_fail_count == 1

    def test_reset_fail(self, registry):
        registry.transition_state("solar-harness:0.3", PaneState.running, increment_fail=True)
        registry.transition_state("solar-harness:0.3", PaneState.dirty)
        registry.transition_state("solar-harness:0.3", PaneState.clean, reset_fail=True)
        assert registry.get_pane_state("solar-harness:0.3").consecutive_fail_count == 0


# ── Context fields ─────────────────────────────────────────────────────


class TestContextFields:
    def test_update_context_hash(self, registry):
        entry = registry.update_context_fields(
            "solar-harness:0.3", context_hash="abc123",
        )
        assert entry.context_hash == "abc123"

    def test_update_persona(self, registry):
        entry = registry.update_context_fields(
            "solar-harness:0.3", persona="builder",
        )
        assert entry.persona == "builder"


# ── Atomic write ───────────────────────────────────────────────────────


class TestAtomicWrite:
    def test_file_written_after_transition(self, registry, tmp_path):
        path = tmp_path / "test-pane-hygiene.json"
        data = json.loads(path.read_text())
        assert "solar-harness:0.3" in data

    def test_file_valid_json_after_concurrent_writes(self, tmp_path):
        path = str(tmp_path / "concurrent.json")
        r = PaneHygieneRegistry(path)
        for i in range(5):
            r.register_pane(f"pane-{i}", "builder")

        errors = []

        def worker(pane_id):
            try:
                r.transition_state(pane_id, PaneState.running)
                r.transition_state(pane_id, PaneState.dirty)
                r.transition_state(pane_id, PaneState.clean)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"pane-{i}",)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent write errors: {errors}"
        data = json.loads(Path(path).read_text())
        assert len(data) == 5
        for pane_id, entry_data in data.items():
            assert entry_data["state"] in ("clean", "running", "dirty")

    def test_load_from_existing_file(self, tmp_path):
        path = str(tmp_path / "persist.json")
        r1 = PaneHygieneRegistry(path)
        r1.register_pane("p:0.0", "builder", model="glm-5.1")
        r1.transition_state("p:0.0", PaneState.running)

        r2 = PaneHygieneRegistry(path)
        entry = r2.get_pane_state("p:0.0")
        assert entry.state == PaneState.running
        assert entry.model == "glm-5.1"


# ── Seed fixture loads ────────────────────────────────────────────────


class TestSeedFixture:
    def test_seed_loads_into_registry(self, tmp_path):
        seed = Path(__file__).resolve().parent / "fixtures" / "pane_hygiene_seed.json"
        data = json.loads(seed.read_text())
        assert len(data) == 5
        ids = set(data.keys())
        expected = {
            "solar-harness:0.3",
            "solar-harness-lab:0.0",
            "solar-harness-lab:0.1",
            "solar-harness-lab:0.2",
            "solar-harness-lab:0.3",
        }
        assert ids == expected

    def test_seed_all_clean(self):
        seed = Path(__file__).resolve().parent / "fixtures" / "pane_hygiene_seed.json"
        data = json.loads(seed.read_text())
        for pid, entry in data.items():
            assert entry["state"] == "clean", f"{pid} not clean"
