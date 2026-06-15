# Your First Solar Session

This guide assumes you are installing the default working product:
`kernel,harness`. Exact timestamps, sprint IDs, paths, and model names can vary.

Solar uses English commands, but some harness/runtime output still contains
Chinese labels because the v1.0 persona is Chinese-first.

## 1. Install And Check Health

Command:

```bash
curl -fsSL https://raw.githubusercontent.com/suraj-subrahmanyan/OpenSolar/v1.0.0-rc.3/get-solar.sh | bash -s -- --yes --components kernel,harness
export PATH="$HOME/.solar/bin:$PATH"
solar doctor
solar status
```

Expected `solar doctor` output:

```text
OpenSolar doctor
  [     ok] solar_home  /home/you/.solar
  [     ok] receipt     /home/you/.solar/install-receipt.json
  [     ok] claude_dir  /home/you/.claude
  [     ok] kernel      /home/you/.claude/solar/SOLAR.md
  [     ok] db          /home/you/.solar/db/solar.db
  [     ok] solar_bin   /home/you/.solar/bin/solar
  schema_version: 0
Verdict: ok
```

Expected `solar status` output:

```text
OpenSolar status
Install
  health: ok
  version: 1.0.0-rc.3
  channel: v1.0.0-rc.3
  components: kernel,harness
Runtime
  harness: installed
  tmux product_delivery: absent (...)
  coordinator: not-running
Daemon
  component: not-installed
  state: not-installed
```

`Daemon component: not-installed` is normal for the default install. Add
`core-runtime` or `daemons` only when you want that optional runtime surface.

## 2. Open The Cockpit And Submit Work

First check launch dependencies:

```bash
solar harness preflight
```

Expected output:

```text
Solar Harness launch preflight
required ok: bash>=4 path=/usr/bin/bash (...)
required ok: python3 path=/usr/bin/python3
required ok: tmux path=/usr/bin/tmux
required ok: claude path=/path/to/claude
required ok: jq path=/usr/bin/jq
required ok: harness dir writable (/home/you/.solar/harness)
manual-pending: live Claude pane behavior is not verified by preflight; after tmux opens, press Enter in each pane and resolve Claude trust/auth/quota prompts.
```

If a required line says `required fail`, install that tool and re-run preflight.

Open the Product Delivery cockpit:

```bash
solar harness start /path/to/project
```

Expected result:

```text
[Harness] ...
```

A `tmux` session named `solar-harness` opens with the Product Delivery panes.
Resolve any Claude Code trust, login, or quota prompts inside the panes. In a
second terminal, confirm the layout:

```bash
solar status
```

Expected runtime section after the cockpit exists:

```text
Runtime
  harness: installed
  tmux product_delivery: present (solar-harness)
  coordinator: alive pid=...
```

Submit a natural-language task:

```bash
solar harness intake "Add a failing parser test, fix the parser, and show the test evidence."
```

Expected first lines:

```text
Sprint created: sprint-...
RawIntent consumed: intent-... (consumed)
Planner handoff: ...
[Harness] Raw intake: /home/you/Knowledge/_raw/solar-harness/intake/intake-...md
```

If the panes are live and Claude is ready, Solar can dispatch into the harness
runtime. If Claude is not trusted, unauthenticated, or rate-limited, `solar
status` and `solar harness status` will show the manual boundary instead of
claiming live work was completed.

## 3. Choose The Main Model

Inspect the current routing:

```bash
solar harness models show
```

Expected output:

```text
┌────────────────────┬──────────────────────────────────────────────┐
│ 配置项             │ 当前值                                       │
├────────────────────┼──────────────────────────────────────────────┤
│ main pm            │ opus                                         │
│ main planner       │ opus                                         │
│ main builder       │ opus                                         │
│ main evaluator     │ opus                                         │
│ lab matrix         │ glm,glm,glm,anthropic-sonnet                 │
└────────────────────┴──────────────────────────────────────────────┘
```

Switch the main Product Delivery panes to a supported alias:

```bash
solar harness models set-main anthropic-sonnet --apply
```

Expected output:

```text
[Harness] 已写入主屏模型: pm/planner/builder/evaluator -> anthropic-sonnet
[Harness] 已按配置刷新 Product Delivery 四分屏
```

If no cockpit is running, omit `--apply`, then start or restart the harness:

```bash
solar harness models set-main anthropic-sonnet
solar harness start /path/to/project
```

## Stop The Session

```bash
solar harness kill
solar status
```

Expected status after stopping:

```text
Runtime
  tmux product_delivery: absent (...)
  coordinator: not-running
```
