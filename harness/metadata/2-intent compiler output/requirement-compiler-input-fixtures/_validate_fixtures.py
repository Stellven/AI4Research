from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[3]
LIB_ROOT = REPO_ROOT / "harness" / "lib"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

import intent_compiler


EXPECTED_FILES = {"intent_ir.json"}
TEMPLATE_PATHS = {
    "intent_ir.json": ROOT.parent / "intent_ir" / "intent_ir.json",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"Expected object JSON: {path}")
    return payload


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_template_shape(name: str, payload: dict[str, Any]) -> None:
    template = load_json(TEMPLATE_PATHS[name])
    assert set(payload) == set(template), (name, set(payload) ^ set(template))
    for field in ("goals", "outcomes", "constraints", "ambiguities", "unknowns", "checks", "decisions"):
        template_rows = template.get(field)
        payload_rows = payload.get(field)
        if isinstance(template_rows, list) and template_rows and isinstance(payload_rows, list):
            template_keys = set(template_rows[0])
            for row in payload_rows:
                assert set(row) == template_keys, (name, field, set(row) ^ template_keys)


def validate_source_spans(intent: dict[str, Any], prompt: str, case_id: str) -> None:
    for collection in ("goals", "outcomes", "constraints", "ambiguities"):
        for row in intent.get(collection, []):
            for span in row.get("source_spans", []):
                assert isinstance(span, list) and len(span) == 2, (case_id, collection, span)
                start, end = span
                assert isinstance(start, int) and isinstance(end, int), (case_id, collection, span)
                assert 0 <= start < end <= len(prompt), (case_id, collection, span, len(prompt))


def validate_case(case: dict[str, Any]) -> None:
    case_id = case["case_id"]
    case_dir = ROOT / case["bundle_path"]
    assert case_dir.is_dir(), f"Missing case directory: {case_id}"
    actual_files = {path.name for path in case_dir.iterdir() if path.is_file()}
    assert actual_files == EXPECTED_FILES, (case_id, actual_files)
    assert set(case["artifacts"]) == EXPECTED_FILES, (case_id, case["artifacts"])
    assert case["expected_consumer"] == "requirement_compiler", case_id

    prompt = case["prompt"]
    raw_hash = sha256_bytes(prompt.encode("utf-8"))
    assert raw_hash == case["raw_text_sha256"], case_id

    intent_path = case_dir / "intent_ir.json"
    intent = load_json(intent_path)
    validate_template_shape("intent_ir.json", intent)
    intent_hash = sha256_bytes(intent_path.read_bytes())

    assert intent["schema_version"] == "solar.intent_ir.v3", case_id
    assert intent["artifact_role"] == "metadata_contract_example_not_live_execution", case_id
    assert intent["generation"] == 0, case_id
    assert intent["producer"]["method"] == "model", case_id
    assert intent["intent_ir_id"] == case["intent_ir_id"], case_id
    assert intent["raw_intent_ref"]["raw_intent_id"] == case["raw_intent_id"], case_id
    assert intent["raw_intent_ref"]["raw_text_sha256"] == raw_hash, case_id
    assert intent_hash == case["intent_ir_sha256"], case_id

    identifiers = []
    identifiers.extend(row["goal_id"] for row in intent["goals"])
    identifiers.extend(row["outcome_id"] for row in intent["outcomes"])
    identifiers.extend(row["constraint_id"] for row in intent["constraints"])
    identifiers.extend(row["ambiguity_id"] for row in intent["ambiguities"])
    identifiers.extend(row["unknown_id"] for row in intent["unknowns"])
    assert len(identifiers) == len(set(identifiers)), (case_id, identifiers)
    known_refs = set(identifiers)
    for unknown in intent["unknowns"]:
        assert unknown["derived_from"], (case_id, unknown)
        assert set(unknown["derived_from"]) <= known_refs, (case_id, unknown)
    assert not intent["conflicts"], case_id
    assert not any(row["blocking"] for row in intent["ambiguities"]), case_id
    validate_source_spans(intent, prompt, case_id)

    mechanical = intent_compiler.validate_intent(
        {
            "raw_intent_id": case["raw_intent_id"],
            "raw": {"text": prompt, "sha256": raw_hash},
        },
        intent,
        generation=0,
    )
    assert mechanical["status"] == "pass", (case_id, mechanical["errors"])

def main() -> None:
    catalog = load_json(ROOT / "fixture_catalog.json")
    assert catalog["schema_version"] == "solar.requirement_compiler_input_fixture_catalog.v1"
    assert catalog["producer"] == "intent_compiler"
    assert catalog["consumer"] == "requirement_compiler"
    assert catalog["case_count"] == 25
    assert len(catalog["cases"]) == 25

    case_ids = [case["case_id"] for case in catalog["cases"]]
    assert len(case_ids) == len(set(case_ids)) == 25
    actual_dirs = {path.name for path in ROOT.iterdir() if path.is_dir()}
    assert actual_dirs == set(case_ids), (actual_dirs - set(case_ids), set(case_ids) - actual_dirs)
    for case in catalog["cases"]:
        validate_case(case)

    categories = Counter(case["category"] for case in catalog["cases"])
    print(
        json.dumps(
            {
                "ok": True,
                "case_count": len(catalog["cases"]),
                "artifact_count": len(catalog["cases"]) * len(EXPECTED_FILES),
                "categories": dict(sorted(categories.items())),
                "producer": catalog["producer"],
                "consumer": catalog["consumer"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
