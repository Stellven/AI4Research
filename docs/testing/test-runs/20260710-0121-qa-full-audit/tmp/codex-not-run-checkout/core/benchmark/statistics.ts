/**
 * Solar Benchmark Statistics Library
 *
 * 基于业界最佳实践的统计分析工具
 * - 使用中位数而非平均值
 * - MAD/IQR 代替标准差
 * - Bootstrap 置信区间
 * - Tukey's Fences 异常值检测
 *
 * @version 1.0.0
 */

import type {
  Statistics,
  Estimate,
  OutlierAnalysis,
  ConfidenceLevel,
  TimeUnit,
} from "./schema";

// ==================== Basic Statistics ====================

/**
 * 计算中位数
 */
export function median(data: number[]): number {
  if (data.length === 0) return 0;
  const sorted = [...data].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * 计算平均值
 */
export function mean(data: number[]): number {
  if (data.length === 0) return 0;
  return data.reduce((sum, v) => sum + v, 0) / data.length;
}

/**
 * 计算标准差
 */
export function stddev(data: number[]): number {
  if (data.length < 2) return 0;
  const avg = mean(data);
  const squaredDiffs = data.map((v) => (v - avg) ** 2);
  return Math.sqrt(squaredDiffs.reduce((sum, v) => sum + v, 0) / (data.length - 1));
}

/**
 * 计算中位数绝对偏差 (MAD)
 * MAD = median(|Xi - median(X)|)
 */
export function mad(data: number[]): number {
  if (data.length === 0) return 0;
  const med = median(data);
  const deviations = data.map((v) => Math.abs(v - med));
  return median(deviations);
}

/**
 * MAD 转换为标准差估计 (使用 k=1.4826)
 */
export function madToStddev(madValue: number): number {
  return madValue * 1.4826;
}

/**
 * 计算百分位数
 */
export function percentile(data: number[], p: number): number {
  if (data.length === 0) return 0;
  const sorted = [...data].sort((a, b) => a - b);
  const index = (p / 100) * (sorted.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] * (upper - index) + sorted[upper] * (index - lower);
}

/**
 * 计算四分位数
 */
export function quartiles(data: number[]): { q1: number; q2: number; q3: number } {
  return {
    q1: percentile(data, 25),
    q2: percentile(data, 50),
    q3: percentile(data, 75),
  };
}

/**
 * 计算四分位距 (IQR)
 */
export function iqr(data: number[]): number {
  const q = quartiles(data);
  return q.q3 - q.q1;
}

/**
 * 计算变异系数 (CV)
 */
export function coefficientOfVariation(data: number[]): number {
  const avg = mean(data);
  if (avg === 0) return 0;
  return stddev(data) / avg;
}

// ==================== Outlier Detection ====================

/**
 * Tukey's Fences 异常值检测
 * 异常值定义: < Q1 - 1.5*IQR 或 > Q3 + 1.5*IQR
 */
export function detectOutliers(data: number[]): OutlierAnalysis {
  const q = quartiles(data);
  const iqrValue = q.q3 - q.q1;
  const lowerFence = q.q1 - 1.5 * iqrValue;
  const upperFence = q.q3 + 1.5 * iqrValue;

  const outlierIndices: number[] = [];
  let lowOutliers = 0;
  let highOutliers = 0;

  data.forEach((v, i) => {
    if (v < lowerFence) {
      lowOutliers++;
      outlierIndices.push(i);
    } else if (v > upperFence) {
      highOutliers++;
      outlierIndices.push(i);
    }
  });

  return {
    lowerFence,
    upperFence,
    lowOutliers,
    highOutliers,
    outlierIndices,
    outlierRatio: (lowOutliers + highOutliers) / data.length,
  };
}

/**
 * 移除异常值
 */
export function removeOutliers(data: number[]): number[] {
  const analysis = detectOutliers(data);
  return data.filter((v) => v >= analysis.lowerFence && v <= analysis.upperFence);
}

// ==================== Bootstrap Confidence Intervals ====================

/**
 * 简单随机数生成器 (用于可重复性)
 */
class SimpleRng {
  private seed: number;

  constructor(seed: number = Date.now()) {
    this.seed = seed;
  }

  next(): number {
    // Linear Congruential Generator
    this.seed = (this.seed * 1103515245 + 12345) & 0x7fffffff;
    return this.seed / 0x7fffffff;
  }

  nextInt(max: number): number {
    return Math.floor(this.next() * max);
  }
}

/**
 * Bootstrap 重采样
 */
function bootstrapSample(data: number[], rng: SimpleRng): number[] {
  const n = data.length;
  const sample: number[] = new Array(n);
  for (let i = 0; i < n; i++) {
    sample[i] = data[rng.nextInt(n)];
  }
  return sample;
}

/**
 * Bootstrap 置信区间
 * 使用 percentile method
 */
export function bootstrapCI(
  data: number[],
  statFn: (d: number[]) => number,
  confidence: ConfidenceLevel = 0.95,
  iterations: number = 1000,
  seed?: number
): { lower: number; upper: number; estimate: number } {
  const rng = new SimpleRng(seed);
  const estimates: number[] = [];

  for (let i = 0; i < iterations; i++) {
    const sample = bootstrapSample(data, rng);
    estimates.push(statFn(sample));
  }

  estimates.sort((a, b) => a - b);

  const alpha = 1 - confidence;
  const lowerIdx = Math.floor((alpha / 2) * iterations);
  const upperIdx = Math.floor((1 - alpha / 2) * iterations);

  return {
    lower: estimates[lowerIdx],
    upper: estimates[upperIdx],
    estimate: statFn(data),
  };
}

// ==================== Complete Statistics ====================

/**
 * 计算完整统计摘要
 */
export function computeStatistics(
  data: number[],
  unit: TimeUnit = "ns",
  confidence: ConfidenceLevel = 0.95,
  removeOutliersFlag: boolean = true
): Statistics {
  // 原始数据统计
  const rawOutliers = detectOutliers(data);

  // 是否移除异常值
  const cleanData = removeOutliersFlag ? removeOutliers(data) : data;

  // 基本统计
  const medianValue = median(cleanData);
  const meanValue = mean(cleanData);
  const stddevValue = stddev(cleanData);
  const madValue = mad(cleanData);
  const iqrValue = iqr(cleanData);

  // Bootstrap 置信区间
  const medianCI = bootstrapCI(cleanData, median, confidence);
  const meanCI = bootstrapCI(cleanData, mean, confidence);

  return {
    samples: data.length,
    median: {
      value: medianValue,
      lower: medianCI.lower,
      upper: medianCI.upper,
      confidence,
      unit,
    },
    mean: {
      value: meanValue,
      lower: meanCI.lower,
      upper: meanCI.upper,
      confidence,
      unit,
    },
    min: Math.min(...cleanData),
    max: Math.max(...cleanData),
    mad: madValue,
    iqr: iqrValue,
    stddev: stddevValue,
    cv: coefficientOfVariation(cleanData),
    percentiles: {
      p50: percentile(cleanData, 50),
      p75: percentile(cleanData, 75),
      p90: percentile(cleanData, 90),
      p95: percentile(cleanData, 95),
      p99: percentile(cleanData, 99),
      p999: percentile(cleanData, 99.9),
    },
  };
}

// ==================== Comparison Statistics ====================

/**
 * 计算 Cohen's d 效应量
 */
export function cohensD(group1: number[], group2: number[]): number {
  const n1 = group1.length;
  const n2 = group2.length;
  const mean1 = mean(group1);
  const mean2 = mean(group2);
  const var1 = stddev(group1) ** 2;
  const var2 = stddev(group2) ** 2;

  // Pooled standard deviation
  const pooledStd = Math.sqrt(
    ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
  );

  return (mean1 - mean2) / pooledStd;
}

/**
 * Welch's t-test (不假设等方差)
 * 返回 t 统计量和近似自由度
 */
export function welchTTest(
  group1: number[],
  group2: number[]
): { t: number; df: number; significant: boolean } {
  const n1 = group1.length;
  const n2 = group2.length;
  const mean1 = mean(group1);
  const mean2 = mean(group2);
  const var1 = stddev(group1) ** 2;
  const var2 = stddev(group2) ** 2;

  const se = Math.sqrt(var1 / n1 + var2 / n2);
  const t = (mean1 - mean2) / se;

  // Welch-Satterthwaite 自由度
  const num = (var1 / n1 + var2 / n2) ** 2;
  const denom =
    (var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1);
  const df = num / denom;

  // 简化的显著性检测 (p < 0.05, 双尾)
  // 对于 df > 30, t > 2.0 通常显著
  const criticalT = df > 30 ? 2.0 : 2.042; // 近似值
  const significant = Math.abs(t) > criticalT;

  return { t, df, significant };
}

/**
 * 计算加速比
 */
export function speedup(baseline: number, current: number): number {
  if (current === 0) return Infinity;
  return baseline / current;
}

/**
 * 计算几何平均
 */
export function geometricMean(values: number[]): number {
  if (values.length === 0) return 0;
  if (values.some((v) => v <= 0)) {
    // 对于加速比，使用对数变换处理
    const logSum = values.reduce((sum, v) => sum + Math.log(Math.max(v, 0.001)), 0);
    return Math.exp(logSum / values.length);
  }
  const product = values.reduce((prod, v) => prod * v, 1);
  return Math.pow(product, 1 / values.length);
}

// ==================== Utilities ====================

/**
 * 时间单位转换
 */
export function convertTimeUnit(
  value: number,
  from: TimeUnit,
  to: TimeUnit
): number {
  const toNs: Record<TimeUnit, number> = {
    ns: 1,
    us: 1000,
    ms: 1000000,
    s: 1000000000,
  };
  return (value * toNs[from]) / toNs[to];
}

/**
 * 自动选择合适的时间单位
 */
export function autoTimeUnit(valueNs: number): TimeUnit {
  if (valueNs >= 1e9) return "s";
  if (valueNs >= 1e6) return "ms";
  if (valueNs >= 1e3) return "us";
  return "ns";
}

/**
 * 格式化时间值
 */
export function formatTime(valueNs: number, precision: number = 2): string {
  const unit = autoTimeUnit(valueNs);
  const converted = convertTimeUnit(valueNs, "ns", unit);
  return `${converted.toFixed(precision)} ${unit}`;
}

/**
 * 格式化百分比变化
 */
export function formatChange(change: number): string {
  const sign = change >= 0 ? "+" : "";
  return `${sign}${(change * 100).toFixed(1)}%`;
}

/**
 * 格式化加速比
 */
export function formatSpeedup(speedupValue: number): string {
  if (speedupValue >= 1) {
    return `${speedupValue.toFixed(2)}x faster`;
  } else {
    return `${(1 / speedupValue).toFixed(2)}x slower`;
  }
}
