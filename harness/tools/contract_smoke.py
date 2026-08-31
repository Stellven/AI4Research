#!/usr/bin/env python3
"""Submit one explicitly authorized rapid smoke request, retaining evidence.

No retries, alternate URLs, service starts, artifact repairs, or worker control.
Call from the authoritative runtime, with its exact URL and an existing request
JSON. Default is preflight only; --submit is deliberately explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--repo-head", required=True)
    parser.add_argument("--expected-sessions", type=int, required=True)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if Path.cwd().resolve() != runtime or not (runtime / "lib/elastic_planner.py").is_file():
        raise SystemExit("Authoritative runtime cwd mismatch")
    url = args.url.rstrip("/")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise urllib.error.URLError("Redirect refused: backend is locked")
    opener = urllib.request.build_opener(NoRedirect)
    def get(route):
        with opener.open(url + route, timeout=10) as response:
            return json.load(response)
    identity = get("/runtime-info")
    sessions = get("/api/sprints")
    if Path(identity["harness_dir"]).resolve() != runtime or not sessions.get("ok") or identity["port"] != urlsplit(url).port:
        raise SystemExit("Backend runtime identity mismatch")
    pid = identity["pid"]
    # This deployed runtime uses WSL/Linux. Unsupported hosts fail explicitly.
    proc = Path("/proc") / str(pid)
    env = dict(item.split(b"=", 1) for item in (proc / "environ").read_bytes().split(b"\0") if b"=" in item)
    selected_env = {key: env.get(key.encode(), b"").decode() for key in
                    ("HARNESS_DIR", "SOLAR_HARNESS_DIR", "SOLAR_TEST_MODE")}
    if (proc / "cwd").resolve() != runtime or any(Path(selected_env[k]).resolve() != runtime for k in ("HARNESS_DIR", "SOLAR_HARNESS_DIR")):
        raise SystemExit("Backend cwd/environment mismatch")
    if selected_env["SOLAR_TEST_MODE"] != "rapid_smoke":
        raise SystemExit("Backend is not in trusted rapid_smoke mode")
    rows = sessions["data"]["sprints"]
    if len(rows) != args.expected_sessions:
        raise SystemExit("Session baseline changed; inspect before submitting")
    if sessions["data"]["active_sprints"]:
        raise SystemExit("Active sessions exist; inspect before starting a smoke task")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    request = {"task": request["task"], "request_id": args.request_id}
    baseline = {"identity": identity, "environment": selected_env, "repo_head": args.repo_head,
                "session_count": len(rows), "sessions": rows,
                "session_status_hashes": {p.name: sha(p) for p in (runtime / "sprints").glob("sprint-*.status.json")},
                "source_hashes": {str(p.relative_to(runtime)): sha(p) for directory in ("lib", "schemas", "tools")
                                  for p in (runtime / directory).rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".sh"}},
                "prompt_sha256": hashlib.sha256(request["task"].encode()).hexdigest(),
                "started_at": datetime.now(timezone.utc).isoformat(), "maximum_submissions": 1}
    print(json.dumps({"identity": identity, "environment": selected_env, "sessions": len(rows),
                      "prompt_sha256": baseline["prompt_sha256"], "submit": args.submit}), flush=True)
    if not args.submit:
        return 0
    if not args.request_id or Path(args.request_id).name != args.request_id or args.request_id in {".", ".."}:
        raise SystemExit("Invalid evidence/request ID")
    evidence = runtime / ".codex-tmp" / args.request_id
    evidence.mkdir(parents=True, exist_ok=False)
    def save(name, data):
        (evidence / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    save("baseline.json", baseline)
    save("request.json", request)
    start = time.monotonic()
    call = urllib.request.Request(url + "/intake", data=json.dumps(request).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener.open(call, timeout=1800) as response:
            result = {"http_status": response.status, "body": json.load(response)}
    except urllib.error.HTTPError as exc:
        result = {"http_status": exc.code, "body": exc.read().decode(errors="replace")}
    except Exception as exc:
        result = {"transport_error": str(exc), "submission_state": "unknown; do not retry"}
    result["duration_seconds"] = round(time.monotonic() - start, 3)
    save("intake-response.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get("http_status") == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
