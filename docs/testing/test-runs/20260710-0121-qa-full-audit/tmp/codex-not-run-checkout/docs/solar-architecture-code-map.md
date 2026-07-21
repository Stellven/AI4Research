# Solar Architecture Code Map

Solar is best understood as an AI-native execution fabric: user intent enters as natural language, becomes a file-backed contract, compiles into task structure, binds to schedulable AI workers, and closes through evidence.

This document maps the architecture to the repository code surface.

---

## 1. The operating model

Solar is not organized around a single model call. It is organized around a software-organization loop:

```text
Boss intent
  -> requirement compiler
  -> TaskGraph IR
  -> logical operator
  -> actor and host binding
  -> lease and dispatch
  -> handoff and evaluation
  -> accepted artifact
  -> memory and optimization
```

The important shift is that the user is not runtime glue. The user sets goal, boundary, budget, and approval policy. Solar handles planning, assignment, execution, evidence review, reporting, and learning.

---

## 2. Actor / host model

Code surface:

- `harness/config/agent-actors.json`
- `harness/config/actor-hosts.json`
- `harness/lib/multi_task_status.py`

Solar separates the worker identity from the execution environment.

An actor carries role, lease, mailbox, capability profile, risk profile, cost profile, quota, policy, evidence, and fallback ladder. A host represents the environment that carries actors: Claude Code session, Antigravity environment, tmux pane, Codex worktree, browser profile, local process, remote shell, or sandbox-like carrier.

This lets Solar reason about AI workers as a fleet rather than as anonymous chats.

---

## 3. Logical operators

Code surface:

- `harness/config/logical-operators.json`

Solar defines logical work separately from concrete execution. Examples already modeled in the repository include:

- `DeepArchitect`
- `RootCauseDebugger`
- `ImplementationWorker`
- `PatchWorker`
- `TestDesigner`
- `BenchmarkRunner`
- `SecurityGate`
- `QuotaBroker`
- `ContextCompressor`
- `DeepResearchBrowser`
- `DeepResearchGemini`
- `DeepResearchChatGPT`
- `WebwrightPlaywright`
- `BrowserUseMcp`
- `YoutubeTranscriptExtractor`
- `TechnologyDiagramPainter`

Each logical operator can describe capability needs, concurrency, cost hint, workflow position, candidate actors, and fallback policy.

This is the database-query-planner idea applied to AI work: define the logical plan first, then choose the physical plan.

---

## 4. Physical operator runtime

Code surface:

- `harness/lib/operator_runtime.py`
- `harness/tools/operatord.py`
- `harness/config/physical-operators.json`

The operator runtime validates task envelopes, checks if an operator is available, acquires process-safe leases, writes inbox tasks atomically, starts operator workers, records heartbeats, writes result artifacts, and normalizes runtime state.

Useful states include:

```text
idle, leased, running, draining, cooldown, quota_exhausted, auth_expired, disabled
```

This is the layer that turns AI surfaces into managed runtime workers.

---

## 5. Requirement compiler and DAG scheduling

Code surface:

- `harness/templates/contract-template-v2.md`
- `harness/lib/epic_decomposer.py`
- `harness/lib/graph_scheduler.py`
- `harness/lib/graph_node_dispatcher.py`

Solar's core flow is not prompt to answer. It is intent to contract to graph to dispatch to evidence.

The DAG scheduler provides several system guarantees:

- invalid graphs fail fast;
- ready nodes require dependencies to pass;
- overlapping write scopes are not batched together;
- missing write scope is treated conservatively;
- parent sprint closure waits for node and gate closure.

This is where Solar starts to behave more like a build system than a chatbot.

---

## 6. Workflow and architecture guards

Code surface:

- `harness/lib/workflow_guard.py`
- `harness/lib/architecture_guard.py`

Workflow guard encodes the lifecycle:

```text
PM -> Planner -> TaskGraph -> Builder -> Evaluator
```

Architecture guard encodes package-first system design. New capabilities should prefer package, plugin, skill, connector, or integration boundaries instead of mutating the control-plane core. Exploration work should define alternatives and stop conditions.

The point is simple: a self-improving agent system needs runtime policy, not just prompts.

---

## 7. Capability capsules

Code surface:

- `harness/lib/capability_capsules.py`
- `harness/config/capability-capsules.registry.yaml`
- `harness/schemas/draft/capability-capsule.v1.draft.json`

Capability capsules package capability intent, input/output contracts, composition, effects, bindings, verification, and operator compatibility into one governance unit.

The registry already contains stable and draft capsules for:

- requirement compiler planning;
- requirement compiler implementation;
- requirement compiler verification;
- research scout and synthesizer paths;
- understand-anything style codebase mapping;
- guard and resource capsules.

This is how Solar moves from loose tools to schedulable capabilities.

---

## 8. Evidence and event sourcing

Code surface:

- `harness/lib/session_log.py`
- `harness/lib/projection_engine.py`
- `harness/lib/research/evaluator.py`

Solar uses an append-only session log with monotonic sequence numbers and idempotency-key deduplication. Projection rebuilds sprint status from the event log and detects drift.

For research work, the evaluator is intentionally model-free. A model may write a human-readable judgement, but research nodes should not pass unless artifacts satisfy evidence and citation constraints.

Evidence is not decoration. It is the definition of completion.

---

## 9. Plugin framework

Code surface:

- `harness/lib/plugin_loader.py`
- `harness/schemas/plugin.schema.json`

Harness plugins live under `harness/plugins/<id>/manifest.yaml` and declare read/write scope, capabilities, commands, background behavior, evaluation packs, and rollback policy.

The public repo ships the framework. A plugin should be treated as usable only after its manifest exists and passes validation.

---

## 10. What the homepage should communicate

The homepage should not undersell Solar as only a multi-agent workflow. The stronger and more accurate framing is:

```text
Solar is an autonomous software organization runtime.
It compiles user intent into executable task structure.
It models AI workers as actors hosted on heterogeneous execution surfaces.
It schedules logical operators onto physical operators.
It closes work through evidence, not self-report.
It is designed to learn from outcomes and improve its own policies.
```

That is the technical identity of Solar.
