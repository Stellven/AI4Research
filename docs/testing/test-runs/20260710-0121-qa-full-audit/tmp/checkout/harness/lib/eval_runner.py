#!/usr/bin/env python3
"""Run small Solar eval packs with explicit command gates."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))


def _load_pack(path: Path) -> dict[str, Any]:
    if path.suffix in {".yaml", ".yml"}:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text()) or {}
    return json.loads(path.read_text())


def run_pack(path: str | Path) -> dict[str, Any]:
    pack_path = Path(path)
    data = _load_pack(pack_path)
    checks = data.get("checks") or []
    results: list[dict[str, Any]] = []
    started = time.time()
    for check in checks:
        name = check.get("name", "unnamed")
        cmd = check.get("cmd", "")
        timeout = int(check.get("timeout_s", 30))
        expect_exit = int(check.get("expect_exit", 0))
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(HARNESS_DIR),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        results.append({
            "name": name,
            "cmd": cmd,
            "exit_code": proc.returncode,
            "expected": expect_exit,
            "passed": proc.returncode == expect_exit,
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        })
    ok = bool(checks) and all(r["passed"] for r in results)
    return {
        "ok": ok,
        "pack": data.get("id", pack_path.stem),
        "path": str(pack_path),
        "checks": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "elapsed_ms": int((time.time() - started) * 1000),
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="eval_runner.py")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run")
    p.add_argument("--pack", required=True)
    p.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "run":
        ap.print_help()
        return 1
    data = run_pack(args.pack)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"Eval {data['pack']}: {data['passed']}/{data['checks']} passed")
    return 0 if data["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
