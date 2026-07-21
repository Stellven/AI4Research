# Solar Product Platform — CHANGELOG

## v1.0.0 (2026-05-09)

First productized release of Solar Harness. Eight slices, one sprint.

### S0 — Pre-Change Snapshot & Restore

- `lib/product_snapshot.py`: SHA256 manifest-based snapshot + restore dry-run
- `solar-harness product snapshot|restore|verify` CLI
- Secrets excluded from plaintext snapshots by default
- 15/15 round-trip tests PASS

### S1 — Installer & Container Validation

- `installer/install.sh`: interactive + non-interactive wizard with vault detection
- `installer/upgrade.sh`: version-guarded upgrade with pre-upgrade snapshot
- `installer/doctor.sh`: environment health check (`--json` output)
- `installer/restore.sh`: versioned snapshot restore
- `config/defaults.yaml`: canonical default config
- `.env.example`: secret placeholder template
- `gitleaks.toml`: secret scanning rules (Anthropic/OpenAI/Google/z.ai/DeepSeek)
- `docker/Dockerfile` + `docker/smoke-test.sh`: G2 container validation image
- Pre-commit + pre-push hooks: secret scan before any git operation
- 38/38 installer tests PASS

### S2 — Skill Platform & Lifecycle

- `config/skills/registry.yaml`: canonical skill registry (5 built-in stable skills)
- `lib/skill_metrics.py`: per-skill event emission to events.jsonl
- `lib/skill_export.py`: package + export skill bundles
- `lib/solar_skills.py`: extended CLI (inventory/registry/promote/demote/eval)
- `evals/packs/skill-coverage/pack.yaml`: skill-platform eval pack
- 26/26 skill lifecycle tests PASS

### S3 — Storage & Data Access

- `config/storage.solar.yaml`: unified storage role config (Obsidian/QMD/MinerU/Mirage)
- `lib/source_manifest.py`: _sources ingestion manifest with SHA256 dedup
- `lib/qmd_adapter.py`: QMD rebuild + broken-link pre-check + abort guard
- `config/mirage.solar.yaml`: corrected mount contract (8 canonical mounts)
- Launchd plist template for background ingestion
- 26/26 storage tests PASS

### S4 — Extension Framework

- `schemas/plugin.schema.json` + `schemas/capability.schema.json`
- 5 plugin manifests: obsidian (closed_loop), qmd (default_usable), mineru (basic_usable), mirage (closed_loop), mermaid (basic_usable)
- `lib/plugin_loader.py`: manifest validation + scope enforcement + install/disable/list
- `lib/capability_registry.py`: sync 17 capabilities to state DB + scorecard
- `solar-harness integrations` extended with plugins/install/disable/list/validate/capabilities/sync-caps
- `ADR/ADR-003-plugin-sandbox-scope-checked.md`
- 23/23 extension framework tests + 36/36 Mirage regression PASS

### S5 — Evolution Engine

- `lib/failure_miner.py`: mine events.jsonl failure clusters keyed by actor:event:reason
- `lib/eval_runner.py`: weighted eval pack runner with expect_field/expect_min/expect_exit
- `lib/evolution_engine.py`: full loop — failure mining → experiment → dual-gate promotion → demotion → scorecard
- `evals/packs/plugin-health/pack.yaml` + `evals/packs/skill-coverage/pack.yaml`
- `experiments/exp-001-qmd-closed-loop/hypothesis.md`: D5.1 closed-loop experiment template
- 17/17 evolution engine tests PASS

### S6 — Control Plane

- `lib/solar_state_db.py`: schema migration + six-table state DB
- `lib/task_queue.py`: task lifecycle (pending→running→done/failed) with lease TTL
- `lib/pane_lease.py`: pane lease acquire/release/heartbeat
- `lib/autopilot.py`: three-state autopilot (idle/active/paused) with watchdog
- `solar-harness leases` + `solar-harness s6-autopilot` subcommands
- `ADR/ADR-001-state-db-schema.md` + `ADR/ADR-005-autopilot-three-states.md`
- 23/23 control plane tests PASS

### S7 — Release Tooling & Final Audit

- `release/build.sh`: tarball builder with SHA256 manifest
- `release/publish.sh`: pre-publish audit gate (secret scan + schema validate + TVS renderer G8)
- `release/CHANGELOG.md`: this file
- `docs/upgrade-guide.md`: upgrade procedure
- `docs/rollback-guide.md`: rollback procedure
- `ADR/ADR-002-skill-packaging-evolution.md`: skill package + evolution ADR
- `ADR/ADR-004-release-artifact-structure.md`: release artifact design ADR
- `tests/release/`: release audit test suite

### Known Limitations

- D7.2 (container round-trip) requires Docker daemon; smoke-test.sh is implemented but daemon was unavailable during this sprint. Resume: `bash docker/smoke-test.sh` once Docker Desktop is running.
- TVS rendering is a required release dependency: Bun and `SOLAR_TVS_ROOT` must be configured before installer doctor or release publish can pass.
