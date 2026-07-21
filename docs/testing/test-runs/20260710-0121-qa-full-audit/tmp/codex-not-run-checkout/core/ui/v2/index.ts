/**
 * TUV v2 - Terminal UI for Solar AI OS
 *
 * Multi-panel layout system with rich components
 *
 * Architecture:
 * - TVS VDL Compiler: Semantic IR → Layout DSL → Character Grid
 * - Layout Manager: Multi-panel responsive layout
 * - Components: TreeView, DiffViewer, CommandPalette
 * - Runtime: Input handling, rendering loop
 *
 * @example
 * ```typescript
 * import { createTUVRuntime } from 'solar/core/ui/v2';
 *
 * const runtime = createTUVRuntime({
 *   layout: 'ide',
 *   title: 'My Project',
 * });
 *
 * runtime.setPanelContent('side', {
 *   lines: ['File 1', 'File 2', 'File 3'],
 * });
 *
 * await runtime.start();
 * ```
 */

// ==================== Types ====================

export type {
  // Panel system
  PanelId,
  PanelConfig,
  PanelState,
  PanelPosition,

  // Layout system
  LayoutPreset,
  LayoutConfig,
  ResponsiveRule,

  // Components
  ComponentType,
  ComponentConfig,
  TreeNode,
  TreeViewConfig,
  TableColumn,
  DataTableConfig,
  DiffLine,
  DiffLineType,
  DiffHunk,
  DiffViewerConfig,
  Command,
  CommandPaletteConfig,

  // Keyboard
  KeyBinding,
  KeymapConfig,

  // Focus
  FocusState,

  // Theme
  TUVTheme,

  // State
  TUVState,
} from "./types";

// ==================== Layout ====================

export { LayoutManager, createLayoutManager } from "./layout-manager";

// ==================== Components ====================

export {
  TreeView,
  createTreeView,
  pathsToTree,
} from "./components/tree-view";

export {
  DiffViewer,
  createDiffViewer,
  parseUnifiedDiff,
  diffStrings,
} from "./components/diff-viewer";

export {
  CommandPalette,
  createCommandPalette,
  createSolarCommandPalette,
  SOLAR_COMMANDS,
} from "./components/command-palette";

// ==================== Runtime ====================

export { TUVRuntime, createTUVRuntime } from "./runtime";
export type { TUVRuntimeConfig, PanelContent } from "./runtime";

// ==================== Quick Start ====================

/**
 * Quick start TUV with Solar defaults
 */
export async function startSolarUI(options?: {
  layout?: LayoutPreset;
  title?: string;
}): Promise<TUVRuntime> {
  const { createTUVRuntime } = await import("./runtime");

  const runtime = createTUVRuntime({
    layout: options?.layout ?? "ide",
    title: options?.title ?? "☀️ Solar AI OS",
    refreshInterval: 1000,
  });

  // Set default content
  runtime.setPanelContent("main", {
    lines: [
      "",
      "  Welcome to Solar AI OS",
      "",
      "  Quick Start:",
      "    Ctrl+Shift+P  Command Palette",
      "    Tab           Cycle Panels",
      "    Ctrl+B        Toggle Sidebar",
      "    Ctrl+`        Toggle Terminal",
      "    Ctrl+Q        Quit",
      "",
      "  Layouts:",
      "    Ctrl+1        IDE Layout",
      "    Ctrl+2        Dashboard Layout",
      "    Ctrl+3        Focus Layout",
      "",
    ],
  });

  runtime.setPanelContent("side", {
    lines: [
      " 📁 Project",
      " ├── 📁 src",
      " │   ├── 📄 index.ts",
      " │   └── 📁 core",
      " ├── 📁 tests",
      " └── 📄 package.json",
    ],
  });

  runtime.setPanelContent("bottom", {
    lines: [
      " [LOG] Solar initialized",
      " [INFO] Ready for commands",
    ],
  });

  await runtime.start();
  return runtime;
}
