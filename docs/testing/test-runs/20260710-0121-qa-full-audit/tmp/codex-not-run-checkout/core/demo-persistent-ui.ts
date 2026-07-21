/**
 * Solar 持久化 UI 演示
 *
 * 使用 Alternate Screen Buffer + 固定布局
 * UI 不会被日志冲走
 */

// ==================== ANSI Escape Codes ====================

const ESC = "\x1b";
const CSI = `${ESC}[`;

const term = {
  // Screen buffer
  enterAltScreen: `${CSI}?1049h`,
  exitAltScreen: `${CSI}?1049l`,

  // Cursor
  hideCursor: `${CSI}?25l`,
  showCursor: `${CSI}?25h`,
  moveTo: (row: number, col: number) => `${CSI}${row};${col}H`,

  // Clear
  clearScreen: `${CSI}2J`,
  clearLine: `${CSI}2K`,

  // Colors
  reset: `${CSI}0m`,
  bold: `${CSI}1m`,
  dim: `${CSI}2m`,
  yellow: `${CSI}33m`,
  cyan: `${CSI}36m`,
  green: `${CSI}32m`,
  red: `${CSI}31m`,
  bgYellow: `${CSI}43m`,
  bgGray: `${CSI}100m`,
  white: `${CSI}97m`,
};

// ==================== Persistent UI Manager ====================

class PersistentUI {
  private width: number;
  private height: number;
  private headerHeight = 3;
  private statusBarHeight = 1;
  private logLines: string[] = [];
  private maxLogLines: number;
  private running = false;
  private refreshTimer?: NodeJS.Timeout;

  // State
  private phase = "P3";
  private agent = "💻 Coder";
  private tokens = 12500;
  private taskStatus = "Running E2E tests...";

  constructor() {
    this.width = process.stdout.columns || 120;
    this.height = process.stdout.rows || 40;
    this.maxLogLines = this.height - this.headerHeight - this.statusBarHeight - 4;
  }

  // ==================== Lifecycle ====================

  start(): void {
    if (this.running) return;
    this.running = true;

    // Enter alternate screen
    process.stdout.write(term.enterAltScreen);
    process.stdout.write(term.hideCursor);
    process.stdout.write(term.clearScreen);

    // Handle resize
    process.stdout.on("resize", () => {
      this.width = process.stdout.columns || 120;
      this.height = process.stdout.rows || 40;
      this.maxLogLines = this.height - this.headerHeight - this.statusBarHeight - 4;
      this.render();
    });

    // Handle exit
    process.on("SIGINT", () => this.stop());
    process.on("SIGTERM", () => this.stop());

    // Initial render
    this.render();

    // Start refresh loop (for clock, etc.)
    this.refreshTimer = setInterval(() => this.render(), 1000);
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;

    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
    }

    // Exit alternate screen
    process.stdout.write(term.showCursor);
    process.stdout.write(term.exitAltScreen);

    console.log("\n👋 Solar UI exited. Your terminal history is preserved.\n");
    process.exit(0);
  }

  // ==================== Logging ====================

  log(message: string, level: "info" | "warn" | "error" | "agent" | "solar" = "info"): void {
    const time = new Date().toLocaleTimeString("en-US", { hour12: false });
    const levelColors: Record<string, string> = {
      info: `${term.green}[INFO]${term.reset}`,
      warn: `${term.yellow}[WARN]${term.reset}`,
      error: `${term.red}[ERROR]${term.reset}`,
      agent: `${term.cyan}[AGENT]${term.reset}`,
      solar: `${term.yellow}[SOLAR]${term.reset}`,
    };

    const line = `${term.dim}${time}${term.reset} ${levelColors[level]} ${message}`;
    this.logLines.push(line);

    // Keep only maxLogLines
    while (this.logLines.length > this.maxLogLines) {
      this.logLines.shift();
    }

    this.renderLogArea();
  }

  // ==================== State Updates ====================

  setPhase(phase: string): void {
    this.phase = phase;
    this.render();
  }

  setAgent(agent: string): void {
    this.agent = agent;
    this.render();
  }

  setTokens(tokens: number): void {
    this.tokens = tokens;
    this.render();
  }

  setTask(status: string): void {
    this.taskStatus = status;
    this.render();
  }

  // ==================== Rendering ====================

  private render(): void {
    if (!this.running) return;

    this.renderHeader();
    this.renderLogArea();
    this.renderStatusBar();
  }

  private renderHeader(): void {
    const time = new Date().toLocaleTimeString("en-US", { hour12: false });

    // Line 1: Title bar
    process.stdout.write(term.moveTo(1, 1));
    const title = " ☀️ Solar AI OS v1.0 ";
    const titleLine = `${term.bgYellow}${term.bold}${title}${" ".repeat(this.width - title.length - time.length - 2)}${time} ${term.reset}`;
    process.stdout.write(titleLine);

    // Line 2: Status line
    process.stdout.write(term.moveTo(2, 1));
    const status = ` Phase: ${term.cyan}${this.phase}${term.reset} │ Agent: ${this.agent} │ Task: ${this.taskStatus} │ Tokens: ${this.tokens.toLocaleString()}`;
    process.stdout.write(term.clearLine);
    process.stdout.write(status.padEnd(this.width));

    // Line 3: Separator
    process.stdout.write(term.moveTo(3, 1));
    process.stdout.write(`${term.dim}${"─".repeat(this.width)}${term.reset}`);
  }

  private renderLogArea(): void {
    if (!this.running) return;

    const startRow = this.headerHeight + 1;

    for (let i = 0; i < this.maxLogLines; i++) {
      process.stdout.write(term.moveTo(startRow + i, 1));
      process.stdout.write(term.clearLine);

      const line = this.logLines[i] || "";
      process.stdout.write(` ${line}`);
    }
  }

  private renderStatusBar(): void {
    process.stdout.write(term.moveTo(this.height, 1));
    const left = ` [Solar] ${this.phase} │ ${this.agent} │ +${(this.tokens / 1000).toFixed(1)}K `;
    const right = ` Ctrl+C: Exit `;
    const padding = this.width - left.length - right.length;
    const statusLine = `${term.bgGray}${term.white}${left}${" ".repeat(Math.max(0, padding))}${right}${term.reset}`;
    process.stdout.write(statusLine);
  }
}

// ==================== Simulation ====================

async function simulate() {
  const ui = new PersistentUI();
  ui.start();

  // Simulate development workflow
  const tasks = [
    { delay: 500, log: "Loading project state...", level: "info" as const },
    { delay: 800, log: "Git status: main branch, 5 files changed", level: "info" as const },
    { delay: 600, log: "Resuming from checkpoint: P3 Implementation", level: "solar" as const },
    { delay: 1000, log: "💻 Coder: Starting code analysis...", level: "agent" as const },
    { delay: 1200, log: "Analyzing core/ui/v2/runtime.ts", level: "info" as const },
    { delay: 800, log: "Analyzing core/agent/protocol.ts", level: "info" as const },
    { delay: 1000, log: "💻 Coder: Running E2E tests...", level: "agent" as const },
    { delay: 1500, log: "Test 1/5: Agent Protocol ✓", level: "info" as const },
    { delay: 1200, log: "Test 2/5: Parallel Executor ✓", level: "info" as const },
    { delay: 1000, log: "Test 3/5: Git Server ✓", level: "info" as const },
    { delay: 1100, log: "Test 4/5: TUV Components ✓", level: "info" as const },
    { delay: 1300, log: "Test 5/5: Integration ✓", level: "info" as const },
    { delay: 500, log: "All tests passed!", level: "solar" as const },
    { delay: 800, log: "🧪 Tester: Verifying results...", level: "agent" as const },
    { delay: 1000, log: "Performance regression check: PASS", level: "info" as const },
    { delay: 600, log: "Coverage: 87%", level: "info" as const },
    { delay: 800, log: "🧪 Tester: Validation complete", level: "agent" as const },
    { delay: 500, log: "Ready for next task", level: "solar" as const },
  ];

  ui.setTask("Loading...");

  for (const task of tasks) {
    await sleep(task.delay);
    ui.log(task.log, task.level);

    // Update status based on progress
    if (task.log.includes("Running E2E")) {
      ui.setTask("Running E2E tests...");
    } else if (task.log.includes("All tests passed")) {
      ui.setTask("Tests complete ✓");
      ui.setTokens(15200);
    } else if (task.log.includes("Tester")) {
      ui.setAgent("🧪 Tester");
    } else if (task.log.includes("Ready")) {
      ui.setTask("Awaiting input");
      ui.setAgent("💻 Coder");
    }
  }

  // Keep running
  ui.log("", "info");
  ui.log(`${term.dim}─── Waiting for next command (Ctrl+C to exit) ───${term.reset}`, "info");

  // Keep the process alive
  await new Promise(() => {});
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ==================== Entry ====================

simulate().catch(console.error);
