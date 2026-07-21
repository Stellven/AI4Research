#!/usr/bin/env bun
/**
 * TVS Footer 检测 Hook
 *
 * 检查 Claude 输出是否包含正确的 TVS Footer
 * 用于 Claude Code 的 PostToolExecution 或 NotificationHandler hook
 */

const TVS_VERSION = "0.4.0";

const FOOTER_PATTERNS = {
  // 完整版 Footer (4行)
  full: [
    /^─{40,}$/,
    /^Powered by TVS v[\d.]+\s*·\s*Style:\s*\S+/,
    /^可选风格:/,
    /^切换风格:/
  ],
  // 简洁版 Footer (1行)
  compact: /Powered by TVS v[\d.]+\s*·\s*\S+\s*·\s*\/theme/
};

const AVAILABLE_STYLES = [
  "zenwhite.terminal",
  "monolith",
  "aurora",
  "cyberpunk",
  "liquid.dark",
  "swiss",
  "solar-dark",
  "solar-light"
];

interface CheckResult {
  valid: boolean;
  hasFooter: boolean;
  footerType: "full" | "compact" | "none";
  style?: string;
  suggestions: string[];
}

export function checkTvsFooter(output: string): CheckResult {
  const lines = output.trim().split("\n");
  const result: CheckResult = {
    valid: false,
    hasFooter: false,
    footerType: "none",
    suggestions: []
  };

  // 检查简洁版
  if (FOOTER_PATTERNS.compact.test(output)) {
    result.valid = true;
    result.hasFooter = true;
    result.footerType = "compact";
    const match = output.match(/Style:\s*(\S+)/);
    if (match) result.style = match[1];
    return result;
  }

  // 检查完整版 (从末尾向前检查4行)
  if (lines.length >= 4) {
    const lastFour = lines.slice(-4);
    const hasFullFooter =
      FOOTER_PATTERNS.full[0].test(lastFour[0]) &&
      FOOTER_PATTERNS.full[1].test(lastFour[1]) &&
      FOOTER_PATTERNS.full[2].test(lastFour[2]) &&
      FOOTER_PATTERNS.full[3].test(lastFour[3]);

    if (hasFullFooter) {
      result.valid = true;
      result.hasFooter = true;
      result.footerType = "full";
      const match = lastFour[1].match(/Style:\s*(\S+)/);
      if (match) result.style = match[1];
      return result;
    }
  }

  // 检查是否有 "Powered by TVS" 但格式不对
  if (/Powered by TVS/.test(output)) {
    result.hasFooter = true;
    result.suggestions.push("Footer 格式不正确，请使用完整版或简洁版格式");
  }

  // 检查是否是需要 TVS 渲染的输出
  const needsTvs =
    /┌.*┐|└.*┘|├.*┤|│/.test(output) || // Box drawing
    /Status|Progress|Task|Phase/.test(output); // Common TVS keywords

  if (needsTvs && !result.hasFooter) {
    result.suggestions.push("检测到 TVS 风格输出但缺少 Footer");
    result.suggestions.push("请添加:");
    result.suggestions.push("────────────────────────────────────────────────────────────────────");
    result.suggestions.push(`Powered by TVS v${TVS_VERSION} · Style: zenwhite.terminal`);
    result.suggestions.push("可选风格: monolith | aurora | cyberpunk | liquid.dark | swiss ...");
    result.suggestions.push("切换风格: /theme <style> | 查看所有: /theme list");
  }

  return result;
}

export function generateFooter(style: string = "zenwhite.terminal"): string {
  const otherStyles = AVAILABLE_STYLES
    .filter(s => s !== style)
    .slice(0, 5)
    .join(" | ");

  return `────────────────────────────────────────────────────────────────────
Powered by TVS v${TVS_VERSION} · Style: ${style}
可选风格: ${otherStyles} ...
切换风格: /theme <style> | 查看所有: /theme list`;
}

export function generateCompactFooter(style: string = "zenwhite.terminal"): string {
  return `Powered by TVS v${TVS_VERSION} · ${style} · /theme to switch`;
}

// CLI mode
if (import.meta.main) {
  const input = await Bun.stdin.text();
  const result = checkTvsFooter(input);

  if (!result.valid) {
    console.error("⚠️  TVS Footer 检查失败");
    result.suggestions.forEach(s => console.error(`   ${s}`));
    process.exit(1);
  } else {
    console.log(`✓ TVS Footer 有效 (${result.footerType}) - Style: ${result.style || "unknown"}`);
  }
}
