/**
 * Braille Renderer Test - 8× 分辨率像素画布
 */

import {
  PixelBuffer,
  renderBrailleBar,
  renderBrailleSparkline,
  renderBrailleWaveform,
  render,
  LayoutDSL,
} from "tvs/v2";

console.log("🎨 Braille Renderer Test (×8 Resolution)\n");
console.log("═".repeat(72));

// ==================== Test 1: 基础 Braille Bar ====================

console.log("\n📋 Test 1: Braille Bar vs Block Bar\n");

console.log("Block Bar (普通):");
const blockChars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
const ratio = 0.72;
const width = 40;
const filled = Math.floor(ratio * width);
const remainder = (ratio * width) % 1;
let blockBar = blockChars[7].repeat(filled);
if (remainder > 0) blockBar += blockChars[Math.floor(remainder * 8)];
console.log(blockBar);

console.log("\nBraille Bar (高分辨率):");
console.log(renderBrailleBar(0.72, 40, 1));

console.log("\nBraille Bar (双高):");
console.log(renderBrailleBar(0.72, 40, 2));

// ==================== Test 2: 不同比例的 Braille Bar ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 2: Braille Bars at Different Ratios\n");

const ratios = [0.1, 0.25, 0.5, 0.75, 0.9, 1.0];
for (const r of ratios) {
  console.log(
    `${(r * 100).toString().padStart(3)}%: ${renderBrailleBar(r, 40, 1)}`,
  );
}

// ==================== Test 3: Sparkline ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 3: Braille Sparkline\n");

const data = [0.2, 0.3, 0.5, 0.4, 0.7, 0.9, 0.8, 0.6, 0.7, 0.8, 0.95, 0.7, 0.5];

console.log("Block Sparkline:");
console.log(
  data.map((v) => blockChars[Math.min(7, Math.floor(v * 8))]).join(""),
);

console.log("\nBraille Sparkline (高分辨率):");
console.log(renderBrailleSparkline(data, 40, 2));

// ==================== Test 4: Waveform ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 4: Braille Waveform\n");

// 生成正弦波数据
const sineData: number[] = [];
for (let i = 0; i < 30; i++) {
  sineData.push((Math.sin((i / 30) * Math.PI * 4) + 1) / 2);
}

console.log("Sine Wave:");
console.log(renderBrailleWaveform(sineData, 40, 2));

// ==================== Test 5: DSL 集成 ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 5: DSL Integration - render: 'braille'\n");

const dsl: LayoutDSL = {
  canvas: { width: 60 },
  style: "solar_default",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "System Metrics" },
      { type: "divider" },
      {
        type: "kv",
        items: [
          { key: "CPU", bar: 0.45, render: "block" },
          { key: "CPU (HD)", bar: 0.45, render: "braille" },
          { key: "Memory", bar: 0.72, render: "block" },
          { key: "Memory (HD)", bar: 0.72, render: "braille" },
        ],
      },
    ],
  },
};

console.log(render(dsl));

// ==================== Test 6: Sparkline Section ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 6: Sparkline Section\n");

const dsl2: LayoutDSL = {
  canvas: { width: 60 },
  style: "enterprise_minimal",
  layout: {
    type: "card",
    sections: [
      { type: "header", text: "Performance History" },
      { type: "divider" },
      { type: "sparkline", data: data, label: "Block", render: "block" },
      { type: "sparkline", data: data, label: "Braille", render: "braille" },
    ],
  },
};

console.log(render(dsl2));

// ==================== Test 7: 像素画布直接绘制 ====================

console.log("\n" + "─".repeat(72));
console.log("\n📋 Test 7: Direct PixelBuffer Drawing\n");

const pb = new PixelBuffer(60, 16);

// 画几条进度条
import { drawBar, drawBorder } from "tvs/v2";

// 边框
drawBorder(pb, 0, 0, 60, 16);

// 三条进度条
drawBar(pb, 2, 2, 56, 3, 0.85);
drawBar(pb, 2, 6, 56, 3, 0.55);
drawBar(pb, 2, 10, 56, 3, 0.25);

console.log(pb.render());

// ==================== Summary ====================

console.log("\n" + "═".repeat(72));
console.log("\n✅ All Braille Renderer tests completed!\n");
console.log("Braille 优势:");
console.log("  • 横向分辨率 ×2 (每字符 2 像素)");
console.log("  • 纵向分辨率 ×4 (每字符 4 像素)");
console.log("  • 总分辨率 ×8 - 接近像素级精度");
console.log("  • 无锯齿 - 平滑渐变效果");
console.log("\n使用方式:");
console.log("  DSL: { key: 'Load', bar: 0.72, render: 'braille' }");
console.log("  API: renderBrailleBar(0.72, 40)");
console.log("  底层: new PixelBuffer(w, h) → pb.render()");
