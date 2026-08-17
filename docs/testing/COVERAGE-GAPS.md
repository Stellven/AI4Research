# Known coverage gaps

Places where CI does **not** check something it looks like it checks. Each entry
stays here until it is closed or explicitly retired, because the failure mode
these all share is that they are invisible: a suite that never asserts something
looks exactly like a suite where that something always holds.

Referenced by ID from the code that carries the gap.

| ID | Gap | Status |
| --- | --- | --- |
| GAP-000 | Where the duplicate harness/tests/ tree came from | explained, decision pending |
| GAP-001 | Dispatch ledger and queue plumbing, 17 assertions | open |
| GAP-002 | Broker integration contracts assert absent symbols | open, needs a product decision |
| GAP-003 | 324 baselined failures are unclassified | open |
| GAP-004 | Four test files excluded from public CI | open by design, re-check on change |
| GAP-005 | No flake quarantine, so a flaky test blocks | open |
| GAP-006 | Secret scan excused on pull requests | **closed** 2026-08-14 |
| GAP-007 | Almost no test is calibrated | open, structural |
| GAP-008 | Scheduler asserts on an operator log it did not wait for | latent race, **does not block CI** |
| GAP-012 | The baseline was recorded under local concurrency CI does not have | **closed** by run 88 |
| GAP-009 | test_autosci_skill_shim.py depends on state other test files create | open, test isolation |
| GAP-010 | 45 test files outside tests/ are run by nothing | open |
| GAP-011 | The suite runs on Linux only | open, scoped decision |
| GAP-013 | 34 test files inside tests/ are run by nothing | **open**, now visible |

---

## GAP-013 — 34 test files inside `tests/` that nothing executes

The census originally inspected only `test_*.py`, `*_test.py` and `*.sh`. It
reported **887 files, 0 unclassified**, and that number was worse than no number:
it reads as a guarantee about the whole directory and was one only for Python and
shell.

Extending it to TypeScript, Node and PowerShell raised the count to 916 and
surfaced 34 files with no runner at all:

| what | count | why nothing runs it |
| --- | ---: | --- |
| `tests/core/*.test.ts` | 17 | `package.json` defines `test = bun test`, but no workflow runs it. `install-matrix.yml` runs `bun install` only. |
| `tests/desktop/**/*.test.cjs` | 9 | `desktop-build.yml` runs three of them, but only on pull requests to `main`, under `desktop/**` paths. This branch targets `openJiuwen-Solar`. The other six are referenced nowhere. |
| `*.mjs` under `tests/` | 6 | No workflow, script or `package.json` entry references them. |
| `tests/platform/windows/*.Tests.ps1` | 2 | `install-matrix.yml` runs `install.Tests.ps1` on `windows-latest`. `windows-evidence-doctor.Tests.ps1` is referenced by nothing. |

All 34 now carry an `excluded` lane and a written reason in
`tests/ci_lanes.json`, so each is a recorded decision. That is not the same as
being tested. **Nothing here is covered; it is only no longer hidden.**

Seven more files were deleted rather than classified: stale duplicates at the
root of `tests/` left behind by the August move, each with a live twin deeper in
the tree.

```
tests/test-release-cut-safety.sh              -> tests/repository/release/test_release_cut_safety.sh
tests/test-release-public-tree.sh             -> tests/repository/release/test_release_public_tree.sh
tests/test-release-checklist.sh               -> tests/repository/release/test_release_checklist.sh
tests/test-release-coherence-tracked-inputs.sh-> tests/repository/release/test_release_coherence_tracked_inputs.sh
tests/test-provider-onboarding.sh             -> tests/platform/provider/test_provider_onboarding.sh
tests/install.Tests.ps1                       -> tests/platform/windows/install.Tests.ps1
tests/windows-evidence-doctor.Tests.ps1       -> tests/platform/windows/windows-evidence-doctor.Tests.ps1
```

They had drifted, and CI was running both copies. `test-release-checklist.sh` was
red while `test_release_checklist.sh` passes, which is what a stale copy looks
like from the outside: a permanent failure nobody can fix, because the file
being fixed is not the file being run.

**Decisions this leaves open, none of them CI's to make:** whether the 17
TypeScript tests should run at all, whether `desktop-build.yml` should trigger
on `openJiuwen-Solar`, and whether the six unreferenced `.mjs` files describe
contracts worth keeping.

---

## GAP-001 — dispatch ledger and queue plumbing

`scripts/check-harness-plumbing.sh` used to run
`"$home_dir/.solar/tests/harness/test_dispatch_ledger.sh"`. That path never
existed: the installer does not ship `tests/` into `~/.solar`, and this was the
only reference to it anywhere in the tree. The call exited 127, so the line
asserted nothing while reading like a passing check.

The line is now removed and the loss is recorded here rather than left implied.

**What is no longer checked.** The test still exists at
`tests/quarantine/unsafe_home_shell/disabled_dispatch_ledger.sh`, 202 lines,
covering 17 named behaviours:

- dispatch id format `d-<compact>-<6hex>`, and 1000 ids being unique
- ledger append for `attempted` / `acked` / `nacked`, and that the record
  carries the dispatch id and kind
- ledger query by sid, by dispatch id, and `--tail`
- queue enqueue returning `ok`, the same intent within 24h returning
  `duplicate`, and a different intent returning `ok`
- queue FIFO: peek returns the first item, peek does not consume, pop removes,
  depth decreases, peek then returns the second item

That is control-plane dedup and ordering. Nothing else in the suite asserts it.

**Why it is not simply re-enabled.** Three separate changes, and each is a
decision:

1. un-quarantine the test (it is quarantined for forcing a real `$HOME`, class
   `unsafe-real-home` in `tests/quarantine/additional_manifest.json`)
2. make it sandbox-safe so it stops writing to the developer's home
3. either ship `tests/` in the installer payload, or rewrite the check to run
   against the repository tree instead of the installed runtime

**Replacement wanted:** a sandbox-safe test covering at minimum dispatch id
uniqueness, ledger append/query round trip, and queue FIFO with 24h dedup.

## GAP-000 — where the duplicate `harness/tests/` tree came from

Not a mystery and not a stray copy. It is a restore that partially undid a
consolidation:

| commit | date | author | what it did | files under `harness/tests/` after |
| --- | --- | --- | --- | ---: |
| `711bd5fba` | 2026-08-07 | James Yuan | "consolidate repository tests under root suite" — moved 971 files to `tests/harness/`, renaming hyphens to underscores | **0** |
| `4b6a0522f` | 2026-08-07 | James Yuan | "Restore overwritten Stellven contributions" | 0 |
| `5f345e2dc` | 2026-08-10 | James Yuan | "Restore exact Stellven source-tip contributions" — **put 364 of them back** | **364** |
| `558f94a51`, `7c7e769a0` | 2026-08-10 | James Yuan | "Verify exact recovery", "Speed exact recovery object validation" | 364 |

`711bd5fba` was deliberate and correct: it also updated all five workflows,
`components.d/harness/component.sh`, `desktop/autotest.sh` and the docs to the
new paths. 1,346 files changed.

`5f345e2dc` restored file contents from an older source tip without accounting
for the fact that those files had been **moved and renamed**, not deleted. So
the restore recreated them at their old paths, beside the new ones, and nothing
was updated to point at them. The same commit re-added the 65 already-gitignored
files (see `ci-improvement/DELETION-MANIFEST.md`), which is the same mistake in
a different directory.

### What is actually in there now

| | files |
| --- | ---: |
| tracked under `harness/tests/` | 364 |
| byte-identical to their `tests/harness/` twin | 117 |
| diverged from their twin | 208 |
| no twin at the same path | 39 |
| ...of those, twin exists under the underscore rename | 33 (19 byte-identical) |
| **no twin under any name, anywhere in the repository** | **6** |

The six:

```
harness/tests/control_plane/test-graph-scheduler.sh
harness/tests/runtime/test-model-call-runtime.sh
harness/tests/skills/test-s2-skill-lifecycle.sh
harness/tests/test-intake-entrypoint.sh
harness/tests/test-role-dispatch-fallback.sh          (also at harness/test-role-dispatch-fallback.sh)
harness/tests/test-wiki-dispatch-state-preflight.sh
```

Five of those six exist nowhere else. They are the only files in the tree that
deleting it would actually lose, and they cover graph scheduler, model-call
runtime, skill lifecycle, intake entrypoint and wiki dispatch preflight.

The 208 "diverged" files are not evidence of unique content: they diverged
because the canonical copies have been maintained since the split and these have
not. That direction should be confirmed before deleting, but the expectation is
that `tests/harness/` is newer everywhere.

### Consequences already recorded elsewhere

- 5 of the secret-scan findings live in this tree (GAP-006, now allowlisted)
- `tests/harness/scenarios/test_collection_hygiene.py` loads
  `harness/tests/conftest.py`, one of the 208 diverged files, to check a
  quarantine manifest whose entries are 27 of 30 dead
- 268 of the 313 test files CI does not run are in here (GAP-010)

## GAP-002 — broker integration contracts assert absent symbols

Three test files assert named sprint acceptance criteria against functions that
do not exist in the product:

| test | contract | absent symbol |
| --- | --- | --- |
| `tests/harness/test_dispatcher_integration.py` | "graph_node_dispatcher.py broker integration (S03 N6)" | `get_broker` |
| `tests/harness/test_autopilot_broker_gate.py` | "autopilot.py broker coverage gate (S04 N1)" | `ready_for_planner`, `ready_for_builder` |
| `tests/harness/runtime/test_browser_research_job.py` | "N2: Browser Agent ChatGPT project routing" | `submit_research_job`, `resolve_monthly_project_name`, `capture_for_research` |

These read as stale tests and are not. The evidence:

- `harness/lib/execution_broker.py` exists, so the broker is not an abandoned
  idea.
- `harness/lib/graph_node_dispatcher.py` mentions broker 12 times and forwards
  `SOLAR_BROKER_ENABLED`, but has no `get_broker()`.
- `harness/lib/autopilot.py` mentions broker **zero** times, though S04 N1
  requires a broker coverage gate there that blocks `ready_for_planner`.
- `ready_for_builder` last appears in `004410b68` under
  `harness/tools/autopilot/`, a package that today contains only
  `__init__.py` and `event_recorder.py` with no module-level functions.

So the shape is a partial or lost integration across two delivered sprints, not
a test that outlived its subject. **Do not delete these tests.** Each needs the
specification and history read to decide between restoring the implementation,
rewriting the test against the contract that actually shipped, or retiring the
contract deliberately. Until that happens they are the only surviving record
that the contract was supposed to exist.

## GAP-003 — the 324 baselined failures are unclassified

`tests/ci_baseline.json` records what is red. It does not record **why**, or
whether the test or the product is wrong. The reason field currently holds the
failure message, which is a symptom.

Rough shape, from the failure signatures:

| signature | count | what it usually means |
| --- | ---: | --- |
| AssertionError | 130 | ran and disagreed; needs a human |
| shell/script exit only | 68 | needs the log read |
| FileNotFoundError | 40 | names a path that is not there |
| AttributeError / ImportError | 30 | names a symbol that is not there, see GAP-002 |
| other | 56 | mixed |

Triage order should be product risk, not signature: controller, scheduler,
evaluator, repair, integrity, evidence and security paths first.

**The default assumption must not be "the test is stale."** This repository is
partially broken by its own account, and the evidence supports that: GAP-002
shows two delivered sprint contracts whose integration points are simply absent
from the product. When a test and the product disagree, the product is at least
as likely to be the wrong one.

Classify every failure as exactly one of:

| class | meaning |
| --- | --- |
| product defect | the product is wrong; the test is right |
| missing contract | the behaviour was specified and never shipped, or was lost |
| test defect | the test is wrong: stale expectation, bad fixture, bad path |
| environment problem | needs something the runner does not have |
| nondeterministic, product side | the product gives different answers to the same input; this is a defect, not a flake |
| nondeterministic, test side | the test is order or timing dependent |
| unknown | not yet determined; never a resting state |

The two nondeterminism classes are deliberately separate. Filing product-side
nondeterminism as "flaky" is how a real intermittent defect gets a permanent
excuse.

## GAP-004 — four test files do not run in public CI

Listed with reasons in `tests/ci_lanes.json`. Excluding them is correct for a
public runner, but the behaviour they cover is unchecked everywhere:

- `test_agent_arena_benchmark.sh` — agent arena benchmark plumbing
- `test_mia_runtime_adapter.sh` — MIA runtime adapter and native memory server
- `test_phase5_content_diversity.py` — live research provider path
- `test_phase5_platform_provider_resilience.py` — Windows/WSL host path

Anything that changes those subsystems has no CI signal at all. Re-check by
hand when touching them.

## GAP-005 — no flake quarantine

The gate blocks when a baselined test passes, so a genuinely flaky test that
happens to pass will block a pull request that had nothing to do with it. The
only escapes today are fixing the test or excluding it from the lane manifest,
and exclusion removes the coverage entirely.

What is missing is a third state: quarantined, with an owner and an expiry, that
runs and reports but does not gate. Google reports roughly 16% of their test
targets are flaky at some point, so this is not a hypothetical.

There is also a circularity that has to be resolved before any quarantine is
built. A test that is sometimes red and sometimes green cannot be handled by the
baseline at all: leave it out and it blocks as a new failure, put it in and it
blocks as an unrecorded fix. The baseline is a two-state mechanism and this is a
three-state problem.

**Quarantine must not become the bin for product-side nondeterminism.** See
GAP-008: the first candidate found turned out to be the product's own
consistency check disagreeing with itself between runs, which is a defect. A
quarantine that accepts those converts defects into permanent noise.

## GAP-006 — secret scan excused on pull requests (CLOSED)

`repository-hygiene` used to set `EXCUSED_ON_PULL_REQUEST: "secret_scan"`, so a
genuinely new secret in a pull request was reported and not blocked. An advisory
secret scan does not stop a leak; it describes one.

The five findings were all fixtures for the secret-**scrubbing** feature: a test
proving a scrubber removes an API key has to contain a key-shaped string, and
there is no version of those tests without one. Each was read individually and
is a literal inside an assertion about redaction, never read from configuration
or sent anywhere.

They are now pinned in `.secret-scan-allowlist` as
`<rule> <sha256-of-the-line> <path>`, which is the mechanism the scanner already
had. Editing a single character of an allowlisted line re-reports it, so the
exception cannot drift into covering something new. The excusal is gone and the
list is empty. Scan result: 4,966 files, no findings, exit 0.

All five live under the duplicated `harness/tests/` tree; if that tree is
removed, the five allowlist lines go with it. The allowlist file carries that
note.

## GAP-007 — almost no test is calibrated

A green test only proves something if it would go red when the behaviour breaks.
Where that has been checked, by mutating the product and requiring a **named
test to fail on its own assertion** rather than on a collection or setup error:

| target | mutations | caught | notes |
| --- | ---: | ---: | --- |
| `gate_ledger.is_gate_consumable` fail-closed guards | 6 | 6 | one survived at first; see below |
| `graph_scheduler.set_node_status` monotonicity | 1 | 1 | |
| `tests/conftest.py` import precedence | 2 | 2 | both survived at first; see below |
| `scripts/check-test-baseline.py` | 9 | 9 | one survived at first; see below |
| `tests/harness/test_pm_dispatch.py` graph status write | 3 | 1 | **still weak** |

Three of those found something:

- **`applied=False` was unguarded in practice.** Deleting the
  `record.get("applied") is False` check from `is_gate_consumable` survived all
  126 gate-ledger tests, because every test that sets `applied=False` also sets
  a doctor author or `gate_consumable=False`, so the record was rejected for a
  different reason every time. A record marked neutralised, from an assigned
  evaluator, at the current generation, would have fed a gate decision. Closed
  by `test_neutralized_record_never_consumable`.
- **Import precedence was protected only by chaos.** Reversing it produced 250+
  collection errors, which is loud but names nothing, and a partial shadowing
  would not break collection at all. Now asserted directly in
  `tests/repository/governance/test_import_precedence.py`, including the
  hostile-`PYTHONPATH` case that is the only one where the dedupe in that loop
  is load-bearing.
- **A gate test passed for the wrong reason.** The rule that red wins when two
  shards disagree was only exercised in the file order where any merge rule
  looks correct. Now parametrised over both orders.

Still weak, and recorded rather than fixed: `test_pm_dispatch.py` detects
**removal** of the graph status write but not **corruption** of it, because a
downstream call rewrites the value. Two of three mutations survive it.

The other ~6,800 cases are uncalibrated. Whole-suite mutation testing is not
feasible and is not the goal; the workable version is mutating **changed** code
during review. Until that exists, "the suite is green" means the suite did not
object, not that it would have.

## GAP-008 — confirmed nondeterminism, cause unclassified

`tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_research_scheduler_online_uses_source_runtime_evidence`
was green in one composed run and red in the next, from the same commit, in the
same shard, at the same list index (648 of 714, so no reshuffle was involved).
It passes 4 out of 4 times when run alone.

What differs is not the test. The product returned exit 2 with:

```
"scheduler_workflow_config_alignment_status": "drift",
"scheduler_workflow_config_alignment_issues": [
  "configured_nodes_missing_from_runner",
  "configured_nodes_not_required_by_run"
]
```

That is `harness/tools/run_scientific_lifecycle_smoke.py` comparing the
configured lifecycle nodes against what the runner actually provides and
requires, and reporting that the configuration declares nodes the runner does
not have. It is the product's own self-consistency check, and it reached a
different verdict on two runs of the same code.

The config drift turned out to be a symptom, not the cause. The retained
runtime record from the failing run,
`.../scheduler_lifecycle/scientific_lifecycle_runtime.json`, gives the chain:

```
paper_analyze_dispatched      -> error   (detail: "failed")
lifecycle_runtime_gate_passed -> error
```

`_run_scheduler_node` returned non-zero, or a status other than `passed`, for
the `paper_analyze` node (operator `autosci-paper-analyze-worker`). The
lifecycle gate then failed, the run stopped after 2 of its 14 declared nodes,
the alignment check reported the remaining 12 configured nodes as not required,
and the shim exited 2. The test asserting exit 0 is the last link, not the
first.

So this is **an intermittent failure in AutoSci scheduler node dispatch**, in
the scheduler path, which is at the top of the risk order in GAP-003. Timing
supports it: the failing run took 6.5s, the passing runs 12.3s and 13.6s, and
the test passes 4 out of 4 in isolation.

### Three runs of the same commit

| | run 1 | run 2 | run 3 |
| --- | ---: | ---: | ---: |
| cases | 7,222 | 7,222 | 7,222 |
| red | 325 | **324** | 325 |
| shards, names as declared | yes | yes | yes |

**Two of 7,222 cases changed state across the three runs (0.03%).** Nothing in
the baseline flipped to passing, and no test was missing from any run. The rest
of the suite is deterministic.

Both unstable cases are in `tests/plugins/autosci/test_autosci_skill_shim.py`
and both have the same failure shape, on a **different node each time**:

| test | runs | failing check |
| --- | --- | --- |
| `..._scheduler_online_uses_source_runtime_evidence` | fail, pass, pass | `paper_analyze_dispatched` -> failed |
| `..._scheduler_run_records_human_gate` | pass, pass, fail | `literature_discover_dispatched` -> failed |

followed in both cases by `lifecycle_runtime_gate_passed -> failed`.

### Withdrawn claims

Two things previously asserted here were not supported by the evidence and are
withdrawn:

- **"One intermittent defect in scheduler node dispatch."** The support offered
  was that both failures had the same shape. Every node emits
  `<node>_dispatched`, so that shape is the only one available when any node
  fails; it is close to tautological and is not evidence of a common cause. One
  dispatch defect, two node-specific defects, and a shared-state cause all fit
  what was observed.
- **"Blocks roughly two pull requests in three."** Two events in three runs
  cannot distinguish a 30% rate from an 80% one. No rate is claimed.

Also noted and discarded: that both failures landed in `pytest-0` is not
evidence. Both tests are in one file, and a file always lands in exactly one
shard, so no other outcome was possible.

**Current classification: confirmed nondeterminism, cause unclassified.**

### Why this blocks, without needing a rate

Both cases are green-side, so each blocks as a new failure when it fires. The
argument does not depend on how often that is:

**A single green-side nondeterministic test breaks the baseline model.** Leave it
out and it blocks as a new failure. Put it in and it blocks as an unrecorded fix
on the runs where it passes. Frequency changes how irritating that is, not
whether it happens.

There is no way to absorb this with the baseline: the tests pass often enough
that recording them as red would then block as unrecorded fixes. That is the
three-state problem in GAP-005, and it is now concrete rather than theoretical.

So the honest order is: understand and fix this dispatch defect, or build the
quarantine state with an owner and an expiry. Turning the gate on before either
means teaching everyone to ignore it in week one.

Why dispatch intermittently fails is triage work and deliberately not done here.

### Cause identified

Full per-run record in `ci-improvement/GAP-008-EVIDENCE.md`. Summary:

Both failures fail **one** check out of twelve,
`operator_log_contains_bridge_action`, with `operator exit_code: 0`, the
evidence gate passed, and `log_tail` equal to `"{"` — a partially written log.
Two different nodes, two different operators, two different tests, two
different runs, one identical signature.

`harness/tools/run_scientific_node_smoke.py` waits for `result.json` via
`_wait_for_result`, then reads `output.log` immediately with no wait of its
own. The operator daemon writes those two files independently and nothing
orders them, so a run that reads the log before the daemon flushes it sees a
truncated file and marks the node failed. The work itself had already
succeeded.

This is a **product defect**: a correctness gate placed on an unsynchronised
log file. The classification moves from "cause unclassified" to "cause
identified, fix not yet demonstrated".

Not attempted, deliberately: the fix. Demonstrating the responsible behaviour
means reproducing the race on purpose, not inferring it from correlation, and
that has not been done.

## GAP-009 — a test file that passes only because other files ran first

Found while investigating GAP-008, and unrelated to it.

`tests/plugins/autosci/test_autosci_skill_shim.py` fails **more** on its own
than it does as part of the suite:

| context | result |
| --- | --- |
| the file alone, 4 runs | 26 failed, 148 passed, 1 skipped — identical every time |
| inside shard `pytest-0`, 3 composed runs | 22, 23, 23 failed of 175 |

So roughly three or four of its tests pass only because something earlier in the
shard left state behind. This is deterministic, not flaky: all four isolated runs
produced byte-identical totals.

Two reasons it matters beyond tidiness:

- Those tests are recorded as **green** in `tests/ci_baseline.json`, which
  credits them with coverage they do not independently have.
- Sharding is by file, and files are dealt round-robin over a sorted list.
  Adding or renaming any test file earlier in that list moves this file to a
  different shard, changing its neighbours, and those tests could then flip to
  red with no change to the code they cover.

Which tests, and what state they inherit, is not investigated. The candidate set
is the difference between the two columns above.

## GAP-010 — 45 test files outside `tests/` are run by nothing

The census, the lane manifest and the shard runner all scan `tests/` and only
`tests/`. That is 754 tracked test-shaped files. The repository has **1,067**.

| location | files | status |
| --- | ---: | --- |
| `tests/` | 754 | run by CI |
| `harness/tests/` | 268 | the duplicate tree; covered by the pending delete decision |
| **elsewhere** | **45** | **run by nothing, and not a duplicate of anything** |

The 45:

| location | files | runner it would need |
| --- | ---: | --- |
| `harness/plugins/autosci/tests/` | 21 | pytest |
| `harness/` root, `test-*.sh` | 11 | bash |
| `desktop/` and `desktop/src/` | 9 | node or bun (`*.test.js`, `*.spec.ts`) |
| `scripts/test-local.sh` | 1 | bash |
| `harness/status-server/` | 1 | mixed |
| `harness/lib/` | 1 | pytest |
| `distribution/pipx/tests/` | 1 | pytest |

27 files repository-wide are JavaScript or TypeScript tests. **No lane in
`tests/ci_lanes.json` can run those at all**; the runner only knows pytest,
bash and direct-interpreter Python.

This is the same class of defect the census was built to prevent, one directory
up: the census proves nothing is invisible *inside* `tests/`, and says nothing
about outside it. Fixing it means either moving these under `tests/`, widening
the census root, or recording each as deliberately out of scope.

## GAP-011 — the suite runs on Linux only

`test-suite` and `test-suite-gate` are `runs-on: ubuntu-latest`, single OS.

The repository does test other platforms, but only for install and packaging,
never for the test suite:

| workflow | job | platform |
| --- | --- | --- |
| `install-matrix.yml` | `install` | ubuntu-latest, macos-latest |
| `install-matrix.yml` | `ps1-pester` | windows-latest |
| `windows-wsl2-install.yml` | `windows-wsl2` | windows-latest |
| `desktop-build.yml` | `build` | matrix |
| `solar-ci.yml` | everything, including `test-suite` | ubuntu-latest only |

So a Windows-only or macOS-only regression in product behaviour is invisible,
while a Windows-only *install* regression is caught. Whether the suite should
be a matrix is a cost decision: nine shards times three OSes is 27 jobs per
pull request. Recorded so the single-OS scope is a choice rather than an
oversight.

Related: `tests/ci_lanes.json` already excludes
`test_phase5_platform_provider_resilience.py` for needing a Windows host. On a
Windows runner that exclusion would be wrong, so lane assignment is
platform-dependent and the manifest has no way to say so.

## GAP-012 — the baseline contains failures that only exist on my machine

Running shard `pytest-0` **alone**, three times, against the same shard run
inside the composed nine-shard run:

| setup | cases | red | stable across runs |
| --- | ---: | ---: | --- |
| shard alone, no other shards | 1,240 | **87** | yes, identical all three |
| composed, 5 shards concurrent | 1,240 | 89, 88, 89 | no |

Zero tests are red when alone and green under load. The difference is one
direction only: **three tests in `tests/plugins/autosci/test_autosci_skill_shim.py`
fail only when other shards are competing for the machine.**

| test | alone | under load |
| --- | --- | --- |
| `..._daily_arxiv_uses_verified_runtime_digest` | pass ×3 | **fail ×3** |
| `..._research_scheduler_online_uses_source_runtime_evidence` | pass ×3 | fail once in three |
| `..._research_scheduler_run_records_human_gate` | pass ×3 | fail once in three |

The first one is the problem. It is red in **every** composed run, so it never
looked nondeterministic and it went into `tests/ci_baseline.json` as a genuine
known failure. It is not one. It is an artefact of running five shards on one
laptop.

On GitHub Actions each matrix job is its own VM, with no competing shards, so
that test will pass — and the gate will block it as an **unrecorded fix**, on a
pull request that has nothing to do with it.

The baseline was generated under conditions CI does not have. At least one of
its 324 entries is wrong for that reason, and only shard `pytest-0` has been
checked; the other eight may carry their own.

### Measured across the whole baseline, not just one shard

256 of the 324 entries resolve to pytest node ids. 255 of those were re-run on a
quiet machine, one process, nothing else running. **Five pass.** They were never
product failures:

```
tests/harness/lib/social_browser_backend_x/test_lease_ratelimit.py::TestBrowserLeaseClientMockFallback::test_blocker_guard_ok_selects_real_backend
tests/harness/runtime/test_mirage_context_access_plane.py::test_context_usage_verifier_fails_missing_required_source
tests/harness/runtime/test_mirage_context_access_plane.py::test_context_usage_verifier_requires_code_source
tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion
tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_daily_arxiv_uses_verified_runtime_digest
```

`daily_arxiv` is the one predicted above. The other four are new, and two of
them are in `runtime/`, a shard this analysis had not touched, which confirms
the contamination is not confined to `pytest-0`.

They are deliberately **not** hand-removed from `tests/ci_baseline.json`. A
partial correction would imply the remaining 319 entries had been verified, and
they have not: the 68 shell and script entries were not re-run at all, and
"passes when alone" is a weaker claim than "passes on a GitHub Actions VM".

### Resolved by GitHub Actions run 87

The baseline is now recorded from CI rather than from a laptop. What that run
showed is worse than contention, and worth recording because the cause was a
methodology error, not a machine:

| | count |
| --- | ---: |
| entries the local baseline was missing | **10** |
| entries that were never red on CI | **8** |
| net | 324 → 326 |

The ten missing entries were not flakes. **All ten fail at the base commit
`5cccc0b49` with a clean worktree.** They were missed because the local baseline
was generated from a working tree with 65 files staged for deletion, so every
test that reads repository state — tracked generated artifacts, workbook
outputs, reconciliation blobs — saw a repository that exists nowhere.

The lesson generalises: **a baseline may only be generated from a committed
tree, and preferably from CI.** Nothing about the local tooling detects a dirty
worktree, and nothing warned.

Of the five entries this document previously called contaminated, only one —
`daily_arxiv` — appears in CI's unrecorded-fix list. The other four are red on
CI as well. "Passes when run alone on a quiet laptop" was a weaker signal than
it looked, and the earlier claim that all five were never product failures was
wrong.

**Remaining before `ENFORCING` can be flipped:** one run reporting a clean
verdict against this baseline with no change to it. Flipping in the same change
that rewrote the baseline would make a clean result unfalsifiable.

### GAP-008 resolution

Downgraded. Six runs with the shard alone or the file alone never reproduce it;
it appears only when five shards compete for one machine. CI gives each shard
its own VM, so CI should not see it.

The underlying code is still wrong: `run_scientific_node_smoke.py` waits for
`result.json` and then reads `output.log` without waiting for it, and the two
are written independently. That race is real and only loses under load. It is a
latent defect worth fixing, not a blocker, and not the reason enforcement is
held — see GAP-012 for that.
