#!/usr/bin/env python3
"""Generate route-level AutoSci semantic parity audit files.

This tool materializes the current semantic audit state. It deliberately does
not infer full parity from wrappers, route declarations, or runtime proof
presence. A route can be marked semantically full only through an explicit
assessment JSON with passing checks and existing evidence references.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "autosci_semantic_parity_audit_matrix.v1"
AUDIT_SCHEMA = "autosci_semantic_parity_audit.v1"
ASSESSMENT_SCHEMA = "autosci_semantic_parity_assessment.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = REPO_ROOT / "harness"
DEFAULT_ROUTE_CONFIG = HARNESS_DIR / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
DEFAULT_AUTOSCI_REPO = Path(os.environ.get("AUTOSCI_REPO", REPO_ROOT.parent / "AutoSci"))
DEFAULT_SOLAR_WRAPPER_ROOT = REPO_ROOT / ".agents" / "skills"
DEFAULT_OUT_DIR = HARNESS_DIR / "artifacts" / "autosci" / "phase19" / "semantic-audits-current"
PASS_STATUSES = {"ok", "pass", "passed"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def non_empty_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def load_routes(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    routes = payload.get("routes")
    if not isinstance(routes, list):
        raise ValueError(f"{path} must contain a routes list")
    result = [route for route in routes if isinstance(route, dict) and str(route.get("native_skill") or "").strip()]
    if not result:
        raise ValueError(f"{path} contains no native_skill routes")
    return result


def load_assessments(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = load_json(path)
    schema = str(payload.get("schema") or "")
    if schema and schema != ASSESSMENT_SCHEMA:
        raise ValueError(f"{path} schema must be {ASSESSMENT_SCHEMA}")
    assessments = payload.get("assessments")
    if not isinstance(assessments, dict):
        raise ValueError(f"{path} must contain an assessments object")
    return {
        str(skill): assessment
        for skill, assessment in assessments.items()
        if str(skill or "").strip() and isinstance(assessment, dict)
    }


def is_pass(status: str) -> bool:
    return status.strip().lower() in PASS_STATUSES


def check_entry(check: str, status: str, detail: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "check": check,
        "status": status,
        "detail": detail,
    }
    if evidence_refs:
        entry["evidence_refs"] = evidence_refs
    return entry


def normalize_assessment_checks(value: Any) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return checks
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            checks.append(
                check_entry(
                    f"assessment_check_{index}",
                    "missing",
                    "Assessment check entry is not an object.",
                )
            )
            continue
        check = str(raw.get("check") or raw.get("name") or f"assessment_check_{index}").strip()
        status = str(raw.get("status") or "missing").strip().lower()
        detail = str(raw.get("detail") or raw.get("description") or "").strip()
        entry = check_entry(check, status, detail or "Assessment-supplied check.", non_empty_strings(raw.get("evidence_refs")))
        checks.append(entry)
    return checks


def ref_for_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def configured_evidence_roots() -> list[Path]:
    roots = [REPO_ROOT, HARNESS_DIR, Path.cwd()]
    for raw in str(os.environ.get("SOLAR_AUTOSCI_EVIDENCE_ROOTS") or "").split(os.pathsep):
        value = raw.strip()
        if value:
            roots.append(Path(value).expanduser())
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def native_repo_ref_candidate(path: Path, *, autosci_repo: Path) -> Path | None:
    parts = list(path.parts)
    if "AutoSci" not in parts:
        return None
    index = parts.index("AutoSci")
    tail = parts[index + 1 :]
    if not tail:
        return autosci_repo
    return autosci_repo / Path(*tail)


def evidence_root_candidates(root: Path, path: Path) -> list[Path]:
    candidates = [root / path]
    if path.parts and path.parts[0] == HARNESS_DIR.name and root.name == HARNESS_DIR.name:
        candidates.append(root / Path(*path.parts[1:]))
    if path.parts and path.parts[0] == "artifacts" and root.name != HARNESS_DIR.name:
        candidates.append(root / HARNESS_DIR.name / path)
    return candidates


def resolve_ref(ref: str, *, audit_dir: Path, autosci_repo: Path) -> Path | None:
    text = str(ref or "").strip()
    if not text or text.startswith(("route:", "native:", "runtime:", "http://", "https://", "doi:", "s2:", "arxiv:")):
        return None
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    candidates = [
        audit_dir / path,
    ]
    native_candidate = native_repo_ref_candidate(path, autosci_repo=autosci_repo)
    if native_candidate is not None:
        candidates.append(native_candidate)
    for root in configured_evidence_roots():
        candidates.extend(evidence_root_candidates(root, path))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def evidence_refs_exist(refs: list[str], *, audit_dir: Path, autosci_repo: Path) -> list[str]:
    missing: list[str] = []
    for ref in refs:
        resolved = resolve_ref(ref, audit_dir=audit_dir, autosci_repo=autosci_repo)
        if resolved is not None and not resolved.exists():
            missing.append(ref)
    return missing


def route_by_skill(routes: list[dict[str, Any]], skills: list[str]) -> list[dict[str, Any]]:
    if not skills:
        return sorted(routes, key=lambda item: str(item.get("native_skill") or ""))
    wanted = set(skills)
    selected = [route for route in routes if str(route.get("native_skill") or "") in wanted]
    found = {str(route.get("native_skill") or "") for route in selected}
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"Route(s) not found: {', '.join(missing)}")
    return sorted(selected, key=lambda item: str(item.get("native_skill") or ""))


def base_evidence(
    route: dict[str, Any],
    *,
    autosci_repo: Path,
    solar_wrapper_root: Path,
    route_config: Path,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    skill = str(route.get("native_skill") or "")
    native_doc = autosci_repo / "i18n" / "en" / "skills" / skill / "SKILL.md"
    solar_wrapper = solar_wrapper_root / skill / "SKILL.md"
    native_refs = [ref_for_path(native_doc)]
    solar_refs = [ref_for_path(route_config)]
    if solar_wrapper.exists():
        solar_refs.append(ref_for_path(solar_wrapper))
    checks = [
        check_entry(
            "native_skill_doc_exists",
            "ok" if native_doc.exists() else "missing",
            "Original AutoSci native skill document exists.",
            [native_refs[0]],
        ),
        check_entry(
            "solar_wrapper_doc_exists",
            "ok" if solar_wrapper.exists() else "missing",
            "Solar wrapper skill document exists.",
            [ref_for_path(solar_wrapper)],
        ),
        check_entry(
            "solar_route_binding_declared",
            "ok" if str(route.get("solar_backend_action") or "").strip() else "missing",
            "Solar feature parity route declares a backend action.",
            [ref_for_path(route_config)],
        ),
    ]
    return native_refs, solar_refs, checks


def build_audit(
    route: dict[str, Any],
    *,
    autosci_repo: Path,
    solar_wrapper_root: Path,
    route_config: Path,
    assessment: dict[str, Any] | None,
    audit_dir: Path,
    default_auditor: str,
    timestamp: str,
) -> tuple[dict[str, Any], list[str]]:
    skill = str(route.get("native_skill") or "")
    native_refs, solar_refs, checks = base_evidence(
        route,
        autosci_repo=autosci_repo,
        solar_wrapper_root=solar_wrapper_root,
        route_config=route_config,
    )
    assessment = assessment or {}
    assessment_checks = normalize_assessment_checks(assessment.get("acceptance_checks"))
    requested_parity = str(assessment.get("semantic_parity") or "partial").strip().lower()
    if requested_parity not in {"full", "partial"}:
        requested_parity = "partial"
    native_refs.extend(non_empty_strings(assessment.get("additional_native_evidence_refs")))
    solar_refs.extend(non_empty_strings(assessment.get("additional_solar_evidence_refs")))
    if requested_parity == "full":
        checks.extend(assessment_checks)
    else:
        checks.extend(assessment_checks)
        checks.append(
            check_entry(
                "full_semantic_assessment_supplied",
                "pending",
                "No completed route-level full semantic equivalence assessment was supplied.",
            )
        )
    missing_refs = evidence_refs_exist([*native_refs, *solar_refs], audit_dir=audit_dir, autosci_repo=autosci_repo)
    full_errors: list[str] = []
    if requested_parity == "full":
        if not assessment_checks:
            full_errors.append("full assessment must provide acceptance_checks")
        failed = [check for check in checks if not is_pass(str(check.get("status") or ""))]
        if failed:
            full_errors.append(
                "full assessment has non-passing checks: "
                + ", ".join(str(check.get("check") or "unknown") for check in failed)
            )
        if missing_refs:
            full_errors.append("full assessment has missing evidence refs: " + ", ".join(missing_refs))
    semantic_parity = "full" if requested_parity == "full" and not full_errors else "partial"
    if full_errors:
        checks.append(
            check_entry(
                "full_semantic_assessment_guard",
                "blocked",
                "; ".join(full_errors),
            )
        )
    remaining = [] if semantic_parity == "full" else [
        *non_empty_strings(route.get("limitations")),
        "Supply a completed full semantic equivalence assessment with passing checks and existing native/Solar evidence refs.",
    ]
    audit = {
        "schema": AUDIT_SCHEMA,
        "status": "completed",
        "native_skill": skill,
        "semantic_parity": semantic_parity,
        "auditor": str(assessment.get("auditor") or default_auditor),
        "audited_at": str(assessment.get("audited_at") or timestamp),
        "native_evidence_refs": list(dict.fromkeys(native_refs)),
        "solar_evidence_refs": list(dict.fromkeys(solar_refs)),
        "acceptance_checks": checks,
        "summary": str(
            assessment.get("summary")
            or (
                "Full semantic equivalence audit supplied and passed."
                if semantic_parity == "full"
                else "Semantic audit evidence is materialized, but full semantic equivalence is not yet proven."
            )
        ),
        "findings": assessment.get("findings") if isinstance(assessment.get("findings"), list) else [],
        "remaining_requirements": remaining,
        "route_snapshot": {
            "autosci_command": route.get("autosci_command"),
            "solar_backend_action": route.get("solar_backend_action"),
            "coverage_status": route.get("coverage_status"),
            "backend_mode": route.get("backend_mode"),
            "side_effect_policy": route.get("side_effect_policy"),
            "required_capabilities": non_empty_strings(route.get("required_capabilities")),
            "limitations": non_empty_strings(route.get("limitations")),
        },
        "provenance": {
            "timestamp": timestamp,
            "tool": "tools/semantic_parity_audit_matrix.py",
            "assessment_schema": ASSESSMENT_SCHEMA,
        },
    }
    return audit, full_errors


def cmd_generate(args: argparse.Namespace) -> int:
    route_config = Path(args.route_config).expanduser()
    autosci_repo = Path(args.autosci_repo).expanduser()
    solar_wrapper_root = Path(args.solar_wrapper_root).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    try:
        routes = route_by_skill(load_routes(route_config), list(args.skill or []))
        assessments = load_assessments(Path(args.assessment_json).expanduser() if args.assessment_json else None)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "status": "failed", "reason": str(exc)}, indent=2, sort_keys=True))
        return 2
    timestamp = utc_now()
    written: list[str] = []
    full_errors: dict[str, list[str]] = {}
    counts = {"full": 0, "partial": 0}
    index_items: list[dict[str, Any]] = []
    for route in routes:
        skill = str(route.get("native_skill") or "")
        audit, errors = build_audit(
            route,
            autosci_repo=autosci_repo,
            solar_wrapper_root=solar_wrapper_root,
            route_config=route_config,
            assessment=assessments.get(skill),
            audit_dir=out_dir,
            default_auditor=args.auditor,
            timestamp=timestamp,
        )
        path = out_dir / f"{skill}.semantic-audit.json"
        write_json(path, audit)
        written.append(str(path))
        counts[str(audit["semantic_parity"])] += 1
        if errors:
            full_errors[skill] = errors
        index_items.append(
            {
                "native_skill": skill,
                "semantic_parity": audit["semantic_parity"],
                "audit_path": str(path),
                "acceptance_check_statuses": {
                    str(check.get("check") or ""): str(check.get("status") or "")
                    for check in audit.get("acceptance_checks", [])
                    if isinstance(check, dict)
                },
            }
        )
    index = {
        "schema": SCHEMA,
        "status": "completed",
        "generated_at": timestamp,
        "route_count": len(routes),
        "semantic_full_count": counts["full"],
        "semantic_partial_count": counts["partial"],
        "audit_paths": written,
        "items": index_items,
    }
    index_path = out_dir / "semantic-audit-index.json"
    write_json(index_path, index)
    result = {
        "schema": SCHEMA,
        "status": "completed" if not full_errors else "completed_with_blocked_full_requests",
        "ok": not full_errors,
        "route_count": len(routes),
        "semantic_full_count": counts["full"],
        "semantic_partial_count": counts["partial"],
        "audit_dir": str(out_dir),
        "index_path": str(index_path),
        "full_request_errors": full_errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if full_errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("generate", help="Generate semantic parity audit JSON files")
    generate.add_argument("--autosci-repo", default=str(DEFAULT_AUTOSCI_REPO))
    generate.add_argument("--route-config", default=str(DEFAULT_ROUTE_CONFIG))
    generate.add_argument("--solar-wrapper-root", default=str(DEFAULT_SOLAR_WRAPPER_ROOT))
    generate.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    generate.add_argument("--skill", action="append", default=[])
    generate.add_argument("--assessment-json", default="")
    generate.add_argument("--auditor", default="phase19-semantic-audit-matrix")
    generate.set_defaults(func=cmd_generate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
