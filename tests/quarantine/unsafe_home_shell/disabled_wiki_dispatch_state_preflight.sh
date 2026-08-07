#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
BRIDGE="$HARNESS_DIR/integrations/obsidian-wiki-bridge.sh"
ENFORCER="$HOME/.claude/hooks/state-read-enforcer.sh"

tmp="$(mktemp -d /tmp/solar-wiki-preflight-test.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

export OBSIDIAN_VAULT_PATH="$tmp/vault"
mkdir -p "$OBSIDIAN_VAULT_PATH"

# shellcheck disable=SC1090
source "$BRIDGE"

dispatch="$(cmd_wiki_ingest --source /tmp/source.md --project preflight-smoke | tail -1)"

[[ -f "$dispatch" ]] || {
  echo "dispatch not created" >&2
  exit 1
}

first_line="$(sed -n '1p' "$dispatch")"
[[ "$first_line" == "---" ]] || {
  echo "frontmatter is not first line" >&2
  exit 1
}

grep -q "SOLAR_STATE_READ_PREFLIGHT" "$dispatch" || {
  echo "missing state-read preflight block" >&2
  exit 1
}

[[ "$(_bridge_dispatch_field "$dispatch" type)" == "wiki-dispatch" ]] || {
  echo "dispatch parser cannot read type" >&2
  exit 1
}

[[ "$(_bridge_dispatch_field "$dispatch" status)" == "pending" ]] || {
  echo "dispatch parser cannot read status" >&2
  exit 1
}

printf '%s' '{"tool_name":"Write","tool_input":{"file_path":"~/Knowledge/references/preflight-smoke.md"}}' \
  | "$ENFORCER" >/tmp/solar-wiki-preflight-enforcer.out

grep -q '"continue": true' /tmp/solar-wiki-preflight-enforcer.out || {
  echo "Knowledge references path is not exempt from state-read enforcer" >&2
  exit 1
}

printf 'ok\n'
