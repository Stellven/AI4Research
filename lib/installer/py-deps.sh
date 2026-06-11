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
    # Pin pip's cache inside SOLAR_HOME so it is removed wholesale on uninstall
    # and the user's own ~/.cache/pip is never touched (mirrors the bun cache
    # contract). Without this, pip leaks an HTTP cache into $HOME/.cache/pip.
    PIP_CACHE_DIR="$SOLAR_HOME/cache/pip"
    export PIP_CACHE_DIR
    mkdir -p "$PIP_CACHE_DIR"
    if [ "${SKIP_PY_DEPS:-false}" = "true" ]; then
        info "deps-light: validating $reqs resolution (pip --dry-run --no-deps)"
        "$py" -m pip install --dry-run --ignore-installed --no-deps -r "$reqs" \
            || die "python requirements failed to resolve: $reqs"
    else
        info "installing python requirements from $reqs"
        "$py" -m pip install -r "$reqs" \
            || die "pip install failed for $reqs"
    fi
}
