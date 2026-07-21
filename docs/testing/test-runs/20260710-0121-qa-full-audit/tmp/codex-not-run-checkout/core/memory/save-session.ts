#!/usr/bin/env bun
/**
 * Solar Session Saver
 * 会话状态保存工具 - 替代 Secretary Agent 的可执行版本
 */

import { Database } from "bun:sqlite";
import { writeFileSync, existsSync, mkdirSync } from "fs";
import { homedir } from "os";

const DB_PATH = process.env.SOLAR_DB_PATH || `${homedir()}/.solar/db/solar.db`;
const SESSION_DIR = `${process.cwd()}/.solar`;

interface SessionState {
  timestamp: string;
  branch: string;
  uncommitted: string[];
  recentCommits: string[];
  keyFiles: string[];
  todos: string[];
}

async function getCurrentState(): Promise<SessionState> {
  const { execSync } = await import("child_process");

  const branch = execSync("git branch --show-current", { encoding: "utf-8" }).trim();
  const uncommittedRaw = execSync("git status --short", { encoding: "utf-8" });
  const uncommitted = uncommittedRaw
    .split("\n")
    .filter(Boolean)
    .map(line => line.trim());

  const recentCommitsRaw = execSync("git log --oneline -5", { encoding: "utf-8" });
  const recentCommits = recentCommitsRaw.split("\n").filter(Boolean);

  // 查找最近修改的关键文件
  const keyFilesRaw = execSync(
    "git diff --name-only HEAD~5..HEAD | head -10",
    { encoding: "utf-8" }
  ).trim();
  const keyFiles = keyFilesRaw ? keyFilesRaw.split("\n") : [];

  return {
    timestamp: new Date().toISOString(),
    branch,
    uncommitted,
    recentCommits,
    keyFiles,
    todos: [],
  };
}

async function saveToMarkdown(state: SessionState): Promise<void> {
  if (!existsSync(SESSION_DIR)) {
    mkdirSync(SESSION_DIR, { recursive: true });
  }

  const content = `# Solar Session Checkpoint

> 自动生成于: ${new Date().toLocaleString()}
> 使用 \`/restore\` 快速恢复此会话

## 项目状态

- **分支**: ${state.branch}
- **工作目录**: ${process.cwd()}

## 最近提交

\`\`\`
${state.recentCommits.join("\n")}
\`\`\`

## 未提交变更

\`\`\`
${state.uncommitted.slice(0, 20).join("\n")}
${state.uncommitted.length > 20 ? `... (${state.uncommitted.length - 20} more)` : ""}
\`\`\`

## 最近修改文件

\`\`\`
${state.keyFiles.join("\n")}
\`\`\`

## 待办事项

${state.todos.length > 0 ? state.todos.map((t, i) => `${i + 1}. ${t}`).join("\n") : "_无待办事项_"}

## 会话摘要

<!-- 由 Claude 自动更新 -->
_最后更新: ${state.timestamp}_

---
*此文件由 Solar auto-checkpoint 自动生成*
`;

  writeFileSync(`${SESSION_DIR}/session.md`, content, "utf-8");
  console.log(`[SaveSession] ✓ 保存到 ${SESSION_DIR}/session.md`);
}

async function saveToDatabase(state: SessionState): Promise<void> {
  const db = new Database(DB_PATH);

  try {
    db.run(`
      INSERT OR REPLACE INTO evo_memory_semantic (
        memory_id,
        namespace,
        key,
        value,
        source_type,
        confidence,
        created_at
      ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    `, [
      `session_${Date.now()}`,
      "system/sessions",
      `checkpoint_${state.timestamp}`,
      JSON.stringify(state),
      "system",
      1.0,
    ]);

    console.log("[SaveSession] ✓ 保存到数据库");
  } catch (error) {
    console.error("[SaveSession] ✗ 数据库保存失败:", error);
  } finally {
    db.close();
  }
}

// CLI 接口
if (import.meta.main) {
  const command = process.argv[2] || "auto-checkpoint";

  switch (command) {
    case "auto-checkpoint":
    case "session-end":
      console.log(`[SaveSession] 执行 ${command}...`);
      const state = await getCurrentState();
      await saveToMarkdown(state);
      await saveToDatabase(state);
      console.log("[SaveSession] ✓ 完成");
      break;

    case "show":
      const showState = await getCurrentState();
      console.log(JSON.stringify(showState, null, 2));
      break;

    default:
      console.log(`
Usage: bun save-session.ts [command]

Commands:
  auto-checkpoint   自动检查点保存 (默认)
  session-end       会话结束保存
  show              显示当前状态 (不保存)
      `);
  }
}
