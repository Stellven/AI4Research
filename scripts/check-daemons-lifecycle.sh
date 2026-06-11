#!/usr/bin/env bash
# daemons lifecycle gate — install the daemons component into a sandbox and
# assert the service file is RENDERED to the right path, structurally valid,
# recorded, and then REMOVED by uninstall. Real daemon START is owner-hardware-
# verified (CI runners have no user-session bus); this proves render + placement
# + removal, which is everything that does NOT need a live service manager.
set -eu

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
home="$(mktemp -d "${TMPDIR:-/tmp}/solar-daemons.XXXXXX")"
cleanup() {
    HOME="$home" "$home/.solar/bin/solar" uninstall --yes >/dev/null 2>&1 || true
    rm -rf "$home"
}
trap cleanup EXIT

# The daemons component installs a systemd --user unit on linux only when
# systemctl is present; without it the component skips by design, so there is
# nothing to assert here (covered by check-daemons-render.sh + the manual run).
if ! command -v systemctl >/dev/null 2>&1; then
    echo "no systemctl on this runner; daemons lifecycle is a manual checklist item — skipping"
    exit 0
fi

# kernel,daemons only: daemons needs bun present (preflight) but does not run it
# to render; core-runtime is not needed to render/place/remove the unit file.
HOME="$home" "$repo_dir/install.sh" --yes --components kernel,daemons --fake-keys --skip-llm-cli

unit="$home/.config/systemd/user/solar-daemon.service"
[ -f "$unit" ] || { echo "FAIL: daemon unit not rendered at $unit" >&2; exit 1; }
if grep -qF '{{' "$unit"; then echo "FAIL: rendered unit has unresolved {{" >&2; exit 1; fi
grep -qE '^\[Service\]' "$unit" || { echo "FAIL: rendered unit missing [Service]" >&2; exit 1; }
grep -qE '^ExecStart=/' "$unit" || { echo "FAIL: rendered unit ExecStart is not absolute" >&2; exit 1; }
grep -q 'solar-daemon.service' "$home/.solar/registered-daemons.txt" 2>/dev/null \
    || { echo "FAIL: daemon not recorded in registered-daemons.txt" >&2; exit 1; }
echo "daemons render+placement: ok ($unit)"

HOME="$home" "$home/.solar/bin/solar" uninstall --yes
if [ -e "$unit" ]; then echo "FAIL: uninstall left the daemon unit: $unit" >&2; exit 1; fi
echo "daemons lifecycle: ok (rendered, structurally valid, recorded, removed by uninstall)"
