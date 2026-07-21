"""Tests for harness.lib.livework.schemas — field completeness and schema_version presence."""

import pytest

from harness.lib.livework import schemas


class TestSchemaVersionPresence:
    """Each of the 4 top-level schemas must have a schema_version field."""

    def test_status_ext_has_schema_version(self):
        s = schemas.StatusExt()
        assert hasattr(s, "schema_version")
        assert isinstance(s.schema_version, str)
        assert s.schema_version == "1.0.0"

    def test_event_v2_has_schema_version(self):
        e = schemas.EventV2()
        assert hasattr(e, "schema_version")
        assert isinstance(e.schema_version, str)

    def test_requirement_intake_has_schema_version(self):
        r = schemas.RequirementIntake()
        assert hasattr(r, "schema_version")
        assert isinstance(r.schema_version, str)

    def test_role_resolver_view_has_schema_version(self):
        v = schemas.RoleResolverView()
        assert hasattr(v, "schema_version")
        assert isinstance(v.schema_version, str)

    def test_schema_version_count(self):
        assert schemas.StatusExt().schema_version == "1.0.0"
        assert schemas.EventV2().schema_version == "1.0.0"
        assert schemas.RequirementIntake().schema_version == "1.0.0"
        assert schemas.RoleResolverView().schema_version == "1.0.0"


class TestStatusExtFields:
    """StatusExt must have all fields from Schema A in data-model.md."""

    def test_idle_state_defaults(self):
        s = schemas.StatusExt()
        assert s.is_idle is True
        assert s.queue_depth == 0
        assert s.active_panes == []
        assert s.last_completed_sprint is None
        assert s.active_sprint is None

    def test_active_sprint_fields(self):
        a = schemas.ActiveSprint(sprint_id="sid", phase="drafting", started_at="2026-05-14T12:00:00Z")
        assert a.sprint_id == "sid"
        assert a.phase == "drafting"
        assert a.started_at == "2026-05-14T12:00:00Z"

    def test_non_idle_state(self):
        a = schemas.ActiveSprint(sprint_id="sid", phase="building", started_at="2026-05-14T12:00:00Z")
        s = schemas.StatusExt(is_idle=False, active_sprint=a, active_panes=["lab:0.3"], queue_depth=1)
        assert s.is_idle is False
        assert s.active_sprint is not None

    def test_total_completed_sprints(self):
        s = schemas.StatusExt(total_completed_sprints=42)
        assert s.total_completed_sprints == 42


class TestEventV2Fields:
    """EventV2 base must have seq, timestamp, event_type fields."""

    def test_base_fields(self):
        e = schemas.EventV2(seq=42, timestamp="2026-05-14T15:00:00Z", event_type="autopilot_heartbeat")
        assert e.seq == 42
        assert e.timestamp == "2026-05-14T15:00:00Z"
        assert e.event_type == "autopilot_heartbeat"

    def test_heartbeat_payload(self):
        p = schemas.AutopilotHeartbeatPayload(idle=True, active_dispatches=0, queue_depth=0)
        assert p.idle is True
        assert p.active_dispatches == 0

    def test_deadlock_payload(self):
        p = schemas.PaneDeadlockPayload(
            pane_id="lab:0.3", dispatch_id="d1", elapsed_seconds=600, deadline_seconds=600, action="alert"
        )
        assert p.pane_id == "lab:0.3"
        assert p.auto_recover is False

    def test_event_type_enum_values(self):
        assert schemas.EventV2Type.AUTOMATIC_HEARTBEAT == "autopilot_heartbeat"
        assert schemas.EventV2Type.PAN_DEADLOCK == "pane_deadlock"
        assert schemas.EventV2Type.REQUIREMENT_INTAKE == "requirement_intake"
        assert schemas.EventV2Type.PM_DRAFTED == "pm_drafted"
        assert schemas.EventV2Type.ROLE_TRANSITION == "role_transition"


class TestRequirementIntakeFields:
    """RequirementIntake must have lifecycle status and rejection info."""

    def test_defaults(self):
        r = schemas.RequirementIntake()
        assert r.status == "pm_analysis"
        assert r.submitted_by == "user"
        assert r.source == "chat"
        assert r.rejection is None

    def test_rejection_present(self):
        rej = schemas.RejectionInfo(error_code="E_REQUIREMENT_TOO_VAGUE", error_message="Too short", hint="Add more detail")
        r = schemas.RequirementIntake(status="rejected", rejection=rej)
        assert r.status == "rejected"
        assert r.rejection is not None
        assert r.rejection.error_code == "E_REQUIREMENT_TOO_VAGUE"

    def test_active_sprint_id_on_reject(self):
        r = schemas.RequirementIntake(status="rejected", active_sprint_id="existing-sid")
        assert r.active_sprint_id == "existing-sid"


class TestRoleResolverViewFields:
    """RoleResolverView must have nodes, next_action, gate_status."""

    def test_defaults(self):
        v = schemas.RoleResolverView(sprint_id="sid", phase="drafting", next_action="Builder working on N2")
        assert v.nodes == []
        assert v.blocked_by == []
        assert v.gate_status == {}

    def test_with_nodes(self):
        n = schemas.NodeSummary(id="N2", status="in_progress", goal="Produce interfaces.md", assigned_to="lab:0.3")
        v = schemas.RoleResolverView(sprint_id="sid", phase="building", nodes=[n], next_action="N2 in progress")
        assert len(v.nodes) == 1
        assert v.nodes[0].id == "N2"
        assert v.nodes[0].assigned_to == "lab:0.3"

    def test_gate_status(self):
        v = schemas.RoleResolverView(gate_status={"outcomes-pass": "passed", "integration-pass": "pending"})
        assert v.gate_status["outcomes-pass"] == "passed"
        assert v.gate_status["integration-pass"] == "pending"
