# Product Brief — 把 codex_pm_router 入口接到 RawIntent 主链。

**Source**: codex-pm-router
**Priority**: P2
**Lane**: delivery
**Handoff To**: planner

## Intent

把 codex_pm_router 入口接到 RawIntent 主链。

## Problem

把 codex_pm_router 入口接到 RawIntent 主链。

## Acceptance Criteria

- 目标变更在声明范围内完成。
- 至少一条测试/执行证据被记录。
- 存在独立 verifier 决策。

## Non-Goals

- 不做无关架构重写。
- 不默认引入新的生产依赖。

## Stop Rules

- 缺少可验证 acceptance 不得标记为完成。
- 缺少 verifier 决策不得进入 DONE。

## Context / Notes

Requirement Compiler produced canonical IR, compiled contracts, and a task DAG proposal.
