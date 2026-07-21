from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
CLASSIFICATION = AUDIT_ROOT / "evidence" / "codex-not-run-phase" / "not-run-scope-classification.csv"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


FEATURES_BY_ID = {row["feature_id"]: row for row in rows(AUDIT_ROOT / "feature-results.csv")}
MAPPINGS_BY_ID = {
    row["feature_id"]: row
    for row in rows(AUDIT_ROOT / "evidence" / "codex-not-run-phase" / "corrected-feature-entrypoint-map.csv")
}
INCLUDED = [
    FEATURES_BY_ID[row["feature_id"]]
    for row in rows(CLASSIFICATION)
    if row["scope_classification"] == "INCLUDED_CODEX_RELEVANT"
]


def path_part(reference: str) -> str:
    value = reference.strip().split("::", 1)[0].strip()
    value = re.sub(r"\s+--?.*$", "", value)
    return value


def resolves(reference: str) -> bool:
    value = path_part(reference)
    if not value:
        return False
    if value.startswith("package.json"):
        return (CHECKOUT / "package.json").is_file()
    if "/" not in value and not Path(value).suffix:
        return False
    return (CHECKOUT / value).exists() or (AUDIT_ROOT / value).exists()


@pytest.mark.parametrize("feature", INCLUDED, ids=[row["feature_id"] for row in INCLUDED])
def test_feature_has_executable_structural_preconditions(feature: dict[str, str]) -> None:
    assert feature["atomic_feature"].strip()
    assert feature["feature_path"].strip()
    assert feature["happy_path_pass_criteria"].strip()
    assert feature["negative_failure_pass_criteria"].strip()
    assert feature["fail_criteria"].strip()

    mapping = MAPPINGS_BY_ID[feature["feature_id"]]
    implementation_refs = [item for item in mapping["implementation_files_functions"].split(";") if item.strip()]
    entrypoint_refs = [item for item in mapping["discovered_entrypoints"].split(";") if item.strip()]
    assert any(resolves(item) for item in implementation_refs + entrypoint_refs), (
        "no mapped entrypoint or implementation reference resolves in the locked checkout"
    )

    test_refs = [item for item in feature["existing_tests"].split(";") if item.strip()]
    if test_refs:
        assert any(resolves(item) for item in test_refs), "mapped test references do not resolve in the locked checkout"
