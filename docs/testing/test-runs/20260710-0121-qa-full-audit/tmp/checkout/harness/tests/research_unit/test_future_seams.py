"""Unit tests for future platform schemas and operator seams.

Verifies the draft JSON schemas syntax, dataclass validation rules,
and seam Protocol implementation behaviors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from research import schemas, seams


class TestDraftSchemasSyntax:
    """Verifies that all new draft JSON schemas are syntactically valid JSON."""

    SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas" / "draft"

    @pytest.mark.parametrize(
        "filename",
        [
            "living-report.v1.draft.json",
            "research-lab.v1.draft.json",
            "research-memory.v1.draft.json",
            "ai-infra-pack.v1.draft.json",
            "artifact-delta-contract.v1.draft.json",
        ],
    )
    def test_schema_json_syntax(self, filename: str) -> None:
        path = self.SCHEMA_DIR / filename
        assert path.exists(), f"Schema file {filename} does not exist at {path}"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["schema_status"] == "draft"
            assert data["schema_version"] == "v1.0.0-draft"
        except Exception as e:
            pytest.fail(f"Failed to load or parse JSON schema {filename}: {e}")


class TestFutureDataclasses:
    """Verifies that the new dataclasses validate their invariants in __post_init__."""

    def test_living_report_validation(self) -> None:
        # Valid construction
        lr = schemas.LivingReport(
            report_id="lr_123",
            topic="Agent Memory",
            active_ast_id="ast_456",
            watch_schedules=[{"schedule_type": "cron", "expression": "0 0 * * *"}],
        )
        assert lr.report_id == "lr_123"

        # Invalid merge strategy
        with pytest.raises(ValueError, match="LivingReport merge_strategy .* invalid"):
            schemas.LivingReport(
                report_id="lr_123",
                topic="Agent Memory",
                active_ast_id="ast_456",
                update_policy={"merge_strategy": "invalid_strategy"},
            )

        # Invalid schedule type
        with pytest.raises(ValueError, match="LivingReport schedule_type .* invalid"):
            schemas.LivingReport(
                report_id="lr_123",
                topic="Agent Memory",
                active_ast_id="ast_456",
                watch_schedules=[{"schedule_type": "invalid_type", "expression": "* * *"}],
            )

    def test_research_lab_validation(self) -> None:
        # Valid construction
        lab = schemas.ResearchLab(lab_id="lab_123", name="AI Safety Lab")
        assert lab.status == "active"

        # Invalid status
        with pytest.raises(ValueError, match="ResearchLab.status .* invalid"):
            schemas.ResearchLab(lab_id="lab_123", name="AI Safety Lab", status="invalid_status")

        # Invalid telemetry log level
        with pytest.raises(ValueError, match="ResearchLab log_level .* invalid"):
            schemas.ResearchLab(
                lab_id="lab_123",
                name="AI Safety Lab",
                telemetry_config={"log_level": "verbose"},
            )

    def test_research_memory_validation(self) -> None:
        # Valid construction
        mem = schemas.ResearchMemory(
            memory_id="mem_123", scope="global", storage_backend="sqlite"
        )
        assert mem.scope == "global"

        # Invalid scope
        with pytest.raises(ValueError, match="ResearchMemory.scope .* invalid"):
            schemas.ResearchMemory(memory_id="mem_123", scope="invalid_scope")

        # Invalid memory type
        with pytest.raises(ValueError, match="ResearchMemory memory_type .* invalid"):
            schemas.ResearchMemory(
                memory_id="mem_123",
                scope="global",
                storage_backend="sqlite",
                memory_types=["invalid_type"],
            )

    def test_ai_infra_pack_validation(self) -> None:
        # Valid construction
        pack = schemas.AIInfraPack(
            pack_id="pack_123",
            pack_name="standard-pack",
            version="1.2.3-alpha.1",
            status="stable",
        )
        assert pack.version == "1.2.3-alpha.1"

        # Invalid semver version format
        with pytest.raises(ValueError, match="AIInfraPack.version .* invalid"):
            schemas.AIInfraPack(
                pack_id="pack_123", pack_name="standard-pack", version="v1.2", status="stable"
            )

        # Invalid MCP server endpoint
        with pytest.raises(ValueError, match="AIInfraPack mcp_server endpoint_type .* invalid"):
            schemas.AIInfraPack(
                pack_id="pack_123",
                pack_name="standard-pack",
                version="1.0.0",
                mcp_servers=[{"name": "mcp-test", "endpoint_type": "invalid_type"}],
            )

    def test_artifact_delta_validation(self) -> None:
        # Valid construction
        delta = schemas.ArtifactDelta(
            delta_id="delta_123",
            target_artifact_id="lr_456",
            target_artifact_type="living_report",
            changes=[{"op": "add", "path": "/metadata/owner", "value": "antigravity"}],
        )
        assert delta.delta_id == "delta_123"

        # Invalid target artifact type
        with pytest.raises(ValueError, match="ArtifactDelta.target_artifact_type .* invalid"):
            schemas.ArtifactDelta(
                delta_id="delta_123",
                target_artifact_id="lr_456",
                target_artifact_type="invalid_type",
            )

        # Invalid operation type
        with pytest.raises(ValueError, match="ArtifactDelta change op .* invalid"):
            schemas.ArtifactDelta(
                delta_id="delta_123",
                target_artifact_id="lr_456",
                target_artifact_type="living_report",
                changes=[{"op": "delete", "path": "/metadata"}],
            )


class TestFutureSeams:
    """Verifies that fallback operators implement their respective Protocol interfaces."""

    def test_living_report_operator_seam(self) -> None:
        op = seams.DegradedLivingReportOperator()
        assert isinstance(op, seams.LivingReportOperator)
        lr = op.initialize_report(topic="Living Docs", initial_ast_id="ast_1")
        assert lr.topic == "Living Docs"
        assert lr.active_ast_id == "ast_1"

        with pytest.raises(NotImplementedError):
            op.update_report("lr_1", "ast_2", "some changes")

        assert op.trigger_watch_cycle("lr_1") == []

    def test_research_lab_operator_seam(self) -> None:
        op = seams.DegradedResearchLabOperator()
        assert isinstance(op, seams.ResearchLabOperator)
        lab = op.register_lab(name="Standard Test Lab", slots=["main:0", "main:1"])
        assert lab.name == "Standard Test Lab"
        assert op.allocate_slot("default_lab", "writing") == "main:0"

        with pytest.raises(NotImplementedError):
            op.submit_experiment("default_lab", {}, "main:0")

        res = op.check_telemetry_limits("default_lab", "run_1")
        assert res["ok"] is True

    def test_research_memory_operator_seam(self) -> None:
        op = seams.DegradedResearchMemoryOperator()
        assert isinstance(op, seams.ResearchMemoryOperator)
        assert op.store_fact("mem_1", "c1", "solar is fast", 0.95) is False
        assert op.query_similar_facts("mem_1", "solar speed") == []
        op.append_episodic_log("mem_1", "run_1", [])

    def test_ai_infra_pack_operator_seam(self) -> None:
        op = seams.DegradedAIInfraPackOperator()
        assert isinstance(op, seams.AIInfraPackOperator)
        pack = op.load_pack("pack_1")
        assert pack.pack_id == "pack_1"
        assert op.provision_mcp_servers(pack) == {}
        tmpl = op.resolve_operator_template(pack, "writer")
        assert tmpl["role"] == "writer"

    def test_artifact_delta_applier_seam(self) -> None:
        op = seams.DegradedArtifactDeltaApplier()
        assert isinstance(op, seams.ArtifactDeltaApplier)
        delta = schemas.ArtifactDelta(
            delta_id="d1",
            target_artifact_id="lr_1",
            target_artifact_type="living_report",
        )
        with pytest.raises(NotImplementedError):
            op.apply_delta(None, delta)
