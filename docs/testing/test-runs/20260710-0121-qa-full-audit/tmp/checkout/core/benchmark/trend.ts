/**
 * Solar Benchmark Trend Analyzer
 *
 * 性能趋势分析，支持:
 * - 历史数据管理
 * - 回归检测
 * - 趋势可视化
 *
 * @version 1.0.0
 */

import * as fs from "fs";
import * as path from "path";
import type {
  BenchmarkReport,
  BenchmarkResult,
  TrendData,
  HistoryPoint,
  ComparisonResult,
} from "./schema";
import { REGRESSION_THRESHOLDS } from "./schema";
import { geometricMean, formatChange, formatSpeedup } from "./statistics";
import { compareBenchmarks } from "./reporter";

// ==================== Storage ====================

const BENCHMARK_DIR = ".solar/benchmarks";

/**
 * 确保基准测试目录存在
 */
export function ensureBenchmarkDir(projectRoot: string = "."): string {
  const dir = path.join(projectRoot, BENCHMARK_DIR);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

/**
 * 保存基准测试报告
 */
export function saveReport(
  report: BenchmarkReport,
  projectRoot: string = "."
): string {
  const dir = ensureBenchmarkDir(projectRoot);
  const date = report.generatedAt.split("T")[0];
  const commit = report.metadata.git.commit.slice(0, 7);
  const filename = `${date}_${commit}.json`;
  const filepath = path.join(dir, filename);

  fs.writeFileSync(filepath, JSON.stringify(report, null, 2));
  return filepath;
}

/**
 * 加载基准测试报告
 */
export function loadReport(filepath: string): BenchmarkReport {
  const content = fs.readFileSync(filepath, "utf-8");
  return JSON.parse(content) as BenchmarkReport;
}

/**
 * 列出所有历史报告
 */
export function listReports(projectRoot: string = "."): string[] {
  const dir = path.join(projectRoot, BENCHMARK_DIR);
  if (!fs.existsSync(dir)) return [];

  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".json") && f !== "baseline.json")
    .map((f) => path.join(dir, f))
    .sort()
    .reverse(); // 最新的在前
}

/**
 * 获取或设置基线
 */
export function getBaseline(projectRoot: string = "."): BenchmarkReport | null {
  const filepath = path.join(projectRoot, BENCHMARK_DIR, "baseline.json");
  if (!fs.existsSync(filepath)) return null;
  return loadReport(filepath);
}

export function setBaseline(
  report: BenchmarkReport,
  projectRoot: string = "."
): void {
  const dir = ensureBenchmarkDir(projectRoot);
  const filepath = path.join(dir, "baseline.json");
  fs.writeFileSync(filepath, JSON.stringify(report, null, 2));
}

// ==================== Trend Analysis ====================

/**
 * 构建趋势数据
 */
export function buildTrendData(
  benchmarkId: string,
  reports: BenchmarkReport[]
): TrendData {
  const history: HistoryPoint[] = [];

  for (const report of reports) {
    const bench = report.benchmarks.find((b) => b.id === benchmarkId);
    if (bench) {
      history.push({
        commit: report.metadata.git.commit,
        timestamp: report.generatedAt,
        median: bench.stats.median.value,
        ci: [bench.stats.median.lower, bench.stats.median.upper],
        samples: bench.stats.samples,
      });
    }
  }

  // 按时间排序
  history.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  // 计算趋势
  let trend: TrendData["trend"] = "stable";
  let recentChangeRate = 0;

  if (history.length >= 3) {
    const recent = history.slice(-3);
    const older = recent[0].median;
    const newer = recent[recent.length - 1].median;
    recentChangeRate = (newer - older) / older;

    if (recentChangeRate < -0.05) {
      trend = "improving";
    } else if (recentChangeRate > 0.05) {
      trend = "degrading";
    }
  }

  return {
    benchmarkId,
    history,
    trend,
    recentChangeRate,
  };
}

/**
 * 获取所有基准测试的趋势
 */
export function getAllTrends(projectRoot: string = "."): TrendData[] {
  const reportPaths = listReports(projectRoot);
  if (reportPaths.length === 0) return [];

  const reports = reportPaths.map(loadReport);

  // 收集所有基准测试 ID
  const benchmarkIds = new Set<string>();
  for (const report of reports) {
    for (const bench of report.benchmarks) {
      benchmarkIds.add(bench.id);
    }
  }

  return Array.from(benchmarkIds).map((id) => buildTrendData(id, reports));
}

// ==================== Regression Detection ====================

export interface RegressionAlert {
  benchmarkId: string;
  type: "warn" | "fail";
  baselineMedian: number;
  currentMedian: number;
  change: number;
  message: string;
}

/**
 * 检测回归
 */
export function detectRegressions(
  current: BenchmarkReport,
  baseline: BenchmarkReport | null,
  thresholds: typeof REGRESSION_THRESHOLDS = REGRESSION_THRESHOLDS
): RegressionAlert[] {
  if (!baseline) return [];

  const alerts: RegressionAlert[] = [];

  for (const currentBench of current.benchmarks) {
    const baselineBench = baseline.benchmarks.find(
      (b) => b.id === currentBench.id
    );
    if (!baselineBench) continue;

    const comparison = compareBenchmarks(baselineBench, currentBench);
    const changePercent = comparison.relativeChange * 100;

    if (changePercent > thresholds.fail) {
      alerts.push({
        benchmarkId: currentBench.id,
        type: "fail",
        baselineMedian: baselineBench.stats.median.value,
        currentMedian: currentBench.stats.median.value,
        change: comparison.relativeChange,
        message: `❌ ${currentBench.name}: ${formatChange(comparison.relativeChange)} regression (>${thresholds.fail}% threshold)`,
      });
    } else if (changePercent > thresholds.warn) {
      alerts.push({
        benchmarkId: currentBench.id,
        type: "warn",
        baselineMedian: baselineBench.stats.median.value,
        currentMedian: currentBench.stats.median.value,
        change: comparison.relativeChange,
        message: `⚠️ ${currentBench.name}: ${formatChange(comparison.relativeChange)} regression (>${thresholds.warn}% threshold)`,
      });
    }
  }

  return alerts;
}

// ==================== ASCII Visualization ====================

/**
 * 生成 ASCII 趋势图
 */
export function renderTrendChart(
  trend: TrendData,
  width: number = 60,
  height: number = 10
): string[] {
  const lines: string[] = [];
  const history = trend.history;

  if (history.length < 2) {
    return [`No trend data available for ${trend.benchmarkId}`];
  }

  // 计算范围
  const values = history.map((h) => h.median);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  // 标题
  const trendEmoji =
    trend.trend === "improving" ? "📈" : trend.trend === "degrading" ? "📉" : "➡️";
  lines.push(`${trendEmoji} ${trend.benchmarkId} (${trend.trend})`);
  lines.push("─".repeat(width));

  // 图表区域
  const chartWidth = width - 10; // 留出 Y 轴标签空间
  const pointSpacing = Math.max(1, Math.floor(chartWidth / (history.length - 1)));

  // 生成图表行
  for (let row = 0; row < height; row++) {
    const threshold = max - (row / (height - 1)) * range;
    let line = "";

    // Y 轴标签
    if (row === 0) {
      line += formatCompact(max).padStart(8) + " │";
    } else if (row === height - 1) {
      line += formatCompact(min).padStart(8) + " │";
    } else {
      line += "        │";
    }

    // 数据点
    for (let i = 0; i < history.length; i++) {
      const value = history[i].median;
      const normalizedValue = (max - value) / range;
      const pointRow = Math.round(normalizedValue * (height - 1));

      if (pointRow === row) {
        line += "●";
      } else if (i > 0) {
        // 连接线
        const prevValue = history[i - 1].median;
        const prevNormalized = (max - prevValue) / range;
        const prevRow = Math.round(prevNormalized * (height - 1));
        const minRow = Math.min(prevRow, pointRow);
        const maxRow = Math.max(prevRow, pointRow);

        if (row > minRow && row < maxRow) {
          line += "│";
        } else {
          line += " ";
        }
      } else {
        line += " ";
      }

      // 间隔
      if (i < history.length - 1) {
        line += " ".repeat(Math.max(0, pointSpacing - 1));
      }
    }

    lines.push(line);
  }

  // X 轴
  lines.push("        └" + "─".repeat(chartWidth));

  // X 轴标签 (显示提交哈希)
  const firstCommit = history[0].commit.slice(0, 7);
  const lastCommit = history[history.length - 1].commit.slice(0, 7);
  const xAxisLabel = `         ${firstCommit}${" ".repeat(chartWidth - 14)}${lastCommit}`;
  lines.push(xAxisLabel);

  return lines;
}

/**
 * 格式化紧凑数字
 */
function formatCompact(value: number): string {
  if (value >= 1e9) return (value / 1e9).toFixed(1) + "G";
  if (value >= 1e6) return (value / 1e6).toFixed(1) + "M";
  if (value >= 1e3) return (value / 1e3).toFixed(1) + "K";
  return value.toFixed(1);
}

// ==================== Summary Report ====================

/**
 * 生成趋势摘要报告
 */
export function generateTrendSummary(
  projectRoot: string = "."
): string {
  const lines: string[] = [];
  const trends = getAllTrends(projectRoot);
  const baseline = getBaseline(projectRoot);
  const reportPaths = listReports(projectRoot);

  lines.push("# Benchmark Trend Summary");
  lines.push("");
  lines.push(`**Reports:** ${reportPaths.length}`);
  lines.push(`**Baseline:** ${baseline ? "Set" : "Not set"}`);
  lines.push("");

  if (trends.length === 0) {
    lines.push("No benchmark history available.");
    return lines.join("\n");
  }

  // 趋势概览
  const improving = trends.filter((t) => t.trend === "improving").length;
  const degrading = trends.filter((t) => t.trend === "degrading").length;
  const stable = trends.filter((t) => t.trend === "stable").length;

  lines.push("## Trend Overview");
  lines.push("");
  lines.push(`| Trend | Count |`);
  lines.push(`|-------|-------|`);
  lines.push(`| 📈 Improving | ${improving} |`);
  lines.push(`| 📉 Degrading | ${degrading} |`);
  lines.push(`| ➡️ Stable | ${stable} |`);
  lines.push("");

  // 详细趋势
  lines.push("## Benchmark Trends");
  lines.push("");

  for (const trend of trends) {
    const emoji =
      trend.trend === "improving" ? "📈" : trend.trend === "degrading" ? "📉" : "➡️";
    const change = formatChange(trend.recentChangeRate);
    lines.push(`- ${emoji} **${trend.benchmarkId}**: ${change} (last 3 commits)`);
  }

  lines.push("");

  // 回归警告
  if (baseline && reportPaths.length > 0) {
    const latestReport = loadReport(reportPaths[0]);
    const alerts = detectRegressions(latestReport, baseline);

    if (alerts.length > 0) {
      lines.push("## ⚠️ Regression Alerts");
      lines.push("");
      for (const alert of alerts) {
        lines.push(`- ${alert.message}`);
      }
      lines.push("");
    }
  }

  return lines.join("\n");
}
