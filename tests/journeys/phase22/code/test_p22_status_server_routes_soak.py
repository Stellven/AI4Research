#!/usr/bin/env python3
"""P22-REPAIR-128: real status-server route matrix and bounded stability soak.

This is deliberately a production-process probe, not a handler unit test.  It launches
``harness/lib/symphony/status-server.py`` with an isolated HOME/HARNESS_DIR, a random loopback
port, and forced token enforcement.  The route matrix checks response structure and negative
boundaries.  The bounded soak then exercises representative read paths concurrently while
recording latency, errors, RSS, handles/file descriptors, and thread count.

This test does *not* claim long-running production stability or portable-wrapper coverage.
Those remain explicit P22-REPAIR-128 boundaries.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import datetime as dt
import json
import math
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_HARNESS = REPO_ROOT / "harness"
SERVER = REPO_HARNESS / "lib" / "symphony" / "status-server.py"
SID = "sprint-p22-route-soak"


def _request(
    port: int,
    path: str,
    *,
    token: str = "",
    method: str = "GET",
    payload: dict | None = None,
    timeout: float = 20.0,
) -> tuple[int, dict[str, str], bytes, float]:
    headers = {}
    if token:
        headers["X-Solar-Token"] = token
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            return response.status, {k.lower(): v for k, v in response.headers.items()}, data, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        data = exc.read()
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, data, time.perf_counter() - started


def _json(body: bytes) -> object:
    return json.loads(body.decode("utf-8"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_ready(root: Path, proc: subprocess.Popen, timeout: float = 30.0) -> tuple[int, int]:
    deadline = time.monotonic() + timeout
    port_file = root / "run" / "status-server.port"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"status server exited before readiness: rc={proc.returncode}")
        try:
            port = int(port_file.read_text(encoding="utf-8").strip())
            status, _, body, _ = _request(port, "/healthz", timeout=1.0)
            runtime_status, _, runtime_body, _ = _request(port, "/runtime-info", timeout=1.0)
            runtime = _json(runtime_body)
            pid_file = int((root / "run" / "status-server.pid").read_text(encoding="utf-8").strip())
            runtime_pid = int(runtime.get("pid")) if isinstance(runtime, dict) else 0
            if (
                status == 200
                and body == b"ok"
                and runtime_status == 200
                and runtime_pid > 0
                and runtime_pid == pid_file
                and Path(runtime.get("harness_dir", "")).resolve() == root.resolve()
            ):
                return port, runtime_pid
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise TimeoutError("status server did not become healthy")


def _process_metrics(pid: int) -> dict[str, int | None]:
    if os.name != "nt":
        proc_root = Path("/proc") / str(pid)
        try:
            statm = (proc_root / "statm").read_text().split()
            rss = int(statm[1]) * int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError):
            rss = None
        try:
            descriptors = len(list((proc_root / "fd").iterdir()))
        except OSError:
            descriptors = None
        try:
            threads = len(list((proc_root / "task").iterdir()))
        except OSError:
            threads = None
        return {"rss_bytes": rss, "handles_or_fds": descriptors, "threads": threads}

    # Native Windows sampling avoids launching PowerShell during the soak.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetProcessHandleCount.restype = ctypes.c_int
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    process = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
    if not process:
        return {"rss_bytes": None, "handles_or_fds": None, "threads": None}

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    rss = None
    if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        rss = int(counters.WorkingSetSize)
    handle_count = ctypes.c_ulong()
    handles = int(handle_count.value) if kernel32.GetProcessHandleCount(process, ctypes.byref(handle_count)) else None

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
    thread_count = None
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot != invalid_handle:
        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_ulong),
                ("cntUsage", ctypes.c_ulong),
                ("th32ThreadID", ctypes.c_ulong),
                ("th32OwnerProcessID", ctypes.c_ulong),
                ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", ctypes.c_ulong),
            ]

        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        count = 0
        ok = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while ok:
            if int(entry.th32OwnerProcessID) == pid:
                count += 1
            ok = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
        thread_count = count
        kernel32.CloseHandle(snapshot)
    kernel32.CloseHandle(process)
    return {"rss_bytes": rss, "handles_or_fds": handles, "threads": thread_count}


def _pid_active(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, OSError):
            return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    code = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return bool(ok and code.value == 259)  # STILL_ACTIVE


def _port_open(port: int) -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _terminate_pid_windows(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.TerminateProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x0001, False, pid)
    if not handle:
        return not _pid_active(pid)
    ok = bool(kernel32.TerminateProcess(handle, 0))
    kernel32.CloseHandle(handle)
    return ok


def _stop_server(proc: subprocess.Popen | None, server_pid: int, port: int, root: Path) -> dict:
    identity_verified_before_stop = False
    if port > 0 and server_pid > 0:
        try:
            status, _, body, _ = _request(port, "/runtime-info", timeout=1.0)
            runtime = _json(body)
            identity_verified_before_stop = (
                status == 200
                and isinstance(runtime, dict)
                and int(runtime.get("pid") or 0) == server_pid
                and Path(runtime.get("harness_dir", "")).resolve() == root.resolve()
            )
        except Exception:
            identity_verified_before_stop = False

    if os.name == "nt":
        if _pid_active(server_pid):
            _terminate_pid_windows(server_pid)
        # A venv launcher can be distinct from the interpreter recorded by the server.
        if proc is not None and proc.pid != server_pid and proc.poll() is None:
            proc.terminate()
        method = "TerminateProcess(actual_server_pid)"
    else:
        if proc is not None and proc.poll() is None:
            proc.terminate()
        method = "SIGTERM"

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and (_pid_active(server_pid) or _port_open(port)):
        time.sleep(0.05)
    if proc is not None:
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3.0)
    return {
        "launcher_pid": proc.pid if proc is not None else None,
        "actual_server_pid": server_pid or None,
        "actual_server_identity_verified_before_stop": identity_verified_before_stop,
        # On Windows the venv launcher can be a distinct parent of the interpreter that owns
        # the listening socket.  Terminating the verified server PID makes that launcher exit
        # non-zero, so label this as launcher evidence rather than a server failure signal.
        "launcher_exit_code": proc.returncode if proc is not None else None,
        "actual_server_pid_absent": not _pid_active(server_pid),
        "port_closed": not _port_open(port),
        "launcher_process_stopped": proc is not None and proc.poll() is not None,
        "termination_method": method,
        "runtime_files_remaining_before_sandbox_cleanup": sorted(
            path.name for path in (root / "run").glob("status-server.*")
        ),
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))]


def _route_matrix(port: int, token: str, root: Path) -> list[dict]:
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def call(path: str, **kwargs):
        return _request(port, path, **kwargs)

    status, headers, body, _ = call("/healthz")
    record("public health", status == 200 and body == b"ok" and headers.get("content-type", "").startswith("text/plain"), f"status={status}")

    status, _, body, _ = call("/runtime-info")
    runtime = _json(body)
    record(
        "runtime identity",
        status == 200 and isinstance(runtime, dict) and runtime.get("ok") is True and Path(runtime.get("harness_dir", "")).resolve() == root.resolve() and runtime.get("pid") is not None,
        f"status={status} pid={runtime.get('pid') if isinstance(runtime, dict) else None}",
    )

    status, headers, body, _ = call("/static/p0.css")
    record("static asset", status == 200 and len(body) > 100 and "css" in headers.get("content-type", ""), f"status={status} bytes={len(body)}")

    for label, supplied in (("missing", ""), ("wrong", "wrong-token")):
        status, _, body, _ = call("/status", token=supplied)
        payload = _json(body)
        record(f"auth {label} token rejected", status == 403 and isinstance(payload, dict) and payload.get("error") == "unauthorized", f"status={status}")

    status, _, body, _ = call("/status", token=token, method="HEAD")
    record("authorized HEAD", status == 200 and body == b"", f"status={status} bytes={len(body)}")
    status, _, _, _ = call("/status", method="HEAD")
    record("unauthorized HEAD", status == 403, f"status={status}")

    status, headers, body, _ = call("/", token=token)
    record("dashboard HTML", status == 200 and b"<!doctype html" in body.lower() and token.encode() in body and "html" in headers.get("content-type", ""), f"status={status} bytes={len(body)}")

    status_payload: object = {}
    status = 0
    status_deadline = time.monotonic() + 45.0
    while time.monotonic() < status_deadline:
        status, _, body, _ = call(f"/status?sprint_id={SID}", token=token, timeout=45.0)
        status_payload = _json(body)
        if isinstance(status_payload, dict) and status_payload.get("requested_sprint_id") == SID:
            break
        time.sleep(0.2)
    record(
        "scoped status structure",
        status == 200 and isinstance(status_payload, dict) and status_payload.get("requested_sprint_id") == SID and isinstance(status_payload.get("current_sprint"), dict) and isinstance(status_payload.get("recent_events"), list),
        f"status={status} projection={status_payload.get('status', 'ready') if isinstance(status_payload, dict) else 'invalid'}",
    )

    status, _, body, _ = call("/settings", token=token)
    settings = _json(body)
    record("settings read structure", status == 200 and isinstance(settings, dict) and settings.get("ok") is True and settings.get("write_supported") is True and isinstance(settings.get("runtime"), dict), f"status={status}")
    status, _, body, _ = call("/settings", token=token, method="POST", payload={"runtime": "codex"})
    settings_write = _json(body)
    config_file = root / "config" / "solar-user-config.json"
    persisted = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    record("settings write persists", status == 200 and isinstance(settings_write, dict) and settings_write.get("ok") is True and persisted.get("runtime") == "codex", f"status={status} written_keys={settings_write.get('written_keys') if isinstance(settings_write, dict) else None}")

    status, _, body, _ = call(f"/events?sprint_id={SID}&limit=5", token=token)
    events = _json(body)
    record("scoped events JSON", status == 200 and isinstance(events, list) and len(events) == 1 and events[0].get("marker") == "P22_ROUTE_EVENT" and events[0].get("_event_scope") == "requested", f"status={status} count={len(events) if isinstance(events, list) else -1}")

    # SSE is a production streaming response. Read only the first event and close the connection;
    # the server handles the expected client disconnect without leaking a request thread.
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/events?sprint_id={SID}&stream=1&limit=5",
        headers={"X-Solar-Token": token, "Accept": "text/event-stream"},
    )
    with urllib.request.urlopen(request, timeout=8.0) as response:
        sse_lines = []
        for _ in range(8):
            line = response.readline().decode("utf-8", "replace")
            sse_lines.append(line)
            if line == "\n" and any(item.startswith("data:") for item in sse_lines):
                break
        sse_type = response.headers.get("Content-Type", "")
    sse_text = "".join(sse_lines)
    record("events SSE", "text/event-stream" in sse_type and "event: solar-event" in sse_text and "P22_ROUTE_EVENT" in sse_text, f"content_type={sse_type} lines={len(sse_lines)}")

    for label, path in (
        ("orchestration dashboard", f"/orchestration/dashboard?sprint_id={SID}"),
        ("orchestration projection", f"/orchestration/projection?sprint_id={SID}&mode=fast"),
    ):
        status, _, body, _ = call(path, token=token)
        payload = _json(body)
        record(label, status == 200 and isinstance(payload, dict) and payload.get("ok") is True and isinstance(payload.get("data"), dict) and bool(payload.get("schema_version")), f"status={status} degraded={len(payload.get('degraded_sources', [])) if isinstance(payload, dict) else -1}")

    status, _, body, _ = call(f"/sprints/{SID}/deliverables", token=token)
    artifacts = _json(body)
    items = artifacts.get("items", []) if isinstance(artifacts, dict) else []
    report_item = next((item for item in items if item.get("name") == "smoke-report.md"), None)
    record("artifact inventory", status == 200 and artifacts.get("ok") is True and report_item is not None and report_item.get("size", 0) > 0, f"status={status} items={len(items)}")
    view_path = "/sprints/{}/deliverables?path={}".format(SID, urllib.parse.quote(report_item.get("rel_path", ""), safe="")) if report_item else ""
    status, headers, body, _ = call(view_path, token=token) if view_path else (0, {}, b"", 0.0)
    record("artifact content", status == 200 and b"P22 route matrix artifact" in body and "markdown" in headers.get("content-type", ""), f"status={status} bytes={len(body)}")

    bad_sid = urllib.parse.quote("../escape", safe="")
    for label, path in (
        ("invalid sprint fails closed", f"/status?sprint_id={bad_sid}"),
        ("invalid orchestration fails closed", f"/orchestration/projection?sprint_id={bad_sid}"),
    ):
        status, _, body, _ = call(path, token=token)
        payload = _json(body)
        record(label, status == 400 and isinstance(payload, dict) and payload.get("error") == "invalid_sprint_id", f"status={status}")

    status, _, body, _ = call(f"/sprints/{SID}/deliverables?path={urllib.parse.quote('../../outside.txt', safe='')}", token=token)
    payload = _json(body)
    record("artifact traversal rejected", status == 404 and isinstance(payload, dict) and "not allowed" in payload.get("error", ""), f"status={status}")
    status, _, body, _ = call("/route-that-does-not-exist", token=token)
    payload = _json(body)
    record("unknown route explicit 404", status == 404 and isinstance(payload, dict) and payload.get("error") == "not found", f"status={status}")
    return checks


def _bounded_soak(port: int, token: str, root: Path, pid: int, duration: float, workers: int) -> dict:
    stop = threading.Event()
    lock = threading.Lock()
    latencies: list[float] = []
    errors: list[dict] = []
    route_counts: dict[str, int] = {}
    routes = [
        ("health", "/healthz", ""),
        ("runtime", "/runtime-info", ""),
        ("settings", "/settings", token),
        ("events", f"/events?sprint_id={SID}&limit=5", token),
        ("projection", f"/orchestration/projection?sprint_id={SID}&mode=fast", token),
        ("static", "/static/p0.css", ""),
    ]

    def validate(name: str, status: int, body: bytes) -> bool:
        if status != 200:
            return False
        if name == "health":
            return body == b"ok"
        if name == "static":
            return len(body) > 100
        payload = _json(body)
        if name == "runtime":
            return isinstance(payload, dict) and payload.get("ok") is True and Path(payload.get("harness_dir", "")).resolve() == root.resolve()
        if name == "settings":
            return isinstance(payload, dict) and payload.get("ok") is True and isinstance(payload.get("runtime"), dict)
        if name == "events":
            return isinstance(payload, list) and len(payload) == 1 and payload[0].get("marker") == "P22_ROUTE_EVENT"
        return isinstance(payload, dict) and payload.get("ok") is True and isinstance(payload.get("data"), dict)

    def worker(offset: int) -> None:
        index = offset
        while not stop.is_set():
            name, path, route_token = routes[index % len(routes)]
            index += 1
            try:
                status, _, body, latency = _request(port, path, token=route_token, timeout=15.0)
                ok = validate(name, status, body)
                with lock:
                    latencies.append(latency)
                    route_counts[name] = route_counts.get(name, 0) + 1
                    if not ok and len(errors) < 20:
                        errors.append({"route": name, "status": status, "reason": "contract_mismatch"})
            except Exception as exc:
                with lock:
                    if len(errors) < 20:
                        errors.append({"route": name, "reason": f"{type(exc).__name__}: {exc}"})

    samples = [{"elapsed_seconds": 0.0, **_process_metrics(pid)}]
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, i) for i in range(workers)]
        while time.monotonic() - started < duration:
            time.sleep(min(1.0, max(0.05, duration - (time.monotonic() - started))))
            samples.append({"elapsed_seconds": round(time.monotonic() - started, 3), **_process_metrics(pid)})
        stop.set()
        for future in futures:
            future.result(timeout=20.0)

    final_metrics = _process_metrics(pid)
    samples.append({"elapsed_seconds": round(time.monotonic() - started, 3), **final_metrics})
    rss_values = [int(sample["rss_bytes"]) for sample in samples if sample.get("rss_bytes") is not None]
    handle_values = [int(sample["handles_or_fds"]) for sample in samples if sample.get("handles_or_fds") is not None]
    thread_values = [int(sample["threads"]) for sample in samples if sample.get("threads") is not None]
    latency_ms = [value * 1000.0 for value in latencies]
    summary = {
        "duration_seconds": round(time.monotonic() - started, 3),
        "workers": workers,
        "requests": len(latencies),
        "route_counts": route_counts,
        "errors": errors,
        "latency_ms": {
            "min": round(min(latency_ms), 3) if latency_ms else None,
            "median": round(statistics.median(latency_ms), 3) if latency_ms else None,
            "p95": round(_percentile(latency_ms, 0.95), 3) if latency_ms else None,
            "p99": round(_percentile(latency_ms, 0.99), 3) if latency_ms else None,
            "max": round(max(latency_ms), 3) if latency_ms else None,
        },
        "process": {
            "rss_initial": rss_values[0] if rss_values else None,
            "rss_final": rss_values[-1] if rss_values else None,
            "rss_max": max(rss_values) if rss_values else None,
            "rss_growth": rss_values[-1] - rss_values[0] if rss_values else None,
            "handles_or_fds_initial": handle_values[0] if handle_values else None,
            "handles_or_fds_final": handle_values[-1] if handle_values else None,
            "handles_or_fds_max": max(handle_values) if handle_values else None,
            "handles_or_fds_growth": handle_values[-1] - handle_values[0] if handle_values else None,
            "threads_initial": thread_values[0] if thread_values else None,
            "threads_final": thread_values[-1] if thread_values else None,
            "threads_max": max(thread_values) if thread_values else None,
            "threads_growth": thread_values[-1] - thread_values[0] if thread_values else None,
        },
        "samples": samples,
    }
    summary["gates"] = {
        "no_contract_errors": not errors,
        "all_routes_exercised": all(route_counts.get(name, 0) > 0 for name, _, _ in routes),
        "p99_under_10_seconds": bool(latency_ms) and _percentile(latency_ms, 0.99) < 10_000,
        "rss_growth_under_128_mib": bool(rss_values) and rss_values[-1] - rss_values[0] < 128 * 1024 * 1024,
        "handle_or_fd_growth_under_64": bool(handle_values) and handle_values[-1] - handle_values[0] < 64,
        "thread_growth_under_16": bool(thread_values) and thread_values[-1] - thread_values[0] < 16,
        "server_still_healthy": _request(port, "/healthz", timeout=3.0)[0] == 200,
    }
    summary["ok"] = all(summary["gates"].values())
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=60.0, help="Bounded soak seconds")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 10.0 <= args.duration <= 300.0:
        parser.error("--duration must be between 10 and 300 seconds")
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")

    run_id = f"p22-128-routes-soak-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output = args.output or REPO_ROOT / "outputs" / "phase22-real-journeys" / run_id / "journey-result.json"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="p22-128-routes-soak-"))
    token = "p22-route-token-ephemeral"
    server_log = output.parent / f"{output.stem}-status-server.log"
    proc: subprocess.Popen | None = None
    actual_port = 0
    actual_server_pid = 0
    result: dict = {}
    try:
        for directory in ("config", "events", "home", "reports", "run", "sessions", "sprints", "state"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        sprint_root = root / "sprints" / SID
        sprint_root.mkdir(parents=True)
        (sprint_root / "smoke-report.md").write_text("# P22 route matrix artifact\n\nReal status-server artifact content.\n", encoding="utf-8")
        (root / "sprints" / f"{SID}.status.json").write_text(
            json.dumps({
                "sprint_id": SID,
                "title": "P22 status route soak",
                "status": "active",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }),
            encoding="utf-8",
        )
        session_dir = root / "sessions" / SID
        session_dir.mkdir(parents=True)
        (session_dir / "events.jsonl").write_text(
            json.dumps({
                "sprint_id": SID,
                "type": "route_probe",
                "actor": "p22-test",
                "marker": "P22_ROUTE_EVENT",
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            }) + "\n",
            encoding="utf-8",
        )
        port = _free_port()
        env = {key: value for key, value in os.environ.items() if key.upper() not in {"HOME", "USERPROFILE", "HARNESS_DIR", "SOLAR_HARNESS_DIR", "SOLAR_AUTH_TOKEN"}}
        env.update({
            "HOME": str(root / "home"),
            "USERPROFILE": str(root / "home"),
            "HARNESS_DIR": str(root),
            "SOLAR_SOURCE_HARNESS_DIR": str(REPO_HARNESS),
            "PYTHONPATH": str(REPO_HARNESS / "lib"),
            "SOLAR_BIND_HOST": "127.0.0.1",
            "SOLAR_STATUS_PORT_START": str(port),
            "SOLAR_STATUS_PORT_END": str(port),
            "SOLAR_REQUIRE_TOKEN": "1",
            "SOLAR_AUTH_TOKEN": token,
            "SOLAR_DB": str(root / "state" / "solar.db"),
            "SOLAR_USER_SECRETS_FILE": str(root / "config" / "secrets.env"),
            "OBSIDIAN_VAULT_PATH": str(root / "knowledge"),
        })
        log_handle = server_log.open("wb")
        try:
            proc = subprocess.Popen([sys.executable, "-u", str(SERVER)], cwd=str(root), env=env, stdout=log_handle, stderr=subprocess.STDOUT)
            actual_port, actual_server_pid = _wait_ready(root, proc)
            matrix = _route_matrix(actual_port, token, root)
            soak = _bounded_soak(actual_port, token, root, actual_server_pid, args.duration, args.workers)
        finally:
            log_handle.close()

        repo_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        matrix_passed = sum(1 for check in matrix if check["ok"])
        result = {
            "schema_version": "phase22.status-routes-soak.v1",
            "run_id": run_id,
            "journey_id": "P22-REPAIR-128",
            "task": "Exercise the production status server across representative routes and a bounded concurrent soak.",
            "repo_head": repo_head,
            "production_entrypoint": str(SERVER.relative_to(REPO_ROOT)).replace("\\", "/"),
            "process_identity": {
                "launcher_pid": proc.pid,
                "actual_server_pid": actual_server_pid,
                "source": "status-server.pid and /runtime-info (required to match)",
                "metrics_sampled_pid": actual_server_pid,
            },
            "exact_command": f"{sys.executable} {Path(__file__).relative_to(REPO_ROOT)} --duration {args.duration} --workers {args.workers} --output {output}",
            "environment": {
                "platform": sys.platform,
                "python": sys.version.split()[0],
                "home": "isolated temporary directory (removed)",
                "harness_dir": "isolated temporary directory (removed)",
                "bind": "127.0.0.1 random port",
                "token_enforcement": "forced; credential not archived",
            },
            "route_matrix": {"passed": matrix_passed, "failed": len(matrix) - matrix_passed, "checks": matrix},
            "bounded_soak": soak,
            "artifact_checks": {"output_exists": True, "server_log": str(server_log)},
            "result": "PASS_WITH_KNOWN_LIMITATIONS" if matrix_passed == len(matrix) and soak.get("ok") else "FAIL",
            "known_limitations": [
                f"The stability run is a bounded {soak.get('duration_seconds')} second soak, not long-running production evidence.",
                "The production Python status-server entrypoint was exercised directly; the portable desktop wrapper runtime was not exercised by this run.",
                "This is one Windows host and an isolated synthetic sprint; hosted, remote, multi-tenant, and provider-backed routes were not inferred.",
            ],
            "cleanup": {},
        }
    except Exception as exc:
        result = {
            "schema_version": "phase22.status-routes-soak.v1",
            "journey_id": "P22-REPAIR-128",
            "result": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        cleanup = _stop_server(proc, actual_server_pid, actual_port, root)
        log_text = server_log.read_text(encoding="utf-8", errors="replace") if server_log.exists() else ""
        error_markers = [
            marker for marker in (
                "Traceback (most recent call last)",
                "Exception occurred during processing of request",
                "Fatal Python error",
            )
            if marker in log_text
        ]
        result.setdefault("artifact_checks", {}).update({
            "server_log": str(server_log),
            "server_log_nonempty": bool(log_text.strip()),
            "unexpected_server_error_markers": error_markers,
            "unexpected_server_errors_absent": not error_markers,
            "sse_disconnect_no_noisy_traceback": "ConnectionResetError" not in log_text and not error_markers,
        })
        if error_markers:
            result["result"] = "FAIL"
            result["server_log_failure"] = {
                "error": "unexpected_server_error_output",
                "markers": error_markers,
            }
        result.setdefault("cleanup", {}).update(cleanup)
        shutil.rmtree(root, ignore_errors=True)
        result["cleanup"]["sandbox_removed"] = not root.exists()
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "result": result.get("result"),
        "route_matrix": result.get("route_matrix", {}),
        "soak": {key: result.get("bounded_soak", {}).get(key) for key in ("duration_seconds", "requests", "errors", "latency_ms", "process", "gates", "ok")},
        "cleanup": result.get("cleanup"),
        "evidence": str(output),
    }, indent=2, default=str))
    cleanup = result.get("cleanup", {})
    cleanup_ok = (
        cleanup.get("actual_server_identity_verified_before_stop") is True
        and cleanup.get("actual_server_pid_absent") is True
        and cleanup.get("port_closed") is True
        and cleanup.get("launcher_process_stopped") is True
        and cleanup.get("sandbox_removed") is True
    )
    log_ok = result.get("artifact_checks", {}).get("unexpected_server_errors_absent") is True
    return 0 if result.get("result") == "PASS_WITH_KNOWN_LIMITATIONS" and cleanup_ok and log_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
