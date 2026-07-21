#!/usr/bin/env bash
# Regression guard: provider-specific Claude Code gateway behavior.
# Z.AI Coding Plan uses the official Claude Code route (AUTH_TOKEN + /api/anthropic)
# and must not use --bare/API_KEY because that can route as API usage billing.
# Other Anthropic-compatible gateways, such as DeepSeek, still need --bare.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

config_value() {
  local config="$1" key="$2"
  printf '%s\n' "$config" | awk -F"'" -v k="$key" '$0 ~ "^" k "=" { print $2; exit }'
}

check_gateway_config() {
  local label="$1" persona="$2" slot="${3:-}"
  local config base_url extra_flags auth_source
  if [[ -n "$slot" ]]; then
    config=$(SOLAR_BUILDER_SLOT="$slot" bash "$HARNESS_DIR/lib/persona-config.sh" --print-config "$persona")
  else
    config=$(bash "$HARNESS_DIR/lib/persona-config.sh" --print-config "$persona")
  fi

  base_url=$(config_value "$config" BASE_URL)
  extra_flags=$(config_value "$config" EXTRA_FLAGS)
  auth_source=$(config_value "$config" AUTH_SOURCE)

  if [[ -z "$base_url" ]]; then
    pass "$label: direct Anthropic/no gateway"
    return 0
  fi

  [[ -n "$auth_source" ]] && pass "$label: auth source set ($auth_source)" || fail "$label: missing AUTH_SOURCE"
  if [[ "$auth_source" == "zhipu" ]]; then
    [[ "$extra_flags" != *"--bare"* ]] && pass "$label: zhipu coding plan does not use --bare" || fail "$label: zhipu must not use --bare"
  else
    [[ "$extra_flags" == *"--bare"* ]] && pass "$label: --bare enabled" || fail "$label: missing --bare"
  fi
  [[ "$extra_flags" == *"--tools default"* ]] && pass "$label: tools constrained" || fail "$label: missing --tools default"
  [[ "$extra_flags" == *"--strict-mcp-config"* ]] && pass "$label: strict MCP config" || fail "$label: missing --strict-mcp-config"
  [[ "$extra_flags" == *"config/empty-mcp.json"* ]] && pass "$label: empty MCP config used" || fail "$label: missing empty MCP config"
}

echo "=== test-gateway-compat.sh ==="

if [[ -f "$HARNESS_DIR/config/empty-mcp.json" ]] && python3 -m json.tool "$HARNESS_DIR/config/empty-mcp.json" >/dev/null; then
  pass "empty-mcp.json exists and is valid JSON"
else
  fail "empty-mcp.json missing or invalid"
fi

for slot in lab-builder-1 lab-builder-2 lab-builder-3 lab-builder-4; do
  check_gateway_config "$slot" "lab-builder" "$slot"
done

for persona in lab-evaluator observer; do
  check_gateway_config "$persona" "$persona"
done

for persona in pm planner builder evaluator; do
  config=$(bash "$HARNESS_DIR/lib/persona-config.sh" --print-config "$persona")
  base_url=$(config_value "$config" BASE_URL)
  extra_flags=$(config_value "$config" EXTRA_FLAGS)
  if [[ -z "$base_url" && -z "$extra_flags" ]]; then
    pass "$persona: main pane preserves full Claude Code behavior"
  else
    fail "$persona: main pane unexpectedly uses gateway flags"
  fi
done

echo ""
echo "=== Results: $PASS PASS / $FAIL FAIL ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL_TESTS_PASS"
