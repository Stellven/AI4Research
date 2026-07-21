# Multi-Task Screen UI v2 — Consolidated Architecture

**Sprint**: `sprint-20260520-solar-harness-request-multi-task-screen-product-ui-redesi-s02-architecture` / N5
**Date**: 2026-05-21
**Status**: Architecture-complete (S02). Implementation target: S03.

This document is the **single entry point** for the multi-task screen v2 architecture.
It consolidates the four node-level contracts (N1–N4) into one navigable reference.

> Source documents (relative to `harness/docs/multi-task-screen/`):
> - `01-view-model.md` — N1: View model contract
> - `02-tvs-rendering.md` — N2: TVS rendering contract
> - `03-fallback-rendering.md` — N3: Fallback rendering contract
> - `04-compatibility-migration.md` — N4: Compatibility & migration plan

---

## 1. Architecture Overview

### 1.1 Three-Layer Architecture

```
╔═══════════════════════════════════════════════════════════════╗
║                     CONTROL PLANE                             ║
║  harness multi-task screen [--layout stacked|two_column|auto] ║
║  draw_screen(view_model, messages, args)                      ║
║  is_tvs_available() → bool  (cached per session)             ║
╚═══════════════════════════════╦═══════════════════════════════╝
                                │
                         screen_view_model(args)
                                │
                                ▼
╔═══════════════════════════════════════════════════════════════╗
║                      VIEW MODEL LAYER                         ║
║  screen_view_model() → dict                                   ║
║  schema_version: "multi_task_screen.view_model.v1"            ║
║  7 fields: health / panes / workers / last_dispatch /         ║
║            dag / meta / schema_version                        ║
║  Producer: multi_task_runner.py (S03)                        ║
║  Source of truth: 01-view-model.md + view_model.schema.json  ║
╚══════════════╦════════════════════════════╦══════════════════╝
               │ TVS available              │ TVS unavailable /
               │                           │ render failed
               ▼                           ▼
╔═════════════════════╗        ╔══════════════════════════════╗
║    TVS RENDERER     ║        ║     FALLBACK RENDERER        ║
║  screen_tvs_payload ║        ║ render_screen_status_lines   ║
║  (view_model,       ║        ║ (view_model, width, height)  ║
║   args, width)      ║        ║ → list[str]                  ║
║  → dict (JSON)      ║        ║                              ║
║  ↓                  ║        ║ Plain ASCII, 4 headings:     ║
║  bun tvs_render_cli ║        ║ PANE MAP / WORKERS /         ║
║  → rendered string  ║        ║ LAST / DAG                   ║
╚═════════════════════╝        ╚══════════════════════════════╝
```

### 1.2 Data Flow Summary

```
tmux capture-pane
        │
        ▼
screen_view_model()     ← pure function, no renderers
        │
        ├──[TVS path]──→ screen_tvs_payload() → bun tvs_render_cli.ts → print
        │
        └──[fallback]──→ render_screen_status_lines() → print("\n".join(lines))
```

### 1.3 Key Design Principles

1. **Single source of truth** — `screen_view_model()` is the only place that reads
   tmux/process state. Renderers are pure projections over the view model dict.
2. **TVS-first with session-level latch** — TVS is checked once per screen session;
   after one failure the session stays on fallback to prevent frame flicker.
3. **`multi-task status` is frozen** — the debug command is preserved byte-for-byte.
   The new `screen` sub-command is additive.
4. **Schema version gates breaking changes** — `schema_version` must be bumped for
   any field rename/removal; additions are non-breaking.

---

## 2. View Model Layer (N1)

> Full spec: `harness/docs/multi-task-screen/01-view-model.md`

### 2.1 Schema

```python
SCHEMA_VERSION = "multi_task_screen.view_model.v1"

def screen_view_model(args: argparse.Namespace) -> dict:
    """Produce a multi_task_screen.view_model.v1 dict from live harness state."""
```

The view model has **seven required top-level fields**:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string const | `"multi_task_screen.view_model.v1"` |
| `health` | object | `overall: ok\|warn\|error` + `capsules[]` |
| `panes` | array[8] | Exactly 8 pane entries (main:0..3, lab:0..3) |
| `workers` | object | Worker summary + sub-state counts |
| `last_dispatch` | object | Most recent dispatch row |
| `dag` | object | Currently focused sprint DAG slice |
| `meta` | object | `source_intent` + `degraded[]` list |

Three optional renderer hints: `generated_at`, `width_hint`, `height_hint`.

### 2.2 Pane State Words (frozen for v1)

```
ok | warn | error | idle | active | blocked | dry_run | ready | working | missing
```

These 10 words are the only legal values for `panes[].state`. Synonyms (`busy`,
`running`, `queued`) are forbidden in the view model layer.

### 2.3 Five Cockpit Questions ↔ View Model Fields

The multi-task screen v2 answers the 5 cockpit questions an operator needs at a glance:

| # | Cockpit question | View model field(s) | Display section |
|---|-----------------|---------------------|-----------------|
| Q1 | Which panes are running and on what model? | `panes[].slot`, `panes[].state`, `panes[].model`, `panes[].role` | PANE MAP / panes section |
| Q2 | How many workers are active vs. blocked? | `workers.counts.active`, `workers.counts.blocked`, `workers.counts.dry_run`, `workers.counts.idle` | WORKERS section |
| Q3 | What was the last dispatch, and to which pane? | `last_dispatch.pane`, `last_dispatch.target_sprint_short`, `last_dispatch.target_node`, `last_dispatch.time` | LAST section |
| Q4 | What is the overall health status? | `health.overall`, `health.capsules[]` | Header banner |
| Q5 | Which DAG nodes are ready/pending in the active sprint? | `dag.sprint_short`, `dag.ready[]`, `dag.pass_count`, `dag.pending_count`, `dag.reviewing_count` | DAG section |

---

## 3. TVS Rendering Layer (N2)

> Full spec: `harness/docs/multi-task-screen/02-tvs-rendering.md`

### 3.1 Function Signature

```python
def screen_tvs_payload(
    view_model: dict,
    args: argparse.Namespace,
    width: int,
) -> dict:
    """Convert a screen_view_model() dict to a TVS v2 payload dict.

    Pure function. No I/O, no subprocess calls.
    Raises ValueError if view_model['schema_version'] != SCHEMA_VERSION.
    Returns dict ready for json.dumps() → bun tvs_render_cli.ts render.
    """
```

### 3.2 TVS Payload Shape

```json
{
  "kind": "screen",
  "layout": "stacked | two_column",
  "header": "◉ Solar Harness  ·  {overall}  ·  {width}×{height}",
  "canvas": {"width": N},
  "style": "solar_default",
  "sections": [
    {"id": "panes",         "type": "table", "label": "Panes",         "columns": [...], "rows": [...]},
    {"id": "workers",       "type": "kv",    "label": "Workers",       "items": [...]},
    {"id": "last_dispatch", "type": "kv",    "label": "Last Dispatch", "items": [...]},
    {"id": "dag",           "type": "kv",    "label": "DAG · S04",     "items": [...]}
  ]
}
```

`kind`, `layout`, `header` are Solar extension fields; TVS CLI `normalizeV2` ignores them
(it only reads `sections`). TVS wraps bare sections into `{layout: {type:"card", sections:[...]}}`.

### 3.3 Layout Modes

| Mode | Width trigger | Arrangement |
|------|--------------|-------------|
| `stacked` | `width < 100` | 4 sections stacked vertically (default: 80-col cockpit) |
| `two_column` | `width >= 100` | panes left / workers+last_dispatch+dag right |

### 3.4 TVS CLI Invocation

```bash
bun harness/lib/tvs_render_cli.ts render --width N --colors off < payload.json
```

---

## 4. Fallback Rendering Layer (N3)

> Full spec: `harness/docs/multi-task-screen/03-fallback-rendering.md`

### 4.1 Function Signature

```python
def render_screen_status_lines(
    view_model: dict,
    width: int,
    height: int,
) -> list[str]:
    """Render view model as plain ASCII fallback screen.

    Pure function. No I/O. Returns list of display lines.
    Every line satisfies: wcswidth(line) <= width.
    len(return) <= height.
    ASCII-only printable chars (U+0020..U+007E).
    """
```

### 4.2 Output Constraints

- **ASCII-only**: `re.search(r"[^\x20-\x7E]", line)` must return `None` for every line
- **Width-safe**: `wcswidth(line) <= width` (uses `unicodedata.east_asian_width`)
- **4 mandatory headings**: `PANE MAP`, `WORKERS`, `LAST`, `DAG`
- **No full sprint IDs**: `sprint-YYYYMMDD-...` patterns are forbidden in body text
- **Deterministic**: byte-for-byte identical output for identical input (golden snapshot test)

### 4.3 Golden Snapshots

```
harness/docs/multi-task-screen/fixtures/snapshot_80x20.expected.txt   (stacked)
harness/docs/multi-task-screen/fixtures/snapshot_120x24.expected.txt  (two_column)
```

Generated by feeding `fixtures/view_model.example.json` into `render_screen_status_lines`.
S04 integration tests must diff actual output against these files.

---

## 5. Compatibility & Migration (N4)

> Full spec: `harness/docs/multi-task-screen/04-compatibility-migration.md`

### 5.1 Command Boundary

| Command | Purpose | Output format |
|---------|---------|---------------|
| `harness multi-task status` | Debug snapshot — raw runner result | **Unchanged** (format frozen) |
| `harness multi-task screen` | Interactive cockpit UI | New TVS/fallback rendered output |

**`multi-task status` output format is not changed.** S03/S04/S05 must not alter its
column headers, line ordering, or exit codes.

### 5.2 Three Rollback Paths

| # | Trigger | Rollback action |
|---|---------|-----------------|
| R1 | `screen_view_model()` raises or schema mismatch | Print single-line banner `"◉ Solar Harness  ·  error  ·  view_model unavailable"` + continue screen loop |
| R2 | TVS subprocess non-zero exit or `TimeoutExpired` (8s) | Log to `meta.degraded`; session-latch TVS as degraded; fall through to fallback renderer |
| R3 | `capture-pane` timeout or 0 panes returned | Fill 8 stub panes with `state="missing"`; set `health.overall="warn"`; return degraded-but-valid view model |

### 5.3 Schema Evolution Rules

- **Non-breaking** (no bump): add optional top-level fields, add `meta.degraded[]` entries
- **Breaking** (bump to `v2`): remove/rename any required field, change `panes[]` cardinality,
  change state word set
- **Frozen forever in v1**: `schema_version` literal, `panes[].slot` format, `panes[].state` enum,
  `health.overall` enum

### 5.4 Field Naming Authority

Authority = `view_model.schema.json`. All field names in all three rendering functions
use the `main-status` vocabulary (no camelCase, no aliases):

| `view_model` field | Rendered label | Type |
|--------------------|---------------|------|
| `panes[].slot` | `slot` | `main:0` .. `lab:3` |
| `panes[].role` | `role` | `PM`, `BUILD`, etc. |
| `panes[].state` | `state` | 10 canonical words |
| `panes[].model` | `model` | `Opus`, `GLM`, `Sonnet` |
| `workers.counts.active` | `active` | `"N / M"` string |
| `last_dispatch.target_sprint_short` | `sprint` | `S04` short format |
| `last_dispatch.target_node` | `node` | `N8-eval` |
| `health.overall` | header `{overall}` | `ok\|warn\|error` |
| `dag.sprint_short` | `DAG · {short}` label | `S04` |
| `dag.ready[]` | `ready` | `", ".join(list)` or `"N/A"` |

---

## 6. S03 Implementation Contract

> This section is the authoritative function-signature reference for S03 implementers.
> All four functions must be added to `harness/lib/multi_task_runner.py`.

### 6.1 Four Required Functions

```python
# --- Function 1: View Model Producer ---
def screen_view_model(args: argparse.Namespace) -> dict:
    """Produce multi_task_screen.view_model.v1 from live harness state.

    Reads: tmux capture-pane, process lists, events.jsonl, task_graph.json.
    Returns: dict conforming to 01-view-model.md §1.
    Never raises on pane/tmux failure — degrade gracefully via meta.degraded[].
    """

# --- Function 2: TVS Payload Builder ---
def screen_tvs_payload(
    view_model: dict,
    args: argparse.Namespace,
    width: int,
) -> dict:
    """Convert view model to TVS v2 payload dict.

    Pure function. No I/O.
    Raises ValueError if schema_version mismatch.
    Full spec: 02-tvs-rendering.md.
    """

# --- Function 3: Fallback Renderer ---
def render_screen_status_lines(
    view_model: dict,
    width: int,
    height: int,
) -> list[str]:
    """Render view model as plain ASCII fallback text screen.

    Pure function. No I/O.
    ASCII-only output, wcswidth(line) <= width for every line.
    Full spec: 03-fallback-rendering.md.
    """

# --- Function 4: Draw Dispatcher ---
def draw_screen(
    view_model: dict,
    messages: list,
    args: argparse.Namespace,
) -> None:
    """TVS-first screen dispatch.

    Calls screen_tvs_payload() + TVS CLI if is_tvs_available().
    Falls back to render_screen_status_lines() on TVS failure.
    Session-level TVS availability latch: no retry after first failure.
    Full spec: 02-tvs-rendering.md §7.
    """
```

### 6.2 Helper Function

```python
def is_tvs_available() -> bool:
    """Check if bun + tvs_render_cli.ts are usable.

    Cached for lifetime of one screen_loop() call.
    Implementation: subprocess check `bun harness/lib/tvs_render_cli.ts --help`
    exits 0 → True; any error → False.
    """
```

### 6.3 Replacement at Call Site

In `render_tvs()` (multi_task_runner.py), replace:
```python
# BEFORE (S02 baseline):
payload = tvs_payload(result, width)
# AFTER (S03):
payload = screen_tvs_payload(view_model, args, width)
```

`render_tvs()` itself is unchanged; only the payload builder call is swapped.

### 6.4 S03 Acceptance Gate

- [ ] All 4 functions in `multi_task_runner.py` with correct signatures
- [ ] `is_tvs_available()` caches result per `screen_loop()` invocation
- [ ] `multi-task status` diff vs. pre-S03 baseline = 0 bytes
- [ ] Unit tests for `screen_view_model` schema_version check
- [ ] Unit tests for `screen_tvs_payload` (stacked + two_column layout modes)
- [ ] Unit tests for `render_screen_status_lines` (4 headings present, ASCII-only)
- [ ] Unit tests for `draw_screen` TVS-first path + fallback path

---

## 7. Migration Sequence

```
S02 (Architecture) ──[evaluator passed]──▶ S03 (Core Runtime)
                                                │
                                                │ Implement 4 functions
                                                │ Replace tvs_payload() call
                                                │ Evaluator tests pass
                                                │
                                           ──[evaluator passed]──▶ S04 (Integration & Hardening)
                                                                        │
                                                                        │ E2E integration test
                                                                        │ Golden snapshot diff
                                                                        │ multi-task status regression
                                                                        │
                                                                   ──[evaluator passed]──▶ S05 (Verification Release)
                                                                                               │
                                                                                               │ Live tmux activation proof
                                                                                               │ CHANGELOG entry
                                                                                               │ multi-task status --deprecated flag
                                                                                               │
                                                                                          ──[evaluator passed]──▶ Epic PASSED
```

---

## 8. Open Items (S03 Risk Register)

| ID | Risk | Impact | Owner |
|----|------|--------|-------|
| OI-1 | TVS v2 `type="table"` section support unconfirmed | TVS may not render table sections → downgrade to `type="text"` | S03 |
| OI-2 | `capture-pane` CJK double-width alignment | Off-by-one column counts under CJK locale | S03/N3 |
| OI-3 | `bun` PATH availability in CI/ssh sessions | `is_tvs_available()` returns False → fallback always active | S03 |
| OI-4 | `panes[]` count ≠ 8 on partial tmux sessions | `screen_view_model()` must pad to exactly 8 stubs | S03 |
| OI-5 | Golden snapshot generation tool | N3 fixtures need `snapshot_80x20.expected.txt` produced by S04 | S04 |

---

## 9. Reference Index

| Artifact | Path | Node | Lines |
|----------|------|------|-------|
| View model contract | `docs/multi-task-screen/01-view-model.md` | N1 | 259 |
| TVS rendering contract | `docs/multi-task-screen/02-tvs-rendering.md` | N2 | 330 |
| Fallback rendering contract | `docs/multi-task-screen/03-fallback-rendering.md` | N3 | 274 |
| Compatibility & migration plan | `docs/multi-task-screen/04-compatibility-migration.md` | N4 | 177 |
| View model fixture | `docs/multi-task-screen/fixtures/view_model.example.json` | N1 | — |
| TVS payload fixture | `docs/multi-task-screen/fixtures/tvs_payload.example.json` | N2 | 65 |
| View model schema | `docs/multi-task-screen/fixtures/view_model.schema.json` | N1 | — |
| TVS CLI | `lib/tvs_render_cli.ts` | upstream | 230 |
| Runner (target) | `lib/multi_task_runner.py` | S03 target | — |
| This document | `docs/multi-task-screen-ui-v2.md` | N5 | — |
