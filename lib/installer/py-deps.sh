#!/usr/bin/env bash

# py-deps.sh — install a component's Python requirements.
#
# Targets may be a component venv (mempalace) or the existing interpreter the
# unchanged harness calls (`python3`). CI sets --skip-py-deps /
# SOLAR_SKIP_PY_DEPS to avoid heavy dependency installs where a separate gate
# validates resolution.
pip_install_reqs() {
    target="$1"
    reqs="$2"
    [ -f "$reqs" ] || die "python requirements missing: $reqs"
    if [ -x "$target/bin/python" ]; then
        py="$target/bin/python"
        install_scope="venv"
    elif [ -x "$target" ]; then
        py="$target"
        install_scope="interpreter"
    else
        die "python target missing: $target"
    fi
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
    if [ "$install_scope" = "venv" ]; then
        "$py" -m pip install -r "$reqs" \
            || die "pip install failed for $reqs"
        return 0
    fi

    # Harness runs the existing `python3` interpreter directly. For externally
    # managed Python installs, user-site + break-system-packages is the least
    # invasive way to make that same interpreter import the required modules.
    if "$py" -m pip install --user -r "$reqs"; then
        return 0
    fi
    if "$py" -m pip install --user --break-system-packages -r "$reqs"; then
        return 0
    fi
    die "pip install failed for $reqs using $py. Install these requirements into that interpreter and re-run:
  $py -m pip install --user -r $reqs"
}
