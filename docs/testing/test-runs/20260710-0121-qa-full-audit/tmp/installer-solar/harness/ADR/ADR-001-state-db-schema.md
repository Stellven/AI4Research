# ADR-001 — State DB Independent Schema

**Status**: Accepted  
**Date**: 2026-05-09  
**Sprint**: sprint-20260509-solar-product-platform S6

## Context

Solar Harness tracks sprint state in two places:
1. `sprints/*.status.json` — per-sprint JSON files, authoritative for coordinator bash
2. `~/.solar/solar.db` — shared SQLite with 250+ tables for all Solar subsystems

Neither provides a structured task/slice lifecycle table that allows:
- Querying "which slices are pending/blocked/passed for sprint X"
- Tracking pane assignments alongside lease state
- Structured event log tied to slice-level lifecycle

## Decision

Introduce `$HARNESS_DIR/run/state.db` as a **dedicated harness control-plane DB**.

Rationale:
- Avoids schema pollution in solar.db (250+ tables already)
- Can be deleted and rebuilt from status.json files (state.db is a cache, not canonical)
- Allows Python autopilot to query without bash shelling
- WAL mode + busy_timeout=5s handles concurrent coordinator + autopilot access

Six tables: `tasks`, `assignments`, `leases`, `events`, `artifacts`, `capabilities`

## Consequences

- state.db is **supplementary**: coordinator bash continues writing status.json; state.db is a derived/parallel view
- Double-write maintained per plan.md C10: old status.json/events.jsonl not deleted
- state.db loss is non-fatal — init_db() recreates schema on next autopilot call
