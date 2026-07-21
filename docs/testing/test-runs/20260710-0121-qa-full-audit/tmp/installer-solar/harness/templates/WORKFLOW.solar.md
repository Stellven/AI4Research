---
tracker:
  kind: solar-sprint
  polling_interval_ms: 5000
workspace:
  root: "${SOLAR_SYMPHONY_WORKSPACE_ROOT}"
agent:
  max_concurrent_agents: 1
  max_retry_backoff_ms: 30000
codex:
  command: "codex"
  turn_timeout_ms: 120000
  stall_timeout_ms: 300000
hooks:
  global_timeout_ms: 120000
  pre_claim_workspace:
    command: "echo pre_claim_workspace sprint=$SPRINT_ID"
    timeout_ms: 30000
    on_failure: fail
  post_claim_workspace:
    command: "echo post_claim_workspace workspace=$WORKSPACE_DIR"
    timeout_ms: 30000
    on_failure: fail
  pre_release_workspace:
    command: "echo pre_release_workspace archiving proof"
    timeout_ms: 60000
    on_failure: continue
  post_release_workspace:
    command: "echo post_release_workspace cleanup done"
    timeout_ms: 30000
    on_failure: continue
---

# Solar Symphony Workflow

## Agent Instructions

### 1. Read Contract

Read the sprint contract file at `contract.md` in the workspace root.
Understand all Done criteria, constraints, and scope boundaries.

### 2. Execute Implementation

Implement the changes specified by the contract.
Follow all constraints listed in the contract.

### 3. Write Handoff

After implementation, write `handoff.md` to the workspace root containing:
- Summary of changes
- Changed files list
- How each Done criterion is satisfied (with evidence)
- Verification method (commands to run)
- Known risks and notes

### 4. Write Proof Artifacts

Write all proof artifacts to the `proof/` directory:
- `proof/run-request.md` — what was requested and what was done
- `proof/runner-env.json` — environment snapshot at execution time

### 5. Forbidden Actions

- **Do NOT** modify live tmux panes (solar-harness, solar-harness-lab) — no live pane mutation allowed
- **Do NOT** run `tmux send-keys`, `tmux respawn-pane`, `tmux kill-pane`, or `tmux kill-session`
- **Do NOT** modify files outside the workspace
- **Do NOT** hardcode API tokens or credentials
- **Do NOT** launch external processes without explicit `--unsafe-run-codex` flag
