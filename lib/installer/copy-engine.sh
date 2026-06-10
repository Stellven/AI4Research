#!/usr/bin/env bash

# Directories of local runtime state that must never reach an install,
# and generated/junk file patterns. This list is the sync contract
# inherited from scripts/sync-harness-runtime.sh: copy code and packaged
# assets, not machine state.
COPY_EXCLUDE_DIRS=".git __pycache__ run runs state logs cache venvs vendor quarantine sprints intents"
COPY_EXCLUDE_FILES=".DS_Store *.pyc *.log *.pid *.port *.tmp *~ .!*!.* .*-probe-cache.json .drafting-notified .intent-hash .last-seen-by-planner .next-last-sid"

copy_payload() {
    src="$1"
    dst="$2"
    [ -d "$src" ] || die "copy source not found: $src"
    dry_run_note "copy $src to $dst" && return 0
    mkdir -p "$dst"
    if command -v rsync >/dev/null 2>&1; then
        set -- -a
        for d in $COPY_EXCLUDE_DIRS; do
            set -- "$@" --exclude "$d/"
        done
        for f in $COPY_EXCLUDE_FILES; do
            set -- "$@" --exclude "$f"
        done
        # Trailing-slash directory excludes (not 'dir/***') so the same
        # behavior holds on openrsync, which ships as rsync on newer macOS.
        rsync "$@" --exclude 'release/artifacts/' "$src/" "$dst/"
    else
        # No rsync: copy everything, then enforce the same exclude
        # contract on the destination. A bare cp -R would silently carry
        # local runtime state into the install.
        cp -R "$src/." "$dst/"
        for d in $COPY_EXCLUDE_DIRS; do
            find "$dst" -name "$d" -prune -exec rm -rf {} + 2>/dev/null || true
        done
        for f in $COPY_EXCLUDE_FILES; do
            find "$dst" -name "$f" -prune -exec rm -rf {} + 2>/dev/null || true
        done
        rm -rf "$dst/release/artifacts"
    fi
}
