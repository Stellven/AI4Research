# 03 — Fallback Rendering Contract (multi-task screen v1)

**Sprint**: `sprint-20260520-...-s02-architecture` / N3
**Companion contracts**: `01-view-model.md` (data shape) + `fixtures/view_model.example.json` (sample input) + `fixtures/snapshot_{80x20,120x24}.expected.txt` (golden snapshots)
**Authority**: this file pins the public signature `render_screen_status_lines(view_model, width, height) -> list[str]` and the width-allocation algorithm. S03 (core-runtime) MUST consume the view model contract without renaming fields and emit text that matches the golden snapshots when fed `view_model.example.json`.

> **Why a separate fallback path?**
> When the TVS (terminal-visual-system) renderer is unavailable (e.g. ssh into a minimal shell, dumb-pipe in CI, evaluator headless run), the screen MUST still degrade to a readable plain-text view. Fallback is the *floor* — no emoji, no nested frames, no wide-character surprises. It does not aim to look pretty; it aims to be machine-greppable and visible on any 80-column terminal.

---

## 1. Signature

```python
def render_screen_status_lines(
    view_model: dict,
    width: int,
    height: int,
) -> list[str]:
    """Render a multi_task_screen.view_model.v1 dict as a fallback text screen.

    Args:
      view_model: parsed JSON that conforms to fixtures/view_model.schema.json.
      width:      target terminal columns (display columns, not bytes).
      height:     target terminal rows (lines), upper bound (not a fill).

    Returns:
      list[str]: each element is one display line. Every line satisfies
        wcswidth(line) <= width (NOT byte-length; see §3). len(list) <= height.

    Raises:
      ValueError: schema_version mismatch (consumer-side responsibility, not the renderer's).
    """
```

`view_model` is the contract from `01-view-model.md`. Renderer is a **pure function** over `view_model`; it MUST NOT read tmux state, files, or environment variables. If the producer can't give the renderer up-to-date data, the producer is responsible for filling `meta.degraded[]`.

---

## 2. Output Shape Constraints

| Rule | Reason | Validation |
|---|---|---|
| `len(returned_lines) <= height` | hard upper bound on screen rows | unit test: assert per `(width, height)` pair |
| `wcswidth(line) <= width` for every line | columns, not bytes; CJK / wide-char safe | unit test using `unicodedata.east_asian_width` |
| ASCII-only printable chars (U+0020..U+007E) | emoji rejected, box-drawing rejected | regex `re.search(r"[^\x20-\x7E]", line)` returns None for every line |
| No multi-line nested table frames (no `┌─┐`, `│`, `└─┘` stacked) | tmux + dumb terminals choke; we'd lose alignment | golden snapshot diff |
| At minimum four headings present: `PANE MAP`, `WORKERS`, `LAST`, `DAG` | locked by acceptance #3 | grep test |
| No full sprint id (`sprint-NNNNNNNN-letter…`) in body text | unreadable in 80 cols; we use 4-char shorts like `S04`, `N8-eval` | regex `sprint-[0-9]{8}-[a-z]` returns 0 matches |
| Deterministic for identical input | golden snapshot diff must be stable | byte-for-byte compare against fixtures |

---

## 3. Width Computation Rule (wcswidth)

The render layer measures **display columns**, not bytes. Most code paths in the broader codebase use a helper named `_display_width()` / `_clip_display()`; this renderer MUST use the same helper (or any equivalent `unicodedata.east_asian_width` lookup) so a single CJK / fullwidth character counts as 2 columns.

```python
import unicodedata

def display_width(s: str) -> int:
    """Sum of display columns for s.

    East-Asian Width values map to columns:
      'F' (fullwidth), 'W' (wide)  -> 2 cols
      'H' (halfwidth), 'Na'         -> 1 col
      'A' (ambiguous)               -> 1 col   # we resolve as 1; matches xterm default
      'N' (neutral)                 -> 1 col
    Control chars (< 0x20)           -> 0 cols  # rejected, but we count defensively
    """
    cols = 0
    for ch in s:
        if ord(ch) < 0x20:
            continue
        eaw = unicodedata.east_asian_width(ch)
        cols += 2 if eaw in ("F", "W") else 1
    return cols
```

Even though this renderer is ASCII-only by policy, the helper is wcswidth-aware so a producer bug that leaks a wide character is **caught** rather than silently corrupted into a wrong-width line. Concretely: if `view_model.panes[i].model == "宽字体"`, the line ends up *longer than width*; the renderer MUST throw the line into a clip path that truncates by display columns, not by `s[:N]` indexing.

```python
def clip_display(s: str, width: int) -> str:
    """Right-truncate s so display_width(result) <= width."""
    out: list[str] = []
    used = 0
    for ch in s:
        w = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        if used + w > width:
            break
        out.append(ch)
        used += w
    return "".join(out)
```

This is the **same shape** as the existing `_clip_display` used by `multi_task_runner.render_screen_status_lines`. The fallback function reuses it.

---

## 4. 80-Column Layout Algorithm

For `width=80, height=20` (golden snapshot: `fixtures/snapshot_80x20.expected.txt`):

```
[ line  1 ]  title line: "Solar Multi-Task    <generated_at_local>   health:<overall>   intent:<source_intent>"
[ line  2 ]  "=" * 80                                                  # full-width separator
[ line  3 ]  "PANE MAP" + pad + "HEALTH"                               # two-column section heading
[ line  4 ]  pane row 0 (main:0)        + pad + health capsule 0
[ line  5 ]  pane row 1 (main:1)        + pad + health capsule 1
[ line  6 ]  pane row 2 (main:2)        + pad + health capsule 2       # marker '>' if state == "working"
[ line  7 ]  pane row 3 (main:3)        + pad + health capsule 3
[ line  8 ]  pane row 4 (lab:0)         + pad + (empty)                # lab panes overflow vertically
[ line  9 ]  pane row 5 (lab:1)         + pad + "DEGRADED"             # degraded heading sits beside lab:1
[ line 10 ]  pane row 6 (lab:2)         + pad + degraded[0]
[ line 11 ]  pane row 7 (lab:3)
[ line 12 ]  WORKERS line  (active/tracked + counts inline)
[ line 13 ]  LAST line     (time, role, pane, target = short_sprint/short_node)
[ line 14 ]  DAG line      (sprint_short, counts, ready=[…])
[ line 15 ]  "-" * 80                                                  # bottom separator
[ line 16 ]  footer:       "fallback render  80x20  ascii-only  no-emoji"
[ line 17 ]  ...                                                       # left blank for future expansion
...
[ line 20 ]  (height limit)
```

### Column allocation (80 cols total)

| Region | Cols | Notes |
|---|---|---|
| left half (PANE MAP table)  | 42 | `  ` indent (2) + 7 (pane id `lab:N `) + 6 (role) + 8 (state) + 9 (model) + a few trailing spaces |
| middle gutter               |  4 | breathing room |
| right half (HEALTH capsules) | 34 | name + 5-char state + free-form detail clipped to 18 |

The marker (`" "` or `">"`) lives at column 1 of the pane row, so the eye scans the leftmost glyph to find the "active pane." Anything else would lose the affordance.

### Mandatory headings (acceptance #3)

`render_screen_status_lines` MUST emit a line containing each of the literal strings `PANE MAP`, `WORKERS`, `LAST`, `DAG` (case-sensitive, no decoration) so grep tests pass.

### Short identifiers (acceptance #4)

Full sprint ids `sprint-YYYYMMDD-<slug>-sNN-<slice>` are *forbidden* in body text — they don't fit in 80 cols. The fallback uses:

- `view_model.last_dispatch.target_sprint_short` (e.g. `S04`) plus
- `view_model.last_dispatch.target_node` (e.g. `N8-eval`)

Producers MUST fill the short form. The renderer does NOT extract `^sprint-...$` regex chunks; if the producer ships a long id by mistake, the renderer clips it but the acceptance grep still catches the leak.

### Emoji & box drawing (acceptance #5, #6)

Emoji codepoints (U+1F000..U+1FAFF and the older U+2600..U+27BF symbol block) are **forbidden** in the renderer's output. The marker field is locked by `view_model.schema.json` to `^[\x20-\x7E]$` (single printable ASCII), so the producer can't sneak emoji in. The renderer additionally:

- Treats any non-ASCII code point as a clip target (drop or replace with `?`).
- Does NOT use `┌─┐│└┘╔╗╚╝═║` for tables. The 80x20 snapshot uses `=` (line 2) and `-` (line 15) as separators *only*; tables are alignment-spaced, not box-framed.

The 120x24 layout also forbids box characters (see §5). Acceptance #6 explicitly checks for `┌─┐` (multi-frame nesting) which is the failure mode we are protecting against.

---

## 5. 120-Column Layout Algorithm

For `width=120, height=24` (golden snapshot: `fixtures/snapshot_120x24.expected.txt`):

```
[ line  1 ]  expanded title: "Solar Multi-Task   <gen>   overall:<o>   source intent:<si>   width=120 height=24"
[ line  2 ]  "=" * 120
[ line  3 ]  "PANE MAP"
[ line  4 ]  main:0 PM   ready  ...   (idle)            |  lab:0   LAB    ready    GLM        (dry-run worker)
[ line  5 ]  main:1 PLAN ready  ...   (idle)            |  lab:1   LAB    ready    GLM        (dry-run worker)
[ line  6 ]> main:2 BUILD working ... (this pane)       |  lab:2   LAB    ready    GLM        (dry-run worker)
[ line  7 ]  main:3 EVAL ready  ...   (idle)            |  lab:3   LAB    ready    Sonnet     (dry-run worker)
[ line  8 ]  (blank)
[ line  9 ]  "HEALTH" + pad + "DEGRADED"
[ line 10 ]  health capsule 0     |  degraded[0]
[ line 11 ]  health capsule 1     |
[ line 12 ]  health capsule 2     |
[ line 13 ]  health capsule 3     |
[ line 14 ]  (blank)
[ line 15 ]  WORKERS  active=N  tracked=N  counts: dry_run=N idle=N blocked=N active=N
[ line 16 ]  LAST     <time>     <role>  pane=<pane>  target = <sprint_short> / <node>
[ line 17 ]  DAG      <sprint_short>  counts: pass=N pending=N reviewing=N   ready: (...)
[ line 18 ]  (blank)
[ line 19 ]  "-" * 120
[ line 20 ]  footer: "fallback render  width=120 height=24  ascii-only  no-emoji  no-nested-frames"
[ line 21..24 ]  reserved (blank) — height budget for future expansion
```

### Column allocation (120 cols total)

| Region | Cols | Notes |
|---|---|---|
| main pane row (left side)   | 60 | id + role + state + model + parenthetical role hint |
| gutter `  |  `              |  4 | single vertical bar with two-space padding either side; this is NOT a table frame, just a visual divider |
| lab pane row (right side)   | 56 | same shape as left; lab panes sit beside their main counterpart |
| WORKERS / LAST / DAG lines  | full | one logical row per concept, never wrap |

The 120-col layout is **wider but not denser**. It does NOT add a second table; it gives each existing element more breathing room. This is on purpose — the fallback path is the *floor* renderer, not the *rich* renderer (that's TVS's job).

### Why no nested frames in 120x24

Even at 120 cols, terminals like macOS Terminal default theme, `tmux` capture, `script(1)`, and pipe-to-file in CI all degrade box-drawing differently. A render that uses `┌`, `─`, `┐`, `│`, `└`, `─`, `┘` to draw a sub-table inside another sub-table breaks visually on at least one of those targets. We avoid the problem class entirely by alignment-spacing, with at most one `|` divider per row.

---

## 6. Field Mapping (view_model → fallback)

| view_model field | Fallback usage |
|---|---|
| `schema_version`           | consumer checks before calling renderer; renderer asserts `== multi_task_screen.view_model.v1` |
| `generated_at` (optional)  | renders into title; if absent, omit time chunk |
| `width_hint` / `height_hint` (optional) | hints only; the explicit `width, height` args override |
| `health.overall`           | title: `health:<value>` |
| `health.capsules[]`        | HEALTH section: name + state + detail |
| `panes[]`                  | PANE MAP section — 8 fixed rows |
| `panes[i].marker`          | first character of each pane row (the `>` affordance) |
| `panes[i].state`           | tokenized state name; ASCII only; no rewrites |
| `workers.active` / `tracked` / `counts.*` | WORKERS line |
| `last_dispatch.time` / `role` / `pane` / `target_sprint_short` / `target_node` | LAST line |
| `dag.sprint_short` / `counts.*` / `ready[]` | DAG line |
| `meta.source_intent`       | title: `intent:<value>` |
| `meta.degraded[]`          | DEGRADED block — each entry as `<source> : <reason>` |

No transformation of values (no humanization, no relative-time conversion). Producers do the formatting; renderer is dumb.

---

## 7. Snapshot Fixtures

| Fixture | Width | Height | Used by |
|---|---|---|---|
| `fixtures/snapshot_80x20.expected.txt` | 80 | 20 | S05 fallback snapshot test (golden compare) |
| `fixtures/snapshot_120x24.expected.txt` | 120 | 24 | S05 fallback snapshot test (golden compare) |

Both snapshots are byte-for-byte stable when the renderer is fed `fixtures/view_model.example.json` with the corresponding `(width, height)` pair. **Updating a snapshot requires bumping the layout doc here AND landing the new fixture in the same PR.**

---

## 8. Error Modes

| Condition | Behavior |
|---|---|
| `schema_version != "multi_task_screen.view_model.v1"` | renderer raises `ValueError("incompatible schema")`; caller prints fallback message and exits non-zero (per `01-view-model.md` §2) |
| `len(view_model["panes"]) != 8`              | renderer raises `ValueError("panes must be exactly 8")`; producers must NOT shrink the array (filled with `state="missing"` placeholders) |
| `width < 40` or `height < 10`                | renderer raises `ValueError`; we don't render into sub-40 col terminals |
| any pane `marker` not in `[\x20-\x7E]`       | producer already failed schema; renderer treats as a defensive bug, prints space `" "` and continues |
| any line would exceed `width` after clip     | renderer clips silently using `clip_display(line, width)` (see §3) |

The renderer is **defensive** in the sense that ASCII guarantees are double-checked, but it is **strict** about line count (`height`) and contract (`schema_version`) — those are producer bugs, not renderer fallbacks.

---

## 9. Negative-case Enforcement Matrix

Each acceptance check has a paired negative test that the snapshot fixtures reject if violated:

| # | Acceptance check | Negative-case sentence |
|---|---|---|
| 1 | `wc -l snapshot_80x20.expected.txt ≤ 20` | snapshot with 21+ lines fails immediately |
| 2 | `awk '{print length}' ... ≤ 80` per line | a single line of length 81 fails the check |
| 3 | snapshot contains `PANE MAP`, `WORKERS`, `LAST`, `DAG` | removing any heading is caught |
| 4 | grep `sprint-[0-9]{8}-[a-z]` returns 0 matches | leaking a full sprint id is caught |
| 5 | grep high-unicode chars returns 0 matches | a stray emoji is caught |
| 6 | no `┌`, `─`, `┐` nested frames in 120x24 | adding a sub-table is caught |
| 7 | this doc ≥ 80 lines, with `wcswidth` + 80/120 algorithm | shorter / missing section caught by N3 evaluator |

---

## 10. Open Questions (deferred to S03)

1. **Localization of headings**: currently `PANE MAP`, `WORKERS`, etc. are English-only. CN locale would need locale-aware strings AND wcswidth-aware spacing. Out of scope for v1.
2. **Truncation glyph**: when `clip_display` cuts a line, do we append `…` (U+2026, 1 col) or `...` (3 cols)? Current choice: `...` because v1 is ASCII-only. Revisit when localization happens.
3. **Empty `view_model.dag.ready`**: rendered as `ready=[]` in 80-col, `ready: (none)` in 120-col. Producer guarantees array (possibly empty) — renderer never sees `None`.

These items do not block the gate; they're carry-over notes for S03 implementer.
