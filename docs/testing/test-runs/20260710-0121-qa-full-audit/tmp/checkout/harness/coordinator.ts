/**
 * Solar Harness — 协调器 TypeScript 版 v2
 *
 * 与 bash coordinator.sh 功能等价, bun 执行
 * 双写期: TS 仅 log 不执行 (除非 coordinator-ts-enabled 开关存在)
 *
 * Sprint: sprint-20260418-232003, D6
 */

import { execSync } from "child_process";
import {
  readFileSync, writeFileSync, existsSync, mkdirSync,
  readdirSync, statSync, appendFileSync,
} from "fs";
import { homedir } from "os";
import { join } from "path";
import { createHash } from "crypto";

// ── 类型定义 ──

interface SprintStatus {
  status: string;
  title: string;
  round: number;
  created_at: string;
  updated_at: string;
  source?: string;
  auto_generated?: boolean;
  parent_goal?: string;
}

type SprintState =
  | "drafting"
  | "active"
  | "planning"
  | "approved"
  | "reviewing"
  | "passed"
  | "failed"
  | "cancelled"
  | "superseded"
  | "eval_pass";

const VALID_STATES: SprintState[] = [
  "drafting", "active", "planning", "approved", "reviewing",
  "passed", "failed", "cancelled", "superseded", "eval_pass",
];

// ── 常量 ──

const HARNESS_DIR = join(homedir(), ".solar", "harness");
const SPRINTS_DIR = join(HARNESS_DIR, "sprints");
const COORD_LOG = join(HARNESS_DIR, ".coordinator-ts.log");
const COMPARE_LOG = join(HARNESS_DIR, "coordinator-compare.jsonl");
const ENABLED_FLAG = join(HARNESS_DIR, "coordinator-ts-enabled");

const SESSION_NAME = "solar-harness";
const LAB_SESSION_NAME = "solar-harness-lab";

const PANE = {
  PM: `${SESSION_NAME}:0.0`,
  PLANNER: `${SESSION_NAME}:0.1`,
  MONITOR: `${SESSION_NAME}:0.2`,
  BUILDER: `${LAB_SESSION_NAME}:0.0`,
  EVALUATOR: `${SESSION_NAME}:0.3`,
};

// ── 日志 ──

function ts(): string {
  return new Date().toISOString().replace(/\.\d+Z$/, "Z");
}

function log(msg: string): void {
  const line = `[${ts()}] [TS] ${msg}`;
  console.error(line);
  try { appendFileSync(COORD_LOG, line + "\n"); } catch {}
}

// ── 双写控制 ──

function isEnabled(): boolean {
  return existsSync(ENABLED_FLAG);
}

function logDecision(sid: string, event: string, detail: string): void {
  const entry = JSON.stringify({ ts: ts(), sid, event, detail, source: "ts", enabled: isEnabled() });
  try { appendFileSync(COMPARE_LOG, entry + "\n"); } catch {}
}

// ── Sprint 扫描 ──

function scanSprints(): Array<{ sid: string; status: SprintStatus }> {
  const results: Array<{ sid: string; status: SprintStatus }> = [];
  try {
    const files = readdirSync(SPRINTS_DIR).filter((f) => f.endsWith(".status.json"));
    for (const f of files) {
      const sid = f.replace(".status.json", "");
      try {
        const raw = readFileSync(join(SPRINTS_DIR, f), "utf-8");
        const status = JSON.parse(raw) as SprintStatus;
        results.push({ sid, status });
      } catch {}
    }
  } catch {}
  return results;
}

function getFileMtime(): number {
  try {
    const files = readdirSync(SPRINTS_DIR).filter((f) => f.endsWith(".status.json"));
    let maxMtime = 0;
    for (const f of files) {
      try {
        const mtime = statSync(join(SPRINTS_DIR, f)).mtimeMs;
        if (mtime > maxMtime) maxMtime = mtime;
      } catch {}
    }
    return maxMtime;
  } catch {
    return 0;
  }
}

// ── 状态机 ──

function getTargetPane(state: string): string {
  switch (state) {
    case "drafting": return PANE.PM;
    case "active": return PANE.PLANNER;
    case "planning": return PANE.EVALUATOR;
    case "approved": return PANE.BUILDER;
    case "reviewing": return PANE.EVALUATOR;
    case "passed": return PANE.PM;
    case "failed": return PANE.BUILDER;
    default: return PANE.PM;
  }
}

function getActionForState(state: string): string {
  switch (state) {
    case "active": return "plan";
    case "planning": return "review_plan";
    case "approved": return "implement";
    case "reviewing": return "review";
    case "passed": return "handle_passed";
    case "failed": return "handle_failed";
    default: return "none";
  }
}

// ── Dispatch (真实 or log-only) ──

function dispatchToPane(pane: string, message: string, sid: string): boolean {
  if (!isEnabled()) {
    log(`[双写-LOG] dispatch → ${pane}: ${message.slice(0, 60)}`);
    logDecision(sid, "dispatch_logged", `pane=${pane} action=${message.slice(0, 40)}`);
    return true;
  }

  // 真实 dispatch
  const instructionFile = join(SPRINTS_DIR, `${sid}.dispatch.md`);
  try { writeFileSync(instructionFile, message); } catch {}
  const shortCmd = `读取并执行 ${instructionFile}`;

  try {
    // D3: pre-unlock for builder/evaluator panes in the current 4-pane layout.
    if (pane === PANE.BUILDER || pane === PANE.EVALUATOR) {
      execSync(`tmux send-keys -t ${pane} Escape 2>/dev/null`, { timeout: 3000 });
      execSync(`tmux send-keys -t ${pane} C-u 2>/dev/null`, { timeout: 3000 });
    }
    execSync(`tmux send-keys -t ${pane} '${shortCmd}' 2>/dev/null`, { timeout: 3000 });
    execSync(`sleep 0.8 && tmux send-keys -t ${pane} Enter 2>/dev/null`, { timeout: 5000 });
    log(`已派发到 ${pane}: ${shortCmd}`);
    logDecision(sid, "dispatched", `pane=${pane}`);
    return true;
  } catch (err: any) {
    log(`dispatch 失败: ${(err.message || "").slice(0, 80)}`);
    return false;
  }
}

// ── 状态处理 ──

function handleSprint(sid: string, status: SprintStatus): void {
  const state = status.status as SprintState;
  const action = getActionForState(state);

  if (action === "none") return;

  log(`检测到: ${sid} → ${state} (action: ${action})`);
  logDecision(sid, "state_detected", `state=${state} action=${action}`);

  // D3: Gate checks (same as bash coordinator)
  if (state === "planning") {
    const planFile = join(SPRINTS_DIR, `${sid}.plan.md`);
    if (!existsSync(planFile)) {
      log(`门禁: planning 但 plan.md 不存在`);
      return;
    }
  }

  if (state === "reviewing") {
    const handoffFile = join(SPRINTS_DIR, `${sid}.handoff.md`);
    if (!existsSync(handoffFile)) {
      log(`门禁: reviewing 但 handoff.md 不存在`);
      return;
    }
  }

  const pane = getTargetPane(state);
  dispatchToPane(pane, `[TS] Sprint ${sid} 状态 ${state}, 动作 ${action}`, sid);
}

// ── 主循环 ──

async function main(): Promise<void> {
  const separator = "═".repeat(50);
  log(`${separator}`);
  log(`[TS协调器v2] 启动: ${new Date().toISOString()}`);
  log(`模式: ${isEnabled() ? "ENABLED (真实执行)" : "DUAL-WRITE (仅log)"}`);
  log(`${separator}`);

  let lastMtime = getFileMtime();

  while (true) {
    await Bun.sleep(10_000);

    const currentMtime = getFileMtime();
    if (currentMtime === lastMtime) continue;
    lastMtime = currentMtime;

    log(`mtime 变化检测: ${currentMtime}`);

    const sprints = scanSprints();
    // 只处理最近变化的 sprint (找最新的非终态)
    const active = sprints
      .filter((s) => !["passed", "cancelled", "superseded", "eval_pass"].includes(s.status.status))
      .sort((a, b) => new Date(b.status.updated_at).getTime() - new Date(a.status.updated_at).getTime());

    if (active.length > 0) {
      const latest = active[0];
      handleSprint(latest.sid, latest.status);
    }
  }
}

main().catch((err) => log(`致命错误: ${err}`));
