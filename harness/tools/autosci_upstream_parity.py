#!/usr/bin/env python3
"""Configurable same-prompt upstream AutoSci versus Solar parity runner.

The upstream command must be a JSON argv array and emit one JSON object with
the semantic fields compared below. Use ``{prompt}`` in an argv item to inject
the exact prompt. No shell is used.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


HARNESS = Path(__file__).resolve().parents[1]
BRIDGE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
FIELDS = (
    "intent",
    "workflow_stages",
    "input_type",
    "language",
    "deliverable_type",
    "required_evidence",
)


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    if isinstance(value, list):
        return sorted(_normalized(item) for item in value)
    return value


def _solar_semantics(prompt: str, artifact_root: Path, sources: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    command = [
        sys.executable,
        str(BRIDGE),
        "research",
        "--prompt",
        prompt,
        "--run-id",
        "upstream-parity-solar",
        "--artifact-root",
        str(artifact_root),
        "--max-steps",
        "1",
    ]
    for source in sources:
        command.extend(["--source", source])
    proc = subprocess.run(command, text=True, encoding="utf-8", capture_output=True, check=False)
    if not proc.stdout:
        raise RuntimeError(f"Solar parity entrypoint produced no JSON (exit {proc.returncode})")
    payload = json.loads(proc.stdout)
    contract = json.loads(Path(payload["task_contract_path"]).read_text(encoding="utf-8"))
    route = payload.get("route") or {}
    constraints = (contract.get("constraints") or {}).get("user_constraints") or {}
    required_evidence: list[str] = []
    if constraints.get("claim_evidence_separation_required"):
        required_evidence.append("claim_evidence_separation")
    minimum_sources = constraints.get("minimum_traceable_sources")
    if minimum_sources:
        required_evidence.append(f"minimum_traceable_sources:{minimum_sources}")
    if constraints.get("detected_urls") or sources:
        required_evidence.append("source_provenance")
    semantics = {
        "intent": contract.get("user_intent", ""),
        "workflow_stages": [route.get("start_stage", ""), route.get("workflow_kind", "")],
        "input_type": route.get("seed_kind", ""),
        "language": (contract.get("deliverable") or {}).get("language", ""),
        "deliverable_type": (contract.get("deliverable") or {}).get("delivery_type", ""),
        "required_evidence": required_evidence,
    }
    return semantics, payload


def _upstream_argv(raw: str, prompt: str) -> list[str]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) for item in parsed):
        raise ValueError("upstream command must be a non-empty JSON string array")
    return [item.replace("{prompt}", prompt) for item in parsed]


def run_parity(
    *,
    prompt: str,
    artifact_root: Path,
    sources: list[str],
    upstream_command_json: str,
) -> tuple[int, dict[str, Any]]:
    solar, solar_payload = _solar_semantics(prompt, artifact_root / "solar", sources)
    if not upstream_command_json:
        return 2, {
            "status": "PARTIAL",
            "reason": "upstream_command_not_configured",
            "solar": solar,
            "solar_task_contract_path": solar_payload.get("task_contract_path", ""),
            "comparisons": {},
        }

    argv = _upstream_argv(upstream_command_json, prompt)
    upstream_proc = subprocess.run(
        argv,
        input=prompt,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=120,
    )
    if upstream_proc.returncode != 0 or not upstream_proc.stdout:
        return 2, {
            "status": "PARTIAL",
            "reason": "upstream_execution_unavailable",
            "upstream_exit_code": upstream_proc.returncode,
            "solar": solar,
            "comparisons": {},
        }
    upstream = json.loads(upstream_proc.stdout)
    comparisons = {
        field: {
            "match": _normalized(solar.get(field)) == _normalized(upstream.get(field)),
            "solar": solar.get(field),
            "upstream": upstream.get(field),
        }
        for field in FIELDS
    }
    matches = all(item["match"] for item in comparisons.values())
    return (0 if matches else 1), {
        "status": "PASS" if matches else "FAIL",
        "solar": solar,
        "upstream": upstream,
        "comparisons": comparisons,
        "solar_task_contract_path": solar_payload.get("task_contract_path", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument(
        "--upstream-command-json",
        default=os.environ.get("SOLAR_AUTOSCI_UPSTREAM_COMMAND_JSON", ""),
        help="JSON argv array; supports {prompt}; defaults to SOLAR_AUTOSCI_UPSTREAM_COMMAND_JSON",
    )
    args = parser.parse_args(argv)
    code, result = run_parity(
        prompt=args.prompt,
        artifact_root=Path(args.artifact_root),
        sources=list(args.source),
        upstream_command_json=args.upstream_command_json,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
