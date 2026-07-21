/**
 * TUV v2 DiffViewer Component
 *
 * Display git-style diffs with syntax highlighting
 * Generates VDL-compatible semantic IR.
 */

import type { DiffLine, DiffHunk, DiffViewerConfig, DiffLineType } from "../types";

// ==================== Types ====================

export interface DiffStats {
  additions: number;
  deletions: number;
  changes: number;
}

export interface ParsedDiff {
  title: string;
  hunks: DiffHunk[];
  stats: DiffStats;
}

// ==================== Colors ====================

const DIFF_COLORS: Record<DiffLineType, string> = {
  added: "success",
  removed: "error",
  modified: "warning",
  unchanged: "muted",
};

const DIFF_PREFIXES: Record<DiffLineType, string> = {
  added: "+",
  removed: "-",
  modified: "~",
  unchanged: " ",
};

// ==================== DiffViewer Class ====================

export class DiffViewer {
  private config: DiffViewerConfig;
  private scrollOffset = 0;
  private focusedHunk = 0;

  constructor(config: DiffViewerConfig) {
    this.config = config;
  }

  // ==================== Navigation ====================

  nextHunk(): void {
    if (this.focusedHunk < this.config.hunks.length - 1) {
      this.focusedHunk++;
    }
  }

  prevHunk(): void {
    if (this.focusedHunk > 0) {
      this.focusedHunk--;
    }
  }

  scrollTo(offset: number): void {
    this.scrollOffset = Math.max(0, offset);
  }

  // ==================== Stats ====================

  getStats(): DiffStats {
    let additions = 0;
    let deletions = 0;
    let changes = 0;

    for (const hunk of this.config.hunks) {
      for (const line of hunk.lines) {
        switch (line.type) {
          case "added":
            additions++;
            break;
          case "removed":
            deletions++;
            break;
          case "modified":
            changes++;
            break;
        }
      }
    }

    return { additions, deletions, changes };
  }

  // ==================== Rendering ====================

  /**
   * Render to VDL-compatible structure
   */
  toVDL(): object {
    const sections: object[] = [];

    // Title and stats
    const stats = this.getStats();
    sections.push({
      type: "kv",
      items: [
        { key: "File", value: this.config.title },
        { key: "Changes", value: `+${stats.additions} -${stats.deletions}`, status: stats.additions > stats.deletions ? "success" : "error" },
      ],
    });

    // Hunks
    for (let i = 0; i < this.config.hunks.length; i++) {
      const hunk = this.config.hunks[i];
      const isFocused = i === this.focusedHunk;

      sections.push({
        type: "divider",
        label: hunk.header,
        emphasis: isFocused ? "bold" : undefined,
      });

      const lines = hunk.lines.map((line) => this.lineToVDL(line));
      sections.push({
        type: "code",
        language: "diff",
        lines,
        showLineNumbers: this.config.showLineNumbers,
      });
    }

    return {
      type: "card",
      header: `📊 ${this.config.title}`,
      sections,
    };
  }

  private lineToVDL(line: DiffLine): object {
    const prefix = DIFF_PREFIXES[line.type];
    const lineNum = this.formatLineNumber(line.lineNumber);

    return {
      type: "text",
      content: `${lineNum} ${prefix} ${line.content}`,
      color: DIFF_COLORS[line.type],
    };
  }

  private formatLineNumber(lineNum: { old?: number; new?: number }): string {
    if (this.config.sideBySide) {
      const old = lineNum.old?.toString().padStart(4) ?? "    ";
      const new_ = lineNum.new?.toString().padStart(4) ?? "    ";
      return `${old} ${new_}`;
    }
    return (lineNum.new ?? lineNum.old ?? "").toString().padStart(4);
  }

  /**
   * Render to plain text lines
   */
  render(width = 80): string[] {
    const lines: string[] = [];
    const stats = this.getStats();

    // Header
    lines.push(`━━━ ${this.config.title} ━━━`);
    lines.push(`+${stats.additions} additions, -${stats.deletions} deletions`);
    lines.push("");

    // Hunks
    for (let i = 0; i < this.config.hunks.length; i++) {
      const hunk = this.config.hunks[i];
      const isFocused = i === this.focusedHunk;

      // Hunk header
      const headerLine = isFocused ? `▶ ${hunk.header}` : `  ${hunk.header}`;
      lines.push(headerLine);

      // Lines
      for (const line of hunk.lines) {
        const prefix = DIFF_PREFIXES[line.type];
        const lineNum = this.formatLineNumber(line.lineNumber);
        const content = line.content.slice(0, width - 10);
        lines.push(`${lineNum} ${prefix} ${content}`);
      }

      lines.push("");
    }

    return lines;
  }

  /**
   * Render unified diff format
   */
  renderUnified(): string[] {
    const lines: string[] = [];

    lines.push(`--- a/${this.config.title}`);
    lines.push(`+++ b/${this.config.title}`);

    for (const hunk of this.config.hunks) {
      lines.push(hunk.header);
      for (const line of hunk.lines) {
        const prefix = DIFF_PREFIXES[line.type];
        lines.push(`${prefix}${line.content}`);
      }
    }

    return lines;
  }

  /**
   * Render side-by-side format
   */
  renderSideBySide(width = 80): string[] {
    const halfWidth = Math.floor((width - 3) / 2);
    const lines: string[] = [];
    const stats = this.getStats();

    // Header
    lines.push("─".repeat(halfWidth) + "┬" + "─".repeat(halfWidth));
    lines.push(
      " Old".padEnd(halfWidth) + "│" + " New".padEnd(halfWidth)
    );
    lines.push("─".repeat(halfWidth) + "┼" + "─".repeat(halfWidth));

    for (const hunk of this.config.hunks) {
      // Group lines for side-by-side display
      const leftLines: DiffLine[] = [];
      const rightLines: DiffLine[] = [];

      for (const line of hunk.lines) {
        if (line.type === "removed") {
          leftLines.push(line);
        } else if (line.type === "added") {
          rightLines.push(line);
        } else {
          // Unchanged - sync both sides
          while (leftLines.length < rightLines.length) {
            leftLines.push({ type: "unchanged", lineNumber: {}, content: "" });
          }
          while (rightLines.length < leftLines.length) {
            rightLines.push({ type: "unchanged", lineNumber: {}, content: "" });
          }
          leftLines.push(line);
          rightLines.push(line);
        }
      }

      // Pad to same length
      while (leftLines.length < rightLines.length) {
        leftLines.push({ type: "unchanged", lineNumber: {}, content: "" });
      }
      while (rightLines.length < leftLines.length) {
        rightLines.push({ type: "unchanged", lineNumber: {}, content: "" });
      }

      // Render paired lines
      for (let i = 0; i < leftLines.length; i++) {
        const left = this.formatSideLine(leftLines[i], halfWidth - 1);
        const right = this.formatSideLine(rightLines[i], halfWidth - 1);
        lines.push(`${left}│${right}`);
      }
    }

    lines.push("─".repeat(halfWidth) + "┴" + "─".repeat(halfWidth));
    return lines;
  }

  private formatSideLine(line: DiffLine, width: number): string {
    const prefix = DIFF_PREFIXES[line.type];
    const num = (line.lineNumber.old ?? line.lineNumber.new ?? "").toString().padStart(4);
    const content = line.content.slice(0, width - 6);
    return `${num} ${prefix}${content}`.padEnd(width);
  }
}

// ==================== Factory ====================

export function createDiffViewer(config: DiffViewerConfig): DiffViewer {
  return new DiffViewer(config);
}

// ==================== Parser ====================

/**
 * Parse unified diff format
 */
export function parseUnifiedDiff(diff: string, title = "file"): ParsedDiff {
  const lines = diff.split("\n");
  const hunks: DiffHunk[] = [];
  let currentHunk: DiffHunk | null = null;
  let oldLine = 0;
  let newLine = 0;

  for (const line of lines) {
    // Hunk header: @@ -1,3 +1,4 @@
    if (line.startsWith("@@")) {
      if (currentHunk) {
        hunks.push(currentHunk);
      }
      currentHunk = { header: line, lines: [] };

      // Parse line numbers
      const match = line.match(/@@ -(\d+),?\d* \+(\d+),?\d* @@/);
      if (match) {
        oldLine = parseInt(match[1], 10);
        newLine = parseInt(match[2], 10);
      }
      continue;
    }

    if (!currentHunk) continue;

    // Diff lines
    if (line.startsWith("+") && !line.startsWith("+++")) {
      currentHunk.lines.push({
        type: "added",
        lineNumber: { new: newLine++ },
        content: line.slice(1),
      });
    } else if (line.startsWith("-") && !line.startsWith("---")) {
      currentHunk.lines.push({
        type: "removed",
        lineNumber: { old: oldLine++ },
        content: line.slice(1),
      });
    } else if (line.startsWith(" ")) {
      currentHunk.lines.push({
        type: "unchanged",
        lineNumber: { old: oldLine++, new: newLine++ },
        content: line.slice(1),
      });
    }
  }

  if (currentHunk) {
    hunks.push(currentHunk);
  }

  // Calculate stats
  let additions = 0;
  let deletions = 0;
  for (const hunk of hunks) {
    for (const line of hunk.lines) {
      if (line.type === "added") additions++;
      if (line.type === "removed") deletions++;
    }
  }

  return {
    title,
    hunks,
    stats: { additions, deletions, changes: 0 },
  };
}

/**
 * Create diff from two strings
 */
export function diffStrings(oldStr: string, newStr: string, title = "file"): ParsedDiff {
  const oldLines = oldStr.split("\n");
  const newLines = newStr.split("\n");
  const diffLines: DiffLine[] = [];

  // Simple line-by-line diff (for production, use a proper diff algorithm)
  const maxLen = Math.max(oldLines.length, newLines.length);

  for (let i = 0; i < maxLen; i++) {
    const oldLine = oldLines[i];
    const newLine = newLines[i];

    if (oldLine === undefined) {
      diffLines.push({
        type: "added",
        lineNumber: { new: i + 1 },
        content: newLine,
      });
    } else if (newLine === undefined) {
      diffLines.push({
        type: "removed",
        lineNumber: { old: i + 1 },
        content: oldLine,
      });
    } else if (oldLine !== newLine) {
      diffLines.push({
        type: "removed",
        lineNumber: { old: i + 1 },
        content: oldLine,
      });
      diffLines.push({
        type: "added",
        lineNumber: { new: i + 1 },
        content: newLine,
      });
    } else {
      diffLines.push({
        type: "unchanged",
        lineNumber: { old: i + 1, new: i + 1 },
        content: oldLine,
      });
    }
  }

  // Group into hunks (context of 3 lines)
  const hunks = groupIntoHunks(diffLines);

  let additions = 0;
  let deletions = 0;
  for (const line of diffLines) {
    if (line.type === "added") additions++;
    if (line.type === "removed") deletions++;
  }

  return {
    title,
    hunks,
    stats: { additions, deletions, changes: 0 },
  };
}

function groupIntoHunks(lines: DiffLine[], context = 3): DiffHunk[] {
  const hunks: DiffHunk[] = [];
  let currentHunk: DiffLine[] = [];
  let unchangedCount = 0;
  let hunkStart = 1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.type === "unchanged") {
      unchangedCount++;
      if (unchangedCount <= context) {
        currentHunk.push(line);
      } else if (currentHunk.length > 0 && currentHunk.some((l) => l.type !== "unchanged")) {
        // End current hunk
        hunks.push({
          header: `@@ -${hunkStart} +${hunkStart} @@`,
          lines: currentHunk,
        });
        currentHunk = [];
      }
    } else {
      // Add context before change
      if (unchangedCount > context) {
        const startContext = Math.max(0, i - context);
        currentHunk = lines.slice(startContext, i).filter((l) => l.type === "unchanged");
        hunkStart = startContext + 1;
      }
      currentHunk.push(line);
      unchangedCount = 0;
    }
  }

  // Don't forget last hunk
  if (currentHunk.length > 0 && currentHunk.some((l) => l.type !== "unchanged")) {
    hunks.push({
      header: `@@ -${hunkStart} +${hunkStart} @@`,
      lines: currentHunk,
    });
  }

  return hunks;
}
