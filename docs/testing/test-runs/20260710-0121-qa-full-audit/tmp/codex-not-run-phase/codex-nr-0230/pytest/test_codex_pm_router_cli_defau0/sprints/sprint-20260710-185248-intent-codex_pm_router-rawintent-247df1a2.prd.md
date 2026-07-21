# 把 codex_pm_router 入口接到 RawIntent 主链。

## Goal
把 codex_pm_router 入口接到 RawIntent 主链。

## Context
基于当前请求直接定位到局部改动范围。

## Scope
- 把 codex_pm_router 入口接到 RawIntent 主链。

## Non-goals
- 不做无关架构重写。
- 不默认引入新的生产依赖。

## Acceptance Criteria
- 目标变更在声明范围内完成。
- 至少一条测试/执行证据被记录。
- 存在独立 verifier 决策。

## Validation
- 运行测试或 smoke check
- 记录 diff / 风险 / 验证证据

## Rollback
如验证失败，回退到变更前状态并保留失败证据。
