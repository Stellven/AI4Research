#!/usr/bin/env bash
# verify-macos-package.sh — one-command macOS package verification.
#
# Runs the full signature/Gatekeeper/notarization chain and either prints GREENLIGHT or names the
# exact failing check. Handles BOTH states:
#   - UNSIGNED / ad-hoc (our V1 stance, identity:null): verifies the bundle is structurally valid
#     and reports that Gatekeeper will block first-run (users use the right-click / "Open Anyway"
#     bypass — see docs/DOWNLOAD.md). NOT a failure — it's the V1 design.
#   - Developer ID signed + notarized (a future signed build): runs codesign -> spctl (per artifact)
#     -> stapler -> syspolicy_check; any of those failing is a real BLOCK.
#
# Run on macOS (a hosted mac runner or a real Mac) — needs codesign/spctl/syspolicy_check.
#
# Usage: bash verify-macos-package.sh <path-to .app | .dmg | .pkg> [--simulate-quarantine]
#   --simulate-quarantine: set com.apple.quarantine first, so the checks reproduce the real
#     download experience (CI-built / curl'd artifacts lack the bit, so spctl alone doesn't mirror
#     what a user hits double-clicking a downloaded DMG).
set -uo pipefail

artifact="${1:-}"
[ -n "$artifact" ] || { echo "usage: $0 <.app|.dmg|.pkg> [--simulate-quarantine]" >&2; exit 64; }
[ -e "$artifact" ] || { echo "not found: $artifact" >&2; exit 64; }
[ "$(uname -s)" = "Darwin" ] || { echo "macOS only (needs codesign/spctl/syspolicy_check)" >&2; exit 64; }
simulate=0; [ "${2:-}" = "--simulate-quarantine" ] && simulate=1
ext="${artifact##*.}"
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
fail=0
section() { printf '\n=== %s ===\n' "$1"; }
run() { # <name> <cmd...>  -> PASS/FAIL, records failure
    local name="$1"; shift
    if "$@" >"$tmp" 2>&1; then echo "PASS  $name"; else echo "FAIL  $name"; sed 's/^/      /' "$tmp"; fail=1; fi
}

if [ "$simulate" = "1" ] && [ "$ext" = "app" ]; then
    section "simulate download quarantine"
    xattr -w com.apple.quarantine "0081;00000000;Solar;" "$artifact" && echo "  com.apple.quarantine set"
fi

# Is it Developer ID signed (vs unsigned/ad-hoc)?
signed_devid=0
if codesign -dv --verbose=4 "$artifact" 2>&1 | grep -qE 'Authority=Developer ID Application'; then
    signed_devid=1
fi

section "codesign — signing identity"
codesign -dv --verbose=4 "$artifact" 2>&1 | grep -iE 'Authority|Signature|Identifier|TeamIdentifier|adhoc' | sed 's/^/  /' || echo "  (no signature)"

if [ "$signed_devid" = "0" ]; then
    # ---- UNSIGNED / ad-hoc path (V1) ----
    section "unsigned bundle structure (V1: ad-hoc / identity:null)"
    case "$ext" in
        app)
            run "Info.plist present" test -f "$artifact/Contents/Info.plist"
            run "executable present" bash -c "test -x \"$artifact/Contents/MacOS/\$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' \"$artifact/Contents/Info.plist\")\""
            run "ad-hoc signature valid" codesign --verify --deep --strict --verbose=2 "$artifact"
            ;;
        dmg) run "dmg verifies (hdiutil)" hdiutil verify "$artifact" ;;
        pkg) run "pkg payload listable" bash -c "pkgutil --payload-files \"$artifact\" >/dev/null" ;;
    esac
    section "RESULT"
    echo "UNSIGNED (expected for V1). Bundle is structurally valid."
    echo "Gatekeeper WILL block first-run — ship the right-click / 'Open Anyway' bypass (docs/DOWNLOAD.md)."
    echo "When you sign with a Developer ID + notarize, re-run this for the full chain."
    exit "$fail"
fi

# ---- Developer ID signed + notarized path ----
section "codesign — verify + notarized requirement"
run "codesign --verify --deep --strict" codesign --verify --deep --strict --verbose=2 "$artifact"
run "codesign notarized requirement" codesign -vvv -R="notarized" --check-notarization "$artifact"

section "Gatekeeper (spctl, per artifact type)"
case "$ext" in
    app) run "spctl assess exec" spctl -a -t exec -vv "$artifact" ;;
    dmg) run "spctl assess open (dmg)" spctl -a -t open -vvv --context context:primary-signature "$artifact" ;;
    pkg) run "spctl assess install (pkg)" spctl -a -t install -vvv "$artifact" ;;
esac

section "notarization staple"
run "stapler validate" xcrun stapler validate "$artifact"

section "syspolicy_check (stricter than spctl — catches what spctl waves through)"
if command -v syspolicy_check >/dev/null 2>&1 && [ "$ext" = "app" ]; then
    run "syspolicy_check distribution" syspolicy_check distribution "$artifact"
else
    echo "  (syspolicy_check needs macOS 14.4+ and a .app target — skipped)"
fi

section "RESULT"
if [ "$fail" = "0" ]; then
    echo "GREENLIGHT: $artifact passes signature + Gatekeeper + notarization."
else
    echo "BLOCKED: one or more checks failed (see above)."
fi
exit "$fail"
