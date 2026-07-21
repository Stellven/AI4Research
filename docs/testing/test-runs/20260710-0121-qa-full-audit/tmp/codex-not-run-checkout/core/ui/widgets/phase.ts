/**
 * Solar Phase Widget
 *
 * 显示 Solar 五阶段流程状态
 *
 * P1研究 → P2设计 → P3实现 → P4验证 → P5收尾
 */

import { card, kv, bar } from "tvs/termplane/sdk/widget";
import type { CardLayout } from "tvs/termplane/render/types";

// ==================== Types ====================

export interface PhaseData {
  current: Phase;
  phases: PhaseStatus[];
  gates: GateStatus[];
  project?: string;
  version?: string;
}

export type Phase = "P1" | "P2" | "P3" | "P4" | "P5";

export interface PhaseStatus {
  id: Phase;
  name: string;
  status: "completed" | "current" | "pending";
  progress?: number;
}

export interface GateStatus {
  id: "G1" | "G2" | "G3";
  passed: boolean;
  retries?: number;
}

// ==================== Constants ====================

export const PHASES = [
  { id: "P1" as Phase, name: "研究", emoji: "🔬" },
  { id: "P2" as Phase, name: "设计", emoji: "🏗️" },
  { id: "P3" as Phase, name: "实现", emoji: "💻" },
  { id: "P4" as Phase, name: "验证", emoji: "🧪" },
  { id: "P5" as Phase, name: "收尾", emoji: "📦" },
];

export const GATES = [
  { id: "G1" as const, name: "设计评审", position: "P2后" },
  { id: "G2" as const, name: "验证通过", position: "P4后" },
  { id: "G3" as const, name: "交付确认", position: "P5后" },
];

// ==================== Widget ====================

export class PhaseWidget {
  readonly id = "solar.phase";
  readonly title = "Solar Phase";

  /**
   * 生成模拟数据
   */
  mockData(currentPhase: Phase = "P3"): PhaseData {
    const currentIndex = PHASES.findIndex((p) => p.id === currentPhase);

    return {
      current: currentPhase,
      phases: PHASES.map((phase, idx) => ({
        id: phase.id,
        name: phase.name,
        status:
          idx < currentIndex
            ? "completed"
            : idx === currentIndex
              ? "current"
              : "pending",
        progress: idx === currentIndex ? 0.65 : idx < currentIndex ? 1 : 0,
      })),
      gates: [
        { id: "G1", passed: currentIndex > 1 },
        { id: "G2", passed: currentIndex > 3 },
        { id: "G3", passed: currentIndex >= 4 },
      ],
      project: "ThunderDuck",
      version: "v1.0.0",
    };
  }

  /**
   * 渲染 Widget
   */
  render(data: PhaseData): CardLayout {
    // 流程进度条
    const progressLine = PHASES.map((phase, idx) => {
      const status = data.phases.find((p) => p.id === phase.id)?.status;
      if (status === "completed") return "✅";
      if (status === "current") return "🔄";
      return "⬜";
    }).join(" → ");

    // Phase 详情
    const currentPhase = data.phases.find((p) => p.status === "current");
    const phaseInfo = PHASES.find((p) => p.id === data.current);

    return card("☀️ SOLAR FLOW", [
      { type: "text", content: progressLine, align: "center" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          {
            key: "Phase",
            value: `${phaseInfo?.emoji} ${data.current} ${phaseInfo?.name}`,
            status: "success",
          },
          { key: "Project", value: data.project || "-" },
          { key: "Version", value: data.version || "-" },
        ],
      },
      ...(currentPhase?.progress !== undefined
        ? [{ type: "bar" as const, value: currentPhase.progress, label: "Progress" }]
        : []),
    ]);
  }

  /**
   * 渲染 Gate 状态
   */
  renderGates(data: PhaseData): CardLayout {
    const items = data.gates.map((gate) => {
      const gateInfo = GATES.find((g) => g.id === gate.id);
      return {
        key: `${gate.id} ${gateInfo?.name}`,
        value: gate.passed ? "PASSED" : "PENDING",
        status: gate.passed ? ("success" as const) : ("warning" as const),
      };
    });

    return card("🚪 GATES", [{ type: "kv", items }]);
  }
}

export const phaseWidget = new PhaseWidget();
