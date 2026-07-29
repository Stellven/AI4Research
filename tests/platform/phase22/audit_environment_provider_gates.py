"""Classify Phase 22's heuristic environment/provider tags after execution.

The atomic matrix deliberately used a broad keyword rule when an exact test
binding was unavailable.  This audit separates genuine external gates from
local configuration gaps, manual oracles, implementation boundaries, and
ordinary selector-review work.  A passing related suite is evidence that the
environment gate is resolved; it is not automatically an atomic PASS binding.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MATRIX_PATH = HERE / "atomic_feature_matrix.json"
OUTPUT_PATH = HERE / "environment_provider_gate_audit.json"

LOCAL = "CONFIG_RESOLVED_EXECUTABLE_EVIDENCE_AVAILABLE"
PASSED = "CONFIG_RESOLVED_ATOMIC_TEST_PASSED"
FAILED = "CONFIG_RESOLVED_TEST_FAILED"
BINDING = "ATOMIC_BINDING_GAP_NOT_CONFIG"
EXTERNAL = "EXTERNAL_CREDENTIAL_OR_ACCOUNT_REQUIRED"
PLATFORM = "PLATFORM_OR_HARDWARE_REQUIRED"
MANUAL = "MANUAL_ORACLE_NOT_CONFIG"
BOUNDARY = "IMPLEMENTATION_BOUNDARY_NOT_CONFIG"


L2_DISPOSITION = {
    # Workflow
    "Constraint Resolution": BINDING,
    "Search Strategy Formation": LOCAL,
    "Signal Organization": LOCAL,
    "Technical Opportunity Screening": BINDING,
    "Falsifiability Screening & Hypothesis Contracting": LOCAL,
    "POC Implementation Environment Preparation": BINDING,
    "Benchmark Protocol & Asset Preparation": LOCAL,
    "Benchmark Execution": FAILED,
    "Metrics & Run Evidence Collection": LOCAL,
    "Experimental, Reasoning & External Validity Review": MANUAL,
    "Delivery Planning & Evidence Handoff": LOCAL,
    "User-Facing Deliverable Generation": LOCAL,
    "Authorized Distribution, Knowledge Transfer & Lifecycle Closure": LOCAL,
    # Foundation
    "Capsule Invocation & Composition": LOCAL,
    "Logical-to-Physical Matching, Selection & Binding": LOCAL,
    "Operator Runtime Evaluation & Capability Profiling": LOCAL,
    "Evaluator-Driven Operator Evolution": BINDING,
    "Performance, Cost & Benchmark Evaluator": FAILED,
    "Model Routing & Selection": FAILED,
    "Model Usage Auditing": LOCAL,
    "Text-Based Artifacts (GEPA / MIPROv2 / TextGrad)": LOCAL,
    "Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL)": LOCAL,
    "DAG and Agent Organization (AFlow / MCTS / ADAS)": BINDING,
    "DAG Scheduler, TaskGraph Readiness & Operator Binding": LOCAL,
    "Execution Admission, Lease & Concurrency Control": LOCAL,
    "Main Loop Dispatch & Runtime Supervision": LOCAL,
    "Constraint Compilation": LOCAL,
    "Build Preparation": LOCAL,
    "Verification Asset Construction": LOCAL,
    "Defect Repair": BINDING,
    "Runtime Deliverable Construction": LOCAL,
    # Vertical
    "Runtime status visibility": LOCAL,
    "Resource Usage, Cost & Capacity Management": LOCAL,
    "Windows App": LOCAL,
    "MacOS App": PLATFORM,
    "MacOS CLI": PLATFORM,
    "Linux Cli": LOCAL,
    "Web Application & Status Service": LOCAL,
    "CLI": LOCAL,
    "GUI": LOCAL,
    "TUI": LOCAL,
    "Authentication & Session Security": LOCAL,
    "Privacy & Personal Data Controls": BINDING,
    "Wechat": LOCAL,
    "TMUX": FAILED,
    "LLM Config": FAILED,
    "Cost/Budget Settings": LOCAL,
    "Cluster setting": LOCAL,
}

EVIDENCE = {
    PASSED: (
        "The required local/provider configuration was supplied or controlled, "
        "and an exact executable atomic selector passed without exposing credentials."
    ),
    LOCAL: (
        "The relevant suite executed with an isolated HOME and local fake/mock "
        "configuration; exact atomic selector review may still be required."
    ),
    FAILED: (
        "The required runtime/dependencies were configured and the relevant "
        "suite executed, but at least one assertion failed; this is not an "
        "environment blocker."
    ),
    BINDING: (
        "The keyword-based environment tag was a false positive. The remaining "
        "gap is an assertion-level atomic binding or behavior test, not machine "
        "configuration."
    ),
    EXTERNAL: (
        "A live authenticated provider/account decision remains. No provider "
        "credential was present and no paid/live call was authorized."
    ),
    PLATFORM: (
        "This behavior requires a native platform, packaged application, GUI "
        "session, or real-hardware runner not available in the current test host."
    ),
    MANUAL: (
        "Scientific/external validity needs domain evidence and reviewer judgment; "
        "installing a dependency cannot create a reliable automated oracle."
    ),
    BOUNDARY: (
        "The L2 contract explicitly calls this dimension unsupported or a stub; "
        "it must be classified as an implementation boundary, not a config gap."
    ),
}


def disposition(row: dict) -> str:
    l2 = row["level_2_feature"]
    atom = row["atomic_feature_name"].lower()

    if l2 == "Verification Asset Construction" and "live-opt-in" in atom:
        return PASSED if "provider" in atom else PLATFORM
    if l2 == "Authentication & Session Security" and atom in {
        "provider authenticated",
        "login start",
        "login status",
    }:
        return PASSED
    if l2 == "Windows App" and atom in {
        "portable package contents",
        "first-run install",
        "backend launch",
        "backend attach",
        "autostart install",
        "autostart remove",
        "repair",
        "sync",
        "keep-data uninstall",
        "diagnostics",
        "real-hardware manual gate",
    }:
        return PLATFORM
    if l2 == "Web Application & Status Service" and atom == "packaged electron attachment":
        return PLATFORM
    if l2 == "GUI" and atom == "responsive packaged view":
        return PLATFORM
    if atom.startswith("unsupported ") or atom == "stub topology not live":
        return BOUNDARY
    return L2_DISPOSITION[l2]


def main() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    source_rows = [
        row
        for row in matrix["atomic_features"]
        if row["test_generation_status"] == "TAGGED_NOT_GENERATED_ENVIRONMENT_GATED"
    ]
    if len(source_rows) != 295:
        raise RuntimeError(f"Expected 295 heuristic gate rows, found {len(source_rows)}")

    rows = []
    counts = Counter()
    l2s: dict[str, set[str]] = {}
    for source in source_rows:
        value = disposition(source)
        counts[value] += 1
        l2s.setdefault(value, set()).add(source["level_2_feature"])
        rows.append(
            {
                "atomic_feature_id": source["atomic_feature_id"],
                "sheet": source["sheet"],
                "level_2_feature": source["level_2_feature"],
                "atomic_feature_name": source["atomic_feature_name"],
                "gate_disposition": value,
                "atomic_result": (
                    "PASS"
                    if value == PASSED
                    else "FAIL"
                    if value == FAILED
                    else "BLOCKED_EXTERNAL"
                    if value in {EXTERNAL, PLATFORM}
                    else "BLOCKED_IMPLEMENTATION"
                    if value == BOUNDARY
                    else "NEEDS_EXACT_ATOMIC_BINDING"
                ),
                "reason": EVIDENCE[value],
            }
        )

    payload = {
        "schema": "phase22.environment_provider_gate_audit.v1",
        "audited_at": "2026-07-27",
        "source": str(MATRIX_PATH.relative_to(HERE.parents[2])).replace("\\", "/"),
        "policy": (
            "A keyword-derived environment/provider tag is not proof of a missing "
            "configuration. Passing related suites only resolves the environment "
            "gate; it does not fabricate an assertion-level atomic binding."
        ),
        "counts": dict(sorted(counts.items())),
        "l2_features_by_disposition": {
            key: sorted(value) for key, value in sorted(l2s.items())
        },
        "atomic_features": rows,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
