# Lane 1 — spec/code mismatches and clarifications

**Date:** 2026-07-06 · **Branch:** `contract/lane1-compiler` (off `contract/lane0-spine`).
Per the lane ground rules, nothing here was silently absorbed into the implementation; every item
is either encoded in the shipped contracts/compiler with a documented reason, or a bound flagged for
its owning lane. Part 1 is the capsule/task_type remap that the round-1 reviewer asked to surface
(F10). Part 2 records the round-2 fix-round decisions (F1/F2/F3/F6/F12) where the code deviates from
the literal disposition wording or carries a conservative bound.

---

## Part 1 — RSI DeepDive capsule / task_type remap (F10)

`workflow-contract-schema.example.json` was written against an *idealized* capsule vocabulary. The
shipped registry (`harness/config/capability-capsules/*.yaml`) admits task types via each capsule's
`contract.preconditions.task_type_in` (the same field the runtime admission gate enforces — no
aliasing at the compile gate, R2a). Three example stages named capsule/task_type pairs the real
registry rejects. `research.deepdive.rsi_demo.workflow.json` corrects them to the mapping that went
green live in v8/v9 (`fe2a7d69`, corpus F-049). This was previously buried in the contract's `note`
field; it is surfaced here.

**Shipped capsule admission (authoritative, from the real registry):**

| Capsule | `task_type_in` admits | code capsule? |
|---|---|---|
| `cap.requirement-research-scout` | `knowledge-extraction` **only** | no |
| `cap.requirement-research-synthesizer` | `evidence`, `research` | no |
| `cap.requirement-compiler-audit` | `audit_inventory`, `documentation`, `evidence`, `reporting` | no |
| `cap.requirement-compiler-implementation` | `debugging`, `implementation`, `refactor` | **yes** (declares `patch_diff`) |

**Remap (example → shipped):**

| Stage | Example pairing | Shipped pairing | Reason |
|---|---|---|---|
| **D1** (scope) | `task_type=audit_inventory`, capsules `[scout, audit]` | capsules `[audit]` — **scout dropped** | scout admits only `knowledge-extraction`; keeping it would fail R2a (`TASK_TYPE_NOT_ADMITTED`). |
| **D2** (sources) | `task_type=audit_inventory`, capsule `[scout]` | `task_type=knowledge-extraction`, capsule `[scout]` | the scout's *only* admitted type is `knowledge-extraction`; the example's `audit_inventory` is unadmitted. |
| **D5** (report) | `task_type=reporting`, capsules `[synthesizer, audit]` | capsules `[audit]` — **synthesizer dropped** | synthesizer admits `evidence`/`research`, not `reporting`; audit admits `reporting`. |

The regression suite pins this remap: `test_every_stage_task_type_admitted_by_every_allowed_capsule`
and `test_shipped_contracts_compile_clean_against_real_registries` fail the moment a stage names a
pair the real registry rejects. `test_task_type_not_admitted_rejects` proves the D2 scope
(`audit_inventory` on the scout ⇒ reject with the admitted set in the message).

**Consequence for the demo:** every RSI artifact-authoring node routes to `cap.requirement-compiler-audit`
(`handoff_md` + external verifier + acceptance criteria + the deterministic validator), *never* to
the implementation capsule — so no node runs under a `patch_diff` obligation it cannot satisfy
(the v7 defect). Part 2 §F2 is the compile-side enforcement of that invariant on the planner path.

---

## Part 2 — round-2 fix-round decisions (F1/F2/F3/F6/F12)

Each fix was implemented red-first against the reviewer's ▶EXECUTED probes. The items below are the
places a reader should know the code's exact behavior, not just the disposition headline.

### F1 — empty stage∩policy intersection ⇒ `ROUTE_UNRESOLVABLE`

`resolve_role_operators` now tracks whether a provider constraint was *declared* (`constrained`),
separate from whether the resulting allowed-set is empty. An empty effective set that arose from a
real stage∩policy intersection (e.g. stage `[openai]` under policy `[anthropic]`) resolves to **zero**
operators. Only the genuinely-unconstrained case (no stage providers **and** no policy) skips the
provider filter. This is the shared resolver used by both `compile_checks` and `plan_validator`, so
F13 (Lane 0.5 preflight passing the run policy) becomes meaningful the moment it lands.

### F2 — the bound capsule is the node-kind authority (deviation + bound documented)

The disposition states "patch_diff obligations legal only when capsule kind = code AND write_scope
has a code target." Taken literally with the *old* write_scope rule ("any code suffix ⇒ code"), the
v7 fixture keeps the implementation (code) capsule, so a decoy `helper.py` satisfies "has a code
target" and would still compile. The literal conjunction alone does **not** reject v7+decoy while
keeping a real code node (implementation capsule + `tool.py`) legal — both use the same code capsule.

**Implemented rule (`classify_node_kind`, three layers):**

1. **Decoy-resistant shape.** A structured-data / rendered-report deliverable in `write_scope`
   (`.json/.jsonl/.html/.csv/.yaml/.xml/...`) marks the node as **artifact-authoring even when a code
   file is also present** — a report/inventory node that drops a `helper.py` is still artifact work.
   `.md` is deliberately **excluded** from that set (it is a code node's README/handoff companion and
   must not, on its own, demote a code node — this is why the real code node keeps its patch proofs).
2. **Declared node_kind may only narrow.** A planner-declared `node_kind:"code"` never escalates a
   shape that classifies below code; it can only make a node *less* code-like.
3. **Capsule ceiling.** `capsule_produces_patch()` reads each capsule's *own* contract (declared
   `patch_diff` output / produced `artifact.patch_diff` / `patch_within_scope` self-check) at registry
   load and stores `produces_patch`. A non-code capsule can never yield a code node, regardless of
   shape or declared node_kind — this closes the audit/research-capsule + decoy-`.py` variant that
   the shape rule alone (no `.json` present) would miss.

`compile_checks` (fixed, author-reviewed contracts) is intentionally **not** changed: it validates the
contract-author's declared stage `node_kind` directly. F2's exploit is the *planner*-controlled path,
which is `plan_validator` + `classify_node_kind`.

**Known conservative bound (fail-closed, not fail-open):** a genuine code node whose `write_scope`
also lists a structured-data file (e.g. `tool.py` + a `config.json`) classifies as **artifact**, so a
legitimate `patch_diff` obligation on it would be rejected and bounce the planner. This is acceptable
in the bounded scope (it matches diagnosis answer #8's "data/report artifacts only vs code target"
framing generalized to *dominance*), and it errs toward rejection, never toward re-admitting the v7
defect. If the generic path later needs code nodes that emit structured-data deliverables, tighten
the shape rule to a code-vs-data *count* comparison rather than presence.

### F3 — acyclicity + depends_on-existence on the planner path

The schema path already enforced these for fixed contracts; the planner path did not. Extracted the
shared cycle finder (`first_cycle_node`), reused by `_check_acyclic`, and added
`_validate_graph_structure` to `validate_plan`: `DEP_NOT_FOUND` (a `depends_on` entry naming no node)
and `GRAPH_CYCLIC` (the graph is not a DAG). Until this landed, R2's anti-hang claim was explicitly
**not** in force on the generic path (R7's bounded-wait backstop is Lane 3).

### F6 — env_gates constrain a match, never constitute one (deviation documented)

The disposition wants env gates as "additional conjuncts." The shipped RSI contract carries an
`env_gate` (`SOLAR_DEMO_REPORT_MODE=1`) **and** the existing suite (`test_rsi_prompt_matches_the_demo_contract`,
demo unset) requires its markers to fire **ungated**. A literal "env_gates are a required conjunct on
the marker path" would suppress the RSI markers whenever demo mode is off — breaking that test. So:

- The standalone env-gate match path is **removed**: a trigger now fires only on an explicit marker or
  the requirement-compiler type. Demo mode can no longer route arbitrary text (the reviewer probe: a
  pure code request under `SOLAR_DEMO_REPORT_MODE=1` used to hijack to the research pipeline).
- env gates remain available as a **suppressing** conjunct via an opt-in flag `trigger.env_gates_required`
  (`_env_gates_suppress`). **No shipped contract sets it**, so the RSI env_gate is now inert for
  routing — its markers carry the demo driver, exactly as the disposition anticipated ("without
  breaking the demo driver, whose prompts contain the markers anyway"). The env_gate is left in the
  contract (no scrub needed, per the disposition) as documentation of the demo-mode intent and a hook
  for any future contract that genuinely wants gated markers.

### F12 — a malformed contract must not break routing for all

`load_all_contracts(skip_invalid=True)` logs and skips an unparseable `*.workflow.json` instead of
aborting the whole load; the router's `match`/`list` and `find_contract` (sibling resolution) use it.
Strict compile/instantiate of a *named* contract still surfaces `ContractSchemaError`. One behavior
change worth noting: a registry whose **only** file is malformed is now a clean **no-match (exit 1,
stub falls back to the generic path)** rather than a load error (exit 2). Both are non-zero, so the
intake stub's "any non-zero ⇒ legacy path" contract is preserved; the round-1 fail-safe test is
rewritten accordingly.

---

## Integration notes for downstream lanes

- **Lane 0.5 (F13):** `compile_checks(..., provider_policy=run_policy)` is where the run policy must be
  threaded; F1 makes the empty-intersection case reject, so preflight and the compiler will now agree
  on the same stage instead of the compiler silently resolving-all.
- **Lane 0.5 (M2 in that lane's doc):** the real compile entrypoint is
  `workflow_contract.compile_checks(contract, capsule_registry, operator_registry, provider_policy=None)`
  returning a list of `{code, stage_id, message, ...}` (empty ⇒ compiles). The plan-graph analogue is
  `plan_validator.validate_plan(task_graph, capsule_registry, operator_registry, provider_policy, contract)`.
- **Round-3 review:** re-run the F1/F2/F3 probes verbatim — empty-intersection RSI-under-anthropic,
  v7+decoy-`helper.py`, v7+`node_kind:"code"`, cyclic and dangling-dep graphs — they must all reject.
