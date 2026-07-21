---
name: retro
namespace: builtin
status: stable
version: "1.0"
description: "Sprint retrospective — extract lessons, update STATE.md, write cortex entries"
tags: [retro, lessons, cortex]
min_score: 0.75
author: solar-harness
created_at: "2026-05-09T00:00:00Z"
---

# Skill: retro

Post-sprint retrospective: what worked, what failed, lessons extracted, STATE.md updated.

## Trigger

User says: `回顾`, `复盘`, `retro`, `/retro`

## Steps

1. **Read eval.md** — review all PASS/FAIL items from the sprint evaluator
2. **What worked** — list 2-3 things that went well
3. **What failed** — list FAIL items with root-cause (not symptoms)
4. **Lessons** — actionable rules extracted from failures
5. **Update STATE.md** — add to Progress.Done + Next Actions if needed
6. **Write cortex** — INSERT INTO cortex_sources for each lesson (credibility ≥ 0.8)
7. **Write sys_favorites** — if insight score ≥ 7

## Output format

```
## Worked
- ...

## Failed
- [item]: root-cause

## Lessons Extracted
1. [rule]: why it matters

## Cortex entries written: N
## STATE.md updated: yes/no
```

## Done when

All FAIL items have root-causes, ≥1 cortex entry written, STATE.md updated.
