/**
 * Solar LLM Integration Test
 *
 * 测试 Solar 与 TVS LLM 模块的集成
 */

import {
  // 核心 API
  generate,
  generateStream,
  chat,
  // Solar 扩展
  solarGenerate,
  solarGenerateStream,
  solarChat,
  initSolarLLM,
  // 配置
  MODELS,
  RECOMMENDED_CONFIGS,
  SOLAR_SYSTEM_PROMPTS,
  usePreset,
  loadConfig,
} from "../core/llm/index";

console.log("🤖 Solar LLM Integration Test\n");
console.log("═".repeat(60));

// ==================== Test 1: 配置加载 ====================

console.log("\n📋 Test 1: 配置加载\n");

const config = initSolarLLM("hybrid");
console.log("Preset: hybrid");
console.log("Default model:", config.default.model);
console.log("Default provider:", config.default.provider);

if (config.tasks) {
  console.log("\nTask-specific models:");
  Object.entries(config.tasks).forEach(([task, model]) => {
    console.log(`  ${task}: ${model.model}`);
  });
}

// ==================== Test 2: 模型预设 ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 2: 模型预设\n");

console.log("Available presets:");
Object.entries(RECOMMENDED_CONFIGS).forEach(([name, cfg]) => {
  console.log(`  ${name}:`);
  console.log(`    default: ${cfg.default.model}`);
  if (cfg.fallback) {
    console.log(`    fallback: ${cfg.fallback.model}`);
  }
});

// ==================== Test 3: Agent 系统提示 ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 3: Agent 系统提示\n");

Object.entries(SOLAR_SYSTEM_PROMPTS).forEach(([agent, prompt]) => {
  console.log(`${agent}:`);
  console.log(`  ${prompt.split("\n")[0]}`);
});

// ==================== Test 4: API 类型检查 ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 4: API 类型检查\n");

console.log("✓ generate() - 普通生成");
console.log("✓ generateStream() - 流式生成");
console.log("✓ chat() - 多轮对话");
console.log("✓ solarGenerate() - Solar Agent 生成");
console.log("✓ solarGenerateStream() - Solar Agent 流式生成");
console.log("✓ solarChat() - Solar Agent 对话");

// ==================== Test 5: 实际调用 (需要 API Key) ====================

console.log("\n" + "─".repeat(60));
console.log("\n📋 Test 5: 实际调用测试\n");

const hasAnthropicKey = !!process.env.ANTHROPIC_API_KEY;
const hasOpenAIKey = !!process.env.OPENAI_API_KEY;

if (hasAnthropicKey || hasOpenAIKey) {
  console.log("检测到 API Key，执行实际调用测试...\n");

  try {
    // 使用 solarGenerate with agent
    const result = await solarGenerate("用一句话介绍自己", {
      agent: "coder",
      maxTokens: 100,
    });

    console.log("Response:", result.content);
    console.log("Model:", result.model);
    console.log("Provider:", result.provider);
    console.log("Latency:", result.latency, "ms");
    if (result.usage) {
      console.log("Tokens:", result.usage.totalTokens);
    }
  } catch (error) {
    console.log("调用失败:", error);
  }
} else {
  console.log("未检测到 API Key，跳过实际调用测试");
  console.log("设置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY 环境变量后可执行测试");
}

// ==================== Summary ====================

console.log("\n" + "═".repeat(60));
console.log("\n✅ Solar LLM Integration Test 完成!\n");
console.log("使用方式:");
console.log("  import { solarGenerate, initSolarLLM } from 'solar/core/llm';");
console.log("  ");
console.log("  initSolarLLM('hybrid');");
console.log("  const result = await solarGenerate('Hello', { agent: 'coder' });");
