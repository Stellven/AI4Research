/**
 * TUV v2 Components
 *
 * Rich UI components for Solar AI OS
 */

export { TreeView, createTreeView, pathsToTree } from "./tree-view";
export type { TreeRenderOptions, TreeState, FlatTreeNode } from "./tree-view";

export { DiffViewer, createDiffViewer, parseUnifiedDiff, diffStrings } from "./diff-viewer";
export type { DiffStats, ParsedDiff } from "./diff-viewer";

export {
  CommandPalette,
  createCommandPalette,
  createSolarCommandPalette,
  SOLAR_COMMANDS,
} from "./command-palette";
export type { CommandMatch, CommandPaletteState } from "./command-palette";
