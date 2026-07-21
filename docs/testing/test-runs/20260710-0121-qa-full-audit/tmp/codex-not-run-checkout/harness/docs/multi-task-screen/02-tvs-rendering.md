# 02 — TVS Rendering Contract (multi-task screen v2)

**Sprint**: `sprint-20260520-solar-harness-request-multi-task-screen-product-ui-redesi-s02-architecture` / N2
**Upstream**: `01-view-model.md` (view model contract), `lib/tvs_render_cli.ts` (TVS CLI)
**Authority**: This file + `fixtures/tvs_payload.example.json` are the single source of truth for
the TVS rendering layer. S03 MUST implement `screen_tvs_payload()` exactly as specified here.
Any change to the function signature or payload shape requires updating this doc in the same PR.

---

## 1. TVS Capability Confirmation

`harness/lib/tvs_render_cli.ts` exists and supports two payload formats:

| Format | Discriminator | Notes |
|--------|--------------|-------|
| **v1 SemanticIR** | top-level `root` key | `{"canvas": {"width": N}, "root": {...}}` |
| **v2 LayoutDSL**  | top-level `layout` or `sections` key | `{"canvas": {"width": N}, "sections": [...]}` |

The `screen_tvs_payload()` contract defined here uses **v2 LayoutDSL with bare `sections`**
(TVS CLI `normalizeV2` wraps these into `{layout: {type: "card", sections: [...]}}` automatically).

The CLI is invoked via:
```
bun harness/lib/tvs_render_cli.ts render --width N --colors off < payload.json
```

or via the existing `render_tvs()` helper at line 1880 in `multi_task_runner.py`.

---

## 2. `screen_tvs_payload()` — Function Signature

```python
def screen_tvs_payload(
    view_model: dict,
    args: argparse.Namespace,
    width: int,
) -> dict:
    """Convert a screen_view_model() dict to a TVS v2 payload dict.

    Args:
        view_model: Output of screen_view_model(). Must have schema_version
                    == "multi_task_screen.view_model.v1".
        args:       argparse Namespace from the 'screen' sub-command.
                    May contain 'layout' override ('stacked'|'two_column'|'auto').
        width:      Terminal column count (int, clamped to 40..240).
                    Determines layout mode when args.layout == 'auto' or absent.

    Returns:
        Dict ready to be JSON-serialised and piped to tvs_render_cli.ts.
        Top-level keys: kind, layout, header, canvas, style, sections.
        The `sections` array is directly consumable by TVS v2 normalizeV2.

    Raises:
        ValueError: if view_model['schema_version'] != 'multi_task_screen.view_model.v1'.
    """
```

### Invariants

- The function is **pure** — no side effects, no I/O, no subprocess calls.
- It MUST check `view_model["schema_version"]` first; mismatch → `ValueError`.
- It MUST NOT read from `multi_task_runner.handle_command()` or any raw runner result.
  All data comes from the already-computed `view_model` dict.
- All cell values MUST be pre-trimmed strings; no raw integers, datetimes, or UUIDs.

---

## 3. Layout Modes

| Mode          | Width trigger  | Column arrangement |
|---------------|----------------|-------------------|
| `stacked`     | `width < 100`  | Single column; all 4 sections stacked vertically |
| `two_column`  | `width >= 100` | Left column: panes section; right column: workers + last_dispatch + dag |

Selection logic (precedence order):

1. If `args.layout` is `'stacked'` or `'two_column'` → use that value directly.
2. If `args.layout` is `'auto'` or absent → derive from `width`:
   - `width < 100` → `stacked`
   - `width >= 100` → `two_column`

The resolved layout mode is stored in the returned payload as the top-level `"layout"` field
(`"stacked"` or `"two_column"`). Renderers downstream MAY inspect this field to adjust
column-divider positioning; TVS CLI itself ignores it (unknown field).

### Canonical breakpoints

| Mode         | Primary use case                     |
|--------------|--------------------------------------|
| `stacked`    | 80×20 tmux cockpit pane (default)    |
| `two_column` | 120×24 full-screen or wider terminal |

---

## 4. Sections Specification

`sections` is an ordered array with exactly 4 entries in stacked mode. In two_column mode the
same 4 logical sections are present but the renderer may split them across columns.

### 4.1 Section: `panes`

```json
{
  "id": "panes",
  "type": "table",
  "label": "Panes",
  "columns": [
    {"key": "slot",   "label": "slot",   "width": 6},
    {"key": "role",   "label": "role",   "width": 6},
    {"key": "state",  "label": "state",  "width": 8},
    {"key": "model",  "label": "model",  "width": 7},
    {"key": "marker", "label": "·",      "width": 1}
  ],
  "rows": [ ...8 objects with keys slot/role/state/model/marker... ]
}
```

- Exactly 8 rows (one per pane). Source: `view_model["panes"]`.
- `slot` format: `main:N` or `lab:N`.
- `state` MUST be one of the 10 canonical state words (from schema); no internal states.
- `marker` is one ASCII char (`" "` idle, `">"` working, `"*"` attention).
- Column widths are ADVISORY for stacked@80; in two_column@120 the table uses the full
  left-column width.

### 4.2 Section: `workers`

```json
{
  "id": "workers",
  "type": "kv",
  "label": "Workers",
  "items": [
    {"key": "active",   "value": "0 / 8"},
    {"key": "dry_run",  "value": "8"},
    {"key": "idle",     "value": "0"},
    {"key": "blocked",  "value": "0"}
  ]
}
```

- Source: `view_model["workers"]`.
- `active` is rendered as `"{active} / {tracked}"`.
- Count fields come from `view_model["workers"]["counts"]`.

### 4.3 Section: `last_dispatch`

```json
{
  "id": "last_dispatch",
  "type": "kv",
  "label": "Last Dispatch",
  "items": [
    {"key": "time",   "value": "20:01"},
    {"key": "pane",   "value": "main:3"},
    {"key": "role",   "value": "evaluator"},
    {"key": "sprint", "value": "S04"},
    {"key": "node",   "value": "N8-eval"}
  ]
}
```

- Source: `view_model["last_dispatch"]`.
- `sprint` maps from `view_model["last_dispatch"]["target_sprint_short"]`.
- `node` maps from `view_model["last_dispatch"]["target_node"]`.
- Full sprint ids (`sprint-20260519-...`) are **forbidden** here per PRD §Visual.
  The view model guarantees `target_sprint_short` already uses the `S04` format.

### 4.4 Section: `dag`

```json
{
  "id": "dag",
  "type": "kv",
  "label": "DAG · S04",
  "items": [
    {"key": "pass",      "value": "7"},
    {"key": "pending",   "value": "1"},
    {"key": "reviewing", "value": "1"},
    {"key": "ready",     "value": "N/A"}
  ]
}
```

- Source: `view_model["dag"]`.
- `label` is composed as `"DAG · " + view_model["dag"]["sprint_short"]`.
- `ready` is `", ".join(view_model["dag"]["ready"])` or `"N/A"` when the list is empty.
- Count values are converted to strings (no raw integers in the payload).

---

## 5. Top-Level Payload Shape

The full payload returned by `screen_tvs_payload()`:

| Field     | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `kind`    | string | yes      | Always `"screen"`. Identifies payload type for log/debug. |
| `layout`  | string | yes      | `"stacked"` or `"two_column"`. Resolved layout mode. |
| `header`  | string | yes      | One-line status banner. Max `width` chars. |
| `canvas`  | object | yes      | `{"width": N}`. Passed through to TVS CLI via `--width`. |
| `style`   | string | yes      | TVS style name. Default `"solar_default"`. |
| `sections`| array  | yes      | Ordered array of 4 section objects (§4.1–§4.4). |

`kind`, `layout`, and `header` are Solar extension fields — TVS CLI v2 ignores them
(they sit at the top level alongside `sections`; `normalizeV2` only reads `sections`).

### Header format

```
◉ Solar Harness  ·  {overall}  ·  {width}×{height}
```

- `{overall}` from `view_model["health"]["overall"]` — one of `ok | warn | error`.
- `{width}` and `{height}` are the terminal size used for this render.
- Truncated to `width` characters if longer.

---

## 6. TVS CLI Interface

`screen_tvs_payload()` output is consumed by the **existing** `render_tvs()` helper. No new
subprocess helper is needed in S03 — only `tvs_payload()` is replaced by `screen_tvs_payload()`.

### Invocation path (S03 implementation)

```python
payload = screen_tvs_payload(view_model, args, width)
proc = subprocess.run(
    [str(harness), "tvs", "render", "--width", str(width), "--colors", "off"],
    input=json.dumps(payload, ensure_ascii=False),
    capture_output=True, text=True, timeout=8,
)
```

The `sections` array is read by `normalizeV2`:
```typescript
// tvs_render_cli.ts normalizeV2 branch:
if (payload.sections) {
  return {
    canvas: { width: opts.width },
    style: payload.style || opts.style,
    layout: { type: "card", sections: payload.sections },
  };
}
```

TVS ignores `kind`, `layout`, `header` (not in its v2 schema).

### Error handling

If the subprocess exits non-zero or raises `subprocess.TimeoutExpired`, the caller MUST:
1. Log the stderr excerpt to `meta.degraded` (add `{"source": "tvs_render", "reason": "tvs_render_error"}`).
2. Fall back to the plain-text renderer (see §7).
3. NOT re-raise — the fallback output is always acceptable.

---

## 7. `draw_screen()` TVS-First Scheduling

```
draw_screen(view_model, messages, args)
    │
    ├─ 1. Check TVS availability
    │       is_tvs_available() → bool
    │       (subprocess check: `bun harness/lib/tvs_render_cli.ts --help` exits 0)
    │
    ├─ if TVS available:
    │   ├─ 2a. payload = screen_tvs_payload(view_model, args, width)
    │   ├─ 2b. output  = tvs_render_subprocess(payload)   # → string
    │   └─ 2c. print(output)   # pre-rendered; print as-is
    │
    └─ if TVS unavailable or render fails:
        ├─ 2d. lines = screen_fallback_render(view_model, width, max_lines)
        └─ 2e. print("\n".join(lines))
```

**Strict invariant**: both the TVS path and the fallback path consume the **same `view_model`
dict** — no additional data fetching. The view model is the single source of truth.

`is_tvs_available()` result is cached for the lifetime of one `screen_loop()` call
(checked once per screen session start, not per frame). Cache TTL = session duration.

### Scheduling priority

| Priority | Condition | Renderer used |
|----------|-----------|---------------|
| 1st      | TVS subprocess succeeds (exit 0) | `screen_tvs_payload()` → TVS CLI |
| 2nd      | TVS unavailable OR subprocess fails | `screen_fallback_render()` (N3 contract) |

**TVS is never retried mid-session** if it fails once. Once the session marks TVS as degraded,
it stays on fallback for the rest of the session to avoid flicker and inconsistent frames.

---

## 8. Width Budget

At `width=80` (stacked), the panes section uses these column widths:

```
│ slot  │ role │ state    │ model  │·│
│ 6     │ 6    │ 8        │ 7      │1│  = 28 data + 6 separators = 34 chars
```

Remaining 80 − 34 = 46 chars are used for box borders, labels, and padding.

At `width=120` (two_column), the panes section occupies 60 cols (left column);
workers/last_dispatch/dag share 58 cols (right column, 2-char gutter).

---

## 9. S03 Implementation Checklist

These items are NOT implemented in S02 (architecture only) but MUST be in S03:

- [ ] `screen_tvs_payload(view_model, args, width) -> dict` in `multi_task_runner.py`
- [ ] `is_tvs_available() -> bool` cached check (subprocess + cache flag)
- [ ] Replace `tvs_payload(result, width)` call in `render_tvs()` with `screen_tvs_payload(view_model, args, width)`
- [ ] `draw_screen()` updated to call `screen_view_model()` first, then TVS/fallback dispatch
- [ ] `meta.degraded` populated with `tvs_render_error` on subprocess failure

---

## 10. Out of Scope (this node)

- **Fallback renderer** — owned by N3 (`03-fallback-rendering.md`).
- **Compatibility / migration plan** — owned by N4 (`04-compatibility-migration.md`).
- **S03 Python implementation** — this document is architecture-only.
- **TVS v2 source code modifications** — we use TVS as-is, no changes to TVS internals.
