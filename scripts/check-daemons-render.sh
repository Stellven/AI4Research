#!/usr/bin/env bash
# daemons render gate — render both daemon service templates with sample
# values and fail on any forbidden token or unresolved {{. Runners have no
# user-session launchctl/systemd, so real daemon start is a manual checklist
# item; this gate covers template correctness.
set -e

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

export SOURCE_DIR="$repo_dir"
export SOLAR_HOME="/tmp/solar-daemon-check/.solar"
export CLAUDE_DIR="/tmp/solar-daemon-check/.claude"
export OS_KIND="linux"
export SELECTED_COMPONENTS="kernel core-runtime daemons"
export SOLAR_DB="$SOLAR_HOME/db/solar.db"
export SOLAR_DAEMON_HOME="/tmp/solar-daemon-check"
export SOLAR_DAEMON_BUN="/tmp/solar-daemon-check/.bun/bin/bun"

. "$repo_dir/lib/installer/common.sh"
. "$repo_dir/lib/installer/render-template.sh"

work="$(mktemp -d "${TMPDIR:-/tmp}/solar-daemon-check.XXXXXX")"
trap 'rm -rf "$work"' EXIT

FORBIDDEN='brain-router|brain_router|skill_retriever|solar-farm|solar_farm|plan-act|plan_act|xiaoai|ml-intern|ml_intern|gstack|小爱|昊哥|/Users/lisihao|haogege1977|192\.168\.|100\.122\.'
fail=0

for tpl in solar-daemon.plist.template solar-daemon.service.template; do
    out="$work/${tpl%.template}"
    render_template "templates/daemons/$tpl" "$out"
    if grep -nE "$FORBIDDEN" "$out"; then echo "FAIL: forbidden token in $tpl" >&2; fail=1; fi
    if grep -nF '{{' "$out"; then echo "FAIL: unresolved {{ in $tpl" >&2; fail=1; fi
    grep -q "$SOLAR_HOME/core/daemon/server.ts" "$out" || { echo "FAIL: $tpl missing daemon entrypoint" >&2; fail=1; }
    echo "ok: $tpl renders clean"
done

[ "$fail" -eq 0 ] || { echo "daemons-render-check FAILED" >&2; exit 1; }
echo "daemons-render-check passed"
