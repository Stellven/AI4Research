from __future__ import annotations

import json

from harness.lib.research.external_validity import evaluate_external_holdout


def _write(tmp_path, rows):
    path = tmp_path / "external.json"
    path.write_text(json.dumps({"claim_id": "claim-1", "minimum_site_support_rate": 0.5, "observations": rows}), encoding="utf-8")
    return path


def _rows():
    return [
        {"split": "development", "observation_id": "d1", "site_id": "lab-a", "source_id": "dev-1", "provider_family": "internal", "evidence_id": "ev-d1", "claim_supported": True},
        {"split": "external_holdout", "observation_id": "h1", "site_id": "site-b", "source_id": "doi:1", "provider_family": "crossref", "evidence_id": "ev-h1", "claim_supported": True},
        {"split": "external_holdout", "observation_id": "h2", "site_id": "site-c", "source_id": "openalex:2", "provider_family": "openalex", "evidence_id": "ev-h2", "claim_supported": True},
    ]


def test_accepts_source_isolated_multi_site_holdout_but_bounds_claim(tmp_path):
    result = evaluate_external_holdout(_write(tmp_path, _rows()))
    assert result["status"] == "accepted"
    assert result["claim_boundary"]["supported_on_observed_external_sites"] is True
    assert result["claim_boundary"]["supports_universal_generalization"] is False
    assert {item["site_id"] for item in result["site_results"]} == {"site-b", "site-c"}


def test_rejects_development_source_leakage(tmp_path):
    rows = _rows()
    rows[1]["source_id"] = "dev-1"
    result = evaluate_external_holdout(_write(tmp_path, rows))
    assert result["status"] == "rejected"
    assert "development_holdout_source_contamination" in result["errors"]


def test_rejects_site_specific_failure_and_single_provider(tmp_path):
    rows = _rows()
    rows[1]["claim_supported"] = False
    rows[2]["provider_family"] = "crossref"
    result = evaluate_external_holdout(_write(tmp_path, rows))
    assert result["status"] == "rejected"
    assert "external_site_threshold_failed:site-b" in result["errors"]
    assert "external_holdout_provider_diversity_insufficient" in result["errors"]

