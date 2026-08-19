# Part B UI proposal — PoC / benchmark / verification evidence

Status: **proposal only, not implemented.** Awaiting approval, and awaiting a
real B1-B7 run so it is built against real artifacts rather than inferred shapes.

## What was investigated

The ask was to lift AutoSci's dashboard graph UI and add a Part B section to it.
Findings from the local checkout of `skyllwt/AutoSci`
(`autosci-spike/upstream-autosci-codex`, MIT licensed):

- `app/modules/graph.js` is a **knowledge graph**, not a workflow graph. It is a
  Cytoscape canvas over `wiki/graph/edges.jsonl` + `citations.jsonl` whose nodes
  are research entities (papers, concepts, methods, people, ideas, experiments)
  and whose edges are citations and relations. It answers "how does the
  literature connect", not "what is Part B doing". Lifting it would produce a
  citation map, not an execution view. **Not recommended for this purpose.**
- `app/modules/dashboard.js` is closer: it renders an idea lifecycle
  (`proposed -> in_progress -> tested -> validated -> failed`) as pure HTML/CSS
  with no chart library. That structure is a reasonable reference for the Part B
  stage roster, and needs no dependency.
- **Blocking technical constraint:** both modules import from CDN
  (`cytoscape` and `marked` from jsdelivr). The container UAT runs with the
  network disabled, so a CDN import would break Part B's UI in exactly the
  environment it has to work in. Any reuse must be a vendored dependency.

## Why this is not a flow diagram

`DESIGN.md` is explicit:

> the orchestration is a capability-routed **DAG, not a line**, so do NOT draw a
> fixed PM -> Planner -> Builder -> Evaluator pipeline with directional
> flow/arrows — that implies a linearity that isn't real.

So no `B1 -> B2 -> ... -> B7` pipeline graphic. The signature element is an
honest **status roster** plus a **static process stream with inline borderless
mono facts**. This proposal follows that.

The existing plan grid already renders B1-B7 as cards with real dependency
labels and status. That stays. This adds the **substance** those cards cannot
carry.

## The backend contract already exists

The compiled task graph already publishes, with no code change required:

```json
"dashboard": { "conditional_part_b": { "status": "conditional",
  "reason": "Part B runs only for execution_profile=part_a_plus_poc and pauses
             at an exact-plan human approval gate.",
  "stages": ["poc_handoff", "idea_evaluation", "experiment_design",
             "experiment_approval", "experiment_run", "claim_verification",
             "final_delivery"] } }
"part_b": { "status": "pending", "reason": "...", "stages": [ ... ] }
```

The React app does not consume either key today. That is the whole gap for the
section frame.

## Proposed section: "Part B · Proof of concept"

Placement: below the existing Plan grid, above the Session timeline. Renders
only when `graph.part_b` is present. Before Part A completes it shows a single
honest line, not an empty scaffold.

### Before (today)

```
Plan   6/15 steps · in progress
 ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
 │ B1 · handoff  │ │ B2 · idea     │ │ B3 · design   │   ← status only,
 │ (conditional) │ │ (conditional) │ │ (conditional) │     no substance
 │ pending       │ │ pending       │ │ pending       │
 └───────────────┘ └───────────────┘ └───────────────┘

Session timeline
```

### After (proposed)

```
Plan   6/15 steps · in progress
 ...unchanged 15-node grid, B1-B7 still shown as cards...

Part B · Proof of concept                    conditional · gated on A8
 Runs only for execution_profile=part_a_plus_poc.

   Handoff        accepted     5 artifacts · 5 evidence records
                               sha256 a2a730b7… · 178,791 bytes
   Idea           selected     evidence-lineage integrity
                               2 candidates considered · 1 rejected
   Plan           frozen       plan sha256 a24e0718…
                               unshare -Urn · network disabled · 8 checks
   Approval       policy       evidence_lineage_integrity_v1 · actor user
                               matched plan sha256 a24e0718…
   Benchmark      exit 0       8/8 integrity checks · rate 1.0
                               42.7s · stdout 2.1 KB · stderr 0 B
   Verification   reconciled   5 claims → 5 verified · 0 unsupported
   Delivery       —            pending

                                              Open final_delivery.md →
```

Left column: stage name. Middle: one-word real state. Right: inline borderless
mono facts pulled from the actual artifact. No arrows, no connectors, no
progress bar.

## Data model (already produced by the capsules)

| Stage | Artifact | Facts to surface |
|---|---|---|
| B1 | `poc_handoff.json` | artifact count, evidence records, manifest sha256, bytes |
| B2 | `idea_evaluation.json` | selected idea, candidates considered, rejections + why |
| B3 | `experiment_plan.json` | plan sha256, command, sandbox, declared checks |
| B4 | `experiment_approval.json` | actor, policy id, matched plan sha256, timestamp |
| B5 | `experiment_result.json`, `benchmark_raw.json`, `stdout.txt` | exit code, checks passed, integrity rate, duration, stream sizes |
| B6 | `claim_verification.json` | claims reconciled, verified, unsupported |
| B7 | `final_delivery.json/.md` | bundle contents, link to open the deliverable |

All are already listed in the Deliverables panel; this gives them meaning
instead of a filename list.

## Honest-state rules this must obey

Directly from `DESIGN.md`, and these are the parts most likely to be got wrong:

- **No progress bar for Part B.** A stalled sprint never shows a filled
  percentage. Part B is conditional; a bar would imply inevitability.
- **A stage with no artifact shows `—` / `pending`.** Never synthesize a result.
- **B4 must not imply a human clicked when policy pre-authorized it.** Our runs
  use `evidence_lineage_integrity_v1`, so the row must read `policy` with the
  policy id and actor, not "approved by user". Conflating the two would
  misrepresent the approval chain — the single most important honesty property
  in Part B.
- **A blocked stage shows amber `#b26a00` + the raw token inline**
  (e.g. `eval_artifact_snapshot_invalid`), not a separate alarming card.
- **Done is quiet ink + a check, never green.** Red stays the brand signal and
  is used for the active stage only.
- Pair every status with text/glyph, never color alone (WCAG 2.2 AA).

## Tokens used (no new ones)

`ink`, `muted`, `subtle`, `faint`, `line_soft`, `surface_quiet`, `blocked`,
`blocked_fill`, `complete`, `primary` (active row only). Type: body
Schibsted Grotesk 400 for labels, Geist Mono 460 `tabular-nums` for all the
facts column. Radius `region: 0` for the section, `small: 6` for any inset.
No new color, font, shadow, gradient, or progress bar.

## Recommended sequencing

Build after a real B1-B7 run exists. Today the furthest any run has reached is
B5, in an earlier session, and the current blocker is A7. Building now means
inferring field names from capsules and schemas and reworking them once real
artifacts land.

The frame (section, roster, conditional rendering off `graph.part_b`) is safe to
build at any time, because that contract is already published and stable. The
per-stage fact rows are what should wait.
