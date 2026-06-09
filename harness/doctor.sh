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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="${HARNESS_DIR:-$SCRIPT_DIR}"
REPO_DIR="$(cd "$HARNESS_DIR/.." && pwd)"
if [[ -x "$REPO_DIR/.venv/bin/python3" ]]; then
  case ":$PATH:" in
    *":$REPO_DIR/.venv/bin:"*) ;;
    *) export PATH="$REPO_DIR/.venv/bin:$PATH" ;;
  esac
fi
export HARNESS_DIR
SESSION_NAME="solar-harness"
LAB_SESSION_NAME="solar-harness-lab"

# --- JSON 模式 (默认) ---
doctor_json() {
  python3 << 'PYEOF'
import json, subprocess, os, re, sys
from pathlib import Path

SESSION_NAME = "solar-harness"
LAB_SESSION_NAME = "solar-harness-lab"
HARNESS_DIR = os.environ.get("HARNESS_DIR") or os.path.expanduser("~/.solar/harness")
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
    "panes": [],
    "warnings": [],
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

# bash version
for b in [os.environ.get("SOLAR_BASH4", ""), os.environ.get("BASH4", ""), "/opt/homebrew/bin/bash", "/usr/local/bin/bash"]:
    if os.path.isfile(b):
        try:
            r = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                result["bash_version"] = r.stdout.split("\n")[0]
                result["bash_path"] = b
                break
        except Exception:
            pass

# tmux sessions
for key, session in [("tmux_session_alive", SESSION_NAME), ("lab_session_alive", LAB_SESSION_NAME)]:
    r = subprocess.run(["tmux", "has-session", "-t", session],
                       capture_output=True, timeout=5)
    result[key] = (r.returncode == 0)

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
                "runtime_alive": False,
                "runtime_process": ""
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
                    if re.search(r"(^|/)(claude|claude\.exe|codex|codex\.exe)(\s|$)", args):
                        pane["runtime_alive"] = True
                        if re.search(r"(^|/)(codex|codex\.exe)(\s|$)", args):
                            pane["runtime_process"] = "codex"
                        elif re.search(r"(^|/)(claude|claude\.exe)(\s|$)", args):
                            pane["runtime_process"] = "claude"
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
                    content = subprocess.run(
                        ["tmux", "capture-pane", "-t",
                         pane["target"], "-p", "-S", "-80"],
                        capture_output=True, text=True, timeout=5
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
    if layout_persona and not p.get("runtime_alive"):
        result["warnings"].append(
            f"pane {p['target']} has no live solar runtime child (layout={layout_persona}, actual={actual_persona or '?'})"
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
            result["warnings"].append("qmd stripped-PATH status check failed")
    except Exception as e:
        result["warnings"].append(f"qmd stripped-PATH resolver check failed: {e}")

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
            result["warnings"].append("qmd status failed")
    except Exception as e:
        result["warnings"].append(f"qmd status failed: {e}")
else:
    result["warnings"].append("qmd resolver found no executable")

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
            result["warnings"].append("qmd launcher repair check failed")
    except Exception as e:
        result["warnings"].append(f"qmd launcher repair check failed: {e}")

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
            result["warnings"].append("gateway compatibility check failed; run test-gateway-compat.sh")
    except Exception as e:
        result["gateway_compat"]["checked"] = True
        result["gateway_compat"]["ok"] = False
        result["warnings"].append(f"gateway compatibility check failed: {e}")
else:
    result["warnings"].append("gateway compatibility check missing: test-gateway-compat.sh")

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
  json_output=$(doctor_json)

  local tmux_alive lab_alive coord_alive watchdog_alive gateway_ok qmd_ok qmd_pending bash_ver panes_count warnings_count gate_audit_summary
  tmux_alive=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin)['tmux_session_alive'])" 2>/dev/null)
  lab_alive=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin).get('lab_session_alive', False))" 2>/dev/null)
  coord_alive=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin)['coordinator_alive'])" 2>/dev/null)
  watchdog_alive=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin)['watchdog_alive'])" 2>/dev/null)
  gateway_ok=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin).get('gateway_compat',{}).get('ok', False))" 2>/dev/null)
  qmd_ok=$(echo "$json_output" | python3 -c "import json,sys; d=json.load(sys.stdin).get('qmd',{}); print(d.get('stripped_path_ok', False) and d.get('stripped_status_ok', False) and d.get('status_ok', False))" 2>/dev/null)
  qmd_pending=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin).get('qmd',{}).get('pending',''))" 2>/dev/null)
  bash_ver=$(echo "$json_output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bash_version','?'))" 2>/dev/null)
  panes_count=$(echo "$json_output" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['panes']))" 2>/dev/null)
  warnings_count=$(echo "$json_output" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['warnings']))" 2>/dev/null)
  gate_audit_summary=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin).get('task_graph_gate_audit',{}).get('summary','N/A'))" 2>/dev/null)

  echo ""
  echo "  ┌─ Doctor Summary ─────────────────────────┐"
  echo "  │ bash:   ${bash_ver:0:30}"
  echo "  │ tmux:   $([ "$tmux_alive" == "True" ] && echo "✅ alive" || echo "❌ down")"
  echo "  │ lab:    $([ "$lab_alive" == "True" ] && echo "✅ alive" || echo "❌ down")"
  echo "  │ coord:  $([ "$coord_alive" == "True" ] && echo "✅ alive" || echo "❌ down")"
  echo "  │ watch:  $([ "$watchdog_alive" == "True" ] && echo "✅ alive" || echo "❌ down")"
  echo "  │ gateway:$([ "$gateway_ok" == "True" ] && echo " ✅ compat" || echo " ❌ check")"
  echo "  │ qmd:    $([ "$qmd_ok" == "True" ] && echo "✅ resolver" || echo "❌ check") ${qmd_pending:0:22}"
  echo "  │ panes:  ${panes_count}"
  echo "  │ gates:  ${gate_audit_summary:0:30}"
  echo "  │ warns:  ${warnings_count}"
  echo "  └────────────────────────────────────────────┘"

  # Show warnings if any
  if [[ "$warnings_count" != "0" ]]; then
    echo "$json_output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for w in d.get('warnings', []):
    print(f'  ⚠ {w}')
" 2>/dev/null
  fi
  echo ""
}

# --- 入口 ---
case "${1:-}" in
  --summary|-s)
    doctor_summary
    ;;
  --json|"")
    doctor_json
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
    exit 1
    ;;
esac
