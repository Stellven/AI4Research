import type {
  NodeExecutionResult,
  OrchestrationEvent,
  TaskGraph,
  TaskNode,
} from "./types";

type NodeHandler = (input: {
  graph: TaskGraph;
  node: TaskNode;
}) => Promise<{ output: string; tokensUsed?: number }>;

type OrchestratorOptions = {
  defaultDebateRounds?: number;
  highRiskThreshold?: number;
  voteMode?: "majority" | "weighted";
  onEvent?: (event: OrchestrationEvent) => void;
};

export class Orchestrator {
  private options: OrchestratorOptions;
  private pausedTasks: Set<string> = new Set();

  constructor(options: OrchestratorOptions = {}) {
    this.options = {
      defaultDebateRounds: options.defaultDebateRounds ?? 1,
      highRiskThreshold: options.highRiskThreshold ?? 0.7,
      voteMode: options.voteMode ?? "weighted",
      onEvent: options.onEvent,
    };
  }

  buildGraph(taskId: string, content: string, parsedIntent: string): TaskGraph {
    const now = new Date().toISOString();
    const intent = parsedIntent?.trim() || "manual";
    return {
      taskId,
      content,
      parsedIntent: intent,
      status: "pending",
      createdAt: now,
      updatedAt: now,
      nodes: [
        {
          id: "node-1",
          intent,
          content,
          status: "pending",
          riskScore: this.estimateRisk(intent, content),
        },
      ],
    };
  }

  async executeGraph(
    graph: TaskGraph,
    handler: NodeHandler,
  ): Promise<{ output: string; tokensUsed: number; nodeResults: NodeExecutionResult[] }> {
    graph.status = "running";
    graph.updatedAt = new Date().toISOString();
    this.emit({ type: "task_started", taskId: graph.taskId, payload: { nodes: graph.nodes.length } });

    const nodeResults: NodeExecutionResult[] = [];
    const outputs: string[] = [];
    let totalTokens = 0;

    for (const node of graph.nodes) {
      if (this.pausedTasks.has(graph.taskId)) {
        graph.status = "paused";
        node.status = "paused";
        this.emit({ type: "task_paused", taskId: graph.taskId, nodeId: node.id });
        break;
      }

      const started = Date.now();
      node.status = "running";
      this.emit({
        type: "node_started",
        taskId: graph.taskId,
        nodeId: node.id,
        payload: { intent: node.intent, risk: node.riskScore },
      });

      try {
        const result = await handler({ graph, node });
        const durationMs = Date.now() - started;
        node.status = "completed";
        node.output = result.output;
        node.tokensUsed = result.tokensUsed || 0;
        totalTokens += node.tokensUsed;
        outputs.push(result.output);
        nodeResults.push({
          nodeId: node.id,
          status: "completed",
          output: result.output,
          tokensUsed: node.tokensUsed,
          durationMs,
        });
        this.emit({
          type: "node_completed",
          taskId: graph.taskId,
          nodeId: node.id,
          payload: {
            durationMs,
            tokensUsed: node.tokensUsed,
            outputPreview: result.output.slice(0, 500),
          },
        });
      } catch (error) {
        const durationMs = Date.now() - started;
        const message = error instanceof Error ? error.message : String(error);
        node.status = "failed";
        node.error = message;
        graph.status = "failed";
        nodeResults.push({ nodeId: node.id, status: "failed", error: message, durationMs });
        this.emit({
          type: "node_failed",
          taskId: graph.taskId,
          nodeId: node.id,
          payload: { error: message, durationMs },
        });
      }
    }

    if (graph.status !== "failed" && graph.status !== "paused") {
      graph.status = "completed";
      this.emit({
        type: "task_completed",
        taskId: graph.taskId,
        payload: { nodes: nodeResults.length, tokensUsed: totalTokens },
      });
    }
    graph.updatedAt = new Date().toISOString();

    return {
      output: outputs.join("\n\n"),
      tokensUsed: totalTokens,
      nodeResults,
    };
  }

  pause(taskId: string): void {
    this.pausedTasks.add(taskId);
    this.emit({ type: "task_paused", taskId });
  }

  resume(taskId: string): void {
    this.pausedTasks.delete(taskId);
    this.emit({ type: "task_resumed", taskId });
  }

  reroute(taskId: string, nodeId: string, target: string): void {
    this.emit({
      type: "node_rerouted",
      taskId,
      nodeId,
      payload: { target },
    });
  }

  setDebateRounds(taskId: string, rounds: number, nodeId?: string): void {
    this.emit({
      type: "intervention_applied",
      taskId,
      nodeId,
      payload: { action: "set_debate_rounds", rounds },
    });
  }

  updatePolicy(policy: Partial<Pick<OrchestratorOptions, "defaultDebateRounds" | "highRiskThreshold" | "voteMode">>): void {
    this.options = { ...this.options, ...policy };
  }

  private estimateRisk(intent: string, content: string): number {
    void intent;
    void content;
    return 0;
  }

  private emit(event: Omit<OrchestrationEvent, "at"> & { at?: string }): void {
    this.options.onEvent?.({
      ...event,
      at: event.at || new Date().toISOString(),
    });
  }
}

export type {
  NodeExecutionResult,
  OrchestrationEvent,
  TaskGraph,
  TaskNode,
} from "./types";
