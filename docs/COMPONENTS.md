<!-- GENERATED FILE — do not edit by hand.
     Regenerate with: ./scripts/gen-components-doc.sh
     Source of truth: components.d/<name>/component.sh -->

# Solar Components

Solar installs as selectable components. The default selection is `kernel` +
`harness`, plus `core-runtime` when `bun` is available; everything else is
opt-in. Select components with `./install.sh --components <list>` (see
[`INSTALL.md`](../INSTALL.md)).

`Default` is `on` (always selected), `auto` (selected when its required
binaries are present), or `off` (opt-in). `Platforms` of `all` means macOS,
Linux, and WSL2.

| Component | Default | Platforms | Requires (bins) | Requires (components) | MCP | Description |
|---|---|---|---|---|---|---|
| `kernel` | on | all | `python3` | — | no | Claude Code kernel overlay with namespaced rules, hooks, and agents |
| `core-runtime` | auto | all | `bun` | — | no | TypeScript core runtime, daemon, and web dashboard |
| `harness` | on | all | `python3` | — | no | Python harness runtime payload |
| `skills-md` | off | all | — | — | no | Generic markdown skills for Claude Code discovery |
| `skills-office` | off | all | — | — | no | Office productivity skills (email, notes, tasks, notion, trello) |
| `skills-obsidian` | off | all | — | — | no | Obsidian vault skills |
| `skills-calendar` | off | darwin | — | — | no | macOS Calendar skills (darwin only) |
| `skills-browser` | off | all | `cargo` | — | no | Browser automation skills (cargo-gated at runtime) |
| `codex-bridge` | off | all | — | — | no | Optional file-based handoff bridge for external coding agents |
| `mempalace` | off | darwin linux wsl | `python3` | `kernel` | yes | Semantic memory MCP server (off by default) |
| `daemons` | off | darwin linux wsl | `bun` | `core-runtime` | no | User-level daemon for the Solar runtime (off by default) |

## Required configuration

Some components need a value supplied with `--set KEY=VALUE` (or the
`SOLAR_<KEY>` environment twin). In non-interactive mode a missing
required value fails with the exact `--set` remedy.

- `mempalace` requires `VAULT_PATH` (required) — Path to knowledge vault
