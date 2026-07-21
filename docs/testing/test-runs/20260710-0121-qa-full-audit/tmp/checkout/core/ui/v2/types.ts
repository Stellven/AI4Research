/**
 * TUV v2 Type Definitions
 *
 * Multi-panel Terminal UI for Solar AI OS
 */

// ==================== Panel System ====================

export type PanelId = "main" | "side" | "bottom" | "header" | "statusbar";

export type PanelPosition = "left" | "right" | "top" | "bottom" | "center";

export interface PanelConfig {
  id: PanelId;
  visible: boolean;
  width?: number | string; // number = chars, string = percentage
  height?: number | string;
  minWidth?: number;
  minHeight?: number;
  resizable?: boolean;
  collapsible?: boolean;
}

export interface PanelState {
  id: PanelId;
  focused: boolean;
  collapsed: boolean;
  width: number;
  height: number;
  scrollOffset: number;
}

// ==================== Layout System ====================

export type LayoutPreset = "ide" | "dashboard" | "focus" | "split" | "minimal";

export interface LayoutConfig {
  preset: LayoutPreset;
  panels: PanelConfig[];
  responsive?: ResponsiveRule[];
}

export interface ResponsiveRule {
  maxWidth: number;
  changes: Partial<Record<PanelId, Partial<PanelConfig>>>;
}

/**
 * IDE Layout:
 * ┌────────────────────────────────────────────────┐
 * │                    Header                      │
 * ├─────────────┬────────────────────┬─────────────┤
 * │             │                    │             │
 * │    Side     │       Main         │    Side     │
 * │   (left)    │                    │   (right)   │
 * │             │                    │             │
 * ├─────────────┴────────────────────┴─────────────┤
 * │                   Bottom                       │
 * ├────────────────────────────────────────────────┤
 * │                  StatusBar                     │
 * └────────────────────────────────────────────────┘
 */
export const LAYOUT_IDE: LayoutConfig = {
  preset: "ide",
  panels: [
    { id: "header", visible: true, height: 1 },
    { id: "side", visible: true, width: "20%", minWidth: 20, resizable: true, collapsible: true },
    { id: "main", visible: true },
    { id: "bottom", visible: true, height: "30%", minHeight: 5, resizable: true, collapsible: true },
    { id: "statusbar", visible: true, height: 1 },
  ],
  responsive: [
    {
      maxWidth: 80,
      changes: {
        side: { visible: false },
        bottom: { height: "20%" },
      },
    },
  ],
};

/**
 * Dashboard Layout:
 * ┌────────────────────────────────────────────────┐
 * │                    Header                      │
 * ├────────────────────────────────────────────────┤
 * │                                                │
 * │                    Main                        │
 * │               (Grid Layout)                    │
 * │                                                │
 * ├────────────────────────────────────────────────┤
 * │                  StatusBar                     │
 * └────────────────────────────────────────────────┘
 */
export const LAYOUT_DASHBOARD: LayoutConfig = {
  preset: "dashboard",
  panels: [
    { id: "header", visible: true, height: 1 },
    { id: "main", visible: true },
    { id: "statusbar", visible: true, height: 1 },
  ],
};

/**
 * Focus Layout - Minimal distraction:
 * ┌────────────────────────────────────────────────┐
 * │                                                │
 * │                    Main                        │
 * │                                                │
 * └────────────────────────────────────────────────┘
 */
export const LAYOUT_FOCUS: LayoutConfig = {
  preset: "focus",
  panels: [{ id: "main", visible: true }],
};

// ==================== Component System ====================

export type ComponentType =
  | "tree-view"
  | "data-table"
  | "code-editor"
  | "diff-viewer"
  | "log-viewer"
  | "command-palette"
  | "file-browser"
  | "agent-monitor"
  | "task-list"
  | "metrics-panel";

export interface ComponentConfig {
  type: ComponentType;
  id: string;
  title?: string;
  data?: unknown;
  options?: Record<string, unknown>;
}

// ==================== Tree View ====================

export interface TreeNode {
  id: string;
  label: string;
  icon?: string;
  children?: TreeNode[];
  expanded?: boolean;
  selected?: boolean;
  data?: unknown;
}

export interface TreeViewConfig {
  root: TreeNode;
  showIcons?: boolean;
  showLines?: boolean;
  multiSelect?: boolean;
  onSelect?: (node: TreeNode) => void;
  onExpand?: (node: TreeNode) => void;
}

// ==================== Data Table ====================

export interface TableColumn {
  key: string;
  header: string;
  width?: number | string;
  align?: "left" | "center" | "right";
  format?: (value: unknown) => string;
}

export interface DataTableConfig {
  columns: TableColumn[];
  rows: Record<string, unknown>[];
  sortable?: boolean;
  selectable?: boolean;
  pageSize?: number;
  onSelect?: (row: Record<string, unknown>) => void;
}

// ==================== Diff Viewer ====================

export type DiffLineType = "unchanged" | "added" | "removed" | "modified";

export interface DiffLine {
  type: DiffLineType;
  lineNumber: { old?: number; new?: number };
  content: string;
}

export interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

export interface DiffViewerConfig {
  title: string;
  hunks: DiffHunk[];
  sideBySide?: boolean;
  showLineNumbers?: boolean;
}

// ==================== Command Palette ====================

export interface Command {
  id: string;
  label: string;
  shortcut?: string;
  category?: string;
  action: () => void | Promise<void>;
}

export interface CommandPaletteConfig {
  commands: Command[];
  placeholder?: string;
  maxVisible?: number;
}

// ==================== Keyboard ====================

export interface KeyBinding {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  meta?: boolean;
  action: string;
  scope?: PanelId | "global";
}

export interface KeymapConfig {
  bindings: KeyBinding[];
  mode?: "normal" | "insert" | "visual"; // Vim modes
}

// ==================== Focus Management ====================

export interface FocusState {
  currentPanel: PanelId;
  currentComponent?: string;
  history: PanelId[];
}

// ==================== Theme ====================

export interface TUVTheme {
  name: string;
  colors: {
    background: string;
    foreground: string;
    primary: string;
    secondary: string;
    accent: string;
    success: string;
    warning: string;
    error: string;
    border: string;
    selection: string;
    focusBorder: string;
  };
  borders: {
    normal: string; // e.g., "single", "double", "rounded"
    focused: string;
  };
}

// ==================== Runtime State ====================

export interface TUVState {
  layout: LayoutConfig;
  panels: Record<PanelId, PanelState>;
  focus: FocusState;
  theme: TUVTheme;
  width: number;
  height: number;
}
