#!/usr/bin/env python3
"""Audit Solar-Harness runtime write paths.

The managed-agent runtime keeps legacy `status.json` and `events.jsonl` files
as compatibility caches, but active writers must also bridge into session-log
v2 through runtime_status.py, runtime_bridge.py, events.sh/events_emit, or
equivalent adoption calls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar" / "harness")).expanduser()

ACTIVE_FILES = [
    "*.sh",
    "lib/*.sh",
    "lib/*.py",
    "tools/*.py",
]

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "vendor",
    "reports",
    "sessions",
    "sprints",
    "logs",
    "tmp",
    "node_modules",
}

CANONICAL_WRITERS = {
    "lib/runtime_status.py",
    "lib/projection_engine.py",
    "lib/runtime_bridge.py",
    "lib/session_log.py",
    "lib/phase-state-machine.sh",
    "lib/events.sh",
    "session.sh",
}

SYSTEM_TELEMETRY_WRITERS = {
    "lib/mirage_events.py",
    "lib/solar_mirage.py",
    "lib/skill_metrics.py",
    "lib/capability_registry.py",
    "lib/intent_engine_adapter.py",
    "tools/mirage_events.py",
    "tools/skill_metrics.py",
    "tools/solar_monitor_bridge.py",
}

BRIDGE_TOKENS = (
    "runtime_status.py",
    "runtime_bridge.py",
    "record_legacy_event",
    "transition_status",
    "events_emit",
    "emit_event",
    "adopt_sprint",
    "runtime_state_source",
    "SOLAR_SESSION_SH_NO_BRIDGE",
)

WRITE_PATTERNS = [
    ("legacy_event_append", re.compile(r">>.*events\.jsonl|open\(.*(?:events\.jsonl|EVENTS|event_file).*['\"]a|with .*events.*open\(.*['\"]a|write_text\(.*events", re.I)),
    ("legacy_status_write", re.compile(r"cat\s+>.*status\.json|open\(.*(?:status\.json|sf|status_file).*['\"]w|write_text\(.*status|json\.dump\(.*open\(.*(?:sf|status_file).*['\"]w", re.I)),
]

READ_ONLY_HINTS = (
    "exists(",
    ".exists()",
    "glob(",
    "read_text",
    "json.loads",
    "json.load",
    "tail",
    "grep",
    "cat ",
    "sed ",
    "status_path",
    "events_path",
    "source_file",
    "query_events",
    "log_path",
)


@dataclass
class Finding:
    path: str
    line: int
    kind: str
    status: str
    reason: str
    text: str


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in ACTIVE_FILES:
        for path in root.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            rel_parts = set(path.relative_to(root).parts)
            if rel_parts & EXCLUDED_PARTS:
                continue
            if path.name.startswith("test-") or path.name.startswith(".bak-") or ".bak-" in path.name:
                continue
            yield path


def _is_probable_read_only(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return True
    if stripped.startswith("echo ") or stripped.startswith("printf "):
        return True
    if any(hint in stripped for hint in READ_ONLY_HINTS):
        if ">>" not in stripped and "open(" not in stripped and "write_text" not in stripped and "json.dump" not in stripped:
            return True
    return False


def _context(lines: list[str], idx: int, radius: int = 12) -> str:
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    return "\n".join(lines[start:end])


def _classify(rel: str, kind: str, context: str) -> tuple[str, str]:
    if rel in CANONICAL_WRITERS:
        return "ok", "canonical runtime writer"
    if rel in SYSTEM_TELEMETRY_WRITERS and kind == "legacy_event_append":
        return "ok", "isolated system telemetry, not sprint lifecycle state"
    if any(token in context for token in BRIDGE_TOKENS):
        return "ok", "legacy cache write is bridged to session-log v2"
    if kind == "legacy_status_write":
        return "error", "status.json write without nearby runtime_status/adopt bridge"
    return "warn", "events.jsonl write without nearby runtime_bridge evidence"


def audit(root: Path) -> dict:
    root = root.expanduser().resolve()
    findings: list[Finding] = []
    scanned = 0
    for path in iter_files(root):
        scanned += 1
        rel = _rel(path, root)
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines):
            if _is_probable_read_only(line):
                continue
            for kind, pattern in WRITE_PATTERNS:
                if not pattern.search(line):
                    continue
                ctx = _context(lines, idx)
                status, reason = _classify(rel, kind, ctx)
                findings.append(Finding(rel, idx + 1, kind, status, reason, line.strip()[:220]))

    counts = {"ok": 0, "warn": 0, "error": 0}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    return {
        "ok": counts.get("error", 0) == 0,
        "root": str(root),
        "scanned_files": scanned,
        "counts": counts,
        "findings": [asdict(f) for f in findings],
    }


def _print_human(result: dict) -> None:
    counts = result["counts"]
    status = "ok" if result["ok"] else "error"
    print(f"Runtime write-path audit: {status}")
    print(f"root: {result['root']}")
    print(f"scanned_files: {result['scanned_files']}")
    print(f"counts: ok={counts.get('ok', 0)} warn={counts.get('warn', 0)} error={counts.get('error', 0)}")
    for f in result["findings"]:
        print(f"- {f['status']} {f['kind']} {f['path']}:{f['line']} — {f['reason']}")
        print(f"  {f['text']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit active runtime write paths for legacy-only state writes.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Harness root to scan")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero on warnings as well as errors")
    args = parser.parse_args()

    result = audit(Path(args.root))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)
    if result["counts"].get("error", 0):
        return 1
    if args.strict and result["counts"].get("warn", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
