#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/solar-codex-intake.sh [options] "request"
  bash scripts/solar-codex-intake.sh [options] --file request.md
  echo "request" | bash scripts/solar-codex-intake.sh [options] --stdin

Options:
  --source, --source-channel VALUE  RawIntent source channel. Default: codex_cli
  --actor VALUE                     RawIntent actor. Default: current user or codex
  --device VALUE                    RawIntent device metadata.
  --no-dispatch                     Capture/consume intent without autopilot dispatch.
  --json                            Ask solar-harness intake for JSON output.
  --dry-run                         Print the resolved harness command only.
  -h, --help                        Show this help.

This is a Codex CLI convenience wrapper. It preserves the existing Harness
entrypoint by calling `solar-harness intake` with Codex source metadata.
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_harness_dir="$repo_dir/harness"
installed_harness_dir="${HOME:-}/.solar/harness"
if [[ -n "${SOLAR_HARNESS_DIR:-}" ]]; then
  harness_dir="$SOLAR_HARNESS_DIR"
elif [[ -n "${HARNESS_DIR:-}" ]]; then
  harness_dir="$HARNESS_DIR"
elif [[ -f "$installed_harness_dir/solar-harness.sh" ]]; then
  harness_dir="$installed_harness_dir"
else
  harness_dir="$repo_harness_dir"
fi
harness_bin="${SOLAR_HARNESS_BIN:-$harness_dir/solar-harness.sh}"
venv_dir="$repo_dir/.venv"
if [[ -x "$venv_dir/bin/python3" ]]; then
  export VIRTUAL_ENV="$venv_dir"
  export PATH="$venv_dir/bin:$PATH"
fi

source_channel="codex_cli"
actor="${USER:-codex}"
device="${SOLAR_INTENT_DEVICE:-}"
dispatch=1
json=0
dry_run=0
request_file=""
use_stdin=0
declare -a request_parts=()

while (($#)); do
  case "$1" in
    --source|--source-channel)
      shift || die "$1 requires a value"
      source_channel="$1"
      ;;
    --actor)
      shift || die "--actor requires a value"
      actor="$1"
      ;;
    --device)
      shift || die "--device requires a value"
      device="$1"
      ;;
    --file)
      shift || die "--file requires a path"
      request_file="$1"
      ;;
    --stdin)
      use_stdin=1
      ;;
    --no-dispatch)
      dispatch=0
      ;;
    --json)
      json=1
      ;;
    --dry-run)
      dry_run=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      request_parts+=("$@")
      break
      ;;
    --*)
      die "unknown option: $1"
      ;;
    *)
      request_parts+=("$1")
      ;;
  esac
  shift || true
done

[[ -f "$harness_bin" ]] || die "solar-harness not found: $harness_bin"

input_count=0
[[ -n "$request_file" ]] && input_count=$((input_count + 1))
[[ "$use_stdin" == "1" ]] && input_count=$((input_count + 1))
((${#request_parts[@]} > 0)) && input_count=$((input_count + 1))
[[ "$input_count" == "1" ]] || die "provide exactly one request source: args, --file, or --stdin"

declare -a harness_args=(intake)
if [[ -n "$request_file" ]]; then
  [[ -f "$request_file" ]] || die "request file not found: $request_file"
  harness_args+=(--file "$request_file")
elif [[ "$use_stdin" == "1" ]]; then
  harness_args+=(--stdin)
else
  harness_args+=(--request "${request_parts[*]}")
fi

[[ "$dispatch" == "0" ]] && harness_args+=(--no-dispatch)
[[ "$json" == "1" ]] && harness_args+=(--json)

if [[ "$dry_run" == "1" ]]; then
  printf 'repo_dir=%q\n' "$repo_dir"
  printf 'HARNESS_DIR=%q\n' "$harness_dir"
  printf 'SOLAR_INTENT_SOURCE_CHANNEL=%q\n' "$source_channel"
  printf 'SOLAR_INTENT_ACTOR=%q\n' "$actor"
  printf 'SOLAR_INTENT_DEVICE=%q\n' "$device"
  printf 'python3=%q\n' "$(command -v python3 2>/dev/null || printf 'N/A')"
  printf 'command='
  printf '%q ' bash "$harness_bin" "${harness_args[@]}"
  printf '\n'
  exit 0
fi

export HARNESS_DIR="$harness_dir"
export SOLAR_HARNESS_DIR="$harness_dir"
export SOLAR_HARNESS_SPRINTS_DIR="${SOLAR_HARNESS_SPRINTS_DIR:-$harness_dir/sprints}"
export SOLAR_INTENT_GATEWAY_DIR="${SOLAR_INTENT_GATEWAY_DIR:-$harness_dir/intents}"
export SOLAR_INTENT_SOURCE_CHANNEL="$source_channel"
export SOLAR_INTENT_ACTOR="$actor"
export SOLAR_INTENT_DEVICE="$device"

cd "$repo_dir"
exec bash "$harness_bin" "${harness_args[@]}"
