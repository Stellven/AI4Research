from __future__ import annotations

import hashlib
import json

from harness.lib.research.external_validity import evaluate_external_holdout


def _save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observation(split, observation_id, site_id, organization, successes=8, lineage=None, evidence_id=None):
    return {
        "schema": "solar.external_observation.v1",
        "split": split,
        "observation_id": observation_id,
        "evidence_id": evidence_id or "evidence-" + observation_id,
        "source_lineage_id": lineage or "lineage-" + observation_id,
        "collected_at": "2026-08-03T00:00:00Z",
        "site": {"site_id": site_id, "kind": "experimental_site", "organization_id": organization, "collection_protocol_id": "protocol-v1"},
        "metric": {"name": "success_rate", "numerator": successes, "denominator": 10},
    }


def _bundle(tmp_path, mutate=None):
    plan = {
        "claim_id": "claim-1", "metric_name": "success_rate", "minimum_site_support_rate": 0.75,
        "registered_at": "2026-08-01T00:00:00Z",
        "authority": {"authority_id": "external-owner", "role": "independent_protocol_owner"},
        "development_site_ids": ["dev-lab"], "external_holdout_site_ids": ["lab-b", "lab-c"],
    }
    rows = [
        _observation("development", "dev-1", "dev-lab", "org-dev", 9),
        _observation("external_holdout", "hold-b", "lab-b", "org-b", 8),
        _observation("external_holdout", "hold-c", "lab-c", "org-c", 9),
    ]
    if mutate:
        mutate(plan, rows)
    plan_path = tmp_path / "plan.json"
    plan_hash = _save(plan_path, plan)
    refs = []
    for index, row in enumerate(rows):
        item = tmp_path / "evidence" / f"{index}.json"
        refs.append({"path": str(item.relative_to(tmp_path)), "sha256": _save(item, row)})
    manifest = tmp_path / "manifest.json"
    _save(manifest, {"external_plan": {"path": "plan.json", "sha256": plan_hash}, "observations": refs})
    return manifest, plan_hash


def test_accepts_hashed_preregistered_metrics_but_bounds_claim(tmp_path):
    result = evaluate_external_holdout(*_bundle(tmp_path))
    assert result["status"] == "accepted", result["errors"]
    assert result["claim_boundary"]["supported_on_preregistered_external_sites"] is True
    assert result["claim_boundary"]["supports_universal_generalization"] is False
    assert {row["support_rate"] for row in result["site_results"]} == {0.8, 0.9}
    assert len(result["evidence_artifacts"]) == 3


def test_rejects_tampered_evidence_after_manifest_hash(tmp_path):
    manifest, trusted = _bundle(tmp_path)
    path = tmp_path / "evidence/1.json"
    payload = json.loads(path.read_text())
    payload["metric"]["numerator"] = 10
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = evaluate_external_holdout(manifest, trusted)
    assert result["status"] == "rejected"
    assert "observation_evidence_hash_mismatch:1" in result["errors"]


def test_rejects_static_boolean_instead_of_derived_counts(tmp_path):
    def attack(plan, rows):
        rows[1]["claim_supported"] = True
        rows[1]["metric"] = {"name": "success_rate", "numerator": True, "denominator": True}
    result = evaluate_external_holdout(*_bundle(tmp_path, attack))
    assert result["status"] == "rejected"
    assert "observation_metric_counts_invalid:1" in result["errors"]


def test_rejects_database_provider_label_as_fake_site(tmp_path):
    def attack(plan, rows):
        plan["external_holdout_site_ids"] = ["crossref", "openalex"]
        for row, label in zip(rows[1:], ("crossref", "openalex")):
            row["site"] = {"site_id": label, "provider_family": label}
    result = evaluate_external_holdout(*_bundle(tmp_path, attack))
    assert result["status"] == "rejected"
    assert "experimental_site_identity_incomplete:1" in result["errors"]
    assert "experimental_site_identity_incomplete:2" in result["errors"]


def test_rejects_shared_source_and_evidence_ids(tmp_path):
    def attack(plan, rows):
        rows[2]["source_lineage_id"] = rows[1]["source_lineage_id"]
        rows[2]["evidence_id"] = rows[1]["evidence_id"]
    result = evaluate_external_holdout(*_bundle(tmp_path, attack))
    assert result["status"] == "rejected"
    assert "source_lineage_id_not_unique" in result["errors"]
    assert "evidence_id_not_unique" in result["errors"]


def test_rejects_embedded_or_posthoc_plan(tmp_path):
    manifest, trusted = _bundle(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["external_plan"] = {"claim_id": "fake", "minimum_site_support_rate": 0}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    result = evaluate_external_holdout(manifest, trusted)
    assert result["status"] == "rejected"
    assert "external_plan_missing" in result["errors"]


def test_rejects_manifest_self_attested_plan_without_out_of_band_anchor(tmp_path):
    manifest, _ = _bundle(tmp_path)
    result = evaluate_external_holdout(manifest)
    assert result["status"] == "rejected"
    assert "external_plan_not_matched_by_out_of_band_trust_anchor" in result["errors"]


def test_rejects_plan_registered_after_observations(tmp_path):
    def attack(plan, rows):
        plan["registered_at"] = "2026-08-10T00:00:00Z"
    result = evaluate_external_holdout(*_bundle(tmp_path, attack))
    assert result["status"] == "rejected"
    assert "observation_not_post_registration:0" in result["errors"]


def test_rejects_development_holdout_lineage_leakage(tmp_path):
    def attack(plan, rows):
        rows[1]["source_lineage_id"] = rows[0]["source_lineage_id"]
    result = evaluate_external_holdout(*_bundle(tmp_path, attack))
    assert result["status"] == "rejected"
    assert "development_holdout_source_lineage_contamination" in result["errors"]
