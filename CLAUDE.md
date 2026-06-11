# OpenSolar Contributor Guide

This file is public guidance for Claude Code or other coding agents working in
this repository checkout. It is not the installed Solar runtime kernel. The
installer generates the runtime kernel under `~/.claude/solar/SOLAR.md` and
keeps runtime state under `~/.solar/`.

For repository work, prefer `AGENTS.md` as the detailed maintainer guide. Keep
this file small, public-safe, and aligned with the shipped tree.

## Project Boundary

- OpenSolar is being packaged as a community-distributable installer and runtime.
- Packaging work should preserve the existing product behavior unless a task
  explicitly asks for a product change.
- The shipped runtime remains a Claude Code overlay plus the Solar runtime
  under `~/.solar/`.
- Experimental or optional integrations should remain component-gated and off
  by default unless their component manifest says otherwise.

## Working Rules

- Work on the branch and scope requested by the owner.
- Keep each change focused on one concern.
- Stage explicit paths only; do not use broad staging such as `git add -A`.
- Do not commit local-only planning or worklog files unless the owner explicitly
  asks to publish them.
- Never run release/orphan cut commands or push release refs unless the owner
  explicitly approves that action.
- Do not introduce personal paths, account handles, secrets, tokens, or
  machine-local defaults into tracked files.

## Repository Areas

- `components.d/` defines installable components.
- `kernel/` contains source material for the generated Claude Code kernel.
- `harness/` contains the local runtime, coordinator, tests, and operator
  control-plane code.
- `core/` contains TypeScript runtime support.
- `scripts/` contains packaging, privacy, install-matrix, and release gates.
- `docs/` contains public documentation and release notes.

## Verification

Run checks that match the files you changed. Common gates are:

```bash
git diff --check
bash scripts/check-privacy.sh
bash scripts/check-installed-clean.sh
bash scripts/smoke-install-matrix.sh minimal
bash scripts/release-cut.sh --source HEAD
```

Private migration branches may need owner-provided release-cut inputs before the
public tree is cut. Public contributor docs must not depend on local-only
release files being present.

For harness runtime launch work, also run:

```bash
bash scripts/check-harness-plumbing.sh
```

That smoke is deterministic harness plumbing, not live Claude behavior. It can
verify install/layout/preflight/coordinator and dispatch artifact plumbing
without consuming Claude quota. Live Claude panes and real delegation results
must be verified manually when Claude auth/quota is available.

## Release Safety

Before any public cut, the release dry run must pass and gitleaks must actually
run. The release cut is a manual owner action: do not create orphan branches,
push release refs, or publish release assets from an ordinary cleanup task.
