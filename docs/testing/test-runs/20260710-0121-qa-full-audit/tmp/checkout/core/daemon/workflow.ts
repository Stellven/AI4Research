/**
 * Solar Workflow Engine - 工作流引擎
 * 驱动五阶段流程，管理 Agent 切换
 */

import type { StateManager, SolarQueries } from "../nerve/state-manager";

// ==================== 类型定义 ====================

export type Phase = "P1" | "P2" | "P3" | "P4" | "P5";
export type Agent =
  | "Researcher"
  | "Architect"
  | "Coder"
  | "Tester"
  | "Reviewer"
  | "Docs"
  | "Ops"
  | "PM"
  | "Secretary"
  | "Guard";
export type Complexity = "simple" | "medium" | "complex";

export interface WorkflowState {
  active: boolean;
  taskId: number | null;
  currentPhase: Phase | null;
  currentAgent: Agent | null;
  complexity: Complexity | null;
  announced: boolean;
  gatesPassed: {
    G1: boolean;
    G2: boolean;
    G3: boolean;
  };
}

export interface StartWorkflowRequest {
  project: string;
  description: string;
  complexity?: Complexity;
}

export interface TransitionRequest {
  toPhase?: Phase;
  toAgent?: Agent;
  gatePassed?: "G1" | "G2" | "G3";
}

// ==================== 常量 ====================

const PHASE_AGENTS: Record<Phase, Agent[]> = {
  P1: ["Researcher"],
  P2: ["Architect", "Guard"],
  P3: ["Coder", "Guard"],
  P4: ["Tester", "Reviewer", "Docs"],
  P5: ["Ops", "PM", "Secretary"],
};

const AGENT_EMOJI: Record<Agent, string> = {
  Researcher: "🔬",
  Architect: "🏗️",
  Coder: "💻",
  Tester: "🧪",
  Reviewer: "👁️",
  Docs: "📖",
  Ops: "⚙️",
  PM: "📊",
  Secretary: "📝",
  Guard: "🛡️",
};

const COMPLEXITY_FLOW: Record<Complexity, Phase[]> = {
  simple: ["P3"],
  medium: ["P2", "P3", "P4"],
  complex: ["P1", "P2", "P3", "P4", "P5"],
};

// ==================== 工作流引擎 ====================

export class WorkflowEngine {
  private state: StateManager;
  private queries: SolarQueries;

  constructor(state: StateManager, queries: SolarQueries) {
    this.state = state;
    this.queries = queries;
  }

  // ==================== 状态管理 ====================

  /**
   * 获取当前工作流状态
   */
  getCurrent(): WorkflowState {
    return {
      active: this.state.get("flow.active", false),
      taskId: this.state.get("flow.task_id", null),
      currentPhase: this.state.get("flow.current_phase", null),
      currentAgent: this.state.get("flow.current_agent", null),
      complexity: this.state.get("flow.complexity", null),
      announced: this.state.get("flow.announced", false),
      gatesPassed: {
        G1: this.state.get("flow.gate.G1", false),
        G2: this.state.get("flow.gate.G2", false),
        G3: this.state.get("flow.gate.G3", false),
      },
    };
  }

  /**
   * 启动工作流
   */
  async start(
    req: StartWorkflowRequest,
  ): Promise<{ success: boolean; taskId?: number; error?: string }> {
    const current = this.getCurrent();
    if (current.active) {
      return { success: false, error: "Workflow already active" };
    }

    // 确定复杂度
    const complexity = req.complexity || "medium";

    // 创建任务
    const taskId = this.queries.createTask({
      project: req.project,
      description: req.description,
      complexity,
    });

    // 确定初始阶段
    const flow = COMPLEXITY_FLOW[complexity];
    const initialPhase = flow[0];
    const initialAgent = PHASE_AGENTS[initialPhase][0];

    // 更新状态
    this.state.setMany({
      "flow.active": true,
      "flow.task_id": taskId,
      "flow.current_phase": initialPhase,
      "flow.current_agent": initialAgent,
      "flow.complexity": complexity,
      "flow.announced": false,
      "flow.gate.G1": false,
      "flow.gate.G2": false,
      "flow.gate.G3": false,
    });

    // 更新任务状态
    this.queries.updateTaskStatus(
      Number(taskId),
      "in_progress",
      initialAgent,
      initialPhase,
    );

    // 记录日志
    this.queries.logMessage("workflow", "engine", {
      event: "started",
      taskId,
      project: req.project,
      complexity,
      initialPhase,
      initialAgent,
    });

    return { success: true, taskId: Number(taskId) };
  }

  /**
   * 停止工作流
   */
  async stop(completed: boolean = false): Promise<void> {
    const current = this.getCurrent();
    if (!current.active || !current.taskId) return;

    // 更新任务状态
    this.queries.updateTaskStatus(
      current.taskId,
      completed ? "completed" : "cancelled",
    );

    // 清理状态
    this.state.setMany({
      "flow.active": false,
      "flow.task_id": null,
      "flow.current_phase": null,
      "flow.current_agent": null,
      "flow.complexity": null,
      "flow.announced": false,
    });

    // 记录日志
    this.queries.logMessage("workflow", "engine", {
      event: completed ? "completed" : "stopped",
      taskId: current.taskId,
    });
  }

  /**
   * 阶段转换
   */
  async transition(
    req: TransitionRequest,
  ): Promise<{ success: boolean; error?: string }> {
    const current = this.getCurrent();
    if (!current.active) {
      return { success: false, error: "No active workflow" };
    }

    const fromPhase = current.currentPhase!;
    const fromAgent = current.currentAgent!;

    let toPhase = req.toPhase || fromPhase;
    let toAgent = req.toAgent || PHASE_AGENTS[toPhase][0];

    // 检查 Gate
    if (req.gatePassed) {
      this.state.set(`flow.gate.${req.gatePassed}`, true);
    }

    // 验证转换合法性
    if (toPhase !== fromPhase) {
      const flow = COMPLEXITY_FLOW[current.complexity!];
      const fromIndex = flow.indexOf(fromPhase);
      const toIndex = flow.indexOf(toPhase);

      if (toIndex === -1) {
        return {
          success: false,
          error: `Phase ${toPhase} not in flow for complexity ${current.complexity}`,
        };
      }

      // 检查 Gate 要求
      if (
        fromPhase === "P2" &&
        toPhase === "P3" &&
        !current.gatesPassed.G1 &&
        !req.gatePassed
      ) {
        return { success: false, error: "G1 Gate not passed" };
      }
      if (
        fromPhase === "P4" &&
        toPhase === "P5" &&
        !current.gatesPassed.G2 &&
        !req.gatePassed
      ) {
        return { success: false, error: "G2 Gate not passed" };
      }
    }

    // 记录转换
    this.queries.recordTransition(
      current.taskId!,
      fromPhase,
      toPhase,
      fromAgent,
      toAgent,
      req.gatePassed,
      req.gatePassed ? true : undefined,
    );

    // 更新状态
    this.state.setMany({
      "flow.current_phase": toPhase,
      "flow.current_agent": toAgent,
      "flow.announced": false,
    });

    // 更新任务
    this.queries.updateTaskStatus(
      current.taskId!,
      "in_progress",
      toAgent,
      toPhase,
    );

    // 记录日志
    this.queries.logMessage("workflow", "engine", {
      event: "transition",
      taskId: current.taskId,
      from: { phase: fromPhase, agent: fromAgent },
      to: { phase: toPhase, agent: toAgent },
      gate: req.gatePassed,
    });

    return { success: true };
  }

  /**
   * 标记已宣告
   */
  markAnnounced(): void {
    this.state.set("flow.announced", true);
  }

  /**
   * 检查工作流状态 (心跳)
   */
  async checkState(): Promise<void> {
    const current = this.getCurrent();
    if (!current.active) return;

    // 检查任务是否存在
    const task = this.queries.getTaskById(current.taskId!);
    if (!task) {
      console.warn("Workflow task not found, stopping");
      await this.stop();
      return;
    }

    // TODO: 检查超时等
  }

  // ==================== 辅助方法 ====================

  /**
   * 获取 Agent emoji
   */
  getAgentEmoji(agent: Agent): string {
    return AGENT_EMOJI[agent] || "🤖";
  }

  /**
   * 获取阶段的 Agent 列表
   */
  getPhaseAgents(phase: Phase): Agent[] {
    return PHASE_AGENTS[phase] || [];
  }

  /**
   * 获取下一阶段
   */
  getNextPhase(): Phase | null {
    const current = this.getCurrent();
    if (!current.active || !current.complexity || !current.currentPhase)
      return null;

    const flow = COMPLEXITY_FLOW[current.complexity];
    const currentIndex = flow.indexOf(current.currentPhase);

    if (currentIndex === -1 || currentIndex === flow.length - 1) {
      return null;
    }

    return flow[currentIndex + 1];
  }

  /**
   * 检查是否是最后阶段
   */
  isFinalPhase(): boolean {
    return this.getNextPhase() === null;
  }

  /**
   * 生成宣告框内容
   */
  generateAnnouncement(task: string, plan: string[]): string {
    const current = this.getCurrent();
    if (!current.currentAgent) return "";

    const emoji = this.getAgentEmoji(current.currentAgent);
    const planLines = plan.map((p, i) => `│   ${i + 1}. ${p}`).join("\n");

    return `
┌─ ${emoji} ${current.currentAgent} ─────────────────────────────────┐
│ Task: ${task.padEnd(40)}│
│ Plan:                                           │
${planLines}
└─────────────────────────────────────────────────┘
    `.trim();
  }
}
