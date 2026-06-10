#!/usr/bin/env bash

copy_payload() {
    src="$1"
    dst="$2"
    [ -d "$src" ] || die "copy source not found: $src"
    dry_run_note "copy $src to $dst" && return 0
    mkdir -p "$dst"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a \
            --exclude '.git/***' \
            --exclude '.DS_Store' \
            --exclude '__pycache__/***' \
            --exclude '*.pyc' \
            --exclude '*.log' \
            --exclude '*.pid' \
            --exclude '*.port' \
            --exclude '*.tmp' \
            --exclude '*~' \
            --exclude '.!*!.*' \
            --exclude '.*-probe-cache.json' \
            --exclude '.drafting-notified' \
            --exclude '.intent-hash' \
            --exclude '.last-seen-by-planner' \
            --exclude '.next-last-sid' \
            --exclude 'run/***' \
            --exclude 'runs/***' \
            --exclude 'state/***' \
            --exclude 'logs/***' \
            --exclude 'cache/***' \
            --exclude 'venvs/***' \
            --exclude 'vendor/***' \
            --exclude 'quarantine/***' \
            --exclude 'sprints/***' \
            --exclude 'intents/***' \
            --exclude 'release/artifacts/***' \
            "$src/" "$dst/"
    else
        cp -R "$src/." "$dst/"
    fi
}
