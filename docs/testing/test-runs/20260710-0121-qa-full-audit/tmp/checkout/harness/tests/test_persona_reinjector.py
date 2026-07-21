"""Tests for PersonaReinjector — inject_persona/runtime_policy/solar_context/verify."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from persona_reinjector import PersonaReinjector, InjectionResult


@pytest.fixture
def tmp_templates(tmp_path):
    base = tmp_path / "templates"
    persona_dir = base / "persona"
    persona_dir.mkdir(parents=True)
    (persona_dir / "builder.md").write_text("You are a Solar Builder.\nBuild code.")
    (persona_dir / "evaluator.md").write_text("You are a Solar Evaluator.\nReview code.")
    rp = base / "runtime_policy.md"
    rp.write_text("Definition of Done: 7 rules.\nNo optimistic words.")
    ctx = base / "solar_context_sprint-123.md"
    ctx.write_text("Sprint context for sprint-123.\nGoal: implement X.")
    return base


class FakeRegistry:
    def __init__(self):
        self.fields = {}

    def update_context_fields(self, pane_id, *, context_hash=None, persona=None, runtime_policy_hash=None):
        self.fields[pane_id] = {
            "context_hash": context_hash,
            "persona": persona,
            "runtime_policy_hash": runtime_policy_hash,
        }

    def get_pane_state(self, pane_id):
        return None


class FakeLedger:
    def __init__(self):
        self.records = []

    def record_reinject(self, pane_id, *, before_state, after_state, success, reason, sprint_id=None):
        self.records.append({"pane_id": pane_id, "success": success, "reason": reason})


def _make_reinjector(tmp_templates, captures=None):
    sent = []
    slept = []
    cap = captures or {"test:0.0": "You are a Solar Builder.\nBuild code."}

    def capture_fn(pid):
        return cap.get(pid, "")

    registry = FakeRegistry()
    ledger = FakeLedger()
    r = PersonaReinjector(
        registry, ledger,
        template_base=str(tmp_templates),
        send_fn=lambda pid, txt: sent.append((pid, txt)),
        sleep_fn=lambda s: slept.append(s),
        capture_fn=capture_fn,
    )
    return r, sent, slept, ledger, registry


# --- inject_persona ---

class TestInjectPersona:
    def test_success(self, tmp_templates):
        r, sent, slept, _, _ = _make_reinjector(tmp_templates)
        assert r.inject_persona("test:0.0", "builder") is True
        assert len(sent) == 1

    def test_missing_template(self, tmp_templates):
        r, _, _, _, _ = _make_reinjector(tmp_templates)
        with pytest.raises(FileNotFoundError):
            r.inject_persona("test:0.0", "nonexistent_role")

    def test_verify_fails(self, tmp_templates):
        r, _, _, _, _ = _make_reinjector(
            tmp_templates, captures={"test:0.0": "completely different text"}
        )
        assert r.inject_persona("test:0.0", "builder") is False


# --- inject_runtime_policy ---

class TestInjectRuntimePolicy:
    def test_success(self, tmp_templates):
        r, sent, _, _, _ = _make_reinjector(
            tmp_templates, captures={"test:0.0": "Definition of Done: 7 rules.\nNo optimistic words."}
        )
        assert r.inject_runtime_policy("test:0.0") is True

    def test_missing_template(self, tmp_path):
        r, _, _, _, _ = _make_reinjector(
            tmp_path / "templates",
            captures={"test:0.0": "text"}
        )
        (tmp_path / "templates" / "persona").mkdir(parents=True)
        (tmp_path / "templates" / "persona" / "builder.md").write_text("x")
        with pytest.raises(FileNotFoundError):
            r.inject_runtime_policy("test:0.0")


# --- inject_solar_context ---

class TestInjectSolarContext:
    def test_success(self, tmp_templates):
        r, _, _, _, _ = _make_reinjector(
            tmp_templates, captures={"test:0.0": "Sprint context for sprint-123.\nGoal: implement X."}
        )
        assert r.inject_solar_context("test:0.0", sprint_id="sprint-123") is True

    def test_custom_path(self, tmp_templates):
        custom = tmp_templates / "custom_ctx.md"
        custom.write_text("Custom context here.")
        r, _, _, _, _ = _make_reinjector(
            tmp_templates, captures={"test:0.0": "Custom context here."}
        )
        assert r.inject_solar_context("test:0.0", sprint_id="xxx",
                                       context_template_path=str(custom)) is True


# --- inject_all ---

class TestInjectAll:
    def test_full_success(self, tmp_templates):
        r, _, _, ledger, registry = _make_reinjector(
            tmp_templates,
            captures={"test:0.0": "You are a Solar Builder.\nBuild code.Definition of Done: 7 rules.\nNo optimistic words.Sprint context for sprint-123.\nGoal: implement X."},
        )
        result = r.inject_all("test:0.0", "builder", "sprint-123")
        assert result.success
        assert result.injected == ["persona", "runtime_policy", "solar_context"]
        assert result.failed_at is None
        assert len(ledger.records) == 1
        assert ledger.records[0]["success"] is True

    def test_persona_failure_stops(self, tmp_templates):
        r, _, _, ledger, _ = _make_reinjector(
            tmp_templates,
            captures={"test:0.0": "wrong text"},
        )
        result = r.inject_all("test:0.0", "builder", "sprint-123")
        assert not result.success
        assert result.failed_at == "persona"
        assert "persona" not in result.injected

    def test_missing_template_records_failure(self, tmp_path):
        base = tmp_path / "templates"
        base.mkdir()
        r, _, _, ledger, _ = _make_reinjector(base, captures={"p": "x"})
        result = r.inject_all("p", "builder", "sprint-123")
        assert not result.success
        assert result.failed_at == "persona"
        assert len(ledger.records) == 1


# --- verify_injection ---

class TestVerifyInjection:
    def test_keyword_found(self, tmp_templates):
        r, _, _, _, _ = _make_reinjector(
            tmp_templates, captures={"p": "Solar Harness Builder active"}
        )
        assert r.verify_injection("p", "persona", "Solar Harness") is True

    def test_keyword_not_found(self, tmp_templates):
        r, _, _, _, _ = _make_reinjector(
            tmp_templates, captures={"p": "something else"}
        )
        assert r.verify_injection("p", "persona", "Solar Harness") is False

    def test_empty_keyword_passes(self, tmp_templates):
        r, _, _, _, _ = _make_reinjector(tmp_templates)
        assert r.verify_injection("p", "persona", "") is True
