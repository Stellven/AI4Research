# Terminal-Bench 2.0 Adapter — Solar-Harness Benchmark Submodule

Status: P0 — landed by sprint `sprint-20260520-benchmark-terminal-bench-2-s03-core-runtime`.
Slice ownership: S03 (Python module + tests). The `solar-harness benchmark` CLI wrapper is owned by S04.
Source-grounding: every fact below traces back to one of the five sources frozen in PRD §1 (urls listed in §1 of this doc).

---

## 1. Evidence Base (PRD §1, frozen)

| # | Source | Fact used | URL |
|---|---|---|---|
| 1 | LangChain blog — *Evaluating Deep Agents CLI on Terminal-Bench 2.0* | LangChain used Harbor to evaluate Deep Agents CLI on Terminal-Bench 2.0; Terminal-Bench 2.0 ships 89 tasks; Harbor owns container isolation, automatic testing, reward scoring and dataset registry. | https://www.langchain.com/blog/evaluating-deepagents-cli-on-terminal-bench-2-0 |
| 2 | Harbor GitHub README | Harbor is a framework for evaluating and optimizing agents and is the official harness for Terminal-Bench 2.0; canonical command shape is `harbor run --dataset terminal-bench@2.0 --agent <agent> --model <model> --n-concurrent <n>`; local execution defaults to Docker, with optional Daytona/Modal/e2b/runloop cloud sandboxes. | https://github.com/harbor-framework/harbor |
| 3 | Terminal-Bench GitHub | Terminal-Bench is an LLM/agent benchmark for complex tasks performed in a real terminal; Apache-2.0 licensed. | https://github.com/harbor-framework/terminal-bench |
| 4 | Terminal-Bench 2.0 arXiv paper | Terminal-Bench 2.0 is composed of 89 terminal tasks inspired by real workflows; each task ships an isolated environment, a human reference solution, and comprehensive tests; frontier agents in the paper score below 65 %. | https://arxiv.org/abs/2601.11868 |
| 5 | Harbor Registry — `terminal-bench@2.0` | The Harbor registry exposes the dataset manifest and per-task run examples for Terminal-Bench 2.0. | https://www.harborframework.com/registry/terminal-bench/2.0 |

Every downstream assertion in this document either restates a fact from one of those five rows or is an internal Solar-Harness design decision; nothing here is freelanced research.

---

## 2. Why an adapter (not a script)

Solar-Harness already has scattered benchmark scripts that each invent their own `doctor`, their own report layout, and their own failure handling. That makes evaluators unable to compare runs, blocks the capability scorecard, and lets "I ran the benchmark on my laptop" results sneak into sprint evidence without any of the safety rails (budget, sandbox, key handling) the rest of Solar enforces.

The benchmark submodule reuses Solar's existing primitives — DAG dispatch, pane assignment, event ledger, artifact registry, evaluator chain — and exposes one stable interface (`BenchmarkAdapter`) that any external benchmark can be wrapped into. Terminal-Bench 2.0 is the first inhabitant; future adapters (e.g. SWE-bench, OSWorld, MLE-bench) plug into the same registry.

---

## 3. Slice boundaries (S03)

| Sprint | Owns | Touched by S03 |
|---|---|---|
| S01 — requirements | Refined PRD + traceability matrix | read-only |
| S02 — architecture | Interface contract, schemas, CBD freeze | read-only |
| **S03 — core runtime** (this one) | `harness/lib/benchmark/` package + `python3 -m harness.lib.benchmark.runner` entrypoint + tests | all writes |
| S04 — orchestration UI | `bin/solar-harness benchmark)` case branch + multi-task dashboard cards | **not** touched by S03 |
| S05 — verification + release | `verify.sh` + cross-sprint smoke + epic close | **not** touched by S03 |

S03 deliberately does not register the `benchmark)` case in `bin/solar-harness`. The acceptance commands therefore use `python3 -m harness.lib.benchmark.runner …` directly. The `solar-harness benchmark …` form lands in S04.

---

## 4. Package layout

```
harness/lib/benchmark/
  __init__.py         re-exports the public Protocol + dataclasses + registry; imports terminal_bench last to seed the registry
  schemas.py          frozen dataclasses, SCHEMA_VERSION, AGENT_ALLOWLIST, SAFE_TASKS, DEFAULT_DATASET, VALID_ENVS
  registry.py         ADAPTER_REGISTRY dict + register() decorator + get_adapter() + list_adapters()
  harbor_adapter.py   detect(), docker_available(), build_argv(), probe_dataset(), probe_api_key()
  terminal_bench.py   TerminalBench20Adapter — composes harbor_adapter; @register at module bottom
  reports.py          write_run_artifacts(), sha256_file(), latest pointers, artifacts manifest
  runner.py           argparse + dispatch + __main__; emits benchmark.* events

harness/tests/benchmark/
  test_benchmark_registry.py        pytest — registry roundtrip + seed discovery
  test_terminal_bench_adapter.py    pytest — argv shape, allowlist gate, budget gate, pending verdict, no-secret-logging
  test_benchmark_report_schema.py   pytest — run.json schema lock + tuple→list serialisation
  test-terminal-bench-adapter.sh    bash — CLI smoke: doctor/list/plan/run-dry-run/rogue-agent/full-without-budget

harness/docs/benchmark/
  terminal-bench-2.md               THIS file
```

S03 must not create files outside those three directories. S04 will add `bin/solar-harness` shell code; S05 will add `verify.sh`; both are out of S03 scope.

---

## 5. Frozen interface (S02 §4)

All dataclasses are `@dataclass(frozen=True)`. S03 can add optional fields with defaults; it cannot rename, remove, or retype existing fields.

```python
SCHEMA_VERSION   = "benchmark.run.v1"
AGENT_ALLOWLIST  = ("claude-code", "deepagents-cli", "openai-cli")   # CBD7
SAFE_TASKS       = ("chess-best-move", "hello-world-cli", "wc-frequency")  # CBD2
DEFAULT_DATASET  = "terminal-bench@2.0"
VALID_ENVS       = ("docker", "daytona", "modal", "e2b", "runloop")

class BenchmarkAdapter(Protocol):
    id: str
    version: str
    def doctor(self) -> BenchmarkDoctor: ...
    def list_tasks(self) -> list[BenchmarkTask]: ...
    def plan(self, request: BenchmarkRunRequest) -> BenchmarkRunPlan: ...
    def run(self, request: BenchmarkRunRequest) -> BenchmarkRunResult: ...
    def parse_result(self, run_dir: Path) -> BenchmarkRunResult: ...
```

`BenchmarkRunResult` carries the PRD §7 minimum field set: run identity (`run_id`, `benchmark`, `benchmark_version`, `dataset`, `adapter`), execution context (`agent`, `model`, `env`), scope (`tasks_requested`, `tasks_completed`), scoring (`score`, `pass_count`, `fail_count`, `pending_count`), timing (`started_at`, `completed_at`, `duration_sec`), exec details (`command`, `exit_code`, `stdout_path`, `stderr_path`), artifacts list, and a triage triple (`verdict`, `failure_modes`, `limitations`). The run-id format is `bench-<YYYYMMDDHHMMSS>-<8hex>` (CBD8).

---

## 6. Harbor command shape

Per Harbor's README (source 2 above), the canonical invocation is:

```bash
harbor run \
  --dataset terminal-bench@2.0 \
  --agent <agent> \
  --model <model> \
  --n-concurrent <n> \
  --env <docker|daytona|modal|e2b|runloop> \
  <task_id> [<task_id> ...]
```

`harbor_adapter.build_argv(req)` is a pure function that reproduces that shape from a `BenchmarkRunRequest`. When Harbor is missing as a binary but `uvx` is on `PATH`, the argv is prefixed with `["uvx", "harbor", ...]` (matches Harbor's distribution as a `uvx`-runnable package). The function never executes the command; execution is the runner's job.

For the dry-run path the argv is still computed and serialised into `run.json` under the `command` field, so evaluators can reproduce the exact invocation without S03 ever spawning a subprocess.

---

## 7. State machine of `run(req)` (S02 §6)

```
INIT  → validate adapter_id / agent / env / task subset / full-budget gate
DOCTOR → harbor + docker + dataset + per-agent key presence; collect missing_prereqs
PLAN  → harbor_adapter.build_argv(req); record env_overrides as presence-only markers
EXEC  → only if not dry_run AND not missing_prereqs; subprocess.Popen → run_dir/stdout.log + stderr.log
PARSE → parse_result(run_dir); score may be None; verdict downgrades to warn on parse failure
REPORT→ reports.write_run_artifacts(run_dir, result); event emitted (completed | failed | pending)
```

Hard validation gates (never silently coerce to `ok`):

- `req.agent ∉ AGENT_ALLOWLIST` → `verdict="error"`, `failure_modes=["agent_not_in_allowlist"]`
- `req.full and not req.confirm_budget` → `verdict="error"`, `failure_modes=["full_run_without_confirm_budget"]`
- `req.env ∈ {daytona,modal,e2b,runloop}` and the matching API key is absent → `verdict="pending"`
- any item in `doctor.missing_prereqs` → `verdict="pending"`, the prereq list propagates verbatim into `failure_modes`

These rules implement PRD §14 "never fabricate a score". If the environment cannot truly run the benchmark, the result is `pending`, not `ok`.

---

## 8. Reports layout

```
~/.solar/harness/reports/benchmark/
  <run-id>/
    run.json                machine-readable, PRD §7 schema-locked
    report.md               human-readable Markdown
    stdout.log              real harbor stdout (only when EXEC ran)
    stderr.log              real harbor stderr (only when EXEC ran)
    events.compat.jsonl     only if main ledger was unwritable (CBD4 fallback)
    artifacts.manifest.json only if registry unavailable (CBD5 fallback)
    exit_code.txt           one-byte int — survives crash recovery
  latest-terminal-bench-2.json   copy (not symlink) of last run.json
  latest-terminal-bench-2.md     copy (not symlink) of last report.md
```

The default base directory is `Path.home() / ".solar/harness/reports/benchmark"`. Tests override it through `SOLAR_BENCH_REPORTS_DIR`. All writes use `tempfile` + `os.replace` for atomicity so partial reports never appear on disk.

---

## 9. Event ledger integration

`runner._emit_event(event_name, payload)` appends one JSON line per state transition to `~/.solar/harness/state/events.jsonl`. On any `OSError`/`PermissionError`/`FileNotFoundError` it falls back to `<run-dir>/events.compat.jsonl` (CBD4). Every event carries `actor="benchmark"` and a UTC timestamp.

Event names (frozen by S02 §8):

```
benchmark.doctor        {adapter_id, verdict, missing_prereqs[]}
benchmark.plan          {adapter_id, command_argv[], dry_run}
benchmark.run.started   {adapter_id, run_id, agent, model, env, tasks[]}
benchmark.run.pending   {run_id, missing_prereqs[]}
benchmark.run.completed {run_id, verdict, score, pass_count, fail_count, duration_sec}
benchmark.run.failed    {run_id, exit_code, failure_modes[]}
```

Payloads are sanitised by `event_bridge._sanitize()` (S04 helper): any key whose name matches `(?:_key|_token|_secret|_password|_passwd|_apikey)$` is replaced with `"<redacted>"` before serialisation, so no real key value can leak through the ledger.

---

## 10. Safety rails (P0)

- **No real Harbor execution** — every test mocks `subprocess.run`; the bash smoke driver swaps in `unittest.mock.patch` stand-ins for `harbor_adapter.detect`, `docker_available`, `probe_dataset`, and `probe_api_key`.
- **No real Docker pulls** — `docker info` has a 2-second timeout; failure is silent (returns `False`), never raises.
- **No secret values logged** — `probe_api_key` returns `bool`. Plan output emits `{"ANTHROPIC_API_KEY": "present"}`, never the value. `test_terminal_bench_adapter.py` plants a `sk-FAKE-DO-NOT-LEAK-XYZ-987654321` sentinel and asserts it never appears in stdout, stderr, or any serialised payload.
- **Allowlist** — agents outside `AGENT_ALLOWLIST` are rejected at the first validation gate.
- **Budget gate** — `--full` requires `--confirm-budget`. Without it, the runner returns `verdict="error"` and exits with code 1.
- **Frontier baseline** — per source 4 (arXiv), frontier agents score < 65 % on Terminal-Bench 2.0; the adapter therefore treats `score` as optional. P0 acceptance never asserts a score floor; it only asserts schema correctness and verdict discipline.

---

## 11. Defaults and CBD resolutions

| CBD | Resolution | Where |
|---|---|---|
| CBD2 | `SAFE_TASKS = ("chess-best-move", "hello-world-cli", "wc-frequency")` | `schemas.py` |
| CBD3 | Score-to-capability mapping deferred to S04 | n/a at S03 |
| CBD4 | Event ledger fallback to `<run-dir>/events.compat.jsonl` | `runner._emit_event` |
| CBD5 | Artifact registry fallback to `artifacts.manifest.json` | `reports.write_run_artifacts` |
| CBD7 | `AGENT_ALLOWLIST = ("claude-code", "deepagents-cli", "openai-cli")` | `schemas.py` |
| CBD8 | Run-id format `bench-<YYYYMMDDHHMMSS>-<8hex>` | `schemas.new_run_id` |

---

## 12. Example invocations

```bash
# 12.1 doctor — pure inspection, never spawns Harbor
python3 -m harness.lib.benchmark.runner doctor --json

# 12.2 list — lists the seeded safe tasks (CBD2)
python3 -m harness.lib.benchmark.runner list --json

# 12.3 plan — computes Harbor argv without executing
python3 -m harness.lib.benchmark.runner plan \
  --agent claude-code --model claude-opus-4-7 \
  --env docker --tasks hello-world-cli --json

# 12.4 run --dry-run — writes PENDING/OK report; never spawns Harbor
SOLAR_BENCH_REPORTS_DIR="$(mktemp -d)" \
  python3 -m harness.lib.benchmark.runner run \
  --agent claude-code --model claude-opus-4-7 \
  --env docker --tasks hello-world-cli --dry-run --json
```

When Harbor/Docker/API keys are absent on a dev box, `run --dry-run` returns `verdict="pending"` with the missing prereqs enumerated in `failure_modes`. That is the **passing** P0 outcome — not a failure.

---

## 13. Cross-references

- S01 PRD: `harness/sprints/sprint-20260520-benchmark-terminal-bench-2-s01-requirements.prd.md`
- S02 design (interface contract): `harness/sprints/sprint-20260520-benchmark-terminal-bench-2-s02-architecture.design.md`
- S03 design (this slice): `harness/sprints/sprint-20260520-benchmark-terminal-bench-2-s03-core-runtime.design.md`
- S03 sprint handoff (P0 acceptance evidence): `harness/sprints/sprint-20260520-benchmark-terminal-bench-2-s03-core-runtime.handoff.md`

---

Knowledge Context: solar-harness context inject used (Mirage degraded → Solar DB + QMD + Obsidian fallback; PRD §1 sources frozen by S01).
Harness Modules Used: harness.context_preflight (STATE.md read before write), harness.dag (graph-scheduler mark), harness.contracts (S02 §4 frozen interface), harness.status, harness.dispatch_visibility.
