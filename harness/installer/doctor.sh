#!/usr/bin/env bash
# ============================================================================
# Solar Product Platform — Product Doctor (installer level)
#
# Output (--json, default):
#   Design §2.2 schema: ts, os, bins, paths, services, secrets, skills, verdict
#
# Usage:
#   doctor.sh                    # JSON output (default)
#   doctor.sh --json             # explicit JSON
#   doctor.sh --summary          # human-readable summary
#
# STOP: NEVER prints real secret values in output.
#       Verdict must be "ok" on clean install with fake keys.
# ============================================================================
set -euo pipefail

SOLAR_HOME="${SOLAR_HOME:-$HOME/.solar}"
HARNESS_DIR="${HARNESS_DIR:-$SOLAR_HOME/harness}"
KNOWLEDGE_VAULT="${KNOWLEDGE_VAULT:-$HOME/Knowledge}"

# ── JSON mode (default) ────────────────────────────────────────────────────
doctor_json() {
  python3 << 'PYEOF'
import json, os, subprocess, platform, sys
from datetime import datetime, timezone

HARNESS_DIR = os.environ.get("HARNESS_DIR", os.path.expanduser("~/.solar/harness"))
KNOWLEDGE_VAULT = os.environ.get("KNOWLEDGE_VAULT", os.path.expanduser("~/Knowledge"))
SOLAR_HOME = os.environ.get("SOLAR_HOME", os.path.expanduser("~/.solar"))

result = {
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "os": {"kind": "", "version": ""},
    "bins": {},
    "paths": {},
    "services": {},
    "secrets": {},
    "skills": {"builtins_count": 0, "registry_drift": 0},
    "verdict": "ok",
    "warnings": []
}

# ── os ──────────────────────────────────────────────────────────────────
result["os"]["kind"] = "darwin" if platform.system() == "Darwin" else "linux"
try:
    if result["os"]["kind"] == "darwin":
        r = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True, timeout=5)
        result["os"]["version"] = r.stdout.strip()
    else:
        import platform as pf
        result["os"]["version"] = pf.release()
except Exception:
    result["os"]["version"] = "unknown"

# ── bins ────────────────────────────────────────────────────────────────
bins = {
    "bash": ["bash", "--version"],
    "python3": ["python3", "--version"],
    "git": ["git", "--version"],
    "bun": ["bun", "--version"],
    "tmux": ["tmux", "-V"],
    "curl": ["curl", "--version"],
    "tar": ["tar", "--version"],
    "jq": ["jq", "--version"],
    "sqlite3": ["sqlite3", "--version"],
    "claude": ["claude", "--version"],
    "codex": ["codex", "--version"],
    "gitleaks": ["gitleaks", "version"],
}

for name, cmd in bins.items():
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        result["bins"][name] = "ok" if r.returncode in (0, 1) else "missing"
    except FileNotFoundError:
        result["bins"][name] = "missing"
    except Exception:
        result["bins"][name] = "missing"

# ── paths ───────────────────────────────────────────────────────────────
paths = {
    "~/.solar": os.path.expanduser("~/.solar"),
    "~/.solar/harness": HARNESS_DIR,
    "~/Knowledge": os.path.expanduser(KNOWLEDGE_VAULT),
    "~/.solar/harness/config": os.path.join(HARNESS_DIR, "config"),
    "~/.solar/harness/backups": os.path.join(HARNESS_DIR, "backups"),
    "~/.solar/harness/run": os.path.join(HARNESS_DIR, "run"),
    "~/.solar/harness/lib": os.path.join(HARNESS_DIR, "lib"),
    "~/.solar/harness/lib/tvs_render_cli.ts": os.path.join(HARNESS_DIR, "lib", "tvs_render_cli.ts"),
    "~/.solar/harness/installer": os.path.join(HARNESS_DIR, "installer"),
}

for label, p in paths.items():
    if os.path.isdir(p):
        result["paths"][label] = "ok"
    elif os.path.exists(p):
        result["paths"][label] = "ok"
    else:
        result["paths"][label] = "missing"
        result["warnings"].append(f"path missing: {label} ({p})")

# ── services ────────────────────────────────────────────────────────────
services = {}

# harness (check pidfiles)
coord_pidfile = os.path.join(HARNESS_DIR, ".coordinator.pid")
if os.path.isfile(coord_pidfile):
    try:
        pid = int(open(coord_pidfile).read().strip())
        os.kill(pid, 0)
        services["harness"] = "running"
    except (ValueError, ProcessLookupError, PermissionError):
        services["harness"] = "stopped"
else:
    services["harness"] = "stopped"

# qmd-mcp
qmd_pidfile = os.path.join(HARNESS_DIR, "run", "qmd-mcp-ipv4-proxy.pid")
if os.path.isfile(qmd_pidfile):
    try:
        pid = int(open(qmd_pidfile).read().strip())
        os.kill(pid, 0)
        services["qmd-mcp"] = {"status": "running"}
    except Exception:
        services["qmd-mcp"] = {"status": "stopped"}
else:
    services["qmd-mcp"] = {"status": "stopped"}

# status-server
ss_pidfile = os.path.join(HARNESS_DIR, "run", "status-server.pid")
if os.path.isfile(ss_pidfile):
    try:
        pid = int(open(ss_pidfile).read().strip())
        os.kill(pid, 0)
        services["status-server"] = {"status": "running"}
    except Exception:
        services["status-server"] = {"status": "stopped"}
else:
    services["status-server"] = {"status": "stopped"}

# mineru (launchd check on macOS)
if result["os"]["kind"] == "darwin":
    try:
        r = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=5
        )
        if "solar.mineru" in r.stdout:
            services["mineru"] = {"status": "running"}
        else:
            services["mineru"] = {"status": "stopped"}
    except Exception:
        services["mineru"] = {"status": "unknown"}
else:
    services["mineru"] = {"status": "not_applicable"}

result["services"] = services

# ── TVS renderer integration ─────────────────────────────────────────────
def resolve_tvs_root():
    explicit = os.environ.get("SOLAR_TVS_ROOT")
    if explicit:
        path = os.path.abspath(os.path.expanduser(explicit))
        return path if os.path.isfile(os.path.join(path, "index.ts")) else ""

    candidates = [
        os.path.join(HARNESS_DIR, "..", "..", "TVS"),
        os.path.expanduser("~/TVS"),
        os.path.expanduser("~/Solar/../TVS"),
    ]
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        path = os.path.abspath(os.path.expanduser(candidate))
        if path in seen:
            continue
        seen.add(path)
        if os.path.isfile(os.path.join(path, "index.ts")):
            return path
    return ""

tvs_root = resolve_tvs_root()
tvs_cli = os.path.join(HARNESS_DIR, "lib", "tvs_render_cli.ts")
tvs_result = {
    "status": "missing",
    "optional": True,
    "bun": result["bins"].get("bun", "missing"),
    "cli": "ok" if os.path.isfile(tvs_cli) else "missing",
    "root": "ok" if tvs_root else "missing",
    "root_path": tvs_root or "",
    "smoke": "not_run",
}

if tvs_result["cli"] == "missing":
    tvs_result["status"] = "optional_missing"
    result["warnings"].append("optional tvs renderer bridge missing: lib/tvs_render_cli.ts")
elif tvs_result["bun"] == "missing":
    tvs_result["status"] = "optional_missing"
    result["warnings"].append("optional tvs renderer dependency missing: bun")
elif tvs_result["root"] == "missing":
    tvs_result["status"] = "optional_missing"
    result["warnings"].append("optional tvs renderer root missing; set SOLAR_TVS_ROOT to enable")
else:
    payload = json.dumps({
        "canvas": {"width": 40},
        "style": "solar_default",
        "root": {
            "type": "card",
            "header": "TVS Doctor",
            "sections": [{"type": "kv", "items": [{"key": "Status", "value": "ok"}]}],
        },
    })
    try:
        env = dict(os.environ)
        env["HARNESS_DIR"] = HARNESS_DIR
        env["SOLAR_TVS_ROOT"] = tvs_root
        r = subprocess.run(
            ["bun", "run", tvs_cli, "render", "--width", "40", "--colors", "off"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if r.returncode == 0 and "TVS Doctor" in r.stdout and "Powered by TVS" in r.stdout:
            tvs_result["status"] = "ok"
            tvs_result["smoke"] = "ok"
        else:
            tvs_result["status"] = "degraded"
            tvs_result["smoke"] = "failed"
            result["warnings"].append("tvs renderer smoke failed")
    except Exception:
        tvs_result["status"] = "degraded"
        tvs_result["smoke"] = "failed"
        result["warnings"].append("tvs renderer smoke failed")

result["services"]["tvs_renderer"] = tvs_result

# ── secrets (configured/missing — NEVER print values) ───────────────────
env_keys = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_AI_API_KEY",
    "zai": "ZAI_API_KEY",
}
for provider, env_var in env_keys.items():
    result["secrets"][provider] = "configured" if os.environ.get(env_var) else "missing"

# Check .env file
env_file = os.path.join(HARNESS_DIR, ".env")
result["secrets"]["env_file"] = "present" if os.path.isfile(env_file) else "missing"

# ── skills ──────────────────────────────────────────────────────────────
registry_path = os.path.join(HARNESS_DIR, "skills", "registry.yaml")
if os.path.isfile(registry_path):
    try:
        import yaml
        with open(registry_path) as f:
            reg = yaml.safe_load(f) or {}
        skills_list = reg.get("skills", [])
        result["skills"]["builtins_count"] = len(skills_list)
        result["skills"]["registry_drift"] = 0
    except Exception:
        result["skills"]["builtins_count"] = 0
        result["skills"]["registry_drift"] = 0
        result["warnings"].append("skills/registry.yaml unreadable")
else:
    result["skills"]["builtins_count"] = 0
    result["skills"]["registry_drift"] = 0

# ── config checks ───────────────────────────────────────────────────────
config_file = os.path.join(HARNESS_DIR, "config", "defaults.yaml")
result["paths"]["config/defaults.yaml"] = "ok" if os.path.isfile(config_file) else "missing"

env_example = os.path.join(HARNESS_DIR, ".env.example")
result["paths"][".env.example"] = "ok" if os.path.isfile(env_example) else "missing"

gitleaks_config = os.path.join(HARNESS_DIR, "gitleaks.toml")
result["paths"]["gitleaks.toml"] = "ok" if os.path.isfile(gitleaks_config) else "missing"

# ── state DB ────────────────────────────────────────────────────────────
state_db = os.path.join(HARNESS_DIR, "run", "state.db")
if os.path.isfile(state_db):
    try:
        import sqlite3
        conn = sqlite3.connect(state_db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        result["services"]["state_db"] = {"status": "ok", "tables": tables}
        conn.close()
    except Exception:
        result["services"]["state_db"] = {"status": "degraded"}
else:
    result["services"]["state_db"] = {"status": "missing"}

# ── verdict ─────────────────────────────────────────────────────────────
critical_paths = [
    result["paths"].get("~/.solar/harness"),
    result["paths"].get("~/.solar/harness/config"),
    result["paths"].get("~/.solar/harness/lib"),
    result["paths"].get("config/defaults.yaml"),
]
critical_bins = [
    result["bins"].get("bash"),
    result["bins"].get("python3"),
    result["bins"].get("git"),
]

if any(v == "missing" for v in critical_paths) or any(v == "missing" for v in critical_bins):
    result["verdict"] = "fail"
elif len(result["warnings"]) > 3:
    result["verdict"] = "degraded"
else:
    result["verdict"] = "ok"

print(json.dumps(result, indent=2, ensure_ascii=False))
PYEOF
}

# ── Summary mode ──────────────────────────────────────────────────────────
doctor_summary() {
  local json_output
  json_output=$(doctor_json)

  local verdict os_kind os_ver bins_ok bins_total paths_ok paths_total
  verdict=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)
  os_kind=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin)['os']['kind'])" 2>/dev/null)
  os_ver=$(echo "$json_output" | python3 -c "import json,sys; print(json.load(sys.stdin)['os']['version'])" 2>/dev/null)

  echo ""
  echo "  ┌─ Product Doctor ───────────────────────────┐"
  echo "  │  OS:        $os_kind $os_ver"
  echo "  │  Verdict:   $verdict"

  # bins summary
  echo "$json_output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
bins = d.get('bins', {})
ok = sum(1 for v in bins.values() if v == 'ok')
total = len(bins)
print(f'  │  Bins:      {ok}/{total} ok')
" 2>/dev/null

  # paths summary
  echo "$json_output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
paths = d.get('paths', {})
ok = sum(1 for v in paths.values() if v == 'ok')
total = len(paths)
print(f'  │  Paths:     {ok}/{total} ok')
" 2>/dev/null

  # TVS renderer summary
  echo "$json_output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
tvs = d.get('services', {}).get('tvs_renderer', {})
print(f\"  │  TVS:       {tvs.get('status', 'N/A')} bun={tvs.get('bun', 'N/A')} root={tvs.get('root', 'N/A')} smoke={tvs.get('smoke', 'N/A')}\")
" 2>/dev/null

  # secrets summary
  echo "$json_output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
secrets = d.get('secrets', {})
for k, v in secrets.items():
    if k != 'env_file':
        print(f'  │  {k}:   {v}')
" 2>/dev/null

  echo "  └──────────────────────────────────────────────┘"

  # warnings
  local warns
  warns=$(echo "$json_output" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('warnings',[])))" 2>/dev/null)
  if [[ "$warns" != "0" ]]; then
    echo "$json_output" | python3 -c "
import json, sys
for w in json.load(sys.stdin).get('warnings', []):
    print(f'  ⚠  {w}')
" 2>/dev/null
  fi
  echo ""
}

# ── entry ─────────────────────────────────────────────────────────────────
# Exit nonzero unless the verdict is "ok", so callers can branch on the exit
# code (matches `solar doctor`). Output is unchanged.
doctor_exit_for() {
  _verdict="$(printf '%s' "$1" | python3 -c \
    "import json,sys
try: print(json.load(sys.stdin).get('verdict','fail'))
except Exception: print('fail')" 2>/dev/null || echo fail)"
  [ "$_verdict" = "ok" ] || exit 1
}

case "${1:-}" in
  --json|"")
    _out="$(doctor_json)"
    printf '%s\n' "$_out"
    doctor_exit_for "$_out"
    ;;
  --summary|-s)
    doctor_summary
    doctor_exit_for "$(doctor_json)"
    ;;
  --help|-h)
    echo "Solar Product Doctor — Design §2.2 schema"
    echo ""
    echo "Usage:"
    echo "  installer/doctor.sh            JSON output (default)"
    echo "  installer/doctor.sh --summary  Human-readable summary"
    echo ""
    echo "Schema: ts, os, bins, paths, services, secrets, skills, verdict"
    echo "Verdict: ok | degraded | fail"
    ;;
  *)
    echo "Unknown option: $1" >&2
    exit 1
    ;;
esac
