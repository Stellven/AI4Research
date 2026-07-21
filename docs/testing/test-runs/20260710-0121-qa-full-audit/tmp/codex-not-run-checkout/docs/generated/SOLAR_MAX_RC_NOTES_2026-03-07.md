# Solar-MAX RC Notes (2026-03-07)

## Scope

本次收口聚焦于架构重整 Phase A-E 的稳定性与可回滚能力，重点修复 `smoke:core-policy` 的服务依赖不稳定问题。

## Key Changes

- `scripts/smoke-core-policy.ts`
  - 执行前自动调用 `scripts/ensure-background-services.sh`
  - 增加 core-policy API 就绪等待（重试 + 超时错误信息）
- `docs/generated/SOLAR_MAX_ARCH_REORG_EXEC_BOARD.md`
  - 追加稳定化与回归通过记录

## Verification (local)

- `bun run smoke:core-policy` -> PASS
- `bun run eval:orchestrator` -> PASS (`7/7`)
- `bun run eval:orchestrator:expanded` -> PASS (`30/30`, cost `$0.0038`)

## Rollback Anchors

- Rollback playbook:
  - `docs/generated/SOLAR_MAX_ROLLBACK_PLAYBOOK.md`
- Policy snapshot example:
  - `docs/generated/policy-snapshots/solar-max-core-policy-2026-03-07T10-46-45-669Z.json`

## Suggested Tag Commands

```bash
git add scripts/smoke-core-policy.ts docs/generated/SOLAR_MAX_ARCH_REORG_EXEC_BOARD.md docs/generated/SOLAR_MAX_RC_NOTES_2026-03-07.md
git commit -m "fix(orchestrator): stabilize core-policy smoke with background-service sync"
git tag v3.1.0-phaseE-rc1
```

> 说明：当前工作区包含大量无关改动，建议只对本次文件做精确暂存后再提交/打 tag。
