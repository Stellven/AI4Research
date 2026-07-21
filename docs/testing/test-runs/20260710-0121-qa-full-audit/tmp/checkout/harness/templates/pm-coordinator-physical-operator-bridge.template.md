# PM Coordinator Template — Physical Operator + Bridge Monitor

## When To Use

Use this template for any non-trivial Mac mini `solar-harness multi-task` sprint that should be dispatched from Codex and monitored until acceptance evidence exists.

## Required Workflow

1. Write PRD, contract, and `task_graph.json`.
2. Every executable DAG node must declare either:
   - `preferred_operator`: exact physical operator id, or
   - `operator_selector`: task intent that the scheduler can map to an operator, or
   - a deliberate legacy `preferred_profile` fallback with a reason.
3. Dispatch the graph to Mac mini with `solar-harness multi-task start`.
4. Start a Mac mini-side monitor bridge for the graph.
5. Codex monitors by pulling bridge `latest.json` / `events.jsonl`, not by long local sleep loops.
6. If `reviewing` has valid handoff evidence, safe-mark the node passed.
7. If child graphs are all passed but a parent graph is still active, align the parent node and write a close-alignment report.

## Operator Fields

Every new operator record should include:

```json
{
  "display_name": "Human label",
  "plane": "headless",
  "owner_host": "solar@example-host",
  "pane": "solar-harness-multi-task:*",
  "profile": "builder",
  "role": "builder",
  "provider": "anthropic|google|local|zhipu|deepseek",
  "vendor": "Vendor name",
  "backend": "claude-cli|command|gemini-cli",
  "model": "model-id",
  "model_config": "short config string",
  "base_url": "native|http://127.0.0.1:8002|agy-cli",
  "command_path": "optional absolute command path",
  "auth_mode": "subscription|oauth|local|none",
  "key_ref": "reference only, never secret",
  "quota_cycle": "monthly|google-account|none",
  "quota_refresh_at": "unknown|N/A|timestamp",
  "quota_guard_state": "ok",
  "enabled": true,
  "available": true,
  "health_status": "ok",
  "input_modalities": ["text"],
  "output_modalities": ["text"],
  "task_classes": ["implementation"],
  "preferred_for": ["implementation"],
  "avoid_for": [],
  "cost_tier": "low|medium|high",
  "latency_tier": "low|medium|high",
  "context_tier": "low|medium|high",
  "max_concurrency": 1,
  "fallback_profile": "builder"
}
```

## DAG Node Examples

Exact operator:

```json
{
  "id": "N1",
  "goal": "Run image analysis on the screenshot",
  "preferred_operator": "mini-antigravity-gemini35-flash-image",
  "read_scope": ["/path/to/screenshot.png"],
  "write_scope": ["/path/to/handoff.md"],
  "acceptance": ["image content described with evidence"]
}
```

Selector:

```json
{
  "id": "N2",
  "goal": "Extract knowledge from design documents",
  "operator_selector": {
    "task_type": "knowledge-extraction",
    "cost_ceiling": "low"
  },
  "read_scope": ["/path/to/docs"],
  "write_scope": ["/path/to/handoff.md"],
  "acceptance": ["knowledge artifacts written", "no Claude used for bulk extraction"]
}
```

## Bridge Monitor Command

Run on Mac mini:

```bash
tmux new-window -d -t solar-harness -n bridge-<short-name> \
  "python3 ~/.solar/harness/tools/solar_monitor_bridge.py \
    --graph ~/.solar/harness/sprints/<sid>.task_graph.json \
    --name <short-name> \
    --interval 15 \
    --stale-sec 300"
```

Codex pulls:

```bash
ssh solar@example-host \
  'cat ~/.solar/harness/run/monitor-bridge/<short-name>.latest.json; tail -20 ~/.solar/harness/run/monitor-bridge/<short-name>.events.jsonl'
```

## Safe推进 Rules

- Allowed: mark `reviewing` as `passed` when handoff exists and acceptance is met.
- Allowed: start next ready node once.
- Allowed: align parent node when child graph is fully passed.
- Disallowed: kill unknown processes, delete task directories, print secrets, or silently switch operator.

## Closeout Evidence

Final report must list:

- graph path
- bridge latest path
- events path
- changed files
- test commands
- operator selection evidence
- known warnings and next sprint candidates
