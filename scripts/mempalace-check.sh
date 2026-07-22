#!/usr/bin/env bash
# mempalace-check.sh — deps-light CI gate for the mempalace component.
#
# The real venv + heavy-deps install (chromadb + sentence-transformers, multi-GB)
# and the venv import smoke are a manual/nightly check (see the mempalace handoff
# in WORKLOG.md). This gate validates everything that does NOT need the multi-GB
# download:
#   (a) requirements resolve  (pip --dry-run --ignore-installed --no-deps)
#   (b) missing required var fails loud with the exact --set remedy, no residue
#   (c) deps-light install renders config.yaml clean, doctor ok, venv present,
#       idempotent, residue-free uninstall, no $HOME/.cache/pip leak
#   (d) MCP registration emits the correct `claude mcp add` and uninstall the
#       matching `claude mcp remove` (fake claude — no real CLI required)
set -e

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-mempalace.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT
home_dir="$sandbox/home"
vault="$sandbox/vault"
mkdir -p "$home_dir" "$vault"
install_sh="$repo_dir/install.sh"

# Keep ambient toolchain state out of the asserted sandbox HOME. On a GH runner
# the rust tooling lazily initializes $HOME/.rustup the first time a rustup
# proxy runs with HOME pointed here; that is a runner artifact, not Solar
# residue. Redirect it (and cargo) to a scratch dir cleaned with the sandbox so
# the strict whole-HOME residue assertion stays valid.
export RUSTUP_HOME="$sandbox/toolchains/rustup"
export CARGO_HOME="$sandbox/toolchains/cargo"

echo "== (a) requirements resolution =="
python3 -m pip install --dry-run --ignore-installed --no-deps \
    -r requirements/mempalace.txt >/dev/null
echo "requirements resolve: ok"

echo "== (b) missing VAULT_PATH fails loud =="
if HOME="$home_dir" "$install_sh" --yes --components kernel,mempalace \
        --fake-keys --skip-llm-cli --skip-py-deps >"$sandbox/neg.out" 2>&1; then
    echo "FAIL: install without VAULT_PATH unexpectedly succeeded" >&2
    exit 1
fi
if ! grep -q "mempalace requires VAULT_PATH; pass --set VAULT_PATH=" "$sandbox/neg.out"; then
    echo "FAIL: missing-var error lacked the exact --set remedy" >&2
    cat "$sandbox/neg.out" >&2
    exit 1
fi
if [ -n "$(find "$home_dir" -mindepth 1 2>/dev/null)" ]; then
    echo "FAIL: failed install left residue" >&2
    find "$home_dir" -mindepth 1 >&2
    exit 1
fi
echo "missing-var gate: ok"

echo "== (c) deps-light install round-trip =="
HOME="$home_dir" "$install_sh" --yes --components kernel,mempalace \
    --fake-keys --skip-llm-cli --skip-py-deps --set VAULT_PATH="$vault"

cfg="$home_dir/.solar/mempalace/config.yaml"
[ -f "$cfg" ] || { echo "FAIL: config.yaml missing" >&2; exit 1; }
if grep -q '{{' "$cfg"; then
    echo "FAIL: unresolved {{ in config.yaml" >&2
    grep -n '{{' "$cfg" >&2
    exit 1
fi
grep -q "^data_dir: $vault$" "$cfg" || {
    echo "FAIL: data_dir not rendered to VAULT_PATH" >&2
    cat "$cfg" >&2
    exit 1
}
[ -x "$home_dir/.solar/venv/bin/python" ] || { echo "FAIL: venv python missing" >&2; exit 1; }
echo "config.yaml render + venv: ok"

HOME="$home_dir" "$home_dir/.solar/bin/solar" doctor --json > "$sandbox/doctor.json"
python3 - "$sandbox/doctor.json" <<'PY'
import json
import sys

d = json.load(open(sys.argv[1]))
if d.get("verdict") != "ok":
    raise SystemExit(f"doctor verdict not ok: {d!r}")
if "mempalace" not in d.get("components", []):
    raise SystemExit("mempalace not in doctor components")
print("doctor verdict: ok")
PY

HOME="$home_dir" "$install_sh" --yes --components kernel,mempalace \
    --fake-keys --skip-llm-cli --skip-py-deps --set VAULT_PATH="$vault" >/dev/null
sentinel_count="$(grep -c '<!-- BEGIN OPENSOLAR -->' "$home_dir/.claude/CLAUDE.md")"
[ "$sentinel_count" = "1" ] || { echo "FAIL: expected 1 sentinel, found $sentinel_count" >&2; exit 1; }
echo "idempotent reinstall: ok"

echo "== (d) MCP register/remove (fake claude) =="
fakebin="$sandbox/bin"
mkdir -p "$fakebin"
mcp_log="$sandbox/claude-mcp.log"
cat > "$fakebin/claude" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$mcp_log"
exit 0
EOF
chmod +x "$fakebin/claude"

# Reinstall with the fake claude on PATH and WITHOUT --skip-llm-cli so
# mcp_register actually runs.
HOME="$home_dir" PATH="$fakebin:$PATH" "$install_sh" --yes --components kernel,mempalace \
    --fake-keys --skip-py-deps --set VAULT_PATH="$vault" >/dev/null
grep -q "mcp add mempalace --scope user -- .*venv/bin/python .*mempalace_mcp_server.py" "$mcp_log" || {
    echo "FAIL: 'claude mcp add' not emitted correctly" >&2
    cat "$mcp_log" >&2
    exit 1
}
echo "mcp add: ok"

HOME="$home_dir" PATH="$fakebin:$PATH" "$home_dir/.solar/bin/solar" uninstall --yes >/dev/null
grep -q "mcp remove mempalace" "$mcp_log" || {
    echo "FAIL: 'claude mcp remove' not emitted" >&2
    cat "$mcp_log" >&2
    exit 1
}
echo "mcp remove: ok"

if [ -e "$home_dir/.cache/pip" ]; then
    echo "FAIL: pip leaked into \$HOME/.cache/pip" >&2
    exit 1
fi
if [ -n "$(find "$home_dir" -mindepth 1 2>/dev/null)" ]; then
    echo "FAIL: uninstall left residue" >&2
    find "$home_dir" -mindepth 1 >&2
    exit 1
fi
echo "residue-free + no pip HOME leak: ok"

echo "mempalace-check passed"
