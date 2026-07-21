# C3 — Config UI Spec (YAML Config Schema)

sprint_id: `sprint-20260525-tech-hotspot-radar-social-browser-backend-for-x-大咖监控-s04-orchestration-ui`
node: `C3`
package_boundary: `spec_only`
generated_at: `2026-05-29`
status: `reviewing`

> 本文件是 YAML 配置规约。S03 core-runtime 实现时消费此规约作为 `ConfigLoader` 的 schema 来源。
> 不执行代码、不调 browser agent、不调 X API、不新起 ThunderOMLX。

---

## §0 设计输入

| 输入 | 来源 | 用途 |
|------|------|------|
| A1 §1 BackendSelector 4-tier fallback | A1-control-plane-data-plane-interfaces.md §1 | §1.1 collection.backend_order |
| A1 §2 RateLimiter 5 knobs | A1 §2 表 5 行 | §1.1 collection.rate_limiter |
| A1 §3 10-step pipeline | A1 §3 | §2 extraction, §4 output |
| A1 §4.1 BrowserLeaseClient 6 ops | A1 §4.1 | §2 extraction.browser_agent |
| A4 OQ-02 ThunderOMLX reuse | A4-oq-resolutions.md OQ-02 | §3 scoring.semantic_socket |
| A4 OQ-05 Knowledge ingest order | A4 OQ-05 | §4 output.knowledge_ingest |
| A3 rollback env | A3-compat-migration.md | §5 rollback |
| HF Paper Insight S04 C3 config | HF Paper S04 design §3 | §5 quality 3 gates reuse |

requirement_ids: `O1, O6`
acceptance_ids: `A-C3-1, A-C3-2, A-C3-3, A-C3-4`

---

## §1 YAML Config — Full Schema

Config file path: `~/.solar/harness/config/social-browser-backend-x.yaml`

```yaml
# schema_version: solar.social_browser_backend.config.v1
# bump on any field rename/addition/removal

collection:
  accounts_seed:
    path: "~/.solar/harness/config/social-accounts-seed.yaml"
    # External file listing 200 seed accounts
    # Format: [{handle: str, tier: 1|2, enabled: bool, note: str?}]
    count_target: 200

  tier_separation:
    tier1:
      label: "P0 大咖"
      scan_frequency: "6h"
      cooldown_seconds: 180
    tier2:
      label: "关注列表"
      scan_frequency: "24h"
      cooldown_seconds: 600

  global_concurrency: 1
  # Hard limit. Override via SOLAR_HOTSPOT_SOCIAL_BROWSER_MAX_CONCURRENCY only.

  backend_order:
    - browser_agent
    - rss_public
    - manual_curated
    # x_api_optional: NOT in auto chain. Explicit --backend x_api only.

  rate_limiter:
    per_account_cooldown:
      tier1_seconds: 180
      tier2_seconds: 600
      minimum_hard_floor: 60
      # CLI --cooldown-seconds cannot set below this floor
    global_concurrency: 1
    jitter:
      min_seconds: 5
      max_seconds: 15
    exp_backoff:
      base: 2
      max_seconds: 300
      initial_seconds: 5
    tier_scan_frequency:
      tier1: "6h"
      tier2: "24h"

extraction:
  browser_agent:
    lease_timeout_seconds: 120
    # Max wait for OperatorLeaseManager.acquire() before triggering tier1→tier2 fallback
    rate_per_account_per_scan: 1
    # One lease per account per scan cycle
    screenshot_path: "~/.solar/screenshots/social-browser-backend-x"
    # Fallback directory for parse failures
    max_scroll_rounds: 3
    # BrowserLeaseClient.controlled_scroll rounds (1-10)
    mock_fixture_path: null
    # When hard_blocker active: path to local HTML fixture for dry-run testing
    # Example: "tests/fixtures/mock-x-profile.html"

  rss_public:
    feed_list:
      path: "~/.solar/harness/config/rss-feeds.yaml"
      # External file listing RSS feed URLs
      # Format: [{url: str, label: str, enabled: bool}]
    max_entries_per_feed: 50

  manual_curated:
    import_path: "~/.solar/harness/config/manual-curated-posts.yaml"
    # Manual import file for curated content
    # Format: [{author_handle, text, post_url, collected_at, note}]

  post_extractor:
    # No additional config; 11-field extraction is schema-driven (A1 §4.2)
    screenshot_on_parse_fail: true
    dom_hash_algorithm: "sha256"

scoring:
  semantic_socket:
    reuse_existing: true
    # Per OQ-02: reuse ThunderOMLX via ~/.thunderomlx/socket; NO new instance (AC-10)
    socket_path: "~/.thunderomlx/socket"
    fallback_on_unavailable: "queue_pending"
    # Options: "queue_pending" | "skip"
    # queue_pending: persist raw, enqueue for later semantic extraction
    # skip: leave semantic_extract_pending=false, downstream steps continue without semantic

  premium_reasoning:
    trigger_threshold: "tier1_and_high_recall"
    # Per OQ-03: only tier1 P0 accounts + high entity/link recall
    # Actual routing logic in S03 runtime, not configurable here
    max_calls_per_scan_cycle: 10
    budget_guard_usd: 1.0
    # Soft budget ceiling per scan cycle; exceeded → downgrade to local-only

output:
  knowledge_ingest:
    raw:
      mode: "sync"
      # Per OQ-05: raw written synchronously before any derived store
      path_pattern: "Knowledge/_raw/social/{date}/{handle}/{post_id_or_hash}.md"
    extracted:
      mode: "async"
      # Async parallel after raw persistence
    qmd:
      mode: "async"
    graph:
      mode: "async"

  ai_influence_report:
    enabled: true
    output_path: "~/.solar/reports/social-trend-report-{date}.md"
    # AI Influence social trend report (pipeline step 10 per A1 §3)
    backend_share_visible: true
    # Show collection_backend breakdown in report

quality:
  gates:
    packet:
      enabled: true
      # Reused from HF Paper Insight epic quality gate
      # Validates: post_record 11 fields populated, dedup_key assigned, raw persisted
      check: "all_required_fields_non_null AND dedup_key IS NOT NULL AND raw_md_exists"

    insight:
      enabled: true
      # Reused from HF Paper Insight epic quality gate
      # Validates: semantic extract produced, links extracted, viewpoint candidate identified
      check: "semantic_extract_row_exists OR semantic_extract_pending=true"
      tolerance_percent: 5
      # Allow up to 5% of posts to be pending semantic extraction

    resonance:
      enabled: true
      # Reused from HF Paper Insight epic quality gate
      # Validates: cross-source link found (GitHub/YouTube/paper) or propagation_chain row exists
      check: "social_links_count > 0 OR propagation_chain_row_exists"

  parse_failure_alert:
    threshold_percent: 10
    # StatusSurface indicator turns red when parse_failure_count_today / scanned_today >= this
```

---

## §2 Hot-Reload Mechanism (Atomic Write/Rename)

### §2.1 Protocol

The running process watches the config file via filesystem poll (interval 5s, default) or inotify where available. Hot-reload uses **atomic write + rename** to avoid reading partial files:

```
1. Write to temp file:  social-browser-backend-x.yaml.tmp.<pid>
2. fsync(temp)
3. rename(temp → social-browser-backend-x.yaml)   # atomic on POSIX
4. Process detects mtime change on next poll cycle
5. Load new config into shadow Config object
6. Validate new config (schema_version match, required fields, value ranges)
7. If valid: swap active config pointer (lock-free read, write under brief mutex)
8. If invalid: log warning with validation errors, retain current config
```

### §2.2 Constraints

- No process restart required for config changes.
- Hot-reload applies to: rate_limiter knobs, tier frequencies, paths, quality thresholds.
- Hot-reload does NOT apply to: `schema_version` (requires restart), `global_concurrency` mid-scan (takes effect on next scan cycle).
- Active lease holders use the config that was active when their scan cycle started; new config applies to the next scan cycle.

### §2.3 Config Validation Rules

| Field | Validation |
|-------|-----------|
| `collection.global_concurrency` | `>= 1` |
| `collection.rate_limiter.per_account_cooldown.tier1_seconds` | `>= minimum_hard_floor (60)` |
| `collection.rate_limiter.per_account_cooldown.tier2_seconds` | `>= minimum_hard_floor (60)` |
| `collection.rate_limiter.exp_backoff.max_seconds` | `>= initial_seconds` |
| `extraction.browser_agent.max_scroll_rounds` | `1 <= x <= 10` |
| `quality.gates.insight.tolerance_percent` | `0 <= x <= 100` |
| `quality.parse_failure_alert.threshold_percent` | `0 < x <= 100` |
| `schema_version` | Must match `solar.social_browser_backend.config.v1` |

---

## §3 Rollback Environment Variable

### §3.1 SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE=1

When this env var is set to `1`:

- The entire social browser backend pipeline is **disabled**.
- `collect-social` CLI exits immediately with rc=0 and message: `Social browser backend disabled via SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE=1`
- No browser lease is acquired, no RSS feeds are fetched, no manual imports are processed.
- X API legacy path remains available (per A3 Phase 1+2 compat), but only via explicit `--backend x_api`.
- This is the **rollback mechanism** per A3 compat & migration plan: returns to pre-browser-backend behavior.

### §3.2 Check Timing

- Checked once at CLI startup (before any backend selection).
- Checked by autopilot tick before triggering scan cycle (S04 C4).
- Not checked mid-scan (active scans continue to termination).

---

## §4 Per-Provider Config Details

### §4.1 browser_agent

| Field | Default | Override Env | Notes |
|-------|---------|-------------|-------|
| `lease_timeout_seconds` | 120 | `SOLAR_HOTSPOT_BROWSER_LEASE_TIMEOUT` | Max wait for OperatorLeaseManager.acquire() |
| `rate_per_account_per_scan` | 1 | — | One lease per account per scan cycle |
| `screenshot_path` | `~/.solar/screenshots/social-browser-backend-x` | — | Directory for parse failure screenshots |
| `max_scroll_rounds` | 3 | — | BrowserLeaseClient.controlled_scroll rounds (1-10) |
| `mock_fixture_path` | null | `SOLAR_HOTSPOT_BROWSER_MOCK_FIXTURE` | Local HTML fixture for dry-run when hard_blocker active |

When `mock_fixture_path` is set and hard_blocker is active:
- `collect-social --dry-run` reads the fixture instead of acquiring a real lease.
- No real browser agent calls are made (per evidence_policy `no_real_browser_agent_calls`).

### §4.2 rss_public

| Field | Default | Override Env | Notes |
|-------|---------|-------------|-------|
| `feed_list.path` | `~/.solar/harness/config/rss-feeds.yaml` | — | External file with RSS feed URLs |
| `max_entries_per_feed` | 50 | — | Cap per feed to avoid overload |

### §4.3 manual_curated

| Field | Default | Override Env | Notes |
|-------|---------|-------------|-------|
| `import_path` | `~/.solar/harness/config/manual-curated-posts.yaml` | — | Manual import file path |

### §4.4 x_api (optional)

| Field | Default | Override Env | Notes |
|-------|---------|-------------|-------|
| token | — | `SOLAR_HOTSPOT_X_API_TOKEN` | Optional; NOT required for browser/rss/manual backends |
| cost_ack_required | true | — | Must pass `--ack-x-api-cost` CLI flag |

x_api is **opt-in only**:
- Never selected by `auto` backend (per A1 §1.3 decision sequence).
- Requires: token present AND `--backend x_api` AND `--ack-x-api-cost`.
- Missing any of these → CLI rc=3 (per A1 §4.5 exit codes).

---

## §5 Environment Variable Override Map

All env overrides follow the pattern `SOLAR_HOTSPOT_*`:

| Env Var | Config Path | Type | Notes |
|---------|-----------|------|-------|
| `SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE` | — (kill switch) | `"1"` to disable | §3 rollback; canonical name per A3 |
| `SOLAR_HOTSPOT_SOCIAL_COOLDOWN_T1` | collection.rate_limiter.per_account_cooldown.tier1_seconds | int | ≥60 |
| `SOLAR_HOTSPOT_SOCIAL_COOLDOWN_T2` | collection.rate_limiter.per_account_cooldown.tier2_seconds | int | ≥60 |
| `SOLAR_HOTSPOT_SOCIAL_BROWSER_MAX_CONCURRENCY` | collection.global_concurrency | int | ≥1; not exposed via CLI |
| `SOLAR_HOTSPOT_SOCIAL_JITTER_MIN` | collection.rate_limiter.jitter.min_seconds | int | |
| `SOLAR_HOTSPOT_SOCIAL_JITTER_MAX` | collection.rate_limiter.jitter.max_seconds | int | |
| `SOLAR_HOTSPOT_SOCIAL_BACKOFF_BASE` | collection.rate_limiter.exp_backoff.base | int | |
| `SOLAR_HOTSPOT_SOCIAL_BACKOFF_MAX` | collection.rate_limiter.exp_backoff.max_seconds | int | |
| `SOLAR_HOTSPOT_SOCIAL_BACKOFF_INITIAL` | collection.rate_limiter.exp_backoff.initial_seconds | int | |
| `SOLAR_HOTSPOT_SOCIAL_SCAN_FREQ_T1` | collection.rate_limiter.tier_scan_frequency.tier1 | str | e.g. "6h" |
| `SOLAR_HOTSPOT_SOCIAL_SCAN_FREQ_T2` | collection.rate_limiter.tier_scan_frequency.tier2 | str | e.g. "24h" |
| `SOLAR_HOTSPOT_BROWSER_LEASE_TIMEOUT` | extraction.browser_agent.lease_timeout_seconds | int | |
| `SOLAR_HOTSPOT_BROWSER_MOCK_FIXTURE` | extraction.browser_agent.mock_fixture_path | str path | |
| `SOLAR_HOTSPOT_X_API_TOKEN` | — (x_api token) | str secret | Never logged/printed |

Priority: env var > YAML config > hardcoded default.

---

## §6 Validation Evidence (self-check)

### Acceptance A-C3-1: 5 YAML subsections with field-level spec

| Subsection | Fields | Status |
|-----------|--------|--------|
| collection | accounts_seed (path/count_target), tier_separation (tier1/tier2 labels+freq+cooldown), global_concurrency, backend_order, rate_limiter (5 knobs) | Present |
| extraction | browser_agent (lease_timeout/rate/screenshot_path/max_scroll_rounds/mock_fixture_path), rss_public (feed_list/max_entries), manual_curated (import_path), post_extractor (screenshot_on_parse_fail/dom_hash_algorithm) | Present |
| scoring | semantic_socket (reuse_existing/socket_path/fallback_on_unavailable), premium_reasoning (trigger_threshold/max_calls/budget_guard) | Present |
| output | knowledge_ingest (raw sync + extracted/qmd/graph async), ai_influence_report (enabled/path/backend_share_visible) | Present |
| quality | gates.packet, gates.insight (tolerance_percent), gates.resonance, parse_failure_alert (threshold_percent) | Present |

### Acceptance A-C3-2: Hot-reload via atomic write/rename

Documented in §2: 8-step atomic write/rename protocol, no process restart, shadow config swap with validation. Constraints on what hot-reload applies to vs. what requires restart.

### Acceptance A-C3-3: Rollback env SOLAR_SOCIAL_BROWSER_BACKEND_DISABLE=1

Documented in §3: kill switch behavior, check timing (startup + autopilot tick), X API legacy path retained.

### Acceptance A-C3-4: Per-provider config fields and defaults

Documented in §4: browser_agent (5 fields), rss_public (2 fields), manual_curated (1 field), x_api (2 fields). All with defaults and override env vars.

---

## §7 Architecture Guard

- package_boundary: `spec_only` — no code, no lib modification.
- core_hits: none — config schema only.
- 3 quality gates (Packet/Insight/Resonance) are reused from HF Paper Insight epic, not re-invented.
- ThunderOMLX semantic socket reuse per OQ-02 (NO new instance, per AC-10).
- Knowledge ingest order per OQ-05 (raw sync, derived async).
