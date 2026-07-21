/**
 * Agent Communication Protocol
 *
 * Standardized message format and communication bus for Solar agents
 */

// ==================== Message Types ====================

export type MessageType =
  | "task"           // Task delegation
  | "result"         // Task completion result
  | "error"          // Error report
  | "status"         // Status update
  | "query"          // Information request
  | "response"       // Query response
  | "event"          // Event notification
  | "handoff"        // Agent handoff
  | "sync";          // State synchronization

export type Priority = "critical" | "high" | "normal" | "low";

export type AgentId =
  | "researcher"
  | "architect"
  | "coder"
  | "tester"
  | "reviewer"
  | "docs"
  | "ops"
  | "guard"
  | "secretary"
  | "reporter"
  | "pm"
  | "benchmark"
  | "sm"
  | "orchestrator"; // Solar flow controller

// ==================== Message Structure ====================

export interface AgentMessage {
  // Identity
  id: string;
  type: MessageType;
  timestamp: number;

  // Routing
  from: AgentId;
  to: AgentId | AgentId[] | "broadcast";

  // Content
  payload: MessagePayload;

  // Metadata
  priority: Priority;
  correlationId?: string;    // Links related messages
  replyTo?: string;          // For request-response pattern
  ttl?: number;              // Time-to-live in ms
  retryCount?: number;

  // Context
  context?: MessageContext;
}

export interface MessagePayload {
  action: string;
  data?: unknown;
  error?: ErrorPayload;
}

export interface ErrorPayload {
  code: string;
  message: string;
  details?: unknown;
  recoverable: boolean;
}

export interface MessageContext {
  phase?: string;            // Current Solar phase
  task?: string;             // Current task
  project?: string;          // Project context
  session?: string;          // Session ID
  trace?: string[];          // Message trace for debugging
}

// ==================== Task Delegation ====================

export interface TaskPayload {
  action: "execute" | "validate" | "review" | "delegate";
  task: TaskDefinition;
  constraints?: TaskConstraints;
  artifacts?: Artifact[];
}

export interface TaskDefinition {
  id: string;
  title: string;
  description: string;
  type: TaskType;
  input?: unknown;
  expectedOutput?: OutputSpec;
  dependencies?: string[];    // Task IDs this depends on
  deadline?: number;          // Unix timestamp
}

export type TaskType =
  | "research"
  | "design"
  | "implement"
  | "test"
  | "review"
  | "document"
  | "deploy"
  | "analyze"
  | "optimize";

export interface TaskConstraints {
  maxDuration?: number;       // Max time in ms
  maxTokens?: number;         // Max token budget
  mustUseTools?: string[];    // Required tools
  forbiddenTools?: string[];  // Forbidden tools
  qualityLevel?: "draft" | "standard" | "high" | "critical";
}

export interface OutputSpec {
  format: "text" | "json" | "markdown" | "code" | "file";
  schema?: object;            // JSON schema for validation
}

export interface Artifact {
  id: string;
  type: "file" | "code" | "data" | "report";
  path?: string;
  content?: string;
  metadata?: Record<string, unknown>;
}

// ==================== Result Structure ====================

export interface ResultPayload {
  action: "complete" | "partial" | "failed" | "blocked";
  taskId: string;
  output?: unknown;
  artifacts?: Artifact[];
  metrics?: ResultMetrics;
  nextSteps?: string[];
}

export interface ResultMetrics {
  duration: number;           // Time taken in ms
  tokensUsed: number;
  toolCalls: number;
  linesChanged?: number;
  testsRun?: number;
  testsPassed?: number;
}

// ==================== Handoff Structure ====================

export interface HandoffPayload {
  action: "request" | "accept" | "decline" | "complete";
  reason: string;
  context: HandoffContext;
  recommendations?: string[];
}

export interface HandoffContext {
  currentState: unknown;
  completedSteps: string[];
  pendingSteps: string[];
  blockers?: string[];
  resources?: Artifact[];
}

// ==================== Message Factory ====================

let messageCounter = 0;

export function createMessage(
  type: MessageType,
  from: AgentId,
  to: AgentId | AgentId[] | "broadcast",
  payload: MessagePayload,
  options?: Partial<Omit<AgentMessage, "id" | "type" | "from" | "to" | "payload" | "timestamp">>
): AgentMessage {
  return {
    id: `msg_${Date.now()}_${++messageCounter}`,
    type,
    timestamp: Date.now(),
    from,
    to,
    payload,
    priority: options?.priority ?? "normal",
    correlationId: options?.correlationId,
    replyTo: options?.replyTo,
    ttl: options?.ttl,
    retryCount: options?.retryCount ?? 0,
    context: options?.context,
  };
}

export function createTaskMessage(
  from: AgentId,
  to: AgentId,
  task: TaskDefinition,
  options?: {
    constraints?: TaskConstraints;
    artifacts?: Artifact[];
    priority?: Priority;
    context?: MessageContext;
  }
): AgentMessage {
  const payload: TaskPayload = {
    action: "execute",
    task,
    constraints: options?.constraints,
    artifacts: options?.artifacts,
  };

  return createMessage("task", from, to, { action: "execute", data: payload }, {
    priority: options?.priority ?? "normal",
    context: options?.context,
  });
}

export function createResultMessage(
  from: AgentId,
  to: AgentId,
  taskId: string,
  result: Omit<ResultPayload, "taskId">,
  correlationId: string
): AgentMessage {
  const payload: ResultPayload = {
    ...result,
    taskId,
  };

  return createMessage("result", from, to, { action: result.action, data: payload }, {
    correlationId,
    priority: result.action === "failed" ? "high" : "normal",
  });
}

export function createErrorMessage(
  from: AgentId,
  to: AgentId,
  error: ErrorPayload,
  correlationId?: string
): AgentMessage {
  return createMessage("error", from, to, { action: "error", error }, {
    correlationId,
    priority: "high",
  });
}

export function createHandoffMessage(
  from: AgentId,
  to: AgentId,
  handoff: HandoffPayload
): AgentMessage {
  return createMessage("handoff", from, to, { action: handoff.action, data: handoff }, {
    priority: "high",
  });
}

// ==================== Message Validation ====================

export function validateMessage(message: AgentMessage): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!message.id) errors.push("Missing message ID");
  if (!message.type) errors.push("Missing message type");
  if (!message.from) errors.push("Missing sender");
  if (!message.to) errors.push("Missing recipient");
  if (!message.payload) errors.push("Missing payload");
  if (!message.timestamp) errors.push("Missing timestamp");

  // Check TTL
  if (message.ttl && Date.now() > message.timestamp + message.ttl) {
    errors.push("Message expired (TTL exceeded)");
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

// ==================== Serialization ====================

export function serializeMessage(message: AgentMessage): string {
  return JSON.stringify(message);
}

export function deserializeMessage(data: string): AgentMessage {
  return JSON.parse(data) as AgentMessage;
}
