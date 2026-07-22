#!/usr/bin/env bash
# verify-macos-package.sh — macOS check for an UNSIGNED / ad-hoc Solar build.
#
# Project stance: NO Apple Developer cert, NO notarization. We ship an AD-HOC-signed (mac.identity
# "-") .app/.dmg; Gatekeeper fires on first run and users click through (right-click Open; on
# Sequoia: System Settings -> Privacy & Security -> "Open Anyway" — see docs/DOWNLOAD.md). So this
# does NOT check notarization. It checks the two things that actually matter for an unsigned build:
#   1. AD-HOC SIGNED + valid — REQUIRED for Apple Silicon (arm64 SIGKILLs unsigned native code, a
#      launch failure separate from any Gatekeeper prompt). identity:null FAILS this; identity:"-"
#      PASSES. This is the single check that decides whether the app runs on Apple Silicon at all.
#   2. Bundle/dmg structurally sound, and (with --launch) it actually starts.
#
# Run on macOS (a mac runner / real Mac / tart VM). For --launch, quarantine is stripped first (CI
# has no human to click "Open Anyway").
#
# Usage: bash verify-macos-package.sh <path-to .app | .dmg> [--launch]
set -uo pipefail

artifact="${1:-}"
[ -n "$artifact" ] || { echo "usage: $0 <.app|.dmg> [--launch]" >&2; exit 64; }
[ -e "$artifact" ] || { echo "not found: $artifact" >&2; exit 64; }
[ "$(uname -s)" = "Darwin" ] || { echo "macOS only (needs codesign/hdiutil)" >&2; exit 64; }
do_launch=0; [ "${2:-}" = "--launch" ] && do_launch=1
ext="${artifact##*.}"
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
fail=0
section() { printf '\n=== %s ===\n' "$1"; }
run() { local name="$1"; shift; if "$@" >"$tmp" 2>&1; then echo "PASS  $name"; else echo "FAIL  $name"; sed 's/^/      /' "$tmp"; fail=1; fi; }

# Resolve the .app to inspect (mount the dmg if needed).
app="$artifact"; mnt=""
if [ "$ext" = "dmg" ]; then
    section "dmg structure"
    run "hdiutil verify" hdiutil verify "$artifact"
    mnt="$(mktemp -d)"
    if hdiutil attach "$artifact" -nobrowse -readonly -mountpoint "$mnt" >/dev/null 2>&1; then
        app="$(/usr/bin/find "$mnt" -maxdepth 2 -name '*.app' -type d | head -1)"
        trap 'hdiutil detach "$mnt" >/dev/null 2>&1; rm -f "$tmp"' EXIT
        echo "  mounted; app: ${app:-<none found>}"
    else
        echo "FAIL  could not mount dmg"; exit 1
    fi
fi
[ -n "$app" ] && [ -d "$app" ] || { echo "FAIL  no .app found to verify" >&2; exit 1; }

section "ad-hoc signature (the Apple-Silicon launch gate)"
codesign -dv --verbose=4 "$app" 2>&1 | grep -iE 'Authority|Signature|Identifier|flags' | sed 's/^/  /' || echo "  (no signature)"
run "ad-hoc signature present" bash -c "codesign -dv --verbose=4 '$app' 2>&1 | grep -qiE 'Signature=adhoc'"
run "signature verifies (--deep --strict)" codesign --verify --deep --strict --verbose=2 "$app"

section "bundle structure"
run "Info.plist present" test -f "$app/Contents/Info.plist"
run "main executable present" bash -c "test -x \"$app/Contents/MacOS/\$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' \"$app/Contents/Info.plist\")\""

if [ "$do_launch" = "1" ]; then
    section "launch (quarantine stripped — no Gatekeeper prompt in CI)"
    xattr -dr com.apple.quarantine "$app" 2>/dev/null || true
    # SELFTEST mode boots the runtime, loads the bundled UI, asserts, and exits — proves the
    # ad-hoc bundle actually runs (the real Apple-Silicon SIGKILL would show as an immediate exit).
    bin="$app/Contents/MacOS/$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app/Contents/Info.plist")"
    if SOLAR_DESKTOP_SELFTEST=1 "$bin" >"$tmp" 2>&1; then
        if grep -q 'SELFTEST OK' "$tmp"; then echo "PASS  launches + SELFTEST OK"; else echo "FAIL  launched but no SELFTEST OK"; sed 's/^/      /' "$tmp"; fail=1; fi
    else
        echo "FAIL  app did not launch cleanly (Apple-Silicon SIGKILL? check ad-hoc signing)"; sed 's/^/      /' "$tmp"; fail=1
    fi
fi

section "RESULT"
if [ "$fail" = "0" ]; then
    echo "GREENLIGHT (unsigned/ad-hoc): runs on Apple Silicon; ship with the Gatekeeper click-through (docs/DOWNLOAD.md)."
else
    echo "BLOCKED: see failures above. If the ad-hoc check failed, set mac.identity \"-\" (not null) in desktop/package.json."
fi
exit "$fail"
