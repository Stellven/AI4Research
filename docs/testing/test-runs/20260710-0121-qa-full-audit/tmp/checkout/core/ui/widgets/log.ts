/**
 * Solar Log Widget
 *
 * 显示 Agent 活动日志
 */

import { card, list, text } from "tvs/termplane/sdk/widget";
import type { CardLayout } from "tvs/termplane/render/types";

// ==================== Types ====================

export interface LogData {
  entries: LogEntry[];
  maxEntries: number;
}

export interface LogEntry {
  timestamp: string;
  agent: string;
  emoji: string;
  message: string;
  level: "info" | "warn" | "error" | "debug";
}

// ==================== Widget ====================

export class LogWidget {
  readonly id = "solar.log";
  readonly title = "Agent Log";

  /**
   * 生成模拟数据
   */
  mockData(): LogData {
    return {
      entries: [
        { timestamp: "14:32:01", agent: "Coder", emoji: "💻", message: "实现 HashJoin v10 算子", level: "info" },
        { timestamp: "14:32:15", agent: "Tester", emoji: "🧪", message: "运行 TPC-H 基准测试", level: "info" },
        { timestamp: "14:32:28", agent: "Architect", emoji: "🏗️", message: "审查设计方案", level: "info" },
        { timestamp: "14:32:45", agent: "Ops", emoji: "⚙️", message: "构建 Release 版本", level: "info" },
        { timestamp: "14:33:02", agent: "Coder", emoji: "💻", message: "优化 Filter SIMD", level: "info" },
        { timestamp: "14:33:18", agent: "Guard", emoji: "🛡️", message: "规范检查通过", level: "info" },
      ],
      maxEntries: 10,
    };
  }

  /**
   * 渲染 Widget
   */
  render(data: LogData): CardLayout {
    const items = data.entries.slice(-6).map((entry) => {
      const levelIcon = entry.level === "error" ? "❌" : entry.level === "warn" ? "⚠️" : "";
      return `${entry.timestamp} [${entry.emoji}${entry.agent}] ${entry.message} ${levelIcon}`;
    });

    return card("📜 AGENT LOG", [
      { type: "list", items, variant: "bullet" },
    ]);
  }

  /**
   * 渲染带时间线的版本
   */
  renderTimeline(data: LogData): CardLayout {
    const items = data.entries.slice(-8).map((entry) => ({
      text: `${entry.timestamp} ${entry.emoji} ${entry.message}`,
      status: entry.level === "error" ? "error" as const : entry.level === "warn" ? "warning" as const : undefined,
    }));

    return card("📜 TIMELINE", [
      { type: "list", items, variant: "bullet" },
      { type: "divider" },
      { type: "text", content: `最近 ${data.entries.length} 条记录`, align: "center" },
    ]);
  }
}

export const logWidget = new LogWidget();
