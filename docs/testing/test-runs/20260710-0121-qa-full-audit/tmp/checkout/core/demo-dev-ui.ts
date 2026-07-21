/**
 * Solar 开发模式 UI 演示
 *
 * 模拟 "我要开发 ThunderDuck" 的界面展示
 */

import { createGitServer } from "./mcp";
import { createTreeView, pathsToTree } from "./ui/v2/components/tree-view";
import { AGENTS } from "./agent";
import { PHASES } from "./flow";

// ==================== ANSI Colors ====================

const colors = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  dim: "\x1b[2m",
  yellow: "\x1b[33m",
  cyan: "\x1b[36m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  magenta: "\x1b[35m",
  blue: "\x1b[34m",
  bgYellow: "\x1b[43m",
  bgBlue: "\x1b[44m",
  bgGray: "\x1b[100m",
  white: "\x1b[97m",
};

const c = colors;

// ==================== Box Drawing ====================

function drawBox(title: string, content: string[], width: number, color = c.yellow): string[] {
  const lines: string[] = [];
  const innerWidth = width - 4;

  lines.push(`${color}┌─ ${title} ${"─".repeat(Math.max(0, innerWidth - title.length - 1))}┐${c.reset}`);

  for (const line of content) {
    const displayLine = line.slice(0, innerWidth).padEnd(innerWidth);
    lines.push(`${color}│${c.reset} ${displayLine} ${color}│${c.reset}`);
  }

  lines.push(`${color}└${"─".repeat(width - 2)}┘${c.reset}`);

  return lines;
}

function drawDoubleBox(title: string, content: string[], width: number): string[] {
  const lines: string[] = [];
  const innerWidth = width - 4;

  lines.push(`${c.yellow}╔═ ${c.bold}${title}${c.reset}${c.yellow} ${"═".repeat(Math.max(0, innerWidth - title.length - 1))}╗${c.reset}`);

  for (const line of content) {
    const displayLine = line.slice(0, innerWidth).padEnd(innerWidth);
    lines.push(`${c.yellow}║${c.reset} ${displayLine} ${c.yellow}║${c.reset}`);
  }

  lines.push(`${c.yellow}╚${"═".repeat(width - 2)}╝${c.reset}`);

  return lines;
}

// ==================== Dashboard Panels ====================

async function renderSolarBanner(project: string, gitInfo: any): Promise<string[]> {
  const width = 70;

  const content = [
    `${c.bold}项目:${c.reset} ${project}`,
    `${c.bold}路径:${c.reset} ~/ThunderDuck`,
    `${"─".repeat(width - 4)}`,
    `${c.bold}分支:${c.reset} ${gitInfo.branch} ${c.dim}|${c.reset} ${c.bold}变更:${c.reset} ${gitInfo.changes}个文件`,
    `${c.bold}最近:${c.reset} ${gitInfo.lastCommit}`,
    `${"─".repeat(width - 4)}`,
    `${c.bold}阶段:${c.reset} ${c.cyan}P3 实现${c.reset} ${c.dim}|${c.reset} ${c.bold}Agent:${c.reset} 💻 Coder`,
    `${c.bold}任务:${c.reset} Solar v1.0 核心开发`,
    `${c.bold}待办:${c.reset}`,
    `  ${c.green}✓${c.reset} TUV v2 Multi-panel`,
    `  ${c.green}✓${c.reset} Agent Protocol`,
    `  ${c.green}✓${c.reset} Parallel Executor`,
    `  ${c.green}✓${c.reset} Git MCP Server`,
    `${"─".repeat(width - 4)}`,
    `${c.bold}关键文件:${c.reset}`,
    `  ${c.dim}•${c.reset} core/ui/v2/runtime.ts`,
    `  ${c.dim}•${c.reset} core/agent/protocol.ts`,
    `  ${c.dim}•${c.reset} core/flow/parallel-executor.ts`,
  ];

  return drawDoubleBox("☀️ Solar", content, width);
}

function renderAgentPanel(): string[] {
  const width = 35;
  const agents = [
    { id: "researcher", status: "idle" },
    { id: "architect", status: "idle" },
    { id: "coder", status: "active" },
    { id: "tester", status: "idle" },
    { id: "reviewer", status: "idle" },
    { id: "guard", status: "watching" },
  ];

  const content = agents.map((a) => {
    const info = AGENTS[a.id];
    const statusIcon =
      a.status === "active" ? `${c.green}●${c.reset}` :
      a.status === "watching" ? `${c.cyan}◐${c.reset}` :
      `${c.dim}○${c.reset}`;
    return `${statusIcon} ${info.emoji} ${a.id.padEnd(12)} ${c.dim}${info.role.slice(0, 10)}${c.reset}`;
  });

  return drawBox("🤖 Agents", content, width, c.cyan);
}

function renderPhasePanel(): string[] {
  const width = 35;
  const currentPhase = "P3";

  const content = Object.entries(PHASES).map(([id, info]) => {
    const isCurrent = id === currentPhase;
    const prefix = isCurrent ? `${c.yellow}▶${c.reset}` : " ";
    const style = isCurrent ? c.bold : c.dim;
    return `${prefix} ${style}${info.emoji} ${id} ${info.name}${c.reset}`;
  });

  content.push("");
  content.push(`${c.dim}Gate G1: ✓ 已通过${c.reset}`);
  content.push(`${c.dim}Gate G2: ◌ 待验证${c.reset}`);

  return drawBox("📊 Phase", content, width, c.magenta);
}

function renderTokenPanel(): string[] {
  const width = 35;
  const used = 12500;
  const limit = 100000;
  const percent = Math.round((used / limit) * 100);
  const barWidth = 20;
  const filled = Math.round((percent / 100) * barWidth);

  const bar = `${c.green}${"█".repeat(filled)}${c.dim}${"░".repeat(barWidth - filled)}${c.reset}`;

  const content = [
    `${c.bold}Session:${c.reset} ${used.toLocaleString()} / ${limit.toLocaleString()}`,
    `${bar} ${percent}%`,
    "",
    `${c.bold}Rate Limit:${c.reset}`,
    `  Requests: ${c.green}45%${c.reset} ${c.dim}(45/100)${c.reset}`,
    `  Tokens:   ${c.green}12%${c.reset} ${c.dim}(12K/100K)${c.reset}`,
    "",
    `${c.dim}Est. remaining: ~87,500 tokens${c.reset}`,
  ];

  return drawBox("🎫 Tokens", content, width, c.blue);
}

function renderTaskPanel(): string[] {
  const width = 35;

  const content = [
    `${c.green}✓${c.reset} 更新架构图`,
    `${c.green}✓${c.reset} TUV v2 Multi-panel`,
    `${c.green}✓${c.reset} Agent Protocol`,
    `${c.green}✓${c.reset} Parallel Executor`,
    `${c.green}✓${c.reset} Git MCP Server`,
    `${c.yellow}►${c.reset} ${c.bold}E2E 测试验证${c.reset}`,
    `${c.dim}○ 文档更新${c.reset}`,
    `${c.dim}○ 性能基准测试${c.reset}`,
  ];

  return drawBox("✅ Tasks", content, width, c.green);
}

function renderFileTree(): string[] {
  const width = 35;
  const files = [
    "core/ui/v2/index.ts",
    "core/ui/v2/runtime.ts",
    "core/ui/v2/layout-manager.ts",
    "core/ui/v2/components/tree-view.ts",
    "core/agent/protocol.ts",
    "core/agent/bus.ts",
    "core/flow/parallel-executor.ts",
    "core/mcp/git-server.ts",
  ];

  const tree = pathsToTree(files, "Solar");
  const treeView = createTreeView({ root: tree, showIcons: true, showLines: true });
  const lines = treeView.render().slice(0, 10);

  return drawBox("📁 Files", lines, width, c.cyan);
}

function renderLogPanel(): string[] {
  const width = 70;
  const now = new Date();
  const time = (offset: number) => {
    const t = new Date(now.getTime() - offset * 1000);
    return t.toLocaleTimeString("en-US", { hour12: false });
  };

  const content = [
    `${c.dim}${time(30)}${c.reset} ${c.green}[INFO]${c.reset}  Agent Protocol test passed`,
    `${c.dim}${time(25)}${c.reset} ${c.green}[INFO]${c.reset}  Parallel Executor test passed`,
    `${c.dim}${time(20)}${c.reset} ${c.green}[INFO]${c.reset}  Git Server test passed`,
    `${c.dim}${time(15)}${c.reset} ${c.green}[INFO]${c.reset}  TUV Components test passed`,
    `${c.dim}${time(10)}${c.reset} ${c.green}[INFO]${c.reset}  Integration test passed`,
    `${c.dim}${time(5)}${c.reset}  ${c.cyan}[AGENT]${c.reset} 💻 Coder: E2E tests complete`,
    `${c.dim}${time(0)}${c.reset}  ${c.yellow}[SOLAR]${c.reset} ☀️ All v1.0 tests passed!`,
  ];

  return drawBox("📋 Log", content, width, c.dim);
}

function renderStatusBar(): string {
  const width = 106;
  const left = `${c.bgGray}${c.white} [Solar] P3 │ 💻 Coder │ +12.5K tokens │ Rate 45% 🟢 ${c.reset}`;
  const right = `${c.bgGray}${c.white} Tab:切换 │ Ctrl+P:命令 │ Ctrl+Q:退出 ${c.reset}`;
  const padding = width - 52 - 38;

  return `${left}${c.bgGray}${" ".repeat(Math.max(0, padding))}${c.reset}${right}`;
}

function renderHeader(): string {
  const width = 106;
  const title = "☀️ Solar AI OS v1.0";
  const time = new Date().toLocaleTimeString("en-US", { hour12: false });
  const padding = width - title.length - time.length - 4;

  return `${c.bgYellow}${c.bold} ${title}${" ".repeat(Math.max(0, padding))}${time} ${c.reset}`;
}

// ==================== Main Render ====================

async function renderDashboard() {
  // Get git info
  const git = createGitServer(process.env.SOLAR_DEMO_REPO || `${process.env.HOME}/ThunderDuck`);
  let gitInfo = { branch: "main", changes: 0, lastCommit: "feat: Solar v1.0" };

  try {
    const status = await git.status();
    const commits = await git.log({ count: 1 });
    gitInfo = {
      branch: status.branch,
      changes: status.unstaged.length + status.untracked.length,
      lastCommit: commits[0]?.message.slice(0, 40) ?? "N/A",
    };
  } catch {
    // Use defaults
  }

  console.clear();

  // Header
  console.log(renderHeader());
  console.log();

  // Main banner
  const banner = await renderSolarBanner("ThunderDuck", gitInfo);
  for (const line of banner) {
    console.log("  " + line);
  }

  console.log();

  // Two-column layout: Agents + Phase | Tokens + Tasks
  const agents = renderAgentPanel();
  const phase = renderPhasePanel();
  const tokens = renderTokenPanel();
  const tasks = renderTaskPanel();

  const maxRows = Math.max(agents.length, phase.length, tokens.length, tasks.length);

  for (let i = 0; i < maxRows; i++) {
    const col1 = agents[i] ?? " ".repeat(35);
    const col2 = phase[i] ?? " ".repeat(35);
    const col3 = tokens[i] ?? " ".repeat(35);
    console.log(`  ${col1}  ${col2}  ${col3}`);
  }

  console.log();

  // File tree + Log
  const fileTree = renderFileTree();
  const log = renderLogPanel();

  const maxRows2 = Math.max(fileTree.length, log.length);

  for (let i = 0; i < maxRows2; i++) {
    const col1 = fileTree[i] ?? " ".repeat(35);
    const col2 = log[i] ?? " ".repeat(70);
    console.log(`  ${col1}  ${col2}`);
  }

  console.log();

  // Status bar
  console.log("  " + renderStatusBar());

  console.log();
  console.log(`  ${c.dim}Press Ctrl+C to exit demo${c.reset}`);
}

// ==================== Entry Point ====================

async function main() {
  // Simulate "我要开发 ThunderDuck"
  console.log(`\n  ${c.yellow}用户:${c.reset} 我要开发 ThunderDuck\n`);
  console.log(`  ${c.cyan}Solar:${c.reset} 正在装载项目...\n`);

  await new Promise((r) => setTimeout(r, 500));

  await renderDashboard();
}

main().catch(console.error);
