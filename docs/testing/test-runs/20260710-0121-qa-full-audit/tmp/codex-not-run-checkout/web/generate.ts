#!/usr/bin/env bun
/**
 * Solar Web Dashboard Generator
 *
 * 极简架构：无服务器，直接生成 HTML
 * - 从 SQLite 读取数据
 * - 生成独立 HTML 文件
 * - 支持 --watch 模式持续更新
 *
 * 使用:
 *   bun run web/generate.ts              # 生成一次
 *   bun run web/generate.ts --watch      # 持续监控更新
 *   bun run web/generate.ts --open       # 生成并打开浏览器
 */

import { Database } from "bun:sqlite";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

// ==================== 配置 ====================

const CONFIG = {
  dbPath: path.join(os.homedir(), ".solar", "solar.db"),
  outputPath: path.join(os.homedir(), ".solar", "dashboard.html"),
  refreshInterval: 3000, // HTML 自动刷新间隔 (ms)
  watchInterval: 2000,   // watch 模式检查间隔 (ms)
  style: "liquid.dark",
};

// ==================== 数据读取 ====================

interface HNTopic {
  id: number;
  title: string;
  url: string;
  score: number;
  author: string;
  comments: number;
  fetched_at: string;
}

interface DashboardData {
  version: string;
  timestamp: string;
  phase: string;
  activeAgent: string | null;
  agents: Array<{ name: string; emoji: string; status: string; count: number }>;
  skills: Array<{ name: string; category: string; count: number }>;
  phases: Array<{ phase: string; label: string; count: number; rate: number }>;
  activity: Array<{ time: string; actor: string; action: string; status: string }>;
  metrics: { invocations: number; successRate: number; latency: number; tokens: number; cost: number };
  hnTopics: HNTopic[];
  hnLastUpdate: string | null;
}

function readData(): DashboardData {
  const now = new Date();

  // 默认数据
  const defaultData: DashboardData = {
    version: "2.0.0",
    timestamp: now.toLocaleString("zh-CN"),
    phase: "P3",
    activeAgent: "Coder",
    agents: [
      { name: "Coder", emoji: "💻", status: "active", count: 156 },
      { name: "Researcher", emoji: "🔬", status: "idle", count: 89 },
      { name: "Tester", emoji: "🧪", status: "idle", count: 67 },
      { name: "Reviewer", emoji: "👁️", status: "idle", count: 45 },
      { name: "Architect", emoji: "📐", status: "idle", count: 34 },
    ],
    skills: [
      { name: "commit", category: "git", count: 89 },
      { name: "review", category: "code", count: 67 },
      { name: "test", category: "dev", count: 56 },
      { name: "build", category: "dev", count: 45 },
      { name: "pr", category: "git", count: 34 },
    ],
    phases: [
      { phase: "P1", label: "研究", count: 23, rate: 100 },
      { phase: "P2", label: "设计", count: 18, rate: 100 },
      { phase: "P3", label: "实现", count: 45, rate: 95.6 },
      { phase: "P4", label: "验证", count: 38, rate: 97.4 },
      { phase: "P5", label: "收尾", count: 15, rate: 100 },
    ],
    activity: [
      { time: formatTime(now), actor: "Coder", action: "completed task", status: "success" },
      { time: formatTime(new Date(now.getTime() - 60000)), actor: "/commit", action: "executed", status: "success" },
      { time: formatTime(new Date(now.getTime() - 120000)), actor: "P3→P4", action: "transition", status: "info" },
    ],
    metrics: { invocations: 523, successRate: 97.8, latency: 2.4, tokens: 1250000, cost: 12.5 },
    hnTopics: [],
    hnLastUpdate: null,
  };

  // 尝试从数据库读取
  if (!fs.existsSync(CONFIG.dbPath)) {
    return defaultData;
  }

  try {
    const db = new Database(CONFIG.dbPath, { readonly: true });

    // 读取 Agents (从 sys_resources + sys_agents 联表)
    const agents = db.query(`
      SELECT r.name, a.emoji, r.status
      FROM sys_agents a
      JOIN sys_resources r ON a.agent_id = r.resource_id
      ORDER BY r.name
    `).all() as any[];
    if (agents.length > 0) {
      defaultData.agents = agents.map((a) => ({
        name: a.name,
        emoji: a.emoji || "🤖",
        status: a.status || "idle",
        count: Math.floor(Math.random() * 100), // TODO: 从统计表读取
      }));
      defaultData.activeAgent = agents.find((a) => a.status === "active")?.name || null;
    }

    // 读取 Skills (从 sys_resources + sys_skills 联表)
    const skills = db.query(`
      SELECT r.name, s.category
      FROM sys_skills s
      JOIN sys_resources r ON s.skill_id = r.resource_id
      WHERE s.user_invocable = 1
      ORDER BY r.name LIMIT 10
    `).all() as any[];
    if (skills.length > 0) {
      defaultData.skills = skills.map((s) => ({
        name: s.name,
        category: s.category || "general",
        count: Math.floor(Math.random() * 50),
      }));
    }

    // 读取最近活动
    try {
      const invocations = db.query(`
        SELECT resource_type, resource_id, success, created_at
        FROM sys_invocations
        ORDER BY created_at DESC LIMIT 5
      `).all() as any[];
      if (invocations.length > 0) {
        defaultData.activity = invocations.map((i) => ({
          time: formatTime(new Date(i.created_at)),
          actor: i.resource_id,
          action: i.success ? "completed" : "failed",
          status: i.success ? "success" : "error",
        }));
      }
    } catch {}

    // 读取 HN Topics
    try {
      const hnTopics = db.query(`
        SELECT id, title, url, score, author, comments, fetched_at
        FROM hn_topics
        WHERE fetched_at = (SELECT MAX(fetched_at) FROM hn_topics)
        ORDER BY score DESC
        LIMIT 15
      `).all() as HNTopic[];
      if (hnTopics.length > 0) {
        defaultData.hnTopics = hnTopics;
        defaultData.hnLastUpdate = hnTopics[0]?.fetched_at || null;
      }
    } catch {}

    db.close();
  } catch (e) {
    console.warn("[Solar Web] DB read error:", e);
  }

  return defaultData;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

// ==================== HTML 生成 ====================

function generateHTML(data: DashboardData): string {
  const style = CONFIG.style;
  const isDark = style.includes("dark") || style === "monolith" || style === "cyberpunk";
  const accent = style === "cyberpunk" ? "#ff00ff" : style === "aurora" ? "#00ff88" : "#3b82f6";

  const phaseIdx = data.phases.findIndex((p) => p.phase === data.phase);

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="${CONFIG.refreshInterval / 1000}">
  <title>Solar Dashboard</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>☀️</text></svg>">
  <style>
    :root {
      --bg: ${isDark ? "#0a0a0f" : "#fafafa"};
      --sf: ${isDark ? "#12121a" : "#fff"};
      --ink: ${isDark ? "#e4e4e7" : "#18181b"};
      --mt: ${isDark ? "#71717a" : "#a1a1aa"};
      --ln: ${isDark ? "#27272a" : "#e4e4e7"};
      --acc: ${accent};
      --ok: #22c55e;
      --warn: #f59e0b;
      --err: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--ink); min-height: 100vh; }
    .app { max-width: 1200px; margin: 0 auto; padding: 24px; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--ln); }
    .logo { display: flex; align-items: center; gap: 8px; font-size: 24px; font-weight: 600; }
    .time { font-size: 13px; color: var(--mt); }
    .grid { display: grid; grid-template-columns: 1fr 300px; gap: 20px; }
    @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
    .card { background: var(--sf); border: 1px solid var(--ln); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    .card h3 { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--mt); margin-bottom: 12px; }
    .kv { display: flex; flex-direction: column; gap: 8px; }
    .kv-row { display: flex; justify-content: space-between; font-size: 14px; }
    .kv-key { color: var(--mt); }
    .kv-val { font-weight: 500; }
    .kv-val.ok { color: var(--ok); }
    .kv-val.warn { color: var(--warn); }
    .kv-val.err { color: var(--err); }
    .kv-val.acc { color: var(--acc); }
    .phases { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
    .phase { padding: 6px 14px; border-radius: 999px; font-size: 13px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); }
    .phase.active { background: rgba(59,130,246,0.15); border-color: var(--acc); color: var(--acc); }
    .phase.done { color: var(--ok); }
    .agents { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 10px; }
    .agent { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 10px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; }
    .agent.active { border-color: var(--acc); background: rgba(59,130,246,0.1); }
    .agent-emoji { font-size: 22px; }
    .agent-name { font-size: 11px; font-weight: 500; }
    .agent-cnt { font-size: 10px; color: var(--mt); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--ln); }
    th { font-size: 11px; font-weight: 500; color: var(--mt); text-transform: uppercase; }
    .tl { display: flex; flex-direction: column; gap: 10px; }
    .tl-item { display: flex; gap: 10px; font-size: 13px; padding-left: 10px; border-left: 2px solid var(--ln); }
    .tl-item.success { border-color: var(--ok); }
    .tl-item.error { border-color: var(--err); }
    .tl-item.info { border-color: var(--acc); }
    .tl-time { color: var(--mt); width: 45px; flex-shrink: 0; }
    .pill { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 999px; font-size: 12px; }
    .pill.ok { background: rgba(34,197,94,0.15); color: var(--ok); }
    footer { margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--ln); text-align: center; font-size: 12px; color: var(--mt); }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div class="logo"><span>☀️</span> Solar Dashboard</div>
      <div class="time">更新: ${data.timestamp}</div>
    </header>

    <div class="grid">
      <div class="main">
        <div class="card">
          <h3>System Overview</h3>
          <div class="kv">
            <div class="kv-row"><span class="kv-key">Version</span><span class="kv-val">v${data.version}</span></div>
            <div class="kv-row"><span class="kv-key">Phase</span><span class="kv-val acc">${data.phase}</span></div>
            <div class="kv-row"><span class="kv-key">Active Agent</span><span class="kv-val ${data.activeAgent ? "acc" : ""}">${data.activeAgent || "None"}</span></div>
          </div>
        </div>

        <div class="card">
          <h3>Five-Phase Workflow</h3>
          <div class="phases">
            ${data.phases.map((p, i) => `<div class="phase ${p.phase === data.phase ? "active" : ""} ${i < phaseIdx ? "done" : ""}">${i < phaseIdx ? "✓" : p.phase === data.phase ? "●" : "○"} ${p.phase} ${p.label}</div>`).join("")}
          </div>
          <table>
            <thead><tr><th>Phase</th><th>Count</th><th>Success</th></tr></thead>
            <tbody>${data.phases.map((p) => `<tr><td>${p.phase} ${p.label}</td><td>${p.count}</td><td>${p.rate}%</td></tr>`).join("")}</tbody>
          </table>
        </div>

        <div class="card">
          <h3>Agents</h3>
          <div class="agents">
            ${data.agents.map((a) => `<div class="agent ${a.status}""><span class="agent-emoji">${a.emoji}</span><span class="agent-name">${a.name}</span><span class="agent-cnt">${a.count}</span></div>`).join("")}
          </div>
        </div>

        <div class="card">
          <h3>Performance</h3>
          <div class="kv">
            <div class="kv-row"><span class="kv-key">Invocations</span><span class="kv-val">${data.metrics.invocations.toLocaleString()}</span></div>
            <div class="kv-row"><span class="kv-key">Success Rate</span><span class="kv-val ${data.metrics.successRate >= 95 ? "ok" : data.metrics.successRate >= 80 ? "warn" : "err"}">${data.metrics.successRate}%</span></div>
            <div class="kv-row"><span class="kv-key">Avg Latency</span><span class="kv-val">${data.metrics.latency}s</span></div>
            <div class="kv-row"><span class="kv-key">Tokens</span><span class="kv-val">${(data.metrics.tokens / 1000000).toFixed(1)}M</span></div>
            <div class="kv-row"><span class="kv-key">Cost</span><span class="kv-val">$${data.metrics.cost.toFixed(2)}</span></div>
          </div>
        </div>
      </div>

      <div class="side">
        <div class="card">
          <h3>Recent Activity</h3>
          <div class="tl">
            ${data.activity.map((a) => `<div class="tl-item ${a.status}"><span class="tl-time">${a.time}</span><span>${a.actor}: ${a.action}</span></div>`).join("")}
          </div>
        </div>

        <div class="card">
          <h3>Top Skills</h3>
          <table>
            <thead><tr><th>Skill</th><th>Count</th></tr></thead>
            <tbody>${data.skills.map((s) => `<tr><td>/${s.name}</td><td>${s.count}</td></tr>`).join("")}</tbody>
          </table>
        </div>

        <div class="card">
          <h3>Alerts</h3>
          <span class="pill ok">● No active alerts</span>
        </div>
      </div>
    </div>

    ${data.hnTopics.length > 0 ? `
    <div class="card" style="margin-top: 20px;">
      <h3>📡 Hacker News Top Stories ${data.hnLastUpdate ? `<span style="float:right;font-weight:normal;text-transform:none;">更新: ${new Date(data.hnLastUpdate).toLocaleString("zh-CN")}</span>` : ""}</h3>
      <table>
        <thead><tr><th>#</th><th>Title</th><th>Score</th><th>💬</th></tr></thead>
        <tbody>
          ${data.hnTopics.slice(0, 10).map((t, i) => `
            <tr>
              <td>${i + 1}</td>
              <td><a href="${t.url || `https://news.ycombinator.com/item?id=${t.id}`}" target="_blank" style="color:var(--ink);text-decoration:none;">${t.title.length > 50 ? t.title.slice(0, 50) + "..." : t.title}</a></td>
              <td style="color:var(--acc);font-weight:600;">${t.score}</td>
              <td>${t.comments}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
    ` : ""}

    <footer>
      Powered by TVS v0.4.0 · ${style} · Auto-refresh ${CONFIG.refreshInterval / 1000}s
    </footer>
  </div>
</body>
</html>`;
}

// ==================== 主程序 ====================

function generate(): void {
  const data = readData();
  const html = generateHTML(data);

  // 确保目录存在
  const dir = path.dirname(CONFIG.outputPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(CONFIG.outputPath, html);
  console.log(`[${new Date().toLocaleTimeString()}] Generated: ${CONFIG.outputPath}`);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const isWatch = args.includes("--watch") || args.includes("-w");
  const isOpen = args.includes("--open") || args.includes("-o");

  // 解析自定义参数
  const styleIdx = args.findIndex((a) => a === "--style" || a === "-s");
  if (styleIdx !== -1 && args[styleIdx + 1]) {
    CONFIG.style = args[styleIdx + 1];
  }

  const outIdx = args.findIndex((a) => a === "--output" || a === "-O");
  if (outIdx !== -1 && args[outIdx + 1]) {
    CONFIG.outputPath = args[outIdx + 1];
  }

  // 生成一次
  generate();

  // 打开浏览器
  if (isOpen) {
    const { spawn } = await import("child_process");
    spawn("open", [CONFIG.outputPath]);
  }

  // Watch 模式
  if (isWatch) {
    console.log(`\n☀️  Solar Dashboard Watch Mode`);
    console.log(`   Output: ${CONFIG.outputPath}`);
    console.log(`   Refresh: ${CONFIG.refreshInterval / 1000}s`);
    console.log(`   Press Ctrl+C to stop\n`);

    setInterval(generate, CONFIG.watchInterval);
  }
}

main().catch(console.error);
