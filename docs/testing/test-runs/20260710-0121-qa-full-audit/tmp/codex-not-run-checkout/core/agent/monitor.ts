/**
 * Solar AI OS - Monitor Agent
 *
 * 资源监控 Agent - 监控 Token 使用、系统资源、异常检测、成本优化
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";

// ==================== Types ====================

export interface TokenUsage {
  timestamp: number;
  input: number;
  output: number;
  total: number;
  model: string;
  session: string;
  task?: string;
}

export interface SessionStats {
  sessionId: string;
  startTime: number;
  endTime?: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalTokens: number;
  requestCount: number;
  errorCount: number;
  avgResponseTime: number;
  peakTokensPerMinute: number;
  costEstimate: number;
}

export interface RateLimitStatus {
  requestsUsed: number;
  requestsLimit: number;
  tokensUsed: number;
  tokensLimit: number;
  resetTime: number;
  percentUsed: number;
}

export interface Alert {
  id: string;
  type: "token_threshold" | "rate_limit" | "error_spike" | "cost_warning" | "anomaly";
  severity: "info" | "warning" | "critical";
  message: string;
  timestamp: number;
  acknowledged: boolean;
  metadata?: Record<string, unknown>;
}

export interface MonitorConfig {
  tokenThreshold: number;           // Token 使用阈值 (触发警告)
  tokenCritical: number;            // Token 临界值 (触发严重警告)
  rateLimitThreshold: number;       // Rate limit 阈值 (%)
  errorSpikeThreshold: number;      // 错误峰值阈值 (每分钟)
  costWarningThreshold: number;     // 成本警告阈值 ($)
  anomalyDetection: boolean;        // 启用异常检测
  alertCallback?: (alert: Alert) => void;  // 警告回调
}

// ==================== Cost Calculator ====================

const MODEL_COSTS = {
  "claude-opus-4-5-20251101": { input: 15, output: 75 },     // per 1M tokens
  "claude-sonnet-4-20250514": { input: 3, output: 15 },
  "claude-haiku-3-5-20241022": { input: 0.8, output: 4 },
  "default": { input: 3, output: 15 },
};

function calculateCost(inputTokens: number, outputTokens: number, model: string): number {
  const costs = MODEL_COSTS[model as keyof typeof MODEL_COSTS] ?? MODEL_COSTS.default;
  const inputCost = (inputTokens / 1_000_000) * costs.input;
  const outputCost = (outputTokens / 1_000_000) * costs.output;
  return inputCost + outputCost;
}

// ==================== Monitor Agent ====================

export class MonitorAgent {
  private config: MonitorConfig;
  private storagePath: string;
  private usageHistory: TokenUsage[] = [];
  private alerts: Alert[] = [];
  private currentSession: SessionStats | null = null;
  private alertIdCounter = 0;

  constructor(config?: Partial<MonitorConfig>) {
    this.config = {
      tokenThreshold: 50000,
      tokenCritical: 80000,
      rateLimitThreshold: 80,
      errorSpikeThreshold: 5,
      costWarningThreshold: 1.0,
      anomalyDetection: true,
      ...config,
    };
    this.storagePath = join(process.env.HOME ?? "~", ".solar", "monitor");
    this.ensureStorage();
    this.loadHistory();
  }

  private ensureStorage(): void {
    if (!existsSync(this.storagePath)) {
      mkdirSync(this.storagePath, { recursive: true });
    }
  }

  private loadHistory(): void {
    const historyFile = join(this.storagePath, "usage-history.json");
    if (existsSync(historyFile)) {
      try {
        this.usageHistory = JSON.parse(readFileSync(historyFile, "utf-8"));
      } catch {
        this.usageHistory = [];
      }
    }

    const alertsFile = join(this.storagePath, "alerts.json");
    if (existsSync(alertsFile)) {
      try {
        this.alerts = JSON.parse(readFileSync(alertsFile, "utf-8"));
      } catch {
        this.alerts = [];
      }
    }
  }

  private saveHistory(): void {
    const historyFile = join(this.storagePath, "usage-history.json");
    // 只保留最近 1000 条记录
    const toSave = this.usageHistory.slice(-1000);
    writeFileSync(historyFile, JSON.stringify(toSave, null, 2));

    const alertsFile = join(this.storagePath, "alerts.json");
    // 只保留最近 100 条警告
    const alertsToSave = this.alerts.slice(-100);
    writeFileSync(alertsFile, JSON.stringify(alertsToSave, null, 2));
  }

  // ==================== Session Management ====================

  /**
   * 开始新会话
   */
  startSession(sessionId?: string): string {
    const id = sessionId ?? `session_${Date.now()}`;
    this.currentSession = {
      sessionId: id,
      startTime: Date.now(),
      totalInputTokens: 0,
      totalOutputTokens: 0,
      totalTokens: 0,
      requestCount: 0,
      errorCount: 0,
      avgResponseTime: 0,
      peakTokensPerMinute: 0,
      costEstimate: 0,
    };
    return id;
  }

  /**
   * 结束会话
   */
  endSession(): SessionStats | null {
    if (!this.currentSession) return null;

    this.currentSession.endTime = Date.now();
    const stats = { ...this.currentSession };

    // 保存会话统计
    const sessionsFile = join(this.storagePath, "sessions.json");
    let sessions: SessionStats[] = [];
    if (existsSync(sessionsFile)) {
      try {
        sessions = JSON.parse(readFileSync(sessionsFile, "utf-8"));
      } catch {
        sessions = [];
      }
    }
    sessions.push(stats);
    writeFileSync(sessionsFile, JSON.stringify(sessions.slice(-50), null, 2));

    this.currentSession = null;
    return stats;
  }

  // ==================== Token Tracking ====================

  /**
   * 记录 Token 使用
   */
  recordUsage(
    inputTokens: number,
    outputTokens: number,
    model: string,
    task?: string
  ): void {
    const usage: TokenUsage = {
      timestamp: Date.now(),
      input: inputTokens,
      output: outputTokens,
      total: inputTokens + outputTokens,
      model,
      session: this.currentSession?.sessionId ?? "unknown",
      task,
    };

    this.usageHistory.push(usage);

    // 更新会话统计
    if (this.currentSession) {
      this.currentSession.totalInputTokens += inputTokens;
      this.currentSession.totalOutputTokens += outputTokens;
      this.currentSession.totalTokens += inputTokens + outputTokens;
      this.currentSession.requestCount++;
      this.currentSession.costEstimate = calculateCost(
        this.currentSession.totalInputTokens,
        this.currentSession.totalOutputTokens,
        model
      );

      // 计算每分钟峰值
      const oneMinuteAgo = Date.now() - 60000;
      const recentUsage = this.usageHistory.filter((u) => u.timestamp > oneMinuteAgo);
      const tokensPerMinute = recentUsage.reduce((sum, u) => sum + u.total, 0);
      if (tokensPerMinute > this.currentSession.peakTokensPerMinute) {
        this.currentSession.peakTokensPerMinute = tokensPerMinute;
      }
    }

    // 检查阈值
    this.checkThresholds();

    // 保存
    this.saveHistory();
  }

  /**
   * 记录错误
   */
  recordError(error: string): void {
    if (this.currentSession) {
      this.currentSession.errorCount++;
    }

    // 检查错误峰值
    const oneMinuteAgo = Date.now() - 60000;
    const recentErrors = this.alerts.filter(
      (a) => a.type === "error_spike" && a.timestamp > oneMinuteAgo
    );

    if (recentErrors.length >= this.config.errorSpikeThreshold) {
      this.createAlert({
        type: "error_spike",
        severity: "warning",
        message: `错误峰值: ${recentErrors.length} 个错误在 1 分钟内`,
        metadata: { error },
      });
    }
  }

  // ==================== Threshold Checking ====================

  private checkThresholds(): void {
    if (!this.currentSession) return;

    const { totalTokens, costEstimate } = this.currentSession;

    // Token 阈值检查
    if (totalTokens >= this.config.tokenCritical) {
      this.createAlert({
        type: "token_threshold",
        severity: "critical",
        message: `Token 使用已达临界值: ${totalTokens.toLocaleString()} / ${this.config.tokenCritical.toLocaleString()}`,
        metadata: { totalTokens, threshold: this.config.tokenCritical },
      });
    } else if (totalTokens >= this.config.tokenThreshold) {
      this.createAlert({
        type: "token_threshold",
        severity: "warning",
        message: `Token 使用超过阈值: ${totalTokens.toLocaleString()} / ${this.config.tokenThreshold.toLocaleString()}`,
        metadata: { totalTokens, threshold: this.config.tokenThreshold },
      });
    }

    // 成本检查
    if (costEstimate >= this.config.costWarningThreshold) {
      this.createAlert({
        type: "cost_warning",
        severity: "warning",
        message: `会话成本警告: $${costEstimate.toFixed(4)} (阈值: $${this.config.costWarningThreshold})`,
        metadata: { costEstimate },
      });
    }

    // 异常检测
    if (this.config.anomalyDetection) {
      this.detectAnomalies();
    }
  }

  private detectAnomalies(): void {
    // 计算过去 10 次请求的平均 token 使用
    const recent = this.usageHistory.slice(-10);
    if (recent.length < 5) return;

    const avgTokens = recent.reduce((sum, u) => sum + u.total, 0) / recent.length;
    const lastUsage = recent[recent.length - 1];

    // 如果最后一次使用超过平均值的 3 倍，视为异常
    if (lastUsage.total > avgTokens * 3) {
      this.createAlert({
        type: "anomaly",
        severity: "info",
        message: `检测到异常 Token 使用: ${lastUsage.total} (平均: ${Math.round(avgTokens)})`,
        metadata: { actual: lastUsage.total, average: avgTokens },
      });
    }
  }

  // ==================== Alert Management ====================

  private createAlert(alert: Omit<Alert, "id" | "timestamp" | "acknowledged">): void {
    // 检查是否有相同类型的未确认警告 (去重)
    const existingAlert = this.alerts.find(
      (a) =>
        a.type === alert.type &&
        !a.acknowledged &&
        Date.now() - a.timestamp < 300000 // 5 分钟内
    );

    if (existingAlert) return;

    const fullAlert: Alert = {
      id: `alert_${++this.alertIdCounter}`,
      timestamp: Date.now(),
      acknowledged: false,
      ...alert,
    };

    this.alerts.push(fullAlert);

    // 触发回调
    if (this.config.alertCallback) {
      this.config.alertCallback(fullAlert);
    }

    this.saveHistory();
  }

  /**
   * 确认警告
   */
  acknowledgeAlert(alertId: string): boolean {
    const alert = this.alerts.find((a) => a.id === alertId);
    if (alert) {
      alert.acknowledged = true;
      this.saveHistory();
      return true;
    }
    return false;
  }

  /**
   * 获取未确认的警告
   */
  getActiveAlerts(): Alert[] {
    return this.alerts.filter((a) => !a.acknowledged);
  }

  // ==================== Statistics ====================

  /**
   * 获取当前会话统计
   */
  getCurrentStats(): SessionStats | null {
    return this.currentSession ? { ...this.currentSession } : null;
  }

  /**
   * 获取使用报告
   */
  getUsageReport(options: { hours?: number; days?: number } = {}): {
    totalTokens: number;
    totalCost: number;
    byModel: Record<string, { tokens: number; cost: number }>;
    byHour: Record<string, number>;
    avgTokensPerRequest: number;
    requestCount: number;
  } {
    const since = Date.now() - (options.days ?? 1) * 24 * 60 * 60 * 1000;
    const filtered = this.usageHistory.filter((u) => u.timestamp >= since);

    const byModel: Record<string, { tokens: number; cost: number }> = {};
    const byHour: Record<string, number> = {};
    let totalTokens = 0;
    let totalCost = 0;

    for (const usage of filtered) {
      totalTokens += usage.total;
      totalCost += calculateCost(usage.input, usage.output, usage.model);

      // By model
      if (!byModel[usage.model]) {
        byModel[usage.model] = { tokens: 0, cost: 0 };
      }
      byModel[usage.model].tokens += usage.total;
      byModel[usage.model].cost += calculateCost(usage.input, usage.output, usage.model);

      // By hour
      const hour = new Date(usage.timestamp).getHours().toString().padStart(2, "0");
      byHour[hour] = (byHour[hour] ?? 0) + usage.total;
    }

    return {
      totalTokens,
      totalCost,
      byModel,
      byHour,
      avgTokensPerRequest: filtered.length > 0 ? totalTokens / filtered.length : 0,
      requestCount: filtered.length,
    };
  }

  /**
   * 获取优化建议
   */
  getOptimizationSuggestions(): string[] {
    const suggestions: string[] = [];
    const report = this.getUsageReport({ days: 7 });

    // 基于使用模式生成建议
    if (report.avgTokensPerRequest > 10000) {
      suggestions.push("平均每次请求 Token 使用较高，考虑拆分复杂任务");
    }

    if (report.byModel["claude-opus-4-5-20251101"]) {
      const opusRatio =
        report.byModel["claude-opus-4-5-20251101"].tokens / report.totalTokens;
      if (opusRatio > 0.5) {
        suggestions.push("Opus 使用占比较高，简单任务可切换到 Sonnet 降低成本");
      }
    }

    // 基于时间模式
    const peakHours = Object.entries(report.byHour)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([h]) => h);
    if (peakHours.length > 0) {
      suggestions.push(`高峰使用时段: ${peakHours.join(", ")} 点，可考虑预缓存常用上下文`);
    }

    // 基于成本
    if (report.totalCost > 5) {
      suggestions.push("周成本超过 $5，考虑启用上下文压缩或使用更轻量模型");
    }

    // 基于警告历史
    const recentAlerts = this.alerts.filter(
      (a) => Date.now() - a.timestamp < 7 * 24 * 60 * 60 * 1000
    );
    const thresholdAlerts = recentAlerts.filter((a) => a.type === "token_threshold");
    if (thresholdAlerts.length > 5) {
      suggestions.push("频繁触发 Token 阈值警告，建议提高阈值或优化使用模式");
    }

    return suggestions;
  }

  // ==================== Display ====================

  /**
   * 生成状态显示
   */
  renderStatus(): string[] {
    const lines: string[] = [];
    const stats = this.currentSession;

    lines.push("┌─ 📊 Monitor Agent ─────────────────────────────────────┐");

    if (stats) {
      const duration = Date.now() - stats.startTime;
      const minutes = Math.floor(duration / 60000);

      lines.push(`│ Session: ${stats.sessionId.slice(0, 20).padEnd(20)}                     │`);
      lines.push(`│ Duration: ${minutes} min                                         │`);
      lines.push(`├──────────────────────────────────────────────────────────┤`);
      lines.push(`│ Tokens:  ${stats.totalTokens.toLocaleString().padEnd(12)} (I: ${stats.totalInputTokens.toLocaleString()} / O: ${stats.totalOutputTokens.toLocaleString()})`.padEnd(59) + "│");
      lines.push(`│ Cost:    $${stats.costEstimate.toFixed(4).padEnd(10)} Requests: ${stats.requestCount}`.padEnd(59) + "│");
      lines.push(`│ Errors:  ${stats.errorCount.toString().padEnd(12)} Peak: ${stats.peakTokensPerMinute.toLocaleString()}/min`.padEnd(59) + "│");

      // Progress bar
      const threshold = this.config.tokenThreshold;
      const percent = Math.min(100, Math.round((stats.totalTokens / threshold) * 100));
      const barWidth = 30;
      const filled = Math.round((percent / 100) * barWidth);
      const bar = "█".repeat(filled) + "░".repeat(barWidth - filled);
      const color = percent >= 90 ? "🔴" : percent >= 70 ? "🟡" : "🟢";

      lines.push(`├──────────────────────────────────────────────────────────┤`);
      lines.push(`│ ${color} [${bar}] ${percent}%`.padEnd(58) + "│");
    } else {
      lines.push("│ No active session                                        │");
    }

    // Active alerts
    const activeAlerts = this.getActiveAlerts();
    if (activeAlerts.length > 0) {
      lines.push(`├──────────────────────────────────────────────────────────┤`);
      lines.push(`│ ⚠️ Alerts (${activeAlerts.length})                                           │`);
      for (const alert of activeAlerts.slice(0, 3)) {
        const icon = alert.severity === "critical" ? "🔴" : alert.severity === "warning" ? "🟡" : "🔵";
        lines.push(`│ ${icon} ${alert.message.slice(0, 50).padEnd(50)}   │`);
      }
    }

    lines.push("└──────────────────────────────────────────────────────────┘");

    return lines;
  }
}

// ==================== Factory ====================

let globalMonitor: MonitorAgent | null = null;

export function getMonitorAgent(config?: Partial<MonitorConfig>): MonitorAgent {
  if (!globalMonitor) {
    globalMonitor = new MonitorAgent(config);
  }
  return globalMonitor;
}

export function createMonitorAgent(config?: Partial<MonitorConfig>): MonitorAgent {
  return new MonitorAgent(config);
}
