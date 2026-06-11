#!/usr/bin/env bash

# py-deps.sh — install a component's Python requirements into its venv.
#
# On a user machine this is the REAL install. CI sets --skip-py-deps /
# SOLAR_SKIP_PY_DEPS to validate resolution only (pip --dry-run --no-deps),
# avoiding the multi-GB embedding/runtime download — the ratified deps-light
# CI policy for heavy components like mempalace (chromadb + sentence-
# transformers). The full venv install + import smoke is a manual/nightly
# check, documented in the mempalace handoff.
pip_install_reqs() {
    venv="$1"
    reqs="$2"
    [ -f "$reqs" ] || die "python requirements missing: $reqs"
    py="$venv/bin/python"
    [ -x "$py" ] || die "venv python missing: $py"
    if [ "${SKIP_PY_DEPS:-false}" = "true" ]; then
        # deps-light (CI): the venv already exists; skip the multi-GB install
        # entirely. Requirement resolution is validated separately and once
        # (scripts/mempalace-check.sh step a: pip --dry-run --no-deps), so the
        # installs need no network and leave no pip cache in the sandbox.
        info "deps-light: skipping pip install of $reqs (resolution validated separately)"
        return 0
    fi
    # Real install on a user machine. Pin pip's cache inside SOLAR_HOME so it is
    # removed wholesale on uninstall and the user's own ~/.cache/pip is never
    # touched (mirrors the bun-cache contract).
    PIP_CACHE_DIR="$SOLAR_HOME/cache/pip"
    export PIP_CACHE_DIR
    mkdir -p "$PIP_CACHE_DIR"
    info "installing python requirements from $reqs"
    "$py" -m pip install -r "$reqs" \
        || die "pip install failed for $reqs"
}
