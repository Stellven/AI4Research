import { ROLE_ORDER, type AgentRole } from "./format";

export type TerminalRunOutcome = "success" | "failure" | "";
export type StageState = "done" | "active" | "blocked" | "pending";

const RUN_PIPELINE: Array<{ role: AgentRole; match: RegExp }> = [
  { role: "pm", match: /intake|spec|prd|scope/ },
  { role: "planner", match: /plan|design|dag|rout/ },
  { role: "builder", match: /build|implement|dispatch|handoff/ },
  {
    role: "evaluator",
    match: /review|eval|accept|verdict/,
  },
];

export function pipelineStages(
  phase: string,
  status: string,
  isBlocked: boolean,
  terminalOutcome: TerminalRunOutcome,
  actionType: string,
  failedRole: AgentRole | "" = "",
  activeRole: AgentRole | "" = "",
): Array<{ role: AgentRole; state: StageState }> {
  const text = `${phase} ${status}`.toLowerCase();
  let activeIdx = 0;
  RUN_PIPELINE.forEach((stage, index) => {
    if (stage.match.test(text)) activeIdx = Math.max(activeIdx, index);
  });
  // The graph's active node is stronger live evidence than a coarse parent
  // phase such as planning_complete.  Without this override that phase can
  // label active builder work as Planner or, historically, Evaluator.
  const activeRoleIdx = activeRole ? ROLE_ORDER.indexOf(activeRole) : -1;
  if (activeRoleIdx >= 0) activeIdx = activeRoleIdx;
  // A live human gate is the strongest current-stage signal.
  if (actionType === "plan_review") activeIdx = 1;
  else if (actionType === "handoff_submit") activeIdx = 2;
  else if (actionType === "eval_review") activeIdx = 3;
  const failedIdx = failedRole ? ROLE_ORDER.indexOf(failedRole) : activeIdx;
  return RUN_PIPELINE.map((stage, index) => {
    let state: StageState;
    if (terminalOutcome === "success") state = "done";
    else if (terminalOutcome === "failure") {
      if (index < failedIdx) state = "done";
      else if (index === failedIdx) state = "blocked";
      else state = "pending";
    } else if (index < activeIdx) state = "done";
    else if (index === activeIdx) state = isBlocked ? "blocked" : "active";
    else state = "pending";
    return { role: stage.role, state };
  });
}
