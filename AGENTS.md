# Contributor Guide

This repository is being prepared for a community-distributable OpenSolar
package. `AGENTS.md` is a contributor-facing guide for coding agents and
maintainers working in this repo. It is not an installed runtime artifact.

## Source of Truth

- Read `MIGRATION_PLAN.md` before migration work.
- Read `WORKLOG.md` before resuming an in-progress local task.
- Do not regenerate, restructure, or reinterpret the migration plan during
  implementation. If the plan conflicts with verified repository facts, record
  the mismatch in `WORKLOG.md` and stop only when the conflict blocks the
  current task.

## Scope

- This migration is packaging work, not a rewrite.
- Keep `core/` TypeScript, `harness/` Python, and skill internals unchanged
  unless the migration plan explicitly names the edit.
- Solar's shipped runtime remains a Claude Code overlay. Do not introduce
  product behavior that assumes this coding agent is the runtime engine.
- Optional bridges and experimental integrations stay component-gated and off
  by default unless the plan says otherwise.

## Local Workflow

- Work on `pkg/migration` unless the user asks for a different branch.
- Local commits are allowed when a scoped task has been verified.
- Do not push branches, tags, or commits without explicit user approval.
- Keep `MIGRATION_PLAN.md` and `WORKLOG.md` as local working documents unless
  the user explicitly asks to publish them.
- One task should map to one commit. Use workstream-prefixed messages such as
  `WS1: repair package manifest`.

## Safety Rules

- Never touch the real `$HOME` during install or uninstall tests. Use a sandbox
  home such as `HOME=$(mktemp -d)`.
- Do not run destructive git operations or history rewrites without explicit
  user approval.
- Before committing, inspect `git status` and stage only files changed for the
  current task.
- Before committing new or modified files, run the repository privacy scan
  described in the migration plan and fix any newly introduced matches.

## Verification

- Prefer automated checks over judgment calls.
- Record meaningful command results and gate status in `WORKLOG.md`.
- If a required check cannot run, record the reason and keep the task marked as
  unverified until the missing check is addressed.
