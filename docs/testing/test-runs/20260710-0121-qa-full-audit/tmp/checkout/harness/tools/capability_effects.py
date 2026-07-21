#!/usr/bin/env python3
"""Use→effect evidence updater for Solar capability injection.

This module connects three observable artifacts:
1. dispatch `.intent.json` says what Solar made visible to the worker.
2. handoff/eval files say what the worker/evaluator actually cited.
3. sys_resource_usage records the use/effect telemetry for audit and evolution.

It does not claim access to private model reasoning.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from resource_telemetry import record_usage
except Exception:  # pragma: no cover - fail-open in copied test fixtures
    record_usage = None  # type: ignore


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-")
    return safe or "unknown"


def _read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _read_json(path: str | Path | None) -> dict[str, Any]:
    text = _read_text(path)
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _terms_for_capability(item: dict[str, Any]) -> list[str]:
    terms = [str(item.get("provider") or "")]
    terms.extend(str(x) for x in item.get("capabilities") or [])
    scorecard = item.get("scorecard") if isinstance(item.get("scorecard"), dict) else {}
    if scorecard:
        terms.append(str(scorecard.get("provider_id") or ""))
        terms.append(str(scorecard.get("runtime_backend") or ""))
    return sorted({t.strip() for t in terms if t and t.strip()}, key=len, reverse=True)


def _evidence_matches(capabilities: list[dict[str, Any]], evidence_text: str) -> list[dict[str, Any]]:
    low = evidence_text.lower()
    matches: list[dict[str, Any]] = []
    for item in capabilities:
        provider = str(item.get("provider") or "unknown")
        matched_terms = []
        for term in _terms_for_capability(item):
            if term and term.lower() in low:
                matched_terms.append(term)
        if matched_terms:
            matches.append({
                "provider": provider,
                "capabilities": item.get("capabilities") or [],
                "matched_terms": matched_terms[:8],
            })
    return matches


def _verdict_from(eval_text: str, eval_json: dict[str, Any], explicit: str = "") -> str:
    if explicit:
        return explicit.strip().lower()
    verdict = str(eval_json.get("verdict") or eval_json.get("status") or "").strip().lower()
    if verdict:
        return verdict
    m = re.search(r"\b(PASS|FAIL|FAILED|PASSED)\b", eval_text, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def scan_effect(
    dispatch_file: str | Path,
    *,
    handoff_file: str | Path | None = None,
    eval_file: str | Path | None = None,
    eval_json_file: str | Path | None = None,
    verdict: str = "",
    record_db: bool = True,
) -> dict[str, Any]:
    dispatch = Path(dispatch_file)
    sidecar = dispatch.with_name(dispatch.name + ".intent.json")
    data = _read_json(sidecar)
    if not data:
        return {"ok": False, "reason": "intent_sidecar_missing_or_invalid", "sidecar": str(sidecar)}

    capabilities = [c for c in data.get("capabilities") or [] if isinstance(c, dict)]
    handoff_text = _read_text(handoff_file)
    eval_text = _read_text(eval_file)
    eval_json = _read_json(eval_json_file)
    evidence_text = "\n".join([handoff_text, eval_text, json.dumps(eval_json, ensure_ascii=False)])
    matches = _evidence_matches(capabilities, evidence_text)
    normalized_verdict = _verdict_from(eval_text, eval_json, explicit=verdict)
    eval_passed = normalized_verdict in {"pass", "passed", "ok"}
    worker_used = bool(matches)

    if worker_used and eval_passed:
        status = "eval_passed_with_worker_evidence"
    elif worker_used:
        status = "worker_evidence_present"
    elif eval_passed:
        status = "eval_passed_without_worker_evidence"
    else:
        status = "no_worker_evidence"

    effect = {
        "status": status,
        "worker_used": worker_used,
        "eval_passed": eval_passed,
        "verdict": normalized_verdict,
        "used_providers": [m["provider"] for m in matches],
        "evidence": matches,
        "evidence_files": {
            "handoff": str(handoff_file or ""),
            "eval": str(eval_file or ""),
            "eval_json": str(eval_json_file or ""),
        },
        "boundary": "Observable handoff/eval evidence only; does not inspect private model reasoning.",
    }
    data["effect"] = effect
    sidecar.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    telemetry_written = False
    if record_db and record_usage is not None:
        telemetry_written = bool(record_usage(
            "tool",
            "solar-capability-effect-recorder",
            intent="capability.effect.scan",
            input_summary=str(dispatch),
            success=worker_used or eval_passed,
            output_summary=f"status={status}; providers={','.join(effect['used_providers']) or 'N/A'}",
            error="" if worker_used or eval_passed else "no observable worker/eval evidence",
            description="Solar-Harness use-to-effect scanner for dispatch intent sidecars, handoff and eval evidence.",
            keywords=["capability", "effect", "handoff", "eval", "activation-proof"],
            config={"dispatch_file": str(dispatch), "sidecar": str(sidecar)},
        ))
        for provider in effect["used_providers"]:
            record_usage(
                "tool",
                f"capability-effect-{_safe_name(provider)}",
                intent="capability.effect.provider_used",
                input_summary=str(dispatch),
                success=eval_passed,
                output_summary=f"provider={provider}; verdict={normalized_verdict or 'N/A'}; status={status}",
                description=f"Observable worker/eval evidence for capability provider {provider}.",
                keywords=["capability", "provider", provider],
                config={"provider": provider, "dispatch_file": str(dispatch)},
            )

    return {
        "ok": True,
        "dispatch_file": str(dispatch),
        "sidecar": str(sidecar),
        "effect": effect,
        "telemetry_written": telemetry_written,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="capability_effects.py")
    ap.add_argument("dispatch_file")
    ap.add_argument("--handoff", default="")
    ap.add_argument("--eval", dest="eval_file", default="")
    ap.add_argument("--eval-json", default="")
    ap.add_argument("--verdict", default="")
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = scan_effect(
        args.dispatch_file,
        handoff_file=args.handoff,
        eval_file=args.eval_file,
        eval_json_file=args.eval_json,
        verdict=args.verdict,
        record_db=not args.no_db,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"capability effect: {result.get('effect', {}).get('status', result.get('reason', 'unknown'))}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
