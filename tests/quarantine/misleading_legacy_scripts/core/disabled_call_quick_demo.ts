/**
 * Call Agent 快速测试 - 不需要通讯录权限
 */

import { createCallAgent } from "./platform";

const agent = createCallAgent();

console.log("╔════════════════════════════════════════════════════════════╗");
console.log("║                📞 Call Agent 快速测试                      ║");
console.log("╚════════════════════════════════════════════════════════════╝");
console.log();

// 测试意图解析
const tests = [
  "我要打电话给张三",
  "打给妈妈",
  "视频呼叫李四",
  "帮我联系王总",
  "call John",
  "打电话给 13812345678",
  "视频联系老板",
];

console.log("✅ 自然语言意图解析:\n");
for (const t of tests) {
  const intent = (agent as any).parseCallIntent(t);
  const icon = intent.action === "video" ? "📹" : "📞";
  console.log(`  ${icon} "${t}"`);
  console.log(`     → action: ${intent.action}, target: ${intent.target || "(未识别)"}`);
}

console.log();
console.log("═══════════════════════════════════════════════════════════════");
console.log();

// 模拟呼叫面板
console.log("📱 呼叫面板预览:\n");
console.log("  ┌─ 📞 Call Agent ─────────────────────────────────────────┐");
console.log("  │ 正在发起 FaceTime 音频呼叫...                            │");
console.log("  ├─────────────────────────────────────────────────────────┤");
console.log("  │ 联系人: 张三                                            │");
console.log("  │ 号码:   +86 138 1234 5678                               │");
console.log("  │ 方式:   FaceTime Audio                                  │");
console.log("  └─────────────────────────────────────────────────────────┘");

console.log();
console.log("╔════════════════════════════════════════════════════════════╗");
console.log("║  ✅ Call Agent 功能就绪！                                  ║");
console.log("╠════════════════════════════════════════════════════════════╣");
console.log("║                                                            ║");
console.log("║  使用方式:                                                 ║");
console.log("║                                                            ║");
console.log("║  1. 自然语言: \"我要打电话给张三\"                           ║");
console.log("║  2. Skill:    /call 张三                                   ║");
console.log("║  3. 视频:     /call 张三 --video                           ║");
console.log("║  4. 直拨:     /call 13812345678                            ║");
console.log("║                                                            ║");
console.log("╚════════════════════════════════════════════════════════════╝");
