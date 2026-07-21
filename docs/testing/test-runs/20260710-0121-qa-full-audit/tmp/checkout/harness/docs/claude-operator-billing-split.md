# Claude Interactive vs Programmatic Physical Operator Billing Split Design

This document details the inventory of live Claude surfaces on the Mac mini executor, validates the local wrapper behavior, and defines the billing-aware operator routing and split policy.

Knowledge Context: `solar-harness context inject` used.

---

## 1. Context & Rationale

Anthropic's billing and limits split materially by surface:
- **Interactive Claude Code/CLI**: Subject to subscription limits (e.g., Pro or Team usage tiers).
- **Programmatic Print Mode (`claude -p` / `--print`) / Agent SDK**: Starting June 15, 2026, programmatic automation on subscription plans draws from a separate monthly Agent SDK credit (or usage/API credits), rather than the standard subscription limits.

To optimize resource allocation, prevent unexpected plan exhaustion, and properly isolate automated tasks from interactive development, Solar must treat interactive panes and print-mode automation as distinct physical operators with separate billing properties and scarcity levels.

---

## 2. Live Mac mini Surface & Wrapper Inventory

### 2.1. Live Process Classification Evidence
Active processes on the Mac mini distinguish the two execution modes clearly:
1. **Interactive Claude Code repls**:
   - Command: `claude` (without `-p` or `--print`)
   - TMUX pane current command: `claude` or running shell executing `claude`.
   - Running example from tmux list-panes:
     `solar-harness:1.0 ✳ Claude Code bash 71661` (associated with interactive user pane).
2. **Programmatic Print-Mode workers**:
   - Command: `claude ... -p <dispatch_content>` or `claude --print <dispatch_content>`
   - Running example from process list:
     `2091 2088 claude --permission-mode bypassPermissions --model sonnet --tools default --strict-mcp-config --mcp-config ~/.solar/harness/config/empty-mcp.json -p <!-- SOLAR_MULTI_TASK_DISPATCH -->...`

### 2.2. Wrapper Behavior Validation
The system wrapper located at `~/bin/claude` (resolving to `~/n/bin/claude`) has the following implementation:
```bash
#!/usr/bin/env bash
exec "~/.local/bin/claude" --dangerously-skip-permissions "$@"
```
- **Analysis**: The wrapper script acts as an arguments-transparent forwarder. It appends `--dangerously-skip-permissions` but does NOT force programmatic mode (does not inject `-p` or `--print` on its own).
- **Classifier Rule**: To classify a process executing via this wrapper, the runtime classifier must evaluate the arguments passed in `$@`.
  - If `$@` contains `-p` or `--print`, it is programmatic (`claude_print`).
  - If `$@` lacks `-p` and `--print`, it is interactive (`claude_code_interactive`).
  - If a custom wrapper script is encountered that hard-codes `-p` (e.g., contains `claude ... -p` inside the script body), the classifier must inspect the script contents to detect if programmatic mode is forced.

---

## 3. Configurable Billing Policy

To avoid hard-coding plan dollar amounts (such as $20, $100, or $200 tiers), the billing policy is designed as a metadata-driven configuration.

### 3.1. Logical Billing Pools
We define two logical pools:
1. `anthropic_subscription_interactive`: Linked to interactive surfaces under the user subscription.
2. `anthropic_agent_sdk_credit`: Linked to programmatic execution drawing from Agent SDK or usage credits.

### 3.2. Operator Catalog Schema Additions
Claude physical operators in `physical-operators.json` will be extended with:
- `surface`: `claude_code_interactive | claude_print | claude_sdk | claude_github_action`
- `billing_surface`: `subscription_interactive | anthropic_agent_sdk_credit | usage_credit | unknown`
- `billing_pool`: Logical pool identifier (e.g. `anthropic_subscription_interactive` or `anthropic_agent_sdk_credit`)
- `launch_cmd_kind`: `interactive_repl | print_once | sdk_call`
- `quota_policy`: Quota management rules:
  - `quota_type`: type of quota boundary (e.g. `subscription-limits`, `monthly-agent-credit`)
  - `reserve_for`: lists of task classes this operator is reserved for.

### 3.3. Configurable Limits Policy
A separate policy config or environment variables (e.g. `SOLAR_AGENT_SDK_CREDIT_LIMIT` and `SOLAR_AGENT_SDK_CREDIT_OBSERVED`) will track the actual credit spent without embedding assumptions in the codebase:
```json
{
  "billing_pools": {
    "anthropic_agent_sdk_credit": {
      "monthly_limit_usd": 100.0,
      "alert_threshold": 0.8,
      "on_exhausted": "disable_and_fallback"
    }
  }
}
```

---

## 4. Quota Broker Routing Policy

Since programmatic `claude_print` operators are scarce (subject to strict credit caps), they are treated as **reserve resources**.

### 4.1. Routing Constraints
- **Use-For List (Allowed high-value tasks)**:
  - `FINAL_REVIEW`
  - `ROOT_CAUSE_DEBUG`
  - `ARCH_DECISION`
  - `SMALL_HIGH_VALUE_BATCH`
- **Avoid-For List (Forbidden heavy/low-value tasks)**:
  - `FANOUT` (automated branch fanouts)
  - `BULK_EDIT` (heavy file rewrites)
  - `TEST_RUN` (iterative test executions)
  - `LOW_VALUE_SCAN` (broad repository searches)

### 4.2. Routing Algorithm Rules
When scheduling a DAG node:
1. Select operator by logical operator class and constraints, not by raw model string.
2. If `preferred_operator` points to a `claude_print` operator, check if the node's `task_type` or metadata matches any item in the `avoid_for` list. If it matches, reject routing and select the configured fallback (e.g. GoogleStack or LocalPrivacy).
3. Under high quota usage (observed credit > threshold), all non-critical tasks must fallback to cheaper non-reserve operators.

---

## 5. Observability and Verification Plan

### 5.1. Status Output Observability
The command `solar-harness multi-task status` will display:
- Detailed operator metadata including `surface` and `billing_surface`.
- Current availability of reserve pools.

### 5.2. Monitor Bridge JSON
`run/monitor-bridge/global.latest.json` will expose:
- `observed_claude_print_process_count`: Scanned process count of active `claude -p` or `claude --print` processes running on the Mac mini.
- Logical `billing_pool` state and current availability flags.

### 5.3. Verification Tests
- **Classifier unit tests**: Test argument lists containing `-p`, `--print`, or no print flags.
- **Wrapper content inspector tests**: Test detection on custom shell script wrappers.
- **Routing verification**: Assert that a node with `task_type: bulk_edit` is never assigned a `claude_print` operator, even if it is the only Claude operator enabled.
