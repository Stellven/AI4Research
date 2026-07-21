# A2 — Interfaces (AI Influence YouTube 报告流)

Sprint: `sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收-s02-architecture`
Node: `A2`
Scope: `spec-only`
Generated: `2026-05-29`

## 0. Purpose

A2 locks the interface contracts that S03/S04/S05 must implement for the AI Influence YouTube report flow. This document does not permit code changes, live Browser Agent calls, fixture runs, or archive writes. It defines:

1. CLI surfaces and exit codes
2. Python module entry points
3. Stable invariants across layers
4. Per-call `model_call_ledger` contract
5. Validator input/output contract covering the 8 required checks
6. Error and downgrade surfaces that remain NG1/NG3 compliant

## 1. CLI surface

### 1.1 Command family

The existing top-level command family is retained under `tech_hotspot_radar.py` and remains reader-visible through:

- `plan-ai-influence-reports`
- `run-ai-influence-planned-reports`
- `validate-ai-influence-planned-reports`

S03 may factor shared logic into a dedicated package, but must not change the user-facing command names without an A4 migration decision.

### 1.2 `plan-ai-influence-reports`

Purpose: build the weekly plan from transcript-backed catalog rows after transcript gating and semantic grouping.

Canonical signature:

```text
plan-ai-influence-reports
  --date YYYY-MM-DD
  --days INT
  --limit INT
  --output-base PATH
  --model MODEL
```

Contract:

- Input source is the completed-video catalog plus transcript-backed grouping materials.
- L2 transcript gate runs before a video can enter the planning corpus.
- Phase 1 planning output must be structured JSON:
  `trend -> chapter -> subsection -> evidence_refs`.
- The command writes:
  - `video-catalog.json`
  - `video-grouping-materials.json`
  - `grouping-prompt.md`
  - `video-groups.json`
  - `planner-prompt.md`
  - `report-plan.json` or `report-plan.blocked.json`

Exit codes:

- `0` = plan written and structurally valid
- `1` = blocked or failed planning
- `2` = operator/runtime error before plan verdict
- `3` = upstream drift detected and plan aborted
- `4` = under-quorum / T3-only / no transcript-backed material

### 1.3 `run-ai-influence-planned-reports`

Purpose: execute per-report writing against a validated plan file and produce final reader-facing artifacts.

Canonical signature:

```text
run-ai-influence-planned-reports
  --date YYYY-MM-DD
  --days INT
  --plan-file PATH
  --report-id STRING
  --output-base PATH
  --model MODEL
  --send
  --skip-notebooklm
  --notebook-name STRING
  --continue-on-error
```

Contract:

- Input is `report-plan.json` from the planning step.
- Writing phase is judgment-bearing and must use Browser Agent ChatGPT 5.5 Thinking high.
- One ChatGPT call per chapter is mandatory.
- Final report bundle must include:
  - `report.md`
  - `report.html`
  - `report-result.json`
  - `validation-result.json`
  - `evidence_map.json`
  - `chatgpt-session.json` or equivalent archive metadata

Exit codes:

- `0` = all requested reports archived after validator PASS
- `1` = one or more reports blocked or validator FAIL
- `2` = operator/runtime error before report verdict
- `3` = upstream drift or contract break discovered during execution
- `4` = no eligible evidence or all candidate reports rejected by gate/quorum rules

### 1.4 `validate-ai-influence-planned-reports`

Purpose: re-run the hardened validator on one report or an entire report directory.

Canonical signature:

```text
validate-ai-influence-planned-reports
  --date YYYY-MM-DD
  --report-id STRING
  --output-base PATH
  --require-project-archive
```

Contract:

- Reads an existing report directory only.
- Must emit a single `validation-result.json` per report directory.
- `--require-project-archive` upgrades missing ChatGPT project archival from warning to FAIL.

Exit codes:

- `0` = every selected report passes all 8 checks
- `1` = one or more reports fail validation
- `2` = validator runtime/operator error
- `3` = expected archive metadata or upstream contract is unreadable
- `4` = requested report selection resolves to zero eligible report directories

## 2. Python module entry points

The package name is implementation-owned by S03, but the callable surfaces are locked here.

### 2.1 Gate and classification

```python
def transcript_gate(video_id: str, transcript_status_row: dict) -> "GateDecision": ...
def group_classifier(video_metadata: dict, gate_decision: "GateDecision") -> "ClassificationDecision": ...
```

Rules:

- `transcript_gate` is pure over the upstream row and returns no filesystem side effect.
- `group_classifier` may only execute after a non-T3 gate decision exists.
- T2 may remain in the plan only as weak evidence and must be labeled downstream.
- `group_classifier` must emit `signal_breakdown` keyed by `S1..S6`.

### 2.2 Browser Agent wrapper

```python
class BrowserAgentClient:
    def plan(self, corpus: dict, *, requested_model: str, run_id: str) -> "Phase1Plan": ...
    def write_chapter(self, chapter_spec: dict, *, requested_model: str, run_id: str, chapter_id: str) -> "Phase2Chapter": ...
    def synthesize(self, chapter_outputs: list[dict], *, requested_model: str, run_id: str) -> "Phase3Synthesis": ...
```

Rules:

- `plan()` is exactly one call per report plan.
- `write_chapter()` is exactly one call per chapter; batching multiple chapters in one model call is forbidden.
- `synthesize()` is exactly one call after all chapter outputs are available.
- All three methods must write the `model_call_ledger` row before returning success to the caller.
- No local ThunderOMLX/Qwen substitution is allowed for these three methods.

### 2.3 Validator and archive

```python
def build_hierarchy(group_plan: dict) -> dict: ...
def validator_run(report_bundle: dict) -> "ValidatorReport": ...
def archive_writer_commit(run_record: dict, report_bundle: dict, validator_report: dict) -> "ArchiveManifest": ...
```

Rules:

- `build_hierarchy()` is deterministic and contains no judgment-bearing model call.
- `validator_run()` must evaluate the fixed 8 checks from N3.
- `archive_writer_commit()` must refuse to publish any artifact when `validator_report.overall == "FAIL"`.
- Archive is atomic: either the 4 required artifact types exist together, or no archive is published.

### 2.4 Reader-facing render helpers

```python
def render_source_mapping_markdown(entry: dict) -> str: ...
def render_source_mapping_html(entry: dict) -> str: ...
def render_report_html(markdown: str, evidence_pack: dict, report_meta: dict) -> str: ...
```

Rules:

- Reader-facing render helpers may not expose `video_id`, `V00x`, `raw_refs`, `pipeline_fields`, `transcript_status`, or processing logs.
- `render_report_html()` must embed at least one inline `<svg>` and may not degrade to ASCII chart output in final HTML.

## 3. Stable invariants

1. Every structured output is JSON-serializable.
2. Every structured output carries `schema_version`.
3. No function mutates inventory rows or `transcript-status` source rows.
4. No final judgment surface may substitute a local model for Browser Agent ChatGPT 5.5 Thinking high.
5. Every judgment-bearing Browser Agent return has a persisted ledger row first.
6. Every evidence reference used in plan/writing/synthesis must be resolvable to transcript segment or metadata evidence.
7. Any T3 exclusion must be preserved into validator input.

## 4. `model_call_ledger` contract

Every Browser Agent invocation writes one row with the following required fields:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `call_id` | string | yes | Unique row id |
| `stage` | enum | yes | `phase1`, `phase2`, `phase3` |
| `run_id` | string | yes | Owning report run |
| `report_id` | string | conditional | Required for chapter/synthesis stage |
| `chapter_id` | string | conditional | Required for `phase2` |
| `sprint_id` | string | yes | Must equal this epic's active sprint lineage |
| `browser_session_id` | string | yes | Stable Browser Agent session |
| `chatgpt_url` | string | yes | Conversation URL for archive |
| `requested_model` | string | yes | Usually `chatgpt-5.5` |
| `resolved_model` | string | yes | Actual model returned by Browser Agent |
| `latency_ms` | integer | yes | End-to-end request latency |
| `cost_estimate_usd` | number | yes | Cost estimate persisted per call |
| `input_token_count` | integer | optional | Provider dependent |
| `output_token_count` | integer | optional | Provider dependent |
| `status` | enum | yes | `ok`, `blocked`, `failed` |
| `error_message` | string | optional | Present on blocked/failed |
| `created_at` | string | yes | ISO8601 UTC |

Rules:

- A row is appended before the calling interface returns.
- Failed calls still append a row with `status != ok`.
- `chatgpt_url` must be the same URL later archived into the project metadata.

## 5. Validator interface mapping

`validator_run()` must expose the full 8-check matrix with deterministic output shape:

```json
{
  "schema_version": "validator_report.v1",
  "run_id": "run_...",
  "overall": "PASS|FAIL",
  "checks": [
    {"id": 1, "name": "internal_terms_blacklist", "status": "PASS|FAIL", "evidence": {}, "diff": null},
    {"id": 2, "name": "bare_video_id", "status": "PASS|FAIL", "evidence": {}, "diff": null},
    {"id": 3, "name": "truncation_tail", "status": "PASS|FAIL", "evidence": {}, "diff": null},
    {"id": 4, "name": "svg_present", "status": "PASS|FAIL", "evidence": {}, "diff": null},
    {"id": 5, "name": "evidence_map_complete", "status": "PASS|FAIL", "evidence": {}, "diff": null},
    {"id": 6, "name": "t3_not_in_core", "status": "PASS|FAIL", "evidence": {}, "diff": null},
    {"id": 7, "name": "group_type_legal", "status": "PASS|FAIL", "evidence": {}, "diff": null},
    {"id": 8, "name": "hierarchy_intact", "status": "PASS|FAIL", "evidence": {}, "diff": null}
  ]
}
```

Deterministic rules:

- `checks` must always contain 8 items in fixed order.
- Missing evidence for a check is a FAIL, not a skip.
- Any single FAIL upgrades `overall` to `FAIL`.

## 6. Error and downgrade surface

| Trigger | Allowed outcome | Forbidden shortcut |
|---------|-----------------|-------------------|
| No transcript-backed material | exit `4`, blocked plan artifact | planning from metadata-only corpus |
| All candidates T3 | exit `4`, `run_rejected_t3_only` | bypassing gate |
| Browser Agent unavailable | exit `1` or `3`, blocked artifact + ledger row | local-model substitution |
| Malformed phase JSON | validator-style reject, rerun allowed | silently coercing broken JSON |
| Validator FAIL | exit `1`, archive denied | publishing partial archive |

## 7. Not in A2

- No implementation of the interfaces
- No schema body finalization beyond contract surface
- No fixture execution
- No Browser Agent live call
- No parent epic close
