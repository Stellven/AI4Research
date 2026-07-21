#!/usr/bin/env bash
# ================================================================
# Solar Harness — operator config reader/writer
#
# Keep runtime launchers out of model policy. Model switches should update
# config/solar-user-config.json (or use an env override for one-off tests),
# then launchers consume this helper.
# ================================================================

[[ -n "${SOLAR_HARNESS_CONFIG_SH_LOADED:-}" ]] && return 0
SOLAR_HARNESS_CONFIG_SH_LOADED=1

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SOLAR_USER_CONFIG="${SOLAR_USER_CONFIG:-$HARNESS_DIR/config/solar-user-config.json}"
SOLAR_MODEL_REGISTRY="${SOLAR_MODEL_REGISTRY:-$HARNESS_DIR/config/model-registry.json}"

solar_model_registry() {
  python3 "$HARNESS_DIR/lib/model_registry.py" --registry "$SOLAR_MODEL_REGISTRY" "$@"
}

SOLAR_DEFAULT_MAIN_MODEL="$(solar_model_registry default main_model 2>/dev/null || printf 'opus')"
SOLAR_DEFAULT_LAB_BUILDER_MATRIX="$(solar_model_registry validate-lab-matrix "$(solar_model_registry default lab_builder_matrix 2>/dev/null || printf 'glm,glm,glm,anthropic-sonnet')" 2>/dev/null || printf 'glm,glm,glm,anthropic-sonnet')"

solar_config_json_get() {
  local dotted_key="$1"
  local default_value="${2:-}"
  python3 - "$SOLAR_USER_CONFIG" "$dotted_key" "$default_value" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
default = sys.argv[3]

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print(default)
    raise SystemExit(0)

cur = data
for part in key.split("."):
    if not isinstance(cur, dict) or part not in cur:
        print(default)
        raise SystemExit(0)
    cur = cur[part]

if cur is None:
    print(default)
elif isinstance(cur, (str, int, float, bool)):
    print(str(cur))
else:
    print(json.dumps(cur, ensure_ascii=False, separators=(",", ":")))
PY
}

solar_config_json_set() {
  local dotted_key="$1"
  local value="$2"
  python3 - "$SOLAR_USER_CONFIG" "$dotted_key" "$value" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
path.parent.mkdir(parents=True, exist_ok=True)

try:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
except Exception as exc:
    raise SystemExit(f"invalid config json: {path}: {exc}")

if not isinstance(data, dict):
    data = {}

cur = data
parts = key.split(".")
for part in parts[:-1]:
    nxt = cur.get(part)
    if not isinstance(nxt, dict):
        nxt = {}
        cur[part] = nxt
    cur = nxt
cur[parts[-1]] = value
data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
tmp.replace(path)
PY
}

solar_lab_builder_matrix() {
  if [[ -n "${SOLAR_LAB_BUILDER_MODEL_MATRIX:-}" ]]; then
    printf '%s\n' "$SOLAR_LAB_BUILDER_MODEL_MATRIX"
    return 0
  fi
  solar_config_json_get "models.lab_builder_matrix" "$SOLAR_DEFAULT_LAB_BUILDER_MATRIX"
}

solar_persona_model() {
  local persona="$1"
  local default_value="${2:-$SOLAR_DEFAULT_MAIN_MODEL}"
  local key=""
  case "$persona" in
    pm) key="models.pm" ;;
    planner) key="models.planner" ;;
    builder) key="models.builder" ;;
    evaluator) key="models.evaluator" ;;
    architect) key="models.architect" ;;
    second-builder) key="models.second_builder" ;;
    lab-evaluator) key="models.lab_evaluator" ;;
    observer) key="models.observer" ;;
    *) key="models.${persona}" ;;
  esac

  local value=""
  value="$(solar_config_json_get "$key" "")"
  if [[ -z "$value" && "$persona" == "pm" ]]; then
    value="$(solar_config_json_get "models.planner" "")"
  elif [[ -z "$value" && "$persona" == "architect" ]]; then
    value="$(solar_config_json_get "models.planner" "")"
  elif [[ -z "$value" && "$persona" == "second-builder" ]]; then
    value="$(solar_config_json_get "models.builder" "")"
  fi

  printf '%s\n' "${value:-$default_value}"
}

solar_set_lab_builder_matrix() {
  local matrix="$1"
  if ! solar_validate_lab_builder_matrix "$matrix"; then
    return 1
  fi
  solar_config_json_set "models.lab_builder_matrix" "$matrix"
}

solar_validate_main_model_alias() {
  local alias="${1:-}"
  solar_model_registry validate-main "$alias"
}

solar_set_main_model() {
  local alias="$1"
  alias="$(solar_validate_main_model_alias "$alias")" || return 1
  for persona in pm planner builder evaluator; do
    solar_config_json_set "models.${persona}" "$alias"
  done
}

solar_validate_lab_builder_matrix() {
  local matrix="${1:-}"
  solar_model_registry validate-lab-matrix "$matrix"
}

solar_model_alias_canonical() {
  solar_model_registry normalize "${1:-}"
}

solar_model_alias_label() {
  solar_model_registry label "${1:-}" 2>/dev/null || printf '%s' "${1:-N/A}"
}

solar_model_short_label() {
  solar_model_registry short-label "${1:-}" 2>/dev/null || solar_model_alias_label "${1:-}"
}

solar_model_key() {
  solar_model_registry model-key "${1:-}" 2>/dev/null || printf '%s' "${1:-unknown}"
}

solar_model_provider() {
  solar_model_registry provider "${1:-}" 2>/dev/null || true
}

solar_model_flag() {
  solar_model_registry model-flag "${1:-}" 2>/dev/null || true
}

solar_lab_builder_matrix_label() {
  local matrix="${1:-}"
  [[ -n "$matrix" ]] || matrix="$(solar_lab_builder_matrix)"
  solar_model_registry matrix-label "$matrix"
}

solar_lab_builder_matrix_item_label() {
  local matrix="${1:-}"
  local index="${2:-0}"
  [[ -n "$matrix" ]] || matrix="$(solar_lab_builder_matrix)"
  local item
  item="$(solar_model_registry matrix-item "$matrix" "$index")"
  solar_model_alias_label "$item"
}
