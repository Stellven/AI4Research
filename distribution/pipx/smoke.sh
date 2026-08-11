#!/usr/bin/env bash
set -eu

log() { printf '[openjiuwen-solar-pipx-smoke] %s\n' "$*" >&2; }
die() { printf '[openjiuwen-solar-pipx-smoke] error: %s\n' "$*" >&2; exit 1; }

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="${OPENJIUWEN_SOLAR_REPO_ROOT:-$(git -C "$script_dir" rev-parse --show-toplevel)}"
[ -d "$repo_root/.git" ] || die "repository root is not a standalone Git checkout: $repo_root"
pkg_dir="$repo_root/distribution/pipx"
install_target="${OPENJIUWEN_SOLAR_INSTALL_TARGET:-$pkg_dir}"
smoke_root="${OPENJIUWEN_SOLAR_SMOKE_ROOT:-${OPENSOLAR_SMOKE_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/openjiuwen-solar-pipx-smoke.XXXXXX")}}"

mkdir -p "$smoke_root/home" "$smoke_root/bin" "$smoke_root/src"
export HOME="$smoke_root/home"
export PATH="$smoke_root/bin:$PATH"
export SOLAR_REPO="file://$repo_root"
export SOLAR_CHANNEL="${SOLAR_CHANNEL:-$(git -C "$repo_root" branch --show-current)}"
export SOLAR_SRC="$smoke_root/src/OpenSolar"
export OPENJIUWEN_SOLAR_GET_SOLAR_URL="$repo_root/get-solar.sh"

[ -n "$SOLAR_CHANNEL" ] || die "could not infer SOLAR_CHANNEL; set it explicitly"
[ -f "$OPENJIUWEN_SOLAR_GET_SOLAR_URL" ] || die "get-solar.sh not found at $OPENJIUWEN_SOLAR_GET_SOLAR_URL"

log "sandbox: $smoke_root"
log "channel: $SOLAR_CHANNEL"

if command -v pipx >/dev/null 2>&1; then
    log "installing wrapper with pipx"
    PIPX_HOME="$smoke_root/pipx" \
    PIPX_BIN_DIR="$smoke_root/bin" \
        pipx install --force "$install_target"
    opensolar_cmd="$smoke_root/bin/openjiuwen-solar"
else
    log "pipx not found; pipx leg unverified, using venv fallback"
    python3 -m venv "$smoke_root/venv"
    "$smoke_root/venv/bin/python" -m pip install --no-build-isolation "$install_target"
    opensolar_cmd="$smoke_root/venv/bin/openjiuwen-solar"
fi

[ -x "$opensolar_cmd" ] || die "openjiuwen-solar command was not installed at $opensolar_cmd"

"$opensolar_cmd" install --yes --components kernel,harness --fake-keys --skip-llm-cli --skip-py-deps
"$opensolar_cmd" status
"$opensolar_cmd" doctor --json
"$opensolar_cmd" harness status-server start
status_port="$(cat "$HOME/.solar/harness/run/status-server.port")"
status_token="$(cat "$HOME/.solar/harness/run/status-server.token")"
"${SOLAR_PYTHON:-python3}" - "$status_port" "$status_token" <<'PY'
import sys
import time
import urllib.request

port, token = sys.argv[1:]
request = urllib.request.Request(f"http://127.0.0.1:{port}/healthz")
request.add_header("X-Solar-Token", token)
last_error = "status server did not become ready"
for _ in range(40):
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status == 200:
                raise SystemExit(0)
    except Exception as exc:
        last_error = str(exc)
        time.sleep(0.25)
raise SystemExit(last_error)
PY
"$opensolar_cmd" harness status-server stop
"$opensolar_cmd" update --fake-keys --skip-llm-cli --skip-py-deps
"$opensolar_cmd" uninstall --yes

[ ! -e "$HOME/.solar" ] || die "~/.solar was not removed"
[ ! -e "$HOME/.claude/solar" ] || die "~/.claude/solar was not removed"
[ -d "$SOLAR_SRC" ] || die "$SOLAR_SRC was not retained"

if command -v pipx >/dev/null 2>&1; then
    PIPX_HOME="$smoke_root/pipx" PIPX_BIN_DIR="$smoke_root/bin" \
        pipx uninstall openjiuwen-solar
else
    "$smoke_root/venv/bin/python" -m pip uninstall -y openjiuwen-solar
fi
{ [ ! -e "$opensolar_cmd" ] && [ ! -L "$opensolar_cmd" ]; } || \
    die "wrapper entrypoint remained after package rollback: $opensolar_cmd"

python3 - "$smoke_root/smoke-evidence.json" "$SOLAR_SRC" <<'PY'
import json
import sys
from pathlib import Path

evidence = {
    "schema_version": "opensolar.runtime-deliverable-smoke/v1",
    "clean_sandbox_install": True,
    "runtime_status": "healthy",
    "doctor": "ok",
    "status_server_health": "passed",
    "runtime_uninstalled": True,
    "wrapper_uninstalled": True,
    "source_retained_for_rollback": Path(sys.argv[2]).is_dir(),
}
Path(sys.argv[1]).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

log "smoke passed"
log "evidence: $smoke_root/smoke-evidence.json"
log "sandbox retained for inspection: $smoke_root"
