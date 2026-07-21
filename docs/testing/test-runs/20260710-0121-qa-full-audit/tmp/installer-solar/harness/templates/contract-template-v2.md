---
name: {{name}}
description: {{description}}
summary: {{summary}}
triggers: [{{triggers}}]
---

# Sprint Contract — {{name}} ({{sprint_id}})
Created: {{created_at}}
Status: drafting
Phase: spec
Project: {{project_dir}}

## Summary

{{summary}}

## When to Use

### Use When
- (condition 1)
- (condition 2)
- (condition 3)

### Do NOT Use When
- (exclusion 1)
- (exclusion 2)
- (exclusion 3)

## Requirements

{{requirements}}

## Process

1. **Spec**: Define requirements and acceptance criteria
2. **Plan**: Design implementation approach and write `sprints/{{sprint_id}}.task_graph.json`
3. **Build**: Control plane dispatches ready DAG nodes in parallel
4. **Test**: Verify functionality
5. **Review**: Node evaluator checks each gate; parent evaluator checks all gates
6. **Ship**: Finalize and deliver

## Required Planning Artifacts

Planner must produce both files before handoff to builders:

- `sprints/{{sprint_id}}.plan.md` — human-readable execution plan
- `sprints/{{sprint_id}}.task_graph.json` — machine-readable DAG validated by:

```bash
~/.solar/bin/solar-harness graph-scheduler enrich-capabilities --graph ~/.solar/harness/sprints/{{sprint_id}}.task_graph.json --source ~/.solar/harness/sprints/{{sprint_id}}.contract.md --in-place
~/.solar/bin/solar-harness graph-scheduler validate --graph ~/.solar/harness/sprints/{{sprint_id}}.task_graph.json
```

Each task graph node must declare `id`, `goal`, `depends_on`, `write_scope`, `read_scope`, `required_skills`, `required_capabilities`, `preferred_model`, `gate`, `acceptance`, and `estimated_cost`. If planner cannot determine external capabilities manually, it must run `graph-scheduler enrich-capabilities` and keep the inferred `required_capabilities` in the graph.

Parallel dispatch rule: nodes can run together only when dependencies are passed and `write_scope` does not overlap. Missing `write_scope` is treated as exclusive and must not be parallelized.

## Definition of Done

- [ ] D1: (criterion)
  <!-- verify: cmd="" expected_exit=0 output_pattern="" -->
- [ ] D2: (criterion)
  <!-- verify: cmd="" expected_exit=0 output_pattern="" -->
- [ ] D3: (criterion)
  <!-- verify: cmd="" expected_exit=0 output_pattern="" -->

## Scope

### In Scope
- (item 1)
- (item 2)

### Out of Scope
- (item 1)
- (item 2)

## Red Flags

- **No mock/stub/TODO**: `grep -rE 'TODO|FIXME|mock|stub|模拟'` in implementation files must return empty
- **No hardcoded secrets**: `grep -rE 'password|secret|token|api.key' --include='*.sh' --include='*.ts' --include='*.py'` must return empty (excluding template placeholders)
- **No temp artifacts**: No important outputs stored in /tmp

## Constraints

> Planner fills in

## Implementation Files

> Builder fills in after completion

## Evaluation Dimensions

1. **Functional completeness**: Each Done criterion checked
2. **Code quality**: Error handling, edge cases, security
3. **Contract compliance**: Within scope
4. **Maintainability**: Naming, structure
