#!/usr/bin/env python3
"""Run the fixed research UAT only through shipped Solar command surfaces.

This utility is deliberately not a scheduler.  It invokes ``solar-harness.sh``
for intake and graph-dispatch ticks, then polls the durable TaskGraph.  Solar's
dispatcher, operator runtime, operatord, evaluator, ledger, and reconciliation
remain the only components that change workflow state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_HARNESS = Path(__file__).resolve().parents[1]
REPO_ROOT = SOURCE_HARNESS.parent
LIB_DIR = SOURCE_HARNESS / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from fixed_research_workflow import (  # noqa: E402
    PART_A_NODE_IDS,
    PART_B_NODE_IDS,
    PHYSICAL_OPERATOR_BY_NODE,
    WORKFLOW_ID,
    validate_source_pack,
)


SCHEMA = "solar.fixed_research.shipped_uat.v1"
MODEL_NODE_IDS = {"evidence_synthesis", "report_draft", "independent_review", "report_revision"}
PRE_APPROVAL_PASSED = (*PART_A_NODE_IDS, "poc_handoff", "idea_evaluation", "experiment_design")
POST_APPROVAL_PENDING = ("experiment_run", "claim_verification", "final_delivery")
SECRET_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "AUTOSCI_REVIEW_LLM_API_KEY",
    "AUTOSCI_RESEARCH_LLM_API_KEY",
    "ZHIPU_API_KEY",
    "ZHIPU_AUTH_TOKEN",
}
SOURCE_FILES = (
    "solar-harness.sh",
    "lib/graph_node_dispatcher.py",
    "lib/graph_scheduler.py",
    "lib/operator_runtime.py",
    "lib/symphony/status-server.py",
    "status-server/routes/orchestration_routes.py",
    "lib/fixed_research_workflow.py",
    "lib/workflow_contract.py",
    "lib/workflow_intake.py",
    "lib/workflow_router.py",
    "tools/operatord.py",
    "tools/fixed_research_benchmark.py",
    "tools/fixed_research_uat.py",
    "plugins/autosci/bin/fixed_research_node_adapter.py",
    "plugins/autosci/backends/literature_discover.py",
    "plugins/autosci/operators/fixed_research_poc.py",
    "plugins/autosci/operators/research_synthesis/evidence_synthesis.py",
    "plugins/autosci/operators/research_synthesis/report_draft.py",
    "plugins/autosci/operators/research_synthesis/report_revision.py",
    "plugins/autosci/operators/research_synthesis/source_discovery.py",
    "plugins/autosci/operators/research_synthesis/source_validation.py",
    "plugins/autosci/services/codex_research.py",
    "plugins/autosci/services/production_research.py",
    "config/capability-capsules.registry.yaml",
    "config/capability-capsules/cap.research-seed-snapshot.yaml",
    "config/capability-capsules/cap.research-public-source-discovery.yaml",
    "config/capability-capsules/cap.research-source-validation.yaml",
    "config/capability-capsules/cap.research-experiment-approval.yaml",
    "config/capability-capsules/cap.research-evidence-poc-experiment-run.yaml",
    "config/capability-capsules/cap.research-evidence-poc-claim-verification.yaml",
    "config/capability-capsules/cap.research-evidence-poc-final-delivery.yaml",
    "config/capability-capsules/cap.research-evidence-synthesis.yaml",
    "config/capability-capsules/cap.research-report-draft.yaml",
    "config/capability-capsules/cap.research-independent-review.yaml",
    "config/capability-capsules/cap.research-report-revision.yaml",
    "config/capability-capsules/cap.research-final-acceptance.yaml",
    "config/capability-capsules/cap.research-evidence-poc-handoff.yaml",
    "config/capability-capsules/cap.research-poc-idea-evaluation.yaml",
    "config/capability-capsules/cap.research-poc-experiment-design.yaml",
    "config/workflows/research.evidence_to_poc.v1.workflow.json",
    "config/physical-operators.json",
    "schemas/evidence/fixed_research_part_b.v1.schema.json",
    "schemas/evidence/fixed_research_human_approval.v1.schema.json",
)


class UATError(RuntimeError):
    """The UAT entry failed closed before reaching its requested boundary."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UATError(f"invalid JSON artifact: {path}: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise UATError(f"JSON artifact must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise UATError(f"{label} must be a regular non-symlink file: {path}")
    return path.resolve(strict=True)


def _source_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in SOURCE_FILES:
        path = _regular_file(SOURCE_HARNESS / relative, "shipped source")
        data = path.read_bytes()
        rows.append({"path": relative, "bytes": len(data), "sha256": _sha(data)})
    return rows


def _git_source() -> dict[str, Any]:
    head = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    if head.returncode != 0 or len(head.stdout.strip()) != 40:
        raise UATError("repository HEAD is unavailable")
    diff = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--binary", "HEAD"],
        capture_output=True,
        check=False,
        timeout=30,
    )
    status_result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "-z"],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if diff.returncode != 0 or status_result.returncode != 0:
        raise UATError("repository diff provenance is unavailable")
    status_rows = [item for item in status_result.stdout.split(b"\0") if item]
    required_files = _source_inventory()
    return {
        "head": head.stdout.strip(),
        "tracked_diff_sha256": _sha(diff.stdout),
        "status_sha256": _sha(status_result.stdout),
        "dirty": bool(status_rows),
        "status_row_count": len(status_rows),
        "required_files": required_files,
        "required_files_sha256": _sha(
            json.dumps(required_files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ),
    }


def _selected_model_provider() -> str:
    return str(os.environ.get("SOLAR_RESEARCH_MODEL_PROVIDER") or "codex").strip().lower()


def _claude_preflight() -> dict[str, Any]:
    """Verify the Claude CLI the model stages will actually invoke.

    The Codex preflight demanded a Codex binary and auth file even when the
    selected provider was Claude -- the same shape as the adapter defects: one
    component imposing a requirement another component had already made
    unsatisfiable. The Claude CLI manages its own authentication state, so the
    checkable preconditions here are presence and executability; an
    unauthenticated CLI still fails closed at the first model stage.
    """
    binary_raw = shutil.which("claude")
    if not binary_raw:
        raise UATError("Claude CLI is unavailable on PATH")
    launcher = Path(binary_raw).absolute()
    try:
        resolved = launcher.resolve(strict=True)
    except OSError as exc:
        raise UATError(f"Claude executable cannot be resolved: {launcher}") from exc
    binary = _regular_file(resolved, "Claude executable target")
    if not os.access(binary, os.X_OK):
        raise UATError(f"Claude executable is not executable: {binary}")
    return {
        "provider": "claude",
        "launcher": str(launcher),
        "binary": str(binary),
        "binary_sha256": _sha(binary.read_bytes()),
        "auth_home": "",
        "auth_file_present": False,
        "auth_managed_by_cli": True,
        "credential_contents_recorded": False,
    }


def _codex_preflight(codex_binary: Path, codex_home: Path) -> dict[str, Any]:
    launcher = codex_binary.expanduser().absolute()
    try:
        resolved_launcher = launcher.resolve(strict=True)
    except OSError as exc:
        raise UATError(f"Codex executable cannot be resolved: {launcher}") from exc
    # npm installs command-line tools as symlinks. Resolve and hash the regular
    # target instead of rejecting the normal installation shape, while still
    # refusing a missing, non-regular, or non-executable target.
    binary = _regular_file(resolved_launcher, "Codex executable target")
    if not os.access(binary, os.X_OK):
        raise UATError(f"Codex executable is not executable: {binary}")
    home = codex_home.expanduser().resolve(strict=True)
    auth = _regular_file(home / "auth.json", "Codex subscription auth")
    mode = stat.S_IMODE(auth.stat().st_mode)
    if mode & 0o077:
        raise UATError("Codex subscription auth must not be accessible by group or others")
    return {
        "launcher": str(launcher),
        "binary": str(binary),
        "binary_sha256": _sha(binary.read_bytes()),
        "auth_home": str(home),
        "auth_file_present": True,
        "auth_file_mode": oct(mode),
        "credential_contents_recorded": False,
    }


def _registry_preflight() -> dict[str, Any]:
    contract = _read_json(SOURCE_HARNESS / "config/workflows/research.evidence_to_poc.v1.workflow.json")
    if contract.get("workflow_id") != WORKFLOW_ID or contract.get("stages_mode") != "fixed":
        raise UATError("fixed workflow contract is missing or not fixed")
    registry = _read_json(SOURCE_HARNESS / "config/physical-operators.json")
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    missing = sorted(set(PHYSICAL_OPERATOR_BY_NODE.values()) - set(operators))
    unavailable = sorted(
        operator_id
        for operator_id in PHYSICAL_OPERATOR_BY_NODE.values()
        if not bool((operators.get(operator_id) or {}).get("enabled"))
        or not bool((operators.get(operator_id) or {}).get("available"))
    )
    if missing or unavailable:
        raise UATError(f"fixed operator registry is not dispatchable: missing={missing}, unavailable={unavailable}")
    shell = (SOURCE_HARNESS / "solar-harness.sh").read_text(encoding="utf-8")
    if "approve-fixed-experiment" not in shell:
        raise UATError("shipped graph-dispatch approval command is unavailable")
    return {
        "workflow_id": WORKFLOW_ID,
        "workflow_version": contract.get("version"),
        "operator_ids": [PHYSICAL_OPERATOR_BY_NODE[node_id] for node_id in (*PART_A_NODE_IDS, *PART_B_NODE_IDS)],
        "max_parallel": 1,
    }


def _ensure_runtime_harness(runtime_harness: Path) -> None:
    runtime_harness.mkdir(parents=True, exist_ok=False)
    for name in ("lib", "tools", "plugins", "personas", "config", "schemas", "scripts"):
        source = SOURCE_HARNESS / name
        if source.is_dir():
            (runtime_harness / name).symlink_to(source, target_is_directory=True)


def _runtime_live(runtime_harness: Path) -> list[dict[str, Any]]:
    registry = SOURCE_HARNESS / "lib/run_process_registry.py"
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(runtime_harness)
    result = subprocess.run(
        [sys.executable, str(registry), "status", "--run-id", "harness"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        raise UATError("run process registry status is unavailable")
    payload = json.loads(result.stdout)
    live = payload.get("live") if isinstance(payload.get("live"), list) else []
    return [item for item in live if isinstance(item, dict)]


def _require_quiescent(runtime_harness: Path) -> None:
    live = _runtime_live(runtime_harness)
    inbox = runtime_harness / "run/operator-inbox"
    queued = list(inbox.glob("*/*.json")) if inbox.exists() else []
    if live or queued:
        raise UATError(f"isolated UAT runtime is not quiescent: live={len(live)}, queued={len(queued)}")


def _runtime_env(
    *,
    runtime_harness: Path,
    evidence_root: Path,
    workspace_root: Path,
    source_pack: Path,
    authority_root: Path,
    codex_home: Path,
    acquisition_mode: str = "source_pack",
    experiment_policy: str = "",
    policy_actor: str = "",
    policy_statement: str = "",
) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in SECRET_ENV_KEYS}
    env.update(
        {
            "HARNESS_DIR": str(runtime_harness),
            "SOLAR_HARNESS_DIR": str(runtime_harness),
            "HARNESS_SPRINTS_DIR": str(evidence_root / "sprints"),
            "SOLAR_HARNESS_SPRINTS_DIR": str(evidence_root / "sprints"),
            "SOLAR_INTENT_GATEWAY_DIR": str(evidence_root / "intents"),
            "SOLAR_INTAKE_WORKSPACE_ROOT": str(workspace_root),
            "SOLAR_KNOWLEDGE_RAW_DIR": str(evidence_root / "knowledge-raw"),
            "SOLAR_RESEARCH_SOURCE_PACK_ROOT": str(authority_root),
            "SOLAR_RESEARCH_SOURCE_PACK": str(source_pack),
            "SOLAR_RESEARCH_EXECUTION_PROFILE": "part_a_plus_poc",
            "SOLAR_WORKFLOW_ROUTER": "1",
            "SOLAR_PRODUCT_MODE": "0",
            "SOLAR_INTENT_REWRITE_CMD": "",
            "SOLAR_GATE_LEDGER": "1",
            "SOLAR_OPERATORD_AUTO_KICK": "1",
            "SOLAR_MULTI_TASK_OPERATORS": str(runtime_harness / "config/physical-operators.json"),
            "SOLAR_CODEX_SOURCE_HOME": str(codex_home),
            "SOLAR_CODEX_OPERATOR_STATE_ROOT": str(evidence_root / "runtime/codex-state"),
        }
    )
    env["SOLAR_RESEARCH_ACQUISITION_MODE"] = acquisition_mode
    if acquisition_mode in {"live_search", "hybrid"}:
        # Intake refuses live acquisition without the exact public no-key
        # retrieval policy, so selecting a live mode selects the policy too.
        env["SOLAR_RESEARCH_RETRIEVAL_POLICY"] = "public_bibliographic_no_key_v1"
    if experiment_policy:
        env["SOLAR_RESEARCH_EXPERIMENT_POLICY"] = experiment_policy
        env["SOLAR_RESEARCH_EXPERIMENT_POLICY_ACTOR"] = policy_actor
        env["SOLAR_RESEARCH_EXPERIMENT_POLICY_STATEMENT"] = policy_statement
    return env


def _manifest_env(env: dict[str, str]) -> dict[str, str]:
    allowed = (
        "HARNESS_DIR",
        "HARNESS_SPRINTS_DIR",
        "SOLAR_HARNESS_SPRINTS_DIR",
        "SOLAR_INTENT_GATEWAY_DIR",
        "SOLAR_INTAKE_WORKSPACE_ROOT",
        "SOLAR_KNOWLEDGE_RAW_DIR",
        "SOLAR_RESEARCH_SOURCE_PACK_ROOT",
        "SOLAR_RESEARCH_SOURCE_PACK",
        "SOLAR_RESEARCH_EXECUTION_PROFILE",
        "SOLAR_RESEARCH_ACQUISITION_MODE",
        "SOLAR_RESEARCH_RETRIEVAL_POLICY",
        "SOLAR_RESEARCH_MODEL_PROVIDER",
        "SOLAR_RESEARCH_MODEL",
        "SOLAR_WORKFLOW_ROUTER",
        "SOLAR_PRODUCT_MODE",
        "SOLAR_GATE_LEDGER",
        "SOLAR_OPERATORD_AUTO_KICK",
        "SOLAR_MULTI_TASK_OPERATORS",
        "SOLAR_CODEX_SOURCE_HOME",
        "SOLAR_CODEX_OPERATOR_STATE_ROOT",
        "SOLAR_CODEX_RESEARCH_MODEL",
        "SOLAR_CODEX_REVIEW_MODEL",
        "SOLAR_CODEX_RESEARCH_REASONING_EFFORT",
        "SOLAR_RESEARCH_EXPERIMENT_POLICY",
        "SOLAR_RESEARCH_EXPERIMENT_POLICY_ACTOR",
        "SOLAR_RESEARCH_EXPERIMENT_POLICY_STATEMENT",
    )
    return {key: env[key] for key in allowed if key in env}


def _command_receipt(
    *,
    sequence: int,
    label: str,
    argv: list[str],
    result: subprocess.CompletedProcess[str],
    started_at: str,
    elapsed_ms: float,
    uat_dir: Path,
) -> dict[str, Any]:
    stem = f"{sequence:04d}-{label}"
    stdout_path = uat_dir / "commands" / f"{stem}.stdout.log"
    stderr_path = uat_dir / "commands" / f"{stem}.stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    receipt = {
        "schema": "solar.fixed_research.uat_command.v1",
        "sequence": sequence,
        "label": label,
        "argv": argv,
        "started_at": started_at,
        "elapsed_ms": round(elapsed_ms, 3),
        "returncode": result.returncode,
        "stdout": {"path": str(stdout_path), "sha256": _sha(stdout_path.read_bytes())},
        "stderr": {"path": str(stderr_path), "sha256": _sha(stderr_path.read_bytes())},
    }
    _write_json(uat_dir / "commands" / f"{stem}.json", receipt)
    return receipt


# `graph-dispatch` exits 2 whenever its result payload carries ok=false, and a
# poll tick that dispatches nothing is one of those cases.  In a single-threaded
# run the eval pass routinely finds its only candidate still waiting on the
# builder that produces the artifacts it grades.  That is the loop working, not
# a failure, so it must not abort the run -- while every other non-zero exit,
# including a specialization-guard rejection, stays fatal.
TRANSIENT_DISPATCH_SKIP_REASONS = frozenset({
    "deterministic_gate_waiting_for_builder",
})


def _is_transient_dispatch_noop(stdout: str) -> bool:
    try:
        payload = json.loads((stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False
    if not isinstance(payload, dict) or payload.get("ok") is not False:
        return False
    # A tick that actually moved the graph, or reported an error, is never
    # transient.
    if payload.get("dispatched") or payload.get("terminalized") or payload.get("errors"):
        return False
    if payload.get("reason"):
        return False
    skipped = payload.get("skipped")
    if not isinstance(skipped, list) or not skipped:
        return False
    return all(
        isinstance(item, dict)
        and str(item.get("reason") or item.get("skip_reason") or "") in TRANSIENT_DISPATCH_SKIP_REASONS
        for item in skipped
    )


class CommandRunner:
    def __init__(self, *, env: dict[str, str], uat_dir: Path, cwd: Path) -> None:
        self.env = env
        self.uat_dir = uat_dir
        self.cwd = cwd
        self.sequence = len(list((uat_dir / "commands").glob("*.json"))) if (uat_dir / "commands").exists() else 0

    def run(
        self,
        label: str,
        argv: list[str],
        *,
        timeout: int = 180,
        tolerate_transient_noop: bool = False,
    ) -> dict[str, Any]:
        self.sequence += 1
        started_at = _now()
        started = time.monotonic()
        result = subprocess.run(
            argv,
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        receipt = _command_receipt(
            sequence=self.sequence,
            label=label,
            argv=argv,
            result=result,
            started_at=started_at,
            elapsed_ms=(time.monotonic() - started) * 1000,
            uat_dir=self.uat_dir,
        )
        if result.returncode != 0:
            if tolerate_transient_noop and _is_transient_dispatch_noop(result.stdout):
                receipt["transient_noop"] = True
                _write_json(self.uat_dir / "commands" / f"{receipt['sequence']:04d}-{label}.json", receipt)
                return receipt
            raise UATError(f"public command failed: {label} rc={result.returncode}; receipt={receipt['sequence']}")
        return receipt


def _shell_command(*args: str) -> list[str]:
    return ["bash", str(SOURCE_HARNESS / "solar-harness.sh"), *args]


def _new_graph(sprints: Path, before: set[Path]) -> Path:
    after = set(sprints.glob("*.task_graph.json"))
    created = sorted(after - before)
    if len(created) != 1:
        raise UATError(f"intake must create exactly one TaskGraph, observed={len(created)}")
    _require_fixed_graph(created[0])
    return created[0]


def _require_fixed_graph(graph_path: Path) -> dict[str, Any]:
    graph = _read_json(graph_path)
    if graph.get("workflow_contract_id") != WORKFLOW_ID:
        raise UATError("intake did not select the exact fixed research workflow")
    if graph.get("execution_profile") != {"kind": "part_a_plus_poc", "part_b": "enabled"}:
        raise UATError("intake did not persist part_a_plus_poc")
    if graph.get("execution_mode") != "single_threaded" or (graph.get("codex_execution") or {}).get("max_parallel") != 1:
        raise UATError("fixed graph does not enforce max parallel 1")
    if [str(item.get("id") or "") for item in graph.get("nodes") or []] != [*PART_A_NODE_IDS, *PART_B_NODE_IDS]:
        raise UATError("dashboard-created graph does not preserve the fixed 15-node topology")
    return graph


def _wait_for_dashboard_graph(
    *,
    sprints: Path,
    request_id: str,
    timeout_seconds: int,
    poll_seconds: float,
) -> Path:
    """Wait for exactly one graph attributed to a dashboard request.

    This function is read-only.  The dashboard/status-server remains the only
    component that invokes intake and creates the sprint.
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        matches: list[Path] = []
        for status_path in sorted(sprints.glob("*.status.json")) if sprints.exists() else []:
            status = _read_json(status_path)
            if str(status.get("request_id") or status.get("intake_request_id") or "") != request_id:
                continue
            sid = str(status.get("sprint_id") or status.get("id") or status_path.name.removesuffix(".status.json"))
            graph_path = sprints / f"{sid}.task_graph.json"
            if graph_path.is_file() and not graph_path.is_symlink():
                matches.append(graph_path)
        if len(matches) > 1:
            raise UATError(f"dashboard request is ambiguously bound to {len(matches)} sprints")
        if len(matches) == 1:
            _require_fixed_graph(matches[0])
            return matches[0]
        time.sleep(max(0.1, poll_seconds))
    raise UATError(f"timed out waiting for dashboard request {request_id}")


def _capture_dashboard_surfaces(*, base_url: str, sprint_id: str, output_dir: Path) -> list[dict[str, Any]]:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise UATError("dashboard evidence URL must be loopback HTTP")
    endpoints = {
        "projection": f"/api/sprints/{urllib.parse.quote(sprint_id)}/projection",
        "events": f"/events?sprint_id={urllib.parse.quote(sprint_id)}&limit=500",
        "deliverables": f"/sprints/{urllib.parse.quote(sprint_id)}/deliverables",
    }
    rows: list[dict[str, Any]] = []
    for label, suffix in endpoints.items():
        url = base_url.rstrip("/") + suffix
        request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(4 * 1024 * 1024 + 1)
            status = int(getattr(response, "status", 200) or 200)
        if status != 200 or len(body) > 4 * 1024 * 1024:
            raise UATError(f"dashboard {label} evidence was unavailable or oversized")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, (dict, list)):
            raise UATError(f"dashboard {label} evidence was not JSON")
        path = output_dir / f"{label}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        rows.append({"label": label, "url": suffix, "path": str(path), "sha256": _sha(body), "bytes": len(body)})
    return rows


def _one_shot_policy(graph_path: Path, graph: dict[str, Any], *, actor: str, statement: str) -> dict[str, Any]:
    metadata = graph.get("experiment_policy") if isinstance(graph.get("experiment_policy"), dict) else {}
    if metadata.get("mode") != "policy_preauthorized" or metadata.get("policy_id") != "evidence_lineage_integrity_v1":
        raise UATError("one-shot intake did not persist the exact fixed experiment policy")
    sid = str(graph.get("sprint_id") or "")
    relative = Path(str(metadata.get("path") or ""))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise UATError("one-shot experiment policy path is unsafe")
    policy_path = graph_path.parent / sid / "workdir" / relative
    policy_path = _regular_file(policy_path, "one-shot experiment policy")
    policy = _read_json(policy_path)
    if (
        _sha(policy_path.read_bytes()) != str(metadata.get("sha256") or "")
        or policy.get("schema") != "solar.fixed_research.experiment_policy_authorization.v1"
        or policy.get("policy_id") != "evidence_lineage_integrity_v1"
        or policy.get("sprint_id") != sid
        or policy.get("actor") != actor
        or policy.get("statement") != statement
    ):
        raise UATError("one-shot experiment policy attribution or hash binding is invalid")
    benchmark = policy.get("benchmark_policy") if isinstance(policy.get("benchmark_policy"), dict) else {}
    if (
        benchmark.get("benchmark_id") != "evidence-lineage-integrity-v1"
        or benchmark.get("runner") != "harness/tools/fixed_research_benchmark.py"
        or benchmark.get("network") != "none"
        or int(benchmark.get("timeout_max_seconds") or 0) > 60
        or benchmark.get("capabilities") != ["execute:fixed_evidence_lineage_benchmark", "network:none"]
    ):
        raise UATError("one-shot experiment policy exceeds the fixed demo boundary")
    return {"path": str(policy_path), "sha256": _sha(policy_path.read_bytes()), "payload": policy}


def _node_statuses(graph: dict[str, Any]) -> dict[str, str]:
    return {
        str(node.get("id") or ""): str(node.get("status") or "pending")
        for node in graph.get("nodes") or []
        if isinstance(node, dict)
    }


def _approval_request(graph_path: Path, graph: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    sid = str(graph.get("sprint_id") or "")
    request_path = graph_path.parent / sid / "workdir/artifacts/research_evidence_to_poc/poc/approval/approval_request.json"
    request = _read_json(request_path)
    if request.get("schema") != "solar.fixed_research.approval_request.v1":
        raise UATError("B4 approval request has an unexpected schema")
    return request_path, request


def _pause_reached(graph_path: Path) -> dict[str, Any] | None:
    graph = _read_json(graph_path)
    statuses = _node_statuses(graph)
    failed = {node: status for node, status in statuses.items() if status in {"failed", "cancelled", "skipped"}}
    if failed:
        raise UATError(f"workflow reached a terminal failure before approval: {failed}")
    other_human = {
        node: status for node, status in statuses.items()
        if status == "needs_human_review" and node != "experiment_approval"
    }
    if other_human:
        raise UATError(f"workflow paused outside the expected B4 gate: {other_human}")
    if statuses.get("experiment_approval") != "needs_human_review":
        return None
    if any(statuses.get(node) != "passed" for node in PRE_APPROVAL_PASSED):
        raise UATError("B4 became reviewable before every required A1-B3 closeout passed")
    if any(statuses.get(node) != "pending" for node in POST_APPROVAL_PENDING):
        raise UATError("post-approval nodes did not remain pending at the B4 pause")
    request_path, request = _approval_request(graph_path, graph)
    return {
        "sprint_id": graph.get("sprint_id"),
        "graph_path": str(graph_path),
        "graph_sha256": _sha(graph_path.read_bytes()),
        "node_statuses": statuses,
        "approval_request": {
            "path": str(request_path),
            "sha256": _sha(request_path.read_bytes()),
            "generation": request.get("generation"),
            "plan_sha256": request.get("plan_sha256"),
            "approved_scope": request.get("approved_scope"),
            "approved_capabilities": request.get("approved_capabilities"),
        },
    }


def _final_reached(graph_path: Path) -> dict[str, Any] | None:
    graph = _read_json(graph_path)
    statuses = _node_statuses(graph)
    failed = {node: status for node, status in statuses.items() if status in {"failed", "cancelled", "skipped", "needs_human_review"}}
    if failed:
        raise UATError(f"workflow did not reach final acceptance: {failed}")
    expected = (*PART_A_NODE_IDS, *PART_B_NODE_IDS)
    if not all(statuses.get(node) == "passed" for node in expected):
        return None
    sid = str(graph.get("sprint_id") or "")
    delivery_dir = graph_path.parent / sid / "workdir/artifacts/research_evidence_to_poc/poc/final"
    delivery_json = _regular_file(delivery_dir / "final_delivery.json", "final delivery JSON")
    delivery_md = _regular_file(delivery_dir / "final_delivery.md", "final delivery Markdown")
    return {
        "sprint_id": sid,
        "graph_path": str(graph_path),
        "graph_sha256": _sha(graph_path.read_bytes()),
        "node_statuses": statuses,
        "final_delivery": {
            "json": {"path": str(delivery_json), "sha256": _sha(delivery_json.read_bytes())},
            "markdown": {"path": str(delivery_md), "sha256": _sha(delivery_md.read_bytes())},
        },
    }


def _advance(
    *,
    graph_path: Path,
    runner: CommandRunner,
    target: str,
    timeout_seconds: int,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        reached = _pause_reached(graph_path) if target == "approval" else _final_reached(graph_path)
        if reached is not None:
            return reached
        runner.run(
            "dispatch-ready",
            _shell_command("graph-dispatch", "dispatch-ready", "--graph", str(graph_path), "--max-parallel", "1"),
            tolerate_transient_noop=True,
        )
        runner.run(
            "dispatch-evals",
            _shell_command("graph-dispatch", "dispatch-evals", "--graph", str(graph_path), "--max-items", "1"),
            tolerate_transient_noop=True,
        )
        time.sleep(max(0.1, poll_seconds))
    raise UATError(f"timed out waiting for {target} boundary after {timeout_seconds}s")


def _acquire_lock(evidence_root: Path) -> Path:
    evidence_root.mkdir(parents=True, exist_ok=True)
    lock = evidence_root / ".fixed-research-uat.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise UATError(f"UAT root is already locked: {lock}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(f"pid={os.getpid()} created_at={_now()}\n")
    return lock


def _start(args: argparse.Namespace) -> dict[str, Any]:
    one_shot = args.phase == "start-to-final"
    evidence_root = Path(args.evidence_root).expanduser().absolute()
    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise UATError(f"{args.phase} requires a new empty evidence root: {evidence_root}")
    lock = _acquire_lock(evidence_root)
    try:
        source_pack = Path(args.source_pack).expanduser().resolve(strict=True)
        authority_root = Path(args.source_authority_root).expanduser().resolve(strict=True)
        request_file = _regular_file(Path(args.request_file).expanduser(), "request file")
        workspace_root = Path(args.workspace_root).expanduser().resolve(strict=True)
        if not workspace_root.is_dir():
            raise UATError(f"workspace root must be a directory: {workspace_root}")
        provider = _selected_model_provider()
        if provider == "claude":
            model_cli = _claude_preflight()
            codex_home = Path(args.codex_home).expanduser()
        else:
            codex_binary_raw = shutil.which("codex")
            if not codex_binary_raw:
                raise UATError("Codex CLI is unavailable on PATH")
            codex_home = Path(args.codex_home).expanduser().resolve(strict=True)
            model_cli = {"provider": "codex", **_codex_preflight(Path(codex_binary_raw), codex_home)}
        source_authority = validate_source_pack(source_pack, authority_root=authority_root)
        source_manifest = {key: value for key, value in source_authority.items() if key != "candidates"}
        runtime_harness = evidence_root / "runtime-harness"
        _ensure_runtime_harness(runtime_harness)
        _require_quiescent(runtime_harness)
        env = _runtime_env(
            runtime_harness=runtime_harness,
            evidence_root=evidence_root,
            workspace_root=workspace_root,
            source_pack=source_pack,
            authority_root=authority_root,
            codex_home=codex_home,
            acquisition_mode=str(getattr(args, "acquisition_mode", "") or "source_pack"),
            experiment_policy="evidence_lineage_integrity_v1" if one_shot else "",
            policy_actor=str(getattr(args, "policy_actor", "") or ""),
            policy_statement=str(getattr(args, "policy_statement", "") or ""),
        )
        uat_dir = evidence_root / "uat"
        intake_argv = _shell_command("intake", "--json", "--file", str(request_file))
        manifest = {
            "schema": SCHEMA,
            "phase": args.phase,
            "status": "preflight_passed",
            "created_at": _now(),
            "source": _git_source(),
            "registry": _registry_preflight(),
            "model_cli": model_cli,
            "request": {"path": str(request_file), "sha256": _sha(request_file.read_bytes()), "bytes": request_file.stat().st_size},
            "source_pack": source_manifest,
            "environment": _manifest_env(env),
            "entry_command": intake_argv,
            "runtime_harness": str(runtime_harness),
            "sprints_dir": str(evidence_root / "sprints"),
        }
        entry_path = uat_dir / "entry-manifest.json"
        _write_json(entry_path, manifest)
        if args.preflight_only:
            manifest["status"] = "preflight_only"
            _write_json(entry_path, manifest)
            return {"ok": True, "status": "preflight_only", "manifest": str(entry_path)}
        runner = CommandRunner(env=env, uat_dir=uat_dir, cwd=workspace_root)
        sprints = evidence_root / "sprints"
        before = set(sprints.glob("*.task_graph.json")) if sprints.exists() else set()
        runner.run("intake", intake_argv)
        graph_path = _new_graph(sprints, before)
        graph = _read_json(graph_path)
        manifest["sprint_id"] = graph.get("sprint_id")
        manifest["graph_path"] = str(graph_path)
        if one_shot:
            manifest["experiment_policy"] = _one_shot_policy(
                graph_path,
                graph,
                actor=str(args.policy_actor),
                statement=str(args.policy_statement),
            )
        manifest["status"] = "running_to_final" if one_shot else "running_to_approval"
        _write_json(entry_path, manifest)
        reached = _advance(
            graph_path=graph_path,
            runner=runner,
            target="final" if one_shot else "approval",
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        _require_quiescent(runtime_harness)
        if one_shot:
            reached["schema"] = SCHEMA
            reached["phase"] = "start-to-final"
            reached["status"] = "passed"
            final_path = uat_dir / "final.json"
            _write_json(final_path, reached)
            manifest["status"] = "passed"
            manifest["final_path"] = str(final_path)
            _write_json(entry_path, manifest)
            return {"ok": True, "status": "passed", "sprint_id": reached["sprint_id"], "final": str(final_path)}
        pause = reached
        request = pause["approval_request"]
        pause["schema"] = SCHEMA
        pause["phase"] = "start-to-approval"
        pause["status"] = "needs_human_review"
        pause["resume_command_template"] = [
            sys.executable,
            str(Path(__file__).resolve()),
            "resume-to-final",
            "--evidence-root",
            str(evidence_root),
            "--actor",
            "<human-actor>",
            "--statement",
            "<exact-human-approval-statement>",
            "--plan-sha256",
            str(request["plan_sha256"]),
            "--scope-json",
            json.dumps(request["approved_scope"], separators=(",", ":"), sort_keys=True),
            *[value for capability in request["approved_capabilities"] for value in ("--capability", str(capability))],
        ]
        pause_path = uat_dir / "pause.json"
        _write_json(pause_path, pause)
        manifest["status"] = "needs_human_review"
        manifest["pause_path"] = str(pause_path)
        _write_json(entry_path, manifest)
        return {"ok": True, "status": "needs_human_review", "sprint_id": pause["sprint_id"], "pause": str(pause_path)}
    finally:
        lock.unlink(missing_ok=True)


def _resume(args: argparse.Namespace) -> dict[str, Any]:
    evidence_root = Path(args.evidence_root).expanduser().resolve(strict=True)
    lock = _acquire_lock(evidence_root)
    try:
        uat_dir = evidence_root / "uat"
        entry_path = uat_dir / "entry-manifest.json"
        entry = _read_json(entry_path)
        if entry.get("schema") != SCHEMA or entry.get("status") != "needs_human_review":
            raise UATError("resume requires a completed start-to-approval manifest")
        graph_path = _regular_file(Path(str(entry.get("graph_path") or "")), "persisted TaskGraph")
        graph = _read_json(graph_path)
        pause = _pause_reached(graph_path)
        if pause is None:
            raise UATError("persisted graph is no longer at the B4 approval boundary")
        runtime_harness = Path(str(entry.get("runtime_harness") or "")).resolve(strict=True)
        _require_quiescent(runtime_harness)
        request = pause["approval_request"]
        try:
            scope = json.loads(args.scope_json)
        except json.JSONDecodeError as exc:
            raise UATError("--scope-json must be valid JSON") from exc
        if not isinstance(scope, dict):
            raise UATError("--scope-json must be an object")
        capabilities = list(args.capability or [])
        if args.plan_sha256 != request["plan_sha256"]:
            raise UATError("approval plan hash does not match the current B4 request")
        if scope != request["approved_scope"]:
            raise UATError("approval scope does not match the current B4 request")
        if capabilities != request["approved_capabilities"]:
            raise UATError("approval capabilities do not match the current B4 request")
        if not args.actor.strip() or not args.statement.strip():
            raise UATError("human actor and exact approval statement are required")
        env = {key: value for key, value in os.environ.items() if key not in SECRET_ENV_KEYS}
        env.update({str(key): str(value) for key, value in (entry.get("environment") or {}).items()})
        runner = CommandRunner(env=env, uat_dir=uat_dir, cwd=Path(env["SOLAR_INTAKE_WORKSPACE_ROOT"]))
        approval_argv = _shell_command(
            "graph-dispatch",
            "approve-fixed-experiment",
            "--graph",
            str(graph_path),
            "--generation",
            str(request["generation"]),
            "--actor",
            args.actor,
            "--statement",
            args.statement,
            "--plan-sha256",
            args.plan_sha256,
            "--scope-json",
            json.dumps(scope, separators=(",", ":"), sort_keys=True),
            *[value for capability in capabilities for value in ("--capability", capability)],
        )
        resume_manifest = {
            "schema": SCHEMA,
            "phase": "resume-to-final",
            "status": "approval_pending",
            "created_at": _now(),
            "sprint_id": graph.get("sprint_id"),
            "graph_path": str(graph_path),
            "approval_request_sha256": request["sha256"],
            "actor": args.actor,
            "statement": args.statement,
            "plan_sha256": args.plan_sha256,
            "scope": scope,
            "capabilities": capabilities,
            "approval_command": approval_argv,
        }
        resume_path = uat_dir / "resume-manifest.json"
        _write_json(resume_path, resume_manifest)
        runner.run("approve-fixed-experiment", approval_argv)
        resume_manifest["status"] = "running_to_final"
        _write_json(resume_path, resume_manifest)
        final = _advance(
            graph_path=graph_path,
            runner=runner,
            target="final",
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        _require_quiescent(runtime_harness)
        final["schema"] = SCHEMA
        final["phase"] = "resume-to-final"
        final["status"] = "passed"
        final_path = uat_dir / "final.json"
        _write_json(final_path, final)
        resume_manifest["status"] = "passed"
        resume_manifest["final_path"] = str(final_path)
        _write_json(resume_path, resume_manifest)
        entry["status"] = "passed"
        entry["final_path"] = str(final_path)
        _write_json(entry_path, entry)
        return {"ok": True, "status": "passed", "sprint_id": final["sprint_id"], "final": str(final_path)}
    finally:
        lock.unlink(missing_ok=True)


def _dashboard_runtime_env(
    *,
    runtime_harness: Path,
    evidence_root: Path,
    sprints: Path,
    codex_home: Path,
) -> dict[str, str]:
    """Environment for controller commands against a dashboard-created sprint.

    Unlike the start path, intake already ran inside the status server, so the
    intake-only variables are deliberately absent.  The run-scoping variables
    the dispatch-time guards read must still be present.
    """

    env = {key: value for key, value in os.environ.items() if key not in SECRET_ENV_KEYS}
    env.update({
        "HARNESS_DIR": str(runtime_harness),
        "SOLAR_HARNESS_DIR": str(runtime_harness),
        "HARNESS_SPRINTS_DIR": str(sprints),
        "SOLAR_HARNESS_SPRINTS_DIR": str(sprints),
        # The dashboard bound this sprint to an intent under the run's own
        # gateway root.  The dispatch-time specialization guard recomputes the
        # expected binding manifest from SOLAR_INTENT_GATEWAY_DIR, so without
        # it the guard looks under the default installed gateway and rejects a
        # perfectly valid binding as
        # fixed_research_intent_binding_evidence_invalid.
        "SOLAR_INTENT_GATEWAY_DIR": str(evidence_root / "intents"),
        "SOLAR_GATE_LEDGER": "1",
        "SOLAR_OPERATORD_AUTO_KICK": "1",
        "SOLAR_MULTI_TASK_OPERATORS": str(runtime_harness / "config/physical-operators.json"),
        "SOLAR_CODEX_SOURCE_HOME": str(codex_home),
        "SOLAR_CODEX_OPERATOR_STATE_ROOT": str(evidence_root / "runtime/codex-state"),
    })
    return env


def _drive_dashboard(args: argparse.Namespace) -> dict[str, Any]:
    """Drive a sprint that was already created by the dashboard front door."""

    evidence_root = Path(args.evidence_root).expanduser().resolve(strict=True)
    lock = _acquire_lock(evidence_root)
    try:
        sprints = evidence_root / "sprints"
        graph_path = _wait_for_dashboard_graph(
            sprints=sprints,
            request_id=args.request_id,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        graph = _require_fixed_graph(graph_path)
        sid = str(graph.get("sprint_id") or "")
        runtime_harness = Path(args.runtime_harness).expanduser().resolve(strict=True)
        request_receipt = _regular_file(
            runtime_harness / "run" / "intake-requests" / f"{args.request_id}.json",
            "dashboard intake request receipt",
        )
        request_payload = _read_json(request_receipt)
        if str(request_payload.get("request_id") or "") != args.request_id:
            raise UATError("dashboard intake receipt request id mismatch")
        _require_quiescent(runtime_harness)
        provider = _selected_model_provider()
        if provider == "claude":
            model_cli = _claude_preflight()
            codex_home = Path(args.codex_home).expanduser()
        else:
            codex_binary_raw = shutil.which("codex")
            if not codex_binary_raw:
                raise UATError("Codex CLI is unavailable on PATH")
            codex_home = Path(args.codex_home).expanduser().resolve(strict=True)
            model_cli = {"provider": "codex", **_codex_preflight(Path(codex_binary_raw), codex_home)}
        env = _dashboard_runtime_env(
            runtime_harness=runtime_harness,
            evidence_root=evidence_root,
            sprints=sprints,
            codex_home=codex_home,
        )
        workspace_root = Path(args.workspace_root).expanduser().resolve(strict=True)
        uat_dir = evidence_root / "uat-dashboard"
        policy = _one_shot_policy(graph_path, graph, actor=args.policy_actor, statement=args.policy_statement)
        manifest = {
            "schema": SCHEMA,
            "phase": "dashboard-to-final",
            "status": "dashboard_sprint_attributed",
            "created_at": _now(),
            "request_id": args.request_id,
            "request_receipt": {
                "path": str(request_receipt),
                "sha256": _sha(request_receipt.read_bytes()),
            },
            "sprint_id": sid,
            "graph_path": str(graph_path),
            "graph_sha256": _sha(graph_path.read_bytes()),
            "experiment_policy": policy,
            "source": _git_source(),
            "registry": _registry_preflight(),
            "model_cli": model_cli,
            "environment": _manifest_env(env),
            "intake_invoked_by_driver": False,
            "controller_commands": ["graph-dispatch dispatch-ready", "graph-dispatch dispatch-evals"],
        }
        manifest_path = uat_dir / "entry-manifest.json"
        _write_json(manifest_path, manifest)
        runner = CommandRunner(env=env, uat_dir=uat_dir, cwd=workspace_root)
        final = _advance(
            graph_path=graph_path,
            runner=runner,
            target="final",
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        _require_quiescent(runtime_harness)
        dashboard_evidence = _capture_dashboard_surfaces(
            base_url=args.status_url,
            sprint_id=sid,
            output_dir=uat_dir / "dashboard",
        )
        final.update({
            "schema": SCHEMA,
            "phase": "dashboard-to-final",
            "status": "passed",
            "request_id": args.request_id,
            "dashboard_evidence": dashboard_evidence,
        })
        final_path = uat_dir / "final.json"
        _write_json(final_path, final)
        manifest["status"] = "passed"
        manifest["final_path"] = str(final_path)
        _write_json(manifest_path, manifest)
        return {"ok": True, "status": "passed", "sprint_id": sid, "final": str(final_path)}
    finally:
        lock.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fixed research shipped-entrypoint local UAT")
    sub = parser.add_subparsers(dest="phase", required=True)
    def add_start_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--evidence-root", required=True)
        target.add_argument("--source-pack", required=True)
        target.add_argument("--source-authority-root", required=True)
        target.add_argument("--request-file", required=True)
        target.add_argument("--workspace-root", required=True)
        target.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
        target.add_argument(
            "--acquisition-mode",
            choices=("source_pack", "live_search", "hybrid"),
            default="source_pack",
            help="hybrid/live_search turn on live public bibliographic retrieval under the no-key policy",
        )
        target.add_argument("--timeout-seconds", type=int, default=7200)
        target.add_argument("--poll-seconds", type=float, default=2.0)
        target.add_argument("--preflight-only", action="store_true")

    start = sub.add_parser("start-to-approval")
    add_start_arguments(start)
    one_shot = sub.add_parser("start-to-final")
    add_start_arguments(one_shot)
    one_shot.add_argument("--policy-actor", required=True)
    one_shot.add_argument("--policy-statement", required=True)
    resume = sub.add_parser("resume-to-final")
    resume.add_argument("--evidence-root", required=True)
    resume.add_argument("--actor", required=True)
    resume.add_argument("--statement", required=True)
    resume.add_argument("--plan-sha256", required=True)
    resume.add_argument("--scope-json", required=True)
    resume.add_argument("--capability", action="append", required=True)
    resume.add_argument("--timeout-seconds", type=int, default=3600)
    resume.add_argument("--poll-seconds", type=float, default=2.0)
    dashboard = sub.add_parser("dashboard-to-final")
    dashboard.add_argument("--evidence-root", required=True)
    dashboard.add_argument("--request-id", required=True)
    dashboard.add_argument("--runtime-harness", default=str(SOURCE_HARNESS))
    dashboard.add_argument("--workspace-root", required=True)
    dashboard.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    dashboard.add_argument("--status-url", default="http://127.0.0.1:8765")
    dashboard.add_argument("--policy-actor", required=True)
    dashboard.add_argument("--policy-statement", required=True)
    dashboard.add_argument("--timeout-seconds", type=int, default=7200)
    dashboard.add_argument("--poll-seconds", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.phase in {"start-to-approval", "start-to-final"}:
            payload = _start(args)
        elif args.phase == "dashboard-to-final":
            payload = _drive_dashboard(args)
        else:
            payload = _resume(args)
    except (UATError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "phase": args.phase, "error_type": type(exc).__name__, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
