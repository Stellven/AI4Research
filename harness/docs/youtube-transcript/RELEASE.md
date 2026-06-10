# YouTube Transcript Acquisition Ladder Release Notes

Sprint: `sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构`

## Scope

This release note records the S01-S05 evidence set for the YouTube transcript acquisition ladder. The release path is local-first:

1. Prefer creator-provided YouTube captions.
2. Prefer YouTube ASR captions before local ASR.
3. Route high-value local ASR through `faster-whisper large-v3` or `WhisperX large-v3` when captions are missing or unusable.
4. Keep premium cloud ASR as an optional escape hatch, disabled by default because of cost policy.
5. Gate report usage by transcript quality and evidence traceability.

## Sprint Summary

| Sprint | Purpose | Status |
|---|---|---|
| S01 Requirements | Define acquisition ladder, quality gates, priority queue, ledger, and report eligibility requirements. | accepted |
| S02 Architecture | Split caption discovery, ASR routing, quality scoring, premium escape, and dashboard concerns. | accepted |
| S03 Core Runtime | Implement acquisition ladder modules, transcript ledgers, ASR routing, quality checks, and cleanup helpers. | accepted |
| S04 Orchestration UI | Add dashboard and CLI command paths for discovery, acquisition, audit, process, and regression checks. | accepted |
| S05 Verification Release | Verify real dashboard/CLI evidence, premium policy, production cleanup gate, regression aggregation, and release closure. | in verification |

## S05 Evidence Paths

| Node | Evidence |
|---|---|
| V1 Dashboard/CLI E2E | `~/.solar/harness/reports/youtube/s05-acceptance/V1-cli_discover.json` |
| V1 Transcript Status | `~/.solar/harness/reports/youtube/s05-acceptance/V1-transcript_status.json` |
| V2 Premium Optional Policy | `~/.solar/harness/reports/youtube/s05-acceptance/V2-premium_optional_local_asr_policy.json` |
| V2 Premium Contract Unit | `~/.solar/harness/reports/youtube/s05-acceptance/V2-premium_contract_unit.json` |
| V3 Backup | `~/.solar/harness/reports/youtube/s05-acceptance/V3-backup_path.json` |
| V3 Production Schema Gate | `~/.solar/harness/reports/youtube/s05-acceptance/V3-production_schema_semantic_gate.json` |
| V4 Regression Aggregation | `~/.solar/harness/reports/youtube/s05-acceptance/V4-regression_report.json` |

## Key Numbers

| Metric | Value | Note |
|---|---:|---|
| Acceptance checks carried by epic | 67 | S01-S04 acceptance base |
| Architecture decisions | 13 | S02 decision set |
| Open questions | 4 | OQ set tracked through S05 |
| Historical cleanup target | 165 | Original fixture target for polluted transcript rows |
| Production literal count | 337 | `transcript_clean IS NOT NULL` is invalid for current production schema |
| Production semantic pollution count | 0 | Safe gate: `length(trim(transcript_clean)) > 0` |
| Premium ASR cost formula | `$0.006 * ceil(minutes)` | Enforced only when premium is enabled |
| Premium daily budget cap | `$20` | Enforced by `youtube_premium_asr_calls` ledger |

## Premium ASR Policy

Premium ASR is not the default path. The default release path is local high-quality ASR:

- `faster_whisper_large_v3` for P0/P1 high-value videos.
- `whisperx_large_v3_diarization` for multi-speaker P0 cases.
- `faster_whisper_medium` for P2 cases.

Premium provider calls are optional and require `SOLAR_YOUTUBE_PREMIUM_OPENAI_KEY`. Without that key, the pipeline must not block the release path or attempt paid cloud calls.

## Rollback

SQLite backup restore:

```bash
cp ~/.solar/harness/backups/youtube/20260529T122641Z/youtube.db.backup \
  ~/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite
```

Module rollback targets:

```text
lib/youtube/acquisition_ladder.py
lib/youtube/premium_escape.py
lib/youtube/pollution_repair.py
lib/youtube/dashboard.py
lib/youtube/cli.py
lib/youtube/report_eligibility.py
```

Config rollback targets:

```text
lib/youtube_config.py
config/youtube*.yaml
```

## ATLAS Hook Notes

ATLAS should monitor:

- Caption acquisition fallback rate.
- Transcript quality tier distribution.
- `missing` rows with non-empty transcript material.
- Premium ASR budget rejection.
- Report eligibility rejects caused by low-quality transcript evidence.

## Carried-Over Items

| ID | Item | Release Position |
|---|---|---|
| OQ-C5-01 | Browser caption capture stability | carried over |
| OQ-C5-02 | Premium provider real E2E | optional, gated by user cost policy |
| OQ-C5-03 | Long-video diarization quality threshold | carried over |

## Release Risk Notes

- Real paid OpenAI transcription was not executed because premium ASR is disabled by user cost policy.
- Production cleanup must use semantic non-empty transcript material, not `IS NOT NULL`, because the current schema uses `NOT NULL DEFAULT ''`.
- YouTube report generation must continue to reject low-quality transcript evidence.

