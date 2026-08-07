#!/usr/bin/env bash
# Regression test: DAG worker discovery must advertise status UI/observability
# capabilities so frontend/status nodes are not stranded as no_matching_worker.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST/lib" "$TMPDIR_TEST/config" "$TMPDIR_TEST/run/pane-leases"
cp "$HARNESS_DIR_REAL/lib/graph_node_dispatcher.py" "$TMPDIR_TEST/lib/graph_node_dispatcher.py"
cp "$HARNESS_DIR_REAL/lib/graph_scheduler.py" "$TMPDIR_TEST/lib/graph_scheduler.py"
cp "$HARNESS_DIR_REAL/lib/task_queue.py" "$TMPDIR_TEST/lib/task_queue.py"
cp "$HARNESS_DIR_REAL/lib/pane_lease.py" "$TMPDIR_TEST/lib/pane_lease.py"
cp "$HARNESS_DIR_REAL/lib/solar_skills.py" "$TMPDIR_TEST/lib/solar_skills.py"
cp "$HARNESS_DIR_REAL/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/solar-autopilot-monitor.py"
for optional in capability_effects.py resource_telemetry.py solar_db.py model_registry.py; do
  if [[ -f "$HARNESS_DIR_REAL/lib/$optional" ]]; then
    cp "$HARNESS_DIR_REAL/lib/$optional" "$TMPDIR_TEST/lib/$optional"
  fi
done
for optional_config in model-registry.json solar-user-config.json; do
  if [[ -f "$HARNESS_DIR_REAL/config/$optional_config" ]]; then
    cp "$HARNESS_DIR_REAL/config/$optional_config" "$TMPDIR_TEST/config/$optional_config"
  fi
done

HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" python3 - <<'PY'
import importlib.util
import os
import sys
from pathlib import Path

root = Path(os.environ["HARNESS_DIR"])
sys.path.insert(0, str(root / "lib"))

import graph_node_dispatcher as dispatcher

workers = dispatcher._discover_workers(dry_run=True)
assert workers, "dispatcher has no dry-run workers"
assert any("frontend" in w.get("skills", []) for w in workers), workers
assert any("python" in w.get("skills", []) for w in workers), workers
assert any("shell" in w.get("skills", []) for w in workers), workers
assert any("python-read" in w.get("skills", []) for w in workers), workers
assert any("dataclasses" in w.get("skills", []) for w in workers), workers
assert any("pytest" in w.get("skills", []) for w in workers), workers
assert any("subprocess" in w.get("skills", []) for w in workers), workers
assert any("sqlite3" in w.get("skills", []) for w in workers), workers
assert any("pure-functions" in w.get("skills", []) for w in workers), workers
assert any("time-injection" in w.get("skills", []) for w in workers), workers
assert any("io" in w.get("skills", []) for w in workers), workers
assert any("fsm" in w.get("skills", []) for w in workers), workers
assert any("integration" in w.get("skills", []) for w in workers), workers
assert any("integration-testing" in w.get("skills", []) for w in workers), workers
assert any("integration-tests" in w.get("skills", []) for w in workers), workers
assert any("regression" in w.get("skills", []) for w in workers), workers
assert any("regression-tests" in w.get("skills", []) for w in workers), workers
for skill in ["bash-tests", "jq", "json", "jsonl-tail", "timeouts", "concurrency"]:
    assert any(skill in w.get("skills", []) for w in workers), (skill, workers)
assert any("json-patch" in w.get("skills", []) for w in workers), workers
assert any("api-design" in w.get("skills", []) for w in workers), workers
assert any("data-modeling" in w.get("skills", []) for w in workers), workers
assert any("compatibility" in w.get("skills", []) for w in workers), workers
for skill in ["terminal-ui", "tvs", "vdl", "snapshot", "snapshot-testing", "flask", "http-routing", "http-endpoint", "autopilot-hooks", "json-traversal", "html", "javascript", "vanilla-dom"]:
    assert any(skill in w.get("skills", []) for w in workers), (skill, workers)
for skill in ["stub-llm", "e2e-test", "cli-view-assertion", "negative-control", "verifier", "registry-introspection", "cli-audit", "cli-design", "argparse", "argparse-bridge", "json-schema", "json-shape-inspect", "validation", "technical-writing", "markdown", "regex", "markdown-parse", "evidence-aggregation", "evidence-collection", "evaluator-summary", "handoff-authoring", "traceability-patch", "knowledge-raw-writeback", "architecture-writing", "solar-harness-control-plane", "algorithm_design", "code_impl", "test_generation", "test_execution"]:
    assert any(skill in w.get("skills", []) for w in workers), (skill, workers)
for skill in ["code-audit", "docs-audit", "type-hints", "type-protocols", "state-schema-design", "refactor", "tmux-inspect", "data-aggregation", "shutil", "urllib", "atomic-writes", "hashing", "unittest-mock", "capability-graph", "event-sourcing"]:
    assert any(skill in w.get("skills", []) for w in workers), (skill, workers)
assert any("lazy-import" in w.get("skills", []) for w in workers), workers
assert any("observability" in w.get("capabilities", []) for w in workers), workers
assert any("evidence" in w.get("capabilities", []) for w in workers), workers
assert any("env-passthrough" in w.get("capabilities", []) for w in workers), workers
assert any("metrics" in w.get("capabilities", []) for w in workers), workers
assert any("documentation" in w.get("capabilities", []) for w in workers), workers
for cap in ["harness.context_preflight", "harness.intent", "harness.dispatch_visibility", "harness.contracts", "harness.dag", "harness.status", "harness.model_routing", "dag.validate", "dag.ready_nodes", "dag.join_gate", "activation.proof", "negative_control", "runtime_artifacts", "autopilot.monitor", "autopilot.safe_apply", "pane.deadlock_detection", "lazy-import", "cli", "algorithm_design", "solar-harness-control-plane", "architecture-writing", "code_impl", "test_generation", "test_execution"]:
    assert any(cap in w.get("capabilities", []) for w in workers), (cap, workers)

spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", root / "solar-autopilot-monitor.py")
monitor = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(monitor)
monitor_workers = monitor.graph_workers()
assert monitor_workers, "autopilot has no workers"
assert any("frontend" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("python" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("shell" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("python-read" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("dataclasses" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("pytest" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("subprocess" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("sqlite3" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("pure-functions" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("time-injection" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("io" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("fsm" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("integration" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("integration-testing" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("integration-tests" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("regression" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("regression-tests" in w.get("skills", []) for w in monitor_workers), monitor_workers
for skill in ["bash-tests", "jq", "json", "jsonl-tail", "timeouts", "concurrency"]:
    assert any(skill in w.get("skills", []) for w in monitor_workers), (skill, monitor_workers)
assert any("json-patch" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("api-design" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("data-modeling" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("compatibility" in w.get("skills", []) for w in monitor_workers), monitor_workers
for skill in ["terminal-ui", "tvs", "vdl", "snapshot", "snapshot-testing", "flask", "http-routing", "http-endpoint", "autopilot-hooks", "json-traversal", "html", "javascript", "vanilla-dom"]:
    assert any(skill in w.get("skills", []) for w in monitor_workers), (skill, monitor_workers)
for skill in ["stub-llm", "e2e-test", "cli-view-assertion", "negative-control", "verifier", "registry-introspection", "cli-audit", "cli-design", "argparse", "argparse-bridge", "json-schema", "json-shape-inspect", "validation", "technical-writing", "markdown", "regex", "markdown-parse", "evidence-aggregation", "evidence-collection", "evaluator-summary", "handoff-authoring", "traceability-patch", "knowledge-raw-writeback", "architecture-writing", "solar-harness-control-plane", "algorithm_design", "code_impl", "test_generation", "test_execution"]:
    assert any(skill in w.get("skills", []) for w in monitor_workers), (skill, monitor_workers)
for skill in ["code-audit", "docs-audit", "type-hints", "type-protocols", "state-schema-design", "refactor", "tmux-inspect", "data-aggregation", "shutil", "urllib", "atomic-writes", "hashing", "unittest-mock", "capability-graph", "event-sourcing"]:
    assert any(skill in w.get("skills", []) for w in monitor_workers), (skill, monitor_workers)
assert any("lazy-import" in w.get("skills", []) for w in monitor_workers), monitor_workers
assert any("observability" in w.get("capabilities", []) for w in monitor_workers), monitor_workers
assert any("evidence" in w.get("capabilities", []) for w in monitor_workers), monitor_workers
assert any("env-passthrough" in w.get("capabilities", []) for w in monitor_workers), monitor_workers
assert any("metrics" in w.get("capabilities", []) for w in monitor_workers), monitor_workers
assert any("documentation" in w.get("capabilities", []) for w in monitor_workers), monitor_workers
for cap in ["harness.context_preflight", "harness.intent", "harness.dispatch_visibility", "harness.contracts", "harness.dag", "harness.status", "harness.model_routing", "dag.validate", "dag.ready_nodes", "dag.join_gate", "activation.proof", "negative_control", "runtime_artifacts", "autopilot.monitor", "autopilot.safe_apply", "pane.deadlock_detection", "lazy-import", "cli", "algorithm_design", "solar-harness-control-plane", "architecture-writing", "code_impl", "test_generation", "test_execution"]:
    assert any(cap in w.get("capabilities", []) for w in monitor_workers), (cap, monitor_workers)
PY

echo "PASS worker capability catalog covers frontend/observability/architecture-specialists"
