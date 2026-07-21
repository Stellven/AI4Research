#!/usr/bin/env bash

# py-deps.sh — install a component's Python requirements.
#
# Targets may be a component venv (mempalace) or the existing interpreter the
# unchanged harness calls (`python3`). CI sets --skip-py-deps /
# SOLAR_SKIP_PY_DEPS to avoid heavy dependency installs where a separate gate
# validates resolution.
pip_install_reqs() {
    target="$1"
    reqs="$2"
    [ -f "$reqs" ] || die "python requirements missing: $reqs"
    if [ -x "$target/bin/python" ]; then
        py="$target/bin/python"
        install_scope="venv"
    elif [ -x "$target" ]; then
        py="$target"
        install_scope="interpreter"
    else
        die "python target missing: $target"
    fi
    if [ "${SKIP_PY_DEPS:-false}" = "true" ]; then
        # deps-light (CI): the venv already exists; skip the multi-GB install
        # entirely. Requirement resolution is validated separately and once
        # (scripts/mempalace-check.sh step a: pip --dry-run --no-deps), so the
        # installs need no network and leave no pip cache in the sandbox.
        info "deps-light: skipping pip install of $reqs (resolution validated separately)"
        return 0
    fi
    # Real install on a user machine. Pin pip's cache inside SOLAR_HOME so it is
    # removed wholesale on uninstall and the user's own ~/.cache/pip is never
    # touched (mirrors the bun-cache contract).
    PIP_CACHE_DIR="$SOLAR_HOME/cache/pip"
    export PIP_CACHE_DIR
    mkdir -p "$PIP_CACHE_DIR"
    info "installing python requirements from $reqs"
    if [ "$install_scope" = "venv" ]; then
        "$py" -m pip install -r "$reqs" \
            || die "pip install failed for $reqs"
        return 0
    fi

    before_user_dists="$SOLAR_HOME/cache/python-user-dists-before.$$"
    after_user_dists="$SOLAR_HOME/cache/python-user-dists-after.$$"
    snapshot_python_user_dists "$py" "$before_user_dists"

    # Harness runs the existing `python3` interpreter directly. For externally
    # managed Python installs, user-site + break-system-packages is the least
    # invasive way to make that same interpreter import the required modules.
    if python_is_externally_managed "$py"; then
        if ! pip_supports_break_system_packages "$py"; then
            # A brand-new Debian/Ubuntu ships python3 with no usable pip (ensurepip
            # is disabled and python3-pip is not installed), so the externally-managed
            # path used to die immediately. Try to bootstrap a pip new enough to honor
            # --break-system-packages before giving up, so a fresh machine can install.
            info "pip for $py lacks --break-system-packages; attempting to bootstrap pip"
            "$py" -m ensurepip --upgrade >/dev/null 2>&1 || true
            "$py" -m pip install --user --upgrade pip >/dev/null 2>&1 || true
        fi
        if ! pip_supports_break_system_packages "$py"; then
            die "$py has no pip that supports --break-system-packages (externally managed Python).
Install pip for this interpreter, then re-run the installer:
  Debian/Ubuntu:  sudo apt-get install -y python3-pip python3-venv
  Fedora/RHEL:    sudo dnf install -y python3-pip
  macOS:          brew install python
(or install the requirements yourself: $py -m pip install --user --break-system-packages -r $reqs)"
        fi
        "$py" -m pip install --user --break-system-packages -r "$reqs" \
            || die "pip install failed for $reqs using $py"
    else
        "$py" -m pip install --user -r "$reqs" \
            || die "pip install failed for $reqs using $py. Install these requirements into that interpreter and re-run:
  $py -m pip install --user -r $reqs"
    fi
    snapshot_python_user_dists "$py" "$after_user_dists"
    record_python_user_deps_delta "$py" "$reqs" "$before_user_dists" "$after_user_dists"
    rm -f "$before_user_dists" "$after_user_dists"
}

python_is_externally_managed() {
    "$1" -c 'import os, sysconfig; stdlib = sysconfig.get_path("stdlib"); raise SystemExit(0 if stdlib and os.path.exists(os.path.join(stdlib, "EXTERNALLY-MANAGED")) else 1)' >/dev/null 2>&1
}

pip_supports_break_system_packages() {
    "$1" -m pip install --help 2>/dev/null | grep -q -- '--break-system-packages'
}

snapshot_python_user_dists() {
    py="$1"
    out="$2"
    "$py" - "$out" <<'PY'
import importlib.metadata as metadata
import re
import site
import sys
from pathlib import Path


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


user_site = site.getusersitepackages()
names = set()
for dist in metadata.distributions(path=[user_site]):
    name = dist.metadata.get("Name")
    if name:
        names.add(normalize(name))
Path(sys.argv[1]).write_text(
    "".join(f"{name}\n" for name in sorted(names)),
    encoding="utf-8",
)
PY
}

record_python_user_deps_delta() {
    py="$1"
    reqs="$2"
    before="$3"
    after="$4"
    PY_DEPS_MANIFEST="$SOLAR_HOME/python-user-deps.json" \
    PY_DEPS_REQS="$reqs" \
    "$py" - "$before" "$after" <<'PY'
import json
import importlib.metadata as metadata
import os
import re
import site
import sys
from pathlib import Path


def read_names(path):
    try:
        return {line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}
    except FileNotFoundError:
        return set()


before = read_names(sys.argv[1])
after = read_names(sys.argv[2])
added = sorted(after - before)

manifest_path = Path(os.environ["PY_DEPS_MANIFEST"])
reqs = os.environ["PY_DEPS_REQS"]
user_site = site.getusersitepackages()
user_base = site.getuserbase()
python_executable = sys.executable
# L1: record ONLY the packages THIS install actually added (after - before). The previous code
# also folded in the full requirement closure, which captured dependencies the user already had
# installed in user-site — so `solar uninstall` could remove packages Solar never installed.

if manifest_path.exists():
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        manifest = {}
else:
    manifest = {}

entries = manifest.get("entries")
if not isinstance(entries, list):
    entries = []

entry = None
for candidate in entries:
    if isinstance(candidate, dict) and candidate.get("user_site") == user_site:
        entry = candidate
        break
if entry is None:
    entry = {
        "python": python_executable,
        "user_base": user_base,
        "user_site": user_site,
        "requirements": [],
        "packages": [],
    }
    entries.append(entry)

packages = sorted(set(entry.get("packages") or []) | set(added))
if not packages:
    raise SystemExit(0)

entry["python"] = python_executable
entry["user_base"] = user_base
entry["user_site"] = user_site
entry["packages"] = packages
entry["requirements"] = sorted(set(entry.get("requirements") or []) | {reqs})

manifest = {"schema": 1, "entries": entries}
tmp = manifest_path.with_name(f"{manifest_path.name}.tmp")
manifest_path.parent.mkdir(parents=True, exist_ok=True)
tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
tmp.replace(manifest_path)
PY
}
