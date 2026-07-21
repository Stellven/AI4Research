// Compatibility implementation — pending upstream original.
// Absent from the public extraction but imported by the daemon. Minimal real
// behavior only; do not extend beyond what the daemon needs to boot and
// serve. See AGENTS.md "Compatibility Modules".

export type OrchestrationEventType =
  | "task_started"
  | "task_completed"
  | "task_paused"
  | "task_resumed"
  | "node_started"
  | "node_completed"
  | "node_failed"
  | "node_rerouted"
  | "intervention_applied"
  | "retry_scheduled"
  | "retry_exhausted"
  | "repair_branch_queued";

export type TaskNodeStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "paused";

export interface OrchestrationEvent {
  type: OrchestrationEventType;
  taskId: string;
  nodeId?: string;
  payload?: Record<string, unknown>;
  at: string;
}

export interface TaskNode {
  id: string;
  intent: string;
  content: string;
  status: TaskNodeStatus;
  riskScore: number;
  output?: string;
  error?: string;
  tokensUsed?: number;
}

export interface TaskGraph {
  taskId: string;
  content: string;
  parsedIntent: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  nodes: TaskNode[];
  createdAt: string;
  updatedAt: string;
}

export interface NodeExecutionResult {
  nodeId: string;
  status: "completed" | "failed";
  output?: string;
  error?: string;
  tokensUsed?: number;
  durationMs: number;
}
