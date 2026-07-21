/**
 * Solar LLM Integration
 *
 * 基于 TVS termplane LLM 模块，提供 Solar 特定的大模型集成
 *
 * @example
 * ```typescript
 * import { generate, usePreset } from 'solar/core/llm';
 *
 * // 使用预设
 * usePreset('hybrid');
 *
 * // 生成代码
 * const result = await generate("优化这段代码", {
 *   task: "code-review",
 *   system: SOLAR_SYSTEM_PROMPT,
 * });
 * ```
 */

// ==================== Re-export TVS LLM ====================
// 直接从 LLM 子模块导入，避免加载其他 termplane 模块

// 配置 API
export {
  // Types
  type LLMProvider,
  type ModelConfig,
  type TaskType,
  type LLMConfig,
  // Presets
  MODELS,
  type ModelPreset,
  RECOMMENDED_CONFIGS,
  type ConfigPreset,
  // Environment
  ENV_KEYS,
  // Config Loader
  ConfigLoader,
  configLoader,
  loadConfig,
  getModel,
  usePreset,
  generateConfigFile,
  generateEnvTemplate,
} from "tvs/termplane/llm";

// 客户端 API
export {
  // Types
  type MessageRole,
  type Message,
  type GenerateOptions,
  type GenerateResult,
  type StreamCallback,
  // Client
  LLMClient,
  llmClient,
  // Functions
  generate,
  generateStream,
  chat,
} from "tvs/termplane/llm";

// Token 优化
export {
  // Types
  type StructuredIntent,
  type DashboardSpec,
  type WidgetPlacement,
  type WidgetSpec,
  type LayoutSpec,
  type StyleSpec,
  type ResponsiveRule,
  type LayoutPatch,
  // Templates
  WIDGET_TEMPLATES,
  LAYOUT_PRESETS,
  // Optimizer
  TokenOptimizer,
  tokenOptimizer,
  // Intent Builder
  IntentBuilder,
  intent,
  // Functions
  fromTemplate,
  fromIntent,
  preset,
} from "tvs/termplane/llm";

// ==================== Solar 特定扩展 ====================

import {
  generate as tvsGenerate,
  generateStream as tvsGenerateStream,
  chat as tvsChat,
  usePreset as tvsUsePreset,
  type GenerateOptions,
  type GenerateResult,
  type Message,
  type StreamCallback,
} from "tvs/termplane/llm";

/**
 * Solar Agent 系统提示
 */
export const SOLAR_SYSTEM_PROMPTS = {
  coder: `你是 Solar Coder Agent，一个专业的代码实现助手。
你的职责是：
- 编写高质量、可维护的代码
- 遵循项目编码规范
- 提供清晰的注释和文档
- 考虑性能和安全性`,

  reviewer: `你是 Solar Reviewer Agent，一个专业的代码审查助手。
你的职责是：
- 审查代码质量和规范
- 发现潜在的 bug 和安全问题
- 提供改进建议
- 确保代码可读性和可维护性`,

  researcher: `你是 Solar Researcher Agent，一个技术研究助手。
你的职责是：
- 研究技术方案的可行性
- 分析不同方案的优缺点
- 提供技术建议
- 收集相关资料和文档`,

  architect: `你是 Solar Architect Agent，一个软件架构设计助手。
你的职责是：
- 设计系统架构
- 评审设计方案
- 考虑可扩展性和可维护性
- 制定技术规范`,

  tester: `你是 Solar Tester Agent，一个测试验证助手。
你的职责是：
- 设计测试用例
- 执行测试并分析结果
- 发现和报告问题
- 验证修复效果`,
};

export type SolarAgent = keyof typeof SOLAR_SYSTEM_PROMPTS;

/**
 * Solar 任务类型映射
 */
export const SOLAR_TASK_MAPPING = {
  coder: "widget-generation",
  reviewer: "code-review",
  researcher: "general",
  architect: "layout-generation",
  tester: "general",
} as const;

/**
 * Solar Agent 生成选项
 */
export interface SolarGenerateOptions extends GenerateOptions {
  /** Solar Agent 类型 */
  agent?: SolarAgent;
  /** 是否使用 Agent 系统提示 */
  useAgentPrompt?: boolean;
}

/**
 * Solar 生成函数 - 带 Agent 支持
 */
export async function solarGenerate(
  prompt: string,
  options: SolarGenerateOptions = {},
): Promise<GenerateResult> {
  const { agent, useAgentPrompt = true, ...restOptions } = options;

  // 设置系统提示
  let system = options.system;
  if (agent && useAgentPrompt && !system) {
    system = SOLAR_SYSTEM_PROMPTS[agent];
  }

  // 设置任务类型
  let task = options.task;
  if (agent && !task) {
    task = SOLAR_TASK_MAPPING[agent] as any;
  }

  return tvsGenerate(prompt, {
    ...restOptions,
    system,
    task,
  });
}

/**
 * Solar 流式生成函数
 */
export async function solarGenerateStream(
  prompt: string,
  callback: StreamCallback,
  options: SolarGenerateOptions = {},
): Promise<GenerateResult> {
  const { agent, useAgentPrompt = true, ...restOptions } = options;

  let system = options.system;
  if (agent && useAgentPrompt && !system) {
    system = SOLAR_SYSTEM_PROMPTS[agent];
  }

  let task = options.task;
  if (agent && !task) {
    task = SOLAR_TASK_MAPPING[agent] as any;
  }

  return tvsGenerateStream(prompt, callback, {
    ...restOptions,
    system,
    task,
  });
}

/**
 * Solar 聊天函数
 */
export async function solarChat(
  messages: Message[],
  options: SolarGenerateOptions = {},
): Promise<GenerateResult> {
  const { agent, useAgentPrompt = true, ...restOptions } = options;

  // 如果指定了 agent 且消息中没有 system，添加 system 消息
  const hasSystem = messages.some((m) => m.role === "system");
  let finalMessages = messages;

  if (agent && useAgentPrompt && !hasSystem) {
    finalMessages = [
      { role: "system", content: SOLAR_SYSTEM_PROMPTS[agent] },
      ...messages,
    ];
  }

  let task = options.task;
  if (agent && !task) {
    task = SOLAR_TASK_MAPPING[agent] as any;
  }

  return tvsChat(finalMessages, {
    ...restOptions,
    task,
  });
}

/**
 * 初始化 Solar LLM 配置
 */
export function initSolarLLM(preset: "local-first" | "cost-effective" | "quality-first" | "hybrid" = "hybrid") {
  return tvsUsePreset(preset);
}
