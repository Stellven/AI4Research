# 01 — View Model Contract (multi-task screen v1)

**Sprint**: `sprint-20260520-solar-harness-request-multi-task-screen-product-ui-redesi-s02-architecture` / N1
**Schema version**: `multi_task_screen.view_model.v1`
**Authority**: this file + `fixtures/view_model.schema.json` + `fixtures/view_model.example.json` are the single source of truth for the view model layer. S03 (core-runtime) MUST consume these without renaming fields. Any rename or removal MUST land in this doc + schema bump + design.md §4/§9 in the same PR.

> **Why a separate view model layer?**
> Both render paths (TVS, fallback) used to compute their own fields from the raw `multi_task_runner.handle_command()` result. Field drift was the failure mode (see historical sprint `sprint-20260520-161147`). This view model normalises the contract: render paths are pure projections, the runtime layer is the only producer.

---

## 1. Top-level Shape

The view model is a single JSON object with **seven required top-level fields**:

| Field            | Type    | Required | Description                                        |
|------------------|---------|----------|----------------------------------------------------|
| `schema_version` | string  | yes      | Pins the contract. Const `multi_task_screen.view_model.v1`. |
| `health`         | object  | yes      | Overall + per-capsule runtime health.              |
| `panes`          | array   | yes      | Exactly 8 entries (main 0..3, lab 0..3).           |
| `workers`        | object  | yes      | Multi-task worker summary + sub-state counts.      |
| `last_dispatch`  | object  | yes      | Most recent dispatch row.                          |
| `dag`            | object  | yes      | Currently focused slice DAG summary.               |
| `meta`           | object  | yes      | Source intent + degraded source list.              |

Three optional fields are permitted (renderer hints):

| Field          | Type    | Notes                                          |
|----------------|---------|------------------------------------------------|
| `generated_at` | string  | ISO 8601 UTC instant of snapshot.              |
| `width_hint`   | integer | Renderer hint for terminal columns (40..240). |
| `height_hint`  | integer | Renderer hint for terminal rows (10..100).    |

`additionalProperties: true` at the top level so future renderer hints can be added without bumping `schema_version`. **Inside** every nested object `additionalProperties: false` — drift inside the contract is a hard error.

---

## 2. `schema_version`

- **Type**: string, `const: "multi_task_screen.view_model.v1"`
- **Legal values**: exactly one literal value. Any other value is a schema FAIL.
- **Invariant**: the consumer MUST inspect `schema_version` before reading any field. Mismatch → fallback renderer prints `incompatible schema` and exits non-zero (design.md §8).
- **When to bump**: only when removing or renaming a field. Adding optional fields is non-breaking and does NOT require a bump.

---

## 3. `health`

```jsonc
{
  "overall": "ok|warn|error",
  "capsules": [
    {"name": "coordinator", "state": "ok",   "detail": "pid 2391"},
    {"name": "tmux",        "state": "ok",   "detail": "session ready"},
    {"name": "models",      "state": "warn", "detail": "1 quota low"},
    {"name": "profile",     "state": "ok",   "detail": "default"}
  ]
}
```

### Fields

| Field              | Type   | Required | Notes |
|--------------------|--------|----------|-------|
| `overall`          | string | yes      | Enum `ok | warn | error`. |
| `capsules`         | array  | yes      | minItems 1. |
| `capsules[].name`  | string | yes      | Free-form, lowercase. Canonical: `coordinator`, `tmux`, `models`, `profile`. |
| `capsules[].state` | string | yes      | Enum `ok | warn | error`. |
| `capsules[].detail`| string | yes      | Short human-readable explanation. Empty string allowed. |

### Invariants

- `overall` is a roll-up: `error > warn > ok`. If any capsule is `error`, `overall` MUST be `error`.
- The capsule list is unordered for storage but rendered in the order returned. Renderers MUST NOT sort capsules — order is producer-controlled.
- `detail` is rendered as suffix text; do NOT cram structured data in there. Use degraded sources (`meta.degraded`) for machine-readable observability.

---

## 4. `panes` (the critical 8-row invariant)

```jsonc
[
  {"plane": "main", "slot": 0, "role": "PM",    "state": "ready",   "model": "Opus",   "marker": " "},
  ...
  {"plane": "lab",  "slot": 3, "role": "LAB",   "state": "ready",   "model": "Sonnet", "marker": " "}
]
```

### Invariants

- `panes.length == 8` always. `minItems: 8, maxItems: 8` in schema.
- Even if a tmux session is missing (`lab` not started), the array MUST contain placeholder rows with `state = "missing"`. Producers MUST NOT shrink the array.
- Canonical order: `main:0, main:1, main:2, main:3, lab:0, lab:1, lab:2, lab:3`. Renderers MAY depend on this order.
- Six required fields per pane: `plane`, `slot`, `role`, `state`, `model`, `marker`. No additional properties.

### Field semantics

| Field    | Type    | Legal values                                                                                  | Invariant |
|----------|---------|-----------------------------------------------------------------------------------------------|-----------|
| `plane`  | string  | Enum `main | lab`.                                                                            | Pinned to two values. |
| `slot`   | integer | `0..3`.                                                                                       | Each `(plane, slot)` pair appears at most once across the array. |
| `role`   | string  | `PM | PLAN | BUILD | EVAL | LAB` (typical).                                                  | Free-form short token; renderer truncates at ~6 chars. |
| `state`  | string  | Fixed 10-word enum: `ok, warn, error, idle, active, blocked, dry_run, ready, working, missing`. | NO additions without schema bump. |
| `model`  | string  | Free-form (`Opus`, `Sonnet`, `Haiku`, `GLM`, …).                                              | Empty string forbidden. |
| `marker` | string  | `^[\x20-\x7E]$` — exactly one printable ASCII char.                                            | Emoji rejected by schema pattern. Common: `" "` (idle), `">"` (working), `"*"` (attention). |

### Why the 10-word state enum

PRD §Visual Rules locks `ok|warn|error|idle|active|blocked|dry_run|ready|working` — 9 words for living panes. We add `missing` so a non-running pane stays in the array (preserves layout) instead of vanishing. Adding more words is a UX surface change — handle it via a schema bump, not a silent producer change.

### Why ASCII-only `marker`

PRD §Visual Rules explicitly forbids emoji because terminal columns must be predictable. The pattern `^[\x20-\x7E]$` (U+0020..U+007E) excludes every emoji code point (all live in U+1F000+ or higher SMP planes) and any wide CJK glyph. `maxLength: 1` is a defence-in-depth so a stray multi-byte sequence still fails fast.

---

## 5. `workers`

```jsonc
{
  "active": 0,
  "tracked": 8,
  "counts": {"dry_run": 8, "idle": 0, "blocked": 0, "active": 0}
}
```

### Fields

| Field             | Type    | Invariant                                                  |
|-------------------|---------|------------------------------------------------------------|
| `active`          | integer | `>= 0` and `<= tracked`.                                   |
| `tracked`         | integer | `>= 0`. Total workers known to the runner snapshot.        |
| `counts.dry_run`  | integer | `>= 0`.                                                    |
| `counts.idle`     | integer | `>= 0`.                                                    |
| `counts.blocked`  | integer | `>= 0`.                                                    |
| `counts.active`   | integer | `>= 0`. SHOULD equal top-level `active` field.             |

The sum `dry_run + idle + blocked + active` SHOULD equal `tracked`. Drift is tolerated by the renderer but flagged in `meta.degraded` with `{source: "workers", reason: "count_drift"}`.

---

## 6. `last_dispatch`

```jsonc
{
  "time": "20:01",
  "role": "evaluator",
  "pane": "main:3",
  "target_sprint_short": "S04",
  "target_node": "N8-eval"
}
```

### Invariants

- `time` is **5 chars exactly**, pattern `^[0-9]{2}:[0-9]{2}$`. Date intentionally omitted to stay under 80 columns. Full absolute timestamps live in `events.jsonl`.
- `pane` MUST match `^(main|lab):[0-3]$`. Free-form pane labels are rejected so renderers can rely on the parse.
- `target_sprint_short` MUST match `^S[0-9]+$`. **Full sprint ids are forbidden** — surfacing `sprint-20260519-solar-harness-vnext-...-s04-orchestration-ui` breaks the 80x20 layout. PRD §Visual.
- `target_node` is free-form short token (`N8-eval`, `D3`, `N1`).
- All five fields required.

---

## 7. `dag`

```jsonc
{
  "sprint_short": "S04",
  "counts": {"pass": 7, "pending": 1, "reviewing": 1},
  "ready": []
}
```

### Fields

| Field                | Type    | Invariant                                              |
|----------------------|---------|--------------------------------------------------------|
| `sprint_short`       | string  | `^S[0-9]+$`. Full sprint id forbidden.                 |
| `counts.pass`        | integer | `>= 0`. Closed nodes that passed evaluation.           |
| `counts.pending`     | integer | `>= 0`. Nodes not yet picked up by a builder.          |
| `counts.reviewing`   | integer | `>= 0`. Nodes in evaluator review.                     |
| `ready`              | array   | Short labels of ready nodes (`["N1", "N3"]`).          |

`ready` MAY be empty. Empty array → fallback renders `ready=N/A`.

---

## 8. `meta`

```jsonc
{
  "source_intent": "screen",
  "degraded": [{"source": "lab", "reason": "lab_session_missing"}]
}
```

### Fields

| Field             | Type   | Invariant                                                      |
|-------------------|--------|----------------------------------------------------------------|
| `source_intent`   | string | Enum `screen | status`. Identifies the Control-Plane intent that produced this view model. |
| `degraded`        | array  | Each entry has `{source, reason}`. Empty array means all data sources are healthy. |
| `degraded[].source` | string | Free-form data source id (`lab`, `autopilot`, `tvs_render`, …). |
| `degraded[].reason` | string | Short code-like reason. Canonical: `lab_session_missing`, `capture_timeout:<pane>`, `tvs_render_error`, `count_drift`. |

---

## 9. Compatibility & migration

- **S03 implements**: `screen_view_model(result, args, width) -> dict` returning this shape. Function signature is pinned in design.md §9.
- **TVS path** (`screen_tvs_payload`) and **fallback path** (`render_screen_status_lines`) MUST both consume the dict produced by `screen_view_model`. Re-computing fields downstream is a regression of historical issue G6 (field drift).
- **`multi-task status`** (unrelated debug command) is unchanged; this view model only governs `multi-task screen`.
- **Old wide-table renderer** — to be deleted in S03. No `--legacy` flag (PRD §Compatibility).
- **`--json` flag** — reserved for S04 to dump the view model JSON; not implemented in S03.

---

## 10. Test fixtures

- `fixtures/view_model.example.json` — canonical instance mirroring design.md §4. Must pass `jsonschema.validate(example, schema)`.
- `fixtures/view_model.schema.json` — JSON Schema Draft 2020-12. Use as input to `jsonschema.Draft202012Validator`.

### Validation invocation (Python)

```bash
python3 -c '
import json, jsonschema
schema = json.load(open("harness/docs/multi-task-screen/fixtures/view_model.schema.json"))
example = json.load(open("harness/docs/multi-task-screen/fixtures/view_model.example.json"))
jsonschema.Draft202012Validator.check_schema(schema)
jsonschema.validate(example, schema, cls=jsonschema.Draft202012Validator)
print("OK")
'
```

### What the schema enforces (proven by N1 negative tests)

| Mutation                              | Schema rejects? |
|---------------------------------------|-----------------|
| `marker = "🔥"`                       | yes — pattern `^[\x20-\x7E]$` |
| `state = "exploding"`                 | yes — enum 10 words           |
| `panes.length = 7`                    | yes — `minItems: 8`           |
| `schema_version = "...v2"`            | yes — `const`                 |
| missing `dag` top-level               | yes — `required`              |
| `dag.sprint_short = "sprint-..."`     | yes — pattern `^S[0-9]+$`     |
| `marker = ">>"`                       | yes — `maxLength: 1`          |
| `last_dispatch.time = "2026-05-20 20:01"` | yes — pattern `^[0-9]{2}:[0-9]{2}$` |
| `panes[0].plane = "control"`          | yes — enum `main|lab`         |

---

## 11. Out of scope

- **Schema v2 design** — out of scope until a real breaking change shows up. Don't pre-design.
- **Render layer contracts** — owned by N2 (`02-tvs-rendering.md`) and N3 (`03-fallback-rendering.md`).
- **Compatibility / migration plan** — owned by N4 (`04-compatibility-migration.md`).
- **Consolidated architecture** — owned by N5 (`multi-task-screen-ui-v2.md`).

This file pins **only** the view model dictionary shape.
