#!/usr/bin/env bash
# get-solar.sh — curl|bash bootstrap for Solar.
#
#   curl -fsSL https://github.com/suraj-subrahmanyan/OpenSolar/releases/latest/download/get-solar.sh | bash
#   curl -fsSL <url> | bash -s -- --yes --components kernel,harness
#
# Clones the published Solar channel and runs install.sh, forwarding every
# argument verbatim. The clone is kept at $SOLAR_SRC so the recorded source_dir
# survives and `solar update` can re-run the installer later.
#
# Overrides (env): SOLAR_REPO, SOLAR_CHANNEL, SOLAR_SRC.
# Style: functions only, main at the end, bash-3.2-safe (no arrays, no [[ ]]).
set -eu

# NOTE (owner-finalized at the release cut): SOLAR_CHANNEL defaults to the
# `stable` release ref and the curl|bash entry URL above is a GitHub Release
# asset. Both resolve once the public release is cut. Until then, override with
# SOLAR_CHANNEL (e.g. a branch) and/or SOLAR_REPO.
SOLAR_REPO="${SOLAR_REPO:-https://github.com/suraj-subrahmanyan/OpenSolar.git}"
SOLAR_CHANNEL="${SOLAR_CHANNEL:-stable}"
SOLAR_SRC="${SOLAR_SRC:-$HOME/.solar-src/OpenSolar}"

log() { printf '[get-solar] %s\n' "$*" >&2; }
die() { printf '[get-solar] error: %s\n' "$*" >&2; exit 1; }

require_git() {
    command -v git >/dev/null 2>&1 || die "git is required; install git and re-run"
}

fetch_source() {
    rm -rf "$SOLAR_SRC"
    mkdir -p "$(dirname "$SOLAR_SRC")"
    log "cloning $SOLAR_REPO (channel: $SOLAR_CHANNEL) -> $SOLAR_SRC"
    if ! git clone --depth 1 --branch "$SOLAR_CHANNEL" "$SOLAR_REPO" "$SOLAR_SRC" 2>/dev/null; then
        die "could not clone channel '$SOLAR_CHANNEL' from $SOLAR_REPO.
  The public release may not be published yet, or the channel is wrong.
  Override with: SOLAR_CHANNEL=<tag-or-branch> SOLAR_REPO=<url> before re-running."
    fi
    [ -f "$SOLAR_SRC/install.sh" ] || die "install.sh not found in the cloned channel ($SOLAR_SRC)"
}

run_installer() {
    log "running install.sh"
    cd "$SOLAR_SRC"
    ./install.sh "$@"
}

main() {
    require_git
    fetch_source
    run_installer "$@"
}

main "$@"
