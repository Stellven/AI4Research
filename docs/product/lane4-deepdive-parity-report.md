# Lane 4 — DeepDive vendor parity report

**Date:** 2026-07-07 · **Branch:** `contract/lane4-deepdive` (off `contract/lane3-ledger` @ `e9d5b856`).
Per implementation-plan Lane 4 Step 1 and target-design §1.8: the DeepDive **router/compiler** (which
OpenSolar packaging dropped) is vendored into this repo so **no CI gate depends on the external
mirror** (review 9.1a). The downstream DeepResearch **engine** (`state_machine.py`, `cli.py`,
`evaluator.py`, `survey/`, `eval-artifacts`) was already vendored here; this port restores only the
missing front-end.

## Sources

- **Primary:** maintainer-provided read-only mirror, `main` @ `e2480290` (carries the DeepDive files
  merged). The source mirror was never modified.
- **Cross-check:** this repo's `upstream/codex/evaluator-control-plane` ref (an earlier productization
  variant; commits `96b9e140`/`9de0586f`/`3d14bc4d` per `rsi-deepdive-workflow-lock.md`).

## Per-file provenance

| Vendored path | Source | git blob | vs codex ref | Byte status |
|---|---|---|---|---|
| `harness/lib/research/deepdive_requirement_compiler.py` | mirror @ e2480290 | `d3585ae4` | codex `efcfc6d2` (differs) | **byte-identical to mirror**; adapted-from-codex = NO |
| `harness/lib/research/deepdive_brief_expander.py` | mirror @ e2480290 | `9a376ab9` | codex identical | byte-identical (both) |
| `harness/lib/research/profiles/__init__.py` | mirror @ e2480290 | `62853991` | codex identical | byte-identical (both) |
| `harness/lib/research/profiles/cais_agent_insight.yaml` | mirror @ e2480290 | `e12f34bf` | codex identical | byte-identical (both) |
| `tests/harness/research_survey/test_deepdive_requirement_compiler.py` | **codex ref** (`upstream/codex/evaluator-control-plane`) | `da4adb80` | — | byte-identical to codex; **mirror does not ship this test** |
| `harness/docs/deepdive-requirement-compiler-isolation.md` | mirror @ e2480290 | (identical to codex) | codex identical | byte-identical; vendored for self-documentation |

Every file was written with `git show <ref>:<path>` and hash-compared with `git hash-object`; all
`IDENTICAL` (see `~/opensolar-state/run-archive/lane4-deepdive/`).

## Adaptations

**None.** No import path, `HARNESS_DIR` resolution, or registry-name edit was needed:

- The compiler imports its profile loader as `from .profiles import …` with an `ImportError`
  fallback; the profiles package sits beside it, so the relative import resolves unchanged.
- The vendored test resolves `harness/lib` itself
  (`_HARNESS_LIB = dirname×3(__file__)/lib`, `sys.path.insert`) and imports `from research import …`.
  This repo's `harness/lib/research/` is the same package name, so no rewrite was required. The test
  is self-contained (no repo conftest dependency); it runs green as-is.
- No registry-name substitution: the compiler is DeepDive-internal (its own
  `solar.deepdive.requirement_contract.v1` schema, `deepdive_research` dag_variant, `DeepDive*`
  operators) and does **not** reference this repo's capability-capsule / physical-operator registries.
  The tie to the shipped `research.deepdive.rsi_demo` contract is made in Lane 4's D-graph golden, not
  by editing the compiler.

## Why the mirror compiler (not codex) is canonical

The sole diff between the mirror and codex compilers is two lines the **mirror adds** on the
insight-runtime (`D10–D18`) nodes inside `build_deepdive_evidence_dag(..., insight_mode=True)`:

```
+                "gates": list(meta["gates"]),
+                "verification_gates": list(meta["gates"]),
```

Target-design §1.8 names the mirror as the primary source ("Sihao's own main now carries the DeepDive
files MERGED"); it is the newer, more complete revision. The delta is **inert for the RSI demo**: the
demo compiles with `insight_mode=False` (survey D1–D9), so these keys never appear in the demo graph.
It only enriches the optional insight overlay, which the 5-artifact demo does not use.

## Present upstream, deliberately NOT ported

- **Insight-runtime engine + its tests** — `tests/harness/research_survey/test_deepdive_insight_release_gates.py`,
  `test_insight_data_builders.py`, `tests/harness/graph/test_deepdive_insight_parent_release_guard.py`
  (codex refs). These exercise the D10–D18 insight overlay and its release gates. Per
  `rsi-deepdive-workflow-lock.md` §1 the "D10–D18 insight overlay [is] not needed for the 5-artifact
  demo." The compiler *code* that supports `insight_mode` is present (it lives in the one vendored
  file); only the insight-specific downstream wiring and tests are out of Lane 4 scope. Vendoring them
  would drag in engine surfaces this lane does not touch and would not add demo coverage.
- **`deepdive_brief_expander` is vendored but not wired into any runtime path.** It is inert (imported
  only by the vendored test). The RSI demo instantiates the Lane 1 contract directly; brief expansion
  is a live-run entry-point step, not part of the deterministic demo.

## Inertness proof (vendored code changes no existing behavior)

- `harness/lib/research/__init__.py` is **untouched** (it imports only `hashing, ids, schemas, seams`;
  the vendored modules are siblings it never imports). `import research` remains byte-clean.
- Adjacent regression set — `workflow_contract/ + gate_ledger/ + test_lane2_scenarios.py +
  research_unit/` — is **468 passed** both **before** and **after** the vendor commit (env pinned
  `HARNESS_DIR=$PWD/harness`). Evidence: `baseline-adjacent-suites.txt` /
  `after-vendor-adjacent-suites.txt` in the run-archive.
- The ported compiler test is a **new** file in a separate dir (`research_survey/`); it adds 9 green
  tests without touching any existing collection.
