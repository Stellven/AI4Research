# TUI Pane Recover & Clean Pane Lifecycle Governance — Release Notes

Epic: `epic-20260527-p0-solar-harness-tui-pane-recover-与-clean-pane-生命周期治理`
Date: 2026-05-28
Status: S05 verification-release

---

## Epic Overview

This epic adds pane recovery, clean-pane lifecycle management, and structured repair to the Solar Harness runtime. It spans 5 sprints (S01–S05) covering requirements, architecture, core runtime, verification, and release.

The core deliverable is a 6-module system that detects pane anomalies, clears stale state, re-injects persona context, writes dual-engine ledger records, and supports autopilot respawn with ATLAS structured repair fallback.

---

## Sprint Summaries

### S01 — Requirements

Delivered 7 objects (O1–O7) with 32 acceptance criteria across:
- O1: `PaneHygieneRegistry` (19-field schema, 6-state FSM, atomic transitions)
- O2: `RecoverDetector` (3 prompt types, per-prompt clear strategy)
- O3: `PaneClearManager` (task-finish `/clear` trigger, 3-step completion check)
- O4: `PersonaReinjector` (persona + context + runtime policy injection)
- O5: Evaluator dispatch (spillover pool, `--max-items` collision avoidance)
- O6: `LedgerWriter` (dual-engine JSONL+SQLite, 6+ fields, reassign extras)
- O7: Safety guardrails (4 PROTECTED sets, `py_compile`, minimal regression)

Key numbers: 32 AC, 7 objects, 5 open questions resolved.

### S02 — Architecture

Resolved 7 decisions (D1–D7) and 5 open questions (OQ-01–OQ-05):
- D1: pane-hygiene 19-field schema with FSM states
- D2: 6-state FSM (clean → running → dirty → cooling → needs_recover → needs_respawn)
- D3: Prompt detector classifier (DET-PROCEED, DET-NONE, DET-RECOVER)
- D4: `/clear` three-step protocol (send-keys + verify + confirm)
- D5: Persona reinjection on clean→running transition
- D6: Dual-engine ledger (JSONL append + SQLite WAL)
- D7: Spillover pool (1 primary + 4 spillover = 5 candidate panes)
- OQ-01: Persistence frequency (in-memory cache + atomic write)
- OQ-02: Retry thresholds (3 attempts, 5/10/15s backoff)
- OQ-03: Re-injection frequency (full on clean→running)
- OQ-04: Spillover pool size (1+4=5)
- OQ-05: Respawn command (kill-pane + split-window + ready marker)

### S03 — Core Runtime

Added all 6 production modules + init script + config + tests:
- `lib/pane_hygiene_registry.py` — 19-field registry with FSM
- `lib/recover_detector.py` — 3-type prompt classifier
- `lib/pane_clear_manager.py` — FSM-driven clear with retry
- `lib/persona_reinjector.py` — template-based persona injection
- `lib/ledger_writer.py` — dual-engine JSONL+SQLite writer
- `lib/dispatch_scheduler.py` — spillover, respawn, PROTECTED guard
- `scripts/init_pane_hygiene.py` — tmux discovery + registry init
- `run/spillover_config.yaml` — pool configuration
- 9 test files in `tests/` with 118 pytest cases

### S04 — Verification (Skipped)

S04 was absorbed into S05 per coordinator decision. All verification activities performed directly in S05 nodes V1–V4.

### S05 — Verification & Release

6 DAG nodes executed:

| Node | Role | Evidence Files | Key Result |
|------|------|---------------|------------|
| V1_real_production_e2e | Production E2E against live tmux | 5 JSON (init, capture, clear, reinject, state) | 5/5 AC evidence produced; PersonaReinjector verify limited by bare-shell env |
| V2_autopilot_respawn_e2e | 5-step respawn + ATLAS repair | 4 JSON (success, kill_fail, split_fail, marker_timeout) | 6/6 verdicts PASS; isolated real LedgerWriter + hygiene registry |
| V3_concurrent_stress | Ledger consistency + spillover + latency | 3 JSON (consistency, collision, latency) | 300/300 dual-write consistency; p99=153ms; spillover 3-distinct |
| V4_regression_aggregation | Cross-sprint regression | 1 JSON (44 records) | 44/44 PASS; 118 pytest baseline |
| V5_release_docs_epic_close_prep | Release docs + eval | RELEASE.md + eval files | This document |
| V6_join_epic_close_ready | Join gate | (pending) | Awaits all V1–V5 acceptance |

---

## V1–V4 Evidence Paths

All evidence files located under `~/.solar/harness/reports/tui-pane/s05-acceptance/`:

```
V1-init.json              # tmux session + fixture panes verified
V1-capture.json           # RecoverDetector real capture-pane classification
V1-clear.json             # PaneClearManager FSM transitions (dirty→cooling→needs_recover→needs_respawn)
V1-reinject.json          # PersonaReinjector send-keys (70 new lines in pane diff)
V1-state.json             # 8 PROTECTED panes untouched verification

V2-success.json           # 5-step respawn: kill→split→marker(0.01s)→hygiene→ledger
V2-kill_fail.json         # ATLAS structured repair for non-existent pane kill
V2-split_fail.json        # ATLAS structured repair for invalid split-window
V2-marker_timeout.json    # ATLAS structured repair for marker timeout (5.2s)

V3-ledger_consistency.json  # 300/300 JSONL==SQLite, 0 missing, fallback sub-tests
V3-spillover_collision.json # 3 concurrent dispatch → 3 distinct panes (no collision)
V3-p99_latency.json         # p50=0.29ms, p95=9.36ms, p99=153.42ms, max=306.09ms

V4-regression_report.json   # 44 records: 32 S01-AC + 7 S02-D + 5 OQ, all PASS
```

### Key Numbers

| Metric | Value |
|--------|-------|
| Total acceptance criteria verified | 32 (S01) |
| Architecture decisions validated | 7 (S02 D1–D7) |
| Open questions resolved | 5 (OQ-01–OQ-05) |
| Regression records | 44 (32+7+5) |
| Pytest baseline | 118 passed |
| Dual-write consistency test | 300/300 records |
| Spillover collision test | 3/3 distinct panes |
| Ledger p99 latency | 153.42ms (SLO ≤ 200ms) |
| Ledger p50 latency | 0.29ms (SLO ≤ 100ms) |
| PROTECTED panes preserved | 8/8 across all V1–V4 runs |

---

## Rollback Commands

To fully remove the tui-pane-recover epic deliverables:

```bash
# 6 production modules
rm -f ~/.solar/harness/lib/pane_hygiene_registry.py
rm -f ~/.solar/harness/lib/pane_clear_manager.py
rm -f ~/.solar/harness/lib/pane_constants.py
rm -f ~/.solar/harness/lib/recover_detector.py
rm -f ~/.solar/harness/lib/persona_reinjector.py
rm -f ~/.solar/harness/lib/ledger_writer.py

# Dispatch module (shared with broader dispatch; remove only if epic rollback is total)
# rm -f ~/.solar/harness/lib/dispatch_scheduler.py

# Init script
rm -f ~/.solar/harness/scripts/init_pane_hygiene.py

# Config
rm -f ~/.solar/harness/run/spillover_config.yaml

# Runtime state
rm -f ~/.solar/harness/run/pane-hygiene.json

# 9 test files
rm -f ~/.solar/harness/tests/test_pane_hygiene_registry.py
rm -f ~/.solar/harness/tests/test_pane_clear_manager.py
rm -f ~/.solar/harness/tests/test_pane_constants.py
rm -f ~/.solar/harness/tests/test_pane_handoff_evidence.py
rm -f ~/.solar/harness/tests/test_pane_lifecycle_jobs.py
rm -f ~/.solar/harness/tests/test_recover_detector.py
rm -f ~/.solar/harness/tests/test_persona_reinjector.py
rm -f ~/.solar/harness/tests/test_ledger_writer.py
rm -f ~/.solar/harness/tests/test_dispatch_scheduler.py

# E2E test script
rm -f ~/.solar/harness/lib/test_v2_autopilot_respawn_e2e.py

# Evidence directory
rm -rf ~/.solar/harness/reports/tui-pane/

# Template fixtures
rm -rf ~/.solar/harness/templates/persona
rm -f ~/.solar/harness/templates/runtime_policy.md
rm -f ~/.solar/harness/templates/solar_context_*.md
```

---

## ATLAS Hook Registration Guidance

The ATLAS structured repair system provides failure detection and recovery. To register hooks for pane lifecycle events:

### 1. Ledger Fallback Hook

Production `LedgerWriter._dual_write` writes to a fallback JSONL file when either engine (JSONL or SQLite) fails. The fallback file includes `_fallback_reason` field. To add ATLAS repair enqueue:

```python
# In lib/ledger_writer.py, after fallback file write:
def _dual_write(self, record: dict) -> bool:
    jsonl_ok = self._write_jsonl(record)
    sqlite_ok = self._write_sqlite(record)
    if not (jsonl_ok and sqlite_ok):
        fallback_record = {**record, "_fallback_reason": f"jsonl={jsonl_ok},sqlite={sqlite_ok}"}
        self._write_fallback(fallback_record)
        # TODO: Add ATLAS repair enqueue
        # atlas_repair.enqueue(
        #     failure_type="LEDGER_ENGINE_FAILURE",
        #     context={"pane_id": record.get("pane_id"), "reason": fallback_record["_fallback_reason"]},
        #     repair_strategy="structured_repair",
        # )
    return jsonl_ok or sqlite_ok
```

### 2. Respawn Failure Hook

The `DispatchScheduler.begin_respawn` method already checks preconditions. To add ATLAS repair on respawn failure:

```python
# In lib/dispatch_scheduler.py, begin_respawn failure path:
def begin_respawn(self, pane_id, **kwargs):
    if not self.can_respawn(pane_id).ok:
        # Record failure in ledger
        self.ledger.record_respawn(pane_id, success=False, reason="precondition_failed", ...)
        # TODO: Add ATLAS repair enqueue
        # atlas_repair.enqueue(
        #     failure_type="RESPAWN_PRECONDITION_FAILED",
        #     context={"pane_id": pane_id, "reason": "max_concurrent_exceeded_or_protected"},
        #     repair_strategy="structured_repair",
        # )
        return ScheduleResult(ok=False, reason=...)
```

### 3. Registering with Coordinator

Add to coordinator's hook configuration:

```yaml
# In harness config or coordinator startup:
atlas_hooks:
  - trigger: "ledger_engine_failure"
    action: "structured_repair"
    max_retries: 2
  - trigger: "respawn_precondition_failed"
    action: "structured_repair"
    max_retries: 2
  - trigger: "pane_clear_failed"
    action: "structured_repair"
    max_retries: 2
```

**Current status**: The fallback buffer mechanism is in production. ATLAS repair enqueue is not yet wired; V3 AC4 noted this as a partial deficit. This is a carried-over item for a future sprint.

---

## Carried-Over Open Questions (OQ-S03-01..03)

Three open questions from S03 Core Runtime remain unresolved at S05 close:

### OQ-S03-01: ClearLedger / record_clear Signature Mismatch

- **Description**: Interface deviation between `ClearLedger` class and the `record_clear` function signatures. The method parameters and return types diverge from the S01 contract specification.
- **Status**: Open
- **Owner**: coordinator
- **Impact**: Integration between S03 modules and downstream consumers may encounter type errors at runtime. The current code works with implicit duck-typing, but formal interface validation will fail.
- **Resolution path**: Add a protocol/ABC class in `lib/pane_constants.py` that both `ClearLedger` and `record_clear` implement. Run `mypy --strict` to validate.

### OQ-S03-02: JSONL Field Count 10 vs 11

- **Description**: The `dispatch-ledger.jsonl` schema has inconsistent field counts across records. Some records contain 10 fields, others 11. The discrepancy is in an optional `task_id` field that is present in `reassign` records but not in `recover`/`clear` records.
- **Status**: Open
- **Owner**: coordinator
- **Impact**: Downstream consumers parsing JSONL with strict field-count expectations will fail on mixed records. The `LedgerWriter` produces correct data; the issue is in the schema specification, not the implementation.
- **Resolution path**: Update the schema to declare `task_id` as optional. Add a JSONL schema version field for forward compatibility.

### OQ-S03-03: Linter API Deviations (Import Style)

- **Description**: The Python linter modifies absolute imports to relative style (e.g., `from lib.x` → `from .x`). When `lib/` lacks `__init__.py`, this causes `ImportError` on fresh checkout after lint.
- **Status**: Open
- **Owner**: coordinator
- **Impact**: CI/CD pipelines that run lint before test will break on fresh clones. Current workaround: `lib/` has no `__init__.py` and uses `sys.path.insert` in test files.
- **Resolution path**: Either (a) add `__init__.py` to `lib/` and switch to package-relative imports, or (b) configure linter to skip import rewriting in `lib/`. Option (a) is preferred for long-term maintainability.

---

## Known Deficits

1. **PersonaReinjector verify on bare shell** (V1 AC4): `verify_injection` keyword check fails when template content is sent via send-keys to zsh (parsed as commands). Works correctly when target pane runs Claude Code.
2. **Ledger ATLAS hook not wired** (V3 AC4): `_dual_write` writes fallback JSONL but does not call ATLAS repair API. Fallback mechanism verified; ATLAS integration is a future sprint item.
3. **Tail latency max=306ms** (V3 AC3): p99=153ms is within 200ms SLO, but max=306ms exceeds it. Under heavier concurrent load this could degrade further.
4. **V2 uses isolated ATLAS adapter** (V2): The test uses an `AtlasStructuredRepair` adapter that records through `LedgerWriter`, not an external ATLAS endpoint. Production ATLAS integration is pending.

---

*Generated: 2026-05-28T23:35:00Z*
*Node: V5_release_docs_epic_close_prep*
*Sprint: sprint-20260527-p0-solar-harness-tui-pane-recover-与-clean-pane-生命周期治理-s05-verification-release*
