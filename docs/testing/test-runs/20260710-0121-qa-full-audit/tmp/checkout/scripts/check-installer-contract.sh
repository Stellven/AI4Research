#!/usr/bin/env bash
# check-installer-contract.sh — deterministic installer contract checks that do
# not need a TTY. The TTY wizard paths live in smoke-installer-wizard-pty.py.
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-contract.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

# GitHub-hosted runners can lazily initialize rustup when HOME points at a
# strict residue-check sandbox, even though this contract is not testing Rust.
# Keep runner toolchain state in the outer scratch dir, matching
# scripts/mempalace-check.sh.
export RUSTUP_HOME="$sandbox/toolchains/rustup"
export CARGO_HOME="$sandbox/toolchains/cargo"

snapshot_home() {
    home="$1"
    out="$2"
    find "$home" -mindepth 1 -print 2>/dev/null | sort > "$out"
}

assert_empty_home() {
    home="$1"
    label="$2"
    residue="$sandbox/$label.residue"
    snapshot_home "$home" "$residue"
    if [ -s "$residue" ]; then
        echo "$label FAILED: unexpected files under HOME:" >&2
        cat "$residue" >&2
        exit 1
    fi
}

assert_components() {
    home="$1"
    expected="$2"
    python3 - "$home/.solar/install-receipt.json" "$expected" <<'PY'
import json
import sys

receipt, expected = sys.argv[1], [x for x in sys.argv[2].split(",") if x]
with open(receipt, encoding="utf-8") as f:
    actual = json.load(f).get("components", [])
if actual != expected:
    raise SystemExit(f"components mismatch: expected {expected!r}, got {actual!r}")
PY
}

run_uninstall() {
    home="$1"
    HOME="$home" "$home/.solar/bin/solar" uninstall --yes >/dev/null
    assert_empty_home "$home" "uninstall"
}

assert_doctor_ok() {
    doctor_json="$1"
    python3 - "$doctor_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
if data.get("verdict") != "ok":
    raise SystemExit(f"doctor verdict is not ok: {data!r}")
PY
}

echo "== --yes path remains non-prompting =="
home="$sandbox/yes"
mkdir -p "$home"
HOME="$home" "$repo_dir/install.sh" \
    --yes --components kernel,harness --fake-keys --skip-llm-cli \
    </dev/null >/dev/null
assert_components "$home" "kernel,harness"
run_uninstall "$home"
echo "--yes path: ok"

echo "== --components selection remains explicit =="
home="$sandbox/components-kernel"
mkdir -p "$home"
HOME="$home" "$repo_dir/install.sh" \
    --yes --components kernel --fake-keys --skip-llm-cli \
    </dev/null >/dev/null
assert_components "$home" "kernel"
run_uninstall "$home"

home="$sandbox/components-autoadd"
mkdir -p "$home"
HOME="$home" "$repo_dir/install.sh" \
    --yes --components harness --fake-keys --skip-llm-cli \
    </dev/null >/dev/null
assert_components "$home" "kernel,harness"
run_uninstall "$home"
echo "--components path: ok"

echo "== full-path solar discovers custom install roots =="
home="$sandbox/custom-root-home"
solar_root="$sandbox/custom root/solar home"
claude_root="$sandbox/custom root/claude dir"
mkdir -p "$home"
HOME="$home" "$repo_dir/install.sh" \
    --yes --components kernel \
    --solar-home "$solar_root" \
    --claude-dir "$claude_root" \
    --fake-keys --skip-llm-cli --skip-py-deps \
    </dev/null >/dev/null
(unset SOLAR_HOME CLAUDE_DIR RECEIPT_PATH; HOME="$home" "$solar_root/bin/solar" doctor --json > "$sandbox/custom-root-doctor.json")
assert_doctor_ok "$sandbox/custom-root-doctor.json"

override_home="$sandbox/custom-root-override-home"
override_solar="$sandbox/custom override/solar home"
override_claude="$sandbox/custom override/claude dir"
mkdir -p "$override_home"
HOME="$override_home" "$repo_dir/install.sh" \
    --yes --components kernel \
    --solar-home "$override_solar" \
    --claude-dir "$override_claude" \
    --fake-keys --skip-llm-cli --skip-py-deps \
    </dev/null >/dev/null
HOME="$home" SOLAR_HOME="$override_solar" CLAUDE_DIR="$override_claude" \
    "$solar_root/bin/solar" doctor --json > "$sandbox/custom-root-override-doctor.json"
assert_doctor_ok "$sandbox/custom-root-override-doctor.json"

(unset SOLAR_HOME CLAUDE_DIR RECEIPT_PATH; HOME="$home" "$solar_root/bin/solar" uninstall --yes >/dev/null)
HOME="$override_home" SOLAR_HOME="$override_solar" CLAUDE_DIR="$override_claude" \
    "$override_solar/bin/solar" uninstall --yes >/dev/null
[ ! -e "$solar_root" ] || { echo "custom-root FAILED: self-located uninstall left $solar_root" >&2; exit 1; }
[ ! -e "$claude_root" ] || { echo "custom-root FAILED: self-located uninstall left $claude_root" >&2; exit 1; }
[ ! -e "$override_solar" ] || { echo "custom-root FAILED: env override uninstall left $override_solar" >&2; exit 1; }
[ ! -e "$override_claude" ] || { echo "custom-root FAILED: env override uninstall left $override_claude" >&2; exit 1; }
assert_empty_home "$home" "custom-root-home"
assert_empty_home "$override_home" "custom-root-override-home"
echo "custom-root full-path discovery: ok"

echo "== --set required vars remain pre-provided =="
home="$sandbox/set-vars"
vault="$sandbox/vault"
mkdir -p "$home" "$vault"
HOME="$home" "$repo_dir/install.sh" \
    --yes --components kernel,mempalace --set "VAULT_PATH=$vault" \
    --fake-keys --skip-llm-cli --skip-py-deps \
    </dev/null >/dev/null
assert_components "$home" "kernel,mempalace"
grep -Fq "$vault" "$home/.solar/mempalace/config.yaml" || {
    echo "--set path FAILED: VAULT_PATH was not rendered into mempalace config" >&2
    exit 1
}
run_uninstall "$home"
echo "--set required vars: ok"

echo "== non-TTY without --yes still fails loud =="
home="$sandbox/non-tty"
mkdir -p "$home"
out="$sandbox/non-tty.out"
if HOME="$home" "$repo_dir/install.sh" --components kernel </dev/null >"$out" 2>&1; then
    echo "non-TTY FAILED: install succeeded without --yes" >&2
    exit 1
fi
grep -q "non-interactive input detected; rerun with --yes" "$out" || {
    echo "non-TTY FAILED: expected loud --yes remedy, got:" >&2
    cat "$out" >&2
    exit 1
}
assert_empty_home "$home" "non-tty"
echo "non-TTY loud failure: ok"

echo "== --dry-run --yes writes zero files =="
home="$sandbox/dry-yes"
mkdir -p "$home"
before="$sandbox/dry-yes.before"
after="$sandbox/dry-yes.after"
snapshot_home "$home" "$before"
HOME="$home" "$repo_dir/install.sh" \
    --yes --components kernel,harness --dry-run --fake-keys --skip-llm-cli \
    </dev/null >/dev/null
snapshot_home "$home" "$after"
if ! cmp -s "$before" "$after"; then
    echo "dry-run FAILED: filesystem snapshot changed for --yes path" >&2
    diff -u "$before" "$after" >&2 || true
    exit 1
fi
echo "--dry-run --yes zero-write: ok"

echo "check-installer-contract passed"
