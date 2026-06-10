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
