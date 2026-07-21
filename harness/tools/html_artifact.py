#!/usr/bin/env python3
"""Register and optionally open human-readable HTML sprint artifacts.

This helper is intentionally fail-open for runtime use. Missing HTML, missing
status files, or macOS open failures must not block PM -> Planner -> Builder
routing; the canonical gates remain the Markdown and JSON artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", HARNESS_DIR / "sprints"))
VALID_KINDS = {"prd_html", "planning_html", "design_html"}


def _warn(message: str) -> None:
    print(f"WARN: {message}", file=sys.stderr)


def _artifact_value(path: Path) -> str:
    try:
        return f"sprints/{path.resolve().relative_to(SPRINTS_DIR.resolve())}"
    except ValueError:
        return str(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _register_status(sid: str, kind: str, html_path: Path) -> bool:
    status_path = SPRINTS_DIR / f"{sid}.status.json"
    if not status_path.is_file():
        _warn(f"status_missing:{status_path}")
        return False
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _warn(f"status_read_failed:{status_path}:{exc}")
        return False
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    artifacts[kind] = _artifact_value(html_path)
    data["artifacts"] = artifacts
    try:
        _atomic_write_json(status_path, data)
    except Exception as exc:
        _warn(f"status_write_failed:{status_path}:{exc}")
        return False
    return True


def _should_open() -> bool:
    return os.environ.get("SOLAR_HTML_AUTO_OPEN", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _open_html(html_path: Path) -> bool:
    if not _should_open():
        return False
    command = os.environ.get("SOLAR_HTML_OPEN_CMD", "").strip()
    if command:
        argv = [command, str(html_path)]
    elif sys.platform == "darwin" and shutil.which("open"):
        argv = ["open", str(html_path)]
    else:
        _warn("open_skipped:not_macos_or_open_missing")
        return False
    try:
        result = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=8)
    except Exception as exc:
        _warn(f"open_failed:{exc}")
        return False
    if result.returncode != 0:
        detail = (result.stderr or "").strip().replace("\n", " ")[:240]
        _warn(f"open_failed:rc={result.returncode}:{detail}")
        return False
    return True


def register(args: argparse.Namespace) -> int:
    kind = str(args.kind or "").strip()
    if kind not in VALID_KINDS:
        _warn(f"invalid_kind:{kind}")
        return 0
    html_path = Path(args.path).expanduser()
    if not html_path.is_file():
        _warn(f"html_missing:{html_path}")
        return 0
    registered = _register_status(args.sid, kind, html_path)
    opened = _open_html(html_path)
    payload = {
        "ok": True,
        "sid": args.sid,
        "kind": kind,
        "path": str(html_path),
        "registered": registered,
        "opened": opened,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"html_artifact kind={kind} registered={registered} opened={opened} path={html_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Register and open Solar Harness HTML artifacts")
    sub = parser.add_subparsers(dest="cmd", required=True)
    reg = sub.add_parser("register", help="Register an HTML artifact in status.json and optionally open it")
    reg.add_argument("--sid", required=True)
    reg.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    reg.add_argument("--path", required=True)
    reg.add_argument("--json", action="store_true")
    reg.set_defaults(func=register)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
