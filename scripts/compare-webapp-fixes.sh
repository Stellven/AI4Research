#!/usr/bin/env bash
# compare-webapp-fixes.sh — differential (A/B/C) verification across git refs. Proves the FIXED
# tree behaves better than the base by running the SAME scenario suite against each ref and
# emitting a Markdown table. Each ref is materialized with `git archive` (clean, no node_modules),
# then the CURRENT scenario tests are injected so identical checks run on every ref — even refs
# that predate the tests (that's the point: base FAILS the invariant the fix introduces).
#
#   bash scripts/compare-webapp-fixes.sh                         # defaults below
#   bash scripts/compare-webapp-fixes.sh base=8812d4a7 backend=a264f32d full=HEAD
#
# Scope: BACKEND scenarios (deterministic, fast, socket-only): settings concurrency + CORS token,
# and session-scoping/orchestration pytest. Frontend-only differences (provenance UI, UI-side
# event guard) are NOT differenced here — they need a per-ref build + browser and are covered by
# verify-webapp-session.sh's functional e2e on the full tree. This is stated, not hidden.
set -u
repo="$(cd "$(dirname "$0")/.." && pwd)"

# Parse label=ref args; default A/B/C.
declare -a LABELS REFS
if [ "$#" -eq 0 ]; then
  set -- "base=8812d4a7" "backend=a264f32d" "full=HEAD"
fi
for a in "$@"; do LABELS+=("${a%%=*}"); REFS+=("${a#*=}"); done

CUR_TESTS=(
  "harness/status-server/test_settings_concurrency.py"
  "harness/tests/test_status_server_session_scoping.py"
  "harness/tests/test_s04_orchestration_routes.py"
)

work="$(mktemp -d "${TMPDIR:-/tmp}/webapp-ab.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# result arrays, indexed by ref position: cors, settings (X/Y), pytest (passed/failed)
declare -a R_CORS R_SET R_PY

materialize() {  # materialize <ref> <dest>
  git -C "$repo" rev-parse --verify -q "$1^{commit}" >/dev/null || { echo "  ref not found: $1" >&2; return 1; }
  mkdir -p "$2"
  git -C "$repo" archive "$1" | tar -x -C "$2"
  # Inject the CURRENT scenario tests (identical checks on every ref).
  for t in "${CUR_TESTS[@]}"; do
    mkdir -p "$2/$(dirname "$t")"
    cp "$repo/$t" "$2/$t"
  done
}

run_ref() {  # run_ref <idx> <ref>
  local idx="$1" ref="$2" dir="$work/$1"
  echo ">>> [$ref] materialize + run backend scenarios" >&2
  if ! materialize "$ref" "$dir"; then R_CORS[$idx]="ERR"; R_SET[$idx]="ERR"; R_PY[$idx]="ERR"; return; fi

  # --- settings concurrency + CORS token ---
  local out
  out="$(cd "$dir" && python3 harness/status-server/test_settings_concurrency.py 2>&1)"
  if grep -q 'PASS  F1 Allow-Headers advertises X-Solar-Token' <<<"$out"; then R_CORS[$idx]="allow"; else R_CORS[$idx]="**MISSING**"; fi
  R_SET[$idx]="$(grep -oE 'BACKEND-P0: [0-9]+/[0-9]+' <<<"$out" | grep -oE '[0-9]+/[0-9]+' | tail -1)"
  [ -n "${R_SET[$idx]:-}" ] || R_SET[$idx]="err"

  # --- session-scoping + orchestration pytest ---
  out="$(cd "$dir" && python3 -m pytest -q harness/tests/test_status_server_session_scoping.py harness/tests/test_s04_orchestration_routes.py 2>&1)"
  local p f e
  p="$(grep -oE '[0-9]+ passed' <<<"$out" | grep -oE '[0-9]+' | tail -1)"; p="${p:-0}"
  f="$(grep -oE '[0-9]+ failed'  <<<"$out" | grep -oE '[0-9]+' | tail -1)"; f="${f:-0}"
  e="$(grep -oE '[0-9]+ error'   <<<"$out" | grep -oE '[0-9]+' | tail -1)"; e="${e:-0}"
  R_PY[$idx]="${p} pass / $((f + e)) fail"
}

echo "Differential webapp verification — $(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo 'now')" >&2
for i in "${!REFS[@]}"; do run_ref "$i" "${REFS[$i]}"; done

# --- emit Markdown report ---
{
  echo "# Webapp fix differential (A/B/C)"
  echo
  printf '| Scenario |'; for i in "${!LABELS[@]}"; do printf ' %s (`%s`) |' "${LABELS[$i]}" "$(git -C "$repo" rev-parse --short "${REFS[$i]}" 2>/dev/null || echo "${REFS[$i]}")"; done; echo
  printf '|---|'; for _ in "${!LABELS[@]}"; do printf '%s' '---|'; done; echo
  printf '| CORS preflight advertises `X-Solar-Token` |'; for i in "${!LABELS[@]}"; do printf ' %s |' "${R_CORS[$i]}"; done; echo
  printf '| settings concurrency (no lost update / no torn read) |'; for i in "${!LABELS[@]}"; do printf ' %s |' "${R_SET[$i]}"; done; echo
  printf '| session-scoping + orchestration (pytest) |'; for i in "${!LABELS[@]}"; do printf ' %s |' "${R_PY[$i]}"; done; echo
  echo
  echo "_settings = checks passed out of 7 (CORS + concurrent runtime/codex/models survival + torn-read watchdog). Frontend-only invariants (provenance chips, UI-side wrong-event guard) are verified by \`verify-webapp-session.sh\` functional e2e on the full tree, not differenced here._"
} | tee "$work/report.md"
