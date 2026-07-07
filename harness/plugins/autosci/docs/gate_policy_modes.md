# AutoSci Gate Policy Modes

This document defines the policy-driven side-effect gate used by the Solar
AutoSci bridge. The default remains `strict_hitl`.

## Mode Matrix

| Mode | Proof | Auto side effects | Still blocked by default |
|---|---|---|---|
| `strict_hitl` | required | local reads and artifact writes only | wiki mutation, local commands, web serving, network, email, remote, destructive/config/credential mutation |
| `safe` | required | local reads and artifact writes only | wiki mutation, local commands, web serving, network, email, remote, destructive/config/credential mutation |
| `parity_demo` | required | sandbox wiki/artifact writes, allowlisted local commands, TeX compile, browser/server probe, PNG export | email, remote, destructive/config/credential mutation; network unless `SOLAR_AUTOSCI_ALLOW_NETWORK=1` |
| `unsafe_native` | best-effort | local writes, wiki mutation, local commands, web/server probe, network | email, remote, destructive/config/credential mutation unless explicit env opt-in |
| `autosci_native` | best-effort | all side effects are attempted without Solar gate blocking | none at the Solar gate layer |

## Risk Opt-In Environment Variables

| Side effect | Env |
|---|---|
| network fetch | `SOLAR_AUTOSCI_ALLOW_NETWORK=1` |
| email send | `SOLAR_AUTOSCI_ALLOW_EMAIL=1` |
| remote execution | `SOLAR_AUTOSCI_ALLOW_REMOTE=1` |
| destructive mutation | `SOLAR_AUTOSCI_ALLOW_DESTRUCTIVE=1` |
| protected config mutation | `SOLAR_AUTOSCI_ALLOW_PROTECTED_CONFIG=1` |
| credential mutation | `SOLAR_AUTOSCI_ALLOW_CREDENTIAL_MUTATION=1` |

## Mode Resolution

Resolution priority:

1. `envelope.inputs.gate_mode`
2. `envelope.inputs.autosci_mode`
3. `SOLAR_AUTOSCI_GATE_MODE`
4. optional config object passed to the policy layer
5. default `strict_hitl`

## Evidence

Actions that consult the policy should attach the serialized decision to:

- `outputs.policy_decision`
- `provenance.gate_policy`
- an optional `gate_policy_decision_json` sidecar

When a policy-connected action needs native side effects but the selected mode
does not allow them, the action should emit `autosci_side_effect_access_request.v1`
instead of treating the block as a terminal runtime failure. The request includes
an `autosci_side_effect_continuation.v1` object with retry patch options for a
bounded policy mode, native mode, or HITL approval evidence. Consumers should
surface that request and re-run the same envelope with an explicit access patch
when the user grants permission.

All AutoSci approval contracts should also carry
`autosci_gate_authorization_request.v1` when approval/runtime artifacts are
missing. Route-level shim gates carry `autosci_route_gate_authorization_request.v1`
only for blocked/schema-only route handoffs, route-only evidence with no
runnable action, or scheduler authorization waits.
Generic workflow-runner blocked nodes carry
`scientific_workflow_gate_authorization_request.v1` and return a successful
process exit for authorization-blocked lifecycles while preserving
`lifecycle_status=blocked`. Legacy research lifecycle smoke blocked nodes use
the same request schema; direct legacy smoke preserves its historical blocked
exit `3`, while shim-mediated `$research --scheduler-run` can opt into a
zero-exit authorization-blocked handoff. True failed gates, such as
configuration drift or production dispatch boundary failures, remain errors.

Auto-approved modes use a synthetic reference of the form:

```text
policy:auto:<mode>:<action>:<utc_timestamp>
```

This is not human approval. It records why the side effect was allowed.

## Current Bridge Coverage

In `strict_hitl`, existing approval/runtime evidence behavior is preserved. In
`parity_demo`, the bridge can generate synthetic policy approval evidence for
the bounded local side effects below:

| Action | Command surface | Parity side effect | Guardrail |
|---|---|---|---|
| `visualize_graph` | `$visualize --serve` | Runs `tools/serve.py --probe-server --port 0`, probes `/api/health`, then shuts down. | Loopback/server proof must still be attached as runtime evidence. |
| `compile_paper` | `$paper-compile --checklist` | Executes a discovered supported TeX executor (`latexmk`, `pdflatex`, `xelatex`, or `lualatex`) when available. | Synthetic allowlist is limited to TeX executors discovered on `PATH`; missing or invalid PDF output remains inconclusive. |
| `build_poster` | `$poster` | Executes a render/export command only when concrete `poster_render_command` or `poster_renderer` allowlist evidence is supplied. | The policy gate does not invent a browser renderer; absent render allowlist remains inconclusive. |
| `run_experiment` | `$exp-run --env local` | Executes a concrete allowlisted local experiment command and then applies the existing runtime/wiki mutation checks when approved. | Policy sidecar records plan handoff commands for audit but does not auto-allowlist them as executable commands; strict/safe blocks emit `autosci_side_effect_access_request.v1`. |
| `init_sources` | `$init --write` | Writes supplied provider/runtime source candidates into the local wiki papers, graph edges, log, index, and context brief. | Policy approval covers wiki fan-in only; it does not execute network/provider fetch, email, remote execution, or bulk ingest. |
| `reset_plan` | `$reset --scope ...` | Executes native `tools/reset_wiki.py` scoped reset when high-risk policy mode allows destructive mutation. | Default `strict_hitl`/`safe` remain blocked; completed execution must include before snapshot, reset runtime evidence, after snapshot, and mutation proof. |
| `setup_status` | `$setup --setup-dotenv-path ...` | Writes a supplied `.env` after-artifact to an explicit dotenv path when high-risk policy mode allows credential/config mutation. | Default `strict_hitl`/`safe` remain blocked; evidence records key names, snapshots, and hashes only, never secret values. |
| `daily_arxiv_prepare_finalize` | `$daily-arxiv` | Attempts live native `tools/daily_arxiv.py prepare` only when network side effects are policy-allowed; supplied verified runtime digest evidence can still complete without live execution. | Strict/safe missing-live paths emit `autosci_side_effect_access_request.v1`; email, scheduler, and auto-ingest still require typed delivery/ingest proof. |
| `generate_ideas` | `$ideate` | Applies approval-gated access semantics to explicit policy or real source/model/wiki/pilot side-effect paths; permissive modes may synthesize approval for implemented writeback paths. | Route policy is `approval_required`, not `dry_run_only`; bounded fixture smoke does not request access for side effects it did not attempt, and promotion still requires source, model, novelty/review, writeback, and pilot evidence. |
| `run_research_lifecycle` | `$research` | Records access-required lifecycle state when network, local command, wiki mutation, remote, or compile side effects are blocked. | The bridge does not fake stage execution; lifecycle completion still requires typed stage evidence or approved stage runners. |

Actions not listed here should not be assumed policy-connected until their
action-level evidence includes `outputs.policy_decision` or a gate policy
sidecar.

## Examples

Strict:

```bash
SOLAR_AUTOSCI_GATE_MODE=strict_hitl python3 harness/plugins/autosci/bin/autosci_bridge.py run --action visualize_graph --envelope artifacts/autosci/demo/visualize.envelope.json
```

Parity demo:

```bash
SOLAR_AUTOSCI_GATE_MODE=parity_demo python3 harness/plugins/autosci/bin/autosci_bridge.py run --action visualize_graph --envelope artifacts/autosci/demo/visualize.envelope.json
```

Native:

```bash
SOLAR_AUTOSCI_GATE_MODE=autosci_native python3 harness/plugins/autosci/bin/autosci_bridge.py run --action visualize_graph --envelope artifacts/autosci/demo/visualize.envelope.json
```

To return to the original behavior, unset `SOLAR_AUTOSCI_GATE_MODE` or set it
to `strict_hitl`.
