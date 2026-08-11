import json
import hashlib
import sys
from pathlib import Path


def check_handoff_package(path):
    package_path = Path(path).resolve()
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    required = [
        "schema",
        "status",
        "experiment_id",
        "environment",
        "integration",
        "conformance",
        "provenance",
        "components",
        "component_hashes",
        "replay",
        "evidence_ids",
        "known_constraints",
    ]
    missing = [item for item in required if item not in payload]
    if missing:
        return {"ok": False, "error": f"missing fields: {missing}", "payload": payload}

    if payload.get("schema") != "autosci_experiment_poc_handoff.v1" or payload.get("status") != "completed":
        return {"ok": False, "error": "handoff package schema/status is not completed", "payload": payload}
    integration = payload.get("integration") if isinstance(payload.get("integration"), dict) else {}
    if integration.get("approved_argv") != integration.get("executed_argv"):
        return {"ok": False, "error": "executed argv does not match approved argv", "payload": payload}
    if integration.get("exit_code") != 0 or integration.get("result_collected") is not True:
        return {"ok": False, "error": "runtime execution was not completed and collected", "payload": payload}
    conformance = payload.get("conformance") if isinstance(payload.get("conformance"), dict) else {}
    if not conformance.get("approval_contract_verified") or not conformance.get("runtime_semantic_verified"):
        return {"ok": False, "error": "handoff package lacks verified approval/runtime conformance", "payload": payload}

    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    required_components = {
        "experiment_plan",
        "runner",
        "dataset",
        "allowlist",
        "manifest",
        "expected_result",
        "runtime_evidence",
        "result",
        "lease_report",
    }
    allowed_components = {*required_components, "lease_recovery_audit"}
    if not required_components.issubset(components) or not set(components).issubset(allowed_components):
        return {
            "ok": False,
            "error": f"component set mismatch: expected {sorted(required_components)}, got {sorted(components)}",
            "payload": payload,
        }
    resolved = {}
    component_hashes = payload.get("component_hashes") if isinstance(payload.get("component_hashes"), dict) else {}
    for name, raw in components.items():
        component = Path(str(raw))
        candidates = [component] if component.is_absolute() else [parent / component for parent in [package_path.parent, *package_path.parents]]
        found = next((candidate for candidate in candidates if candidate.is_file()), None)
        if found is None:
            return {"ok": False, "error": f"component is missing: {name}={raw}", "payload": payload}
        resolved[name] = str(found)
        digest = component_hashes.get(name) if isinstance(component_hashes.get(name), dict) else {}
        if digest.get("path") != raw or digest.get("sha256") != hashlib.sha256(found.read_bytes()).hexdigest():
            return {"ok": False, "error": f"component hash mismatch: {name}", "payload": payload}
        if digest.get("bytes") != found.stat().st_size:
            return {"ok": False, "error": f"component byte count mismatch: {name}", "payload": payload}
    if not payload.get("evidence_ids"):
        return {"ok": False, "error": "no embedded evidence ids", "payload": payload}
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    if provenance.get("source_experiment_plan_sha256") != component_hashes.get("experiment_plan", {}).get("sha256"):
        return {"ok": False, "error": "experiment plan provenance mismatch", "payload": payload}
    replay = payload.get("replay") if isinstance(payload.get("replay"), dict) else {}
    expected_replay_argv = [
        integration.get("approved_argv", [""])[0],
        components.get("runner"),
        components.get("dataset"),
        replay.get("expected_output"),
    ]
    if replay.get("argv") != expected_replay_argv:
        return {"ok": False, "error": "replay argv is not bound to durable components", "payload": payload}

    return {
        "ok": True,
        "error": None,
        "payload": {
            "experiment_id": payload.get("experiment_id"),
            "status": payload.get("status"),
            "schema": payload.get("schema"),
            "component_count": len(resolved),
            "approved_argv": integration.get("approved_argv"),
            "executed_argv": integration.get("executed_argv"),
            "evidence_ids": payload.get("evidence_ids"),
        },
    }


def main(argv):
    if len(argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: python check_poc_handoff.py <product-result-json>"}, ensure_ascii=False))
        return 2
    result = check_handoff_package(argv[1])
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
