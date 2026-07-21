# Data Plane Closeout — Operator Runbook

**Sprint**: sprint-20260508-data-plane-closeout
**Created**: 2026-05-08
**Status**: Active reference doc

---

## 1. Production Truth Sources

| Layer | Location | Authority | Freshness |
|-------|----------|-----------|-----------|
| Sprint status | `~/.solar/harness/sprints/*.status.json` | **Primary** | Live (coordinator-watched) |
| Bridge ledger | `~/.solar/codex-bridge/bridge-ledger.jsonl` | **Primary** | Live (codex-bridge writes) |
| Solar DB | `~/.solar/solar.db` | Primary for historical data | Stale for some tables (see below) |
| Obsidian vault | `~/Knowledge/` | Derived cache (ingested from DB) | Refreshed on wiki-ingest dispatch |
| Flow state | `~/.solar/flow-state.json` | Local only (solar CLI) | Not shared |

### Known Stale Tables

- `sys_data_ledger`: last_checked 2026-02-06 (91+ days stale)
- `sys_resources`: access_count=0 for all rows (dormant)
- `cortex_passages`: may be empty or stale
- `knowledge_records`: last entry 2026-02-27

## 2. Cache/Derived vs Authority

- **Authority** = `status.json`, `bridge-ledger.jsonl`, `solar.db` tables
- **Derived cache** = Obsidian vault pages, FTS5 index, `v_solar_resources` view
- **Local only** = `~/.solar/flow-state.json` (solar CLI, not connected to harness)

## 3. Auditing Data Freshness

```bash
# Full audit (human-readable)
solar-harness data-plane audit

# Machine-parseable audit
solar-harness data-plane audit --json | python3 -m json.tool

# Verbose details per check
solar-harness data-plane audit --verbose
```

The audit checks: state integrity, sys_data_ledger freshness, sys_resources usage, cortex_sources/passages/entries freshness, bridge ledger health, sprint artifacts, resource usage telemetry, accepted artifact path, and solar CLI integration status.

## 4. Repairing Malformed State

```bash
# Dry-run: see what would be fixed
solar-harness data-plane repair-state --dry-run

# Live repair: backup to state_quarantine + delete malformed rows
solar-harness data-plane repair-state

# Verify repair
sqlite3 ~/.solar/solar.db "SELECT count(*) FROM state WHERE json_valid(value)=0;"
# Expected: 0
```

### Rollback

Quarantined rows are preserved in `state_quarantine` table:

```bash
# View quarantined rows
sqlite3 ~/.solar/solar.db "SELECT key, value, quarantined_at, reason FROM state_quarantine;"

# Restore a specific row (manual)
sqlite3 ~/.solar/solar.db "INSERT INTO state (key, value) SELECT key, value FROM state_quarantine WHERE key='YOUR_KEY';"
```

## 5. `solar` vs `solar-harness` Boundary

| | `solar` CLI | `solar-harness` |
|---|---|---|
| **Purpose** | Local lightweight task flow | Production multi-agent orchestration |
| **State** | `~/.solar/flow-state.json` (local) | `sprints/*.status.json` + `solar.db` |
| **DB writes** | None | Yes (bridge ledger, telemetry) |
| **tmux** | No | Yes (pane dispatch) |
| **Status** | `solar status` | `solar-harness status` |

`solar` is intentionally NOT connected to the shared data plane (Option B: by design). This is explicitly declared, not an accidental gap.

## 6. SQLite Lock Risk & WAL Mode

### Current State

All DB connections now use:
- `PRAGMA journal_mode=WAL` — allows concurrent readers while a writer holds the lock
- `PRAGMA busy_timeout=5000` — retries for up to 5 seconds on lock contention
- Shared via `lib/solar_db.py` — single entry point for consistent settings

### Concurrency Test

```bash
bash ~/.solar/harness/test-data-plane-db-concurrency.sh
```

5 parallel processes read + write simultaneously. Should PASS without `database is locked`.

### Remaining Caveats

- WAL mode increases disk usage (`.db-wal` and `.db-shm` files). These auto-clean on checkpoint.
- Very long write transactions (>5s) can still timeout. Break large writes into smaller commits.
- macOS file system locking is slightly different from Linux; the busy_timeout handles this.

## 7. Rollback Steps

### If state repair went wrong

1. Check `state_quarantine` table for backed-up rows
2. Restore: `INSERT INTO state SELECT key, value FROM state_quarantine WHERE key='...'`
3. Delete quarantine entry: `DELETE FROM state_quarantine WHERE key='...'`

### If WAL mode causes issues

```bash
sqlite3 ~/.solar/solar.db "PRAGMA journal_mode=DELETE;"
```

This reverts to default (non-WAL) mode. Concurrent readers may see more lock contention.

### If solar-harness data-plane commands fail

The audit script is standalone Python (`lib/data_plane_audit.py`) with no external dependencies beyond stdlib + sqlite3. If it fails:
1. Check `~/.solar/solar.db` exists and is readable
2. Try `python3 ~/.solar/harness/lib/data_plane_audit.py audit`
