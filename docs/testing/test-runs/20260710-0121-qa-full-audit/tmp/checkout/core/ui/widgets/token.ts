/**
 * Solar Token Widget
 *
 * 显示 Token 使用统计和 Rate Limit 状态
 */

import { card, kv, bar, sparkline } from "tvs/termplane/sdk/widget";
import type { CardLayout } from "tvs/termplane/render/types";

// ==================== Types ====================

export interface TokenData {
  session: {
    input: number;
    output: number;
    total: number;
  };
  rateLimit: {
    used: number;
    limit: number;
    resetIn: number; // seconds
  };
  cost: {
    session: number;
    daily: number;
  };
  history: number[]; // last N token counts
  timestamp: number;
}

// ==================== Widget ====================

export class TokenWidget {
  readonly id = "solar.token";
  readonly title = "Token Stats";

  /**
   * 生成模拟数据
   */
  mockData(): TokenData {
    return {
      session: {
        input: 8234,
        output: 4122,
        total: 12356,
      },
      rateLimit: {
        used: 45000,
        limit: 100000,
        resetIn: 1847,
      },
      cost: {
        session: 0.12,
        daily: 2.45,
      },
      history: Array.from({ length: 20 }, () => Math.random() * 0.8 + 0.1),
      timestamp: Date.now(),
    };
  }

  /**
   * 格式化数字
   */
  private formatNumber(n: number): string {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toString();
  }

  /**
   * 格式化时间
   */
  private formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  /**
   * 渲染 Widget
   */
  render(data: TokenData): CardLayout {
    const ratePercent = Math.round((data.rateLimit.used / data.rateLimit.limit) * 100);
    const rateStatus: "success" | "warning" | "error" =
      ratePercent < 50 ? "success" : ratePercent < 80 ? "warning" : "error";

    return card("🎫 TOKEN STATS", [
      {
        type: "kv",
        items: [
          { key: "Session", value: this.formatNumber(data.session.total) },
          { key: "Input", value: this.formatNumber(data.session.input) },
          { key: "Output", value: this.formatNumber(data.session.output) },
        ],
      },
      { type: "divider" },
      {
        type: "bar",
        value: data.rateLimit.used / data.rateLimit.limit,
        label: "Rate",
      },
      {
        type: "kv",
        items: [
          { key: "Rate", value: `${ratePercent}%`, status: rateStatus },
          { key: "Reset", value: this.formatTime(data.rateLimit.resetIn) },
        ],
      },
    ]);
  }

  /**
   * 渲染简洁版本
   */
  renderCompact(data: TokenData): CardLayout {
    const ratePercent = Math.round((data.rateLimit.used / data.rateLimit.limit) * 100);

    return card("🎫 TOKENS", [
      {
        type: "kv",
        items: [
          { key: "Total", value: this.formatNumber(data.session.total) },
          { key: "Rate", value: `${ratePercent}%` },
          { key: "Cost", value: `$${data.cost.session.toFixed(2)}` },
        ],
      },
      { type: "sparkline", data: data.history, label: "Usage" },
    ]);
  }
}

export const tokenWidget = new TokenWidget();
