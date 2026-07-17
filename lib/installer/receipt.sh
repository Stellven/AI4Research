#!/usr/bin/env bash

write_receipt() {
    dry_run_note "write receipt $RECEIPT_PATH" && return 0
    tmp="$RECEIPT_PATH.tmp.$$"
    mkdir -p "$(dirname "$RECEIPT_PATH")"
    SELECTED_COMPONENTS="$SELECTED_COMPONENTS" \
    SOURCE_DIR="$SOURCE_DIR" \
    SOLAR_HOME="$SOLAR_HOME" \
    CLAUDE_DIR="$CLAUDE_DIR" \
    SOLAR_DB="$SOLAR_DB" \
    OS_KIND="$OS_KIND" \
    python3 - "$tmp" <<'PY'
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

tmp = sys.argv[1]
source = os.environ["SOURCE_DIR"]
try:
    sha = subprocess.check_output(
        ["git", "-C", source, "rev-parse", "--short", "HEAD"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
except Exception:
    sha = "unknown"


def compute_version(src):
    # Real release identity, most-specific first:
    #   1. an ancestor git tag (e.g. v1.0.0-rc.5-13-gabc123) -- only when the
    #      install source is a full checkout whose history carries the tag;
    #   2. the tracked VERSION file -- the release-controlled baseline that
    #      ships in every channel, including shallow/tagless `stable` clones
    #      and git-less tarballs;
    #   3. "unknown" -- never the old hardcoded "p1-alpha" lie.
    try:
        described = subprocess.check_output(
            # Only real release tags (v1.2.3 / v1.0.0-rc.5). --match excludes
            # junk ancestors like archive/* so a dev branch with no version-tag
            # ancestor falls through to the VERSION file instead of reporting a
            # misleading nearest-tag string.
            ["git", "-C", src, "describe", "--tags", "--match", "v[0-9]*"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if described:
            return described[1:] if described.startswith("v") else described
    except Exception:
        pass
    try:
        with open(os.path.join(src, "VERSION"), encoding="utf-8") as vf:
            text = vf.read().strip()
            if text:
                return text
    except Exception:
        pass
    return "unknown"


version = compute_version(source)


def channel_fallback(src):
    # Derive the fallback channel from the source tree's VERSION file — a
    # literal tag here goes stale at the next cut and records a channel the
    # downgrade guard then has to refuse on the very first `solar update`
    # (PKG-001 sibling, found by a real dev-tree install on 2026-07-13).
    # Uses the VERSION file, not compute_version(), because git-describe
    # decorations are not fetchable channels. check-release-coherence.sh
    # check 6 keeps this derived.
    try:
        with open(os.path.join(src, "VERSION"), encoding="utf-8") as vf:
            text = vf.read().strip()
            if text:
                return "v" + text
    except Exception:
        pass
    return "unknown"


# Channel + source repo the install tracks, so `solar update` knows where to
# fetch from. get-solar.sh exports these; a direct install.sh run derives the
# channel from the tree's own VERSION.
channel = os.environ.get("SOLAR_CHANNEL") or channel_fallback(source)
repo = (
    os.environ.get("SOLAR_REPO")
    or "https://github.com/suraj-subrahmanyan/OpenSolar.git"
)

components = [c for c in os.environ.get("SELECTED_COMPONENTS", "").split() if c]
all_roots = {
    "kernel": [os.path.join(os.environ["CLAUDE_DIR"], "solar")],
    "core-runtime": [os.path.join(os.environ["SOLAR_HOME"], "core")],
    "harness": [os.path.join(os.environ["SOLAR_HOME"], "harness")],
    "autosci": [
        os.path.join(os.environ["SOLAR_HOME"], "tools"),
        os.path.join(os.environ["SOLAR_HOME"], ".agents", "skills"),
    ],
    "skills-md": [os.path.join(os.environ["CLAUDE_DIR"], "skills")],
    "codex-bridge": [os.path.join(os.environ["SOLAR_HOME"], "codex-bridge")],
    "mempalace": [
        os.path.join(os.environ["SOLAR_HOME"], "mempalace"),
        os.path.join(os.environ["SOLAR_HOME"], "venv"),
    ],
}
receipt = {
    "schema": 1,
    "version": version,
    "git_sha": sha,
    "channel": channel,
    "repo": repo,
    "source_dir": source,
    "os": os.environ.get("OS_KIND", "unknown"),
    "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "solar_home": os.environ["SOLAR_HOME"],
    "claude_dir": os.environ["CLAUDE_DIR"],
    "db": os.environ["SOLAR_DB"],
    "components": components,
    "component_roots": {name: all_roots[name] for name in components if name in all_roots},
    "sentinels": {
        "claude_md": os.path.join(os.environ["CLAUDE_DIR"], "CLAUDE.md"),
        "begin": "<!-- BEGIN OPENSOLAR -->",
        "end": "<!-- END OPENSOLAR -->",
    },
}
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=2, sort_keys=True)
    f.write("\n")
PY
    mv "$tmp" "$RECEIPT_PATH"
}
