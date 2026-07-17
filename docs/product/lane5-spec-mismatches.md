# Lane 5 spec-vs-code dispositions — wrapper + dashboard contract consumption

**Date:** 2026-07-07 · Branch `contract/lane5-wrapper` (off `contract/lane3-ledger` @
`e9d5b856`). This records places where the Lane 5 wording did not match the Lane 3 tree.

## D1 — wrapper script absent on the Lane 3 base

The plan names `scripts/live_codex_epic_status.py` as an existing file that "gains `--contract`".
On `contract/lane3-ledger`, that path was not present. The latest historical implementation was in
the v8/v9 repair lineage (`1240285a`) and already contained the producer-completion, stability, and
multi-root artifact logic the plan requires retaining.

Disposition: restore that historical wrapper file and add the `--contract` path additively. Existing
v8/v9 replay coverage in the Lane 3 base lives in `harness/tests/workflow_contract/` and
`harness/tests/gate_ledger/test_artifact_manifest.py`, not in wrapper-specific tests.

## D2 — status-server implementation path is `harness/lib/symphony/status-server.py`

The plan says "status-server.py" and points to `harness/status-server/` for patterns. The actual
launched and tested server module is `harness/lib/symphony/status-server.py`; `harness/status-server/`
contains route modules, templates, static assets, and route-specific tests.

Disposition: implement `GET /api/sprints/<sid>/contract` in
`harness/lib/symphony/status-server.py`, adjacent to the existing `/api/sprints/<sid>/projection`
route. No React dashboard files were edited.

## D3 — one `selected_operator_id` writer is in a forbidden file

The relabel requirement is gated by product mode, but one inline task-graph artifact writer remains
in `harness/lib/graph_scheduler.py`. The Lane 5 prompt explicitly forbids editing
`graph_scheduler.py`, so changing that writer in this lane would violate the disjoint-file rule.

Disposition: relabel the non-forbidden physical-plan artifact writer in
`harness/lib/apo_plan_compiler.py` under `SOLAR_PRODUCT_MODE=1`, and make readers tolerate both
`suggested_operator_id` and `selected_operator_id` unconditionally (`route_proof`, status-server
summary, orchestration route projection). The graph-scheduler inline artifact key remains legacy
until a lane that owns `graph_scheduler.py` can change it.

Round 5 amendment: the committed `harness/tools` copies are reachable because installed harnesses
chmod `harness/tools/*.py`, and tools such as `harness/tools/codex_pm_router.py` and
`harness/tools/actor_runtime.py` import `apo_plan_compiler` from the tools script directory. Lane 5
therefore applies the same product-mode relabel to `harness/tools/apo_plan_compiler.py` and the same
reader tolerance to `harness/tools/symphony/status-server.py`; `test_plan_artifact_relabel.py` now
loads those exact files by path.

## D4 — planner-generated contracts have no fixed stages to render

`pm.generic.v1` is a valid shipped contract but declares `stages_mode: planner_generated` and an empty
`stages` list. A literal per-contract stage list would be empty even when a sprint graph has nodes.

Disposition: for contracted sprints with fixed stages, the endpoint renders contract stages. For
planner-generated or uncontracted graphs, it falls back to graph node ids/statuses while still
returning a graceful legacy shape.
