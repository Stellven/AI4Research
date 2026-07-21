#!/usr/bin/env bash

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
info() { printf '[solar-install] %s\n' "$*" >&2; }
die() { red "error: $*"; exit 1; }

timestamp_utc() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

contains_word() {
    needle="$1"
    haystack="$2"
    for item in $haystack; do
        [ "$item" = "$needle" ] && return 0
    done
    return 1
}

command_path() {
    command -v "$1" 2>/dev/null || true
}

python_version_text() {
    "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || true
}

python_is_311_plus() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

bootstrap_python_if_needed() {
    [ "${BOOTSTRAP_SYSTEM_DEPS:-false}" = "true" ] || return 0

    if [ "${OS_KIND:-}" = "darwin" ]; then
        PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
        export PATH
    fi

    current="$(command_path python3)"
    if [ -n "$current" ] && python_is_311_plus "$current"; then
        return 0
    fi

    if [ "${DRY_RUN:-false}" = "true" ]; then
        info "dry-run: would attempt Python 3.11+ bootstrap for OS=$OS_KIND"
        return 0
    fi

    case "$OS_KIND" in
        darwin)
            if ! command -v brew >/dev/null 2>&1; then
                die "Solar requires Python 3.11+ and --bootstrap-system-deps cannot install it because Homebrew is missing.
Install Homebrew, then re-run:
  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"
  export PATH=\"/opt/homebrew/bin:/usr/local/bin:\$PATH\""
            fi
            info "installing Python 3.11+ with Homebrew"
            brew install python
            ;;
        linux|wsl)
            if command -v apt-get >/dev/null 2>&1; then
                info "installing Python runtime dependencies: apt-get install python3 python3-venv python3-pip"
                installer_run_pkg_command apt-get update \
                    && installer_run_pkg_command apt-get install -y python3 python3-venv python3-pip
            elif command -v dnf >/dev/null 2>&1; then
                info "installing Python runtime dependencies: dnf install python3 python3-pip"
                installer_run_pkg_command dnf install -y python3 python3-pip
            elif command -v pacman >/dev/null 2>&1; then
                info "installing Python runtime dependencies: pacman -S python python-pip"
                installer_run_pkg_command pacman -S --needed python python-pip
            else
                die "Solar requires Python 3.11+, but no supported package manager was found. Install Python 3.11+ and re-run."
            fi
            ;;
    esac
}

python_candidate_path() {
    if [ -n "$1" ]; then
        if [ -x "$1" ]; then
            printf '%s\n' "$1"
        else
            command_path "$1"
        fi
    fi
}

detect_python() {
    requested="${SOLAR_PYTHON:-python3}"
    harness_python="$(command_path python3)"
    SOLAR_PYTHON_VERSION=""

    path="$(python_candidate_path "$requested")"
    [ -n "$path" ] || die "python3 is required but was not found on PATH"

    if [ "$requested" != "python3" ] && [ "$path" != "$harness_python" ]; then
        die "SOLAR_PYTHON points at $path, but the unchanged harness invokes python3 at ${harness_python:-missing}.
No wrapper or launch-path rewrite is allowed. Put the desired Python 3.11+ directory first on PATH so 'python3' resolves to it, then re-run."
    fi

    if ! python_is_311_plus "$path"; then
        found=""
        for candidate in python3.13 python3.12 python3.11; do
            alt="$(python_candidate_path "$candidate")"
            [ -n "$alt" ] || continue
            ver="$(python_version_text "$alt")"
            [ -n "$ver" ] && found="$found $candidate=$ver($alt)"
        done
        die "Solar requires Python 3.11+ for the harness runtime. Found:${found:- none}.
The unchanged harness invokes 'python3', currently: $path ($(python_version_text "$path")).
macOS system python3 is often 3.9 and will not work. Install a supported Python and put it first on PATH, then re-run:
  macOS: brew install python
         export PATH=\"/opt/homebrew/bin:/usr/local/bin:\$PATH\"
  Ubuntu/Debian: sudo apt-get install python3 python3-venv python3-pip
  Fedora: sudo dnf install python3 python3-pip
  Arch: sudo pacman -S python python-pip"
    fi

    SOLAR_PYTHON="$path"
    SOLAR_PYTHON_VERSION="$(python_version_text "$path")"
    export SOLAR_PYTHON SOLAR_PYTHON_VERSION
}

detect_os() {
    case "$(uname -s)" in
        Darwin) OS_KIND="darwin" ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                OS_KIND="wsl"
            else
                OS_KIND="linux"
            fi
            ;;
        *) die "unsupported OS: $(uname -s)" ;;
    esac
    export OS_KIND
}

require_bin() {
    bin="$1"
    remedy="$2"
    if ! command -v "$bin" >/dev/null 2>&1; then
        die "missing required command '$bin'. $remedy"
    fi
}

dry_run_note() {
    if [ "$DRY_RUN" = "true" ]; then
        info "dry-run: $*"
        return 0
    fi
    return 1
}
