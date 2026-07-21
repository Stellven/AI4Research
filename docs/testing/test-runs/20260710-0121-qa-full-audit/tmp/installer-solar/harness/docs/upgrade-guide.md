# Solar Product Platform — Upgrade Guide

## Overview

This guide covers upgrading an existing Solar Harness installation to a new version using `installer/upgrade.sh`.

## Prerequisites

- Existing Solar Harness installation at `~/.solar/harness`
- `bash` 4.0+ (`/opt/homebrew/bin/bash` on macOS)
- `python3` 3.9+
- `sqlite3`
- `bun` for TVS rendering (`solar-harness tvs render`)
- `SOLAR_TVS_ROOT` pointing to a TVS checkout that contains `index.ts`

TVS is a release-level dependency, not a cosmetic optional feature. Installer
doctor and release publish gates fail when Bun, `SOLAR_TVS_ROOT`, or the TVS
smoke render is missing.

Example:

```bash
export SOLAR_TVS_ROOT="$HOME/TVS"
test -f "$SOLAR_TVS_ROOT/index.ts"
solar-harness tvs render --width 52 <<'JSON'
{"canvas":{"width":52},"style":"solar_default","root":{"type":"card","header":"TVS Ready","sections":[{"type":"kv","items":[{"key":"Status","value":"ok"}]}]}}
JSON
```

## Before You Upgrade

### 1. Take a snapshot (mandatory)

```bash
solar-harness product snapshot
```

This writes a SHA256-manifest backup to `~/.solar/harness/backups/product-snapshots/<timestamp>/`.

Verify the snapshot:

```bash
solar-harness product verify --latest
```

### 2. Run doctor

```bash
installer/doctor.sh --json
```

All checks must return `ok: true`. Do not upgrade with failing doctor output.

### 3. Check for active tasks

```bash
solar-harness leases list --json
```

If any pane leases are active, wait for them to expire or release them manually before upgrading.

## Upgrade Steps

### Standard upgrade (from tarball)

```bash
# Download and verify the new tarball
curl -O https://releases.solar.internal/solar-harness-<version>.tar.gz
sha256sum -c solar-harness-<version>.sha256

# Run the upgrade script
bash installer/upgrade.sh --version <version> --tarball solar-harness-<version>.tar.gz
```

### Upgrade from git (development)

```bash
cd ~/.solar/harness
git pull origin main
bash installer/upgrade.sh --from-git
```

The upgrade script will:

1. Detect current version from `VERSION` file
2. Take a pre-upgrade snapshot automatically
3. Apply migrations in `lib/migrations/` if present
4. Restart any background services (QMD, Mirage)
5. Run `doctor.sh` as post-upgrade health check

## State DB Migrations

State DB migrations are applied automatically by `installer/upgrade.sh`. Each migration is idempotent (safe to re-run).

To check migration status:

```bash
python3 lib/solar_state_db.py schema-version --json
```

## Post-Upgrade Checks

```bash
# Doctor
SOLAR_TVS_ROOT="$HOME/TVS" installer/doctor.sh --json

# Capability registry
python3 lib/capability_registry.py scorecard --json

# Skill registry
python3 lib/solar_skills.py registry --json

# Verify snapshot still valid
solar-harness product verify --latest
```

## Rollback

If anything goes wrong, see [rollback-guide.md](rollback-guide.md).

## Upgrading Plugins

Plugin manifests are versioned independently. After a harness upgrade:

```bash
# Re-sync capability registry
python3 lib/capability_registry.py sync --json

# Re-validate all manifests
python3 lib/plugin_loader.py validate --json
```

If a plugin has a new required field that is missing, `validate` will report it. Update the manifest or disable the plugin before proceeding.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `doctor.sh` fails after upgrade | Migration incomplete | Run `python3 lib/solar_state_db.py migrate` |
| Capability registry empty | sync not re-run | `python3 lib/capability_registry.py sync` |
| Pane leases stuck | Upgrade happened mid-task | `solar-harness leases release --all` |
| State DB locked | Concurrent process | Wait 30s, retry; if stuck: `solar-harness leases release --all` |
