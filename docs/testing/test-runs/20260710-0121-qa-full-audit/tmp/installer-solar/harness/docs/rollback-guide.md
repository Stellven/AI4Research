# Solar Product Platform — Rollback Guide

## Overview

This guide covers rolling back Solar Harness to a previously snapshotted state using `solar-harness product restore`.

## When to Roll Back

Roll back when:
- An upgrade breaks existing `solar-harness` commands
- The state DB is corrupted
- Plugin manifests cause scope violations that are unrecoverable
- Evolution engine produces bad promotions

Do NOT roll back:
- To fix a config error (edit the config instead)
- To undo a completed sprint (sprints are append-only)

## Rollback Steps

### 1. List available snapshots

```bash
solar-harness product snapshot --list
```

Output shows snapshots sorted by timestamp, newest first.

### 2. Dry-run the restore

Always dry-run first:

```bash
solar-harness product restore --snapshot <timestamp> --dry-run
```

Review the list of files that will be restored. Confirm no live data paths overlap.

### 3. Execute the restore

```bash
solar-harness product restore --snapshot <timestamp>
```

The restore:
1. Validates the snapshot SHA256 manifest
2. Stops any background services (Mirage, QMD scheduler)
3. Restores files listed in the manifest
4. Re-runs `doctor.sh` as post-restore check

### 4. Verify

```bash
installer/doctor.sh --json
solar-harness product verify --snapshot <timestamp>
```

Both must return `ok: true` before resuming normal operations.

## Emergency Rollback (no snapshot available)

If no snapshot exists (first install failure):

```bash
# Reset state DB to empty
rm -f ~/.solar/harness/run/state.db

# Re-run installer
bash installer/install.sh --non-interactive --reset
```

This is destructive: all task history and pane leases are lost.

## Plugin-Level Rollback

To roll back a single plugin without restoring the entire snapshot:

```bash
# From the plugin's manifest rollback.commands field:
solar-harness integrations disable <plugin-id>

# Or use the rollback strategy from the manifest directly:
python3 lib/plugin_loader.py rollback --plugin <plugin-id> --json
```

## Capability Demotion (evolution rollback)

If the evolution engine promoted a capability incorrectly:

```bash
python3 lib/evolution_engine.py demote-degraded --threshold 3.5 --json
```

Or demote a specific capability:

```bash
# Check current scorecard
python3 lib/evolution_engine.py scorecard --json

# Re-sync from manifests (resets to manifest-declared levels)
python3 lib/capability_registry.py sync --json
```

## QMD Rollback

If QMD integration_level was promoted incorrectly (experiment exp-001):

```bash
# Revert manifest
# Edit plugins/qmd/manifest.yaml: integration_level: default_usable
python3 lib/capability_registry.py sync --json
solar-harness integrations disable qmd
```

## Rollback Decision Tree

```
Something broke after upgrade
        │
        ▼
solar-harness product restore --snapshot <ts> --dry-run
        │
   ─────┴─────
  |           |
Looks safe   Too many files affected
  │                 │
  ▼                 ▼
restore          emergency rollback
                 (rm state.db + reinstall)
```

## Notes

- Snapshots do NOT include `venvs/`, `vendor/`, `run/`, or `backups/` themselves.
- Secrets are never included in snapshots (excluded at creation time).
- Snapshots are stored at `~/.solar/harness/backups/product-snapshots/`.
- A snapshot manifest at `manifest.json` lists every file + SHA256 for verification.
