/**
 * Solar Benchmark Module
 *
 * 专业的性能测试框架，基于业界最佳实践
 *
 * @example
 * ```typescript
 * import { createBenchmarkResult, generateReport, exportMarkdown } from 'solar/core/benchmark';
 *
 * // 创建基准测试结果
 * const result = createBenchmarkResult(
 *   'hash_join_1M',
 *   'HashJoin 1M rows',
 *   rawTimings,
 *   { type: 'operator', unit: 'ms' }
 * );
 *
 * // 生成报告
 * const report = await generateReport('TPC-H Benchmark', 'ThunderDuck', [result]);
 *
 * // 导出
 * console.log(exportMarkdown(report));
 * ```
 */

// Schema
export type {
  TimeUnit,
  BenchmarkType,
  ConfidenceLevel,
  Estimate,
  Statistics,
  OutlierAnalysis,
  HardwareInfo,
  SoftwareInfo,
  GitInfo,
  EnvironmentInfo,
  BenchmarkConfig,
  BenchmarkMetadata,
  BenchmarkResult,
  ChangeType,
  ComparisonResult,
  BenchmarkReport,
  ReportSummary,
  HistoryPoint,
  TrendData,
} from "./schema";

export { BENCHMARK_PRESETS, REGRESSION_THRESHOLDS } from "./schema";

// Statistics
export {
  median,
  mean,
  stddev,
  mad,
  madToStddev,
  percentile,
  quartiles,
  iqr,
  coefficientOfVariation,
  detectOutliers,
  removeOutliers,
  bootstrapCI,
  computeStatistics,
  cohensD,
  welchTTest,
  speedup,
  geometricMean,
  convertTimeUnit,
  autoTimeUnit,
  formatTime,
  formatChange,
  formatSpeedup,
} from "./statistics";

// Reporter
export {
  collectHardwareInfo,
  collectSoftwareInfo,
  collectGitInfo,
  collectMetadata,
  createBenchmarkResult,
  compareBenchmarks,
  generateSummary,
  generateReport,
  exportJSON,
  exportMarkdown,
  exportCSV,
  exportRawData,
} from "./reporter";

// Trend Analysis
export type { RegressionAlert } from "./trend";
export {
  ensureBenchmarkDir,
  saveReport,
  loadReport,
  listReports,
  getBaseline,
  setBaseline,
  buildTrendData,
  getAllTrends,
  detectRegressions,
  renderTrendChart,
  generateTrendSummary,
} from "./trend";
