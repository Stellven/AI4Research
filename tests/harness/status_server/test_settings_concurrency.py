#!/usr/bin/env python3
"""Backend P0 gate: prove the status-server settings write is concurrency-safe and CORS advertises
the auth-token header. Spins up the REAL status-server on an isolated temp HARNESS_DIR (nothing
touches ~/.solar), then:

  F1  OPTIONS /settings preflight advertises `X-Solar-Token` in Access-Control-Allow-Headers.
  C1a Concurrent POST /settings to DIFFERENT keys (runtime / codex / models) never loses an update
      (the read-modify-write lost-update bug).
  C1b A reader of solar-user-config.json during a write storm never sees torn/partial JSON.
      Windows raw-path readers may need to retry a sharing transition; the supported HTTP reader
      must remain available and parseable throughout the storm.
  T1  An unsafe sprint_id ("../leak", "..") on /status can't read files outside the harness dirs
      (path traversal via _runtime_events_path; fixed by _valid_sprint_id at the path chokepoints).

Usage:  python3 test_settings_concurrency.py [/path/to/status-server.py]
Exits non-zero if any check fails. No mocks — real server, real HTTP, real concurrent threads.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.client import HTTPConnection
from pathlib import Path

REPO_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')  # .../harness
DEFAULT_SERVER = REPO_HARNESS / "lib" / "symphony" / "status-server.py"
SERVER = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SERVER

results = []
def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))

def wait_port(port_file: Path, timeout=20.0):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            port = int(port_file.read_text().strip())
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1.5) as r:
                if r.status == 200:
                    return port
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("backend not healthy in time")

def post_settings(port, payload):
    body = json.dumps(payload).encode()
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/settings", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    out = json.loads(resp.read() or b"{}")
    conn.close()
    return resp.status, out

def get_settings(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/settings", timeout=5) as r:
        return json.loads(r.read() or b"{}")

def options_headers(port, path="/settings"):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("OPTIONS", path, headers={"Access-Control-Request-Headers": "x-solar-token"})
    resp = conn.getresponse()
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    resp.read(); conn.close()
    return resp.status, hdrs

def main():
    tmp = Path(tempfile.mkdtemp(prefix="solar-backend-p0-"))
    for d in ("config", "run", "sprints", "events", "sessions", "reports", "home"):
        (tmp / d).mkdir(parents=True, exist_ok=True)
    cfg_path = tmp / "config" / "solar-user-config.json"
    # Windows environment names are case-insensitive. Remove inherited aliases
    # before inserting this run's root, otherwise ``Harness_Dir`` can win over
    # ``HARNESS_DIR`` and make the child mutate a stale desktop-test sandbox.
    base_env = {
        key: value for key, value in os.environ.items()
        if key.upper() not in {"HARNESS_DIR", "SOLAR_HARNESS_DIR"}
    }
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        isolated_port = probe.getsockname()[1]
    env = {
        **base_env,
        "HARNESS_DIR": str(tmp),
        "PYTHONPATH": str(REPO_HARNESS / "lib"),
        "SOLAR_BIND_HOST": "127.0.0.1",
        "SOLAR_DB": str(tmp / "solar.db"),
        "SOLAR_USER_SECRETS_FILE": str(tmp / "secrets.env"),
        "HOME": str(tmp / "home"),
        "USERPROFILE": str(tmp / "home"),
        "SOLAR_STATUS_PORT_START": str(isolated_port),
        "SOLAR_STATUS_PORT_END": str(isolated_port),
    }
    proc = subprocess.Popen([sys.executable, str(SERVER)], cwd=str(tmp), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        port = wait_port(tmp / "run" / "status-server.port")

        # --- F1: CORS preflight advertises X-Solar-Token ---
        status, hdrs = options_headers(port)
        allow = hdrs.get("access-control-allow-headers", "")
        check("F1 OPTIONS /settings preflight 204", status == 204, f"status={status}")
        check("F1 Allow-Headers advertises X-Solar-Token",
              "x-solar-token" in allow.lower(), f"Allow-Headers={allow!r}")

        # --- T1: path traversal — an unsafe sprint_id must not read files outside the harness ---
        # Plant a marker one level above SPRINTS_DIR (= HARNESS_DIR/sprints). A pre-fix server maps
        # sprint_id "../leak" -> SPRINTS_DIR/"../leak.events.jsonl" = HARNESS_DIR/leak.events.jsonl
        # and leaks it via /status recent_events; the fix rejects the unsafe id (-> global/empty).
        (tmp / "leak.events.jsonl").write_text(
            json.dumps({"sprint_id": "../leak", "summary": "TRAVERSAL_LEAK_MARKER_XYZ"}) + "\n",
            encoding="utf-8")
        leaked = False
        # Hit the real reachable vector (/events -> _events_for_request -> _runtime_events_path) AND
        # /status. On the unfixed base, /events?sprint_id=../leak leaks the planted file; the fix
        # makes both safe. (/status only reaches the path when recent_events are session-scoped.)
        for ep in ("/events?limit=50&sprint_id=", "/status?sprint_id="):
            for bad in ("../leak", "..", "../../etc/hostname"):
                try:
                    url = f"http://127.0.0.1:{port}{ep}{urllib.parse.quote(bad, safe='')}"
                    with urllib.request.urlopen(url, timeout=5) as r:
                        if "TRAVERSAL_LEAK_MARKER_XYZ" in r.read().decode("utf-8", "replace"):
                            leaked = True
                except Exception:
                    pass  # a rejection / error is also "not leaked"
        check("T1 path traversal blocked (unsafe sprint_id can't read outside harness dirs)", not leaked)

        # --- T2: fail CLOSED — an invalid sprint_id must 400, not silently return global/other data ---
        def status_code(ep):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{ep}", timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
            except Exception:
                return -1
        bad = urllib.parse.quote("../leak", safe="")
        closed = all(status_code(f"{ep}{bad}") == 400 for ep in (
            "/status?sprint_id=", "/events?limit=5&sprint_id=",
            "/orchestration/dashboard?sprint_id=", "/orchestration/projection?sprint_id="))
        check("T2 invalid sprint_id fails closed (400 on status/events/dashboard/projection)", closed)

        # --- C1b: torn-read watchdog reads the config file during the storm ---
        stop = threading.Event()
        torn = {"count": 0, "samples": [], "sharing_transitions": 0}
        def reader():
            while not stop.is_set():
                try:
                    raw = cfg_path.read_text(encoding="utf-8")
                    if raw.strip():
                        json.loads(raw)  # raises on a truncated/partial write
                except (FileNotFoundError, PermissionError):
                    # Arbitrary raw-path readers do not participate in the Windows
                    # ReplaceFile sharing contract. They must retry; unlike a torn
                    # document, this transition cannot be mistaken for valid config.
                    torn["sharing_transitions"] += 1
                except Exception as e:
                    torn["count"] += 1
                    if len(torn["samples"]) < 3:
                        torn["samples"].append(type(e).__name__)
                time.sleep(0.0005)
        rt = threading.Thread(target=reader, daemon=True)
        rt.start()

        api_errors = []
        def api_reader():
            while not stop.is_set():
                try:
                    payload = get_settings(port)
                    if payload.get("ok") is not True:
                        raise AssertionError(f"unexpected settings payload: {payload!r}")
                except Exception as exc:
                    if len(api_errors) < 3:
                        api_errors.append(type(exc).__name__)
        api_rt = threading.Thread(target=api_reader, daemon=True)
        api_rt.start()

        # --- C1a: 3 writers hammer DIFFERENT keys concurrently; none must be lost ---
        ITER = 80
        accepted = {"runtime": 0, "codex": 0, "models": 0}
        write_failures = []
        def w_runtime():
            for _ in range(ITER):
                status, out = post_settings(port, {"runtime": "codex"})
                if out.get("applied_runtime") == "codex":
                    accepted["runtime"] += 1
                elif len(write_failures) < 3:
                    write_failures.append((status, out))
        def w_codex():
            for _ in range(ITER):
                status, out = post_settings(port, {"codex": {"search": True, "effort": "high"}})
                if (out.get("applied_codex") or {}).get("effort") == "high":
                    accepted["codex"] += 1
                elif len(write_failures) < 3:
                    write_failures.append((status, out))
        def w_models():
            for _ in range(ITER):
                status, out = post_settings(port, {"role_models": {"pm": "claude-opus"}})
                if (out.get("applied_models") or {}).get("pm"):
                    accepted["models"] += 1
                elif len(write_failures) < 3:
                    write_failures.append((status, out))
        threads = [threading.Thread(target=f) for f in (w_runtime, w_codex, w_models)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stop.set(); rt.join(timeout=2); api_rt.join(timeout=2)

        # All three writers must have had their writes accepted at least once.
        check("C1a every writer request accepted", all(v == ITER for v in accepted.values()),
              f"accepted={accepted} failures={write_failures}")

        # Final state must contain ALL THREE keys — the lost-update bug drops at least one.
        final = get_settings(port)
        runtime_ok = (final.get("runtime") or {}).get("value") == "codex"
        codex = final.get("codex") or {}
        codex_ok = codex.get("search") is True and str(codex.get("effort")) == "high"
        # models live under the settings payload; read the file directly for an authoritative check.
        on_disk = None
        for _ in range(100):
            try:
                on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
                break
            except (FileNotFoundError, PermissionError):
                time.sleep(0.002)
        on_disk = on_disk or {}
        models_ok = (on_disk.get("models") or {}).get("pm") == "claude-opus"
        check("C1a runtime survived concurrent writes", runtime_ok, json.dumps(final.get("runtime")))
        check("C1a codex survived concurrent writes", codex_ok, json.dumps(codex))
        check("C1a models survived concurrent writes (no lost update)", models_ok,
              json.dumps(on_disk.get("models")))
        check("C1b no torn/partial config read during write storm",
              torn["count"] == 0,
              f"torn={torn['count']} sharing_transitions={torn['sharing_transitions']} {torn['samples']}")
        check("C1c supported HTTP settings reader stayed available during write storm",
              not api_errors, repr(api_errors))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        try:
            err = proc.stderr.read().decode()[-600:] if proc.stderr else ""
            if err.strip():
                print("--- server stderr (tail) ---\n" + err)
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for r in results if r)
    print(f"\nBACKEND-P0: {passed}/{len(results)} passed  (server: {SERVER})")
    sys.exit(0 if passed == len(results) and results else 1)

if __name__ == "__main__":
    main()
