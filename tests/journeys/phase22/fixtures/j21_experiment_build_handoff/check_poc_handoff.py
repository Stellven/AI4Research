import json
import sys
from pathlib import Path


def check_handoff_package(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = ["action", "status", "schema", "result_path", "evidence_path", "evidence"]
    missing = [item for item in required if item not in payload]
    if missing:
        return {"ok": False, "error": f"missing fields: {missing}", "payload": payload}

    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    artifacts = evidence.get("artifacts") if isinstance(evidence.get("artifacts"), list) else []
    outputs = evidence.get("outputs") if isinstance(evidence.get("outputs"), dict) else {}
    runtime = outputs.get("runtime") if isinstance(outputs.get("runtime"), dict) else {}
    result = outputs.get("result") if isinstance(outputs.get("result"), dict) else {}
    command = runtime.get("command_run") or result.get("command_run") or ""
    evidence_ids = runtime.get("evidence_ids") or result.get("evidence_ids") or []

    if not artifacts:
        return {"ok": False, "error": "no product artifacts listed in embedded evidence", "payload": payload}
    if not str(command).strip():
        return {"ok": False, "error": "no runnable command recorded in embedded evidence", "payload": payload}
    if not evidence_ids:
        return {"ok": False, "error": "no embedded evidence ids", "payload": payload}

    return {
        "ok": True,
        "error": None,
        "payload": {
            "action": payload.get("action"),
            "status": payload.get("status"),
            "schema": payload.get("schema"),
            "artifact_count": len(artifacts),
            "command": command,
            "handoff_path": payload.get("handoff_path", ""),
            "evidence_ids": evidence_ids,
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
