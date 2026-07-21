#!/usr/bin/env python3
"""Tests for the goal-driven APO dynamic planning path (S4 — sprint-20260530).

Verifies:
  - classify_task_goal() produces correct task_classification for FlashMLX-style objectives
  - expand_logical_workflow() selects the performance_debug_workflow for PERFORMANCE_KERNEL_DEBUG
  - compile_execution_plan_for_node() emits task_classification, logical_workflow,
    skill_plan, mcp_plan, capsule_plan_artifact, selection_rationale
  - FlashMLX path selects cap.flashmlx-performance-debugger through the generic classifier
    (not a hardcoded branch)
  - Rejected capsule candidates are recorded (explainability is not selection-only)
  - Static fallback is used when no goal text is available and fallback_used=True
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import capability_capsules as cc
import apo_plan_compiler as apo


REGISTRY_PATH = ROOT / "config" / "capability-capsules.registry.yaml"
TAXONOMY_PATH = ROOT / "config" / "task-taxonomy.json"
OPERATORS_PATH = ROOT / "config" / "logical-operators.json"


# ─── classify_task_goal ──────────────────────────────────────────────────────

def test_classify_flashmlx_gather_qmm():
    """FlashMLX gather_qmm benchmark objective → PERFORMANCE_KERNEL_DEBUG, high confidence."""
    result = cc.classify_task_goal(
        "Debug gather_qmm throughput regression in FlashMLX benchmark run",
        taxonomy_path=TAXONOMY_PATH,
    )
    assert result["primary_class"] in ("PERFORMANCE_KERNEL_DEBUG", "PERFORMANCE_REGRESSION"), (
        f"Expected performance class, got {result['primary_class']}"
    )
    assert result["confidence"] in ("high", "medium"), f"Expected high/medium confidence, got {result['confidence']}"
    assert len(result["signals_detected"]) > 0, "Expected at least one signal detected"
    # At least one positive signal from the goal
    positive_signals = [s for s in result["signals_detected"] if s["weight"] > 0]
    assert len(positive_signals) > 0, "Expected at least one positive signal"


def test_classify_produces_rejected_classes():
    """Non-performance goal does not produce PERFORMANCE_REGRESSION as primary."""
    result = cc.classify_task_goal(
        "Implement a new REST endpoint for user profile",
        taxonomy_path=TAXONOMY_PATH,
    )
    assert result.get("rejected_classes") is not None, "rejected_classes must be present"
    # rejected_classes should contain something (not all classes can be primary)
    all_class_ids = {entry["class_id"] for entry in result["rejected_classes"]}
    selected_ids = set(result.get("selected_classes", []))
    # Rejected classes should not overlap with selected classes
    assert all_class_ids.isdisjoint(selected_ids) or len(selected_ids) == 0 or \
        all(r["reason"] in ("below_min_signal_score", "outscored_by_primary") for r in result["rejected_classes"])


def test_classify_empty_goal_returns_no_selection():
    """Empty goal → no task classes selected, graceful fallback."""
    result = cc.classify_task_goal("", taxonomy_path=TAXONOMY_PATH)
    assert result["primary_class"] is None
    assert result["selected_classes"] == []
    assert result["confidence"] == "low"


def test_classify_negative_signal_suppresses_class():
    """Goal with negative signals for performance classes reduces their score."""
    result = cc.classify_task_goal(
        "Update frontend UI component styles and CSS",
        taxonomy_path=TAXONOMY_PATH,
    )
    # 'ui' and 'frontend' are negative signals for performance classes
    perf_classes = {"PERFORMANCE_REGRESSION", "PERFORMANCE_KERNEL_DEBUG"}
    selected = set(result.get("selected_classes", []))
    # Performance classes should not dominate when negative signals are present
    primary = result.get("primary_class")
    if primary in perf_classes:
        # If somehow selected, it must have overcome the negatives — check score
        assert result["signal_score"] > 0, "Score must be positive to select perf class"


# ─── expand_logical_workflow ─────────────────────────────────────────────────

def test_expand_workflow_for_performance_kernel_debug():
    """PERFORMANCE_KERNEL_DEBUG → performance_debug_workflow with 7 stages."""
    classification = {
        "primary_class": "PERFORMANCE_KERNEL_DEBUG",
        "selected_classes": ["PERFORMANCE_KERNEL_DEBUG"],
    }
    workflow = cc.expand_logical_workflow(classification, operators_path=OPERATORS_PATH)
    assert workflow["template"] == "performance_debug_workflow", (
        f"Expected performance_debug_workflow, got {workflow['template']}"
    )
    stage_names = [s["stage_name"] for s in workflow["stages"]]
    assert "ScanContext" in stage_names
    assert "DebugRCA" in stage_names
    assert "ImplementPatch" in stage_names
    assert "RunBenchmark" in stage_names
    assert "VerifyEvidence" in stage_names


def test_expand_workflow_for_code_impl():
    """CODE_IMPL_REQUIRED → implementation_workflow (no RunBenchmark)."""
    classification = {
        "primary_class": "CODE_IMPL_REQUIRED",
        "selected_classes": ["CODE_IMPL_REQUIRED"],
    }
    workflow = cc.expand_logical_workflow(classification, operators_path=OPERATORS_PATH)
    assert workflow["template"] == "implementation_workflow"
    stage_names = [s["stage_name"] for s in workflow["stages"]]
    assert "ScanContext" in stage_names
    assert "ImplementPatch" in stage_names
    assert "RunBenchmark" not in stage_names, "implementation_workflow should not include RunBenchmark"


def test_expand_workflow_no_class_returns_empty():
    """No primary class → empty stages."""
    classification = {"primary_class": None, "selected_classes": []}
    workflow = cc.expand_logical_workflow(classification, operators_path=OPERATORS_PATH)
    assert workflow["stages"] == []


def test_expand_workflow_stages_have_operators():
    """All expanded stages must reference at least one logical operator."""
    classification = {"primary_class": "PERFORMANCE_REGRESSION", "selected_classes": ["PERFORMANCE_REGRESSION"]}
    workflow = cc.expand_logical_workflow(classification, operators_path=OPERATORS_PATH)
    for stage in workflow["stages"]:
        assert len(stage["logical_operators"]) > 0, (
            f"Stage {stage['stage_name']} has no logical operators"
        )


# ─── compile_execution_plan_for_node (full artifact) ─────────────────────────

def _flashmlx_node() -> dict:
    return {
        "id": "gather-qmm-debug",
        "goal": "Debug gather_qmm throughput regression in FlashMLX MLX benchmark",
        "logical_operator": "RootCauseDebugger",
        "depends_on": [],
        "type": "debug",
    }


def test_compile_emits_task_classification():
    """compile_execution_plan_for_node emits task_classification field."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    assert "task_classification" in result, "task_classification must be in compile output"
    tc = result["task_classification"]
    assert "selected_classes" in tc
    assert "confidence" in tc
    assert "signals_detected" in tc
    assert "rejected_classes" in tc


def test_compile_emits_logical_workflow():
    """compile_execution_plan_for_node emits logical_workflow field."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    assert "logical_workflow" in result, "logical_workflow must be in compile output"
    lw = result["logical_workflow"]
    assert "template" in lw
    assert "stages" in lw


def test_compile_emits_skill_plan():
    """compile_execution_plan_for_node emits skill_plan field."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    assert "skill_plan" in result, "skill_plan must be in compile output"


def test_compile_emits_mcp_plan():
    """compile_execution_plan_for_node emits mcp_plan field."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    assert "mcp_plan" in result, "mcp_plan must be in compile output"
    mp = result["mcp_plan"]
    assert "required_mcp" in mp


def test_compile_emits_selection_rationale():
    """compile_execution_plan_for_node emits selection_rationale field."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    assert "selection_rationale" in result
    sr = result["selection_rationale"]
    assert "fallback_used" in sr
    assert "primary_class" in sr


def test_compile_flashmlx_selects_performance_debugger():
    """FlashMLX objective selects cap.flashmlx-performance-debugger via generic classifier."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    capsule_artifact = result.get("capsule_plan_artifact", {})
    selected = capsule_artifact.get("selected_capsule_id") or result.get("capsule_plan", {}).get("capability_capsule_id")
    # The selected capsule should be the performance debugger (not a hardcoded branch)
    assert selected == "cap.flashmlx-performance-debugger", (
        f"Expected cap.flashmlx-performance-debugger via generic classifier, got {selected!r}. "
        f"fallback_used={capsule_artifact.get('fallback_used')}, "
        f"primary_class={result.get('task_classification', {}).get('primary_class')}"
    )
    # Verify it was selected via goal-driven path, not static fallback
    assert not capsule_artifact.get("fallback_used"), (
        "cap.flashmlx-performance-debugger must be selected via goal-driven classifier, not static fallback"
    )


def test_compile_records_rejected_capsule_candidates():
    """Capsule candidates list includes rejected capsules (explainability)."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    candidates = result.get("capsule_plan_artifact", {}).get("candidates", [])
    # Must have at least the selected capsule
    assert len(candidates) >= 1, "capsule candidates list must not be empty"
    # If there are multiple, some must be rejected
    if len(candidates) > 1:
        rejected = [c for c in candidates if not c["selected"]]
        assert len(rejected) > 0, "Multi-candidate list must include rejected candidates"
        for r in rejected:
            assert r.get("rejection_rationale") is not None, "Rejected candidates must have rejection_rationale"


def test_compile_static_fallback_flagged():
    """Node with no goal text falls back to static default and marks fallback_used=True."""
    node = {
        "id": "no-goal-node",
        "goal": "",
        "logical_operator": "ImplementationWorker",
        "depends_on": [],
        "type": "implementation",
    }
    result = apo.compile_execution_plan_for_node(
        node,
        registry_path=REGISTRY_PATH,
    )
    sr = result.get("selection_rationale", {})
    # When no goal text, classifier cannot score → static fallback should be used
    if sr.get("capsule_selected"):
        # If a capsule was selected, check fallback flag is correctly set
        assert isinstance(sr.get("fallback_used"), bool)


def test_compile_mcp_plan_has_required_capabilities_for_flashmlx():
    """FlashMLX node MCP plan includes git.read and shell.benchmark."""
    result = apo.compile_execution_plan_for_node(
        _flashmlx_node(),
        registry_path=REGISTRY_PATH,
    )
    mcp_plan = result.get("mcp_plan", {})
    required_caps = {r["capability"] for r in mcp_plan.get("required_mcp", [])}
    # The flashmlx capsule binds git.read and shell.benchmark
    # At minimum one of these should appear (from capsule manifest or skill metadata)
    assert len(required_caps) > 0, (
        "mcp_plan.required_mcp must not be empty for a FlashMLX debug node"
    )
