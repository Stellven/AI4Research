#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/solar-provider-onboarding.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

HOME_DIR="$TMP/home"
SOLAR_HOME="$HOME_DIR/.solar"
CLAUDE_DIR="$HOME_DIR/.claude"
FAKE_BIN="$TMP/bin"
mkdir -p \
    "$SOLAR_HOME/bin" \
    "$SOLAR_HOME/db" \
    "$SOLAR_HOME/harness/config" \
    "$CLAUDE_DIR/solar" \
    "$FAKE_BIN"
touch "$SOLAR_HOME/bin/solar" "$SOLAR_HOME/db/solar.db"
printf '%s\n' '# Solar kernel fixture' > "$CLAUDE_DIR/solar/SOLAR.md"
printf '%s\n' '{"components":["kernel","harness"],"component_roots":{}}' \
    > "$SOLAR_HOME/install-receipt.json"
printf '%s\n' '#!/usr/bin/env sh' 'exit 0' > "$FAKE_BIN/codex"
chmod +x "$FAKE_BIN/codex"

run_doctor() {
    local runtime="$1" output="$2" runtime_override="${3:-}"
    printf '{"runtime":"%s","models":{"lab_builder_matrix":"anthropic-sonnet,anthropic-sonnet,anthropic-sonnet,anthropic-sonnet"}}\n' \
        "$runtime" > "$SOLAR_HOME/harness/config/solar-user-config.json"
    set +e
    HOME="$HOME_DIR" \
    SOLAR_HOME="$SOLAR_HOME" \
    CLAUDE_DIR="$CLAUDE_DIR" \
    SOLAR_PANE_RUNTIME="$runtime_override" \
    PATH="$FAKE_BIN:/usr/bin:/bin" \
        "$ROOT/bin/solar" doctor --json > "$output"
    local rc=$?
    set -e
    # A minimal fixture can lack optional Python modules. Provider assertions
    # inspect the real doctor payload regardless of that unrelated verdict.
    [ "$rc" -eq 0 ] || [ "$rc" -eq 1 ]
}

run_doctor codex "$TMP/codex-doctor.json"
python3 - "$TMP/codex-doctor.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
runtime = payload.get("runtime") or {}
assert runtime.get("selected") == "codex", runtime
assert runtime.get("cli") == "present", runtime
assert runtime.get("auth") == "unauthenticated", runtime
assert "codex login --device-auth" in runtime.get("guidance", ""), runtime
assert "Claude Code must" not in json.dumps(payload), payload
assert not any("claude CLI missing" in item for item in payload.get("warnings", [])), payload
PY

printf '%s\n' '#!/usr/bin/env sh' 'exit 0' > "$FAKE_BIN/claude"
chmod +x "$FAKE_BIN/claude"
run_doctor claude "$TMP/claude-doctor.json"
python3 - "$TMP/claude-doctor.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
runtime = payload.get("runtime") or {}
assert runtime.get("selected") == "claude", runtime
assert runtime.get("cli") == "present", runtime
assert runtime.get("auth") == "unauthenticated", runtime
assert "claude" in runtime.get("guidance", "").lower(), runtime
assert "codex login" not in runtime.get("guidance", "").lower(), runtime
PY

run_doctor claude "$TMP/runtime-override-doctor.json" codex
python3 - "$TMP/runtime-override-doctor.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    runtime = (json.load(handle).get("runtime") or {})
assert runtime.get("selected") == "codex", runtime
assert runtime.get("source") == "SOLAR_PANE_RUNTIME", runtime
PY

grep -Fq 'codex login --device-auth' "$ROOT/lib/installer/main.sh"
grep -Fq 'solar harness start "$(pwd)"' "$ROOT/lib/installer/main.sh"
grep -Fq 'Codex or Claude Code' "$ROOT/README.md"
grep -Fq 'selected runtime' "$ROOT/INSTALL.md"

echo "provider-aware doctor and onboarding: ok"
