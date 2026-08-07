#!/usr/bin/env bash
# compare-webapp-frontend.sh — FRONTEND/browser differential across refs. Heavier than the fast
# gate (per-ref vite build + a real headless-chromium run), so this is a RELEASE-CANDIDATE / NIGHTLY
# gate, NOT part of scripts/verify-webapp-session.sh. Per ref: materialize (git archive) -> symlink
# react-app node_modules -> vite build that ref's bundle -> run tests/desktop/frontend-scenarios.test.js
# against that ref's real backend + bundle -> tabulate Markdown. Proves the FRONTEND session-isolation
# / transparency fixes (provenance chips, freshness visibility, session route doesn't crash) are
# present in the fixed tree and ABSENT in the base.
#
#   bash scripts/compare-webapp-frontend.sh                  # base=8812d4a7 full=HEAD
#   bash scripts/compare-webapp-frontend.sh base=8812d4a7 full=HEAD
#
# Scenarios NOT yet automated here (documented next additions; each needs backend state-seeding or
# network fault-injection, kept out until reliable): rapid session-switch stale-clobber, wrong-event
# UI guard, SSE drop/reconnect visibility. They are tracked in the webapp audit doc.
set -u
repo="$(cd "$(dirname "$0")/.." && pwd)"
RA_NM="$repo/harness/status-server/react-app/node_modules"
SCEN="$repo/tests/desktop/frontend-scenarios.test.js"
KEYS=(provenance-chips freshness-visible session-no-crash)

[ -d "$repo/desktop/node_modules/playwright" ] || { echo "NOT VERIFIED: desktop Playwright missing"; echo "  fix: ( cd desktop && npm ci && npx playwright install chromium )"; exit 1; }
[ -d "$RA_NM" ] || { echo "NOT VERIFIED: react-app deps missing"; echo "  fix: ( cd harness/status-server/react-app && npm ci )"; exit 1; }
[ -f "$SCEN" ] || { echo "NOT VERIFIED: $SCEN absent"; exit 1; }

if [ "$#" -eq 0 ]; then set -- "base=8812d4a7" "full=HEAD"; fi
declare -a LABELS REFS; for a in "$@"; do LABELS+=("${a%%=*}"); REFS+=("${a#*=}"); done

work="$(mktemp -d "${TMPDIR:-/tmp}/webapp-fe.XXXXXX")"
trap 'rm -rf "$work"' EXIT
declare -A CELL

run_ref() {  # run_ref <idx> <ref>
  local idx="$1" ref="$2" dir="$work/$1"
  git -C "$repo" rev-parse --verify -q "$ref^{commit}" >/dev/null || { for k in "${KEYS[@]}"; do CELL["$idx:$k"]="NOREF"; done; return; }
  mkdir -p "$dir"; git -C "$repo" archive "$ref" | tar -x -C "$dir"
  ln -sfn "$RA_NM" "$dir/harness/status-server/react-app/node_modules"
  if ! ( cd "$dir/harness/status-server/react-app" && npx vite build ) >/dev/null 2>&1; then
    echo "  [$ref] vite build FAILED" >&2; for k in "${KEYS[@]}"; do CELL["$idx:$k"]="BUILDERR"; done; return
  fi
  local out
  out="$(SOLAR_STATUS_SERVER="$dir/harness/lib/symphony/status-server.py" \
         SOLAR_HARNESS_LIB="$dir/harness/lib" SOLAR_REF_LABEL="$ref" \
         node "$SCEN" 2>&1)"
  local k v
  for k in "${KEYS[@]}"; do
    v="$(grep -E "^RESULT $k " <<<"$out" | awk '{print $3}' | tail -1)"
    CELL["$idx:$k"]="${v:-ERR}"
  done
}

for i in "${!REFS[@]}"; do echo ">>> [${REFS[$i]}] build + browser scenarios" >&2; run_ref "$i" "${REFS[$i]}"; done

# --- Markdown report ---
echo "# Webapp frontend differential (browser, RC/nightly)"
echo
printf '| Scenario |'; for i in "${!LABELS[@]}"; do printf ' %s (`%s`) |' "${LABELS[$i]}" "$(git -C "$repo" rev-parse --short "${REFS[$i]}" 2>/dev/null || echo "${REFS[$i]}")"; done; echo
printf '|---|'; for _ in "${!LABELS[@]}"; do printf '%s' '---|'; done; echo
declare -A NICE=( [provenance-chips]="provenance / transparency chips render" [freshness-visible]="data freshness + scope visible (updated / events: / status:)" [session-no-crash]="session route renders, no uncaught JS error" )
for k in "${KEYS[@]}"; do
  printf '| %s |' "${NICE[$k]}"
  for i in "${!LABELS[@]}"; do printf ' %s |' "${CELL[$i:$k]:-ERR}"; done; echo
done
echo
echo "_RC/nightly gate (per-ref vite build + headless chromium). Not in the fast local gate. PASS = present/works; FAIL on base = the fix is absent there (expected). Seed-dependent scenarios (rapid-switch, wrong-event UI, SSE drop) are documented as next additions._"
