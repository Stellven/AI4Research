#!/usr/bin/env bash
# check-update.sh — fetch-based `solar update` end-to-end, fully offline.
#
# Builds a throwaway local git "channel" (file:// URL, no network), installs an
# OLDER state from it, advances the channel with a new migration + version bump,
# then verifies `solar update`:
#   1. fetches the channel, sees the sha changed, reinstalls forward;
#   2. applies the pending migration (schema_version 0 -> 1) and moves the
#      reported version;
#   3. re-running reports "already up to date" and is a no-op.
# Deterministic and network-free, so it is safe as a CI gate.
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-update.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

# Keep runner toolchain state out of the sandbox HOME (matches sibling checks).
export RUSTUP_HOME="$sandbox/toolchains/rustup"
export CARGO_HOME="$sandbox/toolchains/cargo"

channel="$sandbox/channel"
home="$sandbox/home"
src="$sandbox/src/OpenSolar"
solar="$home/.solar/bin/solar"
db="$home/.solar/db/solar.db"

fail() { echo "check-update FAILED: $*" >&2; exit 1; }

# --- legacy receipt: missing repo/channel must stay on maintained origin ----
# Use a fake git transport so this regression check is deterministic and never
# reaches the network.  A pre-channel receipt still has its installed release
# version; that version must select the corresponding maintained-origin tag.
legacy_home="$sandbox/legacy-home"
legacy_solar_home="$legacy_home/.solar"
legacy_fake_bin="$sandbox/legacy-fake-bin"
legacy_git_log="$sandbox/legacy-git.log"
mkdir -p "$legacy_solar_home/bin" "$legacy_fake_bin"
cp "$repo_dir/bin/solar" "$legacy_solar_home/bin/solar"
cat > "$legacy_solar_home/install-receipt.json" <<'JSON'
{
  "version": "1.2.3",
  "git_sha": "abc1234",
  "channel": "",
  "repo": "",
  "components": ["kernel", "harness"]
}
JSON
cat > "$legacy_fake_bin/git" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_GIT_LOG"
if [ "${1:-}" = "clone" ]; then
    dest=""
    for arg in "$@"; do dest="$arg"; done
    mkdir -p "$dest"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$dest/install.sh"
    chmod +x "$dest/install.sh"
    printf '1.2.3\n' > "$dest/VERSION"
    exit 0
fi
if [ "${1:-}" = "-C" ] && [ "${3:-}" = "rev-parse" ]; then
    case "${4:-}" in
        --short) printf 'abc1234\n' ;;
        HEAD) printf 'abc1234567890\n' ;;
    esac
    exit 0
fi
exit 1
SH
chmod +x "$legacy_fake_bin/git"
FAKE_GIT_LOG="$legacy_git_log" PATH="$legacy_fake_bin:$PATH" \
    HOME="$legacy_home" SOLAR_SRC="$sandbox/legacy-src/OpenSolar" \
    "$legacy_solar_home/bin/solar" update >"$sandbox/legacy-update.log" 2>&1 \
    || { cat "$sandbox/legacy-update.log" >&2; fail "legacy receipt update target resolution"; }
grep -Fq -- "--branch v1.2.3 https://github.com/suraj-subrahmanyan/OpenSolar.git" "$legacy_git_log" \
    || { cat "$legacy_git_log" >&2; fail "legacy receipt did not use maintained origin at version-derived channel"; }
echo "legacy receipt target: ok (maintained origin @ v1.2.3)"

# A git-describe development version is not a fetchable release tag.  Refuse
# to guess instead of silently redirecting the install to an unrelated branch.
cat > "$legacy_solar_home/install-receipt.json" <<'JSON'
{
  "version": "1.2.3-4-gabc1234",
  "git_sha": "abc1234",
  "channel": "",
  "repo": "",
  "components": ["kernel", "harness"]
}
JSON
: > "$legacy_git_log"
if FAKE_GIT_LOG="$legacy_git_log" PATH="$legacy_fake_bin:$PATH" \
    HOME="$legacy_home" SOLAR_SRC="$sandbox/legacy-src-invalid/OpenSolar" \
    "$legacy_solar_home/bin/solar" update >"$sandbox/legacy-invalid.log" 2>&1; then
    fail "legacy development-version receipt guessed an update channel"
fi
grep -Fq "legacy receipt has no fetchable release channel" "$sandbox/legacy-invalid.log" \
    || { cat "$sandbox/legacy-invalid.log" >&2; fail "legacy invalid-version refusal was not actionable"; }
[ ! -s "$legacy_git_log" ] || { cat "$legacy_git_log" >&2; fail "legacy invalid-version receipt reached git"; }
echo "legacy receipt invalid version: refused before fetch"

receipt_sha() {
    HOME="$home" "$solar" version --json \
        | python3 -c 'import json,sys;print(json.load(sys.stdin)["git_sha"])'
}
schema_version() {
    HOME="$home" "$solar" doctor --json \
        | python3 -c 'import json,sys;print(json.load(sys.stdin).get("schema_version"))'
}

# --- build the local channel and install the older state ----------------------
git clone --quiet "$repo_dir" "$channel"
git -C "$channel" checkout -q -B testchan
# Make the older state truly older than the migration we add below.
git -C "$channel" -c user.email=t@example.com -c user.name=t \
    commit -q --allow-empty -m "channel baseline"

# file:// (not a bare path) so git honors --depth 1 and produces a genuine
# shallow clone -- exercising the abbreviation-length divergence the sha
# prefix-match in do_update defends against.
HOME="$home" SOLAR_REPO="file://$channel" SOLAR_CHANNEL="testchan" SOLAR_SRC="$src" \
    bash "$channel/get-solar.sh" \
    --yes --components kernel,harness --fake-keys --skip-llm-cli --skip-py-deps \
    >"$sandbox/install.log" 2>&1 \
    || { cat "$sandbox/install.log" >&2; fail "initial install from local channel"; }

sha_a="$(receipt_sha)"
[ -n "$sha_a" ] && [ "$sha_a" != "unknown" ] || fail "no real git_sha after install ($sha_a)"
[ "$(schema_version)" = "0" ] || fail "baseline schema_version should be 0, got $(schema_version)"

# --- advance the channel: new migration + version bump ------------------------
mkdir -p "$channel/core/db/migrations"
printf 'CREATE TABLE IF NOT EXISTS check_update_probe (x INTEGER);\n' \
    > "$channel/core/db/migrations/0001-check-update-probe.sql"
printf '9.9.9-check-update\n' > "$channel/VERSION"
git -C "$channel" add core/db/migrations/0001-check-update-probe.sql VERSION
git -C "$channel" -c user.email=t@example.com -c user.name=t \
    commit -q -m "advance channel: probe migration + version"
full_b="$(git -C "$channel" rev-parse HEAD)"

# --- solar update: must move forward and apply the migration ------------------
HOME="$home" SOLAR_SRC="$src" "$solar" update \
    --fake-keys --skip-llm-cli --skip-py-deps \
    >"$sandbox/update.log" 2>&1 \
    || { cat "$sandbox/update.log" >&2; fail "solar update (forward) returned nonzero"; }

# git_sha is abbreviated and the abbreviation length differs between the full
# channel repo and the shallow update clone, so compare by prefix of the full
# sha rather than by equal short strings.
sha_now="$(receipt_sha)"
[ "$sha_now" != "$sha_a" ] || fail "update did not move the sha off the baseline ($sha_a)"
case "$full_b" in
    "$sha_now"*) : ;;
    *) fail "update sha $sha_now is not a prefix of the advanced channel sha $full_b" ;;
esac
[ "$(schema_version)" = "1" ] || fail "migration not applied; schema_version=$(schema_version)"
ver_now="$(HOME="$home" "$solar" version --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])')"
[ "$ver_now" = "9.9.9-check-update" ] || fail "version did not move (got $ver_now)"
SOLAR_DB="$db" python3 - <<'PY' || fail "probe migration table missing after update"
import os, sqlite3
c = sqlite3.connect(os.environ["SOLAR_DB"])
names = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
raise SystemExit(0 if "check_update_probe" in names else 1)
PY
echo "update forward: ok ($sha_a -> $sha_now, schema_version 0 -> 1, version $ver_now)"

# --- solar update again: already up to date, no-op ----------------------------
HOME="$home" SOLAR_SRC="$src" "$solar" update \
    --fake-keys --skip-llm-cli --skip-py-deps \
    >"$sandbox/update2.log" 2>&1 \
    || { cat "$sandbox/update2.log" >&2; fail "second update returned nonzero"; }
grep -q "already up to date" "$sandbox/update2.log" \
    || { cat "$sandbox/update2.log" >&2; fail "second update was not a no-op"; }
[ "$(schema_version)" = "1" ] || fail "schema_version drifted on no-op update"
echo "update no-op: ok"

echo "check-update: ok"
