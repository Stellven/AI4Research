# C2 CLI Command Tree Spec — collect-social

Sprint: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s04-orchestration-ui`
Node: C2
Upstream: S03 C5 (`lib/social_browser_backend_x/cli.py`) + S02 A1 §3 Interface 5 + S02 A3 compat
Knowledge Context: solar-harness context inject used (mirage:timeout → qmd/obsidian/solar_db fallback)

## 1. Command Path

```
solar-harness wiki tech-hotspot-radar collect-social [OPTIONS]
```

Parent command group: `solar-harness wiki tech-hotspot-radar`
Subcommand: `collect-social`

## 2. Required Options

| Option | Type | Values | Default | Description |
|--------|------|--------|---------|-------------|
| `--backend` | enum | `browser`, `rss`, `manual`, `x_api`, `auto` | `auto` | Backend selection strategy. `auto` invokes `BackendSelector.pick()` which applies 4-tier fallback: browser_agent → rss_public → manual_curated → x_api_optional. |
| `--limit-accounts` | int | `1..200` | — (required) | Maximum accounts to scan in this invocation. Caps the batch roster from the configured seed list. |

## 3. Optional Options

| Option | Type | Values | Default | Description |
|--------|------|--------|---------|-------------|
| `--tier` | enum | `1`, `2`, `both` | `both` | Account tier filter. `1` = P0 大咖 (tier1), `2` = general (tier2), `both` = all accounts. Determines which cooldown/frequency schedule applies. |
| `--dry-run` | flag | — | `false` | Print execution plan without invoking `BrowserLeaseClient.acquire()` or any lease call. No writes to `social_posts` or `Knowledge/_raw`. |

## 4. Legacy Compatibility Options (per S02 A3 Phase 1+2)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--x-api-token` | string | env `X_API_BEARER_TOKEN` | Legacy X API token. Only effective when `--backend x_api`. Ignored by `auto`, `browser`, `rss`, `manual`. |
| `--ack-x-api-cost` | flag | `false` | Required confirmation when `--backend x_api` is selected. Without this flag, `x_api` backend raises a pre-flight error. |

### Legacy Path Behavior

1. **Old invocation** `collect-social --x-api-token <T>` is mapped to `--backend x_api --ack-x-api-cost`.
2. `BackendSelector` is never bypassed: `x_api` goes through the same 4-tier chain and occupies the lowest-priority slot.
3. `--backend auto` never selects `x_api`; it stops at `manual_curated` if browser and rss are unavailable.
4. Three-phase migration ladder (S02 A3 §2): Phase 1 dual-write → Phase 2 browser priority → Phase 3 x_api deprecated opt-in.

## 5. Exit Codes

| Code | Name | Meaning | Output on stderr |
|------|------|---------|------------------|
| `0` | `SUCCESS` | All requested accounts scanned and persisted. `social_posts` rows written. | Summary JSON with counts: `{scanned, inserted, deduped, fallback_count}` |
| `1` | `PARTIAL` | Some accounts failed but at least one succeeded. Failures are per-account isolated (per AC-5). | Per-account failure list + summary JSON with `failed_accounts` array. |
| `2` | `CONFIG_ERROR` | Invalid arguments, missing required options, config file parse failure. | Human-readable error message. No data written. |
| `3` | `BLOCKER_NOT_RESOLVED` | `HardBlockerGuard.check()` returned false for `sprint-20260525-browser-agent-global-operator-cutover` when `--backend browser` is explicitly requested and no fallback is allowed. | Hard blocker sprint ID + current status. No data written. |

### Exit Code Resolution Order

```
1. Validate args (--backend enum, --limit-accounts range, --tier enum)
   → invalid → exit 2

2. Resolve backend via BackendSelector (or explicit --backend)
   → x_api without --ack-x-api-cost → exit 2
   → browser requested but HardBlockerGuard fails → exit 3

3. Execute 10-step pipeline per account
   → all succeed → exit 0
   → some fail, some succeed → exit 1
   → all fail → exit 1 (not exit 3; blocker was already checked)
```

## 6. Dry-Run Mode

When `--dry-run` is passed:

1. **No lease call**: `BrowserLeaseClient.acquire()` is never invoked. `OperatorLeaseManager` is bypassed.
2. **No writes**: No rows inserted into `social_posts`, `social_post_dedup_keys`, `model_call_ledger`, or `Knowledge/_raw`.
3. **Plan printed to stdout**: A structured plan showing:
   ```json
   {
     "mode": "dry-run",
     "backend": "browser_agent",
     "tier": "both",
     "account_count": 50,
     "estimated_duration_seconds": 900,
     "steps": [
       "BackendSelector.pick → browser_agent",
       "BrowserLeaseClient.acquire (simulated)",
       "PostExtractor → 11-field schema",
       "DedupQueue → 24h window",
       "social_posts.insert (skipped)",
       "metrics_snapshots.write (skipped)",
       "ThunderOMLX semantic extract (skipped)",
       "social_links + viewpoints (skipped)",
       "dispatch → Knowledge raw (skipped)",
       "model_call_ledger (skipped)"
     ],
     "rate_limiter": {
       "per_account_cooldown_tier1_s": 180,
       "per_account_cooldown_tier2_s": 600,
       "global_concurrency": 1,
       "jitter_range_s": [5, 15],
       "exp_backoff_base": 2,
       "exp_backoff_max_s": 300
     }
   }
   ```
4. **Exit code**: Always `0` in dry-run (since no real execution occurs) unless args are invalid (`2`).

## 7. Cron Usage

### Tier 1 (P0 大咖) — every 6 hours

```cron
# Tier 1: scan P0 大咖 every 6 hours via browser (or auto-fallback)
0 */6 * * * solar-harness wiki tech-hotspot-radar collect-social --backend auto --limit-accounts 200 --tier 1 >> ~/.solar/logs/collect-social-tier1.log 2>&1
```

### Tier 2 (general) — every 24 hours

```cron
# Tier 2: scan general accounts once daily at 03:17 (off-peak)
17 3 * * * solar-harness wiki tech-hotspot-radar collect-social --backend auto --limit-accounts 200 --tier 2 >> ~/.solar/logs/collect-social-tier2.log 2>&1
```

### Both tiers in one invocation

```cron
# Full scan: both tiers daily at 06:00
0 6 * * * solar-harness wiki tech-hotspot-radar collect-social --backend auto --limit-accounts 200 --tier both >> ~/.solar/logs/collect-social-full.log 2>&1
```

### RateLimiter Enforcement (per S02 A1 RateLimiter)

The cron schedule above respects the RateLimiter 5-knob spec:

| Knob | Tier 1 | Tier 2 | Source |
|------|--------|--------|--------|
| `per_account_cooldown_seconds` | 180 | 600 | S02 A1 §1 |
| `global_concurrency` | 1 | 1 | S02 A1 §1 (硬性) |
| `jitter_range_seconds` | ±5..15 | ±5..15 | S02 A1 §1 |
| `exponential_backoff` | base=2, max=300s | base=2, max=300s | S02 A1 §1 |
| `tier_frequency` | 6h | 24h | S02 A1 §1 |

Cron is the external trigger; `RateLimiter` internally enforces cooldown and backoff. If the cron fires while an account is still in cooldown, that account is skipped with a log entry.

## 8. Rollback Env

```bash
SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE=1
```

When set:
- `BackendSelector` treats `browser_agent` as unavailable.
- `auto` proceeds to `rss_public`, then `manual_curated`.
- `--backend browser` exits `3` (BLOCKER_NOT_RESOLVED equivalent: backend disabled by env).
- Status surface shows `browser_backend_disabled_by_env`.

## 9. Status Subcommand

```
solar-harness wiki tech-hotspot-radar collect-social-status
```

Prints the 7-indicator status surface (per S02 A1 §3 Interface 6):

```json
{
  "total_accounts": 200,
  "enabled_accounts": 195,
  "scanned_today": 47,
  "browser_ready": false,
  "scan_state": "idle",
  "parse_fail_rate": 0.02,
  "fallback_count": 3,
  "by_backend": {
    "browser_agent": 0,
    "rss_public": 40,
    "manual_curated": 7,
    "x_api": 0
  },
  "hard_blocker": {
    "sprint_id": "sprint-20260525-browser-agent-global-operator-cutover",
    "status": "not_passed",
    "mock_mode_active": true
  }
}
```

## 10. Full Command Tree Summary

```
solar-harness wiki tech-hotspot-radar
├── collect-social                    # Scan social accounts
│   ├── --backend {browser|rss|manual|x_api|auto}   # Backend strategy (default: auto)
│   ├── --limit-accounts N           # Max accounts (required)
│   ├── --tier {1|2|both}            # Tier filter (default: both)
│   ├── --dry-run                    # Plan only, no execution
│   ├── --x-api-token <TOKEN>        # Legacy X API token (x_api backend only)
│   └── --ack-x-api-cost             # Confirm x_api cost (required with x_api)
├── collect-social-status            # 7-indicator status surface
└── (future subcommands from other epic slices)
```

## 11. Acceptance Cross-Reference

| Acceptance ID | Requirement | Spec Section |
|---------------|-------------|--------------|
| A-C2-1 | 5 backend choices + --limit-accounts + --tier + --dry-run | §2, §3 |
| A-C2-2 | Exit codes 0/1/2/3 with meaning table | §5 |
| A-C2-3 | Cron usage examples for tier1 6h / tier2 24h | §7 |
| A-C2-4 | Legacy --x-api-token path retained (per S02 A3 compat) | §4 |
| A-C2-5 | Dry-run mode behavior specified (no lease call, plan printed) | §6 |

## 12. Source References

- S02 A1 §3 Interface 5: CLI subcommand spec — `collect-social --backend {browser|rss|manual|x_api|auto} --limit-accounts N`; exit codes 0/1/2/3
- S02 A1 §1 RateLimiter: 5-knob spec (per_account_cooldown / global_concurrency / jitter / exp_backoff / tier_frequency)
- S02 A3 §1-§2: Legacy X API token path preserved as explicit optional; 3-phase migration ladder
- S02 A3 §3: Rollback env `SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE=1`
- S03 C5: `lib/social_browser_backend_x/cli.py` (implementation, not this spec's scope)
- S04 C2 dispatch goal: CLI command tree spec per S03 C5
