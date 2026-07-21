---
name: plan
namespace: builtin
status: stable
version: "1.0"
description: "Sprint planning — translate user intent into sliced PRD + implementation plan"
tags: [planning, sprint, prd]
min_score: 0.8
author: solar-harness
created_at: "2026-05-09T00:00:00Z"
---

# Skill: plan

Turn user intent into a structured PRD, slice topology, and per-slice dispatch plan.

## Trigger

User says: `写计划`, `制定计划`, `/plan`, `Sprint planning`

## Steps

1. **Clarify intent** — ask for outcomes, constraints, timeline if missing
2. **Draft PRD** — Non-Negotiables, Target Architecture, Deliverables, Gates
3. **Slice topology** — identify independent write scopes; draw dependency DAG
4. **Per-slice spec** — Owner, Done conditions, Stop conditions, Round-retry trigger
5. **Gate checklist** — G0..Gn with fail action
6. **Write plan.md** — persisted to sprint directory

## Output format

```
## 0. Slice Topology (DAG)
## 1. Slice Specs (S0..Sn)
## 2. Product Gates (table)
## 3. Risk Register
## 4. Rollback Plan
```

## Done when

- plan.md passes schema gate (变更文件列表 + 技术方案 sections present)
- All slices have exclusive write scopes with no overlap
- Gate fail actions are specific (stop / rollback / no-release)
