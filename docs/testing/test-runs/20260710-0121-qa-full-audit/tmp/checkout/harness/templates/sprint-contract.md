# Sprint Contract — {{title}} ({{sprint_id}})
Created: {{created_at}}
Status: drafting
Project: {{project_dir}}

## 简述 (Summary)
{{summary}}

## 需求 (Requirements)
{{requirements}}

## Done 定义 (Definition of Done)
{{done_criteria}}

## 规划产物 (Required Planning Artifacts)
- `sprints/{{sprint_id}}.plan.md`: 给人看的执行计划
- `sprints/{{sprint_id}}.task_graph.json`: 给控制面执行的 DAG，必须通过：

```bash
~/.solar/bin/solar-harness graph-scheduler enrich-capabilities --graph ~/.solar/harness/sprints/{{sprint_id}}.task_graph.json --source ~/.solar/harness/sprints/{{sprint_id}}.contract.md --in-place
~/.solar/bin/solar-harness graph-scheduler validate --graph ~/.solar/harness/sprints/{{sprint_id}}.task_graph.json
```

每个 DAG 节点必须声明 `id / goal / depends_on / write_scope / read_scope / required_skills / required_capabilities / preferred_model / gate / acceptance / estimated_cost`。如果 planner 无法人工判断外部能力，必须先运行 `graph-scheduler enrich-capabilities`，把自动推导出的 `required_capabilities` 保留在图里。未声明 `write_scope` 的节点禁止并行，只能串行。

## 范围 (Scope)
- 包含: {{scope_in}}
- 不包含: {{scope_out}}

## 约束 (Constraints)
{{constraints}}

## 实现文件清单 (Builder 完成后填写)
{{file_list}}

## 审判官评估维度 (Evaluation Dimensions)
1. **功能完整性**: Done 定义逐条检查
2. **代码质量**: 错误处理、边界条件、安全
3. **合约合规**: 是否在范围内，没超范围
4. **可维护性**: 命名、结构、注释合理性
