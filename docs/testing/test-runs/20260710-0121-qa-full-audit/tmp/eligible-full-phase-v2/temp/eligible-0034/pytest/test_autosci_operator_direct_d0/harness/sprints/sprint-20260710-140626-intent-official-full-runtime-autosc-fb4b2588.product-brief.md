# Product Brief — Official full-runtime AutoSci integration test through normal solar intake. Do n

**Source**: autosci-intake-contract
**Priority**: P1
**Lane**: strategy
**Handoff To**: builder_main

## Intent

Official full-runtime AutoSci integration test through normal solar intake. Do not call a

## Problem

Official full-runtime AutoSci integration test through normal solar intake. Do not call a manual autosci shim. The workflow must ingest papers, extract claims, generate ideas, run exp-design, exp-run, exp-eval, and produce a report.

## Acceptance Criteria

- Normal Solar intake emits a research.autosci.v1 task graph.
- Scientific* nodes resolve to AutoSci research capsules and autosci-* physical operators.
- Autopilot can dispatch ready graph nodes without a manual AutoSci shim call.

## Non-Goals

- 不把论文总结直接当作实现结论。
- 不在缺证据时进入生产实现。

## Stop Rules

- 缺少可验证 acceptance 不得标记为完成。
- 缺少 verifier 决策不得进入 DONE。
- 缺少 evidence ledger 或 critique gate 时不得推进到 adoption。

## Context / Notes

Normal intake selected the contract-bound AutoSci research lifecycle.
