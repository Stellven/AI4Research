/**
 * TUV v2 Command Palette
 *
 * Fuzzy-searchable command interface (VS Code style)
 * Generates VDL-compatible semantic IR.
 */

import type { Command, CommandPaletteConfig } from "../types";

// ==================== Types ====================

export interface CommandMatch {
  command: Command;
  score: number;
  highlights: number[]; // Indices of matched characters
}

export interface CommandPaletteState {
  visible: boolean;
  query: string;
  selectedIndex: number;
  matches: CommandMatch[];
}

// ==================== Command Palette ====================

export class CommandPalette {
  private config: CommandPaletteConfig;
  private state: CommandPaletteState;

  constructor(config: CommandPaletteConfig) {
    this.config = config;
    this.state = {
      visible: false,
      query: "",
      selectedIndex: 0,
      matches: this.getAllCommands(),
    };
  }

  // ==================== Visibility ====================

  open(): void {
    this.state.visible = true;
    this.state.query = "";
    this.state.selectedIndex = 0;
    this.state.matches = this.getAllCommands();
  }

  close(): void {
    this.state.visible = false;
    this.state.query = "";
  }

  toggle(): void {
    if (this.state.visible) {
      this.close();
    } else {
      this.open();
    }
  }

  isVisible(): boolean {
    return this.state.visible;
  }

  // ==================== Search ====================

  setQuery(query: string): void {
    this.state.query = query;
    this.state.selectedIndex = 0;

    if (!query.trim()) {
      this.state.matches = this.getAllCommands();
      return;
    }

    // Fuzzy search
    this.state.matches = this.fuzzySearch(query);
  }

  appendQuery(char: string): void {
    this.setQuery(this.state.query + char);
  }

  backspace(): void {
    if (this.state.query.length > 0) {
      this.setQuery(this.state.query.slice(0, -1));
    }
  }

  clearQuery(): void {
    this.setQuery("");
  }

  private getAllCommands(): CommandMatch[] {
    return this.config.commands.map((cmd) => ({
      command: cmd,
      score: 0,
      highlights: [],
    }));
  }

  private fuzzySearch(query: string): CommandMatch[] {
    const lowerQuery = query.toLowerCase();
    const matches: CommandMatch[] = [];

    for (const command of this.config.commands) {
      const result = this.fuzzyMatch(lowerQuery, command.label.toLowerCase());
      if (result) {
        matches.push({
          command,
          score: result.score,
          highlights: result.highlights,
        });
      }
    }

    // Sort by score (higher is better)
    matches.sort((a, b) => b.score - a.score);

    return matches.slice(0, this.config.maxVisible ?? 10);
  }

  private fuzzyMatch(
    query: string,
    target: string
  ): { score: number; highlights: number[] } | null {
    const highlights: number[] = [];
    let queryIdx = 0;
    let score = 0;
    let consecutiveBonus = 0;

    for (let i = 0; i < target.length && queryIdx < query.length; i++) {
      if (target[i] === query[queryIdx]) {
        highlights.push(i);
        queryIdx++;

        // Scoring
        score += 10; // Base match score

        // Consecutive match bonus
        if (highlights.length > 1 && highlights[highlights.length - 2] === i - 1) {
          consecutiveBonus += 5;
          score += consecutiveBonus;
        } else {
          consecutiveBonus = 0;
        }

        // Start of word bonus
        if (i === 0 || target[i - 1] === " " || target[i - 1] === "-" || target[i - 1] === "_") {
          score += 15;
        }

        // CamelCase bonus
        if (i > 0 && target[i] === target[i].toUpperCase() && target[i - 1] === target[i - 1].toLowerCase()) {
          score += 10;
        }
      }
    }

    // All query characters must match
    if (queryIdx !== query.length) {
      return null;
    }

    // Prefer shorter matches
    score -= (target.length - query.length) * 2;

    return { score, highlights };
  }

  // ==================== Navigation ====================

  selectNext(): void {
    if (this.state.matches.length === 0) return;
    this.state.selectedIndex = (this.state.selectedIndex + 1) % this.state.matches.length;
  }

  selectPrev(): void {
    if (this.state.matches.length === 0) return;
    this.state.selectedIndex =
      (this.state.selectedIndex - 1 + this.state.matches.length) % this.state.matches.length;
  }

  selectFirst(): void {
    this.state.selectedIndex = 0;
  }

  selectLast(): void {
    this.state.selectedIndex = Math.max(0, this.state.matches.length - 1);
  }

  // ==================== Execution ====================

  async executeSelected(): Promise<void> {
    const selected = this.state.matches[this.state.selectedIndex];
    if (selected) {
      this.close();
      await selected.command.action();
    }
  }

  async executeCommand(commandId: string): Promise<void> {
    const command = this.config.commands.find((c) => c.id === commandId);
    if (command) {
      this.close();
      await command.action();
    }
  }

  // ==================== Rendering ====================

  /**
   * Render to VDL-compatible structure
   */
  toVDL(): object {
    if (!this.state.visible) {
      return { type: "spacer", height: 0 };
    }

    const items = this.state.matches.map((match, idx) => {
      const isSelected = idx === this.state.selectedIndex;
      return {
        type: "text",
        content: this.formatCommandLabel(match),
        emphasis: isSelected ? "bold" : undefined,
        color: isSelected ? "primary" : undefined,
        suffix: match.command.shortcut ? `[${match.command.shortcut}]` : undefined,
      };
    });

    return {
      type: "card",
      header: "⌘ Command Palette",
      sections: [
        {
          type: "text",
          content: `> ${this.state.query}█`,
          color: "accent",
        },
        {
          type: "divider",
        },
        {
          type: "list",
          variant: "none",
          items,
        },
      ],
    };
  }

  private formatCommandLabel(match: CommandMatch): string {
    // For VDL, we could add highlighting metadata
    // For now, just return the label with category prefix
    const { command } = match;
    if (command.category) {
      return `${command.category}: ${command.label}`;
    }
    return command.label;
  }

  /**
   * Render to plain text lines
   */
  render(width = 60): string[] {
    if (!this.state.visible) {
      return [];
    }

    const lines: string[] = [];
    const boxWidth = Math.min(width, 60);
    const innerWidth = boxWidth - 4;

    // Top border
    lines.push("┌" + "─".repeat(boxWidth - 2) + "┐");

    // Title
    const title = "⌘ Command Palette";
    const titlePadding = Math.floor((innerWidth - title.length) / 2);
    lines.push("│ " + " ".repeat(titlePadding) + title + " ".repeat(innerWidth - titlePadding - title.length) + " │");

    // Separator
    lines.push("├" + "─".repeat(boxWidth - 2) + "┤");

    // Search input
    const inputLine = `> ${this.state.query}█`;
    lines.push("│ " + inputLine.padEnd(innerWidth) + " │");

    // Separator
    lines.push("├" + "─".repeat(boxWidth - 2) + "┤");

    // Commands
    const maxVisible = this.config.maxVisible ?? 10;
    const visible = this.state.matches.slice(0, maxVisible);

    if (visible.length === 0) {
      lines.push("│ " + "No matching commands".padEnd(innerWidth) + " │");
    } else {
      for (let i = 0; i < visible.length; i++) {
        const match = visible[i];
        const isSelected = i === this.state.selectedIndex;
        const prefix = isSelected ? "▶ " : "  ";

        let label = match.command.label;
        if (match.command.category) {
          label = `${match.command.category}: ${label}`;
        }

        const shortcut = match.command.shortcut ? ` [${match.command.shortcut}]` : "";
        const maxLabelLen = innerWidth - prefix.length - shortcut.length;
        label = label.slice(0, maxLabelLen);

        const line = prefix + label + shortcut;
        lines.push("│ " + line.padEnd(innerWidth) + " │");
      }
    }

    // Bottom border
    lines.push("└" + "─".repeat(boxWidth - 2) + "┘");

    // Help hint
    lines.push("  ↑↓ Navigate  ⏎ Select  Esc Close");

    return lines;
  }

  // ==================== State Access ====================

  getState(): CommandPaletteState {
    return this.state;
  }

  getSelectedCommand(): Command | null {
    const match = this.state.matches[this.state.selectedIndex];
    return match?.command ?? null;
  }

  getMatchCount(): number {
    return this.state.matches.length;
  }
}

// ==================== Factory ====================

export function createCommandPalette(config: CommandPaletteConfig): CommandPalette {
  return new CommandPalette(config);
}

// ==================== Default Solar Commands ====================

export const SOLAR_COMMANDS: Command[] = [
  // Flow commands
  {
    id: "solar.start",
    label: "Start Solar Flow",
    shortcut: "Ctrl+Shift+S",
    category: "Solar",
    action: async () => console.log("Starting Solar Flow..."),
  },
  {
    id: "phase.next",
    label: "Next Phase",
    shortcut: "Ctrl+N",
    category: "Phase",
    action: async () => console.log("Moving to next phase..."),
  },
  {
    id: "phase.prev",
    label: "Previous Phase",
    shortcut: "Ctrl+P",
    category: "Phase",
    action: async () => console.log("Moving to previous phase..."),
  },

  // Git commands
  {
    id: "git.commit",
    label: "Commit Changes",
    shortcut: "Ctrl+K",
    category: "Git",
    action: async () => console.log("Opening commit dialog..."),
  },
  {
    id: "git.push",
    label: "Push to Remote",
    category: "Git",
    action: async () => console.log("Pushing to remote..."),
  },
  {
    id: "git.pull",
    label: "Pull from Remote",
    category: "Git",
    action: async () => console.log("Pulling from remote..."),
  },
  {
    id: "git.status",
    label: "Show Git Status",
    category: "Git",
    action: async () => console.log("Showing git status..."),
  },

  // Agent commands
  {
    id: "agent.researcher",
    label: "Call Researcher",
    category: "Agent",
    action: async () => console.log("Calling Researcher agent..."),
  },
  {
    id: "agent.coder",
    label: "Call Coder",
    category: "Agent",
    action: async () => console.log("Calling Coder agent..."),
  },
  {
    id: "agent.tester",
    label: "Call Tester",
    category: "Agent",
    action: async () => console.log("Calling Tester agent..."),
  },
  {
    id: "agent.reviewer",
    label: "Call Reviewer",
    category: "Agent",
    action: async () => console.log("Calling Reviewer agent..."),
  },

  // View commands
  {
    id: "view.dashboard",
    label: "Toggle Dashboard",
    shortcut: "Ctrl+D",
    category: "View",
    action: async () => console.log("Toggling dashboard..."),
  },
  {
    id: "view.sidebar",
    label: "Toggle Sidebar",
    shortcut: "Ctrl+B",
    category: "View",
    action: async () => console.log("Toggling sidebar..."),
  },
  {
    id: "view.terminal",
    label: "Toggle Terminal",
    shortcut: "Ctrl+`",
    category: "View",
    action: async () => console.log("Toggling terminal..."),
  },

  // File commands
  {
    id: "file.save",
    label: "Save File",
    shortcut: "Ctrl+S",
    category: "File",
    action: async () => console.log("Saving file..."),
  },
  {
    id: "file.saveAll",
    label: "Save All Files",
    shortcut: "Ctrl+Shift+S",
    category: "File",
    action: async () => console.log("Saving all files..."),
  },

  // State commands
  {
    id: "state.save",
    label: "Save Session State",
    category: "State",
    action: async () => console.log("Saving session state..."),
  },
  {
    id: "state.restore",
    label: "Restore Session State",
    category: "State",
    action: async () => console.log("Restoring session state..."),
  },

  // Benchmark commands
  {
    id: "benchmark.run",
    label: "Run Benchmarks",
    category: "Benchmark",
    action: async () => console.log("Running benchmarks..."),
  },
  {
    id: "benchmark.compare",
    label: "Compare with Baseline",
    category: "Benchmark",
    action: async () => console.log("Comparing with baseline..."),
  },

  // Test commands
  {
    id: "test.run",
    label: "Run Tests",
    shortcut: "Ctrl+T",
    category: "Test",
    action: async () => console.log("Running tests..."),
  },
  {
    id: "test.watch",
    label: "Watch Tests",
    category: "Test",
    action: async () => console.log("Starting test watch mode..."),
  },

  // Help
  {
    id: "help.shortcuts",
    label: "Show Keyboard Shortcuts",
    shortcut: "Ctrl+?",
    category: "Help",
    action: async () => console.log("Showing keyboard shortcuts..."),
  },
  {
    id: "help.docs",
    label: "Open Documentation",
    category: "Help",
    action: async () => console.log("Opening documentation..."),
  },
];

/**
 * Create Solar command palette with default commands
 */
export function createSolarCommandPalette(extraCommands: Command[] = []): CommandPalette {
  return new CommandPalette({
    commands: [...SOLAR_COMMANDS, ...extraCommands],
    placeholder: "Type a command...",
    maxVisible: 12,
  });
}
