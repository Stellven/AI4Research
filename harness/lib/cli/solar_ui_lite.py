#!/usr/bin/env python3
"""Read-only terminal dashboard for installed OpenSolar state."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


SESSION_NAME = "solar-harness"
LAB_SESSION_NAME = "solar-harness-lab"
AUTH_PATTERNS = (
    "login",
    "not authenticated",
    "authentication",
    "auth",
    "trust",
)
QUOTA_PATTERNS = (
    "usage limit",
    "rate limit",
    "quota",
    "too many requests",
)


@dataclass
class CmdResult:
    rc: int
    out: str
    err: str


class Style:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def title(self, text: str) -> str:
        return self._wrap("1;36", text)

    def ok(self, text: str) -> str:
        return self._wrap("32", text)

    def warn(self, text: str) -> str:
        return self._wrap("33", text)

    def fail(self, text: str) -> str:
        return self._wrap("31", text)


def run_cmd(argv: list[str], timeout: float = 5.0) -> CmdResult:
    try:
        exec_argv = list(argv)
        if os.name == "nt":
            first = Path(argv[0])
            if first.suffix.lower() not in (".exe", ".bat", ".cmd", ".py"):
                # Shell scripts are not directly executable on Windows; prefix with bash.
                import shutil as _shutil
                bash = _shutil.which("bash") or "bash"
                exec_argv = [bash] + exec_argv
        proc = subprocess.run(
            exec_argv,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return CmdResult(proc.returncode, proc.stdout, proc.stderr)
    except FileNotFoundError as exc:
        return CmdResult(127, "", str(exc))
    except OSError as exc:
        return CmdResult(127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        return CmdResult(124, out, err or f"timed out after {timeout:.1f}s")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_bash_version(text: str) -> tuple[int, int] | None:
    match = re.search(r"version\s+([0-9]+)\.([0-9]+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def configured_pane_runtime(harness_dir: Path) -> str:
    runtime = os.environ.get("SOLAR_PANE_RUNTIME", "").strip().lower()
    if not runtime:
        config = load_json(harness_dir / "config" / "solar-user-config.json")
        runtime = str(config.get("runtime") or "claude").strip().lower()
    return runtime if runtime in {"claude", "codex"} else "claude"


def runtime_display_name(runtime: str) -> str:
    return "Codex" if runtime == "codex" else "Claude"


def dep_statuses(pane_runtime: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    hints = {
        "python3": "macOS: brew install python; Ubuntu/Debian: sudo apt-get install python3",
        "tmux": "macOS: brew install tmux; Ubuntu/Debian: sudo apt-get install tmux",
        "jq": "macOS: brew install jq; Ubuntu/Debian: sudo apt-get install jq",
        "claude": "Install the Claude Code CLI and confirm 'claude --version' works",
        "codex": "Install the Codex CLI and confirm 'codex --version' works",
    }
    for name in ("python3", "tmux", "jq", pane_runtime):
        found = shutil.which(name)
        if found:
            rows.append((name, "ok", found))
        else:
            rows.append((name, "missing", hints[name]))

    candidates: list[Path] = []
    for raw in (
        os.environ.get("BASH", ""),
        shutil.which("bash") or "",
        "/opt/homebrew/bin/bash",
        "/usr/local/bin/bash",
        "/usr/bin/bash",
        "/bin/bash",
    ):
        if raw:
            path = Path(raw).expanduser()
            if path not in candidates:
                candidates.append(path)

    bash_ok = False
    bash_detail = "macOS: brew install bash; Ubuntu/Debian: sudo apt-get install bash"
    for path in candidates:
        if not path.exists():
            continue
        result = run_cmd([str(path), "--version"], timeout=2.0)
        first_line = result.out.splitlines()[0] if result.out else ""
        version = parse_bash_version(first_line)
        if version and version >= (4, 0):
            bash_ok = True
            bash_detail = f"{path} ({first_line})"
            break
        if version:
            bash_detail = f"{path} is {version[0]}.{version[1]}; need >=4"
    rows.append(("bash>=4", "ok" if bash_ok else "missing", bash_detail))
    return rows


def path_status(path: Path, want_dir: bool = False) -> str:
    ok = path.is_dir() if want_dir else path.exists()
    return "ok" if ok else "missing"


def live_pid(pid: str) -> bool:
    if not pid.isdigit():
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def limited_recent_files(root: Path, patterns: tuple[str, ...], limit: int = 5) -> list[Path]:
    if not root.exists():
        return []
    found: list[Path] = []
    for pattern in patterns:
        found.extend(p for p in root.rglob(pattern) if p.is_file())
    found.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return found[:limit]


def classify_live_boundary(captured_text: str, tmux_present: bool, runtime_name: str) -> tuple[str, str]:
    lowered = captured_text.lower()
    if any(pattern in lowered for pattern in QUOTA_PATTERNS):
        return "quota-blocked", f"{runtime_name} pane text reports quota/rate-limit state."
    if any(pattern in lowered for pattern in AUTH_PATTERNS):
        return "auth-blocked", f"{runtime_name} pane text reports auth/trust/login state."
    if not tmux_present:
        return "manual-pending", "No Product Delivery tmux session is present."
    return "unverified", f"Plumbing is visible, but no real {runtime_name} response/delegation proof was found."


def collect_runtime(harness_dir: Path) -> dict:
    tmux_path = shutil.which("tmux")
    runtime: dict = {
        "tmux_path": tmux_path or "",
        "session_present": False,
        "lab_present": False,
        "windows": [],
        "panes": [],
        "captured_text": "",
        "tmux_error": "",
        "coordinator": "not-running",
        "recent": [],
    }
    if tmux_path:
        has = run_cmd([tmux_path, "has-session", "-t", SESSION_NAME], timeout=2.0)
        runtime["session_present"] = has.rc == 0
        lab = run_cmd([tmux_path, "has-session", "-t", LAB_SESSION_NAME], timeout=2.0)
        runtime["lab_present"] = lab.rc == 0
        if has.rc == 0:
            windows = run_cmd(
                [tmux_path, "list-windows", "-t", SESSION_NAME, "-F", "#{window_index}: #{window_name} (#{window_panes} panes)"],
                timeout=2.0,
            )
            runtime["windows"] = [line for line in windows.out.splitlines() if line.strip()]
            panes = run_cmd(
                [tmux_path, "list-panes", "-t", f"{SESSION_NAME}:0", "-F", "#{pane_index}: #{pane_current_command} pid=#{pane_pid}"],
                timeout=2.0,
            )
            runtime["panes"] = [line for line in panes.out.splitlines() if line.strip()]
            capture = run_cmd([tmux_path, "capture-pane", "-p", "-S", "-120", "-t", f"{SESSION_NAME}:0.0"], timeout=2.0)
            runtime["captured_text"] = capture.out
        elif has.err:
            runtime["tmux_error"] = has.err.strip()

    pidfile = harness_dir / ".coordinator.pid"
    if pidfile.exists():
        pid = pidfile.read_text(encoding="utf-8", errors="replace").strip()
        runtime["coordinator"] = f"alive pid={pid}" if live_pid(pid) else f"stale pid={pid or 'unknown'}"

    recent_roots = [
        harness_dir / "run" / "operator-inbox",
        harness_dir / "run" / "operator-results",
        harness_dir / "run" / "operator-status",
        harness_dir / "run" / "queue",
        harness_dir / "sprints",
    ]
    recent: list[Path] = []
    for root in recent_roots:
        recent.extend(limited_recent_files(root, ("*.json", "*.jsonl", "*.status.json"), limit=3))
    recent.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    runtime["recent"] = recent[:6]
    return runtime


def collect_state() -> dict:
    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
    solar_home = Path(os.environ.get("SOLAR_HOME", str(home / ".solar"))).expanduser()
    claude_dir = Path(os.environ.get("CLAUDE_DIR", str(home / ".claude"))).expanduser()
    receipt_path = Path(os.environ.get("RECEIPT_PATH", str(solar_home / "install-receipt.json"))).expanduser()
    receipt = load_json(receipt_path) if receipt_path.exists() else {}
    components = receipt.get("components", []) if isinstance(receipt.get("components"), list) else []

    solar_bin = solar_home / "bin" / "solar"
    harness_bin = solar_home / "bin" / "solar-harness"
    harness_dir = solar_home / "harness"
    pane_runtime = configured_pane_runtime(harness_dir)
    installed_markers = [
        receipt_path,
        solar_bin,
        claude_dir / "solar" / "SOLAR.md",
        solar_home,
    ]
    installed = any(path.exists() for path in installed_markers)

    doctor_payload = {}
    doctor_error = ""
    if solar_bin.exists():
        result = run_cmd([str(solar_bin), "doctor", "--json"], timeout=6.0)
        if result.out.strip():
            try:
                doctor_payload = json.loads(result.out)
            except Exception:
                doctor_error = result.out.strip()
        if result.rc != 0 and not doctor_error:
            doctor_error = (result.err or result.out).strip()
    if not components and isinstance(doctor_payload.get("components"), list):
        components = doctor_payload.get("components", [])

    preflight = CmdResult(0, "", "")
    if harness_bin.exists():
        preflight = run_cmd([str(harness_bin), "preflight"], timeout=8.0)

    return {
        "home": home,
        "solar_home": solar_home,
        "claude_dir": claude_dir,
        "receipt_path": receipt_path,
        "receipt": receipt,
        "components": components,
        "solar_bin": solar_bin,
        "harness_bin": harness_bin,
        "harness_dir": harness_dir,
        "pane_runtime": pane_runtime,
        "installed": installed,
        "doctor_payload": doctor_payload,
        "doctor_error": doctor_error,
        "deps": dep_statuses(pane_runtime),
        "preflight": preflight,
        "runtime": collect_runtime(harness_dir),
    }


def status_word(style: Style, value: str) -> str:
    if value in {"ok", "alive", "present"} or value.startswith("alive"):
        return style.ok(value)
    if value in {"missing", "fail", "preflight-failed", "quota-blocked", "auth-blocked"} or value.startswith("stale"):
        return style.fail(value)
    return style.warn(value)


def render(state: dict, style: Style) -> str:
    lines: list[str] = []
    runtime_name = runtime_display_name(state["pane_runtime"])
    lines.append(style.title("Solar UI-lite"))
    lines.append(f"deterministic local dashboard; not live {runtime_name} behavior")
    lines.append("")

    solar_home: Path = state["solar_home"]
    claude_dir: Path = state["claude_dir"]
    receipt_path: Path = state["receipt_path"]
    components = state["components"]
    doctor = state["doctor_payload"]
    harness_bin: Path = state["harness_bin"]
    harness_dir: Path = state["harness_dir"]
    installed = state["installed"]

    lines.append("[Install health]")
    if not installed:
        lines.append("status: not-installed")
        lines.append(f"expected solar home: {solar_home}")
        lines.append("install with: ./install.sh --yes --components kernel,harness")
    else:
        verdict = doctor.get("verdict") or ("ok" if receipt_path.exists() else "partial")
        lines.append(f"doctor: {status_word(style, str(verdict))}")
        if state["doctor_error"]:
            lines.append(f"doctor detail: {state['doctor_error']}")
        lines.append(f"components: {','.join(components) if components else '(none recorded)'}")
        paths = [
            ("solar_home", solar_home, True),
            ("claude_solar", claude_dir / "solar", True),
            ("receipt", receipt_path, False),
            ("db", Path(state["receipt"].get("db") or solar_home / "db" / "solar.db"), False),
            ("kernel", claude_dir / "solar" / "SOLAR.md", False),
            ("solar_bin", state["solar_bin"], False),
        ]
        for name, path, want_dir in paths:
            lines.append(f"{name}: {status_word(style, path_status(path, want_dir))} {path}")
    lines.append("")

    lines.append("[Harness readiness]")
    if not harness_bin.exists():
        lines.append("status: harness not installed")
        lines.append("remedy: install with --components kernel,harness")
    else:
        preflight: CmdResult = state["preflight"]
        preflight_status = "ok" if preflight.rc == 0 else "preflight-failed"
        lines.append(f"status: {status_word(style, preflight_status)}")
        lines.append(f"harness_bin: {harness_bin}")
    lines.append("required deps:")
    for name, status, detail in state["deps"]:
        rendered = status_word(style, status)
        label = "install hint" if status == "missing" else "path"
        lines.append(f"  {name}: {rendered} ({label}: {detail})")
    if harness_bin.exists():
        lines.append("preflight output:")
        preflight_text = (state["preflight"].out + state["preflight"].err).strip()
        for line in preflight_text.splitlines()[:14]:
            lines.append(f"  {line}")
        if not preflight_text:
            lines.append("  (no output)")
    lines.append("")

    runtime = state["runtime"]
    lines.append("[Runtime status]")
    if not harness_dir.exists():
        lines.append("harness runtime: not installed")
    else:
        tmux_status = "present" if runtime["session_present"] else "absent"
        lines.append(f"tmux Product Delivery session: {status_word(style, tmux_status)} ({SESSION_NAME})")
        lab_status = "present" if runtime["lab_present"] else "absent"
        lines.append(f"tmux Builder Lab session: {status_word(style, lab_status)} ({LAB_SESSION_NAME})")
        if runtime["windows"]:
            lines.append("windows:")
            for line in runtime["windows"][:4]:
                lines.append(f"  {line}")
        if runtime["panes"]:
            lines.append("panes:")
            for line in runtime["panes"][:6]:
                lines.append(f"  {line}")
        if not runtime["tmux_path"]:
            lines.append("tmux: missing; runtime pane status unavailable")
        lines.append(f"coordinator: {status_word(style, runtime['coordinator'])}")
        if runtime["recent"]:
            lines.append("recent dispatch/operator artifacts:")
            for path in runtime["recent"]:
                try:
                    rel = path.relative_to(harness_dir)
                except ValueError:
                    rel = path
                lines.append(f"  {rel}")
        else:
            lines.append("recent dispatch/operator artifacts: none found")
    lines.append("")

    live_status, live_detail = classify_live_boundary(
        runtime["captured_text"],
        bool(runtime["session_present"]),
        runtime_name,
    )
    lines.append("[Manual boundary]")
    lines.append(f"live {runtime_name} status: {status_word(style, live_status)}")
    lines.append(f"detail: {live_detail}")
    lines.append("scope: deterministic install/layout/preflight/runtime plumbing only")
    lines.append(
        f"not verified here: live {runtime_name} panes, real delegation, "
        f"real {runtime_name}-generated results"
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a read-only Solar UI-lite terminal dashboard.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="render once and exit")
    mode.add_argument("--watch", type=float, metavar="N", help="refresh every N seconds")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI color")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.watch is not None and args.watch <= 0:
        parser.error("--watch must be greater than 0")

    style = Style(enabled=(not args.no_color and sys.stdout.isatty()))
    interval = args.watch
    once = args.once or interval is None
    while True:
        state = collect_state()
        if interval is not None and sys.stdout.isatty() and not args.no_color:
            sys.stdout.write("\033[2J\033[H")
        elif not once:
            sys.stdout.write("\n--- refresh ---\n")
        sys.stdout.write(render(state, style))
        sys.stdout.flush()
        if once:
            return 0
        try:
            time.sleep(float(interval))
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    raise SystemExit(main(sys.argv[1:]))
