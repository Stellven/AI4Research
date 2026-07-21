# Product Brief — 新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。

**Source**: codex-pm-router
**Priority**: P2
**Lane**: delivery
**Handoff To**: planner

## Intent

新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。

## Problem

新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。

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
