function text(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

const EVALUATOR_WORKFLOW_STATES = new Set([
  "reviewing",
  "ready_for_review",
  "failed_review",
  "awaiting_review",
  "in_review",
  "evaluating",
]);


function explicitActor(value: unknown): string {
  const role = text(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!role) return "";
  if (
    /evaluator|verifier|verification|reviewer|review|testrunner|tester|quality|auditor|judge/.test(
      role,
    ) ||
    role === "qa" ||
    role === "test" ||
    role === "tests"
  )
    return "Evaluator";
  if (
    /implementationworker|implementation|builder|implementer|developer|coder|artifactcurator|synthesizer/.test(
      role,
    )
  )
    return "Builder";
  if (/planner|architect|router|plancompiler|strategist|designer/.test(role))
    return "Planner";
  if (
    role === "pm" ||
    /productmanager|requirementanalyst|requirements|intake|scope/.test(role)
  )
    return "PM";
  return "";
}


// Infer which agent a DAG node belongs to (node-based steps have no event actor),
// so node logs attach the right artifacts (build->Builder, review->Evaluator, ...).
export function nodeActor(node: { [key: string]: unknown }): string {
  // Governed nodes carry one certificate-covered execution identity. Prefer
  // it over every legacy flat-field heuristic so the UI cannot reinterpret a
  // node differently from validation and scheduling.
  const executableNode =
    node.executable_node &&
    typeof node.executable_node === "object" &&
    !Array.isArray(node.executable_node)
      ? (node.executable_node as { [key: string]: unknown })
      : {};
  for (const value of [
    executableNode.dispatch_role,
    executableNode.logical_operator,
    executableNode.physical_role,
  ]) {
    const actor = explicitActor(value);
    if (actor) return actor;
  }

  // Legacy or uncertified DAGs may only expose flat routing fields.
  for (const value of [
    node.logical_operator,
    node.requested_role,
    node.target_role,
    node.preferred_role,
    node.preferred_operator,
    node.selected_role,
    node.role,
    node.owner,
  ]) {
    const actor = explicitActor(value);
    if (actor) return actor;
  }

  const logicalPlanNode =
    node.logical_plan_node &&
    typeof node.logical_plan_node === "object" &&
    !Array.isArray(node.logical_plan_node)
      ? (node.logical_plan_node as { [key: string]: unknown })
      : {};
  const nestedActor = explicitActor(logicalPlanNode.logical_operator);
  if (nestedActor) return nestedActor;

  // Current certified generic graphs own execution routing through owner and
  // task-type fields; older graphs often omitted all explicit role fields.
  // Use those durable compiler inputs before guessing from an opaque S1/S2 id.
  for (const value of [
    node.dispatch_task_type,
    node.task_type,
    node.type,
  ]) {
    const actor = explicitActor(value);
    if (actor) return actor;
  }

  const caps = (
    Array.isArray(node.required_capabilities) ? node.required_capabilities : []
  )
    .map((cap) => text(cap).toLowerCase())
    .join(" ");
  const id = text(node.id || node.node_id || "node").toLowerCase();
  const combined = `${id} ${caps}`;
  if (/eval|review|verdict|gate|accept/.test(combined)) return "Evaluator";
  if (/build|impl|code|frontend|backend|server|handoff/.test(combined))
    return "Builder";
  if (/plan|design|dag|rout/.test(combined)) return "Planner";
  if (/spec|prd|intake|scope|product/.test(combined)) return "PM";
  return "Planner";
}


export function activeNodeActor(node: { [key: string]: unknown }): string {
  // `status` is intentionally coarse for progress/tone. `workflow_status`
  // preserves execution transitions such as dispatched -> reviewing, which
  // changes the live operator from Builder to Evaluator on the same DAG node.
  const workflowStatus = text(node.workflow_status || node.status).toLowerCase();
  if (EVALUATOR_WORKFLOW_STATES.has(workflowStatus)) return "Evaluator";
  return nodeActor(node);
}
