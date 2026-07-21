#!/usr/bin/env python3
"""
multi_task_pane_state_writer.py

Polls 8 tmux pane runtimes (4 main solar-harness:0.{0-3} + 4 lab solar-harness-lab:0.{0-3})
and emits state/pane-state.json conforming to multi_task_screen.pane_state.v1.

CLI modes:
  --probe              snapshot current pane states and write to file
  --dry-run            snapshot and print JSON to stdout; no write
  --set ID STATE       force-set a single pane's state and write
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = "multi_task_screen.pane_state.v1"

STATE_ENUM = frozenset({
    "ok", "warn", "error", "idle", "active",
    "blocked", "dry_run", "ready", "working", "pending",
})

# 8 canonical panes: 4 main + 4 lab
# wpane = "window.pane" suffix used with tmux -t session:wpane
PANE_DEFS = [
    {"id": "main:0", "session": "solar-harness",     "wpane": "0.0", "role": "pm"},
    {"id": "main:1", "session": "solar-harness",     "wpane": "0.1", "role": "planner"},
    {"id": "main:2", "session": "solar-harness",     "wpane": "0.2", "role": "builder"},
    {"id": "main:3", "session": "solar-harness",     "wpane": "0.3", "role": "evaluator"},
    {"id": "lab:0",  "session": "solar-harness-lab", "wpane": "0.0", "role": "lab"},
    {"id": "lab:1",  "session": "solar-harness-lab", "wpane": "0.1", "role": "lab"},
    {"id": "lab:2",  "session": "solar-harness-lab", "wpane": "0.2", "role": "lab"},
    {"id": "lab:3",  "session": "solar-harness-lab", "wpane": "0.3", "role": "lab"},
]

_HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar/harness"))
STATE_FILE = _HARNESS_DIR / "state" / "pane-state.json"


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _tmux_has_session(session: str) -> bool:
    rc, _ = _run(["tmux", "has-session", "-t", session])
    return rc == 0


def _tmux_display(session: str, wpane: str, fmt: str) -> str:
    rc, out = _run(["tmux", "display-message", "-t", f"{session}:{wpane}", "-p", fmt])
    return out if rc == 0 else ""


def _infer_state(session: str, wpane: str, session_exists: bool) -> tuple[str, bool]:
    """Return (state_enum_value, low_confidence)."""
    if not session_exists:
        return "idle", False

    cmd = _tmux_display(session, wpane, "#{pane_current_command}")
    if not cmd:
        return "idle", False

    cmd_lower = cmd.lower()
    if cmd_lower in ("bash", "zsh", "sh", "fish", "dash"):
        return "ready", False
    if "claude" in cmd_lower:
        return "working", True
    if cmd_lower in ("python3", "python", "node", "ts-node"):
        return "active", True
    return "ready", True


def _infer_model(session: str, wpane: str, session_exists: bool) -> str:
    if not session_exists:
        return ""
    title = _tmux_display(session, wpane, "#{pane_title}")
    title_lower = title.lower()
    for token in ("opus", "sonnet", "haiku", "glm", "deepseek", "gpt", "gemini"):
        if token in title_lower:
            return token
    return ""


def probe_panes() -> list[dict]:
    """Snapshot all 8 pane states from live tmux."""
    now = _now_iso()
    session_cache: dict[str, bool] = {}
    panes = []
    for pdef in PANE_DEFS:
        sid = pdef["session"]
        if sid not in session_cache:
            session_cache[sid] = _tmux_has_session(sid)
        exists = session_cache[sid]
        state, low_conf = _infer_state(sid, pdef["wpane"], exists)
        model = _infer_model(sid, pdef["wpane"], exists)
        panes.append({
            "id": pdef["id"],
            "role": pdef["role"],
            "state": state,
            "model": model,
            "low_confidence": low_conf,
            "mtime": now,
        })
    return panes


def load_or_init() -> dict:
    """Load existing pane-state.json or return blank skeleton."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    now = _now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "panes": [
            {
                "id": p["id"],
                "role": p["role"],
                "state": "idle",
                "model": "",
                "low_confidence": True,
                "mtime": now,
            }
            for p in PANE_DEFS
        ],
    }


def write_atomic(data: dict) -> None:
    """Atomic write: tmp + os.replace so readers never see partial JSON."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def build_payload(panes: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "panes": panes,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="multi_task_pane_state_writer",
        description="Poll tmux pane runtimes and emit state/pane-state.json.",
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--probe", action="store_true",
                     help="Snapshot current pane states and write to file.")
    grp.add_argument("--dry-run", action="store_true", dest="dry_run",
                     help="Snapshot and print JSON to stdout; no write.")
    grp.add_argument("--set", nargs=2, metavar=("ID", "STATE"),
                     help="Force-set one pane's state and write (event-driven use).")

    args = parser.parse_args(argv)

    if args.probe or args.dry_run:
        panes = probe_panes()
        payload = build_payload(panes)
        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            write_atomic(payload)
            print(f"written {STATE_FILE}", file=sys.stderr)
        return

    if args.set:
        pane_id, new_state = args.set
        if new_state not in STATE_ENUM:
            print(f"error: '{new_state}' not in valid states: {sorted(STATE_ENUM)}", file=sys.stderr)
            sys.exit(1)
        data = load_or_init()
        now = _now_iso()
        found = False
        for pane in data["panes"]:
            if pane["id"] == pane_id:
                pane["state"] = new_state
                pane["mtime"] = now
                pane["low_confidence"] = False
                found = True
                break
        if not found:
            known = [p["id"] for p in data["panes"]]
            print(f"error: pane id '{pane_id}' not in {known}", file=sys.stderr)
            sys.exit(1)
        data["generated_at"] = now
        write_atomic(data)
        print(f"set {pane_id} → {new_state}", file=sys.stderr)


if __name__ == "__main__":
    main()
