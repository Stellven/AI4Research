# Codex Core Entrypoints

Solar Core is now Codex-first at the project entrance, while Solar Harness keeps
the same intake, intent capture, intent consume, planning, scheduling, lease,
dispatch, and evidence interfaces.

## Boundary

```text
Codex App / Codex CLI / iMessage / Gmail / Telegram
  -> source adapter
  -> CoreToHarnessRequest or solar-harness intake
  -> RawIntent + Requirement IR
  -> Harness planner / TaskGraph / operator runtime
```

Core owns source normalization and Core-side intent interpretation. Harness owns
durable compilation, scheduling, physical operator binding, runtime state, and
evidence gates.

## Codex App

Use the Codex App by opening this repository as the active workspace and asking
Codex to submit the user request through Solar Core. The workspace policy in
`AGENTS.md` makes Codex the active Core surface and forbids direct `claude -p`
execution from Core.

For project work that should enter Harness, Codex should use one of these paths:

- `core/harness/submitCoreToHarness()` when a TypeScript source adapter has rich
  source metadata.
- `bash scripts/solar-codex-intake.sh "request"` when the Codex session needs a
  direct CLI-style RawIntent submission.

## Codex CLI

Interactive Codex CLI session:

```bash
cd /path/to/OpenSolar
codex "请把这个需求通过 Solar Codex Core 提交到 Harness: <需求文本>"
```

Direct RawIntent submission from the shell:

```bash
cd /path/to/OpenSolar
bash scripts/solar-codex-intake.sh --source codex_cli --no-dispatch --json "<需求文本>"
```

The wrapper uses the existing Harness runtime. Resolution order is
`SOLAR_HARNESS_DIR`, `HARNESS_DIR`, `~/.solar/harness`, then repository
`harness/` as a development fallback.

Dry run without writing Harness state:

```bash
bash scripts/solar-codex-intake.sh --dry-run --no-dispatch --json "<需求文本>"
```

## Core To Harness Schema

The typed Core-side ABI is defined in `core/harness/types.ts`:

- hard fields map to existing `intent_gateway.py capture` flags:
  `request_id`, `source.channel`, `source.actor`, `source.source_trust`,
  `workspace.repo`, `routing.mode`, `routing.urgency`;
- soft fields are rendered into a Markdown envelope by
  `core/harness/markdown-envelope.ts`;
- `core/harness/harness-client.ts` submits the envelope to
  `intent_gateway.py capture` and optionally calls `intent_consumer.py consume`.

This keeps heterogeneous entrance capability intact: source identity changes,
but the Harness-facing protocol remains RawIntent and Requirement IR.

## Existing Source Adapters

The active listener path keeps accepting multiple source channels:

- `core/listeners/imessage-listener.ts`
- `core/listeners/gmail-listener.ts`
- `core/listeners/telegram-listener.ts`
- `core/listeners/message-ingester.ts`
- `core/listeners/message-executor.ts`

Those sources converge at Core, then submit to Harness instead of directly
executing Claude.
