/**
 * Solar Dashboard Layouts
 *
 * 预定义的 Dashboard 布局模板
 */

// ==================== Types ====================

export type SolarLayoutPreset = "full" | "compact" | "minimal" | "dev" | "monitor";

export interface LayoutConfig {
  columns: number;
  gap: number;
  width: number;
  widgets: WidgetPlacement[];
}

export interface WidgetPlacement {
  id: string;
  row: number;
  column: number;
  span?: number;
}

// ==================== Layouts ====================

/**
 * 完整布局 - 6 个 Widget
 *
 * ┌─────────────┬─────────────┬─────────────┐
 * │   Agents    │   Phase     │   Tokens    │
 * ├─────────────┼─────────────┴─────────────┤
 * │   Tasks     │          Log              │
 * └─────────────┴───────────────────────────┘
 */
const FULL_LAYOUT: LayoutConfig = {
  columns: 3,
  gap: 2,
  width: 100,
  widgets: [
    { id: "solar.agent.status", row: 1, column: 1 },
    { id: "solar.phase", row: 1, column: 2 },
    { id: "solar.token", row: 1, column: 3 },
    { id: "solar.task.queue", row: 2, column: 1 },
    { id: "solar.log", row: 2, column: 2, span: 2 },
  ],
};

/**
 * 紧凑布局 - 4 个 Widget
 *
 * ┌─────────────┬─────────────┐
 * │   Agents    │   Phase     │
 * ├─────────────┼─────────────┤
 * │   Tasks     │   Tokens    │
 * └─────────────┴─────────────┘
 */
const COMPACT_LAYOUT: LayoutConfig = {
  columns: 2,
  gap: 2,
  width: 80,
  widgets: [
    { id: "solar.agent.status", row: 1, column: 1 },
    { id: "solar.phase", row: 1, column: 2 },
    { id: "solar.task.queue", row: 2, column: 1 },
    { id: "solar.token", row: 2, column: 2 },
  ],
};

/**
 * 最小布局 - 2 个 Widget
 *
 * ┌─────────────┬─────────────┐
 * │   Phase     │   Tasks     │
 * └─────────────┴─────────────┘
 */
const MINIMAL_LAYOUT: LayoutConfig = {
  columns: 2,
  gap: 2,
  width: 60,
  widgets: [
    { id: "solar.phase", row: 1, column: 1 },
    { id: "solar.task.queue", row: 1, column: 2 },
  ],
};

/**
 * 开发布局 - 侧重代码和任务
 *
 * ┌─────────────┬───────────────────────────┐
 * │   Agents    │           Log             │
 * ├─────────────┼───────────────────────────┤
 * │   Tasks     │          Tokens           │
 * └─────────────┴───────────────────────────┘
 */
const DEV_LAYOUT: LayoutConfig = {
  columns: 3,
  gap: 2,
  width: 100,
  widgets: [
    { id: "solar.agent.status", row: 1, column: 1 },
    { id: "solar.log", row: 1, column: 2, span: 2 },
    { id: "solar.task.queue", row: 2, column: 1 },
    { id: "solar.token", row: 2, column: 2, span: 2 },
  ],
};

/**
 * 监控布局 - 侧重状态和指标
 *
 * ┌─────────────┬─────────────┬─────────────┐
 * │   Agents    │   Tokens    │   Phase     │
 * ├─────────────┴─────────────┴─────────────┤
 * │                  Log                    │
 * └─────────────────────────────────────────┘
 */
const MONITOR_LAYOUT: LayoutConfig = {
  columns: 3,
  gap: 2,
  width: 100,
  widgets: [
    { id: "solar.agent.status", row: 1, column: 1 },
    { id: "solar.token", row: 1, column: 2 },
    { id: "solar.phase", row: 1, column: 3 },
    { id: "solar.log", row: 2, column: 1, span: 3 },
  ],
};

// ==================== Export ====================

export const SOLAR_LAYOUTS: Record<SolarLayoutPreset, LayoutConfig> = {
  full: FULL_LAYOUT,
  compact: COMPACT_LAYOUT,
  minimal: MINIMAL_LAYOUT,
  dev: DEV_LAYOUT,
  monitor: MONITOR_LAYOUT,
};

/**
 * 获取布局配置
 */
export function getLayout(preset: SolarLayoutPreset): LayoutConfig {
  return SOLAR_LAYOUTS[preset];
}
