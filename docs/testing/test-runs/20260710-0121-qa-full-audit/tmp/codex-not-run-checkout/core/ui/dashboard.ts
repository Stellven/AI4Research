/**
 * Solar Dashboard
 *
 * 完整的 Agent 监控面板，支持快捷键操作
 */

import { GridRenderer } from "tvs/termplane/render/grid";
import type { CardLayout } from "tvs/termplane/render/types";

import { SOLAR_LAYOUTS, type SolarLayoutPreset, type LayoutConfig } from "./layouts";
import { AgentStatusWidget } from "./widgets/agent-status";
import { PhaseWidget } from "./widgets/phase";
import { TaskQueueWidget } from "./widgets/task-queue";
import { TokenWidget } from "./widgets/token";
import { LogWidget } from "./widgets/log";
import { KeyboardHandler, renderHelpPanel, type KeyBinding } from "./keyboard";

// ==================== Types ====================

export interface SolarDashboardConfig {
  layout?: SolarLayoutPreset;
  refreshHz?: number;
  width?: number;
  showHeader?: boolean;
  showFooter?: boolean;
  title?: string;
}

// ==================== Dashboard ====================

export class SolarDashboard {
  private config: Required<SolarDashboardConfig>;
  private renderer: GridRenderer;
  private layout: LayoutConfig;
  private layoutPreset: SolarLayoutPreset;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private keyboard: KeyboardHandler;
  private showHelp: boolean = false;
  private paused: boolean = false;

  // Widgets
  private agentWidget = new AgentStatusWidget();
  private phaseWidget = new PhaseWidget();
  private taskWidget = new TaskQueueWidget();
  private tokenWidget = new TokenWidget();
  private logWidget = new LogWidget();

  // Layouts list for cycling
  private layouts: SolarLayoutPreset[] = ["full", "compact", "minimal", "dev", "monitor"];
  private currentLayoutIndex: number = 0;

  constructor(config: SolarDashboardConfig = {}) {
    this.config = {
      layout: config.layout ?? "full",
      refreshHz: config.refreshHz ?? 2,
      width: config.width ?? 100,
      showHeader: config.showHeader ?? true,
      showFooter: config.showFooter ?? true,
      title: config.title ?? "Solar Agent Dashboard",
    };

    this.layoutPreset = this.config.layout;
    this.currentLayoutIndex = this.layouts.indexOf(this.layoutPreset);
    this.layout = SOLAR_LAYOUTS[this.layoutPreset];
    this.renderer = new GridRenderer({
      width: this.config.width,
      columns: this.layout.columns,
      gap: this.layout.gap,
    });

    // 初始化键盘处理
    this.keyboard = new KeyboardHandler();
    this.setupKeyBindings();
  }

  /**
   * 设置快捷键绑定
   */
  private setupKeyBindings(): void {
    const bindings: KeyBinding[] = [
      {
        key: "F1",
        description: "显示/隐藏帮助",
        handler: () => this.toggleHelp(),
      },
      {
        key: "h",
        description: "显示/隐藏帮助",
        handler: () => this.toggleHelp(),
      },
      {
        key: "q",
        description: "退出 Dashboard",
        handler: () => this.quit(),
      },
      {
        key: "c",
        ctrl: true,
        description: "退出 Dashboard",
        handler: () => this.quit(),
      },
      {
        key: "l",
        description: "切换布局 (下一个)",
        handler: () => this.nextLayout(),
      },
      {
        key: "L",
        description: "切换布局 (上一个)",
        handler: () => this.prevLayout(),
      },
      {
        key: "1",
        description: "Full 布局",
        handler: () => this.setLayout("full"),
      },
      {
        key: "2",
        description: "Compact 布局",
        handler: () => this.setLayout("compact"),
      },
      {
        key: "3",
        description: "Minimal 布局",
        handler: () => this.setLayout("minimal"),
      },
      {
        key: "4",
        description: "Dev 布局",
        handler: () => this.setLayout("dev"),
      },
      {
        key: "5",
        description: "Monitor 布局",
        handler: () => this.setLayout("monitor"),
      },
      {
        key: "SPACE",
        description: "暂停/恢复刷新",
        handler: () => this.togglePause(),
      },
      {
        key: "p",
        description: "暂停/恢复刷新",
        handler: () => this.togglePause(),
      },
      {
        key: "r",
        description: "强制刷新",
        handler: () => this.forceRefresh(),
      },
      {
        key: "+",
        description: "加快刷新速度",
        handler: () => this.changeRefreshRate(1),
      },
      {
        key: "-",
        description: "减慢刷新速度",
        handler: () => this.changeRefreshRate(-1),
      },
    ];

    this.keyboard.bindAll(bindings);
  }

  /**
   * 切换帮助显示
   */
  private toggleHelp(): void {
    this.showHelp = !this.showHelp;
    this.forceRefresh();
  }

  /**
   * 切换暂停状态
   */
  private togglePause(): void {
    this.paused = !this.paused;
    this.forceRefresh();
  }

  /**
   * 强制刷新
   */
  private forceRefresh(): void {
    console.log("\x1b[2J\x1b[H");
    console.log(this.render());
  }

  /**
   * 下一个布局
   */
  private nextLayout(): void {
    this.currentLayoutIndex = (this.currentLayoutIndex + 1) % this.layouts.length;
    this.setLayout(this.layouts[this.currentLayoutIndex]);
  }

  /**
   * 上一个布局
   */
  private prevLayout(): void {
    this.currentLayoutIndex = (this.currentLayoutIndex - 1 + this.layouts.length) % this.layouts.length;
    this.setLayout(this.layouts[this.currentLayoutIndex]);
  }

  /**
   * 设置布局
   */
  private setLayout(preset: SolarLayoutPreset): void {
    this.layoutPreset = preset;
    this.currentLayoutIndex = this.layouts.indexOf(preset);
    this.layout = SOLAR_LAYOUTS[preset];
    this.renderer = new GridRenderer({
      width: this.config.width,
      columns: this.layout.columns,
      gap: this.layout.gap,
    });
    this.forceRefresh();
  }

  /**
   * 改变刷新速度
   */
  private changeRefreshRate(delta: number): void {
    const newHz = Math.max(1, Math.min(10, this.config.refreshHz + delta));
    if (newHz !== this.config.refreshHz) {
      this.config.refreshHz = newHz;
      // 重新启动定时器
      if (this.intervalId) {
        clearInterval(this.intervalId);
        this.intervalId = setInterval(() => {
          if (!this.paused) {
            this.forceRefresh();
          }
        }, 1000 / this.config.refreshHz);
      }
      this.forceRefresh();
    }
  }

  /**
   * 退出
   */
  private quit(): void {
    this.stop();
    console.log("\x1b[2J\x1b[H");
    console.log("\n✨ Dashboard stopped. Goodbye!\n");
    process.exit(0);
  }

  /**
   * 渲染 Header Bar
   */
  private renderHeader(): string[] {
    if (!this.config.showHeader) return [];

    const now = new Date().toLocaleTimeString();
    const width = this.config.width;
    const pauseIndicator = this.paused ? " [PAUSED]" : "";
    const layoutIndicator = `[${this.layoutPreset}]`;

    return [
      `\x1b[36m┌${"─".repeat(width - 2)}┐\x1b[0m`,
      `\x1b[36m│ ☀️ ${this.config.title} ${layoutIndicator}${pauseIndicator}`.padEnd(width - 35) + `│ LIVE │ Hz: ${this.config.refreshHz} │ ${now} │\x1b[0m`,
      `\x1b[36m├${"─".repeat(width - 2)}┤\x1b[0m`,
      "",
    ];
  }

  /**
   * 渲染 Footer
   */
  private renderFooter(): string[] {
    if (!this.config.showFooter) return [];

    const width = this.config.width;
    const hint = "F1/h: Help | q: Quit | l: Layout | Space: Pause | +/-: Speed";
    return [
      "",
      `\x1b[90m${"─".repeat(width)}\x1b[0m`,
      `\x1b[90m${hint.padStart(width / 2 + hint.length / 2)}\x1b[0m`,
    ];
  }

  /**
   * 获取 Widget 渲染结果
   */
  private getWidgetCard(widgetId: string): CardLayout {
    switch (widgetId) {
      case "solar.agent.status":
        return this.agentWidget.render(this.agentWidget.mockData());
      case "solar.phase":
        return this.phaseWidget.render(this.phaseWidget.mockData());
      case "solar.task.queue":
        return this.taskWidget.render(this.taskWidget.mockData());
      case "solar.token":
        return this.tokenWidget.render(this.tokenWidget.mockData());
      case "solar.log":
        return this.logWidget.render(this.logWidget.mockData());
      default:
        throw new Error(`Unknown widget: ${widgetId}`);
    }
  }

  /**
   * 渲染一帧
   */
  render(): string {
    const lines: string[] = [];

    // Header
    lines.push(...this.renderHeader());

    // 如果显示帮助，渲染帮助面板
    if (this.showHelp) {
      const helpLines = renderHelpPanel(this.keyboard.getBindings(), 50);
      const padding = Math.floor((this.config.width - 50) / 2);
      for (const line of helpLines) {
        lines.push(" ".repeat(padding) + line);
      }
      lines.push("");
      lines.push(" ".repeat(padding) + "Press any key to close help...");
      return lines.join("\n");
    }

    // 按行分组 Widget
    const rows = new Map<number, Array<{ span: number; lines: string[] }>>();

    for (const placement of this.layout.widgets) {
      const card = this.getWidgetCard(placement.id);
      const cardLines = this.renderer.renderCard(card, placement.span || 1);

      if (!rows.has(placement.row)) {
        rows.set(placement.row, []);
      }
      rows.get(placement.row)!.push({
        span: placement.span || 1,
        lines: cardLines,
      });
    }

    // 渲染每行
    const sortedRows = Array.from(rows.keys()).sort((a, b) => a - b);
    for (const rowNum of sortedRows) {
      const rowCards = rows.get(rowNum)!;
      const rowLines = this.renderer.layoutCards(rowCards);
      lines.push(...rowLines);
      lines.push(""); // 行间距
    }

    // Footer
    lines.push(...this.renderFooter());

    return lines.join("\n");
  }

  /**
   * 启动 Dashboard
   */
  start(): void {
    // 启动键盘监听
    this.keyboard.start();

    console.log("\x1b[2J\x1b[H"); // 清屏
    console.log(this.render());

    this.intervalId = setInterval(() => {
      if (!this.paused) {
        console.log("\x1b[2J\x1b[H"); // 清屏
        console.log(this.render());
      }
    }, 1000 / this.config.refreshHz);

    // 处理退出
    process.on("SIGINT", () => {
      this.quit();
    });
  }

  /**
   * 停止 Dashboard
   */
  stop(): void {
    this.keyboard.stop();
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  /**
   * 渲染一次并返回字符串 (不启动循环)
   */
  renderOnce(): string {
    return this.render();
  }
}
