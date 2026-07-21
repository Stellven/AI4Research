#!/usr/bin/env python3
"""Epic-aware observation helpers for the isolated live Codex E2E wrapper.

This module reads only harness/evidence/workspace files. It does not dispatch
operators, mutate provider routing, or advance graph state.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SUCCESS_STATUSES = {"passed", "completed", "finalized", "eval_passed"}
FAILED_STATUSES = {"failed", "error", "cancelled", "rejected"}
ACTIVE_STATUSES = {
    "active",
    "drafting",
    "planning",
    "planning_complete",
    "prd_ready",
    "queued",
    "reviewing",
    "running",
    "submitted",
}
RUNTIME_ALLOWED_PROVIDERS = {
    "codex": {"openai"},
    "claude": {"anthropic"},
}
DEFAULT_CONTRACT_TERMINAL_STATES = ["passed", "failed", "skipped", "cancelled", "skipped_parent_passed"]
MAX_TEST_OUTPUT_CHARS = 20000
ORCHESTRATION_WEDGE_CLASSIFICATION = "ORCHESTRATION_WEDGE_NOT_PRODUCT_PROOF"
SECRET_ENV_KEYS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH")
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\b(code|codex|openai|anthropic)[-_]?(token|key|secret)[=:][A-Za-z0-9_\-./+=]{8,}\b", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-./+=]{8,}\b", re.IGNORECASE),
)


class ContractArtifactOptionsError(ValueError):
    """Raised when --contract cannot be schema-loaded and registry-confirmed."""


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _redact_payload(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _secret_values_from_env() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        key_upper = key.upper()
        if any(marker in key_upper for marker in SECRET_ENV_KEYS):
            values.append(value)
    return values


def _redact_text(value: str) -> str:
    text = str(value)
    for secret in _secret_values_from_env():
        text = text.replace(secret, "[REDACTED]")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _capture_text(value: Any, limit: int = MAX_TEST_OUTPUT_CHARS) -> tuple[str, bool]:
    text = _redact_text(value if isinstance(value, str) else str(value or ""))
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n[TRUNCATED]", True


def _normalize_provider(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "codex": "openai",
        "gpt": "openai",
        "openai": "openai",
        "claude": "anthropic",
        "claude-cli": "anthropic",
        "anthropic": "anthropic",
        "gemini": "google",
        "google": "google",
        "glm": "zhipu",
        "zhipu": "zhipu",
        "zhipuai": "zhipu",
    }
    return aliases.get(raw, raw)


def _resolved_sprints_dir(harness_dir: Path | None = None) -> Path:
    env_sprints = str(os.environ.get("HARNESS_SPRINTS_DIR") or "").strip()
    if env_sprints:
        return Path(env_sprints)
    if harness_dir is not None:
        return Path(harness_dir) / "sprints"
    env_harness = str(os.environ.get("HARNESS_DIR") or "").strip()
    if env_harness:
        return Path(env_harness) / "sprints"
    env_solar = str(os.environ.get("SOLAR_HARNESS_DIR") or "").strip()
    if env_solar:
        return Path(env_solar) / "sprints"
    return Path.home() / ".solar" / "harness" / "sprints"


def result_type(harness_dir: Path, run_id: str) -> str:
    run_id = str(run_id or "").strip()
    if run_id.startswith("epic-") or (_resolved_sprints_dir(harness_dir) / f"{run_id}.epic.json").exists():
        return "epic"
    return "sprint"


def _coerce_child_id(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("sprint_id", "child_sprint_id", "id"):
            value = str(item.get(key) or "").strip()
            if value.startswith("sprint-"):
                return value
    return ""


def discover_child_sprints(harness_dir: Path, epic_id: str) -> list[str]:
    sprints_dir = _resolved_sprints_dir(harness_dir)
    meta = _read_json(sprints_dir / f"{epic_id}.epic.json")
    graph = _read_json(sprints_dir / f"{epic_id}.task_graph.json")
    child_ids: list[str] = []

    def add(value: str) -> None:
        if value and value not in child_ids:
            child_ids.append(value)

    raw_children = meta.get("child_sprints")
    if isinstance(raw_children, list):
        for item in raw_children:
            add(_coerce_child_id(item))

    nodes = graph.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            add(_coerce_child_id(node))

    if not child_ids:
        for path in sorted(sprints_dir.glob("sprint-*.status.json")):
            data = _read_json(path)
            sid = str(data.get("sprint_id") or path.name[: -len(".status.json")])
            if epic_id.replace("epic-", "") in sid:
                add(sid)

    return child_ids


def detect_role_pool_wedge(harness_dir: Path, run_ids: list[str]) -> list[dict[str, Any]]:
    """Return role-pool inflight-timeout diagnostics for the given runs.

    The coordinator writes ``<sid>.role_pool_inflight_timeout.json`` when a pooled
    operator stays in-flight past the bounded timeout without producing planner
    artifacts. Presence of such a marker means the run wedged on a stalled
    operator rather than making progress. This is a read-only file check: it does
    not dispatch operators or mutate any state.
    """
    sprints_dir = _resolved_sprints_dir(harness_dir)
    wedged: list[dict[str, Any]] = []
    for sid in run_ids:
        marker = sprints_dir / f"{sid}.role_pool_inflight_timeout.json"
        if marker.exists():
            data = _read_json(marker)
            wedged.append({
                "run_id": sid,
                "marker_path": str(marker),
                "role": data.get("role"),
                "reason": data.get("reason") or "role_pool_inflight_timeout",
                "inflight_age_seconds": data.get("inflight_age_seconds"),
                "timeout_seconds": data.get("timeout_seconds"),
            })
    return wedged


def detect_builder_stall(harness_dir: Path, run_ids: list[str]) -> list[dict[str, Any]]:
    """Return builder-node-stall diagnostics for the given runs.

    graph_node_dispatcher writes ``<sid>.builder_node_stalled.json`` when a builder
    DAG node cannot be submitted to / executed by a role-compatible operator (e.g.
    capsule admission rejected the task_type, or no builder worker was available).
    Its presence at terminal means the builder orchestration failed -- NOT a
    report/model quality failure. Read-only file check.
    """
    sprints_dir = _resolved_sprints_dir(harness_dir)
    stalled: list[dict[str, Any]] = []
    for sid in run_ids:
        marker = sprints_dir / f"{sid}.builder_node_stalled.json"
        if marker.exists():
            data = _read_json(marker)
            stalled.append({
                "run_id": sid,
                "marker_path": str(marker),
                "node_id": data.get("node_id"),
                "reason": data.get("reason") or "builder_node_stalled",
                "operator_id": data.get("operator_id"),
            })
    return stalled


def expected_artifacts_from_task(task: str) -> list[str]:
    task = str(task or "")
    expected: list[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        rel = rel.strip().lstrip("./")
        if rel and rel not in seen:
            seen.add(rel)
            expected.append(rel)

    py_files = re.findall(r"(?<![\w./-])([A-Za-z_][\w.-]*\.py)(?![\w./-])", task)
    for py_file in py_files:
        add(py_file)
    if re.search(r"\bpytest\b|\btests?\b", task, flags=re.IGNORECASE) and py_files:
        stem = Path(py_files[0]).stem
        add(f"tests/test_{stem}.py")
    if re.search(r"\bREADME\b", task, flags=re.IGNORECASE):
        add("README.md")
    return expected


def normalize_expected_artifacts(expected_artifacts: list[str], *, allow_absolute: bool = False) -> tuple[list[str], list[dict[str, Any]]]:
    normalized: list[str] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in expected_artifacts:
        value = str(raw or "").strip()
        if not value:
            errors.append({"path": value, "reason": "expected_artifact_empty"})
            continue
        candidate = Path(value)
        if candidate.is_absolute():
            if not allow_absolute:
                errors.append({"path": value, "reason": "expected_artifact_absolute"})
                continue
            rel = str(candidate)
        else:
            stripped = value
            while stripped.startswith("./"):
                stripped = stripped[2:]
            rel_path = Path(stripped)
            if not stripped or stripped == ".":
                errors.append({"path": value, "reason": "expected_artifact_empty"})
                continue
            if any(part == ".." for part in rel_path.parts):
                errors.append({"path": value, "reason": "expected_artifact_escapes_workspace"})
                continue
            rel = rel_path.as_posix()
        if rel not in seen:
            seen.add(rel)
            normalized.append(rel)
    return normalized, errors


def _artifact_resolution_roots(
    harness_dir: Path, run_ids: list[str], workspace: Path, *, kind: str = "sprint"
) -> list[tuple[Path, str]]:
    """Ordered roots to resolve expected artifacts against. Workspace first (the
    canonical shared output location), then each run's sprint workdir -- a builder run
    with cwd=<sprints>/<sid>/workdir writes relative-path outputs there, so the same
    `rsi-deep-research-report/...` artifacts land under the workdir instead of the
    shared workspace (the v9 case)."""
    roots: list[tuple[Path, str]] = [(workspace, "workspace")]
    sprints_dir = _resolved_sprints_dir(harness_dir)
    for sid in run_ids:
        roots.append((sprints_dir / str(sid) / "workdir",
                      "child_workdir" if kind == "epic" else "sprint_workdir"))
    return roots


def _contract_substitute(value: Any, *, sid: str, substitutions: dict[str, str] | None = None) -> str:
    text = str(value or "")
    replacements = {"sid": str(sid or "")}
    replacements.update({str(k): str(v) for k, v in (substitutions or {}).items()})
    for key, item in replacements.items():
        text = text.replace(f"<{key}>", item)
    return text


def _contract_root_path(
    declared: str,
    *,
    sid: str,
    harness_dir: Path | None,
    workspace: Path | None,
    substitutions: dict[str, str] | None = None,
) -> Path:
    resolved = _contract_substitute(declared, sid=sid, substitutions=substitutions).rstrip("/")
    raw = Path(resolved)
    if raw.is_absolute():
        return raw
    parts = raw.parts
    if parts and parts[0] == "workspace" and workspace is not None:
        return workspace.joinpath(*parts[1:])
    if parts and parts[0] == "sprints" and harness_dir is not None:
        return _resolved_sprints_dir(harness_dir).joinpath(*parts[1:])
    return raw


def _workflow_contract_module():
    harness_lib = Path(__file__).resolve().parents[1] / "harness" / "lib"
    lib_text = str(harness_lib)
    if lib_text not in sys.path:
        sys.path.insert(0, lib_text)
    try:
        import workflow_contract  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise ContractArtifactOptionsError(f"contract_module_unavailable: {type(exc).__name__}: {exc}") from exc
    return workflow_contract


def _load_registered_contract(contract_path: Path, harness_dir: Path | None) -> dict[str, Any]:
    workflow_contract = _workflow_contract_module()
    try:
        contract = workflow_contract.load_contract(contract_path)
    except Exception as exc:  # noqa: BLE001
        raise ContractArtifactOptionsError(f"contract_schema_invalid: {type(exc).__name__}: {exc}") from exc

    workflow_id = str(contract.get("workflow_id") or "").strip()
    version = str(contract.get("version") or "").strip()
    workflows_dir = (
        Path(harness_dir) / "config" / "workflows"
        if harness_dir is not None
        else workflow_contract.default_workflows_dir()
    )
    registered = workflow_contract.find_contract(workflow_id, workflows_dir)
    if not registered:
        raise ContractArtifactOptionsError(
            f"contract_unregistered: workflow_id {workflow_id!r} not found in {workflows_dir}"
        )
    registered_version = str(registered.get("version") or "").strip()
    if registered_version != version:
        raise ContractArtifactOptionsError(
            "contract_version_mismatch: "
            f"{workflow_id!r} loaded version {version!r}, registry version {registered_version!r}"
        )
    return contract


def contract_artifact_options(
    contract_path: Path,
    *,
    sid: str,
    substitutions: dict[str, str] | None = None,
    harness_dir: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Read artifact validation inputs from one workflow contract.

    Contract mode is fail-closed: the file must pass the Lane 1 schema loader
    and its workflow_id/version must match the shipped workflow registry.
    """
    contract = _load_registered_contract(Path(contract_path), harness_dir)
    workflow_id = str(contract.get("workflow_id") or "")
    version = str(contract.get("version") or "")
    roots_doc = contract.get("artifact_roots") if isinstance(contract.get("artifact_roots"), dict) else {}

    roots: list[dict[str, Any]] = []
    canonical = str(roots_doc.get("canonical") or "").strip()
    if canonical:
        roots.append({
            "declared": canonical,
            "type": "contract_canonical",
            "root": _contract_root_path(
                canonical,
                sid=sid,
                harness_dir=harness_dir,
                workspace=workspace,
                substitutions=substitutions,
            ),
        })
    for alias in roots_doc.get("aliases", []) or []:
        alias_text = str(alias or "").strip()
        if not alias_text:
            continue
        roots.append({
            "declared": alias_text,
            "type": "contract_alias",
            "root": _contract_root_path(
                alias_text,
                sid=sid,
                harness_dir=harness_dir,
                workspace=workspace,
                substitutions=substitutions,
            ),
        })

    raw_expected = contract.get("required_artifacts") or []
    expected_artifacts = [
        _contract_substitute(item, sid=sid, substitutions=substitutions).strip().lstrip("./")
        for item in raw_expected
        if str(item or "").strip()
    ]

    terminal_states: dict[str, list[str]] = {}
    for stage in contract.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("id") or "").strip()
        if not stage_id:
            continue
        states = stage.get("terminal_states")
        if not isinstance(states, list) or not states:
            states = DEFAULT_CONTRACT_TERMINAL_STATES
        terminal_states[stage_id] = [str(state).strip().lower() for state in states if str(state or "").strip()]

    return {
        "workflow_id": workflow_id,
        "version": version,
        "identity": f"{workflow_id}@{version}" if workflow_id and version else workflow_id,
        "source_path": str(contract_path),
        "expected_artifacts": expected_artifacts,
        "roots": roots,
        "terminal_states": terminal_states,
        "validator_command": _contract_substitute(
            contract.get("validator_command") or "",
            sid=sid,
            substitutions=substitutions,
        ).strip(),
    }


def _file_signature(path: Path) -> tuple[int, str]:
    """(size, sha256) for content-conflict detection. Cheap for small report artifacts."""
    import hashlib
    try:
        data = path.read_bytes()
    except Exception:
        return (0, "")
    return (len(data), hashlib.sha256(data).hexdigest())


def build_artifact_manifest(
    workspace: Path,
    expected_artifacts: list[str],
    *,
    path_errors: list[dict[str, Any]] | None = None,
    roots: list[tuple[Path, str]] | None = None,
) -> dict[str, Any]:
    """Resolve each expected artifact against ordered roots (default: workspace only, so
    existing single-root behavior is preserved). Records the resolved path + root type,
    every root it was found in, and a content-conflict flag. On a cross-root content
    conflict the sprint/child workdir (producer) version wins -- the builder's workdir
    output is the authoritative latest -- and the conflict is recorded; the caller
    (summarize_artifact_validation) only ever validates once producers are terminal and
    route-proof is valid, which is the safe condition for workdir-wins."""
    roots = roots or [(workspace, "workspace")]
    rows: list[dict[str, Any]] = []
    root_conflicts: list[str] = []
    for rel in expected_artifacts:
        rel_path = Path(rel)
        candidates: list[tuple[Path, str]] = []
        if rel_path.is_absolute():
            if rel_path.is_file():
                candidates.append((rel_path, "absolute"))
        else:
            for root, rtype in roots:
                p = root / rel_path
                if p.exists() and p.is_file():
                    candidates.append((p, rtype))
        if not candidates:
            rows.append({
                "path": rel, "absolute_path": str(roots[0][0] / rel_path),
                "resolved_path": "", "resolved_root": "",
                "exists": False, "is_file": False, "size": 0, "mtime": 0,
                "found_in_roots": [], "conflict": False,
            })
            continue
        signatures: dict[tuple[int, str], list[tuple[Path, str]]] = {}
        for p, rtype in candidates:
            signatures.setdefault(_file_signature(p), []).append((p, rtype))
        conflict = len(signatures) > 1
        chosen_path, chosen_root = candidates[0]  # workspace-first order
        if conflict:
            workdir_choice = next(((p, r) for p, r in candidates if r != "workspace"), None)
            if workdir_choice is not None:
                chosen_path, chosen_root = workdir_choice
            root_conflicts.append(rel)
        st = chosen_path.stat()
        rows.append({
            "path": rel, "absolute_path": str(chosen_path),
            "resolved_path": str(chosen_path), "resolved_root": chosen_root,
            "exists": True, "is_file": True,
            "size": st.st_size, "mtime": st.st_mtime,
            "found_in_roots": [r for _, r in candidates], "conflict": conflict,
        })
    errors = path_errors or []
    return {
        "workspace": str(workspace),
        "roots": [{"root": str(r), "type": t} for r, t in roots],
        "expected_artifacts": rows,
        "path_errors": errors,
        "all_expected_exist": (
            not errors and (all(row["exists"] and row["is_file"] for row in rows) if rows else True)
        ),
        "artifact_root_conflicts": root_conflicts,
    }


def _contract_command_for_copy(command: str, harness_dir: Path) -> str:
    """Rewrite a contract validator_command for copied-workspace execution.

    Contract commands are written for the gate executor's convention
    (cwd=HARNESS_DIR: `python3 scripts/<validator>.py --workspace
    sprints/<sid>/workdir`). _run_test_command_in_copy executes with cwd = a
    COPY of the workspace where neither the script's relative path nor the
    harness-relative workspace exists (P3 run-5 note: literal
    `<resolved_root>` even read as shell redirection when unsubstituted).
    Rewrites: script path -> absolute under the harness (harness/scripts
    first); the --workspace value and any leftover `<resolved_root>` -> `.`
    (the copy root, where the overlay reconstructs the canonical layout)."""
    import shlex
    try:
        argv = shlex.split(str(command or ""))
    except ValueError:
        return str(command or "")
    if not argv:
        return str(command or "")
    out: list[str] = []
    idx = 0
    while idx < len(argv):
        token = argv[idx]
        if "<resolved_root>" in token:
            token = token.replace("<resolved_root>", ".")
        if idx == 1 and argv[0] in {"python3", "python"} and token.endswith(".py") and not Path(token).is_absolute():
            for candidate in (harness_dir / token, harness_dir / "scripts" / Path(token).name):
                if candidate.is_file():
                    token = str(candidate)
                    break
        if token == "--workspace" and idx + 1 < len(argv):
            out.append(token)
            out.append(".")
            idx += 2
            continue
        out.append(token)
        idx += 1
    return " ".join(shlex.quote(t) if " " in t else t for t in out)


def _run_test_command_in_copy(
    workspace: Path, command: str, timeout_seconds: int,
    *, overlay: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    command = str(command or "").strip()
    if not command:
        return {
            "ran": False,
            "ok": False,
            "reason": "test_command_missing",
            "command": command,
        }

    with tempfile.TemporaryDirectory(prefix="solar-artifact-validation.", dir=os.environ.get("TMPDIR") or "/tmp") as tmp:
        tmp_workspace = Path(tmp) / "workspace"
        if workspace.exists() and workspace.is_dir():
            shutil.copytree(workspace, tmp_workspace)
        else:
            tmp_workspace.mkdir(parents=True, exist_ok=True)
        # Overlay resolved artifacts at their expected relative paths so workdir outputs
        # (and the chosen version of any cross-root conflict) sit where the validator
        # expects them -- even when the shared workspace never received them.
        for src, rel in (overlay or []):
            try:
                dest = tmp_workspace / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            except Exception:
                pass
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            # This command is an explicit local validation command from the caller.
            # It intentionally uses shell=True for parity with normal CLI snippets,
            # but output is bounded and redacted before evidence is written.
            proc = subprocess.run(
                command,
                cwd=tmp_workspace,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                env=env,
            )
            stdout, stdout_truncated = _capture_text(proc.stdout)
            stderr, stderr_truncated = _capture_text(proc.stderr)
            return {
                "ran": True,
                "ok": proc.returncode == 0,
                "reason": "" if proc.returncode == 0 else "test_command_failed",
                "command": command,
                "returncode": proc.returncode,
                "timeout_seconds": timeout_seconds,
                "copied_workspace": str(tmp_workspace),
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "output_limit_chars": MAX_TEST_OUTPUT_CHARS,
            }
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_truncated = _capture_text(exc.stdout if isinstance(exc.stdout, str) else "")
            stderr, stderr_truncated = _capture_text(exc.stderr if isinstance(exc.stderr, str) else "")
            return {
                "ran": True,
                "ok": False,
                "reason": "test_command_timeout",
                "command": command,
                "timeout_seconds": timeout_seconds,
                "copied_workspace": str(tmp_workspace),
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "output_limit_chars": MAX_TEST_OUTPUT_CHARS,
            }


def _status_kind(status: str) -> str:
    value = str(status or "").strip().lower()
    if value in SUCCESS_STATUSES:
        return "success"
    if value in FAILED_STATUSES or value.startswith("failed"):
        return "failed"
    if value in ACTIVE_STATUSES:
        return "active"
    if not value or value == "missing":
        return "active"
    return "active"


def _load_route_proof(sprints_dir: Path, sid: str) -> tuple[Path, dict[str, Any]]:
    path = sprints_dir / f"{sid}.route-proof.json"
    return path, _read_json(path)


def _providers_from_proof(proof: dict[str, Any]) -> list[str]:
    providers: set[str] = set()
    for stage in proof.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        provider = _normalize_provider(stage.get("provider") or stage.get("provider_raw"))
        if provider:
            providers.add(provider)
    return sorted(providers)


def _stage_count(proof: dict[str, Any]) -> int:
    try:
        return int(proof.get("stage_count") or 0)
    except Exception:
        return 0


def _child_summary(harness_dir: Path, sid: str) -> dict[str, Any]:
    sprints_dir = _resolved_sprints_dir(harness_dir)
    status_path = sprints_dir / f"{sid}.status.json"
    graph_path = sprints_dir / f"{sid}.task_graph.json"
    route_path, route_proof = _load_route_proof(sprints_dir, sid)
    status = _read_json(status_path)
    status_value = str(status.get("status") or status.get("phase") or "missing")
    route_exists = route_path.exists()
    route_stage_count = _stage_count(route_proof)
    return {
        "child_id": sid,
        "status": status_value,
        "status_kind": _status_kind(status_value),
        "phase": status.get("phase"),
        "updated_at": status.get("updated_at"),
        "status_path": str(status_path),
        "status_exists": status_path.exists(),
        "task_graph_path": str(graph_path),
        "task_graph_exists": graph_path.exists(),
        "route_proof_path": str(route_path),
        "route_proof_exists": route_exists,
        "route_proof_ok": bool(route_proof.get("ok")) if route_exists else False,
        "route_proof_stage_count": route_stage_count,
        "route_proof_violations": route_proof.get("violations") if route_exists else [],
        "providers_observed": _providers_from_proof(route_proof) if route_exists else [],
        "executed": status_path.exists() or graph_path.exists() or route_exists,
    }


def _route_summary_for_runs(harness_dir: Path, run_ids: list[str], *, selected_runtime_hint: str = "codex") -> dict[str, Any]:
    child_rows = [_child_summary(harness_dir, sid) for sid in run_ids]
    selected_runtime = ""
    allowed: set[str] = set()
    providers: set[str] = set()
    total_stage_count = 0
    route_violations: list[dict[str, Any]] = []
    missing_route_proofs: list[str] = []
    completed_runs: list[str] = []
    active_runs: list[str] = []
    failed_runs: list[str] = []
    child_proofs_found = 0

    for child in child_rows:
        sid = child["child_id"]
        status_kind = child["status_kind"]
        if status_kind == "success":
            completed_runs.append(sid)
        elif status_kind == "failed":
            failed_runs.append(sid)
        else:
            active_runs.append(sid)

        proof_required = child["route_proof_exists"] or (child["executed"] and status_kind in {"success", "failed"})
        if proof_required and not child["route_proof_exists"]:
            missing_route_proofs.append(sid)
            continue
        if not child["route_proof_exists"]:
            continue

        proof = _read_json(Path(child["route_proof_path"]))
        child_proofs_found += 1
        total_stage_count += child["route_proof_stage_count"]
        selected_runtime = selected_runtime or str(proof.get("selected_runtime") or "")
        allowed.update(_normalize_provider(p) for p in (proof.get("allowed_providers") or []) if _normalize_provider(p))
        providers.update(child["providers_observed"])

        if child["route_proof_stage_count"] < 1:
            route_violations.append({
                "run_id": sid,
                "reason": "route_proof_stage_count_zero",
            })
        for violation in proof.get("violations") or []:
            if isinstance(violation, dict):
                item = {"run_id": sid, **violation}
            else:
                item = {"run_id": sid, "reason": str(violation)}
            route_violations.append(item)
        if not proof.get("ok"):
            route_violations.append({
                "run_id": sid,
                "reason": "route_proof_not_ok",
            })

    selected_runtime = selected_runtime or selected_runtime_hint
    if not allowed:
        allowed = set(RUNTIME_ALLOWED_PROVIDERS.get(selected_runtime, set()))

    for child in child_rows:
        for provider in child["providers_observed"]:
            if allowed and provider not in allowed:
                route_violations.append({
                    "run_id": child["child_id"],
                    "provider": provider,
                    "allowed_providers": sorted(allowed),
                    "reason": "provider_policy_violation",
                })

    return {
        "ok": (
            child_proofs_found > 0
            and total_stage_count > 0
            and not missing_route_proofs
            and not route_violations
            and not failed_runs
        ),
        "selected_runtime": selected_runtime,
        "allowed_providers": sorted(allowed),
        "total_stage_count": total_stage_count,
        "stage_count": total_stage_count,
        "proof_count": child_proofs_found,
        "run_count": len(run_ids),
        "run_ids": run_ids,
        "providers_observed": sorted(providers),
        "violations": route_violations,
        "missing_route_proofs": missing_route_proofs,
        "completed_runs": completed_runs,
        "active_runs": active_runs,
        "failed_runs": failed_runs,
        "runs": child_rows,
        "meaningful_route_proof": child_proofs_found > 0 and total_stage_count > 0,
    }


# A producer node in any of these statuses is still writing/settling its artifacts,
# so the copied-workspace validator must NOT run yet (it would race a mid-draft file).
ACTIVE_PRODUCER_STATUSES = {
    "active", "reviewing", "dispatched", "assigned", "assigning", "drafting",
    "repairing", "repair", "in_progress", "running", "pending", "queued",
    "dispatching", "ready_for_review", "needs_human_review", "failed_review",
}
# Terminal pass-equivalent: the producer is done and its artifacts are final.
PASS_EQUIVALENT_STATUSES = {
    "passed", "completed", "eval_passed", "passed_with_review_warning", "passed_with_warning",
}


def _artifact_matches_write_scope(expected_rel: str, ws_entry: str) -> bool:
    exp = str(expected_rel or "").strip().strip("/")
    ws = str(ws_entry or "").strip().strip("/")
    if not exp or not ws:
        return False
    ws_norm = ws
    if ws_norm.startswith("workspace/"):
        ws_norm = ws_norm[len("workspace/"):]
    if ws_norm == exp or ws.endswith(exp) or exp.endswith(ws_norm):
        return True
    return Path(exp).name == Path(ws).name


def _node_status_value(graph: dict[str, Any], node_id: str, node: dict[str, Any]) -> str:
    results = graph.get("node_results") if isinstance(graph.get("node_results"), dict) else {}
    result = results.get(node_id) if isinstance(results, dict) else None
    if isinstance(result, dict) and result.get("status"):
        return str(result.get("status"))
    return str(node.get("status") or "")


def _producer_nodes_for_artifacts(
    harness_dir: Path,
    run_ids: list[str],
    expected_rel_paths: list[str],
    *,
    terminal_states: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Map expected artifacts to producer graph nodes via write_scope overlap. Returns
    one record per matching node: {sid, node_id, status, active, write_scope}. Never raises.
    An empty result (no write_scope info / no overlap) means 'no active producer' -- the
    existing artifact-mode behavior for simple completed outputs (e.g. paperfilter)."""
    producers: list[dict[str, Any]] = []
    sprints_dir = _resolved_sprints_dir(harness_dir)
    for sid in run_ids:
        graph = _read_json(sprints_dir / f"{sid}.task_graph.json")
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            write_scope = node.get("write_scope") or []
            if isinstance(write_scope, str):
                write_scope = [write_scope]
            if not isinstance(write_scope, list) or not write_scope:
                continue
            overlaps = any(
                _artifact_matches_write_scope(exp, ws)
                for exp in expected_rel_paths for ws in write_scope
            )
            if not overlaps:
                continue
            status = _node_status_value(graph, str(node.get("id") or ""), node)
            node_terminal_states = {
                str(item).strip().lower()
                for item in (terminal_states or {}).get(str(node.get("id") or ""), [])
                if str(item or "").strip()
            }
            active = status.strip().lower() in ACTIVE_PRODUCER_STATUSES
            if node_terminal_states:
                active = active or status.strip().lower() not in node_terminal_states
            producers.append({
                "sid": sid,
                "node_id": str(node.get("id") or ""),
                "status": status,
                "active": active,
                "write_scope": [str(w) for w in write_scope],
            })
    return producers


def _parse_iso(value: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except Exception:
        return None


def _artifact_stability(
    manifest: dict[str, Any],
    state_path: Path | None,
    *,
    min_stable_polls: int = 2,
    min_stable_seconds: int = 30,
) -> dict[str, Any]:
    """Cross-poll file-stability guard. Artifacts are 'stable' once their (size, mtime)
    signature is unchanged for >= min_stable_polls consecutive polls OR >= min_stable_seconds.
    With no state_path (direct/unit calls), returns stable=True so existing single-shot
    behavior is preserved."""
    signature = {
        row["path"]: [row.get("size"), row.get("mtime")]
        for row in manifest.get("expected_artifacts", [])
        if row.get("exists") and row.get("is_file")
    }
    now = _utc_now()
    if state_path is None:
        return {"stable": True, "observations": 1, "first_seen": now, "reason": "stability_tracking_disabled"}
    if not signature:
        return {"stable": False, "observations": 0, "first_seen": now, "reason": "no_artifacts_yet"}
    prior = _read_json(state_path)
    observations = 1
    first_seen = now
    if isinstance(prior, dict) and prior.get("signature") == signature:
        observations = int(prior.get("observations") or 1) + 1
        first_seen = str(prior.get("first_seen") or now)
    started = _parse_iso(first_seen)
    ended = _parse_iso(now)
    elapsed = int((ended - started).total_seconds()) if (started and ended) else 0
    stable = observations >= min_stable_polls or elapsed >= min_stable_seconds
    new_state = {
        "signature": signature,
        "observations": observations,
        "first_seen": first_seen,
        "last_seen": now,
        "elapsed_seconds": elapsed,
        "stable": stable,
    }
    try:
        _write_json(state_path, new_state)
    except Exception:
        pass
    return new_state


def summarize_artifact_validation(
    harness_dir: Path,
    run_id: str,
    *,
    workspace: Path,
    task: str,
    expected_artifacts: list[str] | None = None,
    test_command: str = "python3 -m pytest -q",
    test_timeout_seconds: int = 300,
    terminal: bool = False,
    allow_absolute_artifacts: bool = False,
    stability_state_path: Path | None = None,
    min_stable_polls: int = 2,
    min_stable_seconds: int = 30,
    resolution_roots: list[tuple[Path, str]] | None = None,
    producer_terminal_states: dict[str, list[str]] | None = None,
    contract_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kind = result_type(harness_dir, run_id)
    run_ids = discover_child_sprints(harness_dir, run_id) if kind == "epic" else [run_id]
    raw_expected = expected_artifacts if expected_artifacts is not None else expected_artifacts_from_task(task)
    expected, path_errors = normalize_expected_artifacts(raw_expected, allow_absolute=allow_absolute_artifacts)
    resolution_roots = resolution_roots or _artifact_resolution_roots(harness_dir, run_ids, workspace, kind=kind)
    artifact_manifest = build_artifact_manifest(workspace, expected, path_errors=path_errors, roots=resolution_roots)
    route_summary = _route_summary_for_runs(harness_dir, run_ids)

    blocking_failures: list[dict[str, Any]] = []
    pending_reasons: list[dict[str, Any]] = []

    if route_summary["failed_runs"]:
        blocking_failures.append({
            "reason": "child_sprint_failed",
            "failed_runs": route_summary["failed_runs"],
        })
    if route_summary["missing_route_proofs"]:
        blocking_failures.append({
            "reason": "route_proof_missing_for_executed_work",
            "missing_route_proofs": route_summary["missing_route_proofs"],
        })
    if route_summary["violations"]:
        blocking_failures.append({
            "reason": "route_proof_failed",
            "violations": route_summary["violations"],
        })
    if path_errors:
        blocking_failures.append({
            "reason": "expected_artifact_path_invalid",
            "path_errors": path_errors,
        })
    if not route_summary["meaningful_route_proof"]:
        pending_reasons.append({"reason": "no_meaningful_route_proof"})
    if not artifact_manifest["all_expected_exist"] and not path_errors:
        missing = [row["path"] for row in artifact_manifest["expected_artifacts"] if not row["exists"] or not row["is_file"]]
        pending_reasons.append({
            "reason": "expected_artifacts_missing",
            "missing_artifacts": missing,
        })

    producers = _producer_nodes_for_artifacts(
        harness_dir, run_ids,
        [row["path"] for row in artifact_manifest["expected_artifacts"]],
        terminal_states=producer_terminal_states,
    )
    active_producers = [p for p in producers if p["active"]]
    stability = _artifact_stability(
        artifact_manifest, stability_state_path,
        min_stable_polls=min_stable_polls, min_stable_seconds=min_stable_seconds,
    )
    artifacts_present = artifact_manifest["all_expected_exist"]

    if artifacts_present and active_producers:
        # A producer node is still writing/reviewing its artifacts: do NOT validate a
        # mid-draft file. Remain pending (and, at terminal, incomplete -- not failed).
        pending_reasons.append({
            "reason": "producer_node_active",
            "active_producers": [
                {"node_id": p["node_id"], "status": p["status"], "sid": p["sid"]}
                for p in active_producers
            ],
        })
        test_result = {"ran": False, "ok": False, "reason": "producer_node_active", "command": test_command}
    elif artifacts_present and not stability["stable"]:
        # Files exist but their (size, mtime) signature is not yet stable across polls.
        pending_reasons.append({"reason": "artifacts_not_stable", "stability": stability})
        test_result = {"ran": False, "ok": False, "reason": "artifacts_not_stable", "command": test_command}
    elif artifacts_present:
        # Producers terminal/pass-equivalent (or none) AND artifacts stable: validate.
        # Overlay the resolved artifacts (workspace + sprint-workdir) into the copied
        # validation workspace at their expected relative paths. In CONTRACT mode
        # (resolution_roots provided) the contract's expected artifacts are BARE
        # names — overlaying them at the copy root loses the canonical layout the
        # contract validator checks (rsi_demo: ROOT constant expects
        # rsi-deep-research-report/<file>). Reconstruct <root_basename>/<inner>
        # from the resolving root so the copy mirrors the canonical dir.
        contract_layout = bool(resolution_roots)
        manifest_roots = [
            str(row.get("root"))
            for row in artifact_manifest.get("roots", [])
            if isinstance(row, dict) and row.get("root")
        ]
        overlay = []
        for row in artifact_manifest["expected_artifacts"]:
            src = row.get("resolved_path")
            if not src:
                continue
            rel = row["path"]
            if contract_layout:
                for root in manifest_roots:
                    try:
                        inner = Path(src).relative_to(root)
                    except ValueError:
                        continue
                    rel = str(Path(Path(root).name) / inner)
                    break
            overlay.append((src, rel))
        test_result = _run_test_command_in_copy(workspace, test_command, test_timeout_seconds, overlay=overlay)
        if not test_result.get("ok"):
            blocking_failures.append({
                "reason": test_result.get("reason") or "test_command_failed",
                "test_command": test_command,
                "returncode": test_result.get("returncode"),
            })
    else:
        test_result = {
            "ran": False,
            "ok": False,
            "reason": "expected_artifacts_missing",
            "command": test_command,
        }

    has_active_producers = bool(active_producers)
    if blocking_failures:
        state = "failed"
        failure_class = "artifact_validation_failed"
    elif pending_reasons and terminal:
        # At terminal (timeout): if artifacts are present but producers are still active,
        # or the artifacts are present but not yet stable, this is INCOMPLETE progress --
        # NOT a validator failure. VALIDATOR_FAILED is reserved for producers-done +
        # stable + validator-still-fails (a blocking_failure) or a genuine terminal miss.
        if has_active_producers or (artifacts_present and not stability["stable"]):
            state = "incomplete"
            failure_class = "artifact_validation_incomplete"
        else:
            state = "failed"
            failure_class = "artifact_validation_failed"
    elif pending_reasons:
        state = "pending"
        failure_class = ""
    else:
        state = "passed"
        failure_class = ""

    # Role-pool inflight-timeout markers mean the run wedged on a stalled operator
    # rather than making progress. Surface that distinctly so validation does not
    # read a wedge as a plain "still pending" state. Never overrides a real pass.
    role_pool_wedge = detect_role_pool_wedge(harness_dir, run_ids)
    builder_stall = detect_builder_stall(harness_dir, run_ids)
    orchestration_wedge = bool(role_pool_wedge or builder_stall) and state != "passed"
    classification = (
        "ARTIFACT_VALIDATION_PASSED" if state == "passed" else
        "ARTIFACT_VALIDATION_FAILED" if state == "failed" else
        "ARTIFACT_VALIDATION_INCOMPLETE" if state == "incomplete" else
        "ARTIFACT_VALIDATION_PENDING"
    )
    if orchestration_wedge:
        classification = ORCHESTRATION_WEDGE_CLASSIFICATION
    _wedge_reason = (
        (role_pool_wedge[0]["reason"] if role_pool_wedge else None)
        or (builder_stall[0]["reason"] if builder_stall else None)
    )

    summary = {
        "ok": state == "passed",
        "state": state,
        "failure_class": failure_class,
        "classification": classification,
        "orchestration_wedge": orchestration_wedge,
        "role_pool_wedge": role_pool_wedge,
        "builder_stall": builder_stall,
        "reason": (
            (_wedge_reason if orchestration_wedge else None) or
            (blocking_failures[0]["reason"] if blocking_failures else
             (pending_reasons[0]["reason"] if pending_reasons else ""))
        ),
        "run_id": run_id,
        "run_type": kind,
        "generated_at": _utc_now(),
        "terminal": terminal,
        "not_product_proof": True,
        "not_full_epic_product_proof": kind == "epic",
        "active_or_drafting_runs": route_summary["active_runs"],
        "raw_expected_artifacts": raw_expected,
        "expected_artifacts": expected,
        "artifact_manifest": artifact_manifest,
        "artifact_root_conflicts": artifact_manifest.get("artifact_root_conflicts") or [],
        "artifact_conflict_resolution": "sprint_workdir_wins" if artifact_manifest.get("artifact_root_conflicts") else "",
        "test_result": test_result,
        "route_proof": route_summary,
        "producers": producers,
        "active_producers": active_producers,
        "artifact_stability": stability,
        "blocking_failures": blocking_failures,
        "pending_reasons": pending_reasons,
        "explanation": (
            "Artifact validation checks expected files, copied test execution, and executed-work route proof. "
            "It is not full epic product proof."
        ),
    }
    if contract_summary is not None:
        summary["contract"] = contract_summary
    return summary


def write_artifact_validation_outputs(evidence_dir: Path, summary: dict[str, Any], *, marker_mode: str = "none") -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _write_json(evidence_dir / "artifact-validation-summary.json", summary)
    _write_json(evidence_dir / "artifact-validation-route-proof.json", summary["route_proof"])
    _write_json(evidence_dir / "artifact-validation-manifest.json", summary["artifact_manifest"])
    _write_json(evidence_dir / "artifact-validation-test-result.json", summary["test_result"])

    if marker_mode == "terminal":
        if summary["state"] == "passed" and summary["run_type"] == "epic" and summary["route_proof"].get("active_runs"):
            marker = "ARTIFACT_VALIDATION_PASSED_EPIC_INCOMPLETE.json"
        elif summary["state"] == "passed":
            marker = "ARTIFACT_VALIDATION_PASSED.json"
        elif summary["state"] == "incomplete":
            # Artifacts present but producer nodes still active / not stable at timeout:
            # progress, not a validator failure.
            marker = "ARTIFACT_VALIDATION_INCOMPLETE.json"
        else:
            marker = "ARTIFACT_VALIDATION_FAILED.json"
        _write_json(evidence_dir / marker, {
            "valid": summary["state"] == "passed",
            "classification": summary["classification"],
            "reason": summary.get("reason"),
            "run_id": summary["run_id"],
            "run_type": summary["run_type"],
            "not_product_proof": True,
            "not_full_epic_product_proof": summary["not_full_epic_product_proof"],
            "active_or_drafting_runs": summary["active_or_drafting_runs"],
            "expected_artifacts": summary["expected_artifacts"],
            "artifact_status": summary["artifact_manifest"],
            "test_result": summary["test_result"],
            "route_proof": summary["route_proof"],
            "blocking_failures": summary["blocking_failures"],
            "pending_reasons": summary["pending_reasons"],
            "written_at": _utc_now(),
        })
        if summary.get("orchestration_wedge"):
            _write_json(evidence_dir / "ORCHESTRATION_WEDGE_NOT_PRODUCT_PROOF.json", {
                "valid": False,
                "classification": ORCHESTRATION_WEDGE_CLASSIFICATION,
                "reason": summary.get("reason") or "role_pool_inflight_timeout",
                "run_id": summary["run_id"],
                "run_type": summary["run_type"],
                "not_product_proof": True,
                "role_pool_wedge": summary.get("role_pool_wedge", []),
                "builder_stall": summary.get("builder_stall", []),
                "active_or_drafting_runs": summary["active_or_drafting_runs"],
                "route_proof": summary["route_proof"],
                "written_at": _utc_now(),
            })

    # On a validated pass, copy the resolved artifacts to a stable canonical location
    # (evidence/report/<expected-rel>) so the demo QA kit has one path regardless of
    # whether outputs landed in the shared workspace or a sprint workdir.
    if summary.get("state") == "passed":
        for row in summary["artifact_manifest"]["expected_artifacts"]:
            src = row.get("resolved_path")
            if not src or not Path(src).is_file():
                continue
            try:
                dest = evidence_dir / "report" / row["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            except Exception:
                pass


def summarize_epic(
    harness_dir: Path,
    epic_id: str,
    *,
    workspace: Path,
    task: str,
    required_child_ids: list[str] | None = None,
) -> dict[str, Any]:
    sprints_dir = _resolved_sprints_dir(harness_dir)
    meta_path = sprints_dir / f"{epic_id}.epic.json"
    graph_path = sprints_dir / f"{epic_id}.task_graph.json"
    children = discover_child_sprints(harness_dir, epic_id)
    required = required_child_ids or children
    required_set = set(required)
    child_rows = [_child_summary(harness_dir, sid) for sid in children]

    expected = expected_artifacts_from_task(task)
    artifact_manifest = build_artifact_manifest(workspace, expected)

    completed_children = [c["child_id"] for c in child_rows if c["child_id"] in required_set and c["status_kind"] == "success"]
    failed_children = [c["child_id"] for c in child_rows if c["child_id"] in required_set and c["status_kind"] == "failed"]
    active_children = [c["child_id"] for c in child_rows if c["child_id"] in required_set and c["status_kind"] == "active"]
    missing_route_proofs = [
        c["child_id"]
        for c in child_rows
        if c["executed"] and not c["route_proof_exists"]
    ]

    providers: set[str] = set()
    allowed: set[str] = set()
    selected_runtime = ""
    total_stage_count = 0
    route_violations: list[dict[str, Any]] = []
    child_proofs_found = 0
    for child in child_rows:
        if not child["route_proof_exists"]:
            continue
        proof = _read_json(Path(child["route_proof_path"]))
        child_proofs_found += 1
        total_stage_count += child["route_proof_stage_count"]
        selected_runtime = selected_runtime or str(proof.get("selected_runtime") or "")
        allowed.update(_normalize_provider(p) for p in (proof.get("allowed_providers") or []) if _normalize_provider(p))
        providers.update(child["providers_observed"])
        if child["route_proof_stage_count"] < 1:
            route_violations.append({
                "child_id": child["child_id"],
                "reason": "child_route_proof_stage_count_zero",
            })
        for violation in proof.get("violations") or []:
            if isinstance(violation, dict):
                item = {"child_id": child["child_id"], **violation}
            else:
                item = {"child_id": child["child_id"], "reason": str(violation)}
            route_violations.append(item)
        if not proof.get("ok"):
            route_violations.append({
                "child_id": child["child_id"],
                "reason": "child_route_proof_not_ok",
            })

    if not selected_runtime:
        meta = _read_json(meta_path)
        selected_runtime = str(meta.get("selected_runtime") or "codex")
    if not allowed:
        allowed = set(RUNTIME_ALLOWED_PROVIDERS.get(selected_runtime, set()))

    for child in child_rows:
        for provider in child["providers_observed"]:
            if allowed and provider not in allowed:
                route_violations.append({
                    "child_id": child["child_id"],
                    "provider": provider,
                    "allowed_providers": sorted(allowed),
                    "reason": "provider_policy_violation",
                })

    aggregate_reason = ""
    aggregate_ok = True
    if child_proofs_found == 0:
        aggregate_ok = False
        aggregate_reason = "no_child_route_proofs_aggregated"
        route_violations.append({"reason": aggregate_reason})
    elif total_stage_count == 0:
        aggregate_ok = False
        aggregate_reason = "epic_aggregate_stage_count_zero"
        route_violations.append({"reason": aggregate_reason})
    if failed_children:
        aggregate_ok = False
        aggregate_reason = aggregate_reason or "child_sprint_failed"
    if active_children:
        aggregate_ok = False
        aggregate_reason = aggregate_reason or "active_children_not_terminal"
    if missing_route_proofs:
        aggregate_ok = False
        aggregate_reason = aggregate_reason or "missing_child_route_proof"
    if route_violations:
        aggregate_ok = False
        aggregate_reason = aggregate_reason or "epic_route_proof_failed"
    if not artifact_manifest["all_expected_exist"] and not active_children and not failed_children:
        aggregate_ok = False
        aggregate_reason = aggregate_reason or "final_artifacts_missing"

    if failed_children:
        state = "failed"
        failure_class = "child_sprint_failed"
    elif active_children:
        state = "active"
        failure_class = ""
    elif route_violations or child_proofs_found == 0 or total_stage_count == 0 or missing_route_proofs:
        state = "failed"
        failure_class = "epic_route_proof_failed"
    elif not artifact_manifest["all_expected_exist"]:
        state = "failed"
        failure_class = "final_artifacts_missing"
    else:
        state = "passed"
        failure_class = ""

    # A stalled role-pool operator leaves the epic active with no route proofs and
    # no artifacts. Name that wedge explicitly so it is not confused with a plain
    # in-progress epic. Never overrides a genuine pass.
    role_pool_wedge = detect_role_pool_wedge(harness_dir, children)
    builder_stall = detect_builder_stall(harness_dir, children)
    orchestration_wedge = bool(role_pool_wedge or builder_stall) and state != "passed"
    epic_classification = (
        ORCHESTRATION_WEDGE_CLASSIFICATION if orchestration_wedge else f"EPIC_{state.upper()}"
    )

    route_proof = {
        "ok": aggregate_ok,
        "reason": aggregate_reason,
        "generated_at": _utc_now(),
        "epic_id": epic_id,
        "selected_runtime": selected_runtime,
        "allowed_providers": sorted(allowed),
        "total_stage_count": total_stage_count,
        "stage_count": total_stage_count,
        "child_count": len(children),
        "child_sprints": children,
        "providers_observed": sorted(providers),
        "violations": route_violations,
        "missing_route_proofs": missing_route_proofs,
        "failed_children": failed_children,
        "active_children": active_children,
        "completed_children": completed_children,
        "artifact_status": artifact_manifest,
    }

    return {
        "ok": state == "passed",
        "state": state,
        "failure_class": failure_class,
        "reason": aggregate_reason,
        "classification": epic_classification,
        "orchestration_wedge": orchestration_wedge,
        "role_pool_wedge": role_pool_wedge,
        "builder_stall": builder_stall,
        "epic_id": epic_id,
        "metadata_path": str(meta_path),
        "metadata_exists": meta_path.exists(),
        "task_graph_path": str(graph_path),
        "task_graph_exists": graph_path.exists(),
        "required_child_sprints": required,
        "child_sprints": child_rows,
        "route_proof": route_proof,
        "artifact_manifest": artifact_manifest,
    }


def write_epic_outputs(evidence_dir: Path, summary: dict[str, Any], *, marker_mode: str = "none", timeout_seconds: int | None = None) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _write_json(evidence_dir / "epic-child-status-summary.json", {
        "epic_id": summary["epic_id"],
        "state": summary["state"],
        "reason": summary.get("reason"),
        "metadata_path": summary["metadata_path"],
        "task_graph_path": summary["task_graph_path"],
        "children": summary["child_sprints"],
    })
    _write_json(evidence_dir / "epic-route-proof.json", summary["route_proof"])
    _write_json(evidence_dir / "epic-artifact-manifest.json", summary["artifact_manifest"])

    if marker_mode == "timeout":
        payload = {
            "valid": False,
            "reason": "epic_in_progress_not_product_proof",
            "epic_id": summary["epic_id"],
            "timeout_seconds": timeout_seconds,
            "active_child_sprints": summary["route_proof"]["active_children"],
            "completed_child_sprints": summary["route_proof"]["completed_children"],
            "missing_child_route_proofs": summary["route_proof"]["missing_route_proofs"],
            "latest_updated_at_by_child": {
                child["child_id"]: child.get("updated_at")
                for child in summary["child_sprints"]
            },
            "implementation_child_started": any(
                ("core-runtime" in child["child_id"] or "implementation" in child["child_id"])
                and child["executed"]
                for child in summary["child_sprints"]
            ),
            "expected_final_artifacts_exist": summary["artifact_manifest"]["all_expected_exist"],
            "artifact_status": summary["artifact_manifest"],
            "explanation": "Epic child work was still non-terminal at timeout; this is not product proof.",
            "written_at": _utc_now(),
        }
        _write_json(evidence_dir / "EPIC_IN_PROGRESS_NOT_PRODUCT_PROOF.json", payload)
        if summary.get("orchestration_wedge"):
            _write_json(evidence_dir / "ORCHESTRATION_WEDGE_NOT_PRODUCT_PROOF.json", {
                "valid": False,
                "classification": ORCHESTRATION_WEDGE_CLASSIFICATION,
                "reason": "role_pool_inflight_timeout",
                "epic_id": summary["epic_id"],
                "role_pool_wedge": summary.get("role_pool_wedge", []),
                "builder_stall": summary.get("builder_stall", []),
                "active_child_sprints": summary["route_proof"]["active_children"],
                "written_at": _utc_now(),
            })
    elif marker_mode == "terminal":
        if summary["failure_class"] == "child_sprint_failed":
            _write_json(evidence_dir / "CHILD_SPRINT_FAILED.json", {
                "valid": False,
                "reason": "child_sprint_failed",
                "epic_id": summary["epic_id"],
                "failed_children": summary["route_proof"]["failed_children"],
                "written_at": _utc_now(),
            })
        elif summary["failure_class"] == "epic_route_proof_failed":
            _write_json(evidence_dir / "EPIC_ROUTE_PROOF_FAILED.json", {
                "valid": False,
                "reason": summary["route_proof"].get("reason") or "epic_route_proof_failed",
                "epic_id": summary["epic_id"],
                "violations": summary["route_proof"]["violations"],
                "missing_route_proofs": summary["route_proof"]["missing_route_proofs"],
                "total_stage_count": summary["route_proof"]["total_stage_count"],
                "written_at": _utc_now(),
            })
        elif summary["failure_class"] == "final_artifacts_missing":
            _write_json(evidence_dir / "EPIC_FINAL_ARTIFACTS_MISSING.json", {
                "valid": False,
                "reason": "final_artifacts_missing",
                "epic_id": summary["epic_id"],
                "artifact_status": summary["artifact_manifest"],
                "written_at": _utc_now(),
            })


def _parse_contract_substitutions(values: list[str]) -> dict[str, str]:
    substitutions: dict[str, str] = {}
    for raw in values or []:
        key, sep, value = str(raw or "").partition("=")
        key = key.strip().strip("<>")
        if sep and key:
            substitutions[key] = value.strip()
    return substitutions


def _contract_load_failed_summary(
    *,
    run_id: str,
    contract_path: str,
    error: str,
    terminal: bool,
) -> dict[str, Any]:
    return {
        "ok": False,
        "state": "failed",
        "failure_class": "contract_load_failed",
        "classification": "CONTRACT_LOAD_FAILED",
        "reason": "contract_load_failed",
        "run_id": run_id,
        "run_type": "sprint",
        "generated_at": _utc_now(),
        "terminal": terminal,
        "not_product_proof": True,
        "not_full_epic_product_proof": False,
        "active_or_drafting_runs": [],
        "raw_expected_artifacts": [],
        "expected_artifacts": [],
        "artifact_manifest": {"workspace": "", "roots": [], "expected_artifacts": [], "path_errors": []},
        "artifact_root_conflicts": [],
        "artifact_conflict_resolution": "",
        "test_result": {"ran": False, "ok": False, "reason": "contract_load_failed", "command": ""},
        "route_proof": {"ok": False, "reason": "contract_load_failed", "run_ids": [run_id]},
        "producers": [],
        "active_producers": [],
        "artifact_stability": {"stable": False, "reason": "contract_load_failed"},
        "contract": {"source_path": contract_path, "error": error},
        "blocking_failures": [{"reason": "contract_load_failed", "error": error}],
        "pending_reasons": [],
        "explanation": "Contract artifact validation failed before legacy artifact inference.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_type = sub.add_parser("type")
    p_type.add_argument("--harness-dir", required=True)
    p_type.add_argument("--id", required=True)

    p_sum = sub.add_parser("summarize")
    p_sum.add_argument("--harness-dir", required=True)
    p_sum.add_argument("--epic-id", required=True)
    p_sum.add_argument("--evidence-dir", required=True)
    p_sum.add_argument("--workspace", required=True)
    p_sum.add_argument("--task", default="")
    p_sum.add_argument("--required-child", action="append", default=[])
    p_sum.add_argument("--marker-mode", choices=["none", "timeout", "terminal"], default="none")
    p_sum.add_argument("--timeout-seconds", type=int, default=None)

    p_art = sub.add_parser("artifact-check")
    p_art.add_argument("--harness-dir", required=True)
    p_art.add_argument("--id", required=True)
    p_art.add_argument("--evidence-dir", required=True)
    p_art.add_argument("--workspace", required=True)
    p_art.add_argument("--task", default="")
    p_art.add_argument("--expect-artifact", action="append", default=[])
    p_art.add_argument("--contract", default="")
    p_art.add_argument("--contract-substitution", action="append", default=[], metavar="KEY=VALUE")
    p_art.add_argument("--test-command", default="python3 -m pytest -q")
    p_art.add_argument("--test-timeout-seconds", type=int, default=300)
    p_art.add_argument("--marker-mode", choices=["none", "terminal"], default="none")
    p_art.add_argument("--allow-absolute-artifacts", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    if args.cmd == "type":
        print(result_type(Path(args.harness_dir), args.id))
        return 0
    if args.cmd == "artifact-check":
        contract_options: dict[str, Any] = {}
        contract_roots: list[tuple[Path, str]] | None = None
        expected_artifacts = list(args.expect_artifact or []) or None
        test_command = args.test_command
        if str(args.contract or "").strip():
            substitutions = _parse_contract_substitutions(list(args.contract_substitution or []))
            try:
                contract_options = contract_artifact_options(
                    Path(args.contract),
                    sid=args.id,
                    substitutions=substitutions,
                    harness_dir=Path(args.harness_dir),
                    workspace=Path(args.workspace),
                )
            except ContractArtifactOptionsError as exc:
                summary = _contract_load_failed_summary(
                    run_id=args.id,
                    contract_path=str(args.contract),
                    error=str(exc),
                    terminal=args.marker_mode == "terminal",
                )
                _write_json(Path(args.evidence_dir) / "artifact-validation-summary.json", summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 2
            expected_artifacts = list(contract_options.get("expected_artifacts") or [])
            contract_roots = [
                (row["root"], row["type"])
                for row in contract_options.get("roots") or []
                if isinstance(row, dict) and row.get("root")
            ]
            if contract_options.get("validator_command"):
                test_command = _contract_command_for_copy(
                    str(contract_options["validator_command"]), Path(args.harness_dir)
                )
        summary = summarize_artifact_validation(
            Path(args.harness_dir),
            args.id,
            workspace=Path(args.workspace),
            task=args.task,
            expected_artifacts=expected_artifacts,
            test_command=test_command,
            test_timeout_seconds=args.test_timeout_seconds,
            terminal=args.marker_mode == "terminal",
            allow_absolute_artifacts=args.allow_absolute_artifacts,
            stability_state_path=Path(args.evidence_dir) / "artifact-stability-state.json",
            resolution_roots=contract_roots,
            producer_terminal_states=contract_options.get("terminal_states") if contract_options else None,
            contract_summary={
                key: contract_options.get(key)
                for key in ("workflow_id", "version", "identity", "source_path")
            } if contract_options else None,
        )
        write_artifact_validation_outputs(Path(args.evidence_dir), summary, marker_mode=args.marker_mode)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        state = summary["state"]
        # 0=passed, 1=failed, 3=incomplete (terminal, producers active/unstable), 124=pending.
        return 0 if state == "passed" else (1 if state == "failed" else (3 if state == "incomplete" else 124))

    summary = summarize_epic(
        Path(args.harness_dir),
        args.epic_id,
        workspace=Path(args.workspace),
        task=args.task,
        required_child_ids=list(args.required_child or []) or None,
    )
    write_epic_outputs(Path(args.evidence_dir), summary, marker_mode=args.marker_mode, timeout_seconds=args.timeout_seconds)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["state"] == "passed" else (1 if summary["state"] == "failed" else 124)


if __name__ == "__main__":
    raise SystemExit(main())
