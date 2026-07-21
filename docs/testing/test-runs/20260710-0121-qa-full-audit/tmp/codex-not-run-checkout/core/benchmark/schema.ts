/**
 * Solar Benchmark Report Schema
 *
 * 基于业界最佳实践的性能测试数据结构
 * 参考: Google Benchmark, Criterion.rs, hyperfine, Gil Tene's guidelines
 *
 * @version 1.0.0
 */

// ==================== Core Types ====================

/**
 * 时间单位
 */
export type TimeUnit = "ns" | "us" | "ms" | "s";

/**
 * 基准测试类型
 */
export type BenchmarkType =
  | "micro"      // 微基准测试 (<1ms)
  | "operator"   // 算子基准测试 (1-100ms)
  | "query"      // 查询基准测试 (>100ms)
  | "e2e"        // 端到端测试
  | "throughput" // 吞吐量测试
  | "latency";   // 延迟测试

/**
 * 统计置信度
 */
export type ConfidenceLevel = 0.90 | 0.95 | 0.99;

// ==================== Statistical Types ====================

/**
 * 带置信区间的估计值
 */
export interface Estimate {
  /** 点估计值 */
  value: number;
  /** 置信区间下界 */
  lower: number;
  /** 置信区间上界 */
  upper: number;
  /** 置信度 (0.95 = 95%) */
  confidence: ConfidenceLevel;
  /** 单位 */
  unit: TimeUnit;
}

/**
 * 完整统计摘要
 */
export interface Statistics {
  /** 样本数量 */
  samples: number;
  /** 中位数 (主要指标) */
  median: Estimate;
  /** 平均值 (参考) */
  mean: Estimate;
  /** 最小值 */
  min: number;
  /** 最大值 (不要忽略！) */
  max: number;
  /** 中位数绝对偏差 (MAD) */
  mad: number;
  /** 四分位距 (IQR) */
  iqr: number;
  /** 标准差 (参考) */
  stddev: number;
  /** 变异系数 (CV = stddev/mean) */
  cv: number;
  /** 百分位数 */
  percentiles: {
    p50: number;
    p75: number;
    p90: number;
    p95: number;
    p99: number;
    p999: number;
  };
}

/**
 * 异常值分析 (Tukey's Fences)
 */
export interface OutlierAnalysis {
  /** 下界 (Q1 - 1.5*IQR) */
  lowerFence: number;
  /** 上界 (Q3 + 1.5*IQR) */
  upperFence: number;
  /** 低异常值数量 */
  lowOutliers: number;
  /** 高异常值数量 */
  highOutliers: number;
  /** 异常值索引 */
  outlierIndices: number[];
  /** 异常值比例 */
  outlierRatio: number;
}

// ==================== Metadata Types ====================

/**
 * 硬件信息
 */
export interface HardwareInfo {
  /** CPU 型号 */
  cpuModel: string;
  /** CPU 核心数 */
  cpuCores: number;
  /** CPU 频率 (MHz) */
  cpuFreqMhz: number;
  /** 内存大小 (GB) */
  memoryGb: number;
  /** L1 数据缓存 (KB) */
  cacheL1dKb?: number;
  /** L2 缓存 (KB) */
  cacheL2Kb?: number;
  /** L3 缓存 (KB) */
  cacheL3Kb?: number;
  /** 存储类型 */
  storageType?: "hdd" | "ssd" | "nvme";
  /** 架构 */
  arch: "x86_64" | "arm64" | "other";
}

/**
 * 软件信息
 */
export interface SoftwareInfo {
  /** 操作系统 */
  os: string;
  /** 操作系统版本 */
  osVersion: string;
  /** 编译器 */
  compiler: string;
  /** 编译器版本 */
  compilerVersion: string;
  /** 编译标志 */
  compilerFlags: string;
  /** 构建类型 */
  buildType: "debug" | "release" | "relwithdebinfo";
  /** 运行时版本 (如适用) */
  runtimeVersion?: string;
}

/**
 * Git 信息
 */
export interface GitInfo {
  /** 提交 SHA */
  commit: string;
  /** 分支名 */
  branch: string;
  /** 是否有未提交更改 */
  dirty: boolean;
  /** 提交时间 */
  commitDate?: string;
  /** 标签 (如果有) */
  tag?: string;
}

/**
 * 环境配置
 */
export interface EnvironmentInfo {
  /** Turbo Boost 状态 */
  turboBoost?: boolean;
  /** CPU 调度器 */
  cpuGovernor?: "performance" | "powersave" | "ondemand";
  /** 隔离的 CPU 核心 */
  isolatedCpus?: number[];
  /** 超线程/SMT 状态 */
  hyperthreading?: boolean;
  /** 后台进程负载 */
  systemLoad?: number;
}

/**
 * 基准测试配置
 */
export interface BenchmarkConfig {
  /** 预热迭代次数 */
  warmupIterations: number;
  /** 测量迭代次数 */
  measurementIterations: number;
  /** 输入大小 */
  inputSize?: number;
  /** 随机种子 */
  randomSeed?: number;
  /** 超时时间 (秒) */
  timeout?: number;
  /** 是否剔除异常值 */
  removeOutliers: boolean;
  /** 置信度 */
  confidenceLevel: ConfidenceLevel;
}

/**
 * 完整元数据
 */
export interface BenchmarkMetadata {
  /** 时间戳 (ISO 8601) */
  timestamp: string;
  /** 硬件信息 */
  hardware: HardwareInfo;
  /** 软件信息 */
  software: SoftwareInfo;
  /** Git 信息 */
  git: GitInfo;
  /** 环境配置 */
  environment: EnvironmentInfo;
  /** 基准测试配置 */
  config: BenchmarkConfig;
}

// ==================== Benchmark Result Types ====================

/**
 * 单个基准测试结果
 */
export interface BenchmarkResult {
  /** 唯一标识符 (用于趋势追踪) */
  id: string;
  /** 显示名称 */
  name: string;
  /** 基准测试类型 */
  type: BenchmarkType;
  /** 描述 */
  description?: string;
  /** 输入参数 */
  params?: Record<string, number | string>;
  /** 统计结果 */
  stats: Statistics;
  /** 异常值分析 */
  outliers: OutlierAnalysis;
  /** 原始数据 (可选) */
  rawData?: number[];
  /** 吞吐量 (每秒处理量) */
  throughput?: {
    itemsPerSecond: number;
    bytesPerSecond?: number;
  };
  /** 自定义指标 */
  customMetrics?: Record<string, number>;
}

// ==================== Comparison Types ====================

/**
 * 变化类型
 */
export type ChangeType =
  | "improvement"  // 性能提升
  | "regression"   // 性能回退
  | "nochange"     // 无显著变化
  | "uncertain";   // 不确定

/**
 * 基准对比结果
 */
export interface ComparisonResult {
  /** 基准测试 ID */
  benchmarkId: string;
  /** 基准版本结果 */
  baseline: {
    median: number;
    ci: [number, number];
    commit: string;
  };
  /** 当前版本结果 */
  current: {
    median: number;
    ci: [number, number];
    commit: string;
  };
  /** 绝对变化 */
  absoluteChange: number;
  /** 相对变化 (百分比) */
  relativeChange: number;
  /** 变化类型 */
  changeType: ChangeType;
  /** 加速比 */
  speedup: number;
  /** 统计显著性 (p-value < 0.05) */
  significant: boolean;
  /** 效应量 (Cohen's d) */
  effectSize: number;
}

// ==================== Report Types ====================

/**
 * 完整基准测试报告
 */
export interface BenchmarkReport {
  /** 报告版本 */
  version: "1.0.0";
  /** 报告标题 */
  title: string;
  /** 项目名称 */
  project: string;
  /** 报告生成时间 */
  generatedAt: string;
  /** 元数据 */
  metadata: BenchmarkMetadata;
  /** 基准测试结果 */
  benchmarks: BenchmarkResult[];
  /** 对比结果 (如果有基准版本) */
  comparisons?: ComparisonResult[];
  /** 摘要 */
  summary: ReportSummary;
}

/**
 * 报告摘要
 */
export interface ReportSummary {
  /** 总测试数 */
  totalBenchmarks: number;
  /** 通过数 */
  passed: number;
  /** 回退数 */
  regressions: number;
  /** 改进数 */
  improvements: number;
  /** 整体状态 */
  status: "pass" | "warn" | "fail";
  /** 几何平均加速比 */
  geometricMeanSpeedup?: number;
  /** 关键发现 */
  highlights: string[];
  /** 建议 */
  recommendations: string[];
}

// ==================== Trend Types ====================

/**
 * 历史数据点
 */
export interface HistoryPoint {
  /** 提交 SHA */
  commit: string;
  /** 时间戳 */
  timestamp: string;
  /** 中位数 */
  median: number;
  /** 置信区间 */
  ci: [number, number];
  /** 样本数 */
  samples: number;
}

/**
 * 趋势数据
 */
export interface TrendData {
  /** 基准测试 ID */
  benchmarkId: string;
  /** 历史数据 */
  history: HistoryPoint[];
  /** 趋势方向 */
  trend: "improving" | "degrading" | "stable";
  /** 最近 N 次的变化率 */
  recentChangeRate: number;
}

// ==================== Template Presets ====================

/**
 * 基准测试配置预设
 */
export const BENCHMARK_PRESETS: Record<BenchmarkType, BenchmarkConfig> = {
  micro: {
    warmupIterations: 100,
    measurementIterations: 1000,
    removeOutliers: true,
    confidenceLevel: 0.95,
  },
  operator: {
    warmupIterations: 5,
    measurementIterations: 30,
    removeOutliers: true,
    confidenceLevel: 0.95,
  },
  query: {
    warmupIterations: 2,
    measurementIterations: 10,
    removeOutliers: true,
    confidenceLevel: 0.95,
  },
  e2e: {
    warmupIterations: 1,
    measurementIterations: 5,
    removeOutliers: false,
    confidenceLevel: 0.95,
  },
  throughput: {
    warmupIterations: 3,
    measurementIterations: 20,
    removeOutliers: true,
    confidenceLevel: 0.95,
  },
  latency: {
    warmupIterations: 5,
    measurementIterations: 100,
    removeOutliers: false, // 延迟测试不剔除异常值！
    confidenceLevel: 0.99,
  },
};

/**
 * 回退检测阈值
 */
export const REGRESSION_THRESHOLDS = {
  /** 警告阈值 (%) */
  warn: 5,
  /** 失败阈值 (%) */
  fail: 10,
  /** 统计显著性 p-value */
  significanceLevel: 0.05,
  /** 最小效应量 */
  minEffectSize: 0.2,
};
