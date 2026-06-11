#!/usr/bin/env bash
# kernel-gen-check — assemble the min (kernel only) and max (all P1
# components) SOLAR.md kernels and fail on any forbidden token, any
# unresolved {{ template var, or any excised-subsystem path fragment.
# Also scans the allowlisted base rules and base agents (the files the
# kernel actually installs) for forbidden tokens.
#
# Hook curation/registration is owned by the settings-merge workstream;
# the installed hooks tree is NOT yet covered here (documented in WORKLOG).
set -e

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

export SOURCE_DIR="$repo_dir"
# render_kernel_vars needs concrete path values; these are check-only.
export SOLAR_HOME="/tmp/solar-kernel-check/.solar"
export CLAUDE_DIR="/tmp/solar-kernel-check/.claude"
export SOLAR_DB="$SOLAR_HOME/db/solar.db"

. "$repo_dir/lib/installer/common.sh"
. "$repo_dir/lib/installer/kernel-gen.sh"

work="$(mktemp -d "${TMPDIR:-/tmp}/solar-kernel-check.XXXXXX")"
trap 'rm -rf "$work"' EXIT

FORBIDDEN='brain-router|brain_router|skill_retriever|skill-retriever|solar-farm|solar_farm|plan-act|plan_act|xiaoai|ml-intern|ml_intern|gstack|小爱|昊哥|/Users/lisihao|haogege1977|192\.168\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.'
# Excised-subsystem path fragments. Most are subsumed by FORBIDDEN; the
# meaningful addition is insight-agent (the solar-farm /insight backend),
# which is not itself a bare forbidden token.
DENYLIST='core/solar-farm|scripts/xiaoai|core/plan-act|mcp__brain-router|mcp__skill_retriever|insight-agent'

fail=0

scan_file() {
    label="$1"
    file="$2"
    if grep -nE "$FORBIDDEN" "$file"; then
        echo "FAIL: forbidden token in $label" >&2
        fail=1
    fi
    if grep -n '{{' "$file"; then
        echo "FAIL: unresolved {{ template var in $label" >&2
        fail=1
    fi
    if grep -nE "$DENYLIST" "$file"; then
        echo "FAIL: excised-subsystem path fragment in $label" >&2
        fail=1
    fi
}

echo "== min assembly (kernel only)"
SELECTED_COMPONENTS="kernel"
kernel_assemble "$work/min.md"
scan_file "min SOLAR.md" "$work/min.md"
echo "ok: min assembly built ($(wc -l < "$work/min.md") lines)"

echo "== max assembly (all P1 components)"
SELECTED_COMPONENTS="kernel core-runtime harness skills-md codex-bridge"
kernel_assemble "$work/max.md"
scan_file "max SOLAR.md" "$work/max.md"
echo "ok: max assembly built ($(wc -l < "$work/max.md") lines)"

echo "== allowlisted base rules"
while IFS= read -r name; do
    name="$(printf '%s' "$name" | awk '{$1=$1; print}')"
    case "$name" in ''|'#'*) continue ;; esac
    f="$repo_dir/rules/$name.md"
    [ -f "$f" ] || { echo "FAIL: base rule missing: $f" >&2; fail=1; continue; }
    scan_file "rules/$name.md" "$f"
done < "$repo_dir/kernel/base-rules.txt"
echo "ok: base rules scanned"

echo "== allowlisted base agents"
while IFS= read -r name; do
    name="$(printf '%s' "$name" | awk '{$1=$1; print}')"
    case "$name" in ''|'#'*) continue ;; esac
    f="$repo_dir/agents/$name.md"
    [ -f "$f" ] || { echo "FAIL: base agent missing: $f" >&2; fail=1; continue; }
    scan_file "agents/$name.md" "$f"
done < "$repo_dir/kernel/base-agents.txt"
echo "ok: base agents scanned"

echo "== allowlisted base hooks"
while IFS= read -r name; do
    name="$(printf '%s' "$name" | awk '{$1=$1; print}')"
    case "$name" in ''|'#'*) continue ;; esac
    f="$repo_dir/hooks/$name.sh"
    [ -f "$f" ] || { echo "FAIL: base hook missing: $f" >&2; fail=1; continue; }
    scan_file "hooks/$name.sh" "$f"
done < "$repo_dir/kernel/base-hooks.txt"
echo "ok: base hooks scanned"

if [ "$fail" -ne 0 ]; then
    echo "kernel-gen-check FAILED" >&2
    exit 1
fi
echo "kernel-gen-check passed"
