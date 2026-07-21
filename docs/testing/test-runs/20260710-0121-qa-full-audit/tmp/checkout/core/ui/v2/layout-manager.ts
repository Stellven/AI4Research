/**
 * TUV v2 Layout Manager
 *
 * Manages multi-panel layout with responsive resizing
 */

import type {
  LayoutConfig,
  LayoutPreset,
  PanelConfig,
  PanelId,
  PanelState,
  ResponsiveRule,
  TUVState,
  LAYOUT_IDE,
  LAYOUT_DASHBOARD,
  LAYOUT_FOCUS,
} from "./types";

// ==================== Layout Presets ====================

const PRESETS: Record<LayoutPreset, LayoutConfig> = {
  ide: {
    preset: "ide",
    panels: [
      { id: "header", visible: true, height: 1 },
      { id: "side", visible: true, width: "20%", minWidth: 20, resizable: true, collapsible: true },
      { id: "main", visible: true },
      { id: "bottom", visible: true, height: "30%", minHeight: 5, resizable: true, collapsible: true },
      { id: "statusbar", visible: true, height: 1 },
    ],
    responsive: [
      { maxWidth: 80, changes: { side: { visible: false }, bottom: { height: "20%" } } },
    ],
  },
  dashboard: {
    preset: "dashboard",
    panels: [
      { id: "header", visible: true, height: 1 },
      { id: "main", visible: true },
      { id: "statusbar", visible: true, height: 1 },
    ],
  },
  focus: {
    preset: "focus",
    panels: [{ id: "main", visible: true }],
  },
  split: {
    preset: "split",
    panels: [
      { id: "header", visible: true, height: 1 },
      { id: "side", visible: true, width: "50%", resizable: true },
      { id: "main", visible: true },
      { id: "statusbar", visible: true, height: 1 },
    ],
  },
  minimal: {
    preset: "minimal",
    panels: [
      { id: "main", visible: true },
      { id: "statusbar", visible: true, height: 1 },
    ],
  },
};

// ==================== Layout Manager ====================

export class LayoutManager {
  private state: TUVState;
  private terminalWidth: number;
  private terminalHeight: number;

  constructor(preset: LayoutPreset = "ide", width?: number, height?: number) {
    this.terminalWidth = width ?? process.stdout.columns ?? 120;
    this.terminalHeight = height ?? process.stdout.rows ?? 40;

    this.state = {
      layout: { ...PRESETS[preset] },
      panels: this.initPanelStates(PRESETS[preset]),
      focus: {
        currentPanel: "main",
        history: [],
      },
      theme: DEFAULT_THEME,
      width: this.terminalWidth,
      height: this.terminalHeight,
    };

    this.applyResponsiveRules();
  }

  // ==================== Panel States ====================

  private initPanelStates(layout: LayoutConfig): Record<PanelId, PanelState> {
    const states: Partial<Record<PanelId, PanelState>> = {};

    for (const panel of layout.panels) {
      states[panel.id] = {
        id: panel.id,
        focused: panel.id === "main",
        collapsed: false,
        width: this.resolveSize(panel.width, this.terminalWidth),
        height: this.resolveSize(panel.height, this.terminalHeight),
        scrollOffset: 0,
      };
    }

    // Ensure all panels have state
    const allPanels: PanelId[] = ["main", "side", "bottom", "header", "statusbar"];
    for (const id of allPanels) {
      if (!states[id]) {
        states[id] = {
          id,
          focused: false,
          collapsed: true,
          width: 0,
          height: 0,
          scrollOffset: 0,
        };
      }
    }

    return states as Record<PanelId, PanelState>;
  }

  private resolveSize(size: number | string | undefined, total: number): number {
    if (size === undefined) return 0;
    if (typeof size === "number") return size;
    if (size.endsWith("%")) {
      return Math.floor((parseFloat(size) / 100) * total);
    }
    return parseInt(size, 10);
  }

  // ==================== Responsive ====================

  private applyResponsiveRules(): void {
    const rules = this.state.layout.responsive || [];

    for (const rule of rules) {
      if (this.terminalWidth <= rule.maxWidth) {
        this.applyRule(rule);
      }
    }

    this.recalculateLayout();
  }

  private applyRule(rule: ResponsiveRule): void {
    for (const [panelId, changes] of Object.entries(rule.changes)) {
      const panel = this.state.layout.panels.find((p) => p.id === panelId);
      if (panel) {
        Object.assign(panel, changes);
      }
    }
  }

  // ==================== Layout Calculation ====================

  recalculateLayout(): void {
    const { panels } = this.state.layout;
    const visible = panels.filter((p) => p.visible);

    // Calculate fixed heights (header, statusbar)
    let usedHeight = 0;
    const header = visible.find((p) => p.id === "header");
    const statusbar = visible.find((p) => p.id === "statusbar");
    const bottom = visible.find((p) => p.id === "bottom");

    if (header) {
      const h = this.resolveSize(header.height, this.terminalHeight) || 1;
      this.state.panels.header.height = h;
      usedHeight += h;
    }

    if (statusbar) {
      const h = this.resolveSize(statusbar.height, this.terminalHeight) || 1;
      this.state.panels.statusbar.height = h;
      usedHeight += h;
    }

    if (bottom && !this.state.panels.bottom.collapsed) {
      const h = this.resolveSize(bottom.height, this.terminalHeight);
      this.state.panels.bottom.height = h;
      usedHeight += h;
    }

    // Remaining height for main/side
    const remainingHeight = this.terminalHeight - usedHeight;

    // Calculate widths
    let usedWidth = 0;
    const side = visible.find((p) => p.id === "side");

    if (side && !this.state.panels.side.collapsed) {
      const w = this.resolveSize(side.width, this.terminalWidth);
      this.state.panels.side.width = w;
      this.state.panels.side.height = remainingHeight;
      usedWidth += w;
    }

    // Main gets remaining width
    this.state.panels.main.width = this.terminalWidth - usedWidth;
    this.state.panels.main.height = remainingHeight;

    // Bottom spans full width
    if (bottom) {
      this.state.panels.bottom.width = this.terminalWidth;
    }

    // Header and statusbar span full width
    this.state.panels.header.width = this.terminalWidth;
    this.state.panels.statusbar.width = this.terminalWidth;
  }

  // ==================== Focus Management ====================

  focusPanel(panelId: PanelId): void {
    const panel = this.state.layout.panels.find((p) => p.id === panelId);
    if (!panel?.visible) return;

    // Update focus state
    this.state.focus.history.push(this.state.focus.currentPanel);
    if (this.state.focus.history.length > 10) {
      this.state.focus.history.shift();
    }

    // Update panel states
    for (const id of Object.keys(this.state.panels) as PanelId[]) {
      this.state.panels[id].focused = id === panelId;
    }

    this.state.focus.currentPanel = panelId;
  }

  focusPrevious(): void {
    const prev = this.state.focus.history.pop();
    if (prev) {
      this.focusPanel(prev);
    }
  }

  cycleFocus(direction: "next" | "prev"): void {
    const visible = this.state.layout.panels
      .filter((p) => p.visible && !["header", "statusbar"].includes(p.id))
      .map((p) => p.id);

    const currentIdx = visible.indexOf(this.state.focus.currentPanel);
    if (currentIdx === -1) {
      this.focusPanel(visible[0]);
      return;
    }

    const nextIdx =
      direction === "next"
        ? (currentIdx + 1) % visible.length
        : (currentIdx - 1 + visible.length) % visible.length;

    this.focusPanel(visible[nextIdx]);
  }

  // ==================== Panel Operations ====================

  togglePanel(panelId: PanelId): void {
    const panel = this.state.layout.panels.find((p) => p.id === panelId);
    if (!panel?.collapsible) return;

    this.state.panels[panelId].collapsed = !this.state.panels[panelId].collapsed;
    this.recalculateLayout();

    // If collapsed focused panel, move focus
    if (this.state.panels[panelId].collapsed && this.state.focus.currentPanel === panelId) {
      this.focusPanel("main");
    }
  }

  resizePanel(panelId: PanelId, delta: number): void {
    const panel = this.state.layout.panels.find((p) => p.id === panelId);
    if (!panel?.resizable) return;

    const state = this.state.panels[panelId];
    const isHorizontal = panelId === "side";
    const currentSize = isHorizontal ? state.width : state.height;
    const minSize = isHorizontal ? (panel.minWidth ?? 10) : (panel.minHeight ?? 3);
    const maxSize = isHorizontal ? this.terminalWidth * 0.5 : this.terminalHeight * 0.7;

    const newSize = Math.max(minSize, Math.min(maxSize, currentSize + delta));

    if (isHorizontal) {
      state.width = newSize;
    } else {
      state.height = newSize;
    }

    this.recalculateLayout();
  }

  setLayout(preset: LayoutPreset): void {
    this.state.layout = { ...PRESETS[preset] };
    this.state.panels = this.initPanelStates(this.state.layout);
    this.applyResponsiveRules();
    this.focusPanel("main");
  }

  // ==================== State Access ====================

  getState(): TUVState {
    return this.state;
  }

  getPanelState(panelId: PanelId): PanelState {
    return this.state.panels[panelId];
  }

  getVisiblePanels(): PanelState[] {
    return this.state.layout.panels
      .filter((p) => p.visible && !this.state.panels[p.id].collapsed)
      .map((p) => this.state.panels[p.id]);
  }

  getFocusedPanel(): PanelId {
    return this.state.focus.currentPanel;
  }

  // ==================== Terminal Resize ====================

  handleResize(width: number, height: number): void {
    this.terminalWidth = width;
    this.terminalHeight = height;
    this.state.width = width;
    this.state.height = height;
    this.applyResponsiveRules();
  }

  // ==================== Render Regions ====================

  /**
   * Get render regions for each panel
   * Returns { panelId: { x, y, width, height } }
   */
  getRenderRegions(): Record<PanelId, { x: number; y: number; width: number; height: number }> {
    const regions: Record<PanelId, { x: number; y: number; width: number; height: number }> = {
      header: { x: 0, y: 0, width: 0, height: 0 },
      side: { x: 0, y: 0, width: 0, height: 0 },
      main: { x: 0, y: 0, width: 0, height: 0 },
      bottom: { x: 0, y: 0, width: 0, height: 0 },
      statusbar: { x: 0, y: 0, width: 0, height: 0 },
    };

    let y = 0;

    // Header
    if (this.state.panels.header.height > 0) {
      regions.header = {
        x: 0,
        y,
        width: this.state.panels.header.width,
        height: this.state.panels.header.height,
      };
      y += this.state.panels.header.height;
    }

    // Side + Main (same row)
    const sideState = this.state.panels.side;
    const mainState = this.state.panels.main;

    if (sideState.width > 0 && !sideState.collapsed) {
      regions.side = {
        x: 0,
        y,
        width: sideState.width,
        height: sideState.height,
      };
      regions.main = {
        x: sideState.width,
        y,
        width: mainState.width,
        height: mainState.height,
      };
    } else {
      regions.main = {
        x: 0,
        y,
        width: this.terminalWidth,
        height: mainState.height,
      };
    }

    y += mainState.height;

    // Bottom
    const bottomState = this.state.panels.bottom;
    if (bottomState.height > 0 && !bottomState.collapsed) {
      regions.bottom = {
        x: 0,
        y,
        width: bottomState.width,
        height: bottomState.height,
      };
      y += bottomState.height;
    }

    // StatusBar
    if (this.state.panels.statusbar.height > 0) {
      regions.statusbar = {
        x: 0,
        y,
        width: this.state.panels.statusbar.width,
        height: this.state.panels.statusbar.height,
      };
    }

    return regions;
  }
}

// ==================== Default Theme ====================

const DEFAULT_THEME = {
  name: "solar",
  colors: {
    background: "#1a1a2e",
    foreground: "#eaeaea",
    primary: "#f9a825",
    secondary: "#7c4dff",
    accent: "#00bcd4",
    success: "#4caf50",
    warning: "#ff9800",
    error: "#f44336",
    border: "#3d3d5c",
    selection: "#3d3d5c",
    focusBorder: "#f9a825",
  },
  borders: {
    normal: "single",
    focused: "double",
  },
};

// ==================== Factory ====================

export function createLayoutManager(preset: LayoutPreset = "ide"): LayoutManager {
  return new LayoutManager(preset);
}
