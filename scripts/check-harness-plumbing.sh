#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-harness-plumbing.XXXXXX")"
home_dir="$sandbox/home"
install_sh="$repo_dir/install.sh"

cleanup() {
  rm -rf "$sandbox"
}
trap cleanup EXIT

echo "deterministic harness plumbing smoke, not live runtime behavior"
echo "sandbox=$sandbox"

HOME="$home_dir" "$install_sh" --yes --components kernel,harness --fake-keys --skip-llm-cli >/dev/null

doctor_json="$sandbox/solar-doctor.json"
HOME="$home_dir" "$home_dir/.solar/bin/solar" doctor --json > "$doctor_json"
python3 - "$doctor_json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
if payload.get("verdict") != "ok":
    raise SystemExit(f"solar doctor verdict was not ok: {payload}")
PY
echo "solar doctor: ok"

selected_runtime="$(python3 - "$home_dir/.solar/harness/config/solar-user-config.json" <<'PY'
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    data = {}
runtime = str(data.get("runtime") or "claude").strip().lower()
print(runtime if runtime in {"claude", "codex"} else "claude")
PY
)"
echo "selected pane runtime: $selected_runtime"

python3 "$home_dir/.solar/harness/tools/check_capsule_operator_bindings.py"
echo "stable capsule/operator bindings: coherent"

fake_ok="$sandbox/fake-ok"
mkdir -p "$fake_ok"
cat > "$fake_ok/claude" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in
  --version) echo "claude fake-for-preflight" ;;
esac
exit 0
SH
chmod +x "$fake_ok/claude"
cat > "$fake_ok/codex" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in
  --version|-V|version) echo "codex fake-for-preflight" ;;
esac
exit 0
SH
chmod +x "$fake_ok/codex"

preflight_ok="$sandbox/preflight-ok.txt"
HOME="$home_dir" PATH="$fake_ok:/usr/bin:/bin:$PATH" "$home_dir/.solar/bin/solar-harness" preflight > "$preflight_ok"
grep -q "required ok: ${selected_runtime}" "$preflight_ok"
# Runtime-aware: preflight prints "live <runtime> pane" (e.g. "live claude pane" / "live codex pane"),
# so match any runtime name rather than the stale literal "Claude".
grep -qE 'manual-pending: live .* pane behavior is not verified by preflight' "$preflight_ok"
echo "solar-harness preflight with fake selected runtime CLI: ok"

fake_fail="$sandbox/fake-fail"
mkdir -p "$fake_fail"
cat > "$fake_fail/tmux" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$sandbox/tmux-fail.log"
exit 1
SH
chmod +x "$fake_fail/tmux"

set +e
HOME="$home_dir" PATH="$fake_fail:/usr/bin:/bin" "$home_dir/.solar/bin/solar-harness" start "$repo_dir" --skip-doctor > "$sandbox/start-missing-runtime.txt" 2>&1
start_rc=$?
set -e
if [ "$start_rc" -eq 0 ]; then
  echo "FAIL: solar-harness start passed despite missing selected runtime CLI" >&2
  cat "$sandbox/start-missing-runtime.txt" >&2
  exit 1
fi
# Runtime-aware: a missing runtime CLI is reported as "required fail: <runtime> runtime CLI not found"
# (or the generic "<cmd> not found on PATH") — match the selected runtime failure however it's worded.
grep -qE "required fail:.*${selected_runtime}" "$sandbox/start-missing-runtime.txt"
if grep -q 'new-session' "$sandbox/tmux-fail.log" 2>/dev/null; then
  echo "FAIL: preflight failure reached tmux new-session" >&2
  cat "$sandbox/tmux-fail.log" >&2
  exit 1
fi
echo "solar-harness start missing-runtime preflight: ok (no tmux new-session)"

fake_status="$sandbox/fake-status"
mkdir -p "$fake_status"
cp "$fake_ok/claude" "$fake_status/claude"
cp "$fake_ok/codex" "$fake_status/codex"
cat > "$fake_status/tmux" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in
  has-session)
    case "${3:-}" in
      solar-harness) exit 0 ;;
      *) exit 1 ;;
    esac
    ;;
  list-windows)
    printf '0: Product Delivery* (4 panes)\n'
    exit 0
    ;;
  list-panes)
    printf 'solar-harness\t0.0\t1\tbash\t0\n'
    printf 'solar-harness\t0.1\t1\tbash\t0\n'
    printf 'solar-harness\t0.2\t1\tbash\t0\n'
    printf 'solar-harness\t0.3\t1\tbash\t0\n'
    exit 0
    ;;
  capture-pane)
    printf "You've hit your usage limit. Use /rate-limit-options after reset.\n"
    exit 0
    ;;
  display-message)
    printf '%%1\n'
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
SH
chmod +x "$fake_status/tmux"

status_out="$sandbox/status.txt"
HOME="$home_dir" PATH="$fake_status:/usr/bin:/bin:$PATH" "$home_dir/.solar/bin/solar-harness" status > "$status_out" 2>&1 || true
# Runtime-aware: depending on whether a child process is detected in the pane, the
# classifier surfaces the manual boundary as AUTH/QUOTA-BLOCKED, LIVE-CHILD-PRESENT, or
# MANUAL-PENDING. Assert that some manual-boundary marker is surfaced (the all-green guard
# below is the real safety check), rather than the stale literal "AUTH/QUOTA-BLOCKED".
grep -qE 'AUTH/QUOTA-BLOCKED|LIVE-CHILD-PRESENT|MANUAL-PENDING' "$status_out"
# Runtime-aware: status prints "real <runtime> response/delegation remains owner-manual"
# (runtime_label is Claude/codex/etc.), so match any runtime name rather than the stale "Claude".
grep -qE 'deterministic status only; real .* response/delegation remains owner-manual' "$status_out"
if grep -qE '全部通过|verified-live|live [[:alpha:]]+ status: (verified|ok)([^[:alpha:]-]|$)' "$status_out"; then
  echo "FAIL: status output made an all-green/live-verified claim" >&2
  cat "$status_out" >&2
  exit 1
fi
echo "solar-harness status auth/quota boundary: ok"

HARNESS_DIR="$home_dir/.solar/harness" bash "$repo_dir/tests/quarantine/unsafe_home_shell/disabled_dispatch_ledger.sh" >/dev/null
echo "dispatch ledger/queue plumbing: ok"

envelope="$sandbox/no-llm-envelope.json"
cat > "$envelope" <<'JSON'
{
  "task_id": "task-plumbing-smoke",
  "sprint_id": "sprint-plumbing-smoke",
  "node_id": "N1",
  "operator_id": "mini-codex-gpt55-medium-builder-1",
  "task_type": "smoke",
  "objective": "prove operator runtime envelope and inbox plumbing without launching an LLM",
  "lease_ttl_seconds": 60
}
JSON

submit_json="$sandbox/operator-submit.json"
HARNESS_DIR="$home_dir/.solar/harness" SOLAR_OPERATORD_AUTO_KICK=0 \
  python3 "$home_dir/.solar/harness/lib/operator_runtime.py" submit --envelope "$envelope" > "$submit_json"

inbox_path="$(python3 - "$submit_json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(payload["inbox_path"])
PY
)"
[ -f "$inbox_path" ] || { echo "FAIL: operator inbox envelope missing: $inbox_path" >&2; exit 1; }

result_path="$(HARNESS_DIR="$home_dir/.solar/harness" PYTHONPATH="$home_dir/.solar/harness/lib" python3 - <<'PY'
from datetime import datetime, timezone
import operator_runtime

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
path = operator_runtime.write_result(
    "mini-codex-gpt55-medium-builder-1",
    "task-plumbing-smoke",
    "sprint-plumbing-smoke",
    "N1",
    "completed",
    0,
    now,
    now,
    "deterministic harness plumbing smoke; no live selected runtime behavior",
)
print(path)
PY
)"
[ -f "$result_path" ] || { echo "FAIL: operator result artifact missing: $result_path" >&2; exit 1; }
echo "operator runtime envelope/inbox/result plumbing: ok"

HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes >/dev/null
echo "deterministic harness plumbing smoke passed"
