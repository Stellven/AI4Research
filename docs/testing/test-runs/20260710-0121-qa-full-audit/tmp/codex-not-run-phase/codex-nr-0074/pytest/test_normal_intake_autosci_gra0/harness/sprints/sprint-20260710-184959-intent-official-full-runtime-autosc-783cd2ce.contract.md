# Compiled Contract — Official full-runtime AutoSci integration test through normal solar intake. Do n

## Canonical Sources

- `requirement_ir.json` is the source of truth.
- `contracts/*.yaml` are canonical structured contracts.
- `.contract.md` is a compiled human-readable view.

## Product Contract

- goal: Official full-runtime AutoSci integration test through normal solar intake. Do not call a
- success_metrics:
  - Normal Solar intake emits a research.autosci.v1 task graph.
  - Scientific* nodes resolve to AutoSci research capsules and autosci-* physical operators.
  - Autopilot can dispatch ready graph nodes without a manual AutoSci shim call.
- non_goals:
  - 不把论文总结直接当作实现结论。
  - 不在缺证据时进入生产实现。

## Interface Contract

- name: RequirementCompilerAdapters
- version: 1.0
- invariants:
  - Requirement IR is the only source of truth.
  - DAG nodes[*].id must be unique.
  - Every acceptance criterion maps to at least one validation step.

## Agent Execution Contract

- allowed_paths:
  - apps/pm-pane/**
  - packages/requirement-ir/**
  - harness/**
- forbidden_paths:
  - infra/prod/**
  - .env*
  - secrets/**
- approval_required_when:
  - new production dependency
  - database migration
  - network access
  - touching auth or billing
- stop_conditions:
  - 缺少可验证 acceptance 不得标记为完成。
  - 缺少 verifier 决策不得进入 DONE。
  - 缺少 evidence ledger 或 critique gate 时不得推进到 adoption。

## Research Contract

- hypothesis: Official full-runtime AutoSci integration test through normal solar intake. Do not call a
- source_papers:
- rejection_criteria:
  - No evidence ledger available
  - No verifier/critique gate
