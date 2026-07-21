/**
 * Solar Agent System
 *
 * Multi-agent communication and collaboration framework
 *
 * @example
 * ```typescript
 * import { getBus, createTaskMessage } from 'solar/core/agent';
 *
 * const bus = getBus();
 *
 * // Subscribe to messages
 * bus.subscribe('coder', async (message) => {
 *   console.log('Received:', message);
 *   // Handle task...
 * });
 *
 * // Send task to coder
 * const task = createTaskMessage('orchestrator', 'coder', {
 *   id: 'task_1',
 *   title: 'Implement feature',
 *   description: 'Add dark mode toggle',
 *   type: 'implement',
 * });
 *
 * bus.publish(task);
 * ```
 */

// ==================== Protocol ====================

export type {
  MessageType,
  Priority,
  AgentId,
  AgentMessage,
  MessagePayload,
  ErrorPayload,
  MessageContext,
  TaskPayload,
  TaskDefinition,
  TaskType,
  TaskConstraints,
  OutputSpec,
  Artifact,
  ResultPayload,
  ResultMetrics,
  HandoffPayload,
  HandoffContext,
} from "./protocol";

export {
  createMessage,
  createTaskMessage,
  createResultMessage,
  createErrorMessage,
  createHandoffMessage,
  validateMessage,
  serializeMessage,
  deserializeMessage,
} from "./protocol";

// ==================== Bus ====================

export type {
  MessageHandler,
  MessageFilter,
  Subscription,
  BusConfig,
  BusStats,
} from "./bus";

export { AgentBus, getBus, resetBus } from "./bus";

// ==================== Monitor Agent ====================

export type {
  TokenUsage,
  SessionStats,
  RateLimitStatus,
  Alert,
  MonitorConfig,
} from "./monitor";

export {
  MonitorAgent,
  getMonitorAgent,
  createMonitorAgent,
} from "./monitor";

// ==================== Agent Registry ====================

export const AGENTS: Record<string, { emoji: string; role: string; phase: string[] }> = {
  researcher: {
    emoji: "🔬",
    role: "技术调研与可行性分析",
    phase: ["P1"],
  },
  architect: {
    emoji: "🏗️",
    role: "架构设计与方案评审",
    phase: ["P2"],
  },
  coder: {
    emoji: "💻",
    role: "代码实现与优化",
    phase: ["P3"],
  },
  tester: {
    emoji: "🧪",
    role: "测试与性能验证",
    phase: ["P4"],
  },
  reviewer: {
    emoji: "👁️",
    role: "代码审查与安全检查",
    phase: ["P4"],
  },
  docs: {
    emoji: "📖",
    role: "文档生成与维护",
    phase: ["P5"],
  },
  ops: {
    emoji: "⚙️",
    role: "构建与部署",
    phase: ["P5"],
  },
  guard: {
    emoji: "🛡️",
    role: "规范检查与版本完整性",
    phase: ["P3", "P4", "P5"],
  },
  secretary: {
    emoji: "📦",
    role: "记录整理与状态持久化",
    phase: ["P1", "P2", "P3", "P4", "P5"],
  },
  reporter: {
    emoji: "📝",
    role: "技术报告撰写",
    phase: ["P1", "P5"],
  },
  pm: {
    emoji: "📋",
    role: "产品验收",
    phase: ["P5"],
  },
  benchmark: {
    emoji: "📊",
    role: "性能基准测试",
    phase: ["P4"],
  },
  sm: {
    emoji: "🔍",
    role: "Skill 市场搜索与安装",
    phase: ["P1", "P2", "P3", "P4", "P5"],
  },
  monitor: {
    emoji: "📊",
    role: "资源监控与成本优化",
    phase: ["P1", "P2", "P3", "P4", "P5"],
  },
};

/**
 * Get agent info by ID
 */
export function getAgentInfo(agentId: string): { emoji: string; role: string; phase: string[] } | undefined {
  return AGENTS[agentId];
}

/**
 * Get agents for a specific phase
 */
export function getAgentsForPhase(phase: string): string[] {
  return Object.entries(AGENTS)
    .filter(([_, info]) => info.phase.includes(phase))
    .map(([id]) => id);
}
