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

# kernel,daemons,status-daemon: neither needs its target runtime present to render/place/remove the
# unit file. systemctl --user enable harmlessly no-ops on the sandbox unit path (not the real
# manager search path), so nothing is actually started.
HOME="$home" "$repo_dir/install.sh" --yes --components kernel,daemons,status-daemon --fake-keys --skip-llm-cli

# assert_unit <unit-path> <registered-name> <label>
assert_unit() {
    u="$1"; reg="$2"; label="$3"
    [ -f "$u" ] || { echo "FAIL: $label unit not rendered at $u" >&2; exit 1; }
    if grep -qF '{{' "$u"; then echo "FAIL: $label unit has unresolved {{" >&2; exit 1; fi
    grep -qE '^\[Service\]' "$u" || { echo "FAIL: $label unit missing [Service]" >&2; exit 1; }
    grep -qE '^ExecStart=/' "$u" || { echo "FAIL: $label unit ExecStart is not absolute" >&2; exit 1; }
    grep -q "$reg" "$home/.solar/registered-daemons.txt" 2>/dev/null \
        || { echo "FAIL: $label not recorded in registered-daemons.txt" >&2; exit 1; }
    echo "$label render+placement: ok ($u)"
}

unit="$home/.config/systemd/user/solar-daemon.service"
status_unit="$home/.config/systemd/user/solar-status-server.service"
assert_unit "$unit" "solar-daemon.service" "daemons"
assert_unit "$status_unit" "solar-status-server.service" "status-daemon"

HOME="$home" "$home/.solar/bin/solar" uninstall --yes
if [ -e "$unit" ]; then echo "FAIL: uninstall left the daemon unit: $unit" >&2; exit 1; fi
if [ -e "$status_unit" ]; then echo "FAIL: uninstall left the status-daemon unit: $status_unit" >&2; exit 1; fi
echo "daemons lifecycle: ok (daemons + status-daemon rendered, valid, recorded, removed by uninstall)"
