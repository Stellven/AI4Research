/**
 * Solar UI Quick Start
 *
 * 快速渲染函数，无需创建 Dashboard 实例
 */

import { GridRenderer } from "tvs/termplane/render/grid";
import { card, kv, bar } from "tvs/termplane/sdk/widget";

import { SolarDashboard, type SolarDashboardConfig } from "./dashboard";
import { PHASES, type Phase } from "./widgets/phase";

// ==================== Banner ====================

/**
 * 渲染 Solar 启动横幅
 */
export function renderBanner(options?: {
  project?: string;
  phase?: Phase;
  agent?: string;
  version?: string;
}): string {
  const { project = "Solar", phase = "P3", agent = "Coder", version = "v3.0.0" } = options || {};

  const phaseInfo = PHASES.find((p) => p.id === phase);
  const phaseName = phaseInfo ? `${phaseInfo.emoji} ${phase} ${phaseInfo.name}` : phase;

  const lines = [
    "┌─ ☀️ Solar ──────────────────────────────────────┐",
    `│ 项目: ${project.padEnd(40)}│`,
    `│ 版本: ${version.padEnd(40)}│`,
    "├─────────────────────────────────────────────────┤",
    `│ 阶段: ${phaseName.padEnd(40)}│`,
    `│ Agent: ${agent.padEnd(39)}│`,
    "└─────────────────────────────────────────────────┘",
  ];

  return lines.join("\n");
}

// ==================== Status Bar ====================

/**
 * 渲染状态栏 (单行)
 */
export function renderStatusBar(options?: {
  phase?: Phase;
  agent?: string;
  tokens?: number;
  rate?: number;
}): string {
  const { phase = "P3", agent = "Coder", tokens = 0, rate = 0 } = options || {};

  const rateIcon = rate < 50 ? "🟢" : rate < 80 ? "🟡" : "🔴";
  const tokenStr = tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}K` : tokens.toString();

  return `[Solar] ${phase} | ${agent} | +${tokenStr} | Rate ${rate}% ${rateIcon}`;
}

// ==================== Quick Dashboard ====================

/**
 * 快速启动 Dashboard
 */
export function quickDashboard(config?: SolarDashboardConfig): SolarDashboard {
  const dashboard = new SolarDashboard(config);
  return dashboard;
}

// ==================== Quick Widgets ====================

/**
 * 快速渲染 Agent 状态卡片
 */
export function renderAgentCard(agents: Array<{ name: string; status: "running" | "idle" }>): string {
  const renderer = new GridRenderer({ width: 40, columns: 1, gap: 0 });

  const cardLayout = card("☀️ AGENTS", [
    {
      type: "kv",
      items: agents.map((a) => ({
        key: a.name,
        value: a.status.toUpperCase(),
        status: a.status === "running" ? ("success" as const) : ("warning" as const),
      })),
    },
  ]);

  return renderer.renderCard(cardLayout).join("\n");
}

/**
 * 快速渲染进度卡片
 */
export function renderProgressCard(title: string, progress: number, label?: string): string {
  const renderer = new GridRenderer({ width: 40, columns: 1, gap: 0 });

  const cardLayout = card(title, [
    { type: "bar", value: progress, label: label || "Progress" },
    { type: "text", content: `${Math.round(progress * 100)}% complete`, align: "center" },
  ]);

  return renderer.renderCard(cardLayout).join("\n");
}

/**
 * 快速渲染统计卡片
 */
export function renderStatsCard(
  title: string,
  stats: Array<{ key: string; value: string | number; status?: "success" | "warning" | "error" }>,
): string {
  const renderer = new GridRenderer({ width: 40, columns: 1, gap: 0 });

  const cardLayout = card(title, [
    {
      type: "kv",
      items: stats.map((s) => ({
        key: s.key,
        value: String(s.value),
        status: s.status,
      })),
    },
  ]);

  return renderer.renderCard(cardLayout).join("\n");
}
