/**
 * Solar Agent Status Widget
 *
 * 显示 Solar 13 个 Agent 的运行状态
 */

import { card, kv } from "tvs/termplane/sdk/widget";
import type { CardLayout } from "tvs/termplane/render/types";

// ==================== Types ====================

export interface AgentStatusData {
  agents: Array<{
    id: string;
    emoji: string;
    status: "running" | "idle" | "error" | "offline";
    tasks?: number;
    phase?: string;
  }>;
  timestamp: number;
}

// ==================== Solar Agents ====================

export const SOLAR_AGENTS = [
  { id: "Researcher", emoji: "🔬", description: "技术研究与可行性分析" },
  { id: "Architect", emoji: "🏗️", description: "架构设计与方案评审" },
  { id: "PM", emoji: "📋", description: "产品验收" },
  { id: "Reporter", emoji: "📝", description: "技术报告撰写" },
  { id: "Coder", emoji: "💻", description: "代码实现" },
  { id: "Tester", emoji: "🧪", description: "测试与性能回归检查" },
  { id: "Reviewer", emoji: "👁️", description: "代码审查" },
  { id: "Docs", emoji: "📖", description: "文档生成" },
  { id: "Ops", emoji: "⚙️", description: "构建部署" },
  { id: "Guard", emoji: "🛡️", description: "规范检查与版本完整性" },
  { id: "Secretary", emoji: "📎", description: "记录整理与状态持久化" },
  { id: "BenchmarkReporter", emoji: "📊", description: "生成结构化测试报告" },
  { id: "SM", emoji: "🛒", description: "Skill 市场" },
] as const;

// ==================== Widget ====================

export class AgentStatusWidget {
  readonly id = "solar.agent.status";
  readonly title = "Solar Agents";

  /**
   * 生成模拟数据
   */
  mockData(): AgentStatusData {
    return {
      agents: SOLAR_AGENTS.map((agent) => ({
        id: agent.id,
        emoji: agent.emoji,
        status: Math.random() > 0.6 ? "running" : "idle",
        tasks: Math.floor(Math.random() * 5),
      })),
      timestamp: Date.now(),
    };
  }

  /**
   * 渲染 Widget
   */
  render(data: AgentStatusData): CardLayout {
    const items = data.agents.map((agent) => {
      const statusMap: Record<string, "success" | "warning" | "error"> = {
        running: "success",
        idle: "warning",
        error: "error",
        offline: "error",
      };

      return {
        key: `${agent.emoji} ${agent.id}`,
        value: agent.status.toUpperCase(),
        status: statusMap[agent.status],
      };
    });

    return card("☀️ SOLAR AGENTS", [{ type: "kv", items }]);
  }

  /**
   * 渲染简洁版本 (只显示活跃 Agent)
   */
  renderCompact(data: AgentStatusData): CardLayout {
    const activeAgents = data.agents.filter((a) => a.status === "running");
    const items = activeAgents.map((agent) => ({
      key: `${agent.emoji} ${agent.id}`,
      value: agent.tasks ? `${agent.tasks} tasks` : "active",
      status: "success" as const,
    }));

    return card("☀️ ACTIVE AGENTS", [
      { type: "kv", items },
      { type: "divider" },
      {
        type: "text",
        content: `${activeAgents.length}/${data.agents.length} active`,
        align: "center",
      },
    ]);
  }
}

export const agentStatusWidget = new AgentStatusWidget();
