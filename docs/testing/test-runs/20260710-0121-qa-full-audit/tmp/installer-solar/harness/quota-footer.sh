#!/bin/bash
# Solar Harness — pane footer quota/token summary
set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
PERSONA="${1:-}"
LABEL="${2:-$PERSONA}"
SLOT="${3:-${SOLAR_BUILDER_SLOT:-}}"

usage() {
  echo "Usage: $0 <persona> [label] [slot]" >&2
}

[[ -n "$PERSONA" ]] || { usage; exit 2; }

fmt_num() {
  local n="${1:-0}"
  if [[ "$n" == "N/A" ]]; then
    printf "N/A"
  elif [[ "$n" =~ ^[0-9]+$ ]] && (( n >= 1000000 )); then
    awk -v n="$n" 'BEGIN { printf "%.1fM", n / 1000000 }'
  elif [[ "$n" =~ ^[0-9]+$ ]] && (( n >= 1000 )); then
    awk -v n="$n" 'BEGIN { printf "%.1fK", n / 1000 }'
  else
    printf "%s" "$n"
  fi
}

if [[ -n "$SLOT" ]]; then
  export SOLAR_BUILDER_SLOT="$SLOT"
fi

CONFIG=$(bash "$HARNESS_DIR/lib/persona-config.sh" --print-config "$PERSONA" 2>/dev/null || true)
DISPLAY_MODEL=$(printf '%s\n' "$CONFIG" | awk -F= '$1=="DISPLAY_MODEL"{gsub(/^'\''|'\''$/, "", $2); print $2; exit}')
DISPLAY_MODEL="${DISPLAY_MODEL:-N/A}"
MODEL_ID=$(printf '%s\n' "$CONFIG" | awk -F= '$1=="MODEL_ID"{gsub(/^'\''|'\''$/, "", $2); print $2; exit}')
if [[ -f "$HARNESS_DIR/lib/harness-config.sh" ]]; then
  # shellcheck source=/dev/null
  source "$HARNESS_DIR/lib/harness-config.sh"
fi

if [[ -n "$MODEL_ID" ]] && command -v solar_model_key >/dev/null 2>&1; then
  MODEL_KEY="$(solar_model_key "$MODEL_ID")"
else
  MODEL_KEY=$(DISPLAY_MODEL="$DISPLAY_MODEL" python3 - <<'PY'
import os, re
name = os.environ.get("DISPLAY_MODEL", "").lower()
if "glm-5.1" in name:
    print("glm-5.1")
elif "glm-4.7" in name:
    print("glm-4.7")
elif "deepseek" in name:
    print("deepseek")
elif "opus" in name:
    print("claude-opus")
elif "sonnet" in name:
    print("claude-sonnet")
elif "haiku" in name:
    print("claude-haiku")
else:
    s = re.sub(r"[^a-z0-9._-]+", "-", name).strip("-")
    print(s or "unknown")
PY
)
fi

USED_TOKENS=$(MODEL_KEY="$MODEL_KEY" HARNESS_DIR="$HARNESS_DIR" python3 - <<'PY'
import datetime, glob, json, os, time

model_key = os.environ.get("MODEL_KEY", "")
today = datetime.datetime.now().astimezone().date().isoformat()
root = os.path.expanduser("~/.claude/projects")
cache_dir = os.path.join(os.environ.get("HARNESS_DIR", os.path.expanduser("~/.solar/harness")), "state", "quota-footer")
cache_path = os.path.join(cache_dir, f"{model_key}.json")
ttl_seconds = 60

try:
    if os.path.exists(cache_path) and time.time() - os.path.getmtime(cache_path) < ttl_seconds:
        data = json.load(open(cache_path, "r", encoding="utf-8"))
        if data.get("date") == today:
            print(int(data.get("used_tokens") or 0))
            raise SystemExit
except SystemExit:
    raise
except Exception:
    pass

total = 0
seen = set()

def match_model(model: str) -> bool:
    m = (model or "").lower()
    if model_key in ("claude-opus", "claude-sonnet", "claude-haiku"):
        return m.startswith(model_key)
    if model_key == "deepseek":
        return "deepseek" in m
    return m == model_key or m.startswith(model_key + "-")

def usage_total(u: dict) -> int:
    return sum(int(u.get(k) or 0) for k in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ))

for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
    try:
        if datetime.datetime.fromtimestamp(os.path.getmtime(path)).astimezone().date().isoformat() != today:
            continue
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if today not in line or '"usage"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message") or {}
                if not match_model(str(msg.get("model") or "")):
                    continue
                usage = msg.get("usage") or {}
                dedupe_key = (
                    obj.get("requestId"),
                    msg.get("id"),
                    usage.get("input_tokens"),
                    usage.get("output_tokens"),
                    usage.get("cache_creation_input_tokens"),
                    usage.get("cache_read_input_tokens"),
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                total += usage_total(usage)
    except Exception:
        continue

try:
    os.makedirs(cache_dir, exist_ok=True)
    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"date": today, "model_key": model_key, "used_tokens": total}, f)
        f.write("\n")
    os.replace(tmp, cache_path)
except Exception:
    pass

print(total)
PY
)

LOCAL_QUOTA_REMAINING=$(MODEL_KEY="$MODEL_KEY" USED_TOKENS="$USED_TOKENS" python3 - <<'PY'
import json, os

model_key = os.environ.get("MODEL_KEY", "")
used = int(os.environ.get("USED_TOKENS") or 0)
paths = [
    os.environ.get("SOLAR_MODEL_QUOTAS_FILE", ""),
    os.path.expanduser("~/.solar/harness/model-quotas.json"),
]

quota = None
for path in paths:
    if not path or not os.path.exists(path):
        continue
    try:
        data = json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        continue
    entry = data.get(model_key)
    if isinstance(entry, dict):
        quota = entry.get("daily_token_limit") or entry.get("token_limit") or entry.get("limit")
    elif isinstance(entry, int):
        quota = entry
    if quota is not None:
        break

if quota is None:
    print("N/A")
else:
    print(max(0, int(quota) - used))
PY
)

PROVIDER_QUOTA=$(bash "$HARNESS_DIR/quota-providers.sh" "$MODEL_KEY" text 2>/dev/null || printf "quota:N/A(provider-fail)")
if [[ "$PROVIDER_QUOTA" == quota:N/A* && "$LOCAL_QUOTA_REMAINING" != "N/A" ]]; then
  QUOTA_DISPLAY="剩余:$(fmt_num "$LOCAL_QUOTA_REMAINING")"
elif [[ "$PROVIDER_QUOTA" == quota:N/A* ]]; then
  QUOTA_DISPLAY="余:N/A"
else
  QUOTA_DISPLAY="$PROVIDER_QUOTA"
fi

if [[ -n "$MODEL_ID" ]] && command -v solar_model_short_label >/dev/null 2>&1; then
  MODEL_SHORT="$(solar_model_short_label "$MODEL_ID")"
else
  MODEL_SHORT=$(DISPLAY_MODEL="$DISPLAY_MODEL" python3 - <<'PY'
import os
name = os.environ.get("DISPLAY_MODEL", "N/A")
for old, new in [
    ("Claude Opus (Anthropic)", "Opus"),
    ("Claude Sonnet (Anthropic, full tools)", "Sonnet"),
    ("Claude Sonnet", "Sonnet"),
    ("GLM-5.1", "GLM-5.1"),
    ("GLM-4.7", "GLM-4.7"),
    ("DeepSeek V4 Pro", "DeepSeek V4"),
]:
    if old in name:
        print(new)
        raise SystemExit
print(name[:24])
PY
)
fi

printf "%s | 模型:%s | %s | 已用:%s tok" \
  "$LABEL" "$MODEL_SHORT" "$QUOTA_DISPLAY" "$(fmt_num "$USED_TOKENS")"
