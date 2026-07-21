/**
 * 从历史会话数据初始化本体偏好
 * 基于 usage-stats.json 和历史 JSONL 文件分析用户偏好
 */

import { Database } from "bun:sqlite";
import { existsSync, readFileSync, readdirSync } from "fs";
import { join } from "path";
import { OntologyManager } from "./manager";
import { PreferenceSignal } from "./types";

interface UsageStats {
  totals: {
    sessions: number;
    messages: number;
    inputTokens: number;
    outputTokens: number;
  };
  projects: {
    name: string;
    sessions: number;
    totalMessages: number;
    avgDepth: number;
    inputTokens: number;
    outputTokens: number;
  }[];
  hourlyActivity: { hour: string; count: number }[];
  sessionDepthDistribution: {
    short: number;
    medium: number;
    long: number;
    veryLong: number;
  };
}

async function initFromHistory() {
  console.log("=== 从历史数据初始化本体偏好 ===\n");

  // 1. 加载 usage-stats.json
  const statsPath = join(process.env.HOME!, "Solar/data/usage-stats.json");
  if (!existsSync(statsPath)) {
    console.log("⚠️ 未找到 usage-stats.json，请先运行数据提取脚本");
    return;
  }

  const stats: UsageStats = JSON.parse(readFileSync(statsPath, "utf-8"));
  console.log(`[1] 加载统计数据:`);
  console.log(`    会话数: ${stats.totals.sessions}`);
  console.log(`    消息数: ${stats.totals.messages}`);
  console.log(`    Token: ${(stats.totals.inputTokens + stats.totals.outputTokens).toLocaleString()}`);
  console.log();

  // 2. 初始化本体系统
  const dbPath = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;
  const db = new Database(dbPath);
  const ontology = new OntologyManager(db);
  ontology.initialize();
  console.log("[2] 本体系统初始化完成\n");

  // 3. 分析偏好信号
  const signals: PreferenceSignal[] = [];
  const now = new Date();

  // 3.1 工作时间偏好 (从 hourlyActivity 分析)
  const hourCounts: Record<string, number> = {};
  for (const h of stats.hourlyActivity) {
    const hour = parseInt(h.hour.split("T")[1].split(":")[0]);
    let period: string;
    if (hour >= 6 && hour < 12) period = "morning";
    else if (hour >= 12 && hour < 18) period = "afternoon";
    else if (hour >= 18 && hour < 22) period = "evening";
    else period = "night";
    hourCounts[period] = (hourCounts[period] || 0) + h.count;
  }

  const totalHours = Object.values(hourCounts).reduce((a, b) => a + b, 0);
  const peakPeriod = Object.entries(hourCounts).sort((a, b) => b[1] - a[1])[0];

  if (peakPeriod) {
    const periodValues: Record<string, number> = {
      morning: 0.0,
      afternoon: 0.33,
      evening: 0.67,
      night: 1.0,
    };
    signals.push({
      dimension_id: "work_time",
      value: periodValues[peakPeriod[0]],
      weight: Math.min(peakPeriod[1] / totalHours * 5, 3), // 根据占比调整权重
      source: "session",
      timestamp: now,
      evidence: `主要工作时段: ${peakPeriod[0]} (${peakPeriod[1]}/${totalHours} 活动)`,
    });
    console.log(`[3] 工作时间偏好: ${peakPeriod[0]} (${((peakPeriod[1] / totalHours) * 100).toFixed(1)}%)`);
  }

  // 3.2 会话深度偏好 (从 sessionDepthDistribution 分析)
  const depthDist = stats.sessionDepthDistribution;
  const totalSessions = depthDist.short + depthDist.medium + depthDist.long + depthDist.veryLong;
  const longRatio = (depthDist.long + depthDist.veryLong) / totalSessions;

  signals.push({
    dimension_id: "session_depth",
    value: longRatio, // 长会话占比越高，值越大
    weight: 2.0, // 历史数据权重较高
    source: "session",
    timestamp: now,
    evidence: `长会话占比: ${(longRatio * 100).toFixed(1)}% (${depthDist.long + depthDist.veryLong}/${totalSessions})`,
  });
  console.log(`    会话深度偏好: ${(longRatio * 100).toFixed(1)}% 长会话`);

  // 3.3 成本敏感度 (从 Token 使用分析)
  const avgTokensPerSession = (stats.totals.inputTokens + stats.totals.outputTokens) / stats.totals.sessions;
  // 假设 100K tokens/session 是中等水平
  const costSensitivity = Math.max(0, 1 - avgTokensPerSession / 200000);

  signals.push({
    dimension_id: "cost_sensitivity",
    value: costSensitivity,
    weight: 1.5,
    source: "session",
    timestamp: now,
    evidence: `平均 Token/会话: ${avgTokensPerSession.toFixed(0)}`,
  });
  console.log(`    成本敏感度: ${(costSensitivity * 100).toFixed(1)}% (avg ${avgTokensPerSession.toFixed(0)} tokens/session)`);

  // 3.4 项目专注度 (从项目分布分析)
  if (stats.projects.length > 0) {
    const topProject = stats.projects[0];
    const topProjectRatio = topProject.totalMessages / stats.totals.messages;

    // 高专注度 = 主要在一个项目上工作
    // 这可能暗示用户偏好深度工作
    if (topProjectRatio > 0.4) {
      signals.push({
        dimension_id: "speed_vs_quality",
        value: 0.7, // 专注说明可能更重视质量
        weight: 1.0,
        source: "session",
        timestamp: now,
        evidence: `主要项目 ${topProject.name} 占 ${(topProjectRatio * 100).toFixed(1)}%`,
      });
      console.log(`    质量偏好: 专注于 ${topProject.name} (${(topProjectRatio * 100).toFixed(1)}%)`);
    }
  }

  // 3.5 自动化信任度 (从历史数据推断)
  // 如果用户经常使用长会话，说明信任自动执行
  if (longRatio > 0.5) {
    signals.push({
      dimension_id: "automation_trust",
      value: 0.7,
      weight: 1.0,
      source: "session",
      timestamp: now,
      evidence: `长会话占比高 (${(longRatio * 100).toFixed(1)}%) 暗示信任自动执行`,
    });
    console.log(`    自动化信任: 高 (长会话占比 ${(longRatio * 100).toFixed(1)}%)`);
  }

  console.log();

  // 4. 应用信号到本体
  console.log(`[4] 应用 ${signals.length} 个偏好信号...`);
  await ontology.onSessionEnd("history_init", signals);

  // 5. 触发本体重计算
  console.log("[5] 重计算本体...");
  await ontology.recomputeOntology("从历史数据初始化");

  // 6. 显示更新后的偏好
  console.log("\n[6] 更新后的偏好状态:");
  const prefs = ontology.getAllPreferences();
  for (const pref of prefs) {
    const value = pref.current_value ?? pref.default_value;
    const conf = (pref.confidence * 100).toFixed(0);
    console.log(`    ${pref.name}: ${value.toFixed(2)} (置信度: ${conf}%)`);
  }

  // 7. 显示生成的 Agent 规则
  console.log("\n[7] 生成的 Agent 规则:");
  const coderContext = ontology.getAgentContext("coder");
  for (const [key, value] of Object.entries(coderContext.rules)) {
    console.log(`    ${key}: ${JSON.stringify(value)}`);
  }

  console.log("\n=== 初始化完成 ===");
  db.close();
}

initFromHistory().catch(console.error);
