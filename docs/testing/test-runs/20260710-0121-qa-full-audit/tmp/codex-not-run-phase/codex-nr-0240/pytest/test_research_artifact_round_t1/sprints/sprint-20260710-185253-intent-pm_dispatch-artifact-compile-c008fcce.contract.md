# Compiled Contract — pm_dispatch 入口的研究 artifact 必须出现在 compiled package。

## Canonical Sources

- `requirement_ir.json` is the source of truth.
- `contracts/*.yaml` are canonical structured contracts.
- `.contract.md` is a compiled human-readable view.

## Product Contract

- goal: pm_dispatch 入口的研究 artifact 必须出现在 compiled package。
- success_metrics:
  - paper/source inventory 完整可追溯。
  - claim -> evidence -> implication 映射完整。
  - 研究结论具备 adoption/rejection criteria。
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

- hypothesis: pm_dispatch 入口的研究 artifact 必须出现在 compiled package。
- source_papers:
- rejection_criteria:
  - No evidence ledger available
  - No verifier/critique gate
