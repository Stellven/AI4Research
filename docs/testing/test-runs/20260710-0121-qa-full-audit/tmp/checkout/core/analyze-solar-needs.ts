/**
 * Solar 自适应分析 - 分析 Solar 还需要什么功能
 *
 * 基于用户行为分析模块，模拟并分析当前使用模式
 */

import {
  BehaviorRecorder,
  PreferenceAnalyzer,
  AdaptiveRecommender,
  type UserAction,
  type AdaptiveInsights,
} from "./adaptive";

// ==================== 模拟历史行为数据 ====================

function generateSimulatedBehavior(): UserAction[] {
  const now = Date.now();
  const hour = 3600000;
  const day = 24 * hour;

  // 基于 Solar 项目的实际使用模式生成模拟数据
  const actions: UserAction[] = [
    // ========== 开发模式相关 ==========
    { timestamp: now - 7 * day, type: "mode_switch", action: "dev", context: { project: "ThunderDuck" } },
    { timestamp: now - 7 * day + hour, type: "agent_interaction", action: "analyze codebase", context: { agent: "researcher", success: true, tokens: 2500 } },
    { timestamp: now - 7 * day + 2 * hour, type: "agent_interaction", action: "design optimization", context: { agent: "architect", success: true, tokens: 3200 } },
    { timestamp: now - 7 * day + 3 * hour, type: "agent_interaction", action: "implement SIMD filter", context: { agent: "coder", success: true, tokens: 5000 } },
    { timestamp: now - 7 * day + 4 * hour, type: "agent_interaction", action: "run benchmarks", context: { agent: "tester", success: true, tokens: 1500 } },

    // ========== 工具调用 ==========
    { timestamp: now - 6 * day, type: "tool_call", action: "Read", context: { success: true, duration: 50 } },
    { timestamp: now - 6 * day, type: "tool_call", action: "Read", context: { success: true, duration: 45 } },
    { timestamp: now - 6 * day, type: "tool_call", action: "Grep", context: { success: true, duration: 120 } },
    { timestamp: now - 6 * day, type: "tool_call", action: "Glob", context: { success: true, duration: 80 } },
    { timestamp: now - 6 * day, type: "tool_call", action: "Write", context: { success: true, duration: 30 } },
    { timestamp: now - 6 * day, type: "tool_call", action: "Edit", context: { success: true, duration: 25 } },
    { timestamp: now - 6 * day, type: "tool_call", action: "Bash", context: { success: true, duration: 500 } },
    { timestamp: now - 6 * day, type: "tool_call", action: "Bash", context: { success: false, duration: 100 } }, // 失败
    { timestamp: now - 6 * day, type: "tool_call", action: "Task", context: { success: true, duration: 3000 } },

    // ========== Skill 使用 ==========
    { timestamp: now - 5 * day, type: "skill_use", action: "commit", context: { project: "ThunderDuck" } },
    { timestamp: now - 5 * day, type: "skill_use", action: "commit", context: { project: "ThunderDuck" } },
    { timestamp: now - 4 * day, type: "skill_use", action: "commit", context: { project: "Solar" } },
    { timestamp: now - 4 * day, type: "skill_use", action: "test", context: { project: "Solar" } },
    { timestamp: now - 3 * day, type: "skill_use", action: "benchmark", context: { project: "ThunderDuck" } },
    { timestamp: now - 3 * day, type: "skill_use", action: "benchmark", context: { project: "ThunderDuck" } },
    { timestamp: now - 2 * day, type: "skill_use", action: "review", context: { project: "ThunderDuck" } },
    { timestamp: now - 1 * day, type: "skill_use", action: "solar", context: { project: "Solar" } },
    { timestamp: now - 1 * day, type: "skill_use", action: "status", context: {} },
    { timestamp: now - 1 * day, type: "skill_use", action: "save", context: {} },
    { timestamp: now - 1 * day, type: "skill_use", action: "restore", context: {} },

    // ========== 命令执行 ==========
    { timestamp: now - 5 * day, type: "command", action: "git status", context: { project: "ThunderDuck" } },
    { timestamp: now - 5 * day, type: "command", action: "git diff", context: { project: "ThunderDuck" } },
    { timestamp: now - 5 * day, type: "command", action: "git log", context: { project: "ThunderDuck" } },
    { timestamp: now - 4 * day, type: "command", action: "cmake", context: { project: "ThunderDuck" } },
    { timestamp: now - 4 * day, type: "command", action: "make", context: { project: "ThunderDuck" } },
    { timestamp: now - 4 * day, type: "command", action: "ctest", context: { project: "ThunderDuck" } },
    { timestamp: now - 3 * day, type: "command", action: "npm test", context: { project: "Solar" } },
    { timestamp: now - 3 * day, type: "command", action: "npx tsx", context: { project: "Solar" } },

    // ========== Agent 密集交互 ==========
    { timestamp: now - 2 * day, type: "agent_interaction", action: "implement hash join", context: { agent: "coder", success: true, tokens: 8000 } },
    { timestamp: now - 2 * day, type: "agent_interaction", action: "implement hash join", context: { agent: "coder", success: true, tokens: 6000 } },
    { timestamp: now - 2 * day, type: "agent_interaction", action: "write test cases", context: { agent: "tester", success: true, tokens: 2000 } },
    { timestamp: now - 2 * day, type: "agent_interaction", action: "review code", context: { agent: "reviewer", success: true, tokens: 1500 } },
    { timestamp: now - 1 * day, type: "agent_interaction", action: "document API", context: { agent: "docs", success: true, tokens: 1200 } },
    { timestamp: now - 1 * day, type: "agent_interaction", action: "build project", context: { agent: "ops", success: true, tokens: 800 } },
    { timestamp: now - 1 * day, type: "agent_interaction", action: "security check", context: { agent: "guard", success: true, tokens: 600 } },

    // ========== 办公模式 ==========
    { timestamp: now - 3 * day, type: "mode_switch", action: "office", context: {} },
    { timestamp: now - 3 * day, type: "command", action: "check email", context: {} },
    { timestamp: now - 3 * day, type: "command", action: "list reminders", context: {} },

    // ========== 最近活动 (今天) ==========
    { timestamp: now - 4 * hour, type: "mode_switch", action: "dev", context: { project: "Solar" } },
    { timestamp: now - 3 * hour, type: "agent_interaction", action: "design architecture", context: { agent: "architect", success: true, tokens: 4000 } },
    { timestamp: now - 2 * hour, type: "agent_interaction", action: "implement adaptive engine", context: { agent: "coder", success: true, tokens: 12000 } },
    { timestamp: now - 1 * hour, type: "agent_interaction", action: "implement shortcuts module", context: { agent: "coder", success: true, tokens: 8000 } },
    { timestamp: now - 30 * 60000, type: "tool_call", action: "Write", context: { success: true, duration: 40 } },
    { timestamp: now - 30 * 60000, type: "tool_call", action: "Write", context: { success: true, duration: 35 } },
    { timestamp: now - 30 * 60000, type: "tool_call", action: "Edit", context: { success: true, duration: 20 } },
    { timestamp: now - 20 * 60000, type: "tool_call", action: "Read", context: { success: true, duration: 30 } },
    { timestamp: now - 10 * 60000, type: "skill_use", action: "status", context: {} },

    // ========== 重复模式 (检测用) ==========
    { timestamp: now - 5 * day, type: "command", action: "Read", context: {} },
    { timestamp: now - 5 * day, type: "command", action: "Edit", context: {} },
    { timestamp: now - 5 * day, type: "command", action: "Bash", context: {} },
    { timestamp: now - 4 * day, type: "command", action: "Read", context: {} },
    { timestamp: now - 4 * day, type: "command", action: "Edit", context: {} },
    { timestamp: now - 4 * day, type: "command", action: "Bash", context: {} },
    { timestamp: now - 3 * day, type: "command", action: "Read", context: {} },
    { timestamp: now - 3 * day, type: "command", action: "Edit", context: {} },
    { timestamp: now - 3 * day, type: "command", action: "Bash", context: {} },
  ];

  return actions;
}

// ==================== 增强推荐器 ====================

class SolarAdaptiveRecommender extends AdaptiveRecommender {
  /**
   * 生成 Solar 特定的推荐
   */
  generateSolarInsights(actions: UserAction[]): {
    missingSkills: string[];
    missingAgents: string[];
    missingHooks: string[];
    missingMCPs: string[];
    missingFeatures: string[];
  } {
    const stats = this.analyzeStats(actions);

    return {
      missingSkills: this.detectMissingSkills(stats),
      missingAgents: this.detectMissingAgents(stats),
      missingHooks: this.detectMissingHooks(stats),
      missingMCPs: this.detectMissingMCPs(stats),
      missingFeatures: this.detectMissingFeatures(stats),
    };
  }

  private analyzeStats(actions: UserAction[]) {
    const skillUsage = new Map<string, number>();
    const agentUsage = new Map<string, number>();
    const toolUsage = new Map<string, number>();
    const modeUsage = new Map<string, number>();
    const commandPatterns: string[] = [];
    const projectUsage = new Map<string, number>();
    let errorCount = 0;
    let totalTokens = 0;

    for (const action of actions) {
      if (action.type === "skill_use") {
        skillUsage.set(action.action, (skillUsage.get(action.action) ?? 0) + 1);
      }
      if (action.context.agent) {
        agentUsage.set(action.context.agent, (agentUsage.get(action.context.agent) ?? 0) + 1);
      }
      if (action.type === "tool_call") {
        toolUsage.set(action.action, (toolUsage.get(action.action) ?? 0) + 1);
        if (!action.context.success) errorCount++;
      }
      if (action.type === "mode_switch") {
        modeUsage.set(action.action, (modeUsage.get(action.action) ?? 0) + 1);
      }
      if (action.type === "command") {
        commandPatterns.push(action.action);
      }
      if (action.context.project) {
        projectUsage.set(action.context.project, (projectUsage.get(action.context.project) ?? 0) + 1);
      }
      if (action.context.tokens) {
        totalTokens += action.context.tokens;
      }
    }

    return {
      skillUsage,
      agentUsage,
      toolUsage,
      modeUsage,
      commandPatterns,
      projectUsage,
      errorCount,
      totalTokens,
      totalActions: actions.length,
    };
  }

  private detectMissingSkills(stats: ReturnType<typeof this.analyzeStats>): string[] {
    const missing: string[] = [];
    const existingSkills = Array.from(stats.skillUsage.keys());

    // 检测缺失的 skill
    const potentialSkills = [
      { name: "pr", condition: existingSkills.includes("commit"), reason: "频繁使用 /commit，但未使用 /pr" },
      { name: "docs", condition: stats.agentUsage.has("coder") && !existingSkills.includes("docs"), reason: "写了很多代码，但很少生成文档" },
      { name: "refactor", condition: (stats.toolUsage.get("Edit") ?? 0) > 10, reason: "频繁编辑文件，可能需要重构技能" },
      { name: "debug", condition: stats.errorCount > 5, reason: "有多次操作失败，需要调试技能" },
      { name: "profile", condition: existingSkills.includes("benchmark"), reason: "运行基准测试，但缺少性能分析技能" },
      { name: "deploy", condition: stats.agentUsage.has("ops"), reason: "使用 Ops agent，但缺少部署技能" },
      { name: "security-scan", condition: stats.agentUsage.has("guard"), reason: "使用 Guard agent，但缺少安全扫描技能" },
      { name: "changelog", condition: existingSkills.includes("commit"), reason: "频繁提交，需要自动生成 changelog" },
      { name: "release", condition: existingSkills.includes("commit") && existingSkills.includes("test"), reason: "完整的 CI 流程，需要发布技能" },
      { name: "migration", condition: stats.projectUsage.size > 1, reason: "多项目工作，可能需要迁移技能" },
    ];

    for (const skill of potentialSkills) {
      if (skill.condition && !existingSkills.includes(skill.name)) {
        missing.push(`/${skill.name} - ${skill.reason}`);
      }
    }

    return missing;
  }

  private detectMissingAgents(stats: ReturnType<typeof this.analyzeStats>): string[] {
    const missing: string[] = [];
    const existingAgents = Array.from(stats.agentUsage.keys());

    const potentialAgents = [
      {
        id: "debugger",
        condition: stats.errorCount > 3,
        reason: "频繁遇到错误，需要专门的调试 Agent",
        capabilities: ["错误分析", "堆栈追踪", "自动修复建议"]
      },
      {
        id: "profiler",
        condition: stats.skillUsage.has("benchmark"),
        reason: "运行基准测试，需要性能分析 Agent",
        capabilities: ["热点分析", "内存分析", "火焰图生成"]
      },
      {
        id: "migrator",
        condition: stats.projectUsage.size > 2,
        reason: "多项目工作，需要迁移专家 Agent",
        capabilities: ["API 兼容性检查", "依赖升级", "代码转换"]
      },
      {
        id: "translator",
        condition: stats.commandPatterns.some(c => c.includes("i18n") || c.includes("locale")),
        reason: "涉及国际化，需要翻译 Agent",
        capabilities: ["文本翻译", "本地化检查", "格式验证"]
      },
      {
        id: "scheduler",
        condition: stats.modeUsage.has("office"),
        reason: "使用办公模式，需要日程调度 Agent",
        capabilities: ["日程规划", "优先级排序", "时间估算"]
      },
      {
        id: "monitor",
        condition: stats.totalTokens > 50000,
        reason: "Token 消耗较高，需要监控 Agent",
        capabilities: ["资源监控", "异常检测", "成本优化"]
      },
    ];

    for (const agent of potentialAgents) {
      if (agent.condition && !existingAgents.includes(agent.id)) {
        missing.push(`@${agent.id} - ${agent.reason} [${agent.capabilities.join(", ")}]`);
      }
    }

    return missing;
  }

  private detectMissingHooks(stats: ReturnType<typeof this.analyzeStats>): string[] {
    const missing: string[] = [];

    // 基于使用模式推荐 hooks
    const potentialHooks = [
      {
        name: "pre-commit-lint",
        event: "PreToolCall",
        condition: stats.skillUsage.has("commit"),
        reason: "提交前自动运行 lint 检查",
      },
      {
        name: "auto-test",
        event: "PostToolCall",
        condition: (stats.toolUsage.get("Write") ?? 0) > 5,
        reason: "文件写入后自动运行相关测试",
      },
      {
        name: "error-notify",
        event: "OnError",
        condition: stats.errorCount > 3,
        reason: "错误时发送通知或自动重试",
      },
      {
        name: "session-summary",
        event: "SessionEnd",
        condition: stats.totalActions > 20,
        reason: "会话结束时生成工作总结",
      },
      {
        name: "token-alert",
        event: "TokenThreshold",
        condition: stats.totalTokens > 30000,
        reason: "Token 使用超过阈值时提醒",
      },
      {
        name: "auto-save",
        event: "Interval",
        condition: stats.totalActions > 10,
        reason: "定期自动保存会话状态",
      },
      {
        name: "project-context-load",
        event: "ModeSwitch",
        condition: stats.projectUsage.size > 1,
        reason: "切换项目时自动加载上下文",
      },
      {
        name: "benchmark-guard",
        event: "PreToolCall",
        condition: stats.skillUsage.has("benchmark"),
        reason: "防止性能回退的守护钩子",
      },
    ];

    for (const hook of potentialHooks) {
      if (hook.condition) {
        missing.push(`${hook.name} (${hook.event}) - ${hook.reason}`);
      }
    }

    return missing;
  }

  private detectMissingMCPs(stats: ReturnType<typeof this.analyzeStats>): string[] {
    const missing: string[] = [];

    const potentialMCPs = [
      {
        name: "docker",
        condition: stats.commandPatterns.some(c => c.includes("docker") || c.includes("container")),
        reason: "Docker 容器管理 MCP",
        capabilities: ["容器生命周期", "镜像管理", "日志查看"],
      },
      {
        name: "kubernetes",
        condition: stats.commandPatterns.some(c => c.includes("kubectl") || c.includes("k8s")),
        reason: "Kubernetes 集群管理 MCP",
        capabilities: ["Pod 管理", "部署", "服务发现"],
      },
      {
        name: "database",
        condition: stats.commandPatterns.some(c => c.includes("sql") || c.includes("db")),
        reason: "数据库操作 MCP",
        capabilities: ["查询执行", "模式管理", "数据导出"],
      },
      {
        name: "monitoring",
        condition: stats.agentUsage.has("ops"),
        reason: "监控系统 MCP (Prometheus/Grafana)",
        capabilities: ["指标查询", "告警管理", "仪表盘"],
      },
      {
        name: "ci-cd",
        condition: stats.skillUsage.has("commit") && stats.skillUsage.has("test"),
        reason: "CI/CD 管道 MCP (GitHub Actions/Jenkins)",
        capabilities: ["工作流触发", "状态查询", "日志查看"],
      },
      {
        name: "cloud",
        condition: stats.projectUsage.size > 1,
        reason: "云服务 MCP (AWS/GCP/Azure)",
        capabilities: ["资源管理", "配置", "成本查询"],
      },
      {
        name: "calendar",
        condition: stats.modeUsage.has("office"),
        reason: "日历 MCP (Google Calendar/Apple Calendar)",
        capabilities: ["事件管理", "提醒", "空闲时间查询"],
      },
      {
        name: "slack",
        condition: stats.modeUsage.has("office"),
        reason: "Slack 通信 MCP",
        capabilities: ["消息发送", "频道管理", "状态更新"],
      },
    ];

    for (const mcp of potentialMCPs) {
      if (mcp.condition) {
        missing.push(`${mcp.name} - ${mcp.reason} [${mcp.capabilities.join(", ")}]`);
      }
    }

    return missing;
  }

  private detectMissingFeatures(stats: ReturnType<typeof this.analyzeStats>): string[] {
    const missing: string[] = [];

    // 基于使用模式推荐新功能
    const potentialFeatures = [
      {
        name: "智能代码补全集成",
        condition: stats.agentUsage.has("coder") && (stats.agentUsage.get("coder") ?? 0) > 5,
        reason: "频繁使用 Coder agent，可集成 LSP 提供更智能的补全",
      },
      {
        name: "实时协作模式",
        condition: stats.projectUsage.size > 1,
        reason: "多项目工作，可能需要与团队实时协作",
      },
      {
        name: "语音交互",
        condition: stats.totalActions > 30,
        reason: "大量交互，语音输入可提高效率",
      },
      {
        name: "可视化流程编辑器",
        condition: stats.modeUsage.size > 1,
        reason: "多模式切换，可视化编辑器帮助设计工作流",
      },
      {
        name: "智能任务拆分",
        condition: stats.agentUsage.size > 3,
        reason: "使用多个 Agent，自动任务拆分提高效率",
      },
      {
        name: "上下文压缩",
        condition: stats.totalTokens > 50000,
        reason: "Token 消耗高，智能压缩上下文节省成本",
      },
      {
        name: "离线模式",
        condition: stats.toolUsage.has("Read") && stats.toolUsage.has("Write"),
        reason: "本地文件操作频繁，支持离线工作",
      },
      {
        name: "多模型切换",
        condition: stats.totalTokens > 30000,
        reason: "根据任务复杂度自动切换 Opus/Sonnet/Haiku",
      },
      {
        name: "项目模板系统",
        condition: stats.projectUsage.size > 1,
        reason: "多项目工作，模板系统加速新项目创建",
      },
      {
        name: "知识库集成",
        condition: stats.agentUsage.has("researcher"),
        reason: "使用 Researcher agent，集成知识库提高研究效率",
      },
    ];

    for (const feature of potentialFeatures) {
      if (feature.condition) {
        missing.push(`${feature.name} - ${feature.reason}`);
      }
    }

    return missing;
  }
}

// ==================== 主分析函数 ====================

async function analyzeSolarNeeds() {
  console.log("╔════════════════════════════════════════════════════════════════════════╗");
  console.log("║              🧠 Solar 自适应分析 - 功能需求分析报告                      ║");
  console.log("╚════════════════════════════════════════════════════════════════════════╝");
  console.log();

  // 1. 生成模拟行为数据
  console.log("📊 收集用户行为数据...");
  const actions = generateSimulatedBehavior();
  console.log(`   收集到 ${actions.length} 条行为记录`);
  console.log();

  // 2. 分析偏好
  console.log("🎯 分析用户偏好...");
  const analyzer = new PreferenceAnalyzer();
  const preferences = analyzer.analyzeActions(actions);

  console.log("   检测到的偏好:");
  for (const pref of preferences) {
    console.log(`   • ${pref.category}:${pref.key} = ${JSON.stringify(pref.value).slice(0, 50)} (置信度: ${(pref.confidence * 100).toFixed(0)}%)`);
  }
  console.log();

  // 3. 生成 Solar 特定推荐
  console.log("💡 生成推荐...");
  const recommender = new SolarAdaptiveRecommender(analyzer);
  const insights = recommender.generateSolarInsights(actions);

  // 4. 输出报告
  console.log();
  console.log("═══════════════════════════════════════════════════════════════════════════");
  console.log();

  console.log("🎯 缺失的 Skills (建议开发):");
  console.log("─────────────────────────────────────────────────────────────────────────");
  if (insights.missingSkills.length === 0) {
    console.log("   (无)");
  } else {
    for (const skill of insights.missingSkills) {
      console.log(`   • ${skill}`);
    }
  }
  console.log();

  console.log("🤖 缺失的 Agents (建议创建):");
  console.log("─────────────────────────────────────────────────────────────────────────");
  if (insights.missingAgents.length === 0) {
    console.log("   (无)");
  } else {
    for (const agent of insights.missingAgents) {
      console.log(`   • ${agent}`);
    }
  }
  console.log();

  console.log("🪝 缺失的 Hooks (建议添加):");
  console.log("─────────────────────────────────────────────────────────────────────────");
  if (insights.missingHooks.length === 0) {
    console.log("   (无)");
  } else {
    for (const hook of insights.missingHooks) {
      console.log(`   • ${hook}`);
    }
  }
  console.log();

  console.log("🔌 缺失的 MCPs (建议集成):");
  console.log("─────────────────────────────────────────────────────────────────────────");
  if (insights.missingMCPs.length === 0) {
    console.log("   (无)");
  } else {
    for (const mcp of insights.missingMCPs) {
      console.log(`   • ${mcp}`);
    }
  }
  console.log();

  console.log("✨ 缺失的功能 (建议开发):");
  console.log("─────────────────────────────────────────────────────────────────────────");
  if (insights.missingFeatures.length === 0) {
    console.log("   (无)");
  } else {
    for (const feature of insights.missingFeatures) {
      console.log(`   • ${feature}`);
    }
  }
  console.log();

  console.log("═══════════════════════════════════════════════════════════════════════════");
  console.log();
  console.log(`📅 分析时间: ${new Date().toLocaleString()}`);
  console.log(`📈 基于 ${actions.length} 条行为记录`);
  console.log();

  return insights;
}

// ==================== Entry ====================

analyzeSolarNeeds().catch(console.error);
