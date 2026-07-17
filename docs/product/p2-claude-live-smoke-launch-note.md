# P2 Claude Live Smoke Launch Note

Date: 2026-07-07

`scripts/live-claude-e2e-isolated.sh` is the deterministic launch wrapper for
the supervised Claude/Anthropic P2 smoke. It is the Claude twin of the Codex
wrapper, but it does not run unless `SOLAR_LIVE_E2E_ALLOW=1` is set.

Deterministic preflight scope:

- Builds a fresh sandbox HOME and archived harness from the checked-out commit.
- Exposes host `$HOME/.claude/.credentials.json` as
  sandbox `$HOME/.claude/.credentials.json` by symlink only; token contents are
  never read or printed.
- Pins sandbox `e2e.env` to `SOLAR_PANE_RUNTIME=claude`,
  `SOLAR_PM_DEFAULT_PROVIDERS=anthropic`, and
  `SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=anthropic`.
- Bakes product flags into sandbox `e2e.env`: `SOLAR_GATE_LEDGER=1`,
  `SOLAR_PRODUCT_MODE=1`, and `SOLAR_WORKFLOW_ROUTER=1`.
- Runs `run_preflight.py --providers anthropic --contract
  harness/config/workflows/code.cli_smoke_anthropic.workflow.json` before any
  `/intake` submission.
- Asserts the required Claude operator registry entries are Anthropic-backed:
  `mini-claude-opus-planner-print`, `mini-claude-sonnet-builder-2`, and
  `mini-claude-sonnet-evaluator-print`.

Live Claude execution is intentionally out of scope for this commit. The
script exits after deterministic preparation with `--prepare-only`, and without
`SOLAR_LIVE_E2E_ALLOW=1` it preserves evidence but does not spend Claude quota.
