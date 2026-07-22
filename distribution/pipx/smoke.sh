#!/usr/bin/env bash
set -eu

log() { printf '[openjiuwen-solar-pipx-smoke] %s\n' "$*" >&2; }
die() { printf '[openjiuwen-solar-pipx-smoke] error: %s\n' "$*" >&2; exit 1; }

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
pkg_dir="$repo_root/distribution/pipx"
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
        pipx install --force "$pkg_dir"
    opensolar_cmd="$smoke_root/bin/openjiuwen-solar"
else
    log "pipx not found; pipx leg unverified, using venv fallback"
    python3 -m venv "$smoke_root/venv"
    "$smoke_root/venv/bin/python" -m pip install --no-build-isolation "$pkg_dir"
    opensolar_cmd="$smoke_root/venv/bin/openjiuwen-solar"
fi

[ -x "$opensolar_cmd" ] || die "openjiuwen-solar command was not installed at $opensolar_cmd"

"$opensolar_cmd" install --yes --components kernel,harness --fake-keys --skip-llm-cli --skip-py-deps
"$opensolar_cmd" status
"$opensolar_cmd" doctor --json
"$opensolar_cmd" harness preflight
"$opensolar_cmd" update --fake-keys --skip-llm-cli --skip-py-deps
"$opensolar_cmd" uninstall --yes

[ ! -e "$HOME/.solar" ] || die "~/.solar was not removed"
[ ! -e "$HOME/.claude/solar" ] || die "~/.claude/solar was not removed"
[ -d "$SOLAR_SRC" ] || die "$SOLAR_SRC was not retained"

log "smoke passed"
log "sandbox retained for inspection: $smoke_root"
