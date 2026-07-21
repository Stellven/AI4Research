#!/usr/bin/env bash
# check-installed-clean.sh — assert the INSTALLED/shipped payload carries ZERO
# personal tokens.
#
# Closes the structural gap that let the bare author handle ship in non-kernel
# payload: kernel-gen-check covers only the kernel tree (SOLAR.md + base rules/
# agents/hooks) and its token list lacked the bare handle, so personal data in
# core/, harness/, mempalace/, and shipped skills was ungated.
#
# PERSONAL TOKENS ONLY — the bare author handle + persona proper nouns
# proper nouns + owner paths/IPs. Architectural names (solar-farm/gstack/
# brain-router/...) remain TOLERATED in harness/core internals per the ratified
# WS7 scope and are NOT checked here.
#
# Shipped payload = core/, harness/, mempalace/, skills/ (component source
# trees) + the kernel-shipped hooks/rules/agents (the base allowlists) +
# kernel/fragments + kernel/components.
#
# Usage:
#   check-installed-clean.sh             scan (exit 1 on any hit)
#   check-installed-clean.sh --self-test negative test (planted token detected)
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

# Bare handles cover the path/email/topic forms (/Users/<h>, <h>@, *-<h>-*).
PERSONAL='lisihao|sihaoli|haogege1977|192\.168\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.|小爱|昊哥|xiaoai|Li Sihao|Sihao Li'

# Print the shipped-payload pathspecs, one per line.
build_paths() {
    printf '%s\n' core/ harness/ mempalace/ skills/ kernel/fragments/ kernel/components/
    for spec in "hooks/:.sh:kernel/base-hooks.txt" \
                "rules/:.md:kernel/base-rules.txt" \
                "agents/:.md:kernel/base-agents.txt"; do
        prefix="${spec%%:*}"; rest="${spec#*:}"; suffix="${rest%%:*}"; file="${rest#*:}"
        [ -f "$file" ] || continue
        while IFS= read -r name; do
            name="${name%%#*}"
            name="$(printf '%s' "$name" | awk '{$1=$1; print}')"
            [ -n "$name" ] && printf '%s%s%s\n' "$prefix" "$name" "$suffix"
        done < "$file"
    done
}

if [ "${1:-}" = "--self-test" ]; then
    tmp="$(mktemp)"
    printf 'guardian = sihaoli\n' >"$tmp"
    if grep -qIE "$PERSONAL" "$tmp"; then
        rm -f "$tmp"
        echo "self-test ok: planted personal token detected by the scan pattern"
        exit 0
    fi
    rm -f "$tmp"
    echo "self-test FAILED: planted token not detected" >&2
    exit 1
fi

# Intentional word-split: each line of build_paths is a separate git pathspec
# (none contain spaces). A match => a personal token in the shipped payload.
# shellcheck disable=SC2046
if hits="$(git grep -nIE "$PERSONAL" -- $(build_paths))"; then
    echo "check-installed-clean FAILED: personal token(s) in the shipped payload:" >&2
    printf '%s\n' "$hits" >&2
    exit 1
fi
echo "check-installed-clean passed: no personal tokens in the shipped payload"
