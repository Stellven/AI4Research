/**
 * Solar UI Module
 *
 * 基于 TVS termplane 引擎，提供 Solar 特定的终端 UI 能力
 *
 * @example
 * ```typescript
 * import { SolarDashboard, AgentWidget } from 'solar/core/ui';
 *
 * // 快速启动 Agent 监控面板
 * const dashboard = new SolarDashboard();
 * dashboard.start();
 *
 * // 或单独渲染 Widget
 * const widget = new AgentWidget();
 * console.log(widget.render(agentData));
 * ```
 */

// ==================== Re-export TVS Core ====================

// GridRenderer
export { GridRenderer } from "tvs/termplane/render/grid";

// DSL Helpers
export { card, kv, sparkline, bar, list, text, createWidget } from "tvs/termplane/sdk/widget";

// Types
export type { CardLayout } from "tvs/termplane/render/types";

// ==================== Solar UI ====================

export { SolarDashboard } from "./dashboard";
export type { SolarDashboardConfig } from "./dashboard";

export { AgentStatusWidget } from "./widgets/agent-status";
export type { AgentStatusData } from "./widgets/agent-status";

export { PhaseWidget } from "./widgets/phase";
export type { PhaseData } from "./widgets/phase";

export { TaskQueueWidget } from "./widgets/task-queue";
export type { TaskQueueData } from "./widgets/task-queue";

export { TokenWidget } from "./widgets/token";
export type { TokenData } from "./widgets/token";

export { LogWidget } from "./widgets/log";
export type { LogData } from "./widgets/log";

// ==================== Layouts ====================

export { SOLAR_LAYOUTS } from "./layouts";
export type { SolarLayoutPreset } from "./layouts";

// ==================== Quick Start ====================

export {
  renderBanner,
  renderStatusBar,
  quickDashboard,
  renderAgentCard,
  renderProgressCard,
  renderStatsCard,
} from "./quick";

// ==================== Keyboard ====================

export { KeyboardHandler, renderHelpPanel, KEY_CODES, keyboard } from "./keyboard";
export type { KeyHandler, KeyBinding } from "./keyboard";
