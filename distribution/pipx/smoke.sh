#!/usr/bin/env bash
set -euo pipefail

log() { printf '[openjiuwen-solar-pipx-smoke] %s\n' "$*" >&2; }
die() { printf '[openjiuwen-solar-pipx-smoke] error: %s\n' "$*" >&2; exit 1; }

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="${OPENJIUWEN_SOLAR_REPO_ROOT:-}"
if [ -z "$repo_root" ] && git -C "$script_dir" rev-parse --show-toplevel >/dev/null 2>&1; then
    repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
fi
install_target="${OPENJIUWEN_SOLAR_INSTALL_TARGET:-${repo_root:+$repo_root/distribution/pipx}}"
get_solar="${OPENJIUWEN_SOLAR_GET_SOLAR_URL:-${repo_root:+$repo_root/get-solar.sh}}"
smoke_root="${OPENJIUWEN_SOLAR_SMOKE_ROOT:-${OPENSOLAR_SMOKE_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/openjiuwen-solar-pipx-smoke.XXXXXX")}}"

mkdir -p "$smoke_root"
evidence_path="$smoke_root/smoke-evidence.json"
evidence_tmp="$smoke_root/.smoke-evidence.tmp.$$"
rm -f "$evidence_path" "$evidence_tmp"
run_id="$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"
run_root="$smoke_root/.runs/$run_id"
ledger="$run_root/command-ledger.jsonl"
result_status="failed"
failure_step="initialization"
pipx_status="NOT_TESTED"
pipx_reason="pipx availability not evaluated"
opensolar_cmd=""

record_command() {
    label="$1"; rc="$2"; stdout_path="$3"; stderr_path="$4"; shift 4
    python3 - "$ledger" "$run_id" "$label" "$rc" "$stdout_path" "$stderr_path" "$@" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

ledger, run_id, label, rc, stdout_path, stderr_path, *argv = sys.argv[1:]
def digest(path):
    payload = Path(path).read_bytes()
    return hashlib.sha256(payload).hexdigest(), len(payload)
stdout_sha, stdout_bytes = digest(stdout_path)
stderr_sha, stderr_bytes = digest(stderr_path)
row = {
    "run_id": run_id,
    "label": label,
    "argv": argv,
    "exit_code": int(rc),
    "stdout_sha256": stdout_sha,
    "stdout_bytes": stdout_bytes,
    "stderr_sha256": stderr_sha,
    "stderr_bytes": stderr_bytes,
}
with open(ledger, "a", encoding="utf-8") as stream:
    stream.write(json.dumps(row, sort_keys=True) + "\n")
PY
}

record_not_tested() {
    label="$1"; reason="$2"
    python3 - "$ledger" "$run_id" "$label" "$reason" <<'PY'
import json
import sys
with open(sys.argv[1], "a", encoding="utf-8") as stream:
    stream.write(json.dumps({
        "run_id": sys.argv[2],
        "label": sys.argv[3],
        "status": "NOT_TESTED",
        "reason": sys.argv[4],
        "exit_code": None,
    }, sort_keys=True) + "\n")
PY
}

run_step() {
    label="$1"; shift
    failure_step="$label"
    stdout_path="$run_root/logs/$label.stdout"
    stderr_path="$run_root/logs/$label.stderr"
    set +e
    "$@" > >(tee "$stdout_path") 2> >(tee "$stderr_path" >&2)
    rc=$?
    set -e
    record_command "$label" "$rc" "$stdout_path" "$stderr_path" "$@"
    [ "$rc" -eq 0 ] || return "$rc"
}

finalize_evidence() {
    original_rc=$?
    trap - EXIT
    if [ "$result_status" != "passed" ] && [ -n "$opensolar_cmd" ] && [ -x "$opensolar_cmd" ]; then
        "$opensolar_cmd" harness status-server stop >/dev/null 2>&1 || true
    fi
    RESULT_STATUS="$result_status" FAILURE_STEP="$failure_step" RUN_ID="$run_id" \
    PIPX_STATUS="$pipx_status" PIPX_REASON="$pipx_reason" \
    OPENSOLAR_CMD="$opensolar_cmd" \
    python3 - "$ledger" "$evidence_tmp" "$evidence_path" "$smoke_root" "$run_root" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ledger, temp_path, evidence_path, smoke_root, run_root = map(Path, sys.argv[1:])
run_id = os.environ["RUN_ID"]
commands = []
if ledger.is_file():
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("run_id") == run_id:
                commands.append(row)

def successful(label):
    return any(row.get("label") == label and row.get("exit_code") == 0 for row in commands)

doctor_path = run_root / "logs" / "doctor.stdout"
doctor = {}
if successful("doctor") and doctor_path.is_file():
    try:
        doctor = json.loads(doctor_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        doctor = {}
health_path = run_root / "health-response.json"
health = {}
if successful("health") and health_path.is_file():
    try:
        health = json.loads(health_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        health = {}

status = os.environ["RESULT_STATUS"]
opensolar_cmd = Path(os.environ["OPENSOLAR_CMD"]) if os.environ.get("OPENSOLAR_CMD") else None
payload = {
    "schema_version": "opensolar.runtime-deliverable-smoke/v2",
    "run_id": run_id,
    "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": status,
    "failure_step": os.environ["FAILURE_STEP"] if status != "passed" else "",
    "commands": commands,
    "package_manager": {
        "pipx": {
            "status": os.environ["PIPX_STATUS"],
            "reason": os.environ["PIPX_REASON"],
        }
    },
    "observations": {
        "clean_sandbox_install": successful("runtime-install"),
        "doctor_verdict": doctor.get("verdict", "unavailable"),
        "health_http_status": health.get("http_status"),
        "health_body_sha256": health.get("body_sha256", ""),
        "runtime_uninstalled": successful("runtime-uninstall")
        and not (smoke_root / "home" / ".solar").exists()
        and not (smoke_root / "home" / ".claude" / "solar").exists(),
        "wrapper_uninstalled": successful("package-uninstall")
        and opensolar_cmd is not None
        and not opensolar_cmd.exists()
        and not opensolar_cmd.is_symlink(),
        "source_retained_for_rollback": successful("runtime-uninstall") and (smoke_root / "src" / "OpenSolar").is_dir(),
    },
}
temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temp_path, evidence_path)
PY
    exit "$original_rc"
}
trap finalize_evidence EXIT

if [ -n "$(find "$smoke_root" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    failure_step="sandbox-admission"
    die "smoke root must be new or empty: $smoke_root"
fi
mkdir -p "$run_root/logs" "$smoke_root/home" "$smoke_root/bin" "$smoke_root/src"

failure_step="input-validation"
[ -n "$install_target" ] || die "install target is required when no repository checkout is available"
[ -f "$install_target" ] || [ -d "$install_target" ] || die "install target not found: $install_target"
[ -n "$get_solar" ] || die "get-solar bootstrap is required when no repository checkout is available"
[ -f "$get_solar" ] || die "get-solar bootstrap not found: $get_solar"

export HOME="$smoke_root/home"
export PATH="$smoke_root/bin:$PATH"
export SOLAR_REPO="${SOLAR_REPO:-bundled-runtime-source}"
export SOLAR_CHANNEL="${SOLAR_CHANNEL:-runtime-deliverable}"
export SOLAR_SRC="$smoke_root/src/OpenSolar"
export OPENJIUWEN_SOLAR_GET_SOLAR_URL="$get_solar"

log "sandbox: $smoke_root"
log "channel: $SOLAR_CHANNEL"

if command -v pipx >/dev/null 2>&1; then
    pipx_status="PASS"
    pipx_reason="pipx install and uninstall were exercised"
    run_step package-install env \
        "PIPX_HOME=$smoke_root/pipx" \
        "PIPX_BIN_DIR=$smoke_root/bin" \
        pipx install --force "$install_target"
    opensolar_cmd="$smoke_root/bin/openjiuwen-solar"
else
    pipx_status="NOT_TESTED"
    pipx_reason="pipx is unavailable; isolated venv fallback was exercised"
    record_not_tested pipx-install "$pipx_reason"
    run_step create-wrapper-venv python3 -m venv "$smoke_root/venv"
    run_step package-install "$smoke_root/venv/bin/python" -m pip install \
        --disable-pip-version-check --no-build-isolation "$install_target"
    opensolar_cmd="$smoke_root/venv/bin/openjiuwen-solar"
fi

[ -x "$opensolar_cmd" ] || die "openjiuwen-solar command was not installed at $opensolar_cmd"
run_step runtime-install "$opensolar_cmd" install --yes --components kernel,harness --fake-keys --skip-llm-cli --skip-py-deps
run_step status "$opensolar_cmd" status
run_step doctor "$opensolar_cmd" doctor --json
run_step status-server-start "$opensolar_cmd" harness status-server start
status_port="$(cat "$HOME/.solar/harness/run/status-server.port")"
status_token_file="$HOME/.solar/harness/run/status-server.token"

health_script="$smoke_root/health-check.py"
cat > "$health_script" <<'PY'
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

port, token_path, output_path = sys.argv[1:]
token = Path(token_path).read_text(encoding="utf-8").strip()
request = urllib.request.Request(f"http://127.0.0.1:{port}/healthz")
request.add_header("X-Solar-Token", token)
last_error = "status server did not become ready"
for _ in range(40):
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            body = response.read()
            payload = {
                "http_status": response.status,
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_bytes": len(body),
            }
            Path(output_path).write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            raise SystemExit(0 if response.status == 200 else 1)
    except Exception as exc:
        last_error = str(exc)
        time.sleep(0.25)
raise SystemExit(last_error)
PY
run_step health "${SOLAR_PYTHON:-python3}" "$health_script" "$status_port" "$status_token_file" "$run_root/health-response.json"
run_step status-server-stop "$opensolar_cmd" harness status-server stop

if [ "${OPENJIUWEN_SOLAR_SKIP_UPDATE:-0}" = "1" ]; then
    record_not_tested update "self-contained source snapshot has no remote update channel"
else
    run_step update "$opensolar_cmd" update --fake-keys --skip-llm-cli --skip-py-deps
fi

run_step runtime-uninstall "$opensolar_cmd" uninstall --yes
[ ! -e "$HOME/.solar" ] || die "~/.solar was not removed"
[ ! -e "$HOME/.claude/solar" ] || die "~/.claude/solar was not removed"
[ -d "$SOLAR_SRC" ] || die "$SOLAR_SRC was not retained"

if [ "$pipx_status" = "PASS" ]; then
    run_step package-uninstall env \
        "PIPX_HOME=$smoke_root/pipx" \
        "PIPX_BIN_DIR=$smoke_root/bin" \
        pipx uninstall openjiuwen-solar
else
    run_step package-uninstall "$smoke_root/venv/bin/python" -m pip uninstall -y openjiuwen-solar
fi
{ [ ! -e "$opensolar_cmd" ] && [ ! -L "$opensolar_cmd" ]; } || \
    die "wrapper entrypoint remained after package rollback: $opensolar_cmd"

result_status="passed"
failure_step=""
log "smoke passed"
log "evidence: $evidence_path"
log "sandbox retained for inspection: $smoke_root"
