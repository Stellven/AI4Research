---
name: ship
namespace: builtin
status: stable
version: "1.0"
description: "Release — checklist-driven final verification before pushing/merging"
tags: [release, checklist, deploy]
min_score: 0.8
author: solar-harness
created_at: "2026-05-09T00:00:00Z"
---

# Skill: ship

Pre-release checklist execution: tests green, secrets clean, docs updated, no regressions.

## Trigger

User says: `发布`, `上线`, `ship`, `/ship`

## Checklist

- [ ] All tests pass (unit + integration)
- [ ] `gitleaks detect` 0 findings
- [ ] CHANGELOG / release notes updated
- [ ] `solar-harness product snapshot` taken pre-deploy
- [ ] `solar-harness doctor` verdict=ok
- [ ] No TODO/FIXME in changed files
- [ ] Peer review approved (or solo with explicit waiver)

## Stop conditions

- Any secret found in diff → quarantine + stop
- Test failure → stop, do not push
- doctor verdict != ok → stop

## Done when

All checklist items pass and push/merge executes without error.
