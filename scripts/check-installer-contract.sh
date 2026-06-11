#!/usr/bin/env bash
# check-installer-contract.sh — deterministic installer contract checks that do
# not need a TTY. The TTY wizard paths live in smoke-installer-wizard-pty.py.
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-contract.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

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
