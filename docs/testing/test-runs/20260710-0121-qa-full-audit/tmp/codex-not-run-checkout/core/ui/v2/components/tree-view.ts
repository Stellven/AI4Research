/**
 * TUV v2 TreeView Component
 *
 * Hierarchical tree display for files, tasks, etc.
 * Generates VDL-compatible semantic IR.
 */

import type { TreeNode, TreeViewConfig } from "../types";

// ==================== Types ====================

export interface TreeRenderOptions {
  indent?: number;
  showIcons?: boolean;
  showLines?: boolean;
  maxDepth?: number;
  expandedIds?: Set<string>;
  selectedId?: string;
  focusedId?: string;
}

export interface TreeState {
  expanded: Set<string>;
  selected: string | null;
  focused: string | null;
  flatNodes: FlatTreeNode[];
}

export interface FlatTreeNode {
  node: TreeNode;
  depth: number;
  isLast: boolean;
  parentIsLast: boolean[];
}

// ==================== Icons ====================

const ICONS: Record<string, string> = {
  folder: "📁",
  folderOpen: "📂",
  file: "📄",
  typescript: "🔷",
  javascript: "🟨",
  json: "📋",
  markdown: "📝",
  git: "🔀",
  config: "⚙️",
  test: "🧪",
  agent: "🤖",
  task: "✅",
  taskPending: "⏳",
  taskDone: "✓",
  error: "❌",
  warning: "⚠️",
  info: "ℹ️",
};

// ==================== Line Characters ====================

const LINE_CHARS = {
  vertical: "│",
  horizontal: "─",
  corner: "└",
  tee: "├",
  space: " ",
};

// ==================== TreeView Class ====================

export class TreeView {
  private state: TreeState;
  private config: TreeViewConfig;

  constructor(config: TreeViewConfig) {
    this.config = config;
    this.state = {
      expanded: new Set(),
      selected: null,
      focused: null,
      flatNodes: [],
    };

    // Initialize expanded nodes
    this.initExpanded(config.root);
    this.flatten();
  }

  private initExpanded(node: TreeNode, depth = 0): void {
    if (node.expanded && node.children?.length) {
      this.state.expanded.add(node.id);
    }
    if (node.children) {
      for (const child of node.children) {
        this.initExpanded(child, depth + 1);
      }
    }
  }

  // ==================== State Management ====================

  toggle(nodeId: string): void {
    if (this.state.expanded.has(nodeId)) {
      this.state.expanded.delete(nodeId);
    } else {
      this.state.expanded.add(nodeId);
    }
    this.flatten();
    this.config.onExpand?.(this.findNode(nodeId)!);
  }

  select(nodeId: string): void {
    this.state.selected = nodeId;
    const node = this.findNode(nodeId);
    if (node) {
      this.config.onSelect?.(node);
    }
  }

  focus(nodeId: string): void {
    this.state.focused = nodeId;
  }

  expandAll(): void {
    this.traverseAll((node) => {
      if (node.children?.length) {
        this.state.expanded.add(node.id);
      }
    });
    this.flatten();
  }

  collapseAll(): void {
    this.state.expanded.clear();
    this.flatten();
  }

  // ==================== Navigation ====================

  moveFocus(direction: "up" | "down" | "parent" | "firstChild"): void {
    const { flatNodes, focused } = this.state;
    if (!flatNodes.length) return;

    const currentIdx = flatNodes.findIndex((n) => n.node.id === focused);

    switch (direction) {
      case "up":
        if (currentIdx > 0) {
          this.state.focused = flatNodes[currentIdx - 1].node.id;
        }
        break;
      case "down":
        if (currentIdx < flatNodes.length - 1) {
          this.state.focused = flatNodes[currentIdx + 1].node.id;
        } else if (currentIdx === -1) {
          this.state.focused = flatNodes[0].node.id;
        }
        break;
      case "parent":
        const current = flatNodes[currentIdx];
        if (current && current.depth > 0) {
          // Find parent by looking backwards for node with depth - 1
          for (let i = currentIdx - 1; i >= 0; i--) {
            if (flatNodes[i].depth === current.depth - 1) {
              this.state.focused = flatNodes[i].node.id;
              break;
            }
          }
        }
        break;
      case "firstChild":
        const focusedNode = this.findNode(focused!);
        if (focusedNode?.children?.length && this.state.expanded.has(focusedNode.id)) {
          this.state.focused = focusedNode.children[0].id;
        }
        break;
    }
  }

  // ==================== Flattening ====================

  private flatten(): void {
    this.state.flatNodes = [];
    this.flattenNode(this.config.root, 0, true, []);
  }

  private flattenNode(
    node: TreeNode,
    depth: number,
    isLast: boolean,
    parentIsLast: boolean[]
  ): void {
    this.state.flatNodes.push({
      node,
      depth,
      isLast,
      parentIsLast: [...parentIsLast],
    });

    if (node.children?.length && this.state.expanded.has(node.id)) {
      const children = node.children;
      for (let i = 0; i < children.length; i++) {
        this.flattenNode(children[i], depth + 1, i === children.length - 1, [
          ...parentIsLast,
          isLast,
        ]);
      }
    }
  }

  private findNode(id: string, node: TreeNode = this.config.root): TreeNode | null {
    if (node.id === id) return node;
    if (node.children) {
      for (const child of node.children) {
        const found = this.findNode(id, child);
        if (found) return found;
      }
    }
    return null;
  }

  private traverseAll(fn: (node: TreeNode) => void, node: TreeNode = this.config.root): void {
    fn(node);
    if (node.children) {
      for (const child of node.children) {
        this.traverseAll(fn, child);
      }
    }
  }

  // ==================== Rendering ====================

  /**
   * Render to VDL-compatible structure
   */
  toVDL(): object {
    const items = this.state.flatNodes.map((flat) => this.renderNodeToVDL(flat));

    return {
      type: "list",
      variant: "none",
      items,
    };
  }

  private renderNodeToVDL(flat: FlatTreeNode): object {
    const { node, depth, isLast, parentIsLast } = flat;
    const isExpanded = this.state.expanded.has(node.id);
    const hasChildren = (node.children?.length ?? 0) > 0;
    const isSelected = this.state.selected === node.id;
    const isFocused = this.state.focused === node.id;

    // Build prefix
    let prefix = "";
    if (this.config.showLines && depth > 0) {
      for (let i = 0; i < depth - 1; i++) {
        prefix += parentIsLast[i] ? "  " : LINE_CHARS.vertical + " ";
      }
      prefix += isLast ? LINE_CHARS.corner + LINE_CHARS.horizontal : LINE_CHARS.tee + LINE_CHARS.horizontal;
    } else {
      prefix = "  ".repeat(depth);
    }

    // Build icon
    let icon = "";
    if (this.config.showIcons) {
      if (node.icon && ICONS[node.icon]) {
        icon = ICONS[node.icon] + " ";
      } else if (hasChildren) {
        icon = (isExpanded ? ICONS.folderOpen : ICONS.folder) + " ";
      } else {
        icon = ICONS.file + " ";
      }
    }

    // Expand indicator
    const expandIndicator = hasChildren ? (isExpanded ? "▼ " : "▶ ") : "  ";

    return {
      type: "text",
      content: prefix + expandIndicator + icon + node.label,
      emphasis: isFocused ? "bold" : isSelected ? "underline" : undefined,
      color: isFocused ? "primary" : isSelected ? "accent" : undefined,
      meta: { nodeId: node.id, selectable: true },
    };
  }

  /**
   * Render to plain text lines
   */
  render(options: TreeRenderOptions = {}): string[] {
    const lines: string[] = [];
    const { showIcons = this.config.showIcons, showLines = this.config.showLines } = options;

    for (const flat of this.state.flatNodes) {
      const { node, depth, isLast, parentIsLast } = flat;
      const isExpanded = this.state.expanded.has(node.id);
      const hasChildren = (node.children?.length ?? 0) > 0;
      const isSelected = this.state.selected === node.id;
      const isFocused = this.state.focused === node.id;

      // Build line
      let line = "";

      // Tree lines
      if (showLines && depth > 0) {
        for (let i = 0; i < depth - 1; i++) {
          line += parentIsLast[i] ? "  " : LINE_CHARS.vertical + " ";
        }
        line += isLast ? LINE_CHARS.corner + LINE_CHARS.horizontal : LINE_CHARS.tee + LINE_CHARS.horizontal;
      } else {
        line = "  ".repeat(depth);
      }

      // Expand indicator
      line += hasChildren ? (isExpanded ? "▼ " : "▶ ") : "  ";

      // Icon
      if (showIcons && node.icon && ICONS[node.icon]) {
        line += ICONS[node.icon] + " ";
      }

      // Label
      line += node.label;

      // Focus/selection indicator
      if (isFocused) {
        line = "» " + line.slice(2);
      } else if (isSelected) {
        line = "• " + line.slice(2);
      }

      lines.push(line);
    }

    return lines;
  }

  // ==================== State Access ====================

  getState(): TreeState {
    return this.state;
  }

  getFlatNodes(): FlatTreeNode[] {
    return this.state.flatNodes;
  }

  getVisibleCount(): number {
    return this.state.flatNodes.length;
  }
}

// ==================== Factory ====================

export function createTreeView(config: TreeViewConfig): TreeView {
  return new TreeView(config);
}

// ==================== Helpers ====================

/**
 * Create file tree from file paths
 */
export function pathsToTree(paths: string[], rootLabel = "root"): TreeNode {
  const root: TreeNode = {
    id: "root",
    label: rootLabel,
    icon: "folder",
    children: [],
    expanded: true,
  };

  for (const path of paths) {
    const parts = path.split("/").filter(Boolean);
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      const id = parts.slice(0, i + 1).join("/");

      let child = current.children?.find((c) => c.label === part);
      if (!child) {
        child = {
          id,
          label: part,
          icon: isFile ? getFileIcon(part) : "folder",
          children: isFile ? undefined : [],
          expanded: !isFile && i < 2, // Auto-expand first 2 levels
        };
        current.children = current.children || [];
        current.children.push(child);
      }
      current = child;
    }
  }

  // Sort: folders first, then alphabetically
  sortTree(root);
  return root;
}

function sortTree(node: TreeNode): void {
  if (!node.children?.length) return;

  node.children.sort((a, b) => {
    const aIsFolder = (a.children?.length ?? 0) > 0;
    const bIsFolder = (b.children?.length ?? 0) > 0;
    if (aIsFolder !== bIsFolder) return aIsFolder ? -1 : 1;
    return a.label.localeCompare(b.label);
  });

  for (const child of node.children) {
    sortTree(child);
  }
}

function getFileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase();
  const iconMap: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    json: "json",
    md: "markdown",
    test: "test",
    spec: "test",
  };

  if (filename.includes(".test.") || filename.includes(".spec.")) {
    return "test";
  }

  return iconMap[ext ?? ""] || "file";
}
