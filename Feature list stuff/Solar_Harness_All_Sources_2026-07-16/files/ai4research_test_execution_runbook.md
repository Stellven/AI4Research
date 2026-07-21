# Test Execution Runbook for AI4Research Coding-Agent Audit

Use this runbook with the QA workbook and control DOCX. The runbook defines a safe, staged execution order. Commands are examples; the coding agent must adapt exact paths to the checked-out repo and record every command in `command-log.tsv`.

## Phase 0 — Establish immutable repo state

```bash
git status --short
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git remote -v
```

Write results to:

```text
docs/testing/test-runs/<timestamp>-full-audit/repo-state.txt
```

## Phase 1 — Environment discovery

```bash
uname -a
python3 --version
node --version || true
bun --version || true
git --version
bash --version | head -1
tmux -V || true
jq --version || true
```

Write results to `environment.json` and note missing tools as `SKIPPED_ENV` where relevant.

## Phase 2 — Static inventory validation

The agent should compare the workbook feature taxonomy against the repo checkout.

Recommended scans:

```bash
git ls-files > artifacts/tracked-files.txt
find . -name '*.py' -o -name '*.sh' -o -name '*.ts' -o -name '*.js' -o -name '*.json' -o -name '*.yml' -o -name '*.yaml' > artifacts/source-files.txt
```

Inventory targets:

- Python functions/classes and CLI subcommands
- Shell scripts and shell functions
- TypeScript/JavaScript exports and package scripts
- JSON/YAML schemas, workflow nodes, route configs, component manifests
- Markdown skill files and slash-command surfaces
- GitHub Actions jobs
- Existing test files and test cases

Outputs:

```text
function-inventory.csv
feature-entrypoint-map.csv
existing-test-map.csv
missing-test-plan.csv
```

## Phase 3 — Unit and schema/gate tests

Run deterministic tests first. No network or real credentials.

Examples:

```bash
python3 -m pytest harness/plugins/autosci/tests -q
python3 -m pytest harness/tests/evaluators/scientific -q
```

For schema/gate tests, use valid and invalid fixtures. Expected result may be `PASS`, `FAIL`, or `INCONCLUSIVE_EXPECTED` depending on the feature criteria.

## Phase 4 — Fixture integration tests

Use isolated fixtures and temp output roots.

```bash
TMPDIR="$(mktemp -d)"
export HARNESS_DIR="$TMPDIR/harness"
export SOLAR_AUTOSCI_OUTPUT_HARNESS="$TMPDIR/harness"
mkdir -p "$HARNESS_DIR"
```

Run AutoSci bridge actions and harness commands only against temp paths. Never use real `~/.solar` or `~/.claude`.

## Phase 5 — Installer / lifecycle tests in isolated HOME

```bash
TMPHOME="$(mktemp -d)"
export HOME="$TMPHOME/home"
export SOLAR_HOME="$TMPHOME/solar"
export CLAUDE_DIR="$TMPHOME/claude"
mkdir -p "$HOME" "$SOLAR_HOME" "$CLAUDE_DIR"

./install.sh --dry-run --yes --components kernel,harness,autosci
./install.sh --yes --components kernel,harness,autosci --solar-home "$SOLAR_HOME" --claude-dir "$CLAUDE_DIR"
"$SOLAR_HOME/bin/solar" doctor --json
```

Classify failures carefully. If a platform dependency is missing, use `SKIPPED_ENV` only when the failure is correctly diagnosed and documented.

## Phase 6 — Approval-gated dry-run and blocked-path tests

For gated routes, a correct result may be blocked/inconclusive with a continuation request.

Check for:

- no protected side effect executed
- approval request or side-effect access request emitted
- status is structured, not a raw crash
- limitations are visible
- feature ID and evidence path are recorded

## Phase 7 — Optional live-provider/manual tests

Only run when the user explicitly approves. These may include network/provider discovery, remote execution, browser rendering, email delivery, or full desktop packaging.

Each live-provider test must record:

- approval reference
- provider used
- credentials mode without leaking secrets
- before/runtime/after artifacts
- exact command and output
- whether result is live evidence or only partial evidence

## Phase 8 — Final report generation

Write:

```text
final-report.md
feature-results.csv
pass-fail-results.csv
command-log.tsv
```

The final report must use the DOCX template and cite evidence paths for every failure, blocked expected result, and inconclusive result.
