#!/usr/bin/env bash
# ================================================================
# Solar Harness — Doctor (纯只读健康诊断)
#
# 输出 JSON 含: tmux_session_alive, coordinator_*, watchdog_*,
#   bash_version, bash_path, panes[], warnings[], repairs_available[]
#
# --summary: 人类可读摘要 (用于启动首屏)
#
# @module solar-farm/harness/doctor
# ================================================================
set -eu

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
export HARNESS_DIR
SESSION_NAME="solar-harness"
LAB_SESSION_NAME="solar-harness-lab"

# --- JSON 模式 (默认) ---
doctor_json() {
  python3 << 'PYEOF'
import json, subprocess, os, re, shutil, sys
from pathlib import Path

SESSION_NAME = "solar-harness"
LAB_SESSION_NAME = "solar-harness-lab"
HARNESS_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or "~/.solar/harness"
))
sys.path.insert(0, os.path.join(HARNESS_DIR, "lib"))
try:
    from qmd_resolver import resolve_qmd_bin
except Exception:
    def resolve_qmd_bin():
        return ""

result = {
    "tmux_session_alive": False,
    "lab_session_alive": False,
    "coordinator_pid": 0,
    "coordinator_alive": False,
    "watchdog_pid": 0,
    "watchdog_alive": False,
    "bash_version": "",
    "bash_path": "",
    "bash_major": 0,
    "panes": [],
    "warnings": [],
    "required_checks": [],
    "manual_checks": [],
    "optional_checks": [],
    "repairs_available": [],
    "qmd": {
        "resolver": "",
        "stripped_path_ok": False,
        "stripped_status_ok": False,
        "status_ok": False,
        "vectors": "",
        "pending": "",
        "repair_status": "",
        "repair_action": ""
    },
    "gateway_compat": {
        "checked": False,
        "ok": False,
        "script": os.path.join(HARNESS_DIR, "test-gateway-compat.sh")
    },
    "task_graph_gate_audit": {
        "present": False,
        "status": "missing",
        "summary": "N/A",
        "graphs_changed": 0,
        "graphs_unresolved": 0,
        "generated_at": "",
        "report_path": "",
        "markdown_report_path": ""
    },
}

def command_path(name):
    return shutil.which(name) or ""

def add_check(bucket, name, status, detail="", hint=""):
    result[bucket].append({
        "name": name,
        "status": status,
        "detail": detail,
        "hint": hint,
    })

def run_quiet(args, timeout=5, env=None):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)

def classify_claude_tail(text):
    if re.search(r"You(?:'|’)ve hit .*limit|rate[- ]limit|quota exhausted|RESOURCE_EXHAUSTED|429|/rate-limit-options|Upgrade your plan", text, re.I):
        return "auth_or_quota_blocked"
    if re.search(r"trust|trusted|Do you trust|permission|auth|login|Press Enter|press enter", text, re.I):
        return "manual_pending"
    return "manual_pending"

layout_personas = {}
layout_path = os.path.join(HARNESS_DIR, "farm-layout.json")
if os.path.isfile(layout_path):
    try:
        layout = json.load(open(layout_path))
        default_session = layout.get("session_name", SESSION_NAME)
        for w in layout.get("windows", []):
            session = w.get("session") or default_session
            win = w.get("index", 0)
            for p in w.get("panes", []):
                target = f"{session}:{win}.{p.get('pane_index')}"
                layout_personas[target] = p.get("persona") or p.get("role") or ""
    except Exception:
        pass

required_hints = {
    "python3": "macOS: brew install python; Ubuntu/Debian: sudo apt-get install python3",
    "tmux": "macOS: brew install tmux; Ubuntu/Debian: sudo apt-get install tmux",
    "claude": "Install the Claude Code CLI and confirm 'claude --version' works before launching panes",
    "jq": "macOS: brew install jq; Ubuntu/Debian: sudo apt-get install jq",
}

# bash version
bash_candidates = [
    "/opt/homebrew/bin/bash",
    "/usr/local/bin/bash",
    command_path("bash"),
    "/bin/bash",
]
seen_bash = set()
for b in bash_candidates:
    if not b or b in seen_bash:
        continue
    seen_bash.add(b)
    if os.path.isfile(b):
        try:
            r = run_quiet([b, "--version"])
            if r.returncode == 0:
                version_line = r.stdout.split("\n")[0]
                major_match = re.search(r"version\s+([0-9]+)", version_line)
                major = int(major_match.group(1)) if major_match else 0
                if major >= 4 or not result["bash_path"]:
                    result["bash_version"] = version_line
                    result["bash_path"] = b
                    result["bash_major"] = major
                if major >= 4:
                    break
        except Exception:
            pass

if result["bash_major"] >= 4:
    add_check("required_checks", "bash>=4", "ok", f"{result['bash_path']} ({result['bash_version']})")
else:
    detail = f"{result['bash_path']} ({result['bash_version']})" if result["bash_path"] else "not found"
    add_check("required_checks", "bash>=4", "fail", detail, "macOS: brew install bash; Ubuntu/Debian: sudo apt-get install bash")

for cmd in ["python3", "tmux", "claude", "jq"]:
    path = command_path(cmd)
    if path:
        add_check("required_checks", cmd, "ok", path)
    else:
        add_check("required_checks", cmd, "fail", "not found on PATH", required_hints[cmd])

if os.access(HARNESS_DIR, os.W_OK):
    add_check("required_checks", "harness_dir_writable", "ok", HARNESS_DIR)
else:
    add_check("required_checks", "harness_dir_writable", "fail", HARNESS_DIR, f"fix ownership/permissions for {HARNESS_DIR}; do not run Solar as root")

# tmux sessions
tmux_path = command_path("tmux")
if tmux_path:
    for key, session in [("tmux_session_alive", SESSION_NAME), ("lab_session_alive", LAB_SESSION_NAME)]:
        r = run_quiet(["tmux", "has-session", "-t", session])
        result[key] = (r.returncode == 0)
else:
    result["warnings"].append("tmux unavailable; session status not checked")

if result["tmux_session_alive"]:
    add_check("required_checks", "product_delivery_session", "ok", SESSION_NAME)
else:
    add_check("required_checks", "product_delivery_session", "fail", f"{SESSION_NAME} not running", "run: solar-harness start <workdir>")

if result["lab_session_alive"]:
    add_check("optional_checks", "builder_lab_session", "ok", LAB_SESSION_NAME)
else:
    add_check("optional_checks", "builder_lab_session", "optional_warning", f"{LAB_SESSION_NAME} not running", "optional: run solar-harness 扩展 <workdir> when you need the lab")

# coordinator pid
pidfile = os.path.join(HARNESS_DIR, ".coordinator.pid")
if os.path.isfile(pidfile):
    try:
        pid = int(open(pidfile).read().strip())
        result["coordinator_pid"] = pid
        os.kill(pid, 0)
        result["coordinator_alive"] = True
    except (ValueError, ProcessLookupError):
        result["warnings"].append(f"coordinator pidfile stale: {pidfile}")
    except PermissionError:
        result["coordinator_alive"] = True
if result["coordinator_alive"]:
    add_check("required_checks", "coordinator", "ok", f"pid={result['coordinator_pid']}")
elif result["tmux_session_alive"]:
    add_check("required_checks", "coordinator", "fail", "not alive", "run: solar-harness wake or restart solar-harness")
else:
    add_check("manual_checks", "coordinator", "manual_pending", "not expected until Product Delivery is started")

# watchdog pid
wpidfile = os.path.join(HARNESS_DIR, ".watchdog.pid")
if os.path.isfile(wpidfile):
    try:
        wpid = int(open(wpidfile).read().strip())
        result["watchdog_pid"] = wpid
        os.kill(wpid, 0)
        result["watchdog_alive"] = True
    except (ValueError, ProcessLookupError):
        result["warnings"].append(f"watchdog pidfile stale: {wpidfile}")
    except PermissionError:
        result["watchdog_alive"] = True
if result["watchdog_alive"]:
    add_check("optional_checks", "watchdog", "ok", f"pid={result['watchdog_pid']}")
else:
    add_check("optional_checks", "watchdog", "optional_warning", "not alive", "watchdog is resilience only; Product Delivery can be manually verified without it")

def scan_session(session):
    panes = []
    try:
        r = subprocess.run(
            ["tmux", "list-panes", "-t", session, "-F",
             "#{session_name}\t#{window_index}.#{pane_index}\t#{pane_pid}\t#{pane_current_command}\t#{pane_dead}"],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            pane = {
                "session": parts[0],
                "target": f"{parts[0]}:{parts[1]}",
                "index": parts[1],
                "pid": int(parts[2]),
                "cmd": parts[3],
                "alive": parts[4] != "1",
                "last_activity_ts": "",
                "persona": "",
                "persona_source": "",
                "layout_persona": layout_personas.get(f"{parts[0]}:{parts[1]}", ""),
                "claude_alive": False,
                "claude_state": "unknown"
            }
            # Prefer the launch wrapper argv. Pane scrollback can lose the
            # Persona header after long conversations; argv remains reliable.
            try:
                queue = [pane["pid"]]
                seen = set()
                while queue:
                    pid = queue.pop(0)
                    if pid in seen:
                        continue
                    seen.add(pid)
                    args = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "args="],
                        capture_output=True, text=True, timeout=2
                    ).stdout.strip()
                    if re.search(r"(^|/)(claude|claude\.exe)(\s|$)", args):
                        pane["claude_alive"] = True
                    m = re.search(r"start-(?:incarnation|launcher)\.sh\s+([A-Za-z0-9_-]+)", args)
                    if m and not pane["persona"]:
                        pane["persona"] = m.group(1)
                        pane["persona_source"] = "process"
                    kids = subprocess.run(
                        ["pgrep", "-P", str(pid)],
                        capture_output=True, text=True, timeout=2
                    ).stdout.strip().splitlines()
                    queue.extend(int(k) for k in kids if k.strip().isdigit())
            except Exception:
                pass
            # detect persona from pane content
            if not pane["persona"]:
                try:
                    content = run_quiet(
                        ["tmux", "capture-pane", "-t",
                         pane["target"], "-p", "-S", "-80"],
                    ).stdout
                    matches = re.findall(r"Persona:\s*([A-Za-z0-9_-]+)", content)
                    if matches:
                        pane["persona"] = matches[-1]
                        pane["persona_source"] = "scrollback"
                except Exception:
                    pass
            if not pane["persona"]:
                pane["persona"] = pane["layout_persona"]
                pane["persona_source"] = "layout" if pane["persona"] else ""
            try:
                tail = run_quiet(["tmux", "capture-pane", "-t", pane["target"], "-p", "-S", "-80"]).stdout
            except Exception:
                tail = ""
            if pane["claude_alive"]:
                pane["claude_state"] = "live_child_present"
            else:
                pane["claude_state"] = classify_claude_tail(tail)
            panes.append(pane)
    except Exception as e:
        result["warnings"].append(f"pane scan failed for {session}: {e}")
    return panes

# panes
if result["tmux_session_alive"]:
    result["panes"].extend(scan_session(SESSION_NAME))
if result["lab_session_alive"]:
    result["panes"].extend(scan_session(LAB_SESSION_NAME))

# dead pane warnings
for p in result["panes"]:
    if not p["alive"]:
        result["warnings"].append(f"pane {p.get('target', p.get('index'))} is dead (persona={p.get('persona','?')})")
    layout_persona = p.get("layout_persona", "")
    actual_persona = p.get("persona", "")
    if layout_persona and actual_persona and layout_persona != actual_persona:
        result["warnings"].append(
            f"pane {p['target']} persona mismatch: layout={layout_persona}, actual={actual_persona}, source={p.get('persona_source','?')}"
        )
    if layout_persona and not p.get("claude_alive"):
        state = p.get("claude_state") or "manual_pending"
        add_check(
            "manual_checks",
            f"pane {p['target']} claude",
            state,
            f"layout={layout_persona}, actual={actual_persona or '?'}",
            "press Enter in the pane and resolve Claude trust/auth/quota prompts",
        )
    elif layout_persona and p.get("claude_alive"):
        add_check(
            "manual_checks",
            f"pane {p['target']} claude",
            "live_child_present",
            f"layout={layout_persona}, actual={actual_persona or '?'}",
            "child process is present; real Claude response/delegation still requires owner manual verification",
        )

# repairs available
if os.path.isfile(pidfile) and not result["coordinator_alive"]:
    result["repairs_available"].append("coordinator-down: run solar-harness wake")
if os.path.isfile(wpidfile) and not result["watchdog_alive"]:
    result["repairs_available"].append("watchdog-down: run watchdog start")

# qmd resolver / launcher health. This is deliberately stripped-PATH tested so
# launchd and ssh non-interactive environments do not regress silently.
qmd_resolver_script = os.path.join(HARNESS_DIR, "lib", "qmd-resolver.sh")
if os.path.isfile(qmd_resolver_script):
    try:
        env = {
            "HOME": os.path.expanduser("~"),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HARNESS_DIR": HARNESS_DIR,
        }
        if os.environ.get("QMD_BIN"):
            env["QMD_BIN"] = os.environ["QMD_BIN"]
        r = subprocess.run(
            ["bash", qmd_resolver_script, "--print"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        if r.returncode == 0 and r.stdout.strip():
            result["qmd"]["resolver"] = r.stdout.strip().splitlines()[0]
            result["qmd"]["stripped_path_ok"] = True
        h = subprocess.run(
            ["bash", os.path.join(HARNESS_DIR, "solar-harness.sh"), "wiki", "qmd-status"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        result["qmd"]["stripped_status_ok"] = (h.returncode == 0)
        if h.returncode != 0:
            add_check("optional_checks", "qmd_stripped_path_status", "optional_warning", "qmd stripped-PATH status check failed", "install qmd/mineru-document-explorer or set QMD_BIN when using wiki/QMD features")
    except Exception as e:
        add_check("optional_checks", "qmd_stripped_path_resolver", "optional_warning", f"qmd stripped-PATH resolver check failed: {e}", "optional for core harness")

if not result["qmd"]["resolver"]:
    qmd_bin = resolve_qmd_bin()
    result["qmd"]["resolver"] = qmd_bin
else:
    qmd_bin = result["qmd"]["resolver"]

if qmd_bin:
    try:
        r = subprocess.run([qmd_bin, "status"], capture_output=True, text=True, timeout=12)
        result["qmd"]["status_ok"] = (r.returncode == 0)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                s = line.strip()
                if s.startswith("Vectors:"):
                    result["qmd"]["vectors"] = s.split(":", 1)[1].strip()
                elif s.startswith("Pending:"):
                    result["qmd"]["pending"] = s.split(":", 1)[1].strip()
        else:
            add_check("optional_checks", "qmd_status", "optional_warning", "qmd status failed", "optional for core harness")
    except Exception as e:
        add_check("optional_checks", "qmd_status", "optional_warning", f"qmd status failed: {e}", "optional for core harness")
else:
    add_check("optional_checks", "qmd", "optional_warning", "qmd resolver found no executable", "optional for core harness; install qmd/mineru-document-explorer when using wiki/QMD features")

qmd_repair = os.path.join(HARNESS_DIR, "lib", "qmd-launcher-repair.sh")
if os.path.isfile(qmd_repair) and os.access(qmd_repair, os.X_OK):
    try:
        r = subprocess.run([qmd_repair, "--check", "--json"], capture_output=True, text=True, timeout=15)
        if r.stdout.strip():
            d = json.loads(r.stdout.strip().splitlines()[-1])
            result["qmd"]["repair_status"] = d.get("status", "")
            result["qmd"]["repair_action"] = d.get("action", "")
        if r.returncode == 2:
            result["repairs_available"].append("qmd-launcher-abi: run solar-harness wiki qmd-repair --apply")
        elif r.returncode not in (0,):
            add_check("optional_checks", "qmd_launcher_repair", "optional_warning", "qmd launcher repair check failed", "optional for core harness")
    except Exception as e:
        add_check("optional_checks", "qmd_launcher_repair", "optional_warning", f"qmd launcher repair check failed: {e}", "optional for core harness")

# symphony section
symphony_dir = os.path.join(HARNESS_DIR, "lib", "symphony")
scheduler_path = os.path.join(symphony_dir, "scheduler.py")
state_dir = os.path.join(HARNESS_DIR, "state", "symphony")
symphony = {
    "installed": os.path.isfile(scheduler_path),
    "workspace_root": "",
    "claimed": 0,
    "running": 0,
    "retry": 0,
    "repairs_available": []
}
if symphony["installed"]:
    # Resolve workspace root
    try:
        ws_r = subprocess.run(
            ["bash", os.path.join(symphony_dir, "workspace-manager.sh"), "root"],
            capture_output=True, text=True, timeout=5
        )
        symphony["workspace_root"] = ws_r.stdout.strip()
    except Exception:
        pass
    # Count state files
    for sub in ["claimed", "running", "retry", "completed"]:
        sub_dir = os.path.join(state_dir, sub)
        if os.path.isdir(sub_dir):
            count = len([f for f in os.listdir(sub_dir) if f.endswith(".json")])
            symphony[sub] = count
    # Check for stale claimed
    claimed_dir = os.path.join(state_dir, "claimed")
    if os.path.isdir(claimed_dir):
        for f in os.listdir(claimed_dir):
            if not f.endswith(".json"):
                continue
            try:
                d = json.load(open(os.path.join(claimed_dir, f)))
                claimed_at = d.get("claimed_at", "")
                if claimed_at:
                    from datetime import datetime, timezone
                    claimed_time = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - claimed_time).total_seconds() / 3600
                    if age_hours > 1:
                        symphony["repairs_available"].append(f"stale-claimed: {d.get('sprint_id', '?')} claimed {age_hours:.1f}h ago")
            except Exception:
                pass
result["symphony"] = symphony

# Third-party Anthropic-compatible gateway guard. This is read-only and catches
# regressions where z.ai/DeepSeek panes would launch with the full MCP payload.
gateway_script = result["gateway_compat"]["script"]
if os.path.isfile(gateway_script):
    try:
        r = subprocess.run(
            ["bash", gateway_script],
            capture_output=True, text=True, timeout=15
        )
        result["gateway_compat"]["checked"] = True
        result["gateway_compat"]["ok"] = (r.returncode == 0)
        if r.returncode != 0:
            add_check("optional_checks", "gateway_compat", "optional_warning", "gateway compatibility check failed", "run test-gateway-compat.sh if using third-party Anthropic-compatible gateways")
        else:
            add_check("optional_checks", "gateway_compat", "ok", "compatible")
    except Exception as e:
        result["gateway_compat"]["checked"] = True
        result["gateway_compat"]["ok"] = False
        add_check("optional_checks", "gateway_compat", "optional_warning", f"gateway compatibility check failed: {e}", "optional for core harness")
else:
    add_check("optional_checks", "gateway_compat", "optional_warning", "gateway compatibility check missing: test-gateway-compat.sh", "optional for core harness")

reports_dir = Path(HARNESS_DIR) / "reports"
audit_reports = sorted(reports_dir.glob("task-graph-gate-backfill-audit-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
if audit_reports:
    latest = audit_reports[0]
    try:
        audit = json.loads(latest.read_text(encoding="utf-8"))
        md_path = str(audit.get("markdown_report") or audit.get("markdown_report_path") or "")
        if not md_path:
            inferred_md = latest.with_suffix(".md")
            if inferred_md.exists():
                md_path = str(inferred_md)
        unresolved = int(audit.get("graphs_unresolved") or 0)
        changed = int(audit.get("graphs_changed") or 0)
        result["task_graph_gate_audit"] = {
            "present": True,
            "status": "warn" if unresolved else "ok",
            "summary": f"{changed} changed / {unresolved} unresolved",
            "graphs_changed": changed,
            "graphs_unresolved": unresolved,
            "generated_at": str(audit.get("generated_at") or ""),
            "report_path": str(latest),
            "markdown_report_path": md_path,
        }
        if unresolved:
            result["warnings"].append(f"task_graph gate audit unresolved: {unresolved} graph(s)")
            result["repairs_available"].append(f"task-graph-gate-audit: inspect {latest}")
    except Exception as e:
        result["warnings"].append(f"task_graph gate audit unreadable: {e}")

print(json.dumps(result, indent=2, ensure_ascii=False))
PYEOF
}

# --- Summary 模式 (人类可读) ---
doctor_summary() {
  local json_output
  # Reuse a JSON sweep the caller already computed (DOCTOR_JSON_CACHE) so the
  # entry point can render the summary and decide the exit code from one sweep
  # instead of running the expensive doctor_json twice.
  json_output="${DOCTOR_JSON_CACHE:-$(doctor_json)}"

  SOLAR_DOCTOR_JSON="$json_output" python3 <<'PY'
import json
import os

d = json.loads(os.environ["SOLAR_DOCTOR_JSON"])

def icon(status):
    return {
        "ok": "OK",
        "fail": "FAIL",
        "manual_pending": "MANUAL-PENDING",
        "auth_or_quota_blocked": "AUTH/QUOTA-BLOCKED",
        "optional_warning": "OPTIONAL-WARN",
        "live_child_present": "LIVE-CHILD-PRESENT",
    }.get(status, status.upper() if status else "UNKNOWN")

required = d.get("required_checks", [])
manual = d.get("manual_checks", [])
optional = d.get("optional_checks", [])
required_fail = [c for c in required if c.get("status") != "ok"]

print("")
print("  ┌─ Harness Runtime Status ─────────────────────────")
print(f"  │ required: {'FAIL' if required_fail else 'OK'}")
for c in required:
    line = f"  │   [{icon(c.get('status'))}] {c.get('name')}: {c.get('detail')}"
    print(line[:140])
    if c.get("status") != "ok" and c.get("hint"):
        print(f"  │      hint: {c.get('hint')}"[:140])

print("  │ manual boundary:")
if manual:
    for c in manual:
        print(f"  │   [{icon(c.get('status'))}] {c.get('name')}: {c.get('detail')}"[:140])
        if c.get("hint"):
            print(f"  │      {c.get('hint')}"[:140])
else:
    print("  │   [MANUAL-PENDING] live Claude panes are not verified until the owner starts Claude and observes a response")

print("  │ optional:")
for c in optional[:12]:
    print(f"  │   [{icon(c.get('status'))}] {c.get('name')}: {c.get('detail')}"[:140])
if len(optional) > 12:
    print(f"  │   ... {len(optional) - 12} more optional checks")

print(f"  │ panes: {len(d.get('panes', []))}")
print(f"  │ task-graph gates: {d.get('task_graph_gate_audit', {}).get('summary', 'N/A')}")
print("  └──────────────────────────────────────────────────")
print("  deterministic status only; real Claude response/delegation remains owner-manual until quota/auth allows it.")

for w in d.get("warnings", []):
    print(f"  warning: {w}")
print("")
PY
}

# Exit nonzero when any REQUIRED check failed, so callers (solar-harness doctor,
# migrate import gate) can branch on the exit code instead of always passing.
# Optional/manual warnings do not change the exit. A malformed JSON body is left
# to the JSON validity of the output, not masked here.
doctor_required_exit() {
  if printf '%s' "$1" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
req = d.get("required_checks", [])
sys.exit(1 if any(c.get("status") != "ok" for c in req) else 0)
'; then
    :
  else
    exit 1
  fi
}

# --- 入口 ---
case "${1:-}" in
  --summary|-s)
    _out="$(doctor_json)"
    DOCTOR_JSON_CACHE="$_out" doctor_summary
    doctor_required_exit "$_out"
    ;;
  --json|"")
    _out="$(doctor_json)"
    printf '%s\n' "$_out"
    doctor_required_exit "$_out"
    ;;
  --help|-h)
    echo "solar-harness doctor — 纯只读健康诊断"
    echo ""
    echo "用法:"
    echo "  solar-harness doctor           输出 JSON"
    echo "  solar-harness doctor --summary 人类可读摘要"
    echo ""
    echo "纯只读，不修改任何状态或重启进程。"
    ;;
  *)
    echo "未知参数: $1" >&2
    exit 2
    ;;
esac
