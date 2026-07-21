# DRAFT — Upstream Source-Export Request (for owner to forward)

> **Status: DRAFT. Do not send as-is.** This note is prepared for the project
> owner to forward through their direct supervisor. It is framed for the whole
> team, not a single contributor: the items below are the last source-level
> gaps blocking a clean, community-distributable OpenSolar package, and
> resolving them benefits every downstream consumer, not just this fork.

## Context

The community-packaging effort has reached a working, CI-verified state: a
stranger on a fresh macOS or Linux machine can install, doctor, and cleanly
uninstall Solar, with the daemon and web dashboard booting as gated checks.
Two source-level gaps remain that the packaging work cannot resolve on its own
because the source was never part of the public extraction. We request an
export of the following, under a redistribution-compatible license.

## Request 1 — TVS (terminal rendering stack)

**What:** the `tvs` package, specifically the `termplane` rendering core and
its `llm` submodule (the modules imported as `tvs/termplane/render/*`,
`tvs/termplane/sdk/*`, and `tvs/termplane/llm`).

**Why:** the terminal-UI surfaces (`core/ui/**`, the daemon UI watcher, the
agent-dashboard TUI, and the harness terminal renderer) import TVS directly.
TVS source is not in the repository and carries no redistribution grant, so
these surfaces currently ship only as an optional component gated behind a
user-supplied `SOLAR_TVS_ROOT`. The web dashboard already covers the required
dashboard gate TVS-free, so this is not a blocker for core runtime — but
without a license grant the terminal-UI experience cannot be redistributed at
all.

**If granted:** TVS is vendored as a workspace package, the optional
terminal-UI component folds into the default runtime, and a TUI render smoke
test joins CI. **If not granted:** the terminal-UI component stays optional and
TVS is never redistributed.

## Request 2 — Originals of three daemon-imported modules

**What:** the upstream originals of three modules the daemon imports that were
absent from the public extraction:

| Module path | Role |
|---|---|
| `core/daemon/skill-dispatcher` | resolves and dispatches installed skills |
| `core/orchestrator/*` (`index`, `types`, `retry-policy`) | task-graph construction, execution, retry policy, control surface |
| `core/config/privacy` | contact/identity configuration accessor |

**Why:** the daemon failed to boot without them. To make the daemon real and
bootable, the packaging effort authored minimal compatibility implementations,
each marked in its file header as a compatibility implementation pending the
upstream original, and documented as such in the contributor guide. They are
deliberately scoped to only what the daemon needs to boot and serve — they do
not reproduce the real scheduling, dispatch, or privacy behavior.

**If granted:** the compatibility modules are swapped for the upstream
originals wholesale. **If not granted:** the compatibility modules remain as
the provisional, clearly-marked implementations they are today.

## What we are NOT requesting

No runtime data, no credentials, no personal configuration. Only source for the
modules above, under a license that permits redistribution in a community
package.

## Suggested handling

A source export (or a license grant plus a pointer to the modules) is
sufficient. If a redistribution license is not feasible for any item, a written
"optional, user-supplied" disposition for that item lets the package ship
around it cleanly.
