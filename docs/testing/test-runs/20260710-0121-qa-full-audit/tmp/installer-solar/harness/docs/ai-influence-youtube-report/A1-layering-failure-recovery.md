# A1 — Layering, State Machine, Observability & Failure Recovery

sprint: `sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收-s02-architecture`
node: `A1`
write_scope: `docs/ai-influence-youtube-report/A1-layering-failure-recovery.md`
generated_at: 2026-05-29
status: `reviewing`
package_boundary: `spec_only` — no code, no live `plan-ai-influence-reports` runs, no Browser Agent ChatGPT calls
governance: NG1 (no transcript-gate bypass) · NG3 (no local-model substitution for L5 judgment-bearing phases) · spec-only DoD

Knowledge Context: `solar-harness context inject used` (Mirage degraded with `mirage_path:no_results`; QMD solar-wiki + Solar DB + Obsidian Vault hit)
Harness Modules Used: `harness-knowledge`, `harness-graph`
Solar Capabilities (injected, planned): Solar-Harness Runtime · solar-graph-scheduler · solar-knowledge-ingest · Superpowers (workflow.planning) · ATLAS (failure.structured_repair, referenced by §6 failure matrix only)

---

## 0. Scope & relation to upstream artifacts

A1 is the first node of the S02 architecture slice. It locks the **runtime shape** that S03/S04/S05 must implement:

- **Layered architecture L1-L7** with one responsibility per layer.
- **Control plane vs data plane** split, naming every state store and every failure surface.
- **8-state RunRecord state machine**, with the three explicit terminal rejection states.
- **Observability spec** for the four mandatory structured event streams (`runs.jsonl`, `model_call_ledger.jsonl`, `validator_report.json`, `archive_manifest.json`).
- **9-row failure-recovery matrix** covering every named class of upstream and downstream failure for this pipeline.
- **Degraded modes** that hold the NG-policy line: no ThunderOMLX/Qwen substitution at L5, no transcript-gate bypass.

A1 does **not** finalize:
- CLI / Python module signatures (owned by **A2** → `A2-interfaces.md`).
- Canonical JSON schemas for cross-component artifacts (owned by **A3** → `A3-data-model.md`).
- Legacy CLI flag inventory, compat adapters, migration plan (owned by **A4** → `A4-compat-migration.md`).
- Sprint-level closeout, design.md cross-references, eval.{md,json} (owned by **A5**).

A1 references the canonical S01 spec documents for invariants it does not own:

| Reference | Source | Used in A1 §… |
|-----------|--------|----------------|
| T0-T3 transcript grading thresholds | `docs/ai-influence-youtube-report/N1-transcript-gate-classification.md` §1.1 | §1.L2, §3, §6 row 1+2 |
| 7 `group_type` values + multi-signal classifier | N1 §2.1-§2.4 | §1.L3, §6 row 3 |
| Browser Agent ChatGPT 5.5 Thinking high 3-phase rule | `docs/ai-influence-youtube-report/N2-high-model-chatgpt-plan-writing.md` §1, §5 | §1.L5, §4.2, §6 row 4-5, §7 NG3 |
| Per-chapter call invariant (one call per chapter, no batching) | N2 §2.2 | §1.L5, §3 (state `chaptered`) |
| `model_call_ledger` schema | N2 §4 | §4.2 |
| 8 validator checks | `docs/ai-influence-youtube-report/N3-output-validator-archive-fixture.md` §3.1 + §3.4 | §1.L6, §4.3, §6 row 6 |
| 4-artifact archive (md + html + plan.json + evidence_map.json) | N3 §4.1, §4.2 | §1.L7, §4.4, §6 row 7 |
| ChatGPT 杂项 session metadata | N3 §4.3 | §1.L5, §4.4 |
| S01 outcome traceability O1-O10 | S01 traceability.json | §0, §8 |
| Cross-epic surface (YouTube Transcript epic / HF Paper Insight epic) | sprint design.md §7 | §6 row 8 |

---

## 1. Layered architecture L1-L7

Each layer has one responsibility, one input contract, one output contract, and one failure surface that is observable in the control plane (§2). Layers are stacked bottom-up; data flows upward; cancellation flows downward.

### 1.L1 — Video Inventory & Metadata (read-only consumer)

| Field | Value |
|-------|-------|
| Responsibility | Provide the seed inventory of YouTube videos for the requested window. |
| Inputs | `--week <YYYY-WW>` or `--date-range <start> <end>` from the operator; the existing `tech-hotspot-radar` ingest as the upstream source of truth. |
| Outputs (data plane) | `raw_video_list[]` — a list of `{video_handle, metadata, transcript_artifact_path, transcript_status}` rows. `video_handle` carries reader-facing fields only (channel / title / published_at); `video_id` is retained internally for joins but never leaks to L7 (see NG4). |
| Side effects | **None.** L1 MUST NOT mutate inventory, transcript-status, or any upstream artifact. |
| Failure surface | Inventory unavailable (network / disk / schema mismatch) → emits `step=L1.fetch_inventory outcome=fail reason=<…>` to `runs.jsonl`; control plane raises `run_rejected_upstream_unreachable` (see §3). |
| Owner & boundary | Wraps the existing tech-hotspot-radar inventory reader; no logic re-implementation. Cross-epic surface is owned by A4. |

### 1.L2 — Transcript Quality Gate (T0-T3 grading)

| Field | Value |
|-------|-------|
| Responsibility | Apply the T0/T1/T2/T3 4-level grading verbatim per N1 §1.1 and partition the inventory. |
| Inputs | `raw_video_list[]` from L1; `transcript-status --json` rows from the YouTube Transcript epic (`entity_recall`, `WER`, `segment_density`). |
| Outputs (data plane) | `gate_decision[]` keyed by `video_handle`, each carrying `{grade ∈ T0..T3, entity_recall, wer, segment_density, evidence_notes}`. A `t3_exclusions` block per N1 §1.4 is emitted in parallel. |
| Side effects | None. Pure function over the inputs. |
| Failure surface | Missing transcript-status row → emits `step=L2.gate outcome=skip reason=transcript_missing video_handle=<…>`; gate metric schema drift → emits `step=L2.gate outcome=fail reason=upstream_schema_drift`; partition where all surviving rows are T3 → control plane raises `run_rejected_t3_only`. |
| NG enforcement | **NG1** — gate invocation order is mandatory; the only allowed `bypass_reason` is `none`. Any non-`none` bypass is a contract violation and fails at boundary §7.1. |

### 1.L3 — Video Group Classification (7 `group_type`)

| Field | Value |
|-------|-------|
| Responsibility | Classify each T0/T1/T2 video into exactly one of `{event, conference, keynote, interview, tutorial, product_update, other}` using the 6-signal multi-signal classifier from N1 §2.2. Single-signal classification is forbidden. |
| Inputs | The T0/T1/T2 subset of `gate_decision[]`; per-video metadata (title, channel, duration, speaker count, Q&A presence, slide density). |
| Outputs (data plane) | `classification_decision[]` carrying `{group_type, confidence, signal_breakdown{S1..S6}, fallback_used}` per N1 §2.4. |
| Side effects | None. Deterministic; no LLM involved at this layer. |
| Failure surface | Max confidence < 0.50 for any video → `fallback_used=true`, `group_type=other`, no run abort (see §6 row 3); per-signal extraction failure (e.g., S6 slide_density unavailable) → signal raw_score=0.0, not error. |
| NG enforcement | Single-signal classification forbidden — enforced as an invariant on the classifier output (`signal_breakdown` MUST list all 6 signals). |

### 1.L4 — Report Hierarchy Builder (deterministic; no LLM)

| Field | Value |
|-------|-------|
| Responsibility | Build the deterministic `trend → chapter → subsection` skeleton from the L3 grouped corpus, with `evidence_refs` pinned to transcript segment identifiers (not raw `video_id`). |
| Inputs | `classification_decision[]` from L3; Phase 1 plan structure preview (post-L5 Phase 1 — see §1.L5). |
| Outputs (data plane) | `report_hierarchy` carrying the trend/chapter/subsection nodes plus evidence_ref pointers. |
| Side effects | None. |
| Failure surface | Orphan subsection (no parent chapter) → emits `step=L4.hierarchy outcome=fail reason=orphan_node`; this is also caught by L6 Check 8 as defense-in-depth. |
| NG enforcement | Reader-facing `evidence_refs` MUST resolve to `video_handle` (channel/title/published_at), never to bare `video_id` (NG4). |

### 1.L5 — Browser Agent ChatGPT 5.5 Thinking high (judgment-bearing)

| Field | Value |
|-------|-------|
| Responsibility | The three judgment-bearing phases per N2 §1: Phase 1 plan (one call), Phase 2 per-chapter writing (**one call per chapter, no batching**, per N2 §2.2), Phase 3 final synthesis (one call). |
| Inputs | The grouped corpus from L4 + L3; allowed_evidence packets; the style contract (no internal terms, no video_id, must show source_mapping). |
| Outputs (data plane) | `phase1_plan`, `phase2_chapter[]` (one per chapter), `phase3_synthesis`. Each output references the `model_call_id` row written to `model_call_ledger.jsonl` (§4.2). |
| Side effects | Writes one row per call to `model_call_ledger.jsonl`; archives the ChatGPT conversation to project `杂项` per N3 §4.3; produces `chatgpt-session.json` sidecar. |
| Failure surface | ChatGPT unreachable (timeout > 90 s) → §6 row 4; malformed JSON output → §6 row 5; archive failure to `杂项` → non-fatal (`archive_status=failed` recorded, report proceeds). |
| NG enforcement | **NG3** — ThunderOMLX / Qwen / any other local model MUST NOT be substituted for Phase 1/2/3. If Browser Agent is unavailable, the run aborts with `run_rejected_model_unreachable`; degraded modes never replace the high model here (see §7). |

### 1.L6 — Output Validator (8 checks; any-FAIL ⇒ archive rejected)

| Field | Value |
|-------|-------|
| Responsibility | Run the 8 deterministic validator checks per N3 §3.1 against the rendered `report.md`, `report.html`, `plan.json`, and `evidence_map.json`. Any single check FAIL rejects the archive (N3 §3.2). |
| Inputs | The four rendered artifacts; the grep blacklist file `lib/ai-influence-report/forbidden-tokens.txt` (N3 §3.4); the L3 `signal_breakdown` for Check 7 audit. |
| Outputs (data plane) | `validator_report.json` carrying the 8 per-check results plus `overall ∈ {PASS, FAIL}` (§4.3). |
| Side effects | Reads only. Validator MUST NOT touch ChatGPT URL reachability (no network call) — flagged by N3 §6.3 / §8.3. |
| Failure surface | Any check FAIL → exit code 1 → control plane raises `run_rejected_validator`; operator error (bad args / missing file / malformed JSON) → exit code 2, run blocked at boundary. |
| NG enforcement | **NG2** (no ASCII chart in final), **NG4** (no internal fields), **NG5** (no truncation tail) all enforced here. Validator MAY NOT be bypassed (NG1 sibling): `--allow-bypass` is owned by L7 archive writer and emits FATAL; production disables it. |

### 1.L7 — Reporting Surface & Archive

| Field | Value |
|-------|-------|
| Responsibility | Persist the 4 reader-facing / machine-readable artifacts in the date-bucketed archive directory and emit the archive manifest. |
| Inputs | L6 `validator_report.json` with `overall=PASS`; the 4 artifacts (`report.md`, `report.html`, `plan.json`, `evidence_map.json`) from L4/L5; optional `chatgpt-session.json` sidecar from L5. |
| Outputs (data plane) | Directory `~/Knowledge/_raw/tech-hotspot-radar/ai-influence-planned/<YYYY-MM-DD>/reports/<report_slug>/` populated atomically with the 4 mandatory files; `archive_manifest.json` (§4.4). |
| Side effects | Filesystem writes (one directory per report). Archive write is atomic per run: either all 4 mandatory artifacts or none. |
| Failure surface | ENOSPC / EPERM / directory collision → §6 row 7; partial-archive recovery is forbidden (no half-written report). |
| NG enforcement | Refuses to commit if `validator_report.overall != PASS`. The `--allow-bypass` killswitch (A4 owns the flag definition) is FATAL-logged and disabled in production. |

### 1.X — Cross-cutting invariants

| Invariant | Rationale | Enforcement point |
|-----------|-----------|-------------------|
| All cross-layer artifacts are JSON-serializable; no raw transcript blobs in function args | A2 stable invariants (sprint design.md §2.3) | A2 surface; A3 schemas |
| Every output carries `schema_version` | Forward compat | A3 schemas |
| Inventory and transcript-status are read-only across L1-L7 | Avoid upstream drift via write-back | A2 invariants |
| `video_id` may appear in spec discussion (this doc) but never in L7 reader-facing artifacts | NG4 | L6 Check 1+2 |
| `video_handle = {channel, title, published_at}` is the canonical reader-facing identifier | N1 §1.4; N3 §1.1 | L4 hierarchy + L5 prompts + L6 evidence_map check |

---

## 2. Control plane vs data plane

### 2.1 Plane split

| Plane | Function | Components | State store (durable) | Failure surface |
|-------|----------|-----------|-----------------------|-----------------|
| **Control** | Decide what to do next; drive the state machine; gate L6 → L7 transition. | CLI entry (`plan-ai-influence-reports run/validate/replay`), `RunRecord` state machine (§3), scheduler hooks (idle/retry/abort). | Per-run JSON `runs/<run_id>/report_state.json` (current state + phase_artifacts manifest) + append-only event log `runs.jsonl`. | Any state transition that fails its precondition aborts the run; idempotent restart from the last `passed` phase via `replay --run-id`. |
| **Data** | Carry the artifacts produced by each layer; serve them to downstream layers and to L7 archive. | L1-L5 outputs as JSON; L6 validator inputs; final L7 artifacts as md / html / json. | Per-run filesystem under `runs/<run_id>/` for forensics + final archive under `~/Knowledge/_raw/tech-hotspot-radar/ai-influence-planned/<YYYY-MM-DD>/reports/<report_slug>/`. | Bad data fails L6 validator; any-FAIL ⇒ archive rejected; the `runs/<run_id>/` directory is retained for forensic audit. |

### 2.2 State stores

| Store | Plane | Path | Mutability | Owner |
|-------|-------|------|------------|-------|
| `runs.jsonl` | Control | `runs/<run_id>/runs.jsonl` (per-run) OR central `runs/index.jsonl` (one-line summary per run; A4 to decide) | append-only | Control plane scheduler |
| `report_state.json` | Control | `runs/<run_id>/report_state.json` | overwrite-on-transition (atomic rename) | Control plane state machine |
| `model_call_ledger.jsonl` | Observability (control / cross-cutting) | `runs/<run_id>/model_call_ledger.jsonl` (and rolled up into a central ledger for cost accounting by A4) | append-only | L5 BrowserAgentClient |
| `validator_report.json` | Data → Control gate | `runs/<run_id>/validator_report.json` | written once at L6 finalize | L6 validator |
| `archive_manifest.json` | Data → Audit | `<archive_dir>/archive_manifest.json` | written once at L7 commit | L7 archive writer |
| Per-run artifact tree (`raw_video_list.json`, `gate_decision.json`, `classification_decision.json`, `phase1_plan.json`, `phase2_chapter/<chapter_id>.json`, `phase3_synthesis.json`, `report.md`, `report.html`, `plan.json`, `evidence_map.json`) | Data | `runs/<run_id>/…` | written once per phase | Per-layer outputs |
| Archive tree (4 mandatory artifacts) | Data | `<archive_dir>/{report.md, report.html, plan.json, evidence_map.json}` + optional `chatgpt-session.json` | written atomically at L7 | L7 archive writer |

### 2.3 Failure surfaces by plane

| Layer | Control-plane signal on failure | Data-plane consequence |
|-------|--------------------------------|------------------------|
| L1 fetch_inventory | `state_transition: created → run_rejected_upstream_unreachable` | No data emitted; run forensics directory empty save for the L1 fail event. |
| L2 transcript_gate | `state_transition: graded → run_rejected_t3_only` when partition is empty of T0/T1/T2 | `t3_exclusions` block emitted before abort; downstream layers not invoked. |
| L3 classifier | No abort signal; `confidence<threshold` flows into `fallback_used=true` | `classification_decision[]` has at least one row with `group_type=other`. |
| L4 hierarchy | `state_transition: planned → run_rejected_hierarchy` (catchable by replay) | Partial hierarchy retained for forensics. |
| L5 Browser Agent unreachable | `state_transition: <current> → run_rejected_model_unreachable` after one retry | Phase outputs absent or partial for the failing phase; ledger row carries `archive_status=failed` and `outcome=unreachable`. |
| L5 malformed JSON | One JSON-schema-validation retry with strict-JSON nudge; on second failure same as above | Raw model output retained for replay; parsed JSON absent. |
| L6 validator any-FAIL | `state_transition: validated → run_rejected_validator` | `validator_report.json` retained showing failing check IDs + evidence; archive write not attempted. |
| L7 archive ENOSPC / EPERM | `state_transition: validated → run_rejected_archive_io` (catchable by replay) | Partial archive forbidden — any write that started gets rolled back via temp-dir + atomic rename pattern. |

---

## 3. RunRecord state machine (8 states + 3 explicit rejection terminals)

A single run is identified by `run_id` (UUID v4 minted at L1 by the control plane). The state machine is append-only at the event level (`runs.jsonl`) and overwrite-on-transition at the snapshot level (`report_state.json`, atomic rename).

### 3.1 The 8 success-path states

| # | State | Entry condition | Exit condition | Layer association |
|---|-------|-----------------|----------------|-------------------|
| 1 | `created` | `run` command invoked; `run_id` minted; window argument parsed | L1 fetch_inventory returns non-empty | L1 |
| 2 | `graded` | All L2 gate decisions emitted | At least one video in T0 ∪ T1 ∪ T2 (else → `run_rejected_t3_only`) | L2 |
| 3 | `grouped` | All L3 classification decisions emitted | All non-T3 videos carry a `group_type` (incl. `other`) | L3 |
| 4 | `planned` | L5 Phase 1 plan output returned and JSON-validated | Plan carries ≥ 1 trend with ≥ 1 chapter | L4 + L5 Phase 1 |
| 5 | `chaptered` | L5 Phase 2 has been invoked **once per chapter** (no batching), all per-chapter outputs returned and JSON-validated | All planned chapters have a chapter output | L5 Phase 2 |
| 6 | `synthesized` | L5 Phase 3 final synthesis returned and JSON-validated | Final markdown + HTML + inline SVG + source map appendix present | L5 Phase 3 |
| 7 | `validated` | L6 validator has run all 8 checks | `validator_report.overall = PASS` (else → `run_rejected_validator`) | L6 |
| 8 | `archived` | L7 commit succeeded; `archive_manifest.json` written | Terminal success | L7 |

### 3.2 The 3 explicit rejection terminals (PRD-required)

| Terminal | Entry condition | Recovery option |
|----------|-----------------|-----------------|
| `run_rejected_t3_only` | After `graded`: T0 ∪ T1 ∪ T2 partition is empty (count = N inventory, T3 = N). | None within this run — re-issue after upstream transcript quality improves. Forensics retained. |
| `run_rejected_validator` | After `validated`: any of the 8 checks reports FAIL. | `validate-report --report <path>` may be re-run after a fix that mutates the artifact bundle outside the standard pipeline (e.g., editorial pass); otherwise the run is dead. Forensics retained. |
| `run_rejected_model_unreachable` | After any L5 phase: ChatGPT 5.5 Thinking high is unreachable after one retry, OR returns malformed JSON twice. | `replay --run-id <id>` after Browser Agent is restored; the run resumes from the last `passed` phase. No local-model substitution (NG3). |

### 3.3 Additional non-PRD rejection terminals (for completeness; A1 owns)

These are not in the PRD's three named terminals but the failure-recovery matrix (§6) needs distinct labels:

| Terminal | Entry condition | Recovery option |
|----------|-----------------|-----------------|
| `run_rejected_upstream_unreachable` | L1 cannot fetch inventory (network / disk / schema mismatch). | Re-issue after upstream restored. |
| `run_rejected_hierarchy` | L4 produced an orphan or skipped-level hierarchy (defense-in-depth before L6). | Investigate L3 grouping output; usually indicates an L3 bug; not retryable inline. |
| `run_rejected_archive_io` | L7 ENOSPC / EPERM / collision after retries. | Free space or resolve collision, then `replay --run-id`. |
| `run_rejected_upstream_drift` | A4 compat adapter detects cross-epic schema drift at L2 or L3. | Update adapter and rerun; do not silently misread. |

`run_rejected_*` states are **terminal** (no exit transitions from this state in the same `run_id`). `replay --run-id` mints a new run that may re-enter from the last passed phase.

### 3.4 ASCII transition diagram

```
created
  │   L1.fetch_inventory.ok
  ▼
  ┌──── L1.fetch_inventory.fail ────→ run_rejected_upstream_unreachable
graded                                              (terminal)
  │   L2.gate.partition_non_empty
  ▼
  ┌──── L2.gate.t3_only ─────────────→ run_rejected_t3_only
grouped                                             (terminal)
  │   L3.classify.all_decisions_emitted
  ▼
planned
  │   L4.hierarchy.ok  &&  L5.phase1.ok
  ▼
  ├──── L4.hierarchy.orphan ─────────→ run_rejected_hierarchy
  └──── L5.phase1.unreachable/malformed (after retry) ─→ run_rejected_model_unreachable
chaptered
  │   L5.phase2(one call per chapter).all_ok
  ▼
  └──── L5.phase2.unreachable/malformed (after retry) ─→ run_rejected_model_unreachable
synthesized
  │   L5.phase3.ok
  ▼
  └──── L5.phase3.unreachable/malformed (after retry) ─→ run_rejected_model_unreachable
validated
  │   L6.validator.overall=PASS
  ▼
  └──── L6.validator.any_fail ───────→ run_rejected_validator
archived (terminal success)
  │
  └──── L7.archive.io_fail ──────────→ run_rejected_archive_io
                                        (replayable after free / resolve)
```

### 3.5 Transition rules (control-plane invariants)

| Rule | Description |
|------|-------------|
| `R1` | Every transition appends one `state_transition` event to `runs.jsonl` with `{run_id, from, to, t, reason, evidence_paths}`. |
| `R2` | `report_state.json` is overwritten by atomic rename (write-to-temp + `os.rename`); no half-written state on disk. |
| `R3` | A run in any `run_rejected_*` state is terminal for its `run_id`. `replay --run-id` mints a new `run_id` linked by `replayed_from`. |
| `R4` | Re-entry from a prior state is allowed only if all upstream artifacts on disk match the hash recorded in `report_state.phase_artifacts`. Mismatch → `replay` aborts with operator error (exit 2). |
| `R5` | Concurrent runs of the same `--week` are allowed (different `run_id`s); they MUST write under different `runs/<run_id>/` and different `<archive_dir>/<report_slug>` (slug collision is rejected by L7 per N3 §8.6). |
| `R6` | `state_transition` events are the **only** signal the scheduler uses to advance the run; data-plane artifact presence alone is not sufficient (avoids races). |

---

## 4. Observability spec — four structured streams

A1 locks the **field set** for the four mandatory streams. Canonical JSON schemas (`*.v1`) are owned by **A3**; per-stream consumer (CLI / dashboard / cost rollup) is owned by **A2** / **A4**. **No `print()` for runtime telemetry; structured JSON only.**

### 4.1 `runs.jsonl` — append-only event log (control plane)

Stored per-run at `runs/<run_id>/runs.jsonl`; optionally rolled up to `runs/index.jsonl` for the dashboard (A4 to decide).

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `event_id` | string (UUID v4) | yes | Unique per event |
| `run_id` | string (UUID v4) | yes | The run this event belongs to |
| `t` | ISO-8601 UTC timestamp | yes | Wall-clock when the event was emitted |
| `event_type` | enum {`state_transition`, `step_started`, `step_ended`, `warning`, `fatal`} | yes | Coarse event taxonomy |
| `step` | string | conditional | Required when `event_type ∈ {step_started, step_ended}`; format `L<n>.<verb>` e.g. `L2.gate`, `L5.phase2`. |
| `from` / `to` | string | conditional | Required when `event_type = state_transition`; reference §3 states. |
| `outcome` | enum {`ok`, `fail`, `skip`, `retry`} | conditional | Required for `step_ended`. |
| `reason` | string | conditional | Required when `outcome ∈ {fail, skip, retry}`; free-form short text. |
| `evidence_paths` | string[] | optional | Filesystem paths to the artifacts produced/consumed by this step (under `runs/<run_id>/…`). |
| `model_call_id` | string | optional | Cross-reference into `model_call_ledger.jsonl` (set for L5 steps). |
| `latency_ms` | int | optional | Wall-clock duration for `step_ended`. |
| `schema_version` | string (literal `runs.event.v1`) | yes | Forward-compat pin. |

Required events per run:
- One `state_transition` per state change (§3.1, §3.2, §3.3).
- One pair `step_started` / `step_ended` per L1-L7 step, including the per-chapter Phase 2 invocations (one pair per chapter).
- One `fatal` event for any non-`run_rejected_*` crash (e.g., uncaught exception in the control plane).

### 4.2 `model_call_ledger.jsonl` — append-only L5 call ledger

Stored per-run at `runs/<run_id>/model_call_ledger.jsonl`; central rollup at `~/.solar/ledgers/ai_influence_youtube.ledger.jsonl` for cost accounting (A4 to confirm path).

Fields (canonical per N2 §4; A1 pins the minimum set):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `call_id` | string (UUID v4) | yes | Unique per call; referenced by `runs.jsonl.model_call_id`. |
| `module` | string (literal `ai_influence_youtube`) | yes | Multi-module ledger needs disambiguation. |
| `stage` | enum {`phase1_plan`, `phase2_chapter_write`, `phase3_synthesis`} | yes | Maps 1:1 to L5 phases. |
| `model` | string (literal `chatgpt-5.5-thinking-high`) | yes | NG3 enforcement: any other value is a contract violation. |
| `provider` | string (literal `browser_agent_chatgpt`) | yes | NG3 sibling. |
| `sprint_id` | string | yes | The originating sprint (this sprint = `sprint-20260528-…-s02-architecture`). |
| `report_id` | string | yes | Plan-level identifier. |
| `chapter_id` | string \| null | conditional | Required when `stage = phase2_chapter_write`; null otherwise. |
| `browser_session_id` | string | yes | Stable handle from the Browser Agent wrapper. |
| `chatgpt_project` | string (literal `杂项`) | yes | Archive target (N3 §4.3). |
| `conversation_url` | string \| null | yes | Reachable URL; null only when Browser Agent failed before allocating a conversation. |
| `input_tokens_estimate` | int | optional | Best-effort. |
| `output_tokens_estimate` | int | optional | Best-effort. |
| `estimated_cost_usd` | float | optional | Best-effort. |
| `call_count` | int | yes | Always 1 per ledger row; rollup is a sum. |
| `prompt_version` | string | yes | One of `aiyt-plan-v1`, `aiyt-chapter-v1`, `aiyt-synthesis-v1`. |
| `schema_version` | string (literal `model_call_ledger.v1`) | yes | A3 owns the canonical schema. |
| `archive_status` | enum {`pending`, `archived`, `failed`} | yes | Reflects the 杂项 archival outcome. |
| `latency_ms` | int | yes | Wall-clock for the round-trip. |
| `outcome` | enum {`ok`, `unreachable`, `malformed_json`, `retry_then_ok`} | yes | Drives §6 row 4-5 recovery decisions. |
| `created_at` | ISO-8601 UTC | yes | Wall-clock when the row was appended. |

Invariants:
- Phase 2 emits one row per chapter (no batching, per N2 §2.2).
- A row MUST be appended **before** the L5 call result is consumed by L6; this is the audit anchor.
- `outcome = unreachable` after one retry triggers `run_rejected_model_unreachable` (no NG3 fallback).

### 4.3 `validator_report.json` — single-shot L6 output

One file per run at `runs/<run_id>/validator_report.json`. Also surfaced via `validate-report` stdout per N3 §3.3.

Fields:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `run_id` | string | yes | |
| `report_dir` | string (filesystem path) | yes | Where the 4 artifacts live during validation. |
| `validator_version` | string | yes | e.g. `v1.0.0`; bump on blacklist additions per N3 §3.4. |
| `checks` | array of `{id ∈ 1..8, name, status ∈ {PASS, FAIL}, evidence, diff?}` | yes | Exactly 8 entries. `name` is human-readable per N3 §3.1. `diff` is required when `status = FAIL`. |
| `overall` | enum {`PASS`, `FAIL`} | yes | `PASS` iff every check.status = `PASS`. |
| `failed_check_ids` | int[] | yes | Empty when `overall = PASS`. |
| `t` | ISO-8601 UTC | yes | When the validator finished. |
| `schema_version` | string (literal `validator_report.v1`) | yes | A3 owns the canonical schema. |

L6 stdout / stderr mapping per N3 §3.3:
- Exit 0 → stdout: `{"ok": true, "checks": {1..8: "pass"}}`.
- Exit 1 → stderr: `{"ok": false, "failed_checks": [{id, reason, evidence}, …]}`.
- Exit 2 → operator error; stderr human-readable; stdout empty.

### 4.4 `archive_manifest.json` — L7 commit receipt

One file per report at `<archive_dir>/archive_manifest.json`.

Fields:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `archive_dir` | string (absolute path) | yes | The `~/Knowledge/_raw/tech-hotspot-radar/ai-influence-planned/<YYYY-MM-DD>/reports/<report_slug>/` directory. |
| `run_id` | string | yes | The producing run. |
| `report_slug` | string | yes | e.g. `2026-W21-gpt5-multimodal-launches`. |
| `artifacts` | array of `{path, sha256, type ∈ {md, html, plan_json, evidence_map_json}}` | yes | Exactly the 4 mandatory artifact types per N3 §4.2. |
| `chatgpt_session_url` | string \| null | yes | From the `chatgpt-session.json` sidecar (N3 §4.3); null if absent. |
| `validator_report_path` | string | yes | The producing `validator_report.json` (typically under `runs/<run_id>/`). |
| `created_at` | ISO-8601 UTC | yes | Commit timestamp. |
| `schema_version` | string (literal `archive_manifest.v1`) | yes | A3 owns the canonical schema. |

Invariants:
- `archive_manifest.json` is written **after** the 4 mandatory artifacts land via atomic rename. If any artifact write fails, none of the 4 land and `archive_manifest.json` is not emitted.
- Optional sidecar files (e.g. `chatgpt-session.json`) MAY also be listed in `artifacts[]`, but their absence does not fail Check 5 (per N3 §4.3).

### 4.5 Stream summary

| Stream | Append-only? | Per-run vs central | Required for sprint gate |
|--------|--------------|--------------------|--------------------------|
| `runs.jsonl` | yes | per-run (+ optional central index) | yes |
| `model_call_ledger.jsonl` | yes | per-run (+ central rollup for cost) | yes |
| `validator_report.json` | no (single-shot write) | per-run | yes |
| `archive_manifest.json` | no (single-shot write) | per-report (under archive dir) | yes (required for success path; absent on `run_rejected_*`) |

---

## 5. Cross-layer invariants & boundary checks

A1 owns the invariants that every layer downstream from §1 must respect; A2/A3 codify them in interfaces and schemas.

| ID | Invariant | Where enforced | Failure consequence |
|----|-----------|----------------|---------------------|
| I-1 | `video_id` never leaves L1-L4 internal storage into L5 prompts or L7 reader-facing artifacts | L5 prompt builder (NG4) + L6 Check 1/2 | Validator FAIL → `run_rejected_validator` |
| I-2 | Phase 2 emits exactly one L5 call per chapter | L5 dispatcher (N2 §2.2) | Mis-count → contract violation; L5 dispatcher aborts run before phase output is consumed |
| I-3 | `model_call_ledger.jsonl` row is appended **before** the L5 result is returned to the caller | L5 BrowserAgentClient (N2 §4) | Missing row → audit FAIL during sprint closeout; treated as a data-plane bug |
| I-4 | `validator_report.overall = PASS` is the **only** signal L7 consumes for the archive gate | L7 archive writer (N3 §3.2) | Bypass attempt → FATAL log + production disable |
| I-5 | Inventory and transcript-status are read-only across all layers | L1 + L2 (NG-sibling) | Any write detected → control plane aborts run; treated as a code-level contract violation |
| I-6 | T3 videos NEVER appear in evidence_refs of any chapter body | L4 builder + L6 Check 6 | Validator FAIL Check 6 → `run_rejected_validator` |
| I-7 | All cross-layer artifacts carry `schema_version`; downstream rejects on unknown major version | A3 schemas; A2 stable invariants | Mis-version → contract violation, run aborts at the consumer boundary |
| I-8 | The archive directory is the only write target outside `runs/<run_id>/`; nothing else on the filesystem is mutated | L7 archive writer | Write outside scope → contract violation; pre-flight check |
| I-9 | Atomic archive: either all 4 mandatory artifacts land or none | L7 archive writer | Partial archive → rollback to staging dir; emit `run_rejected_archive_io` |
| I-10 | NG3 — no local model (ThunderOMLX / Qwen / others) is substitutable for L5 Phase 1/2/3 judgment | L5 prompt routing table (N2 §5) + §7 degraded modes | Substitution detected → contract violation; not a recoverable failure |

---

## 6. 9-row failure-recovery matrix

The nine rows mandated by the dispatch acceptance bullet. Each row identifies the failure, its detection signal (control- or data-plane), the recovery, and the NG-aligned degraded mode.

| # | Failure | Detection signal | Recovery | Degraded mode (NG-compliant) | Terminal / Replayable |
|---|---------|-------------------|----------|-------------------------------|-----------------------|
| 1 | **Transcript missing** for a video in inventory (no row in `transcript-status --json`) | L2 gate input check; `step=L2.gate outcome=skip reason=transcript_missing` per affected video | Mark the video as missing in `gate_decision[]`; exclude from this run; do not retry inline | If surviving (T0/T1/T2) count ≥ 3 → run proceeds with surviving videos; if `< 3` → abort with `under_quorum` (mapped to `run_rejected_t3_only` per dispatch terminal naming) | Run completes if quorum holds; else terminal |
| 2 | **T3-only run** (after gate, T0∪T1∪T2 = ∅) | L2 partition emits zero core/weak rows | Abort run; emit `run_rejected_t3_only` | None — no useful corpus exists; **NG1** forbids gate bypass to admit T3 anyway | **Terminal** `run_rejected_t3_only`; forensics retained |
| 3 | **L3 classifier low confidence** (max group_type confidence < 0.50 for one or more videos) | L3 emits `signal_breakdown` with `fallback_used=true`, `group_type=other` | Fallback to `other` per N1 §2.3 cascade | Report still generated; the `other` bucket may be large; surfaced as **OQ-A1-01** for tuning sprint after S05 fixture | Non-terminal; run continues |
| 4 | **Browser Agent ChatGPT 5.5 unreachable** at any L5 phase (Phase 1/2/3) — timeout > 90 s | L5 BrowserAgentClient round-trip timer; `model_call_ledger.outcome=unreachable` | Retry once with the same prompt and a fresh browser session; on second failure abort with `run_rejected_model_unreachable` | **No NG3-allowed degraded mode for judgment-bearing phases.** Local-model substitution is FORBIDDEN. The pipeline pauses (`status=blocked_high_model_unavailable` per N2 §5) and the run terminates; `replay --run-id` resumes from the last passed phase once the agent is restored. | **Terminal** `run_rejected_model_unreachable`; replayable via `replay` after restoration |
| 5 | **L5 returns malformed JSON** (fails the strict schema check for the active phase) | L5 JSON-schema validator against `phase1_plan.v1` / `phase2_chapter.v1` / `phase3_synthesis.v1` | Retry once with a strict-JSON nudge appended to the prompt; on second failure abort with `run_rejected_model_unreachable` (same terminal as row 4 — both are "the model failed to deliver usable judgment") | Same NG3-aligned restriction as row 4: **no local-model substitution**. The raw model output is retained in `runs/<run_id>/` for forensic replay or operator-driven editorial fix-up. | **Terminal** `run_rejected_model_unreachable`; replayable after editorial fix or after agent improvement |
| 6 | **L6 validator any-FAIL** (one or more of the 8 checks fails) | `validator_report.overall=FAIL` and `failed_check_ids` non-empty | Block archive (N3 §3.2); operator inspects `failed_check_ids` and the per-check `diff`; fix the offending artifact and rerun `validate-report` alone (no need to redo L1-L5) | **No bypass mode.** `--allow-bypass` exists at L7 only for emergency operator override; FATAL-logged and disabled in production per L7 contract | **Terminal** `run_rejected_validator` for the run; `validate-report` may be re-run alone after a manual fix |
| 7 | **Archive disk write fails** (ENOSPC / EPERM / slug collision) | L7 archive writer's pre-flight + per-file try/except; `step=L7.archive outcome=fail reason=enospc|eperm|slug_collision` | Roll back any partial writes via the staging-dir + atomic rename pattern (so the archive directory is left in either fully-committed or empty state — I-9); emit `run_rejected_archive_io` | **No partial archive.** Either all 4 mandatory artifacts land or none. After ENOSPC resolved or slug suffixed, `replay --run-id` re-emits the archive without redoing L5 | **Terminal** `run_rejected_archive_io`; replayable after operator resolves disk / collision |
| 8 | **Cross-epic upstream drift** (YouTube Transcript epic field rename, or HF Paper Insight epic Browser Agent symbol shift) | A4 `compat_adapter_v1` runtime check at L2 boundary (transcript-status fields) or L5 boundary (Browser Agent symbol import); `step=L2.gate outcome=fail reason=upstream_schema_drift` | Halt the run before data is misread; emit `run_rejected_upstream_drift`; surface to coordinator for cross-epic planner sync (per sprint design §4.2 / §4.3) | **No silent retrofit.** Adapter MUST be updated by a planner pass; A4 owns the adapter spec. Until the adapter ships, the run cannot proceed. | **Terminal** `run_rejected_upstream_drift`; replayable after adapter ships |
| 9 | **Mirage VFS degraded** (during sprint-time KB context inject; observed this pass per the dispatch runtime context) | `solar-harness context inject` returns `[degraded] mirage_path:no_results` or equivalent in the dispatch runtime context | Continue the active sprint task using the remaining KB sources (QMD solar-wiki + Solar DB + Obsidian Vault); document the degradation in the handoff `Capability / KB Usage Evidence` section | Not S02-fixable in this sprint; carries through as **OQ-S02-07** (also see sprint design §9 / OQ table). Runtime pipeline (L1-L7) is **not** affected because runs.jsonl / ledger / validator do not depend on Mirage. | Non-terminal at run scope; non-fixable at sprint scope |

---

## 7. Degraded modes — NG3 + NG1 compliance

### 7.1 NG1 — no transcript-gate bypass

| Aspect | Decision |
|--------|----------|
| Default | Gate is mandatory on every run; `evidence_policy.no_transcript_gate_bypass = true`. |
| Operator override | **None.** No `--skip-gate`, no env var, no config flag may admit T3 to core evidence. |
| Test bypass | Test fixtures use synthetic T0/T1/T2 inputs; they do not bypass L2 — they exercise it. |
| Detection | L6 Check 6 (T3 not in core evidence) provides defense-in-depth at the validator boundary. |
| Failure mode | Bypass attempt → contract violation; the L2 dispatcher aborts the run before L3 is invoked; no `state_transition` to `grouped` is emitted. |

### 7.2 NG3 — no local-model substitution for L5 judgment-bearing phases

| Aspect | Decision |
|--------|----------|
| Allowed at L5 Phase 1/2/3 | Browser Agent ChatGPT 5.5 Thinking high (N2 §1, §5). |
| Forbidden at L5 Phase 1/2/3 | ThunderOMLX / Qwen / any local model / any other Browser-Agent-routed model. |
| Allowed elsewhere | ThunderOMLX / Qwen are permitted for: transcript cleanup, evidence atom extraction, entity normalization, grouping **hints** (final grouping decision lives at L3 with multi-signal classifier or at L5 Phase 1 — local model hints are advisory only), low-risk validation. Per N2 §5 table. |
| Degraded mode if Browser Agent unavailable | Per §6 rows 4 and 5: run aborts with `run_rejected_model_unreachable`; pipeline pauses (`status=blocked_high_model_unavailable` per N2 §5); operator restores Browser Agent and issues `replay --run-id`. **No local-model fallback at any L5 phase.** |
| Operator override | **None.** No `--use-local-model` or similar may route L5 Phase 1/2/3 to anything other than ChatGPT 5.5 Thinking high. |
| Detection (audit) | `model_call_ledger.jsonl` row carries `model=chatgpt-5.5-thinking-high` and `provider=browser_agent_chatgpt` as literals; any other value is a contract violation flagged at sprint closeout. |

### 7.3 Other NG policies (recap; not directly required by this acceptance row but referenced for completeness)

| Policy | Enforcement layer |
|--------|-------------------|
| NG2 — no ASCII chart in final output | L6 Check 4 (`<svg>` present + raster `<img>` forbidden) per N3 §2.1, §2.2 |
| NG4 — no internal fields in reader-facing surfaces | L6 Check 1 (grep blacklist) + Check 2 (bare 11-char video_id regex in prose) per N3 §3.1, §3.4 + I-1 |
| NG5 — no truncation tail | L6 Check 3 per N3 §3.1 |

### 7.4 Operator override surface (summary)

| Flag | Owner | Default | Production | Purpose | NG-aligned? |
|------|-------|---------|------------|---------|-------------|
| `--gate-on` | A4 (CLI flag spec) | on | locked on | Activate the L2 gate | NG1-aligned |
| `--allow-bypass` | A4 (CLI flag spec) | off | **disabled** (FATAL on use) | Emergency bypass at L7 archive gate only | NG-aligned via FATAL-log + production disable |
| `--use-local-model` (hypothetical) | **not defined** | n/a | n/a | Would violate NG3; A4 MUST NOT introduce this flag | NG3 violation if introduced |
| `--dry-run` | A2 (CLI subcommand) | off | allowed | Run through `synthesized` without committing to archive | Compatible with all NG |
| `--week` / `--date-range` | A2 (CLI subcommand) | required | allowed | Inventory window selector | Compatible with all NG |

---

## 8. Acceptance traceability (this node A1)

S02 dispatch acceptance for A1 (six bullets, verbatim from the dispatch file):

| Acceptance ID | Bullet (verbatim) | Section(s) of this doc | Status |
|---------------|-------------------|-------------------------|--------|
| A-A1-1 | Layered view L1-L7 with explicit responsibility per layer | §1.L1, §1.L2, §1.L3, §1.L4, §1.L5, §1.L6, §1.L7, §1.X | covered |
| A-A1-2 | Control plane vs data plane split with state stores and failure surfaces | §2.1 (split), §2.2 (state stores), §2.3 (failure surfaces) | covered |
| A-A1-3 | 8-state RunRecord state machine plus `run_rejected_t3_only` / `run_rejected_validator` / `run_rejected_model_unreachable` terminal states | §3.1 (8 states), §3.2 (3 PRD-named terminals), §3.3 (additional terminals), §3.4 (ASCII diagram), §3.5 (transition rules) | covered |
| A-A1-4 | Observability spec covering `runs.jsonl` + `model_call_ledger.jsonl` + `validator_report.json` + `archive_manifest.json` with required fields | §4.1, §4.2, §4.3, §4.4, §4.5 | covered |
| A-A1-5 | 9-row failure-recovery matrix (transcript missing / T3-only / classifier low confidence / ChatGPT unreachable / malformed JSON / validator FAIL / archive ENOSPC / cross-epic drift / mirage degraded) | §6 (exactly 9 rows in order) | covered |
| A-A1-6 | Degraded modes that are NG3-compliant (no local-model substitution for L5 judgment-bearing phases) and NG1-compliant (no transcript gate bypass) | §7.1 (NG1), §7.2 (NG3), §7.4 (operator override surface) | covered |

Upstream S01 outcome traceability (cross-reference to PRD outcomes O1-O10 via S01 traceability.json):

| S01 outcome | Touched by A1 |
|-------------|---------------|
| O1 (T0-T3 gate) | §1.L2, §3 (`graded` state + `run_rejected_t3_only`), §6 rows 1+2 |
| O2 (7 group_type) | §1.L3, §3 (`grouped` state), §6 row 3 |
| O3 (3-phase ChatGPT invocation) | §1.L5, §3 (`planned`/`chaptered`/`synthesized`), §4.2 ledger, §7.2 |
| O4 (structured JSON hierarchy) | §1.L4, §1.L5, §3 (`planned`/`chaptered`) |
| O5 (reader-facing source mapping) | §1.X invariants, §5 I-1 |
| O6 (SVG embedding) | §1.L6 (Check 4 reference), §7.3 NG2 recap |
| O7 (8 validator checks) | §1.L6, §4.3, §6 row 6 |
| O8 (archive layout) | §1.L7, §4.4, §6 row 7 |
| O9 (2026-W21 fixture) | Not directly owned by A1 (S05 owns); A1 ensures the pipeline can produce the artifacts the fixture exercises |
| O10 (traceability + handoff) | Out of scope for A1; sprint-level handoff is A5 |

---

## 9. Risks and OQ (A1-local)

| OQ id | Risk | Mitigation | Owner |
|-------|------|------------|-------|
| OQ-A1-01 | Classifier confidence threshold (0.50 / 0.65 / 0.70) is design-time; large `other` bucket inflation under real corpus | Tune after S05 2026-W21 fixture replay; calibration data lives in `runs/<run_id>/classification_decision.json` | Post-S05 calibration sprint |
| OQ-A1-02 | `model_call_ledger.jsonl` central rollup path is unspecified | A4 to confirm whether rollup lives under `~/.solar/ledgers/` or under a per-epic ledger | A4 |
| OQ-A1-03 | Replay semantics for `run_rejected_validator` are ambiguous when the fix is an editorial change to `report.md` (not a re-emission from L5) | A4 to spec the `validate-report --report-dir` re-run path (already in sprint design §2.1) and the relationship to `replay --run-id` | A4 |
| OQ-A1-04 | `runs.jsonl` central index path is unspecified | A4 to decide central vs per-run only | A4 |
| OQ-A1-05 | The two `run_rejected_*` terminals introduced by A1 (`run_rejected_upstream_unreachable`, `run_rejected_hierarchy`, `run_rejected_archive_io`, `run_rejected_upstream_drift`) are not in the PRD-named three; needs A5 sprint-level sign-off | A5 to accept them in the sprint-level acceptance review | A5 |
| OQ-A1-06 | 11-char `video_id` regex (L6 Check 2) needs a markdown-AST-aware predicate to avoid false positives in code fences | A2 to spec the predicate interface; A3 to formalize the AST schema if needed | A2 (lead) + A3 |
| OQ-A1-07 | Mirage VFS degraded during this dispatch's KB context inject (carried from S01 OQ-S02-07) | Not A1-fixable; other 3 KB sources covered the necessary inputs for this pass | Cross-pane infra |

---

## 10. Scope compliance

- Write scope: `docs/ai-influence-youtube-report/A1-layering-failure-recovery.md` — exclusive single-file write. ✓
- Read scope respected: only the files listed in the dispatch's Read Scope (PRD, contract, sprint design, sprint plan, S01 N4 handoff, S01 traceability.json, N1, N2, N3, epic.md, epic.traceability.json) were consulted plus STATE.md for the pre-write Read hook. ✓
- Package boundary: `spec_only`. No code written; no `.py`/`.ts`/`.sh` files created or modified; no live calls; no fixture generation. ✓
- Architecture guard: no core_hits; package_boundary respected; guard warnings/errors `none`. ✓
- NG1 / NG2 / NG3 / NG4 / NG5 enforced in spec language. ✓
- Parent epic NOT closed; only this node is marked `reviewing` by the handoff step. ✓

---

## 11. Self-check (pre-handoff)

| Self-check | Result |
|------------|--------|
| §1 enumerates exactly 7 layers L1-L7, each with Responsibility / Inputs / Outputs / Side effects / Failure surface / NG enforcement | ✓ |
| §2 names every state store and every failure surface, split by plane | ✓ |
| §3 enumerates the 8 success states AND names the 3 PRD-required `run_rejected_*` terminals (`t3_only`, `validator`, `model_unreachable`) | ✓ |
| §4 enumerates exactly the 4 mandatory streams with required fields, schema_version, append-only semantics | ✓ |
| §6 has exactly 9 rows in the order specified by the dispatch acceptance bullet | ✓ |
| §7 explicitly maps NG3 → "no local-model substitution at L5 judgment-bearing phases" and NG1 → "no transcript-gate bypass" | ✓ |
| No code / no fixture / no live call / no parent-epic close | ✓ |
| No `done` / `complete` / `implemented` language about un-built downstream work | ✓ |
| Schema names (`runs.event.v1`, `model_call_ledger.v1`, `validator_report.v1`, `archive_manifest.v1`) are referenced as forward pointers to A3, not redefined here | ✓ |
| All forward references to A2 / A3 / A4 / A5 are explicit and bounded | ✓ |
