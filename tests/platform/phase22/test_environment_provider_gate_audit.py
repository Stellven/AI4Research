"""Integrity checks for the reviewed environment/provider gate audit."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
AUDIT = json.loads(
    (HERE / "environment_provider_gate_audit.json").read_text(encoding="utf-8")
)


def test_every_heuristic_environment_gate_has_one_reviewed_disposition() -> None:
    rows = AUDIT["atomic_features"]
    assert len(rows) == 295
    assert len({row["atomic_feature_id"] for row in rows}) == 295
    assert all(row["gate_disposition"] and row["reason"] for row in rows)


def test_environment_gate_audit_counts_match_rows() -> None:
    actual = Counter(row["gate_disposition"] for row in AUDIT["atomic_features"])
    assert dict(sorted(actual.items())) == AUDIT["counts"]


def test_external_and_platform_gates_never_claim_pass() -> None:
    for row in AUDIT["atomic_features"]:
        if row["gate_disposition"] in {
            "EXTERNAL_CREDENTIAL_OR_ACCOUNT_REQUIRED",
            "PLATFORM_OR_HARDWARE_REQUIRED",
        }:
            assert row["atomic_result"] == "BLOCKED_EXTERNAL"


def test_resolved_provider_and_auth_gates_have_exact_pass_evidence() -> None:
    expected = {
        "P22-AF-FN-058-08",
        "P22-AF-VT-014-05",
        "P22-AF-VT-014-08",
        "P22-AF-VT-014-09",
    }
    resolved = {
        row["atomic_feature_id"]
        for row in AUDIT["atomic_features"]
        if row["gate_disposition"] == "CONFIG_RESOLVED_ATOMIC_TEST_PASSED"
    }
    assert resolved == expected
    assert all(
        row["atomic_result"] == "PASS"
        for row in AUDIT["atomic_features"]
        if row["atomic_feature_id"] in expected
    )
