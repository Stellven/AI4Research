# Product Brief — 通过 Browser Agent 前门研究后再编译 requirement package。

**Source**: codex-pm-router
**Priority**: P1
**Lane**: delivery
**Handoff To**: planner

## Intent

通过 Browser Agent 前门研究后再编译 requirement package。

## Problem

通过 Browser Agent 前门研究后再编译 requirement package。

## Acceptance Criteria

- PRD、contract、TaskDAG 互相对齐。
- 实施、验证、兼容/发布路径均已显式表达。
- 每条验收标准都能追溯到验证或 gate。

## Non-Goals

- 不在首批交付中做完整四区 PM pane 重构。
- 不绕过 planner 直接进入 builder。

## Stop Rules

- 缺少可验证 acceptance 不得标记为完成。
- 缺少 verifier 决策不得进入 DONE。

## Context / Notes

Requirement Compiler produced canonical IR, compiled contracts, and a task DAG proposal.

## Research Artifact Inputs

- path: /tmp/frontdoor-research.json
- project_name: 需求研究-2026-05
- conversation_id: conv-frontdoor-002
- source_url: https://chatgpt.com/c/conv-frontdoor-002
