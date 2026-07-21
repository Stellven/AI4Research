#!/usr/bin/env python3
"""Prove Solar-Harness capabilities are activated, not just installed.

This runner focuses on "can it actually be used?" rather than green status:

1. Default dispatch text contains intent/capability context.
2. DAG graph-node dispatch receives the same context.
3. Real runtimes produce observable artifacts.
4. Negative controls do not falsely select unrelated capabilities.

Boundary: no benchmark can prove an LLM's private reasoning.  We prove the
worker-visible prompt/context, runtime calls, and produced artifacts.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import importlib.util
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
REPORTS = HARNESS / "reports"
SOLAR_BIN = HARNESS / "solar-harness.sh"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(cmd: list[str], evidence_dir: Path, name: str, timeout: int = 180) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        result = {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "duration_s": round(time.time() - started, 3),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": cmd,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "exit_code": 99,
            "duration_s": round(time.time() - started, 3),
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "cmd": cmd,
        }
    stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    write_json(evidence_dir / "commands" / f"{stem}.json", {k: v for k, v in result.items() if k not in {"stdout", "stderr"}})
    write_text(evidence_dir / "commands" / f"{stem}.stdout.txt", result["stdout"][-80000:])
    write_text(evidence_dir / "commands" / f"{stem}.stderr.txt", result["stderr"][-80000:])
    return result


def proof_dispatch_activation(evidence_dir: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="solar-activation-dispatch-"))
    try:
        dispatch = tmp / "dispatch.md"
        dispatch.write_text(
            "\n".join([
                "# Activation Proof Dispatch",
                "",
                "赶紧继续修复：用系统化调试排查 browser-use localhost screenshot 问题，",
                "用 MarkItDown 处理 PDF，用 Ruflo swarm 做多代理拆解，并把证据写入 handoff。",
            ]),
            encoding="utf-8",
        )
        result = run([sys.executable, str(HARNESS / "lib" / "solar_skills.py"), "inject", str(dispatch)], evidence_dir, "dispatch_inject", timeout=60)
        text = dispatch.read_text(encoding="utf-8", errors="replace")
        write_text(evidence_dir / "dispatch" / "activation-dispatch.injected.md", text)
        sidecar = dispatch.with_name(dispatch.name + ".intent.json")
        sidecar_out = evidence_dir / "dispatch" / "activation-dispatch.injected.md.intent.json"
        if sidecar.exists():
            sidecar_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sidecar, sidecar_out)
        required = [
            "<solar-intent-context>",
            "<solar-capability-context>",
            "execute confidence",
            "Superpowers",
            "Browser-use MCP",
            "MarkItDown",
            "Ruflo",
        ]
        missing = [item for item in required if item not in text]
        return {
            "name": "default dispatch activates intent/capability context",
            "status": "ok" if result["ok"] and not missing else "error",
            "passed": result["ok"] and not missing,
            "evidence": {
                "injected_file": str(evidence_dir / "dispatch" / "activation-dispatch.injected.md"),
                "intent_telemetry_file": str(sidecar_out) if sidecar.exists() else "",
                "missing": missing,
            },
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def proof_graph_dispatch_activation(evidence_dir: Path) -> dict[str, Any]:
    result = run(["bash", str(HARNESS / "tests" / "control_plane" / "test-graph-node-dispatcher.sh")], evidence_dir, "graph_node_dispatcher", timeout=180)
    stdout = result["stdout"]
    required = [
        "dispatch text has capability block",
        "dispatch text selected gstack",
        "dispatch text selected MarkItDown",
        "eval text has capability block",
        "S3 downstream released",
    ]
    missing = [item for item in required if item not in stdout]
    return {
        "name": "DAG graph-node dispatch activates context and gates downstream",
        "status": "ok" if result["ok"] and not missing else "error",
        "passed": result["ok"] and not missing,
        "evidence": {
            "stdout": str(evidence_dir / "commands" / "graph_node_dispatcher.stdout.txt"),
            "missing": missing,
        },
    }


def proof_use_effect_telemetry(evidence_dir: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="solar-activation-effect-"))
    try:
        dispatch = tmp / "dispatch.md"
        dispatch.write_text(
            "# Effect Proof\n\nUse MarkItDown to convert PDF evidence and write handoff/eval proof.\n",
            encoding="utf-8",
        )
        inject = run([sys.executable, str(HARNESS / "lib" / "solar_skills.py"), "inject", str(dispatch)], evidence_dir, "effect_inject", timeout=60)
        handoff = tmp / "handoff.md"
        handoff.write_text(
            "# Handoff\n\n## Capability / KB Usage Evidence\n\n- Used MarkItDown document.convert evidence for PDF markdown extraction.\n",
            encoding="utf-8",
        )
        eval_json = tmp / "eval.json"
        eval_json.write_text('{"verdict":"PASS","summary":"MarkItDown evidence checked"}\n', encoding="utf-8")
        effect = run(
            [
                sys.executable,
                str(HARNESS / "lib" / "solar_skills.py"),
                "effect-scan",
                str(dispatch),
                "--handoff",
                str(handoff),
                "--eval-json",
                str(eval_json),
                "--json",
            ],
            evidence_dir,
            "effect_scan",
            timeout=60,
        )
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(effect["stdout"])
        except Exception:
            parsed = {"parse_error": effect["stdout"][-1000:]}
        sidecar = dispatch.with_name(dispatch.name + ".intent.json")
        sidecar_out = evidence_dir / "dispatch" / "effect-dispatch.intent.json"
        if sidecar.exists():
            sidecar_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sidecar, sidecar_out)
        status = ((parsed.get("effect") or {}).get("status") or "")
        return {
            "name": "use-to-effect telemetry updates intent sidecar from handoff/eval",
            "status": "ok" if inject["ok"] and effect["ok"] and status == "eval_passed_with_worker_evidence" else "error",
            "passed": bool(inject["ok"] and effect["ok"] and status == "eval_passed_with_worker_evidence"),
            "evidence": {
                "intent_telemetry_file": str(sidecar_out) if sidecar.exists() else "",
                "effect_status": status,
                "used_providers": (parsed.get("effect") or {}).get("used_providers", []),
            },
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def proof_runtime_effect(evidence_dir: Path) -> dict[str, Any]:
    result = run(["bash", str(SOLAR_BIN), "integrations", "heavy-proof", "--json"], evidence_dir, "heavy_proof_runtime", timeout=900)
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(result["stdout"])
    except Exception:
        parsed = {"parse_error": result["stdout"][-1000:]}
    write_json(evidence_dir / "runtime" / "heavy-proof.json", parsed)
    expected = {
        "MemPalace real semantic search": "hits=3",
        "Apple Notes mock source to wiki dispatch": "exported=1",
        "Accepted sprint artifact to wiki dispatch": "dispatch_exists=True",
        "Browser-use real browser navigation": "marker_found=True",
    }
    seen = {item.get("name"): str(item.get("evidence", {}).get("reason", "")) for item in parsed.get("results", [])}
    missing = [name for name, marker in expected.items() if marker not in seen.get(name, "")]
    return {
        "name": "real runtimes produce observable artifacts",
        "status": "ok" if result["ok"] and parsed.get("ok") and not missing else "error",
        "passed": bool(result["ok"] and parsed.get("ok") and not missing),
        "evidence": {
            "heavy_proof_json": str(evidence_dir / "runtime" / "heavy-proof.json"),
            "heavy_proof_evidence_dir": parsed.get("evidence_dir", ""),
            "missing": missing,
            "seen": seen,
        },
    }


def proof_ruflo_runtime_effect(evidence_dir: Path) -> dict[str, Any]:
    result = run(["bash", str(SOLAR_BIN), "integrations", "ruflo-runtime-smoke", "--json"], evidence_dir, "ruflo_runtime_smoke", timeout=120)
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(result["stdout"])
    except Exception:
        parsed = {"parse_error": result["stdout"][-1000:]}
    write_json(evidence_dir / "runtime" / "ruflo-runtime-smoke.json", parsed)
    commands = {item.get("name"): item for item in parsed.get("commands", []) if isinstance(item, dict)}
    missing = [name for name in ("help", "version", "mcp_help") if not commands.get(name, {}).get("ok")]
    not_sandboxed = [
        name for name in ("help", "version", "mcp_help")
        if commands.get(name, {}).get("executor") != "sandbox"
        or commands.get(name, {}).get("execution_mode") != "argv"
        or not commands.get(name, {}).get("evidence_file")
    ]
    passed = bool(result["ok"] and parsed.get("ok") and not missing and not not_sandboxed)
    return {
        "name": "Ruflo sandbox runtime exposes CLI and MCP command surface",
        "status": "ok" if passed else "error",
        "passed": passed,
        "evidence": {
            "runtime_smoke_json": str(evidence_dir / "runtime" / "ruflo-runtime-smoke.json"),
            "backend": parsed.get("backend", ""),
            "runtime_package": parsed.get("runtime_package", ""),
            "missing": missing,
            "not_sandboxed": not_sandboxed,
            "sandboxed_commands": [
                name for name in ("help", "version", "mcp_help")
                if commands.get(name, {}).get("executor") == "sandbox"
            ],
        },
    }


def proof_model_call_runtime_projection(evidence_dir: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="solar-activation-model-call-"))
    session_id = f"activation-model-call-{int(time.time())}"
    dispatch_id = f"activation-model-call-{os.getpid()}"
    pane = "solar-harness:0.2"
    try:
        instruction = tmp / "instruction.md"
        instruction.write_text(
            "# Model Call Activation Proof\n\n"
            "Use Solar knowledge context and write an observable handoff artifact.\n",
            encoding="utf-8",
        )
        request = run(
            [
                sys.executable,
                str(HARNESS / "lib" / "model_call_runtime.py"),
                "request",
                "--session-id",
                session_id,
                "--pane",
                pane,
                "--dispatch-id",
                dispatch_id,
                "--instruction-file",
                str(instruction),
                "--status",
                "queued",
                "--json",
            ],
            evidence_dir,
            "model_call_request",
            timeout=60,
        )
        succeeded = run(
            [
                sys.executable,
                str(HARNESS / "lib" / "model_call_runtime.py"),
                "succeeded",
                "--session-id",
                session_id,
                "--pane",
                pane,
                "--dispatch-id",
                dispatch_id,
                "--instruction-file",
                str(instruction),
                "--status",
                "accepted",
                "--json",
            ],
            evidence_dir,
            "model_call_succeeded",
            timeout=60,
        )

        events_path = HARNESS / "sessions" / session_id / "events.jsonl"
        events = []
        if events_path.exists():
            for raw in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    events.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass

        status_module_path = HARNESS / "lib" / "symphony" / "status-server.py"
        projection: dict[str, Any] = {}
        if status_module_path.exists():
            spec = importlib.util.spec_from_file_location("solar_status_server_activation", status_module_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                projection = mod._latest_model_call_for_pane(pane, "")  # type: ignore[attr-defined]

        write_json(evidence_dir / "runtime" / "model-call-runtime.json", {
            "session_id": session_id,
            "dispatch_id": dispatch_id,
            "pane": pane,
            "events_path": str(events_path),
            "events": events,
            "status_projection": projection,
        })
        event_types = {ev.get("type") for ev in events}
        missing = [t for t in ["model_call_requested", "model_call_succeeded"] if t not in event_types]
        projected = projection.get("dispatch_id") == dispatch_id and projection.get("status") == "ok"
        return {
            "name": "model-call events project into status UI evidence",
            "status": "ok" if request["ok"] and succeeded["ok"] and not missing and projected else "error",
            "passed": bool(request["ok"] and succeeded["ok"] and not missing and projected),
            "evidence": {
                "runtime_json": str(evidence_dir / "runtime" / "model-call-runtime.json"),
                "events_path": str(events_path),
                "missing": missing,
                "projected_status": projection.get("status", ""),
                "projected_dispatch": projection.get("dispatch_id", ""),
            },
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def proof_status_ui_capability_health_projection(evidence_dir: Path) -> dict[str, Any]:
    status_module_path = HARNESS / "lib" / "symphony" / "status-server.py"
    payload: dict[str, Any] = {}
    if status_module_path.exists():
        try:
            spec = importlib.util.spec_from_file_location("solar_status_server_capability_health", status_module_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                payload = mod._status_payload(limit=5)  # type: ignore[attr-defined]
        except Exception as exc:
            payload = {"error": f"{type(exc).__name__}: {exc}"}
    write_json(evidence_dir / "runtime" / "status-ui-capability-health.json", payload)

    health = payload.get("capability_health") if isinstance(payload, dict) else {}
    checks = health.get("checks") if isinstance(health, dict) else {}
    required_checks = ["model", "knowledge", "mirage_qmd", "intent", "skills", "sandbox"]
    missing_checks = [name for name in required_checks if name not in checks]
    bad_checks = [
        name for name, item in (checks or {}).items()
        if name in required_checks and item.get("status") not in {"ok", "warn"}
    ]

    pane_missing = []
    for screen_name in ("main_screen", "lab_screen"):
        panes = ((payload.get(screen_name) or {}).get("panes") or []) if isinstance(payload, dict) else []
        for pane in panes:
            pane_health = pane.get("capability_health") or {}
            pane_checks = pane_health.get("checks") or {}
            missing = [name for name in required_checks if name not in pane_checks]
            if missing:
                pane_missing.append({"pane": pane.get("target"), "missing": missing})

    passed = bool(health) and not missing_checks and not bad_checks and not pane_missing
    return {
        "name": "status UI projects model/KB/Mirage/intent/skills/sandbox health per pane",
        "status": "ok" if passed else "error",
        "passed": passed,
        "evidence": {
            "status_payload": str(evidence_dir / "runtime" / "status-ui-capability-health.json"),
            "missing_checks": missing_checks,
            "bad_checks": bad_checks,
            "pane_missing": pane_missing[:8],
            "overall_status": health.get("status") if isinstance(health, dict) else "",
        },
    }


def proof_disposable_sandbox_runtime_lifecycle(evidence_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(HARNESS / "lib"))
    payload: dict[str, Any] = {}
    try:
        from hands_runtime import SandboxHand
        from runtime_interfaces import ResultStatus

        os.environ["SOLAR_SANDBOX_VISIBLE_TEST"] = "visible"
        os.environ["SOLAR_SANDBOX_SECRET_TEST"] = "sandbox-secret-value-12345"
        hand = SandboxHand()
        ref = hand.provision(capabilities=["shell", "evidence"])
        guard_root = Path(tempfile.mkdtemp(prefix="solar-activation-sandbox-guard-"))
        result = hand.execute(
            ref,
            "activation-sandbox",
            {
                "argv": ["/bin/sh", "-c", 'printf "%s/%s" "$SOLAR_SANDBOX_VISIBLE_TEST" "$TOKEN" > result.txt; cat result.txt'],
                "env_allow": ["SOLAR_SANDBOX_VISIBLE_TEST"],
                "secret_refs": {"TOKEN": "env:SOLAR_SANDBOX_SECRET_TEST"},
                "write_guard_roots": [str(guard_root)],
                "session_id": f"activation-sandbox-{os.getpid()}",
                "sprint_id": f"activation-sandbox-{os.getpid()}",
                "activity_id": "activation-sandbox-lifecycle",
            },
            idempotency_key=f"activation-sandbox-{os.getpid()}",
            timeout_seconds=15,
        )
        evidence_file = Path(result.metadata.get("evidence_file", ""))
        evidence = json.loads(evidence_file.read_text(encoding="utf-8")) if evidence_file.exists() else {}
        workspace_manifest = evidence.get("workspace_manifest") or {}
        write_guard = evidence.get("write_guard") or {}
        write_guard_violations = write_guard.get("violations") or []
        disposed = hand.dispose(ref)
        shutil.rmtree(guard_root, ignore_errors=True)
        workspace_removed = bool(disposed.output.get("workspace_removed"))
        secret_redacted = (
            result.output == "visible/[REDACTED]"
            and "sandbox-secret-value" not in json.dumps(evidence, ensure_ascii=False)
        )
        payload = {
            "hand_id": ref.hand_id,
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "output": result.output,
            "evidence_file": str(evidence_file),
            "workspace_file_count": workspace_manifest.get("file_count"),
            "workspace_removed": workspace_removed,
            "execution_mode": evidence.get("execution_mode", ""),
            "write_guard_enabled": bool(write_guard.get("enabled")),
            "write_guard_violations": len(write_guard_violations),
            "env_allow": evidence.get("env_allow", []),
            "secret_names": evidence.get("secret_names", []),
            "secret_redacted": secret_redacted,
            "boundary": "local process sandbox, not VM/container isolation",
        }
        passed = (
            result.status == ResultStatus.OK
            and evidence_file.exists()
            and int(workspace_manifest.get("file_count") or 0) >= 1
            and workspace_removed
            and evidence.get("execution_mode") == "argv"
            and bool(write_guard.get("enabled"))
            and not write_guard_violations
            and secret_redacted
        )
    except Exception as exc:
        passed = False
        payload = {"error": f"{type(exc).__name__}: {exc}"}

    write_json(evidence_dir / "runtime" / "disposable-sandbox-lifecycle.json", payload)
    return {
        "name": "disposable sandbox runtime uses argv/write-guard and disposes workspace",
        "status": "ok" if passed else "error",
        "passed": passed,
        "evidence": {
            "runtime_json": str(evidence_dir / "runtime" / "disposable-sandbox-lifecycle.json"),
            "evidence_file": payload.get("evidence_file", ""),
            "workspace_removed": payload.get("workspace_removed", False),
            "execution_mode": payload.get("execution_mode", ""),
            "write_guard_enabled": payload.get("write_guard_enabled", False),
            "write_guard_violations": payload.get("write_guard_violations", 0),
            "secret_redacted": payload.get("secret_redacted", False),
            "boundary": payload.get("boundary", ""),
        },
    }


def proof_sandbox_write_guard_blocks_host_write(evidence_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(HARNESS / "lib"))
    payload: dict[str, Any] = {}
    guard_root = Path(tempfile.mkdtemp(prefix="solar-activation-write-guard-"))
    try:
        from hands_runtime import SandboxHand
        from runtime_interfaces import ResultStatus

        hand = SandboxHand()
        ref = hand.provision(capabilities=["shell", "evidence"])
        leak_path = guard_root / "host-leak.txt"
        result = hand.execute(
            ref,
            "activation-sandbox-write-guard",
            {
                "argv": ["/bin/sh", "-c", f"printf leaked > {str(leak_path)!r}"],
                "write_guard_roots": [str(guard_root)],
                "session_id": f"activation-write-guard-{os.getpid()}",
                "sprint_id": f"activation-write-guard-{os.getpid()}",
                "activity_id": "activation-sandbox-write-guard",
            },
            idempotency_key=f"activation-write-guard-{os.getpid()}",
            timeout_seconds=15,
        )
        evidence_file = Path(result.metadata.get("evidence_file", ""))
        evidence = json.loads(evidence_file.read_text(encoding="utf-8")) if evidence_file.exists() else {}
        write_guard = evidence.get("write_guard") or {}
        violations = write_guard.get("violations") or []
        disposed = hand.dispose(ref)
        payload = {
            "hand_id": ref.hand_id,
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "error": result.error,
            "evidence_file": str(evidence_file),
            "execution_mode": evidence.get("execution_mode", ""),
            "write_guard_enabled": bool(write_guard.get("enabled")),
            "write_guard_violations": violations,
            "workspace_removed": bool(disposed.output.get("workspace_removed")),
            "leak_path": str(leak_path),
            "boundary": "local process sandbox write guard detects host writes; it is not VM/container isolation",
        }
        passed = (
            result.status == ResultStatus.ERROR
            and "write guard violation" in (result.error or "")
            and evidence.get("execution_mode") == "argv"
            and bool(write_guard.get("enabled"))
            and any(item.get("type") == "created" and str(item.get("path", "")).endswith("host-leak.txt") for item in violations)
            and bool(disposed.output.get("workspace_removed"))
        )
    except Exception as exc:
        passed = False
        payload = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(guard_root, ignore_errors=True)

    write_json(evidence_dir / "runtime" / "sandbox-write-guard-negative.json", payload)
    return {
        "name": "sandbox write guard detects host writes outside workspace",
        "status": "ok" if passed else "error",
        "passed": passed,
        "evidence": {
            "runtime_json": str(evidence_dir / "runtime" / "sandbox-write-guard-negative.json"),
            "evidence_file": payload.get("evidence_file", ""),
            "execution_mode": payload.get("execution_mode", ""),
            "write_guard_enabled": payload.get("write_guard_enabled", False),
            "violation_count": len(payload.get("write_guard_violations") or []),
            "workspace_removed": payload.get("workspace_removed", False),
            "boundary": payload.get("boundary", ""),
        },
    }


def proof_mirage_exec_routes_through_sandbox(evidence_dir: Path) -> dict[str, Any]:
    marker = f"activation_mirage_sandbox_{os.getpid()}"
    logical_path = f"/raw/_{marker}.txt"
    physical_path = HOME / "Knowledge" / "_raw" / f"_{marker}.txt"
    payload: dict[str, Any] = {}
    try:
        write_result = run(
            [str(SOLAR_BIN), "mirage", "exec", "--json", "--", f"echo {marker} > {logical_path}"],
            evidence_dir,
            "mirage_exec_sandbox_write",
            timeout=60,
        )
        read_result = run(
            [str(SOLAR_BIN), "mirage", "exec", "--json", "--", f"cat {logical_path}"],
            evidence_dir,
            "mirage_exec_sandbox_read",
            timeout=60,
        )
        write_payload = json.loads(write_result.get("stdout") or "{}")
        read_payload = json.loads(read_result.get("stdout") or "{}")
        evidence_file = Path(write_payload.get("evidence_file", ""))
        evidence = json.loads(evidence_file.read_text(encoding="utf-8")) if evidence_file.exists() else {}
        payload = {
            "write": write_payload,
            "read": read_payload,
            "evidence_file": str(evidence_file),
            "evidence_execution_mode": evidence.get("execution_mode", ""),
            "evidence_write_guard_enabled": bool((evidence.get("write_guard") or {}).get("enabled")),
            "evidence_write_guard_violations": len((evidence.get("write_guard") or {}).get("violations") or []),
        }
        passed = (
            write_result.get("ok")
            and read_result.get("ok")
            and write_payload.get("exit_code") == 0
            and write_payload.get("executor") == "sandbox"
            and write_payload.get("execution_mode") == "argv"
            and bool((write_payload.get("write_guard") or {}).get("enabled"))
            and not ((write_payload.get("write_guard") or {}).get("violations") or [])
            and evidence_file.exists()
            and read_payload.get("stdout") == marker
        )
    except Exception as exc:
        passed = False
        payload = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            physical_path.unlink(missing_ok=True)
        except OSError:
            pass

    write_json(evidence_dir / "runtime" / "mirage-exec-sandbox-route.json", payload)
    return {
        "name": "Mirage exec routes default data access commands through SandboxHand",
        "status": "ok" if passed else "error",
        "passed": bool(passed),
        "evidence": {
            "runtime_json": str(evidence_dir / "runtime" / "mirage-exec-sandbox-route.json"),
            "evidence_file": payload.get("evidence_file", ""),
            "executor": (payload.get("write") or {}).get("executor", ""),
            "execution_mode": (payload.get("write") or {}).get("execution_mode", ""),
            "write_guard_enabled": bool(((payload.get("write") or {}).get("write_guard") or {}).get("enabled")),
            "read_stdout": (payload.get("read") or {}).get("stdout", ""),
        },
    }


def _load_module_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def proof_qmd_search_routes_through_sandbox(evidence_dir: Path) -> dict[str, Any]:
    """Prove `mirage_search.search_qmd` lands inside SandboxHand (argv + evidence)."""
    payload: dict[str, Any] = {}
    passed = False
    try:
        mirage = _load_module_by_path("mirage_search", HARNESS / "lib" / "mirage_search.py")
        # Ensure sys.path is set so internal qmd_resolver import works.
        lib_dir = str(HARNESS / "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        mirage.search_qmd("activation-proof sandbox routing", max_hits=1)
        route = dict(getattr(mirage, "LAST_QMD_ROUTE", {}) or {})
        evidence_file = Path(route.get("evidence_file", "") or "")
        evidence = (
            json.loads(evidence_file.read_text(encoding="utf-8")) if evidence_file.exists() else {}
        )
        payload = {
            "executor": route.get("executor", ""),
            "execution_mode": route.get("execution_mode", ""),
            "evidence_file": str(evidence_file),
            "evidence_command_name": evidence.get("command_name", ""),
            "evidence_execution_mode": evidence.get("execution_mode", ""),
            "exit_code": route.get("exit_code"),
            "sandbox_status": route.get("sandbox_status", ""),
            "fallback_reason": route.get("fallback_reason", ""),
            "argv_first": (route.get("argv") or [""])[0],
        }
        # Honest proof: executor must be sandbox; mode argv; evidence file present.
        # Exit code from qmd may be non-zero (sandbox HOME isolation hides host's
        # collection config) — that is OK as long as routing is verifiable.
        passed = (
            route.get("executor") == "sandbox"
            and route.get("execution_mode") == "argv"
            and evidence_file.exists()
            and evidence.get("execution_mode") == "argv"
            and evidence.get("command_name") == "qmd-search"
        )
    except Exception as exc:
        payload = {"error": f"{type(exc).__name__}: {exc}"}
        passed = False

    write_json(evidence_dir / "runtime" / "qmd-search-sandbox-route.json", payload)
    return {
        "name": "mirage_search.search_qmd routes through SandboxHand",
        "status": "ok" if passed else "error",
        "passed": bool(passed),
        "evidence": {
            "runtime_json": str(evidence_dir / "runtime" / "qmd-search-sandbox-route.json"),
            "evidence_file": payload.get("evidence_file", ""),
            "executor": payload.get("executor", ""),
            "execution_mode": payload.get("execution_mode", ""),
            "evidence_command_name": payload.get("evidence_command_name", ""),
            "fallback_reason": payload.get("fallback_reason", ""),
        },
    }


def proof_pdftotext_extract_routes_through_sandbox(evidence_dir: Path) -> dict[str, Any]:
    """Prove `wiki-upload-backfill._run_extract_sandboxed` lands inside SandboxHand.

    Honest proof: even when the underlying CLI fails (missing PDF, missing
    binary) the routing must still emit executor=sandbox + argv mode + evidence
    file. We probe via a `cat` argv that is guaranteed to succeed inside the
    sandbox so we can also assert stdout pass-through.
    """
    payload: dict[str, Any] = {}
    passed = False
    fixture: Path | None = None
    try:
        backfill = _load_module_by_path(
            "wiki_upload_backfill_proof",
            HARNESS / "lib" / "wiki-upload-backfill.py",
        )
        fixture = Path(tempfile.mkstemp(prefix="activation-extract-", suffix=".txt")[1])
        marker = f"sandbox-extract-marker-{os.getpid()}"
        fixture.write_text(marker, encoding="utf-8")

        route = backfill._run_extract_sandboxed(
            "cat", ["cat", str(fixture)], timeout=15
        )
        evidence_file = Path(route.get("evidence_file", "") or "")
        evidence = (
            json.loads(evidence_file.read_text(encoding="utf-8")) if evidence_file.exists() else {}
        )
        payload = {
            "executor": route.get("executor", ""),
            "execution_mode": route.get("execution_mode", ""),
            "evidence_file": str(evidence_file),
            "evidence_command_name": evidence.get("command_name", ""),
            "evidence_execution_mode": evidence.get("execution_mode", ""),
            "evidence_secret_names": evidence.get("secret_names", []),
            "exit_code": route.get("exit_code"),
            "ok": route.get("ok"),
            "stdout_marker_match": (route.get("stdout") or "").strip() == marker,
            "argv_first": (route.get("argv") or [""])[0],
        }
        passed = (
            route.get("executor") == "sandbox"
            and route.get("execution_mode") == "argv"
            and bool(route.get("ok"))
            and evidence_file.exists()
            and evidence.get("execution_mode") == "argv"
            and (route.get("stdout") or "").strip() == marker
            and not evidence.get("secret_names")  # no inline credentials
        )
    except Exception as exc:
        payload = {"error": f"{type(exc).__name__}: {exc}"}
        passed = False
    finally:
        if fixture is not None:
            try:
                fixture.unlink(missing_ok=True)
            except OSError:
                pass

    write_json(evidence_dir / "runtime" / "pdftotext-extract-sandbox-route.json", payload)
    return {
        "name": "wiki-upload-backfill extract routes through SandboxHand",
        "status": "ok" if passed else "error",
        "passed": bool(passed),
        "evidence": {
            "runtime_json": str(evidence_dir / "runtime" / "pdftotext-extract-sandbox-route.json"),
            "evidence_file": payload.get("evidence_file", ""),
            "executor": payload.get("executor", ""),
            "execution_mode": payload.get("execution_mode", ""),
            "evidence_command_name": payload.get("evidence_command_name", ""),
            "stdout_marker_match": payload.get("stdout_marker_match", False),
        },
    }


def proof_negative_control(evidence_dir: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="solar-activation-negative-"))
    try:
        dispatch = tmp / "negative.md"
        dispatch.write_text("# Negative\n\nCompute 2 + 2 only.\n", encoding="utf-8")
        result = run([sys.executable, str(HARNESS / "lib" / "solar_skills.py"), "inject", str(dispatch)], evidence_dir, "negative_inject", timeout=60)
        text = dispatch.read_text(encoding="utf-8", errors="replace")
        write_text(evidence_dir / "negative" / "negative.injected.md", text)
        sidecar = dispatch.with_name(dispatch.name + ".intent.json")
        sidecar_out = evidence_dir / "negative" / "negative.injected.md.intent.json"
        if sidecar.exists():
            sidecar_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sidecar, sidecar_out)
        false_hits = [name for name in ["Browser-use MCP", "MarkItDown", "Ruflo", "Empirical Research", "gstack"] if name in text]
        return {
            "name": "negative control does not activate unrelated capabilities",
            "status": "ok" if result["ok"] and not false_hits else "error",
            "passed": result["ok"] and not false_hits,
            "evidence": {
                "injected_file": str(evidence_dir / "negative" / "negative.injected.md"),
                "intent_telemetry_file": str(sidecar_out) if sidecar.exists() else "",
                "false_hits": false_hits,
            },
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_markdown(payload: dict[str, Any]) -> str:
    rows = []
    for idx, item in enumerate(payload["proofs"], 1):
        rows.append(f"│ {idx:<2} │ {item['name'][:42]:<42} │ {item['status']:<6} │ {str(item['evidence'])[:52]:<52} │")
    return "\n".join([
        f"# Solar Capability Activation Proof — {payload['generated_at']}",
        "",
        f"- Result: `{'PASS' if payload['ok'] else 'FAIL'}`",
        f"- Passed: `{payload['passed']}/{payload['total']}`",
        f"- Evidence: `{payload['evidence_dir']}`",
        "",
        "```text",
        "┌────┬────────────────────────────────────────────┬────────┬──────────────────────────────────────────────────────┐",
        "│ #  │ Proof                                      │ 状态   │ 证据                                                 │",
        "├────┼────────────────────────────────────────────┼────────┼──────────────────────────────────────────────────────┤",
        *rows,
        "└────┴────────────────────────────────────────────┴────────┴──────────────────────────────────────────────────────┘",
        "```",
        "",
        "## Boundary",
        "",
        "- 能证明：默认 prompt/dispatch 已带能力、真实 runtime 已执行、产物已生成、负例不误触发。",
        "- 不能证明：LLM 私有思考过程一定按某个 skill 思考；只能证明 worker 可见输入和可观察输出。",
        "",
    ])


def main() -> int:
    evidence_dir = REPORTS / "capability-activation-evidence" / "latest"
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    proofs = [
        proof_dispatch_activation(evidence_dir),
        proof_graph_dispatch_activation(evidence_dir),
        proof_use_effect_telemetry(evidence_dir),
        proof_runtime_effect(evidence_dir),
        proof_ruflo_runtime_effect(evidence_dir),
        proof_model_call_runtime_projection(evidence_dir),
        proof_disposable_sandbox_runtime_lifecycle(evidence_dir),
        proof_sandbox_write_guard_blocks_host_write(evidence_dir),
        proof_mirage_exec_routes_through_sandbox(evidence_dir),
        proof_qmd_search_routes_through_sandbox(evidence_dir),
        proof_pdftotext_extract_routes_through_sandbox(evidence_dir),
        proof_status_ui_capability_health_projection(evidence_dir),
        proof_negative_control(evidence_dir),
    ]
    passed = sum(1 for item in proofs if item["passed"])
    payload = {
        "ok": passed == len(proofs),
        "generated_at": now(),
        "passed": passed,
        "total": len(proofs),
        "evidence_dir": str(evidence_dir),
        "proofs": proofs,
    }
    write_json(REPORTS / "capability-activation-proof-latest.json", payload)
    write_text(REPORTS / "capability-activation-proof-latest.md", render_markdown(payload))
    write_json(evidence_dir / "activation-proof.json", payload)
    write_text(evidence_dir / "activation-proof.md", render_markdown(payload))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
