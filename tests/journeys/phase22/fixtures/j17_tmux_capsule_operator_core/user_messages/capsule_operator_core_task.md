You are operating inside the J17 Phase 22 TMUX harness journey.

User task:

In workspace `{workspace_root}`, complete a capability/operator core exercise
for the local solar candidate pipeline. Use Solar's normal harness lifecycle:
intake, requirement compilation, planning, operator selection, execution,
evaluation, and recovery if interrupted.

Minimum requested outcome:

1. Select and invoke more than one capability/operator, not just inspect
   registry files.
2. Produce or update a TaskGraph plus any CodeGraph or WorkflowGraph style
   artifact the harness normally emits for the work.
3. Create durable task/operator records that name the logical operator,
   physical operator or actor, capability match, model/runtime choice, and
   execution result.
4. Qualify the invoked operator path with evidence that it ran against this
   workspace and record whether promotion/version evolution is supported.
5. Run `{test_command}` from the workspace and preserve the result.
6. If the first execution is interrupted after planning, resume through the
   same user entrypoint and preserve recovery evidence.

Constraints:

- Stay inside `{workspace_root}` and the isolated harness root.
- Do not touch repository production code.
- Do not edit Phase 22 reports, workbook, matrix, generator, validator, or
  other journey files.
- The final artifacts must contain enough evidence for each of these owned L2
  checks: capsule governance, capsule invocation/composition, capsule
  evolution/version promotion, logical operator registration, operator
  qualification, logical-to-physical binding, physical operator fleet
  execution, runtime evaluation/profiling, model registry selection, code graph,
  workflow graph, durable task queue, and failure recovery/resumability.
