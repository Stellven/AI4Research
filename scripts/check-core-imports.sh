#!/usr/bin/env bash
# Static import-resolution gate over core/.
#
# Gate 1: the shipped entrypoint closure (daemon + web dashboard) must fully
#         resolve under Bun's own resolver - this is what must boot on a
#         fresh install.
# Gate 2: every TypeScript file under core/ is swept for unresolved module
#         imports (tsc TS2307). Anything not covered by the documented
#         allowlist fails, so new ghost modules surface all at once instead
#         of one boot failure at a time.
#
# This is an import-resolution gate, not a type-correctness gate: upstream
# core/ carries pre-existing type errors that are out of packaging scope,
# so non-resolution diagnostics are intentionally ignored.
set -e

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

allowlist_file="scripts/core-import-allowlist.txt"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/solar-core-gate.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

echo "== gate 1: shipped entrypoint closure resolves (bun build)"
bun build core/daemon/server.ts core/dashboard/server.ts \
    --target bun --outdir "$work_dir/bundle" >/dev/null
echo "ok: daemon + dashboard closure fully resolved"

echo "== gate 2: whole-core unresolved-import sweep (tsc TS2307, allowlisted)"
tsc_bin="./node_modules/.bin/tsc"
if [ ! -x "$tsc_bin" ]; then
    echo "typescript is not installed; run: bun install --frozen-lockfile" >&2
    exit 1
fi

find core -name '*.ts' ! -path '*/node_modules/*' | sort > "$work_dir/files.txt"

set +e
# shellcheck disable=SC2046
"$tsc_bin" --noEmit --skipLibCheck --target esnext --module preserve \
    --moduleResolution bundler --types bun \
    $(cat "$work_dir/files.txt") > "$work_dir/tsc.log" 2>&1
set -e

grep 'error TS2307' "$work_dir/tsc.log" \
    | sed -E "s/.*Cannot find module '([^']+)'.*/\1/" \
    | sort -u > "$work_dir/missing.txt" || true

violations=0
while IFS= read -r module; do
    [ -n "$module" ] || continue
    allowed=false
    while IFS= read -r pattern; do
        case "$pattern" in
            ''|'#'*) continue ;;
        esac
        # shellcheck disable=SC2254
        case "$module" in
            $pattern) allowed=true; break ;;
        esac
    done < "$allowlist_file"
    if [ "$allowed" != "true" ]; then
        violations=$((violations + 1))
        echo "unresolved import outside allowlist: $module" >&2
        grep 'error TS2307' "$work_dir/tsc.log" | grep "'$module'" >&2 || true
    fi
done < "$work_dir/missing.txt"

if [ "$violations" -gt 0 ]; then
    echo "core import gate FAILED: $violations unresolved module(s)" >&2
    exit 1
fi
echo "ok: no unresolved core/ imports outside the documented allowlist"
echo "core import gate passed"
