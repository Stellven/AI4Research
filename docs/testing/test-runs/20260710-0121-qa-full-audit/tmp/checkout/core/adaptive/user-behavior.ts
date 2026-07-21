/**
 * Solar AI OS - 用户行为分析与自适应模块
 *
 * 功能:
 * 1. 记录用户使用行为 (命令、工具调用、Agent 交互)
 * 2. 定期分析行为模式，提取用户喜好
 * 3. 基于喜好自动推荐/生成: Skills, Agents, Hooks, Workflows
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

// ==================== Types ====================

export interface UserAction {
  timestamp: number;
  type: "command" | "tool_call" | "agent_interaction" | "skill_use" | "mode_switch";
  action: string;
  context: {
    project?: string;
    phase?: string;
    agent?: string;
    duration?: number;
    success?: boolean;
    tokens?: number;
  };
  metadata?: Record<string, unknown>;
}

export interface UserPreference {
  category: string;
  key: string;
  value: unknown;
  confidence: number; // 0-1
  learnedAt: number;
  updatedAt: number;
  evidence: string[]; // 支持这个偏好的证据
}

export interface SkillRecommendation {
  type: "install" | "develop" | "configure";
  skill: string;
  reason: string;
  priority: "high" | "medium" | "low";
  source?: string; // URL for install, or spec for develop
}

export interface AgentRecommendation {
  agentId: string;
  role: string;
  reason: string;
  capabilities: string[];
}

export interface HookRecommendation {
  hook: string;
  event: string;
  action: string;
  reason: string;
}

export interface WorkflowRecommendation {
  name: string;
  steps: string[];
  reason: string;
  trigger?: string;
}

export interface AdaptiveInsights {
  preferences: UserPreference[];
  skillRecommendations: SkillRecommendation[];
  agentRecommendations: AgentRecommendation[];
  hookRecommendations: HookRecommendation[];
  workflowRecommendations: WorkflowRecommendation[];
  analyzedAt: number;
}

// ==================== Behavior Recorder ====================

export class BehaviorRecorder {
  private actions: UserAction[] = [];
  private storagePath: string;
  private maxActionsInMemory = 1000;

  constructor(storagePath?: string) {
    this.storagePath = storagePath ?? join(process.env.HOME ?? "~", ".solar", "behavior");
    this.ensureStorageDir();
    this.loadRecentActions();
  }

  private ensureStorageDir(): void {
    if (!existsSync(this.storagePath)) {
      mkdirSync(this.storagePath, { recursive: true });
    }
  }

  private loadRecentActions(): void {
    const recentFile = join(this.storagePath, "recent-actions.json");
    if (existsSync(recentFile)) {
      try {
        this.actions = JSON.parse(readFileSync(recentFile, "utf-8"));
      } catch {
        this.actions = [];
      }
    }
  }

  /**
   * 记录用户行为
   */
  record(action: Omit<UserAction, "timestamp">): void {
    const fullAction: UserAction = {
      ...action,
      timestamp: Date.now(),
    };

    this.actions.push(fullAction);

    // 内存限制
    if (this.actions.length > this.maxActionsInMemory) {
      this.archiveOldActions();
    }

    // 实时保存最近行为
    this.saveRecentActions();
  }

  /**
   * 记录命令执行
   */
  recordCommand(command: string, context: UserAction["context"] = {}): void {
    this.record({
      type: "command",
      action: command,
      context,
    });
  }

  /**
   * 记录工具调用
   */
  recordToolCall(
    tool: string,
    success: boolean,
    duration: number,
    context: UserAction["context"] = {}
  ): void {
    this.record({
      type: "tool_call",
      action: tool,
      context: { ...context, success, duration },
    });
  }

  /**
   * 记录 Agent 交互
   */
  recordAgentInteraction(
    agent: string,
    task: string,
    success: boolean,
    tokens: number
  ): void {
    this.record({
      type: "agent_interaction",
      action: task,
      context: { agent, success, tokens },
    });
  }

  /**
   * 记录 Skill 使用
   */
  recordSkillUse(skill: string, context: UserAction["context"] = {}): void {
    this.record({
      type: "skill_use",
      action: skill,
      context,
    });
  }

  /**
   * 记录模式切换
   */
  recordModeSwitch(mode: string, project?: string): void {
    this.record({
      type: "mode_switch",
      action: mode,
      context: { project },
    });
  }

  /**
   * 获取最近行为
   */
  getRecentActions(count = 100): UserAction[] {
    return this.actions.slice(-count);
  }

  /**
   * 获取指定时间范围的行为
   */
  getActionsInRange(startTime: number, endTime: number): UserAction[] {
    return this.actions.filter(
      (a) => a.timestamp >= startTime && a.timestamp <= endTime
    );
  }

  /**
   * 获取统计数据
   */
  getStats(): {
    totalActions: number;
    byType: Record<string, number>;
    byAgent: Record<string, number>;
    bySkill: Record<string, number>;
    successRate: number;
  } {
    const byType: Record<string, number> = {};
    const byAgent: Record<string, number> = {};
    const bySkill: Record<string, number> = {};
    let successCount = 0;
    let totalWithSuccess = 0;

    for (const action of this.actions) {
      // By type
      byType[action.type] = (byType[action.type] ?? 0) + 1;

      // By agent
      if (action.context.agent) {
        byAgent[action.context.agent] = (byAgent[action.context.agent] ?? 0) + 1;
      }

      // By skill
      if (action.type === "skill_use") {
        bySkill[action.action] = (bySkill[action.action] ?? 0) + 1;
      }

      // Success rate
      if (action.context.success !== undefined) {
        totalWithSuccess++;
        if (action.context.success) successCount++;
      }
    }

    return {
      totalActions: this.actions.length,
      byType,
      byAgent,
      bySkill,
      successRate: totalWithSuccess > 0 ? successCount / totalWithSuccess : 1,
    };
  }

  private saveRecentActions(): void {
    const recentFile = join(this.storagePath, "recent-actions.json");
    writeFileSync(recentFile, JSON.stringify(this.actions.slice(-500), null, 2));
  }

  private archiveOldActions(): void {
    const archiveDir = join(this.storagePath, "archive");
    if (!existsSync(archiveDir)) {
      mkdirSync(archiveDir, { recursive: true });
    }

    // 归档前半部分
    const toArchive = this.actions.slice(0, this.maxActionsInMemory / 2);
    const archiveFile = join(archiveDir, `actions-${Date.now()}.json`);
    writeFileSync(archiveFile, JSON.stringify(toArchive, null, 2));

    // 保留后半部分
    this.actions = this.actions.slice(this.maxActionsInMemory / 2);
  }
}

// ==================== Preference Analyzer ====================

export class PreferenceAnalyzer {
  private preferences: Map<string, UserPreference> = new Map();
  private storagePath: string;

  constructor(storagePath?: string) {
    this.storagePath = storagePath ?? join(process.env.HOME ?? "~", ".solar", "preferences");
    this.ensureStorageDir();
    this.loadPreferences();
  }

  private ensureStorageDir(): void {
    if (!existsSync(this.storagePath)) {
      mkdirSync(this.storagePath, { recursive: true });
    }
  }

  private loadPreferences(): void {
    const prefFile = join(this.storagePath, "preferences.json");
    if (existsSync(prefFile)) {
      try {
        const prefs: UserPreference[] = JSON.parse(readFileSync(prefFile, "utf-8"));
        for (const pref of prefs) {
          this.preferences.set(`${pref.category}:${pref.key}`, pref);
        }
      } catch {
        // Ignore
      }
    }
  }

  /**
   * 分析用户行为，提取偏好
   */
  analyzeActions(actions: UserAction[]): UserPreference[] {
    const newPreferences: UserPreference[] = [];

    // 1. 分析常用 Agent
    const agentUsage = this.countByField(actions, (a) => a.context.agent);
    const topAgents = this.getTopN(agentUsage, 3);
    if (topAgents.length > 0) {
      newPreferences.push(this.createPreference(
        "agent",
        "preferred_agents",
        topAgents.map((a) => a.key),
        this.calculateConfidence(topAgents[0].count, actions.length),
        topAgents.map((a) => `Used ${a.key} ${a.count} times`)
      ));
    }

    // 2. 分析常用 Skill
    const skillUsage = this.countByField(
      actions.filter((a) => a.type === "skill_use"),
      (a) => a.action
    );
    const topSkills = this.getTopN(skillUsage, 5);
    if (topSkills.length > 0) {
      newPreferences.push(this.createPreference(
        "skill",
        "frequently_used",
        topSkills.map((s) => s.key),
        this.calculateConfidence(topSkills[0].count, actions.length),
        topSkills.map((s) => `Used /${s.key} ${s.count} times`)
      ));
    }

    // 3. 分析工作时间段
    const hourUsage = this.countByField(actions, (a) => {
      const hour = new Date(a.timestamp).getHours();
      if (hour >= 6 && hour < 12) return "morning";
      if (hour >= 12 && hour < 18) return "afternoon";
      if (hour >= 18 && hour < 22) return "evening";
      return "night";
    });
    const peakTime = this.getTopN(hourUsage, 1)[0];
    if (peakTime) {
      newPreferences.push(this.createPreference(
        "schedule",
        "peak_hours",
        peakTime.key,
        this.calculateConfidence(peakTime.count, actions.length),
        [`Most active during ${peakTime.key} (${peakTime.count} actions)`]
      ));
    }

    // 4. 分析项目偏好
    const projectUsage = this.countByField(
      actions.filter((a) => a.context.project),
      (a) => a.context.project!
    );
    const topProjects = this.getTopN(projectUsage, 3);
    if (topProjects.length > 0) {
      newPreferences.push(this.createPreference(
        "project",
        "active_projects",
        topProjects.map((p) => p.key),
        this.calculateConfidence(topProjects[0].count, actions.length),
        topProjects.map((p) => `Worked on ${p.key} ${p.count} times`)
      ));
    }

    // 5. 分析模式偏好
    const modeUsage = this.countByField(
      actions.filter((a) => a.type === "mode_switch"),
      (a) => a.action
    );
    const topModes = this.getTopN(modeUsage, 2);
    if (topModes.length > 0) {
      newPreferences.push(this.createPreference(
        "mode",
        "preferred_modes",
        topModes.map((m) => m.key),
        this.calculateConfidence(topModes[0].count, actions.length),
        topModes.map((m) => `Switched to ${m.key} mode ${m.count} times`)
      ));
    }

    // 6. 分析工具调用模式
    const toolUsage = this.countByField(
      actions.filter((a) => a.type === "tool_call"),
      (a) => a.action
    );
    const topTools = this.getTopN(toolUsage, 10);
    if (topTools.length > 0) {
      newPreferences.push(this.createPreference(
        "tool",
        "frequently_used",
        topTools.map((t) => t.key),
        this.calculateConfidence(topTools[0].count, actions.length),
        topTools.slice(0, 5).map((t) => `Called ${t.key} ${t.count} times`)
      ));
    }

    // 更新存储
    for (const pref of newPreferences) {
      const key = `${pref.category}:${pref.key}`;
      const existing = this.preferences.get(key);
      if (existing) {
        // 合并证据，更新置信度
        pref.evidence = [...new Set([...existing.evidence, ...pref.evidence])].slice(-10);
        pref.confidence = (existing.confidence + pref.confidence) / 2;
        pref.learnedAt = existing.learnedAt;
      }
      this.preferences.set(key, pref);
    }

    this.savePreferences();
    return newPreferences;
  }

  /**
   * 获取所有偏好
   */
  getAllPreferences(): UserPreference[] {
    return Array.from(this.preferences.values());
  }

  /**
   * 获取特定类别的偏好
   */
  getPreferencesByCategory(category: string): UserPreference[] {
    return this.getAllPreferences().filter((p) => p.category === category);
  }

  /**
   * 获取高置信度偏好
   */
  getHighConfidencePreferences(threshold = 0.7): UserPreference[] {
    return this.getAllPreferences().filter((p) => p.confidence >= threshold);
  }

  private countByField<T>(
    items: T[],
    getField: (item: T) => string | undefined
  ): Map<string, number> {
    const counts = new Map<string, number>();
    for (const item of items) {
      const field = getField(item);
      if (field) {
        counts.set(field, (counts.get(field) ?? 0) + 1);
      }
    }
    return counts;
  }

  private getTopN(counts: Map<string, number>, n: number): { key: string; count: number }[] {
    return Array.from(counts.entries())
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, n);
  }

  private calculateConfidence(count: number, total: number): number {
    // 基于出现频率和绝对次数计算置信度
    const frequency = count / Math.max(total, 1);
    const absoluteScore = Math.min(count / 20, 1); // 20次以上满分
    return Math.min((frequency + absoluteScore) / 2, 1);
  }

  private createPreference(
    category: string,
    key: string,
    value: unknown,
    confidence: number,
    evidence: string[]
  ): UserPreference {
    return {
      category,
      key,
      value,
      confidence,
      learnedAt: Date.now(),
      updatedAt: Date.now(),
      evidence,
    };
  }

  private savePreferences(): void {
    const prefFile = join(this.storagePath, "preferences.json");
    writeFileSync(prefFile, JSON.stringify(this.getAllPreferences(), null, 2));
  }
}

// ==================== Adaptive Recommender ====================

export class AdaptiveRecommender {
  private analyzer: PreferenceAnalyzer;
  private storagePath: string;

  constructor(analyzer: PreferenceAnalyzer, storagePath?: string) {
    this.analyzer = analyzer;
    this.storagePath = storagePath ?? join(process.env.HOME ?? "~", ".solar", "adaptive");
    this.ensureStorageDir();
  }

  private ensureStorageDir(): void {
    if (!existsSync(this.storagePath)) {
      mkdirSync(this.storagePath, { recursive: true });
    }
  }

  /**
   * 基于用户偏好生成自适应建议
   */
  generateInsights(actions: UserAction[]): AdaptiveInsights {
    const preferences = this.analyzer.getAllPreferences();
    const stats = this.calculateStats(actions);

    return {
      preferences,
      skillRecommendations: this.recommendSkills(preferences, stats),
      agentRecommendations: this.recommendAgents(preferences, stats),
      hookRecommendations: this.recommendHooks(preferences, stats),
      workflowRecommendations: this.recommendWorkflows(preferences, stats),
      analyzedAt: Date.now(),
    };
  }

  private calculateStats(actions: UserAction[]): {
    toolUsage: Map<string, number>;
    agentUsage: Map<string, number>;
    errorPatterns: Map<string, number>;
    repetitiveActions: string[];
  } {
    const toolUsage = new Map<string, number>();
    const agentUsage = new Map<string, number>();
    const errorPatterns = new Map<string, number>();
    const actionSequences: string[] = [];

    for (const action of actions) {
      if (action.type === "tool_call") {
        toolUsage.set(action.action, (toolUsage.get(action.action) ?? 0) + 1);
        if (!action.context.success) {
          errorPatterns.set(action.action, (errorPatterns.get(action.action) ?? 0) + 1);
        }
      }
      if (action.context.agent) {
        agentUsage.set(action.context.agent, (agentUsage.get(action.context.agent) ?? 0) + 1);
      }
      actionSequences.push(action.action);
    }

    // 检测重复模式
    const repetitiveActions = this.detectRepetitivePatterns(actionSequences);

    return { toolUsage, agentUsage, errorPatterns, repetitiveActions };
  }

  private detectRepetitivePatterns(actions: string[]): string[] {
    const patterns: string[] = [];
    const windowSize = 3;

    // 滑动窗口检测重复序列
    const sequences = new Map<string, number>();
    for (let i = 0; i <= actions.length - windowSize; i++) {
      const seq = actions.slice(i, i + windowSize).join(" -> ");
      sequences.set(seq, (sequences.get(seq) ?? 0) + 1);
    }

    for (const [seq, count] of sequences) {
      if (count >= 3) {
        patterns.push(seq);
      }
    }

    return patterns;
  }

  /**
   * 推荐 Skills
   */
  private recommendSkills(
    preferences: UserPreference[],
    stats: ReturnType<typeof this.calculateStats>
  ): SkillRecommendation[] {
    const recommendations: SkillRecommendation[] = [];

    // 基于高频工具推荐相关 skill
    const toolPref = preferences.find((p) => p.category === "tool" && p.key === "frequently_used");
    if (toolPref) {
      const tools = toolPref.value as string[];

      // Git 相关
      if (tools.some((t) => t.includes("git") || t === "Bash")) {
        recommendations.push({
          type: "configure",
          skill: "git-advanced",
          reason: "频繁使用 Git 操作，建议启用高级 Git 技能",
          priority: "medium",
        });
      }

      // 测试相关
      if (tools.some((t) => t.includes("test") || t.includes("jest") || t.includes("vitest"))) {
        recommendations.push({
          type: "install",
          skill: "test-coverage",
          reason: "频繁运行测试，建议安装测试覆盖率分析技能",
          priority: "medium",
          source: "https://github.com/solar/skills/test-coverage",
        });
      }
    }

    // 基于重复模式推荐自动化 skill
    if (stats.repetitiveActions.length > 0) {
      recommendations.push({
        type: "develop",
        skill: "auto-workflow",
        reason: `检测到重复操作模式: ${stats.repetitiveActions[0]}，建议开发自动化 Skill`,
        priority: "high",
      });
    }

    // 基于错误模式推荐
    for (const [tool, count] of stats.errorPatterns) {
      if (count >= 5) {
        recommendations.push({
          type: "configure",
          skill: `${tool}-helper`,
          reason: `${tool} 经常失败 (${count}次)，建议配置错误处理助手`,
          priority: "high",
        });
      }
    }

    // 基于项目类型推荐
    const projectPref = preferences.find((p) => p.category === "project");
    if (projectPref) {
      const projects = projectPref.value as string[];
      // 可以根据项目名称/类型推荐特定 skill
      if (projects.some((p) => p.toLowerCase().includes("react"))) {
        recommendations.push({
          type: "install",
          skill: "react-devtools",
          reason: "React 项目开发，推荐 React 专用开发工具",
          priority: "low",
        });
      }
    }

    return recommendations;
  }

  /**
   * 推荐 Agents
   */
  private recommendAgents(
    preferences: UserPreference[],
    stats: ReturnType<typeof this.calculateStats>
  ): AgentRecommendation[] {
    const recommendations: AgentRecommendation[] = [];

    // 检查是否缺少特定类型的 Agent
    const agentPref = preferences.find((p) => p.category === "agent" && p.key === "preferred_agents");
    const usedAgents = agentPref ? (agentPref.value as string[]) : [];

    // 如果主要使用 Coder 但很少用 Tester
    if (usedAgents.includes("coder") && !usedAgents.includes("tester")) {
      recommendations.push({
        agentId: "auto-tester",
        role: "自动测试 Agent",
        reason: "频繁编写代码但很少运行测试，建议启用自动测试 Agent",
        capabilities: ["自动生成测试用例", "测试覆盖率分析", "回归测试"],
      });
    }

    // 如果经常有错误
    const totalErrors = Array.from(stats.errorPatterns.values()).reduce((a, b) => a + b, 0);
    if (totalErrors > 10) {
      recommendations.push({
        agentId: "debugger",
        role: "调试专家 Agent",
        reason: `检测到 ${totalErrors} 次操作失败，建议启用调试专家 Agent`,
        capabilities: ["错误分析", "堆栈追踪", "自动修复建议"],
      });
    }

    // 基于模式推荐
    const modePref = preferences.find((p) => p.category === "mode" && p.key === "preferred_modes");
    if (modePref) {
      const modes = modePref.value as string[];
      if (modes.includes("office")) {
        recommendations.push({
          agentId: "scheduler",
          role: "日程调度 Agent",
          reason: "经常使用办公模式，建议启用智能日程调度 Agent",
          capabilities: ["日程规划", "会议提醒", "任务优先级排序"],
        });
      }
    }

    return recommendations;
  }

  /**
   * 推荐 Hooks
   */
  private recommendHooks(
    preferences: UserPreference[],
    stats: ReturnType<typeof this.calculateStats>
  ): HookRecommendation[] {
    const recommendations: HookRecommendation[] = [];

    // 基于错误模式推荐 OnError hook
    if (stats.errorPatterns.size > 0) {
      recommendations.push({
        hook: "auto-retry",
        event: "OnError",
        action: "自动重试失败的操作（最多3次）",
        reason: "检测到频繁的操作失败，建议添加自动重试机制",
      });
    }

    // 基于工作时间推荐
    const schedulePref = preferences.find((p) => p.category === "schedule");
    if (schedulePref && schedulePref.value === "night") {
      recommendations.push({
        hook: "night-mode",
        event: "SessionStart",
        action: "自动启用夜间模式（减少 token 消耗，静默通知）",
        reason: "经常在夜间工作，建议添加夜间模式自动切换",
      });
    }

    // 基于项目偏好推荐
    const projectPref = preferences.find((p) => p.category === "project");
    if (projectPref && (projectPref.value as string[]).length > 1) {
      recommendations.push({
        hook: "project-context",
        event: "ModeSwitch",
        action: "自动加载项目特定配置和上下文",
        reason: "在多个项目间切换，建议添加项目上下文自动加载",
      });
    }

    // 基于常用 skill 推荐
    const skillPref = preferences.find((p) => p.category === "skill");
    if (skillPref) {
      const skills = skillPref.value as string[];
      if (skills.includes("commit")) {
        recommendations.push({
          hook: "pre-commit-check",
          event: "PreToolCall",
          action: "在 git commit 前自动运行 lint 和测试",
          reason: "频繁使用 /commit，建议添加提交前检查",
        });
      }
    }

    return recommendations;
  }

  /**
   * 推荐工作流
   */
  private recommendWorkflows(
    preferences: UserPreference[],
    stats: ReturnType<typeof this.calculateStats>
  ): WorkflowRecommendation[] {
    const recommendations: WorkflowRecommendation[] = [];

    // 基于重复模式生成工作流
    for (const pattern of stats.repetitiveActions.slice(0, 3)) {
      const steps = pattern.split(" -> ");
      recommendations.push({
        name: `auto-${steps[0]}-workflow`,
        steps,
        reason: `检测到重复执行: ${pattern}`,
        trigger: `当开始 ${steps[0]} 时自动执行`,
      });
    }

    // 基于 Agent 使用模式推荐
    const agentSequences = this.detectAgentSequences(stats.agentUsage);
    for (const seq of agentSequences) {
      recommendations.push({
        name: `${seq.from}-to-${seq.to}-flow`,
        steps: [`@${seq.from} 执行任务`, `自动移交给 @${seq.to}`, `验证结果`],
        reason: `经常从 ${seq.from} 切换到 ${seq.to}`,
        trigger: `当 @${seq.from} 完成任务时`,
      });
    }

    return recommendations;
  }

  private detectAgentSequences(
    agentUsage: Map<string, number>
  ): { from: string; to: string }[] {
    // 简化实现：返回使用最多的两个 agent 的组合
    const sorted = Array.from(agentUsage.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 2);

    if (sorted.length === 2) {
      return [{ from: sorted[0][0], to: sorted[1][0] }];
    }
    return [];
  }

  /**
   * 保存分析结果
   */
  saveInsights(insights: AdaptiveInsights): void {
    const insightsFile = join(this.storagePath, "insights.json");
    writeFileSync(insightsFile, JSON.stringify(insights, null, 2));

    // 同时保存人类可读的报告
    this.saveHumanReadableReport(insights);
  }

  private saveHumanReadableReport(insights: AdaptiveInsights): void {
    const reportFile = join(this.storagePath, "adaptive-report.md");
    const lines: string[] = [
      "# Solar 自适应分析报告",
      "",
      `> 分析时间: ${new Date(insights.analyzedAt).toLocaleString()}`,
      "",
      "## 用户偏好",
      "",
    ];

    for (const pref of insights.preferences) {
      lines.push(`### ${pref.category}: ${pref.key}`);
      lines.push(`- **值**: ${JSON.stringify(pref.value)}`);
      lines.push(`- **置信度**: ${(pref.confidence * 100).toFixed(0)}%`);
      lines.push(`- **证据**: ${pref.evidence.slice(0, 3).join(", ")}`);
      lines.push("");
    }

    lines.push("## Skill 推荐", "");
    for (const rec of insights.skillRecommendations) {
      lines.push(`- **[${rec.priority}] ${rec.skill}** (${rec.type})`);
      lines.push(`  ${rec.reason}`);
    }

    lines.push("", "## Agent 推荐", "");
    for (const rec of insights.agentRecommendations) {
      lines.push(`- **${rec.agentId}**: ${rec.role}`);
      lines.push(`  ${rec.reason}`);
      lines.push(`  能力: ${rec.capabilities.join(", ")}`);
    }

    lines.push("", "## Hook 推荐", "");
    for (const rec of insights.hookRecommendations) {
      lines.push(`- **${rec.hook}** (${rec.event})`);
      lines.push(`  ${rec.reason}`);
    }

    lines.push("", "## 工作流推荐", "");
    for (const rec of insights.workflowRecommendations) {
      lines.push(`- **${rec.name}**`);
      lines.push(`  步骤: ${rec.steps.join(" → ")}`);
      lines.push(`  ${rec.reason}`);
    }

    writeFileSync(reportFile, lines.join("\n"));
  }
}

// ==================== Adaptive Engine ====================

export class AdaptiveEngine {
  private recorder: BehaviorRecorder;
  private analyzer: PreferenceAnalyzer;
  private recommender: AdaptiveRecommender;
  private analysisInterval: NodeJS.Timeout | null = null;

  constructor(basePath?: string) {
    const base = basePath ?? join(process.env.HOME ?? "~", ".solar");
    this.recorder = new BehaviorRecorder(join(base, "behavior"));
    this.analyzer = new PreferenceAnalyzer(join(base, "preferences"));
    this.recommender = new AdaptiveRecommender(this.analyzer, join(base, "adaptive"));
  }

  /**
   * 启动自适应引擎
   */
  start(intervalMs = 3600000): void {
    // 默认每小时分析一次
    this.analysisInterval = setInterval(() => {
      this.runAnalysis();
    }, intervalMs);

    console.log(`[Adaptive] Engine started, analysis interval: ${intervalMs}ms`);
  }

  /**
   * 停止自适应引擎
   */
  stop(): void {
    if (this.analysisInterval) {
      clearInterval(this.analysisInterval);
      this.analysisInterval = null;
    }
    console.log("[Adaptive] Engine stopped");
  }

  /**
   * 记录行为
   */
  record(action: Omit<UserAction, "timestamp">): void {
    this.recorder.record(action);
  }

  /**
   * 手动触发分析
   */
  runAnalysis(): AdaptiveInsights {
    const actions = this.recorder.getRecentActions(500);
    this.analyzer.analyzeActions(actions);
    const insights = this.recommender.generateInsights(actions);
    this.recommender.saveInsights(insights);
    return insights;
  }

  /**
   * 获取当前偏好
   */
  getPreferences(): UserPreference[] {
    return this.analyzer.getAllPreferences();
  }

  /**
   * 获取统计信息
   */
  getStats(): ReturnType<BehaviorRecorder["getStats"]> {
    return this.recorder.getStats();
  }

  /**
   * 获取最新分析结果
   */
  getLatestInsights(): AdaptiveInsights | null {
    const insightsFile = join(
      process.env.HOME ?? "~",
      ".solar",
      "adaptive",
      "insights.json"
    );
    if (existsSync(insightsFile)) {
      try {
        return JSON.parse(readFileSync(insightsFile, "utf-8"));
      } catch {
        return null;
      }
    }
    return null;
  }
}

// ==================== Exports ====================

export function createAdaptiveEngine(basePath?: string): AdaptiveEngine {
  return new AdaptiveEngine(basePath);
}

// 单例
let globalEngine: AdaptiveEngine | null = null;

export function getAdaptiveEngine(): AdaptiveEngine {
  if (!globalEngine) {
    globalEngine = createAdaptiveEngine();
  }
  return globalEngine;
}
