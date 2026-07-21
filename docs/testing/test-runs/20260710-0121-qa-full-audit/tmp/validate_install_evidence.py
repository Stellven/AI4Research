from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    doctor = json.loads((root / "evidence/commands/phase5_doctor_json.stdout.txt").read_text(encoding="utf-8"))
    receipt_path = root / "tmp/installer-solar/install-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    checks = {
        "doctor_verdict_ok": doctor.get("verdict") == "ok",
        "doctor_paths_all_ok": bool(doctor.get("paths")) and set(doctor["paths"].values()) == {"ok"},
        "doctor_drift_empty": doctor.get("drift") == [],
        "doctor_components_exact": set(doctor.get("components") or []) == {"kernel", "harness", "autosci"},
        "python_minimum_ok": doctor.get("python", {}).get("min_ok") is True,
        "python_imports_ok": set((doctor.get("python", {}).get("harness_imports") or {}).values()) == {"ok"},
        "receipt_exists_and_object": isinstance(receipt, dict) and receipt_path.is_file(),
        "solar_binary_exists": (root / "tmp/installer-solar/bin/solar").is_file(),
        "harness_exists": (root / "tmp/installer-solar/harness/solar-harness.sh").is_file(),
        "autosci_installed": (root / "tmp/installer-solar/.agents/autosci-runtime-source").exists(),
        "all_install_targets_isolated": all(
            str(path.resolve()).startswith(str(root))
            for path in (root / "tmp/installer-solar", root / "tmp/installer-claude", root / "tmp/installer-home")
        ),
        "warnings_do_not_claim_provider_readiness": doctor.get("models", {}).get("zhipu_credentials") == "missing"
        and doctor.get("models", {}).get("claude_cli") == "missing",
    }
    result = {
        "schema": "qa.install_evidence_validation.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "limitations": [
            "Install used --skip-py-deps and pre-existing local dependencies; this is not network/bootstrap parity.",
            "Provider credentials and Claude CLI were intentionally absent; doctor warnings are expected.",
        ],
    }
    output = root / "evidence/install-evidence-validation.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
