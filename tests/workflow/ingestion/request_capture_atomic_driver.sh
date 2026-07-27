#!/usr/bin/env bash
set -euo pipefail

case_name="${1:?atomic case name is required}"
repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
scratch="$(mktemp -d)"
cleanup() {
  if [[ "${PHASE22_KEEP_SCRATCH:-0}" == "1" ]]; then
    echo "phase22 scratch retained: $scratch" >&2
  else
    rm -rf "$scratch"
  fi
}
trap cleanup EXIT

harness_copy="$scratch/harness"
project="$scratch/project"
test_home="$scratch/home"
mkdir -p "$harness_copy" "$project" "$test_home" "$scratch/raw" "$scratch/intents"
cp -R "$repo_root/harness/lib" "$harness_copy/lib"
cp -R "$repo_root/harness/tools" "$harness_copy/tools"
for optional_dir in capability-capsules config schemas templates workflows; do
  if [[ -d "$repo_root/harness/$optional_dir" ]]; then
    cp -R "$repo_root/harness/$optional_dir" "$harness_copy/$optional_dir"
  fi
done
cp "$repo_root/harness/solar-harness.sh" "$harness_copy/solar-harness.sh"
chmod +x "$harness_copy/solar-harness.sh"

python3 - "$harness_copy/solar-harness.sh" "$harness_copy" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
harness = sys.argv[2]
text = path.read_text()
text = text.replace(
    'HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"',
    f'HARNESS_DIR="${{HARNESS_DIR:-{harness}}}"',
    1,
)
text = text.replace('HARNESS_DIR="$HOME/.solar/harness"', f'HARNESS_DIR="{harness}"', 1)
path.write_text(text)
PY

export HOME="$test_home"
export HARNESS_DIR="$harness_copy"
export SOLAR_HARNESS_DIR="$harness_copy"
export SOLAR_KNOWLEDGE_RAW_DIR="$scratch/raw"
export SOLAR_INTENT_GATEWAY_DIR="$scratch/intents"

run_from_project() {
  (cd "$project" && "$harness_copy/solar-harness.sh" intake "$@")
}

assert_success_payload() {
  local output_file="$1" expected_text="$2" expected_dispatch="$3"
  python3 - "$output_file" "$scratch/intents" "$expected_text" "$expected_dispatch" <<'PY'
import json
from pathlib import Path
import sys

output_path, intents_path, expected_text, expected_dispatch = sys.argv[1:]
payload = json.loads(Path(output_path).read_text())
assert payload["ok"] is True, payload
assert payload["dispatch_requested"] is (expected_dispatch == "true"), payload
intent_id = payload["intent_gateway"]["intent_id"]
assert intent_id, payload
raw = json.loads((Path(intents_path) / intent_id / "raw_intent.json").read_text())
assert raw["raw"]["text"] == expected_text, raw
PY
}

case "$case_name" in
  direct_text)
    out="$scratch/direct.json"
    run_from_project --no-dispatch --json "Direct request text" >"$out"
    assert_success_payload "$out" "Direct request text" false
    ;;
  file)
    printf '%s\n' "Request read from file" >"$scratch/request.md"
    out="$scratch/file.json"
    run_from_project --file "$scratch/request.md" --no-dispatch --json >"$out"
    assert_success_payload "$out" "Request read from file" false
    ;;
  stdin)
    out="$scratch/stdin.json"
    printf '%s\n' "Request read from stdin" | run_from_project --stdin --no-dispatch --json >"$out"
    assert_success_payload "$out" "Request read from stdin" false
    ;;
  no_dispatch)
    marker="$scratch/autopilot-called"
    export PHASE22_AUTOPILOT_MARKER="$marker"
    cat >"$harness_copy/tools/solar-autopilot-monitor.py" <<'PY'
import os
from pathlib import Path
Path(os.environ["PHASE22_AUTOPILOT_MARKER"]).write_text("called")
PY
    out="$scratch/no-dispatch.json"
    run_from_project --no-dispatch --json "Do not dispatch this request" >"$out"
    assert_success_payload "$out" "Do not dispatch this request" false
    [[ ! -e "$marker" ]]
    ;;
  successful_dispatch)
    marker="$scratch/autopilot-called"
    export PHASE22_AUTOPILOT_MARKER="$marker"
    cat >"$harness_copy/tools/solar-autopilot-monitor.py" <<'PY'
import os
from pathlib import Path
Path(os.environ["PHASE22_AUTOPILOT_MARKER"]).write_text("called")
print('{"ok": true}')
PY
    out="$scratch/dispatch.json"
    run_from_project --json "Dispatch this request" >"$out"
    assert_success_payload "$out" "Dispatch this request" true
    [[ -f "$marker" ]]
    python3 - "$out" <<'PY'
import json
from pathlib import Path
import sys
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["autopilot_returncode"] == 0, payload
PY
    ;;
  empty_input)
    set +e
    run_from_project --no-dispatch --json >"$scratch/empty.out" 2>"$scratch/empty.err"
    rc=$?
    set -e
    [[ "$rc" -ne 0 ]]
    [[ ! -d "$scratch/intents" || -z "$(find "$scratch/intents" -mindepth 1 -print -quit)" ]]
    ;;
  missing_file)
    set +e
    run_from_project --file "$scratch/does-not-exist.md" --no-dispatch --json >"$scratch/missing.out" 2>"$scratch/missing.err"
    rc=$?
    set -e
    [[ "$rc" -ne 0 ]]
    grep -Fq "intake file not found" "$scratch/missing.out"
    [[ ! -d "$scratch/intents" || -z "$(find "$scratch/intents" -mindepth 1 -print -quit)" ]]
    ;;
  workspace_mismatch)
    set +e
    (cd "$harness_copy" && "$harness_copy/solar-harness.sh" intake --no-dispatch --json "Wrong workspace") >"$scratch/mismatch.out" 2>"$scratch/mismatch.err"
    rc=$?
    set -e
    [[ "$rc" -ne 0 ]]
    grep -Fq "no user workspace is bound" "$scratch/mismatch.err"
    ;;
  *)
    echo "unknown atomic case: $case_name" >&2
    exit 2
    ;;
esac
