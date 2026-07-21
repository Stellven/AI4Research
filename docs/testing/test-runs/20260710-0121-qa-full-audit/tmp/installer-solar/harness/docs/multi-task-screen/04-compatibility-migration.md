# 04 — Compatibility & Migration (multi-task screen v1)

**Sprint**: `sprint-20260520-solar-harness-request-multi-task-screen-product-ui-redesi-s02-architecture` / N4
**Companion contracts**: `01-view-model.md`, `02-tvs-rendering.md`, `03-fallback-rendering.md`, plus the existing runtime in `harness/lib/multi_task_runner.py`.
**Authority**: this file pins the operational boundary between the **new** `multi-task screen` UI and the **retained** `multi-task status` debug command, the rollback paths when the new UI degrades, the `schema_version` evolution policy, and the S03 → S04 → S05 migration sequence. Field naming is delegated to `view_model.schema.json`; this doc only resolves cross-vocabulary ambiguity by mapping the v1 fields onto the legacy `main-status` vocabulary.

---

## 1. Scope Boundary — `multi-task screen` (new) vs. `multi-task status` (retained)

The two subcommands have **disjoint responsibilities** and MUST NOT share a renderer, a CLI parser branch, or a snapshot fixture.

| Aspect                       | `multi-task screen` (new, this sprint)                                | `multi-task status` (retained debug)                                |
|------------------------------|------------------------------------------------------------------------|----------------------------------------------------------------------|
| Audience                     | live cockpit operator                                                  | dev/eval grep, scripts, CI log capture                               |
| Output shape                 | full-frame TVS render OR plain ASCII fallback                          | line-oriented `print_table` (legacy `multi_task_runner` columns)     |
| Refresh model                | `screen_loop()` periodic redraw                                        | one-shot per invocation                                              |
| Data source                  | `screen_view_model() → view_model.v1`                                  | direct `list_task_rows()` + per-row capture                          |
| Renderer entry point         | `draw_screen()` → `screen_tvs_payload()` OR `render_screen_status_lines()` | unchanged `multi_task_status` handler in `multi_task_runner.py`       |
| Schema authority             | `multi_task_screen.view_model.v1` (`fixtures/view_model.schema.json`)  | none (free-form columns; tests grep specific column labels)          |
| Stability promise            | breaking changes gated by `schema_version` bump                        | **output format frozen** — line/column shape is contract-by-greppability |

### 1.1 `multi-task status` retention promise

`multi-task status` is **retained as a debug command** for the foreseeable future. The S03/S04/S05 work in this epic MUST NOT alter:

- the subcommand name (`multi-task status`),
- the column headers emitted by `print_table` in the existing handler,
- the line ordering and active/dry-run grouping,
- the exit code semantics (`0` always; failures are surfaced in `evidence` strings, not exit codes),
- the truncation thresholds used by `_clip_display`.

Concretely: any test that today greps the output of `multi-task status` (column labels `multi_task / status / pane_type / tmux / sprint#node / updated`, or the active/dry-run section dividers) MUST keep passing through S05. If a future maintainer needs to refresh that handler's vocabulary, they MUST update **this doc** in the same PR and treat it as a breaking change to a separate contract — `multi-task status` is a sibling, not a child, of the new view model.

---

## 2. Field Naming Authority

The single source of truth for **field names exposed to renderers** is `view_model.schema.json` (`fixtures/view_model.schema.json`). Vocabulary inside that schema is intentionally aligned with the long-standing `main-status` words from `multi_task_runner.py` so a developer who already knows the legacy command can read the new screen.

When a name appears in both the schema and the legacy command but with different surface forms, the table below resolves the mapping. **Renderers MUST read the view_model field name** (left column) and never re-fetch from the legacy command output (right column).

| # | view_model field (authoritative)        | main-status / legacy vocabulary             | Notes                                                                 |
|---|------------------------------------------|----------------------------------------------|-----------------------------------------------------------------------|
| 1 | `panes[i].state`                         | `status` (e.g. `working`, `ready`, `idle`)   | 10 canonical state words; same enum, renamed for renderer clarity     |
| 2 | `panes[i].slot`                          | `multi_task` (e.g. `main:0`, `lab:3`)        | identical syntax (`role:N`); field renamed to avoid overloading       |
| 3 | `panes[i].model`                         | `model` column (e.g. `Sonnet`, `GLM`)        | identical values; column header normalised                            |
| 4 | `panes[i].marker`                        | (no legacy field — derived)                  | one ASCII char; new affordance owned by view model                    |
| 5 | `last_dispatch.target_sprint_short`      | implicit `sprint#node` column prefix          | enforced `^S[0-9]+$`; full sprint id forbidden in any new field        |
| 6 | `last_dispatch.target_node`              | `sprint#node` column suffix                  | e.g. `N8-eval`; same value, distinct field                            |
| 7 | `dag.sprint_short` / `dag.counts.*`      | (no legacy equivalent)                       | new aggregation, view-model-only                                      |
| 8 | `workers.active` / `workers.tracked`     | active/dry-run section counts                | identical semantics; renderer reads view_model only                   |
| 9 | `meta.source_intent`                     | (none)                                       | new field; enumerates `screen` vs `status` invocation paths           |

Rules:

1. Renderers (TVS and fallback) MUST consume only view_model fields. Reading directly from `multi_task_runner.handle_command()` or `list_task_rows()` is a regression of historical issue **G6 (field drift)**.
2. If a legacy column name needs to be exposed to the new screen, the producer (`screen_view_model()`) is the place to do the renaming, never the renderer. The renderer is dumb (see `03-fallback-rendering.md` §1).
3. Producers MUST NOT silently leak full sprint ids (`sprint-YYYYMMDD-...`) into any view_model string. The schema enforces `^S[0-9]+$` on `*_sprint_short` fields; violations are caught at schema-validate time, not at render time.

---

## 3. Rollback Paths

Three discrete failure classes are protected by named rollback paths. Each path is **detected by the producer side** and **declared in `view_model.meta.degraded[]`** so downstream tooling (CI grep, evaluator) can see exactly which fallback was taken without re-deriving from logs.

### 3.1 Rollback A — view_model production failure

**Trigger**: `screen_view_model()` raises, or its returned dict fails schema validation (`additionalProperties:false` violation inside a nested object, missing required key, `schema_version` mismatch).

**Behavior**:

1. `draw_screen()` catches the producer exception (`ValueError`, `KeyError`, `jsonschema.ValidationError`).
2. Emits a **single-line plain-ASCII banner** containing the literal string `view_model unavailable` plus the exception class name; no TVS, no fallback table.
3. Appends `{"source": "screen_view_model", "reason": "<exception_class>"}` to a transient `meta.degraded` list captured in the screen session log (NOT in the absent view_model — there is no view_model on this path).
4. Exits the current frame; `screen_loop()` continues at the next tick and may recover if the producer error was transient (e.g. a SQLite lock).

**Recovery**: operator runs `solar-harness multi-task status` to obtain the legacy view; the retained debug command is the **fallback of fallbacks**. This is the explicit reason `multi-task status` cannot be retired.

### 3.2 Rollback B — TVS render exception

**Trigger**: the subprocess `bun tvs_render_cli.ts render …` exits non-zero, raises `subprocess.TimeoutExpired`, or returns invalid UTF-8.

**Behavior**:

1. `draw_screen()` (per `02-tvs-rendering.md` §6) appends `{"source": "tvs_render", "reason": "tvs_render_error"}` to `view_model.meta.degraded` **before** delegating to the fallback renderer.
2. Calls `render_screen_status_lines(view_model, width, height)` (see `03-fallback-rendering.md`) with the **same** view_model dict — no re-fetch.
3. **TVS is not retried mid-session** (`02-tvs-rendering.md` §7). Once the session marks TVS degraded, every subsequent frame uses the fallback. This avoids alternating frames and tmux flicker.

**Recovery**: at next `screen_loop()` session start, the `is_tvs_available()` cache is rebuilt, so a TVS that was repaired offline becomes available again on the next invocation.

### 3.3 Rollback C — capture-pane timeout / unreadable terminal

**Trigger**: the producer side `tmux capture-pane` invocation used to detect pane working state exceeds its timeout (default 8s), or the terminal width/height read returns invalid values (`<40` cols or `<10` rows).

**Behavior**:

1. The producer (`screen_view_model()` path) marks the affected panes with `state="missing"` and `marker=" "`; the panes array stays at the contractual length of 8 (see `03-fallback-rendering.md` §8).
2. `meta.degraded` gains `{"source": "capture_pane", "reason": "timeout", "panes": ["main:2", …]}` listing the specific panes that timed out.
3. Renderer treats `state="missing"` like any other state word — no special-casing; the badge appears blank, not red, because the renderer is dumb (per `03-fallback-rendering.md` §6).
4. If width/height are below the renderer's lower bound, `render_screen_status_lines` raises `ValueError`; `draw_screen()` falls back to a one-line `screen unavailable (terminal too small)` banner and continues. No partial frames.

**Recovery**: operator resizes the terminal or fixes the failing pane (e.g. claude killed). Next tick recovers without restart.

### 3.4 Rollback matrix summary

| Path | Trigger                              | `meta.degraded.source` | Renderer used at this frame    | TVS retry policy        |
|------|--------------------------------------|------------------------|---------------------------------|-------------------------|
| A    | view_model production failure        | `screen_view_model`    | one-line banner                | n/a — no view_model     |
| B    | TVS render subprocess exception      | `tvs_render`           | `render_screen_status_lines`   | not retried this session |
| C    | capture-pane timeout / tiny terminal | `capture_pane`         | fallback OR small-screen banner | unaffected               |

---

## 4. Schema Evolution Policy (`schema_version`)

The view_model dict carries a top-level `schema_version` field pinned to `multi_task_screen.view_model.v1` (`01-view-model.md` §2). Evolution is governed by three rules:

1. **Additive change**: a new nested object field MAY be added under any object that declares `additionalProperties: true` (only the top level today) without bumping `schema_version`. Renderers MUST ignore unknown top-level keys gracefully.
2. **Non-additive change**: renaming a field, changing a type, narrowing an enum, or adding a required field inside a nested object (which is `additionalProperties: false`) is a **breaking change**. Such changes REQUIRE bumping the version string to an explicit `multi_task_screen.view_model.vN` where `N` is the next integer.
3. **No silent re-interpretation**: the consumer MUST inspect `schema_version` before reading any field. Mismatch is a hard `ValueError` at the producer/consumer boundary — it does NOT fall through to fallback rendering automatically (compare with Rollback A: that path is for production errors, not version drift).

### 4.1 Carrying both versions

If a future S0X simultaneously needs v1 and v2 consumers, producers MAY emit a dict whose `schema_version` is `multi_task_screen.view_model.v2` but whose nested objects are a strict superset of v1; v1 consumers MUST still refuse such input on the `schema_version` check (no implicit downgrade). The migration is then: ship v2 producer behind a feature flag, update consumers in lock-step, retire v1.

### 4.2 Snapshot fixture invariant

Every breaking version bump REQUIRES updating both `fixtures/view_model.example.json` AND the golden snapshot fixtures (`fixtures/snapshot_80x20.expected.txt`, `fixtures/snapshot_120x24.expected.txt`) in the **same PR**. The fixtures are the operational proof that producer + renderer + version line up; merging without them defeats the schema_version contract.

---

## 5. Migration Sequence — S03 → S04 → S05

The three downstream slices land in a strict order, each gated on the previous slice's evaluator PASS.

### 5.1 S03 — Core Runtime (producer side)

- Implements `screen_view_model(result, args, width) → dict` returning a `view_model.v1`-shaped object (`01-view-model.md` §10).
- Adds `screen_tvs_payload()` and `is_tvs_available()` per `02-tvs-rendering.md` §9.
- Wires `draw_screen()` to call producer once, then dispatch TVS vs fallback per `02-tvs-rendering.md` §7.
- **Does NOT** modify the legacy `multi-task status` handler in any way (§1.1 promise).
- **Does NOT** touch `tvs_render_cli.ts` internals (`02-tvs-rendering.md` §10).

Gate: producer + TVS path + fallback path round-trip a fixture-equivalent view_model end-to-end on a developer machine; legacy `multi-task status` regression test passes byte-identically.

### 5.2 S04 — Orchestration / UX

- Adds the `screen_loop()` refresh cadence, the keyboard hotkey table (if any), and integrates `meta.source_intent` plumbing so an operator can distinguish a `screen` invocation from a `status` invocation in capture logs.
- Wires Rollback A's one-line banner, Rollback B's session-degraded sticky flag, and Rollback C's `state="missing"` plumbing into the producer.
- **Still does NOT** alter `multi-task status` output.

Gate: at least one of each rollback path observed in a controlled fault-injection run (kill TVS binary, kill a target pane, force schema mismatch); `meta.degraded` populated correctly for all three; legacy regression still byte-identical.

### 5.3 S05 — Verification & Release

- Adds golden snapshot tests for 80x20 and 120x24 (the fixtures already exist).
- Adds a contract test that loads `view_model.schema.json` and asserts `screen_view_model()` output validates clean.
- Adds a `multi-task status` regression test that compares stdout against the recorded golden — this is the operational proof of §1.1.
- Publishes the four docs (`01-…` through `04-…`) into the harness wiki as `accepted` artifacts.

Gate: full test suite green, both subcommands manually exercised on a real cockpit, `multi-task status` golden byte-identical to a pre-S03 capture.

### 5.4 Sequence invariants

- **No skipping.** S04 cannot land while S03 is `reviewing`/`failed`; S05 cannot land while S04 is open. The DAG enforces this via the existing `parent-ready-check` (`solar-graph-scheduler` capability).
- **No retroactive vocabulary change.** If S05 surfaces a naming issue, the fix is a v2 schema bump in a follow-up sprint, NOT an in-place rename inside the current sprint window.
- **Rollback to S03 state is always possible** by reverting only the consumer changes (`draw_screen()` branch) while leaving the producer in place; the producer alone is harmless because it is pure (`01-view-model.md` §2 invariant).

---

## 6. Out of Scope (this node)

- **Localization of headings** (deferred to S03+ per `03-fallback-rendering.md` §10).
- **TVS v2 source code changes** (`02-tvs-rendering.md` §10).
- **Retirement plan for `multi-task status`** — explicitly retained; no retirement date is set in this epic.
- **Cross-host federation** of the screen across multiple machines — single-host cockpit only for v1.
