#!/usr/bin/env bash
# Release-coherence gate: the version/channel/mode/reference invariants that
# let a cut tag actually install, update, and verify itself.
#
# Born from the 2026-07-08 system-test bench (P6 corpus PKG-001..004): rc.8
# shipped a get-solar.sh channel default still on rc.6, so `solar update`
# DOWNGRADED fresh rc.8 installs; the pipx package carried three different
# versions and pointed at the wrong repo; three verification scripts were
# 644; and a smoke referenced a script that did not exist. Every check here
# makes one of those classes structurally impossible to ship again.
#
# Run standalone from the repo root, or via release-cut.sh (which runs it
# inside the scratch orphan tree before a cut).
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
FAIL=0

log() { printf '%s\n' "$*"; }
fail() { log "FAIL: $*"; FAIL=1; }
ok() { log "ok: $*"; }

VERSION="$(tr -d '[:space:]' < VERSION 2>/dev/null || true)"
if [ -z "$VERSION" ]; then
    fail "VERSION file missing or empty"
    echo "release-coherence: FAIL"; exit 1
fi
TAG="v$VERSION"
# PEP 440 form for the pipx package: 1.0.0-rc.8 -> 1.0.0rc8
PEP440="$(printf '%s' "$VERSION" | sed 's/-rc\./rc/')"

# ---- check 1: get-solar.sh channel default == the version being cut -------
log "check 1: get-solar.sh SOLAR_CHANNEL default == $TAG (PKG-001)"
CHANNEL_DEFAULT="$(sed -n 's/^SOLAR_CHANNEL="\${SOLAR_CHANNEL:-\([^}]*\)}"$/\1/p' get-solar.sh)"
if [ -z "$CHANNEL_DEFAULT" ]; then
    fail "could not parse SOLAR_CHANNEL default from get-solar.sh"
elif [ "$CHANNEL_DEFAULT" != "$TAG" ]; then
    fail "get-solar.sh channel default is '$CHANNEL_DEFAULT', VERSION is '$VERSION' (installs will record the wrong update channel)"
else
    ok "channel default $CHANNEL_DEFAULT"
fi

# ---- check 2: pipx package version + URL coherence (PKG-003) --------------
log "check 2: pipx distribution coherent with VERSION"
PIPX=distribution/pipx
PIPX_VERSIONS="$(python3 - <<'PY' | tr -d '\r'
import ast
import tomllib
from pathlib import Path

root = Path("distribution/pipx")
project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
module = ast.parse((root / "opensolar_cli/__init__.py").read_text(encoding="utf-8"))
init_version = ""
for statement in module.body:
    if not isinstance(statement, ast.Assign):
        continue
    if any(isinstance(target, ast.Name) and target.id == "__version__" for target in statement.targets):
        init_version = ast.literal_eval(statement.value)
        break
print(project.get("project", {}).get("version", ""))
print(init_version)
PY
)"
PYPROJECT_V="$(printf '%s\n' "$PIPX_VERSIONS" | sed -n '1p')"
INIT_V="$(printf '%s\n' "$PIPX_VERSIONS" | sed -n '2p')"
[ "$PYPROJECT_V" = "$PEP440" ] && ok "pyproject version $PYPROJECT_V" \
    || fail "pipx pyproject version '$PYPROJECT_V' != '$PEP440'"
[ "$INIT_V" = "$PEP440" ] && ok "__init__ version $INIT_V" \
    || fail "pipx __init__ version '$INIT_V' != '$PEP440'"
if grep -q "raw.githubusercontent.com/suraj-subrahmanyan/OpenSolar/$TAG/" "$PIPX/opensolar_cli/cli.py"; then
    ok "PUBLIC_GET_SOLAR_URL pinned to the maintained repo at $TAG"
else
    fail "pipx cli.py PUBLIC_GET_SOLAR_URL is not the maintained repo at $TAG"
fi
# Judge only tracked release inputs. Recursive filesystem grep lets local build
# residue (for example an untracked *.egg-info directory) veto a release even
# though the public orphan cannot contain it.
STALE_TAGS="$(git grep -hoE 'v1\.0\.0-rc\.[0-9]+' -- "$PIPX" \
    | grep -v "^$TAG$" | sort -u || true)"
if [ -n "$STALE_TAGS" ]; then
    fail "pipx tree references stale tags: $(printf '%s' "$STALE_TAGS" | tr '\n' ' ')"
else
    ok "no stale tag references in $PIPX"
fi

# ---- check 2b: every public version-bearing surface is coherent ------------
# A release is installed from more than VERSION/get-solar/pipx: the README,
# first-session guide, PowerShell bootstrap, and desktop builders all embed or
# package a release identity.  Scan the canonical public surfaces together so
# a tag cannot publish mixed-version instructions or rc.8 desktop artifacts
# under an rc.9 workflow run.
log "check 2b: public install/docs/desktop surfaces coherent with VERSION"
VERSIONED_PATHS=(
    README.md
    INSTALL.md
    docs/FIRST-SESSION.md
    get-solar.sh
    install.ps1
    distribution/pipx
    desktop/package.json
    desktop/package-lock.json
    tests/desktop/bootstrap-contract.test.cjs
)
for path in "${VERSIONED_PATHS[@]}"; do
    [ -e "$path" ] || fail "version-bearing surface missing: $path"
done
PUBLIC_STALE_TAGS="$(git grep -hoE 'v1\.0\.0-rc\.[0-9]+' -- "${VERSIONED_PATHS[@]}" \
    | grep -v "^$TAG$" | sort -u || true)"
if [ -n "$PUBLIC_STALE_TAGS" ]; then
    fail "public version-bearing surfaces reference stale tags: $(printf '%s' "$PUBLIC_STALE_TAGS" | tr '\n' ' ')"
else
    ok "no stale tags in public version-bearing surfaces"
fi
DESKTOP_VERSIONS="$(python3 - <<'PY' | tr -d '\r'
import json
from pathlib import Path

pkg = json.loads(Path("desktop/package.json").read_text(encoding="utf-8"))
lock = json.loads(Path("desktop/package-lock.json").read_text(encoding="utf-8"))
print(pkg.get("version", ""))
print(lock.get("version", ""))
print((lock.get("packages") or {}).get("", {}).get("version", ""))
PY
)"
if [ "$DESKTOP_VERSIONS" != "$(printf '%s\n%s\n%s' "$VERSION" "$VERSION" "$VERSION")" ]; then
    fail "desktop package versions are not all '$VERSION': $(printf '%s' "$DESKTOP_VERSIONS" | tr '\n' ' ')"
else
    ok "desktop package + lock versions $VERSION"
fi

# ---- check 3: every shebang script in scripts/ is executable (PKG-002) ----
log "check 3: scripts/*.sh with shebangs are 755 in the index"
BAD_MODE=0
while IFS= read -r line; do
    mode="${line%% *}"
    path="${line##*	}"
    case "$(head -c2 "$path" 2>/dev/null)" in
        '#!')
            if [ "$mode" != "100755" ]; then
                fail "$path has a shebang but index mode $mode"
                BAD_MODE=1
            fi
            ;;
    esac
done < <(git ls-files -s -- 'scripts/*.sh')
[ "$BAD_MODE" -eq 0 ] && ok "all shebang scripts executable"

# ---- check 3b: every tracked shell file parses -----------------------------
# The harness component and desktop packages copy broad source trees, not only
# scripts/.  A dormant shell file is therefore still shipped code.  Parse the
# complete tracked shell surface so an unreferenced legacy helper cannot evade
# the release gate and land broken in an install.
log "check 3b: all tracked shell files pass bash -n"
BAD_SYNTAX=0
while IFS= read -r path; do
    # A deliberate deletion remains in `git ls-files` until it is staged.  The
    # release tree cannot contain a missing file, so skip that pre-commit state
    # and parse every tracked shell file that will actually remain.
    [ -f "$path" ] || continue
    if ! syntax_error="$(bash -n "$path" 2>&1)"; then
        fail "$path does not parse: $(printf '%s' "$syntax_error" | head -n 1)"
        BAD_SYNTAX=1
    fi
done < <(git ls-files '*.sh')
[ "$BAD_SYNTAX" -eq 0 ] && ok "all tracked shell files parse"

# ---- check 3c: shipped runtime cannot contain placeholder proof ------------
log "check 3c: shipped runtime contains no placeholder verification command"
PLACEHOLDER_PROOF="$(git grep -nF 'echo placeholder' -- bin core harness components.d 2>/dev/null || true)"
if [ -n "$PLACEHOLDER_PROOF" ]; then
    fail "placeholder proof command found in shipped runtime: $(printf '%s' "$PLACEHOLDER_PROOF" | head -n 1)"
else
    ok "no placeholder proof command in shipped runtime"
fi

# ---- check 4: intra-repo script references exist (PKG-004) ----------------
log "check 4: scripts/ referenced paths exist"
BAD_REF=0
while IFS= read -r ref; do
    if [ ! -e "$ref" ]; then
        fail "referenced path does not exist: $ref"
        BAD_REF=1
    fi
done < <(grep -rhoE '"?scripts/[A-Za-z0-9._-]+\.(sh|ts|py)"?' scripts/ \
    | tr -d '"' | sort -u)
[ "$BAD_REF" -eq 0 ] && ok "all script references resolve"

# ---- check 5: solar update refuses version downgrades (PKG-001b) ----------
log "check 5: bin/solar version-compare guard behaves"
probe() {
    got="$(bash bin/solar version-compare "$1" "$2" 2>/dev/null)"
    if [ "$got" != "$3" ]; then
        fail "version-compare $1 $2 -> '$got' (want '$3')"
    fi
}
if grep -q "version-compare" bin/solar; then
    probe 1.0.0-rc.6 1.0.0-rc.8 lt
    probe 1.0.0-rc.8 1.0.0-rc.6 gt
    probe 1.0.0-rc.8 1.0.0-rc.8 eq
    probe 1.0.0-rc.8 1.0.0 lt      # rc precedes its GA release
    probe 1.0.0 1.0.0-rc.8 gt
    probe unknown 1.0.0-rc.8 unknown
    [ "$FAIL" -eq 0 ] && ok "version-compare guard present and correct"
else
    fail "bin/solar has no version-compare guard (updates cannot refuse downgrades)"
fi

# ---- check 5b: legacy update recovery stays on maintained origin -----------
log "check 5b: pre-channel receipt recovery is maintained-origin and version-derived"
if grep -q 'github.com/Stellven/OpenSolar' bin/solar; then
    fail "bin/solar still redirects a legacy receipt to the upstream fork"
elif ! grep -q 'DEFAULT_SOLAR_REPO="https://github.com/suraj-subrahmanyan/OpenSolar.git"' bin/solar; then
    fail "bin/solar maintained-origin fallback is missing"
elif ! grep -q 'release_channel_from_version' bin/solar; then
    fail "bin/solar legacy channel is not derived from the installed release version"
else
    ok "legacy update recovery stays on maintained origin and derives its release tag"
fi

# ---- check 6: receipt.sh channel fallback derives from VERSION ------------
# PKG-001 sibling found by real-machine install verification (2026-07-13): a
# direct install.sh run (dev tree, desktop-bundled Resources/harness) recorded
# channel v1.0.0-rc.6 from a hardcoded fallback in receipt.sh, so the very
# first `solar update` hit the downgrade guard. The fallback must be derived
# from the VERSION file, never a literal tag that goes stale at the next cut.
log "check 6: receipt.sh channel fallback derives from VERSION (PKG-001 sibling)"
RECEIPT=lib/installer/receipt.sh
if grep -Eq 'SOLAR_CHANNEL"\) or "v[0-9]' "$RECEIPT"; then
    fail "receipt.sh hardcodes a channel fallback tag (grep: 'or \"v<digit>'); derive it from VERSION instead"
elif ! grep -q 'channel_fallback' "$RECEIPT"; then
    fail "receipt.sh has no channel_fallback derivation (channel fallback must come from the VERSION file)"
else
    ok "receipt channel fallback is VERSION-derived"
fi

if [ "$FAIL" -eq 0 ]; then
    log "release-coherence: PASS"
    exit 0
fi
log "release-coherence: FAIL"
exit 1
