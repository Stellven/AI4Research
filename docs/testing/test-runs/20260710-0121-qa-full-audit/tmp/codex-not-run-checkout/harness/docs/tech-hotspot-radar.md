# Tech Hotspot Radar

Unified YouTube / Social / GitHub tech hotspot scanning pipeline.

## CLI Reference

```bash
python3 scripts/tech_hotspot_radar.py [--config PATH] [--db PATH] <command>
```

### Commands

| Command | Description |
|---------|-------------|
| `init` | Create SQLite tables (23 tables) |
| `status` | Show row counts and recent pipeline runs |
| `doctor` | Health check: schema, failures, storage, retries |
| `seed [all\|youtube\|social\|github]` | Import seed data from config |
| `preprocess-fixture` | N1B: Create local preprocess evidence atom fixtures |
| `premium-gate-fixture` | N1B: Test premium gating logic |
| `model-router-test` | N1B: Verify model router mappings |
| `budget-trim-test` | N1B: Verify budget trimming priorities |
| `premium-mock-test` | N1B: Prove raw text never reaches premium model |
| `verifier-fixture` | N1B: Create verifier fixture |
| `youtube-fixture` | N2: YouTube pipeline fixture (9 ACs) |
| `social-fixture` | N3: Social pipeline fixture (9 ACs) |
| `github-fixture` | N4: GitHub pipeline fixture (9 ACs) |
| `report-fixture` | N5: Cross-source report fixture (8 ACs) |

### Flags

- `--config PATH` — Override config YAML path (default: `config/tech-hotspot-radar.yaml`)
- `--db PATH` — Override SQLite database path (default: `~/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite`)

## Configuration

Config file: `config/tech-hotspot-radar.yaml`

### Sections

- **youtube** — 50 channels with channel_id, name, url, category, priority, scan_rotation_group
- **social** — 151 accounts with handle, display_name, category, tier; category_weights and tier_weights for account weighting
- **github** — 9 topics and 9 tracked repos
- **hot_score_weights** — Per-source weight formulas (YouTube 0.30/0.20/0.20/0.15/0.10/0.05, Social 0.25/0.20/0.20/0.15/0.10/0.10, GitHub 0.30/0.20/0.15/0.15/0.10/0.10)
- **alert_rules** — Severity thresholds for hotspot alerts
- **fetch** — Timeout, user_agent, rate limiting
- **schedule** — Cron schedule for daily runs
- **output** — Database path and raw output directory

## Daily Schedule

### Recommended Cron

```bash
# Run daily at 6:00 AM local time
0 6 * * * cd ~/Solar/harness && python3 scripts/tech_hotspot_radar.py init && python3 scripts/tech_hotspot_radar.py seed all
```

### Disable Schedule

```bash
# Comment out or remove the cron entry
crontab -e
# Remove the line containing tech_hotspot_radar.py
```

Or set `schedule.enabled: false` in `config/tech-hotspot-radar.yaml`.

## Database Schema

23 tables total:

- **YouTube**: youtube_channels, youtube_videos, youtube_video_snapshots, youtube_transcripts
- **Social**: social_accounts, social_posts, social_post_snapshots, social_clusters
- **GitHub**: github_topics, github_repos, github_star_snapshots
- **Cross-source**: hotspot_events, cross_source_links, hotspot_alerts
- **Pipeline**: pipeline_runs, retry_queue
- **Reasoning (N1B)**: evidence_atoms, hotspot_clusters, reasoning_packets, premium_reasoning_results, insight_verifications, token_ledger
- **Metadata**: _meta

## Output Artifacts

Reports written to `Knowledge/_raw/tech-hotspot-radar/YYYY-MM-DD/`:

- `{youtube,social,github}-report.md` — Source-specific Markdown reports
- `unified-overview.md` — Daily unified overview
- `alerts.json` / `alerts.md` — Alert summaries
- `transcripts.jsonl` — Transcript package
- `report.html` — Gmail-safe HTML report
- `wiki-dispatch.md` — Wiki ingest dispatch for Knowledge integration

## Rollback

```bash
# Remove the database
rm -f ~/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite

# Remove output artifacts
rm -rf ~/Knowledge/_raw/tech-hotspot-radar/

# Remove config (if needed)
rm -f ~/Solar/harness/config/tech-hotspot-radar.yaml

# Existing scripts (youtube_influence_digest.py, ai_influence_daily.py, github_trends_digest.py)
# remain untouched and continue to work independently
```

## Testing

```bash
bash tests/test-tech-hotspot-radar.sh
```

105 assertions covering: init, status, doctor, seed, schema integrity, N1B reasoning pipeline, N2 YouTube, N3 Social, N4 GitHub, N5 Reporting.
