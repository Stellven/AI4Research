#!/bin/bash
# Solar Harness — real provider quota/balance probes.
# Never prints credentials. Network failures degrade to a compact warn string.
set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
MODEL_KEY="${1:-}"
MODE="${2:-text}"
CACHE_DIR="$HARNESS_DIR/state/quota-providers"
TTL_SECONDS="${SOLAR_QUOTA_PROVIDER_TTL_SECONDS:-300}"

usage() {
  echo "Usage: $0 <model-key> [text|json]" >&2
}

[[ -n "$MODEL_KEY" ]] || { usage; exit 2; }

mkdir -p "$CACHE_DIR" 2>/dev/null || true

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip(), ensure_ascii=False))'
}

emit_json() {
  local provider="$1" status="$2" metric="$3" value="$4" unit="$5" note="$6"
  printf '{"provider":%s,"status":%s,"metric":%s,"value":%s,"unit":%s,"note":%s}\n' \
    "$(printf '%s' "$provider" | json_escape)" \
    "$(printf '%s' "$status" | json_escape)" \
    "$(printf '%s' "$metric" | json_escape)" \
    "$(printf '%s' "$value" | json_escape)" \
    "$(printf '%s' "$unit" | json_escape)" \
    "$(printf '%s' "$note" | json_escape)"
}

emit_text() {
  local status="$1" metric="$2" value="$3" unit="$4" note="$5"
  case "$status" in
    ok)
      if [[ -n "$unit" ]]; then
        printf "%s:%s %s" "$metric" "$value" "$unit"
      else
        printf "%s:%s" "$metric" "$value"
      fi
      ;;
    *) printf "quota:N/A(%s)" "$note" ;;
  esac
}

emit() {
  local provider="$1" status="$2" metric="$3" value="$4" unit="$5" note="$6"
  if [[ "$MODE" == "json" ]]; then
    emit_json "$provider" "$status" "$metric" "$value" "$unit" "$note"
  else
    emit_text "$status" "$metric" "$value" "$unit" "$note"
  fi
}

cache_get() {
  local name="$1" path="$CACHE_DIR/${name}.json"
  [[ -f "$path" ]] || return 1
  python3 - "$path" "$TTL_SECONDS" "$MODE" <<'PY'
import json, os, sys, time
path, ttl, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3]
if time.time() - os.path.getmtime(path) > ttl:
    raise SystemExit(1)
data = json.load(open(path, encoding="utf-8"))
if mode == "json":
    print(json.dumps(data, ensure_ascii=False))
else:
    status = data.get("status", "warn")
    if status == "ok":
        metric = data.get("metric", "quota")
        value = data.get("value", "N/A")
        unit = data.get("unit", "")
        print(f"{metric}:{value} {unit}".rstrip())
    else:
        print(f"quota:N/A({data.get('note', 'warn')})")
PY
}

cache_put() {
  local name="$1" provider="$2" status="$3" metric="$4" value="$5" unit="$6" note="$7"
  local path="$CACHE_DIR/${name}.json" tmp="$CACHE_DIR/${name}.json.tmp"
  emit_json "$provider" "$status" "$metric" "$value" "$unit" "$note" > "$tmp" 2>/dev/null && mv "$tmp" "$path" 2>/dev/null || true
}

read_deepseek_key() {
  if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    printf '%s' "$DEEPSEEK_API_KEY"
    return 0
  fi
  if [[ -f "$HOME/.config/llm-keys/deepseek" ]]; then
    tr -d '\r\n' < "$HOME/.config/llm-keys/deepseek"
    return 0
  fi
  return 1
}

probe_deepseek() {
  local name="deepseek"
  cache_get "$name" && return 0
  local key
  key="$(read_deepseek_key 2>/dev/null || true)"
  if [[ -z "$key" ]]; then
    cache_put "$name" "deepseek" "warn" "余额" "N/A" "" "no-key"
    emit "deepseek" "warn" "余额" "N/A" "" "no-key"
    return 0
  fi
  local raw
  raw="$(curl -fsS --max-time 8 \
    -H "Authorization: Bearer ${key}" \
    -H "Accept: application/json" \
    "https://api.deepseek.com/user/balance" 2>/dev/null || true)"
  local parsed
  parsed="$(RAW="$raw" python3 - <<'PY'
import json, os
try:
    data = json.loads(os.environ.get("RAW") or "{}")
    infos = data.get("balance_infos") or []
    if not data.get("is_available", False) and not infos:
        print("warn\t余额\tN/A\t\tunavailable")
        raise SystemExit
    preferred = None
    for item in infos:
        if item.get("currency") == "CNY":
            preferred = item
            break
    preferred = preferred or (infos[0] if infos else {})
    currency = preferred.get("currency", "")
    value = preferred.get("total_balance", "N/A")
    unit = " CNY" if currency == "CNY" else (f" {currency}" if currency else "")
    print(f"ok\t余额\t{value}\t{unit}\t")
except Exception as e:
    print("warn\t余额\tN/A\t\tapi-fail")
PY
)"
  IFS=$'\t' read -r status metric value unit note <<< "$parsed"
  cache_put "$name" "deepseek" "$status" "$metric" "$value" "$unit" "$note"
  emit "deepseek" "$status" "$metric" "$value" "$unit" "$note"
}

probe_zhipu() {
  local name="zhipu"
  cache_get "$name" && return 0
  source "$HARNESS_DIR/model-config.sh" 2>/dev/null || true
  local key="${ZHIPU_AUTH_TOKEN:-${ZHIPU_API_KEY:-}}"
  if [[ -z "$key" ]]; then
    cache_put "$name" "zhipu" "warn" "quota" "N/A" "" "no-key"
    emit "zhipu" "warn" "quota" "N/A" "" "no-key"
    return 0
  fi
  # Zhipu Coding Plan tokens used through the Claude Code compatible endpoint
  # are not reliably represented by the bigmodel monitor quota endpoint.  That
  # endpoint can return 0 after weekly window changes even when the coding plan
  # is usable again, which incorrectly makes lab panes look quota-exhausted and
  # blocks dispatch.  Default to an informational N/A unless explicitly asked
  # to query the monitor endpoint.
  if [[ "${SOLAR_ZHIPU_QUOTA_PROBE_MODE:-coding-plan}" != "monitor" ]]; then
    cache_put "$name" "zhipu" "warn" "quota" "N/A" "" "coding-plan"
    emit "zhipu" "warn" "quota" "N/A" "" "coding-plan"
    return 0
  fi
  local raw
  raw="$(curl -fsS --max-time 8 \
    -H "Authorization: ${key}" \
    -H "Content-Type: application/json" \
    -H "User-Agent: Solar-Harness/1.0" \
    "https://bigmodel.cn/api/monitor/usage/quota/limit" 2>/dev/null || true)"
  local parsed
  parsed="$(RAW="$raw" python3 - <<'PY'
import json, os
try:
    data = json.loads(os.environ.get("RAW") or "{}")
    limits = ((data.get("data") or {}).get("limits") or [])
    token = next((x for x in limits if x.get("type") == "TOKENS_LIMIT"), None)
    if not token:
        print("warn\tquota\tN/A\t\tno-token-limit")
        raise SystemExit
    usage = int(token.get("usage") or 0)
    current = int(token.get("currentValue") or 0)
    remaining = max(0, usage - current)
    print(f"ok\t余\t{remaining}\t tok\t")
except Exception:
    print("warn\tquota\tN/A\t\tapi-fail")
PY
)"
  IFS=$'\t' read -r status metric value unit note <<< "$parsed"
  cache_put "$name" "zhipu" "$status" "$metric" "$value" "$unit" "$note"
  emit "zhipu" "$status" "$metric" "$value" "$unit" "$note"
}

probe_anthropic() {
  local name="anthropic"
  cache_get "$name" && return 0
  local key="${ANTHROPIC_ADMIN_API_KEY:-}"
  if [[ -z "$key" ]]; then
    cache_put "$name" "anthropic" "warn" "quota" "N/A" "" "no-admin-key"
    emit "anthropic" "warn" "quota" "N/A" "" "no-admin-key"
    return 0
  fi
  local start end raw
  start="$(date -u +%Y-%m-%dT00:00:00Z)"
  end="$(date -u -v+1d +%Y-%m-%dT00:00:00Z 2>/dev/null || date -u -d tomorrow +%Y-%m-%dT00:00:00Z)"
  raw="$(curl -fsS --max-time 8 \
    -H "x-api-key: ${key}" \
    -H "anthropic-version: 2023-06-01" \
    -H "User-Agent: Solar-Harness/1.0" \
    "https://api.anthropic.com/v1/organizations/usage_report/messages?starting_at=${start}&ending_at=${end}&bucket_width=1d" 2>/dev/null || true)"
  local parsed
  parsed="$(RAW="$raw" python3 - <<'PY'
import json, os
def walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)
try:
    data = json.loads(os.environ.get("RAW") or "{}")
    total = 0
    for d in walk(data):
        for k in ("uncached_input_tokens", "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            v = d.get(k)
            if isinstance(v, int):
                total += v
    print(f"ok\tAPI用量\t{total}\t tok\tadmin-usage")
except Exception:
    print("warn\tquota\tN/A\t\tapi-fail")
PY
)"
  IFS=$'\t' read -r status metric value unit note <<< "$parsed"
  cache_put "$name" "anthropic" "$status" "$metric" "$value" "$unit" "$note"
  emit "anthropic" "$status" "$metric" "$value" "$unit" "$note"
}

case "$MODEL_KEY" in
  deepseek*) probe_deepseek ;;
  glm-*|zhipu*) probe_zhipu ;;
  claude-*|anthropic*) probe_anthropic ;;
  *) emit "unknown" "warn" "quota" "N/A" "" "unknown-model" ;;
esac
