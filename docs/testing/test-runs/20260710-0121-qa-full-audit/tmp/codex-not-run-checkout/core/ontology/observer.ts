/**
 * Solar Preference Observer
 * 从会话和用户行为中提取偏好信号
 */

import { PreferenceSignal } from "./types";

export interface SessionData {
  sessionId: string;
  startTime: Date;
  endTime?: Date;
  messageCount: number;
  tokenUsage: { input: number; output: number };
  toolCalls: { tool: string; count: number; successRate: number }[];
  agentInteractions: { agent: string; count: number }[];
  userFeedback?: string[];
  project?: string;
}

export class PreferenceObserver {
  /**
   * 从会话数据中提取偏好信号
   */
  extractSignals(session: SessionData): PreferenceSignal[] {
    const signals: PreferenceSignal[] = [];
    const now = new Date();

    // 1. 工作时间偏好
    signals.push(this.extractWorkTimeSignal(session.startTime, now));

    // 2. 会话深度偏好
    signals.push(this.extractSessionDepthSignal(session.messageCount, now));

    // 3. 从用户反馈中提取信号
    if (session.userFeedback) {
      signals.push(...this.extractFeedbackSignals(session.userFeedback, now));
    }

    // 4. 从工具使用中推断偏好
    signals.push(...this.extractToolUsageSignals(session.toolCalls, now));

    // 5. Token 使用模式
    signals.push(this.extractCostSensitivitySignal(session.tokenUsage, now));

    return signals.filter((s) => s !== null) as PreferenceSignal[];
  }

  /**
   * 从显式用户反馈中提取信号
   */
  extractFromExplicitFeedback(feedback: string): PreferenceSignal[] {
    const signals: PreferenceSignal[] = [];
    const now = new Date();
    const feedbackLower = feedback.toLowerCase();

    // 详细程度反馈
    if (feedbackLower.includes("太长") || feedbackLower.includes("简洁") || feedbackLower.includes("精简")) {
      signals.push({
        dimension_id: "verbosity",
        value: 0.2,
        weight: 3.0, // 显式反馈权重高
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }
    if (feedbackLower.includes("详细") || feedbackLower.includes("更多信息") || feedbackLower.includes("展开")) {
      signals.push({
        dimension_id: "verbosity",
        value: 0.8,
        weight: 3.0,
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }

    // 解释需求反馈
    if (feedbackLower.includes("直接做") || feedbackLower.includes("别解释") || feedbackLower.includes("不用解释")) {
      signals.push({
        dimension_id: "explanation",
        value: 0.1,
        weight: 3.0,
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }
    if (feedbackLower.includes("解释一下") || feedbackLower.includes("为什么") || feedbackLower.includes("说明")) {
      signals.push({
        dimension_id: "explanation",
        value: 0.9,
        weight: 2.0,
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }

    // 速度 vs 质量反馈
    if (feedbackLower.includes("快点") || feedbackLower.includes("速度") || feedbackLower.includes("赶紧")) {
      signals.push({
        dimension_id: "speed_vs_quality",
        value: 0.2,
        weight: 2.0,
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }
    if (feedbackLower.includes("质量") || feedbackLower.includes("仔细") || feedbackLower.includes("认真")) {
      signals.push({
        dimension_id: "speed_vs_quality",
        value: 0.9,
        weight: 2.0,
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }

    // 自动化信任反馈
    if (feedbackLower.includes("自动") || feedbackLower.includes("不用确认") || feedbackLower.includes("直接执行")) {
      signals.push({
        dimension_id: "automation_trust",
        value: 0.9,
        weight: 2.5,
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }
    if (feedbackLower.includes("先确认") || feedbackLower.includes("问我") || feedbackLower.includes("等等")) {
      signals.push({
        dimension_id: "automation_trust",
        value: 0.2,
        weight: 2.5,
        source: "explicit",
        timestamp: now,
        evidence: `用户反馈: "${feedback}"`,
      });
    }

    // 正面反馈 (强化当前行为)
    if (
      feedbackLower.includes("不错") ||
      feedbackLower.includes("可以") ||
      feedbackLower.includes("好的") ||
      feedbackLower.includes("行")
    ) {
      // 正面反馈不改变偏好值，但增加置信度
      // 这里返回一个特殊的信号表示强化
      signals.push({
        dimension_id: "_reinforce_current",
        value: 1.0,
        weight: 0.5,
        source: "feedback",
        timestamp: now,
        evidence: `正面反馈: "${feedback}"`,
      });
    }

    return signals;
  }

  // ==================== 私有方法 ====================

  private extractWorkTimeSignal(startTime: Date, now: Date): PreferenceSignal {
    const hour = startTime.getHours();
    let timeCategory: string;
    let value: number;

    if (hour >= 6 && hour < 12) {
      timeCategory = "morning";
      value = 0.0;
    } else if (hour >= 12 && hour < 18) {
      timeCategory = "afternoon";
      value = 0.33;
    } else if (hour >= 18 && hour < 22) {
      timeCategory = "evening";
      value = 0.67;
    } else {
      timeCategory = "night";
      value = 1.0;
    }

    return {
      dimension_id: "work_time",
      value,
      weight: 1.0,
      source: "session",
      timestamp: now,
      evidence: `会话开始于 ${hour}:00 (${timeCategory})`,
    };
  }

  private extractSessionDepthSignal(messageCount: number, now: Date): PreferenceSignal {
    // 归一化: 0-50 = 短, 50-200 = 中, 200+ = 长
    const normalized = Math.min(messageCount / 300, 1.0);

    return {
      dimension_id: "session_depth",
      value: normalized,
      weight: 1.0,
      source: "session",
      timestamp: now,
      evidence: `会话消息数: ${messageCount}`,
    };
  }

  private extractFeedbackSignals(feedback: string[], now: Date): PreferenceSignal[] {
    const signals: PreferenceSignal[] = [];

    for (const fb of feedback) {
      signals.push(...this.extractFromExplicitFeedback(fb));
    }

    return signals;
  }

  private extractToolUsageSignals(
    toolCalls: { tool: string; count: number; successRate: number }[],
    now: Date
  ): PreferenceSignal[] {
    const signals: PreferenceSignal[] = [];

    // 如果频繁使用测试工具，说明重视质量
    const testTools = toolCalls.filter(
      (t) => t.tool.toLowerCase().includes("test") || t.tool.toLowerCase().includes("benchmark")
    );
    if (testTools.length > 0) {
      const totalTestCalls = testTools.reduce((sum, t) => sum + t.count, 0);
      if (totalTestCalls > 5) {
        signals.push({
          dimension_id: "speed_vs_quality",
          value: 0.8,
          weight: 0.5,
          source: "session",
          timestamp: now,
          evidence: `频繁使用测试工具 (${totalTestCalls} 次)`,
        });
      }
    }

    // 如果频繁使用 Git 工具，说明重视版本控制
    const gitTools = toolCalls.filter((t) => t.tool.toLowerCase().includes("git"));
    if (gitTools.length > 0) {
      const totalGitCalls = gitTools.reduce((sum, t) => sum + t.count, 0);
      if (totalGitCalls > 3) {
        signals.push({
          dimension_id: "risk_tolerance",
          value: 0.3, // 频繁提交说明风险规避
          weight: 0.3,
          source: "session",
          timestamp: now,
          evidence: `频繁使用 Git 工具 (${totalGitCalls} 次)`,
        });
      }
    }

    return signals;
  }

  private extractCostSensitivitySignal(
    tokenUsage: { input: number; output: number },
    now: Date
  ): PreferenceSignal {
    const total = tokenUsage.input + tokenUsage.output;
    // 如果 token 使用较低，可能对成本敏感
    // 这是一个弱信号
    const normalized = Math.min(total / 100000, 1.0);

    return {
      dimension_id: "cost_sensitivity",
      value: 1 - normalized, // 使用越少，敏感度越高
      weight: 0.2, // 弱信号
      source: "session",
      timestamp: now,
      evidence: `Token 使用: ${total}`,
    };
  }
}

// ==================== Factory ====================

let _observer: PreferenceObserver | null = null;

export function getPreferenceObserver(): PreferenceObserver {
  if (!_observer) {
    _observer = new PreferenceObserver();
  }
  return _observer;
}
