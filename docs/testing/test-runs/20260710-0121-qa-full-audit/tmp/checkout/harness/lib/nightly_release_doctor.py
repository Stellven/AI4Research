#!/usr/bin/env python3
"""Doctor for the external-heavy Solar nightly release gate.

The normal PR workflow intentionally avoids checks that require a prepared
machine. This doctor makes those requirements explicit and reusable from local
shells, GitHub Actions preflight, and future automations.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Check:
    name: str
    status: str
    detail: str
    required_for_full: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "required_for_full": self.required_for_full,
        }


def _run(cmd: list[str], *, cwd: Path, timeout: int = 30, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _short(text: str, *, limit: int = 240) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _check_file(path: Path, name: str, *, required_for_full: bool = False) -> Check:
    if path.exists():
        return Check(name, "ok", str(path), required_for_full)
    return Check(name, "error", f"missing: {path}", required_for_full)


def _check_cmd_exists(cmd: str, *, required_for_full: bool = False) -> Check:
    found = shutil.which(cmd)
    if found:
        return Check(cmd, "ok", found, required_for_full)
    status = "error" if required_for_full else "warn"
    return Check(cmd, status, "missing", required_for_full)


def _check_bash_syntax(harness_dir: Path, rel: str) -> Check:
    result = _run(["bash", "-n", rel], cwd=harness_dir)
    if result.returncode == 0:
        return Check(f"{rel} syntax", "ok", "bash -n")
    return Check(f"{rel} syntax", "error", _short(result.stderr or result.stdout))


def _check_release_dry_run(harness_dir: Path) -> Check:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness_dir)
    result = _run(["bash", "release/build.sh", "--dry-run"], cwd=harness_dir, timeout=60, env=env)
    output = f"{result.stdout}\n{result.stderr}"
    if "would create" in output and "Exclusions" in output:
        return Check("release dry-run", "ok", "would create + exclusions")
    return Check("release dry-run", "error", _short(output))


def _check_plugin_manifest(harness_dir: Path) -> Check:
    result = _run([sys.executable, "lib/plugin_loader.py", "validate", "--json"], cwd=harness_dir, timeout=60)
    if result.returncode != 0:
        return Check("plugin manifest schema", "error", _short(result.stderr or result.stdout))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return Check("plugin manifest schema", "error", f"invalid json: {exc}")
    if payload.get("ok") is True:
        return Check("plugin manifest schema", "ok", f"checked={payload.get('checked', 'N/A')}")
    return Check("plugin manifest schema", "error", _short(result.stdout))


def _check_solar_context(harness_dir: Path) -> Check:
    cmd = ["bash", "solar-harness.sh", "context", "inject", "--query", "nightly release preflight", "--format", "markdown"]
    result = _run(cmd, cwd=harness_dir, timeout=60)
    if result.returncode == 0:
        return Check("Solar context", "ok", "context inject")
    return Check("Solar context", "warn", _short(result.stderr or result.stdout))


def _json_from_output(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise json.JSONDecodeError("missing json object", text, 0)
    payload, _end = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("json payload is not an object", text, start)
    return payload


def _check_mirage_drive(harness_dir: Path) -> Check:
    result = _run(["bash", "solar-harness.sh", "mirage", "doctor", "--json"], cwd=harness_dir, timeout=30)
    if result.returncode != 0:
        return Check("Mirage /drive", "error", _short(result.stderr or result.stdout), True)
    try:
        payload = _json_from_output(f"{result.stdout}\n{result.stderr}")
    except json.JSONDecodeError as exc:
        return Check("Mirage /drive", "error", f"invalid mirage doctor json: {exc}", True)
    drive = payload.get("drive") if isinstance(payload.get("drive"), dict) else {}
    if drive.get("status") == "ok":
        detail = drive.get("local_root") or drive.get("reason") or "drive.status=ok"
        return Check("Mirage /drive", "ok", str(detail), True)
    return Check("Mirage /drive", "error", _short(json.dumps(drive, ensure_ascii=False)), True)



def _check_tvs_root(value: str) -> Check:
    if not value:
        return Check("SOLAR_TVS_ROOT", "error", "unset", True)
    path = Path(value).expanduser()
    if (path / "index.ts").exists():
        return Check("SOLAR_TVS_ROOT", "ok", str(path), True)
    return Check("SOLAR_TVS_ROOT", "error", f"index.ts missing under {path}", True)


def run_doctor(harness_dir: Path, *, tvs_root: str = "", include_external: bool = True) -> dict[str, Any]:
    harness_dir = harness_dir.expanduser().resolve()
    checks: list[Check] = [
        _check_file(harness_dir / "VERSION", "VERSION"),
        _check_file(harness_dir / "release/CHANGELOG.md", "release/CHANGELOG.md"),
        _check_file(harness_dir / "docs/upgrade-guide.md", "docs/upgrade-guide.md"),
        _check_file(harness_dir / "docs/rollback-guide.md", "docs/rollback-guide.md"),
        _check_bash_syntax(harness_dir, "release/build.sh"),
        _check_bash_syntax(harness_dir, "release/publish.sh"),
        _check_release_dry_run(harness_dir),
        _check_plugin_manifest(harness_dir),
    ]
    for n in ("001", "002", "003", "004", "005"):
        matches = list((harness_dir / "ADR").glob(f"ADR-{n}-*.md"))
        checks.append(Check(f"ADR-{n}", "ok" if matches else "error", str(matches[0]) if matches else "missing"))
    checks.append(_check_cmd_exists("bun", required_for_full=True))
    checks.append(_check_tvs_root(tvs_root or os.environ.get("SOLAR_TVS_ROOT", "")))
    if include_external:
        checks.append(_check_solar_context(harness_dir))
        checks.append(_check_mirage_drive(harness_dir))

    required = [item for item in checks if item.required_for_full]
    ok = all(item.status != "error" for item in checks if not item.required_for_full)
    full_ready = all(item.status == "ok" for item in required)
    return {
        "ok": ok,
        "full_ready": full_ready,
        "harness_dir": str(harness_dir),
        "checks": [item.as_dict() for item in checks],
        "summary": {
            "ok": sum(1 for item in checks if item.status == "ok"),
            "warn": sum(1 for item in checks if item.status == "warn"),
            "error": sum(1 for item in checks if item.status == "error"),
            "required_for_full_errors": [
                item.name for item in checks if item.required_for_full and item.status == "error"
            ],
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "## Solar nightly release doctor",
        "",
        f"- Harness: `{payload.get('harness_dir')}`",
        f"- Preflight ok: `{payload.get('ok')}`",
        f"- Full gate ready: `{payload.get('full_ready')}`",
        "",
        "| Check | Status | Required for full | Detail |",
        "|---|---:|---:|---|",
    ]
    for item in payload.get("checks") or []:
        detail = str(item.get("detail") or "").replace("|", "\\|")
        lines.append(
            f"| {item.get('name')} | {item.get('status')} | {item.get('required_for_full')} | `{detail}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check nightly release gate prerequisites.")
    parser.add_argument("--harness-dir", default=os.environ.get("HARNESS_DIR", str(Path.cwd())))
    parser.add_argument("--tvs-root", default=os.environ.get("SOLAR_TVS_ROOT", ""))
    parser.add_argument("--json", action="store_true", help="Emit JSON payload.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown summary.")
    parser.add_argument("--require-full", action="store_true", help="Exit non-zero unless full gate dependencies are ready.")
    parser.add_argument("--skip-external", action="store_true", help="Skip Solar context and Mirage /drive probes.")
    args = parser.parse_args(argv)

    payload = run_doctor(Path(args.harness_dir), tvs_root=args.tvs_root, include_external=not args.skip_external)
    if args.markdown:
        print(render_markdown(payload), end="")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.json else None))
    if args.require_full:
        return 0 if payload.get("full_ready") else 1
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
