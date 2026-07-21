/**
 * Solar Benchmark Reporter
 *
 * 生成结构化的性能测试报告
 *
 * @version 1.0.0
 */

import * as os from "os";
import type {
  BenchmarkReport,
  BenchmarkResult,
  BenchmarkMetadata,
  BenchmarkConfig,
  BenchmarkType,
  ComparisonResult,
  ReportSummary,
  ChangeType,
  TimeUnit,
  HardwareInfo,
  SoftwareInfo,
  GitInfo,
  BENCHMARK_PRESETS,
  REGRESSION_THRESHOLDS,
} from "./schema";
import {
  computeStatistics,
  detectOutliers,
  speedup,
  geometricMean,
  cohensD,
  welchTTest,
  formatTime,
  formatChange,
  formatSpeedup,
} from "./statistics";

// ==================== Metadata Collection ====================

/**
 * 收集硬件信息
 */
export function collectHardwareInfo(): HardwareInfo {
  const cpus = os.cpus();
  const cpuModel = cpus[0]?.model || "Unknown";
  const cpuFreqMhz = cpus[0]?.speed || 0;

  return {
    cpuModel,
    cpuCores: cpus.length,
    cpuFreqMhz,
    memoryGb: Math.round(os.totalmem() / (1024 ** 3)),
    arch: os.arch() === "arm64" ? "arm64" : os.arch() === "x64" ? "x86_64" : "other",
  };
}

/**
 * 收集软件信息
 */
export function collectSoftwareInfo(): SoftwareInfo {
  return {
    os: os.type(),
    osVersion: os.release(),
    compiler: "unknown",
    compilerVersion: "unknown",
    compilerFlags: "",
    buildType: "release",
  };
}

/**
 * 从 Git 获取信息
 */
export async function collectGitInfo(): Promise<GitInfo> {
  try {
    const { execSync } = await import("child_process");
    const commit = execSync("git rev-parse HEAD", { encoding: "utf-8" }).trim();
    const branch = execSync("git branch --show-current", { encoding: "utf-8" }).trim();
    const status = execSync("git status --porcelain", { encoding: "utf-8" });
    const dirty = status.length > 0;

    let tag: string | undefined;
    try {
      tag = execSync("git describe --tags --exact-match 2>/dev/null", { encoding: "utf-8" }).trim();
    } catch {
      tag = undefined;
    }

    return { commit, branch, dirty, tag };
  } catch {
    return {
      commit: "unknown",
      branch: "unknown",
      dirty: false,
    };
  }
}

/**
 * 收集完整元数据
 */
export async function collectMetadata(
  config: Partial<BenchmarkConfig> = {}
): Promise<BenchmarkMetadata> {
  const defaultConfig: BenchmarkConfig = {
    warmupIterations: 5,
    measurementIterations: 30,
    removeOutliers: true,
    confidenceLevel: 0.95,
  };

  return {
    timestamp: new Date().toISOString(),
    hardware: collectHardwareInfo(),
    software: collectSoftwareInfo(),
    git: await collectGitInfo(),
    environment: {},
    config: { ...defaultConfig, ...config },
  };
}

// ==================== Benchmark Result Builder ====================

/**
 * 从原始数据创建 BenchmarkResult
 */
export function createBenchmarkResult(
  id: string,
  name: string,
  rawData: number[],
  options: {
    type?: BenchmarkType;
    description?: string;
    params?: Record<string, number | string>;
    unit?: TimeUnit;
    removeOutliers?: boolean;
    throughput?: { items: number; bytes?: number };
    customMetrics?: Record<string, number>;
  } = {}
): BenchmarkResult {
  const {
    type = "operator",
    description,
    params,
    unit = "ns",
    removeOutliers = true,
    throughput,
    customMetrics,
  } = options;

  const stats = computeStatistics(rawData, unit, 0.95, removeOutliers);
  const outliers = detectOutliers(rawData);

  // 计算吞吐量
  let throughputResult: BenchmarkResult["throughput"];
  if (throughput) {
    const medianSeconds = stats.median.value / (unit === "ns" ? 1e9 : unit === "us" ? 1e6 : unit === "ms" ? 1e3 : 1);
    throughputResult = {
      itemsPerSecond: throughput.items / medianSeconds,
      bytesPerSecond: throughput.bytes ? throughput.bytes / medianSeconds : undefined,
    };
  }

  return {
    id,
    name,
    type,
    description,
    params,
    stats,
    outliers,
    rawData,
    throughput: throughputResult,
    customMetrics,
  };
}

// ==================== Comparison ====================

/**
 * 比较两个基准测试结果
 */
export function compareBenchmarks(
  baseline: BenchmarkResult,
  current: BenchmarkResult
): ComparisonResult {
  const baselineMedian = baseline.stats.median.value;
  const currentMedian = current.stats.median.value;

  const absoluteChange = currentMedian - baselineMedian;
  const relativeChange = (currentMedian - baselineMedian) / baselineMedian;
  const speedupValue = speedup(baselineMedian, currentMedian);

  // 统计显著性检测
  const baselineData = baseline.rawData || [];
  const currentData = current.rawData || [];
  let significant = false;
  let effectSize = 0;

  if (baselineData.length > 2 && currentData.length > 2) {
    const tTest = welchTTest(baselineData, currentData);
    significant = tTest.significant;
    effectSize = Math.abs(cohensD(baselineData, currentData));
  }

  // 确定变化类型
  let changeType: ChangeType;
  const threshold = 0.05; // 5%

  if (!significant || Math.abs(relativeChange) < threshold) {
    changeType = "nochange";
  } else if (relativeChange < -threshold) {
    changeType = "improvement"; // 时间减少 = 改进
  } else if (relativeChange > threshold) {
    changeType = "regression"; // 时间增加 = 回退
  } else {
    changeType = "uncertain";
  }

  return {
    benchmarkId: baseline.id,
    baseline: {
      median: baselineMedian,
      ci: [baseline.stats.median.lower, baseline.stats.median.upper],
      commit: "baseline",
    },
    current: {
      median: currentMedian,
      ci: [current.stats.median.lower, current.stats.median.upper],
      commit: "current",
    },
    absoluteChange,
    relativeChange,
    changeType,
    speedup: speedupValue,
    significant,
    effectSize,
  };
}

// ==================== Report Generation ====================

/**
 * 生成报告摘要
 */
export function generateSummary(
  benchmarks: BenchmarkResult[],
  comparisons?: ComparisonResult[]
): ReportSummary {
  const highlights: string[] = [];
  const recommendations: string[] = [];

  let regressions = 0;
  let improvements = 0;
  const speedups: number[] = [];

  if (comparisons && comparisons.length > 0) {
    for (const comp of comparisons) {
      if (comp.changeType === "regression") {
        regressions++;
        highlights.push(
          `⚠️ ${comp.benchmarkId}: ${formatChange(comp.relativeChange)} (${formatSpeedup(comp.speedup)})`
        );
      } else if (comp.changeType === "improvement") {
        improvements++;
        highlights.push(
          `✅ ${comp.benchmarkId}: ${formatChange(comp.relativeChange)} (${formatSpeedup(comp.speedup)})`
        );
      }
      speedups.push(comp.speedup);
    }
  }

  // 检测高变异系数
  for (const bench of benchmarks) {
    if (bench.stats.cv > 0.1) {
      recommendations.push(
        `${bench.name}: CV=${(bench.stats.cv * 100).toFixed(1)}% - 考虑增加迭代次数或检查环境稳定性`
      );
    }
    if (bench.outliers.outlierRatio > 0.1) {
      recommendations.push(
        `${bench.name}: ${(bench.outliers.outlierRatio * 100).toFixed(1)}% 异常值 - 检查系统干扰`
      );
    }
  }

  // 确定整体状态
  let status: "pass" | "warn" | "fail" = "pass";
  if (regressions > 0) {
    status = comparisons!.some((c) => c.relativeChange > 0.1) ? "fail" : "warn";
  }

  return {
    totalBenchmarks: benchmarks.length,
    passed: benchmarks.length - regressions,
    regressions,
    improvements,
    status,
    geometricMeanSpeedup: speedups.length > 0 ? geometricMean(speedups) : undefined,
    highlights: highlights.slice(0, 5),
    recommendations: recommendations.slice(0, 5),
  };
}

/**
 * 生成完整报告
 */
export async function generateReport(
  title: string,
  project: string,
  benchmarks: BenchmarkResult[],
  options: {
    baselineBenchmarks?: BenchmarkResult[];
    config?: Partial<BenchmarkConfig>;
  } = {}
): Promise<BenchmarkReport> {
  const metadata = await collectMetadata(options.config);

  // 生成对比结果
  let comparisons: ComparisonResult[] | undefined;
  if (options.baselineBenchmarks) {
    comparisons = [];
    for (const current of benchmarks) {
      const baseline = options.baselineBenchmarks.find((b) => b.id === current.id);
      if (baseline) {
        comparisons.push(compareBenchmarks(baseline, current));
      }
    }
  }

  const summary = generateSummary(benchmarks, comparisons);

  return {
    version: "1.0.0",
    title,
    project,
    generatedAt: new Date().toISOString(),
    metadata,
    benchmarks,
    comparisons,
    summary,
  };
}

// ==================== Output Formats ====================

/**
 * 导出为 JSON
 */
export function exportJSON(report: BenchmarkReport): string {
  return JSON.stringify(report, null, 2);
}

/**
 * 导出为 Markdown
 */
export function exportMarkdown(report: BenchmarkReport): string {
  const lines: string[] = [];

  // Header
  lines.push(`# ${report.title}`);
  lines.push("");
  lines.push(`**Project:** ${report.project}`);
  lines.push(`**Generated:** ${report.generatedAt}`);
  lines.push(`**Commit:** ${report.metadata.git.commit.slice(0, 8)}${report.metadata.git.dirty ? " (dirty)" : ""}`);
  lines.push("");

  // Summary
  lines.push("## Summary");
  lines.push("");
  const statusEmoji = report.summary.status === "pass" ? "✅" : report.summary.status === "warn" ? "⚠️" : "❌";
  lines.push(`| Metric | Value |`);
  lines.push(`|--------|-------|`);
  lines.push(`| Status | ${statusEmoji} ${report.summary.status.toUpperCase()} |`);
  lines.push(`| Total Benchmarks | ${report.summary.totalBenchmarks} |`);
  lines.push(`| Passed | ${report.summary.passed} |`);
  lines.push(`| Regressions | ${report.summary.regressions} |`);
  lines.push(`| Improvements | ${report.summary.improvements} |`);
  if (report.summary.geometricMeanSpeedup) {
    lines.push(`| Geometric Mean Speedup | ${report.summary.geometricMeanSpeedup.toFixed(2)}x |`);
  }
  lines.push("");

  // Highlights
  if (report.summary.highlights.length > 0) {
    lines.push("### Highlights");
    lines.push("");
    for (const h of report.summary.highlights) {
      lines.push(`- ${h}`);
    }
    lines.push("");
  }

  // Benchmarks
  lines.push("## Benchmark Results");
  lines.push("");
  lines.push("| Benchmark | Median | σ (MAD) | Min | Max | Samples |");
  lines.push("|-----------|--------|---------|-----|-----|---------|");

  for (const bench of report.benchmarks) {
    const median = formatTime(bench.stats.median.value);
    const mad = formatTime(bench.stats.mad);
    const min = formatTime(bench.stats.min);
    const max = formatTime(bench.stats.max);
    lines.push(`| ${bench.name} | ${median} | ${mad} | ${min} | ${max} | ${bench.stats.samples} |`);
  }
  lines.push("");

  // Comparisons
  if (report.comparisons && report.comparisons.length > 0) {
    lines.push("## Comparison vs Baseline");
    lines.push("");
    lines.push("| Benchmark | Baseline | Current | Change | Speedup | Significant |");
    lines.push("|-----------|----------|---------|--------|---------|-------------|");

    for (const comp of report.comparisons) {
      const baseline = formatTime(comp.baseline.median);
      const current = formatTime(comp.current.median);
      const change = formatChange(comp.relativeChange);
      const spd = comp.speedup.toFixed(2) + "x";
      const sig = comp.significant ? "✓" : "-";
      const typeEmoji = comp.changeType === "improvement" ? "🟢" : comp.changeType === "regression" ? "🔴" : "⚪";
      lines.push(`| ${comp.benchmarkId} | ${baseline} | ${current} | ${typeEmoji} ${change} | ${spd} | ${sig} |`);
    }
    lines.push("");
  }

  // Environment
  lines.push("## Environment");
  lines.push("");
  lines.push("### Hardware");
  lines.push("");
  lines.push(`- **CPU:** ${report.metadata.hardware.cpuModel}`);
  lines.push(`- **Cores:** ${report.metadata.hardware.cpuCores}`);
  lines.push(`- **Memory:** ${report.metadata.hardware.memoryGb} GB`);
  lines.push(`- **Architecture:** ${report.metadata.hardware.arch}`);
  lines.push("");

  lines.push("### Software");
  lines.push("");
  lines.push(`- **OS:** ${report.metadata.software.os} ${report.metadata.software.osVersion}`);
  lines.push(`- **Build Type:** ${report.metadata.software.buildType}`);
  lines.push("");

  lines.push("### Configuration");
  lines.push("");
  lines.push(`- **Warmup Iterations:** ${report.metadata.config.warmupIterations}`);
  lines.push(`- **Measurement Iterations:** ${report.metadata.config.measurementIterations}`);
  lines.push(`- **Remove Outliers:** ${report.metadata.config.removeOutliers}`);
  lines.push(`- **Confidence Level:** ${report.metadata.config.confidenceLevel * 100}%`);
  lines.push("");

  // Recommendations
  if (report.summary.recommendations.length > 0) {
    lines.push("## Recommendations");
    lines.push("");
    for (const r of report.summary.recommendations) {
      lines.push(`- ${r}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

/**
 * 导出为 CSV (用于外部分析)
 */
export function exportCSV(report: BenchmarkReport): string {
  const lines: string[] = [];

  // Header
  lines.push("benchmark_id,name,type,median_ns,mean_ns,stddev_ns,mad_ns,min_ns,max_ns,samples,p50,p75,p90,p95,p99");

  // Data
  for (const bench of report.benchmarks) {
    const row = [
      bench.id,
      `"${bench.name}"`,
      bench.type,
      bench.stats.median.value,
      bench.stats.mean.value,
      bench.stats.stddev,
      bench.stats.mad,
      bench.stats.min,
      bench.stats.max,
      bench.stats.samples,
      bench.stats.percentiles.p50,
      bench.stats.percentiles.p75,
      bench.stats.percentiles.p90,
      bench.stats.percentiles.p95,
      bench.stats.percentiles.p99,
    ];
    lines.push(row.join(","));
  }

  return lines.join("\n");
}

/**
 * 导出原始数据 (用于趋势分析)
 */
export function exportRawData(report: BenchmarkReport): string {
  const lines: string[] = [];

  lines.push("benchmark_id,iteration,value_ns");

  for (const bench of report.benchmarks) {
    if (bench.rawData) {
      bench.rawData.forEach((value, i) => {
        lines.push(`${bench.id},${i},${value}`);
      });
    }
  }

  return lines.join("\n");
}
