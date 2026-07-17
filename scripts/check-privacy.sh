#!/usr/bin/env bash
# check-privacy.sh — repo-wide PRIVACY scan for the public release.
#
# Scope (ratified P4 decision — see WORKLOG "privacy-gate scope"):
#   This gate covers PRIVACY only:
#     1. Real secrets — gitleaks, run by the CI privacy-gate job using
#        harness/gitleaks.toml (not invoked here).
#     2. This script — a repo-wide grep over tracked files for UNAMBIGUOUS
#        owner-identifying personal tokens (paths / handles / emails / LAN IPs).
#   Architectural-name excision (solar-farm/gstack/brain-router/...) is gated
#   SEPARATELY and strictly in the INSTALLED tree by scripts/check-kernel-gen.sh
#   (untouched). Other persona names (小爱/昊哥/xiaoai/sihaoli/Li Sihao) are
#   personal-but-parked in non-installed contributor content on pkg/migration;
#   their repo-wide zero-tolerance is enforced by the orphan-cut verification
#   (P4 step 3), NOT here.
#
# The tokens below are already zero in tracked content; this gate keeps them
# that way and fails loudly if any reappear.
#
# Usage:
#   check-privacy.sh             run the live scan (exit 1 on any hit)
#   check-privacy.sh --self-test negative test: assert a planted token trips
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

# Unambiguous owner-identifying personal tokens. NOT the architectural names
# (parked by design; gated in the installed tree by check-kernel-gen.sh).
PERSONAL='lisihao|sihaoli@|haogege1977|SihaodeMacBook|192\.168\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.'

# Scanner scripts legitimately embed the token PATTERNS in their own source.
EXCLUDE=(
    ':(exclude)scripts/check-privacy.sh'
    ':(exclude)scripts/check-kernel-gen.sh'
    ':(exclude)scripts/check-daemons-render.sh'
    ':(exclude)scripts/release-cut.sh'
    ':(exclude)scripts/check-installed-clean.sh'
)

if [ "${1:-}" = "--self-test" ]; then
    tmp="$(mktemp)"
    printf 'private mirror = opensolar-state/lisihao-Solar-mirror\n' >"$tmp"
    if grep -qIE "$PERSONAL" "$tmp"; then
        rm -f "$tmp"
        echo "self-test ok: planted personal token detected by the scan pattern"
        exit 0
    fi
    rm -f "$tmp"
    echo "self-test FAILED: planted personal token not detected" >&2
    exit 1
fi

# Live scan over tracked files (git grep excludes node_modules, the ignored
# local-only working files, and the scanner scripts). A match => fail.
if hits="$(git grep -nIE "$PERSONAL" -- . "${EXCLUDE[@]}")"; then
    echo "check-privacy FAILED: owner-identifying personal token(s) in tracked files:" >&2
    printf '%s\n' "$hits" >&2
    exit 1
fi
echo "check-privacy passed: no owner-identifying personal tokens in tracked files"
