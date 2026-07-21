/**
 * Solar UI Engine - 本地渲染引擎
 * "LLM 说什么，引擎画什么" - 零 Token 消耗
 */

import {
  existsSync,
  readFileSync,
  readdirSync,
  writeFileSync,
  mkdirSync,
} from "fs";
import { join, dirname } from "path";

// ==================== 类型定义 ====================

export type UIType =
  | "banner"
  | "box"
  | "status"
  | "progress"
  | "table"
  | "tree"
  | "figlet"
  | "cowsay"
  | "alert"
  | "list"
  | "card"
  | "divider"
  | "custom";

export interface UICommand {
  id: string;
  type: UIType;
  template?: string;
  data: Record<string, any>;
  style?: StyleOptions;
  timestamp: string;
  priority?: "low" | "normal" | "high";
}

export interface StyleOptions {
  color?: string;
  gradient?: string[];
  border?: "single" | "double" | "round" | "bold" | "classic";
  borderColor?: string;
  padding?: number;
  width?: number;
  align?: "left" | "center" | "right";
  font?: string;
  complete?: string;
  incomplete?: string;
  bullet?: string;
  numbered?: boolean;
  [key: string]: any;
}

export interface RenderResult {
  output: string;
  width: number;
  height: number;
}

export interface Theme {
  colors: {
    primary: string;
    secondary: string;
    success: string;
    warning: string;
    error: string;
    info: string;
  };
  borders: {
    default: string;
  };
  icons: Record<string, string>;
}

type Renderer = (data: any, style?: StyleOptions) => Promise<string> | string;

// ==================== 辅助函数 ====================

// ANSI 颜色代码
const COLORS: Record<string, string> = {
  black: "\x1b[30m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  magenta: "\x1b[35m",
  cyan: "\x1b[36m",
  white: "\x1b[37m",
  gray: "\x1b[90m",
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  dim: "\x1b[2m",
};

function colorize(text: string, color?: string): string {
  if (!color) return text;
  const code = COLORS[color];
  return code ? `${code}${text}${COLORS.reset}` : text;
}

function stripAnsi(str: string): string {
  return str.replace(/\x1B\[[0-9;]*m/g, "");
}

function repeat(char: string, count: number): string {
  return char.repeat(Math.max(0, count));
}

function padEnd(str: string, length: number, char: string = " "): string {
  const strLen = stripAnsi(str).length;
  return str + repeat(char, length - strLen);
}

function padStart(str: string, length: number, char: string = " "): string {
  const strLen = stripAnsi(str).length;
  return repeat(char, length - strLen) + str;
}

function center(str: string, width: number, char: string = " "): string {
  const strLen = stripAnsi(str).length;
  const padding = Math.max(0, width - strLen);
  const left = Math.floor(padding / 2);
  const right = padding - left;
  return repeat(char, left) + str + repeat(char, right);
}

// ==================== 边框字符集 ====================

const BORDERS = {
  single: { tl: "┌", tr: "┐", bl: "└", br: "┘", h: "─", v: "│" },
  double: { tl: "╔", tr: "╗", bl: "╚", br: "╝", h: "═", v: "║" },
  round: { tl: "╭", tr: "╮", bl: "╰", br: "╯", h: "─", v: "│" },
  bold: { tl: "┏", tr: "┓", bl: "┗", br: "┛", h: "━", v: "┃" },
  classic: { tl: "+", tr: "+", bl: "+", br: "+", h: "-", v: "|" },
};

// ==================== UI Engine 类 ====================

export class UIEngine {
  private renderers: Map<string, Renderer> = new Map();
  private templates: Map<string, string> = new Map();
  private theme: Theme;
  private baseDir: string;

  constructor(baseDir?: string) {
    this.baseDir = baseDir || `${process.env.HOME}/.solar/ui`;
    this.theme = this.loadTheme();
    this.loadTemplates();
    this.registerBuiltinRenderers();
  }

  // ==================== 主题加载 ====================

  private loadTheme(): Theme {
    const themePath = join(this.baseDir, "themes", "default.json");
    if (existsSync(themePath)) {
      return JSON.parse(readFileSync(themePath, "utf-8"));
    }
    return {
      colors: {
        primary: "yellow",
        secondary: "cyan",
        success: "green",
        warning: "yellow",
        error: "red",
        info: "blue",
      },
      borders: { default: "round" },
      icons: {
        ok: "🟢",
        warning: "🟡",
        error: "🔴",
        info: "🔵",
        success: "✅",
      },
    };
  }

  // ==================== 模板加载 ====================

  private loadTemplates() {
    const templatesDir = join(this.baseDir, "templates");
    if (!existsSync(templatesDir)) return;

    const loadDir = (dir: string, prefix: string = "") => {
      if (!existsSync(dir)) return;
      const files = readdirSync(dir, { withFileTypes: true });
      for (const file of files) {
        if (file.isDirectory()) {
          loadDir(join(dir, file.name), `${prefix}${file.name}/`);
        } else if (file.name.endsWith(".tpl")) {
          const name = prefix + file.name.replace(".tpl", "");
          this.templates.set(name, readFileSync(join(dir, file.name), "utf-8"));
        }
      }
    };
    loadDir(templatesDir);
  }

  // ==================== 内置渲染器 ====================

  private registerBuiltinRenderers() {
    // Banner - 大横幅
    this.register("banner", (data, style) => {
      return this.renderBanner(data, style);
    });

    // Box - 信息盒子
    this.register("box", (data, style) => {
      return this.renderBox(data, style);
    });

    // Status - 状态行
    this.register("status", (data) => {
      return this.renderStatus(data);
    });

    // Progress - 进度条
    this.register("progress", (data, style) => {
      return this.renderProgress(data, style);
    });

    // Table - 表格
    this.register("table", (data, style) => {
      return this.renderTable(data, style);
    });

    // Tree - 树形结构
    this.register("tree", (data, style) => {
      return this.renderTree(data.root || data, "", true, true);
    });

    // FIGlet - 大字
    this.register("figlet", async (data, style) => {
      return this.renderFiglet(data.text, style?.font);
    });

    // Cowsay - 对话气泡
    this.register("cowsay", (data, style) => {
      return this.renderCowsay(data.text, style?.cow);
    });

    // Alert - 警告框
    this.register("alert", (data, style) => {
      return this.renderAlert(data, style);
    });

    // List - 列表
    this.register("list", (data, style) => {
      return this.renderList(data.items, style);
    });

    // Divider - 分隔线
    this.register("divider", (data, style) => {
      return this.renderDivider(data.label, style);
    });

    // Card - 卡片 (KV pairs / stats)
    this.register("card", (data, style) => {
      return this.renderCard(data, style);
    });

    // Custom - 自定义模板
    this.register("custom", (data) => {
      const template = this.templates.get(data.template);
      if (!template) return `[Template not found: ${data.template}]`;
      return this.renderTemplate(template, data);
    });
  }

  // ==================== 核心渲染方法 ====================

  async render(command: UICommand): Promise<RenderResult> {
    const renderer = this.renderers.get(command.type);
    if (!renderer) {
      const output = `[Unknown UI type: ${command.type}]`;
      return { output, width: output.length, height: 1 };
    }

    const output = await renderer(command.data, command.style);
    const lines = output.split("\n");
    const height = lines.length;
    const width = Math.max(...lines.map((l) => stripAnsi(l).length));

    return { output, width, height };
  }

  register(type: string, renderer: Renderer) {
    this.renderers.set(type, renderer);
  }

  // ==================== 渲染实现 ====================

  private renderBanner(data: any, style?: StyleOptions): string {
    const width = style?.width || 60;
    const b = BORDERS[style?.border || "round"];

    const lines: string[] = [];

    // 顶部边框
    lines.push(b.tl + repeat(b.h, width - 2) + b.tr);

    // 空行
    lines.push(b.v + repeat(" ", width - 2) + b.v);

    // 标题
    const title = data.title || "☀️  S O L A R";
    const version = data.version ? `v${data.version}` : "";
    const titleLine = `${title}  ${version}`;
    lines.push(b.v + center(titleLine, width - 2) + b.v);

    // 副标题
    if (data.subtitle) {
      lines.push(b.v + center(data.subtitle, width - 2) + b.v);
    }

    // 空行
    lines.push(b.v + repeat(" ", width - 2) + b.v);

    // 底部边框
    lines.push(b.bl + repeat(b.h, width - 2) + b.br);

    return lines.join("\n");
  }

  private renderBox(data: any, style?: StyleOptions): string {
    const width = style?.width || 50;
    const padding = style?.padding || 1;
    const b = BORDERS[style?.border || "round"];

    // 准备内容行
    let contentLines: string[] = [];

    // 标题
    if (data.title) {
      contentLines.push(data.title);
      contentLines.push("");
    }

    // Agent 宣告格式
    if (data.agent) {
      const emoji = data.emoji || "🤖";
      contentLines = [`${emoji} ${data.agent}`];
      if (data.task) {
        contentLines.push("");
        contentLines.push(`Task: ${data.task}`);
      }
      if (data.plan && Array.isArray(data.plan)) {
        contentLines.push("");
        contentLines.push("Plan:");
        data.plan.forEach((step: string, i: number) => {
          contentLines.push(`  ${i + 1}. ${step}`);
        });
      }
    }

    // 通用内容
    if (data.content) {
      if (typeof data.content === "string") {
        contentLines.push(...data.content.split("\n"));
      } else if (Array.isArray(data.content)) {
        contentLines.push(...data.content);
      }
    }

    // 计算内容宽度
    const innerWidth = width - 2 - padding * 2;
    const lines: string[] = [];

    // 顶部边框 (带标题)
    if (data.header) {
      const headerText = ` ${data.header} `;
      const leftPad = 2;
      const rightPad = width - 2 - leftPad - headerText.length;
      lines.push(
        b.tl + repeat(b.h, leftPad) + headerText + repeat(b.h, rightPad) + b.tr,
      );
    } else {
      lines.push(b.tl + repeat(b.h, width - 2) + b.tr);
    }

    // 上 padding
    for (let i = 0; i < padding; i++) {
      lines.push(b.v + repeat(" ", width - 2) + b.v);
    }

    // 内容
    for (const line of contentLines) {
      const paddedLine =
        repeat(" ", padding) + padEnd(line, innerWidth) + repeat(" ", padding);
      lines.push(b.v + paddedLine + b.v);
    }

    // 下 padding
    for (let i = 0; i < padding; i++) {
      lines.push(b.v + repeat(" ", width - 2) + b.v);
    }

    // 底部边框
    lines.push(b.bl + repeat(b.h, width - 2) + b.br);

    return lines.join("\n");
  }

  private renderStatus(data: any): string {
    const { phase, agent, tokens, rate, status } = data;
    const statusIcon = this.theme.icons[status] || "⚪";
    const bar = this.miniProgressBar(rate || 0, 10);

    return `[Solar] ${phase || "P3"} | ${agent || "Coder"} | ${tokens || "+0"} | Rate ${bar} ${rate || 0}% ${statusIcon}`;
  }

  private renderProgress(data: any, style?: StyleOptions): string {
    const { label, value, max, current, total } = data;
    const actualValue = value ?? current ?? 0;
    const actualMax = max ?? total ?? 100;

    const width = style?.width || 30;
    const complete = style?.complete || "█";
    const incomplete = style?.incomplete || "░";

    const percent = Math.round((actualValue / actualMax) * 100);
    const filled = Math.round((width * actualValue) / actualMax);
    const empty = width - filled;

    const bar = repeat(complete, filled) + repeat(incomplete, empty);
    const labelPart = label ? `${label}: ` : "";

    return `${labelPart}${bar} ${percent}%`;
  }

  private renderTable(data: any, style?: StyleOptions): string {
    const { headers, rows } = data;
    if (!headers || !rows) return "[Invalid table data]";

    // 计算列宽
    const colWidths: number[] = headers.map((h: string, i: number) => {
      const maxRowWidth = Math.max(
        ...rows.map((r: any[]) => String(r[i] || "").length),
      );
      return Math.max(h.length, maxRowWidth) + 2;
    });

    const b = BORDERS[style?.border || "single"];
    const lines: string[] = [];

    // 顶部
    lines.push(b.tl + colWidths.map((w) => repeat(b.h, w)).join(b.h) + b.tr);

    // 表头
    const headerLine = headers
      .map((h: string, i: number) => center(h, colWidths[i]))
      .join(b.v);
    lines.push(b.v + headerLine + b.v);

    // 分隔线
    lines.push("├" + colWidths.map((w) => repeat(b.h, w)).join("┼") + "┤");

    // 数据行
    for (const row of rows) {
      const rowLine = row
        .map(
          (cell: any, i: number) =>
            " " + padEnd(String(cell || ""), colWidths[i] - 1),
        )
        .join(b.v);
      lines.push(b.v + rowLine + b.v);
    }

    // 底部
    lines.push(b.bl + colWidths.map((w) => repeat(b.h, w)).join(b.h) + b.br);

    return lines.join("\n");
  }

  private renderTree(
    node: any,
    prefix: string,
    isLast: boolean,
    isRoot: boolean = false,
  ): string {
    if (!node) return "";

    const connector = isRoot ? "" : isLast ? "└── " : "├── ";
    const extension = isRoot ? "" : isLast ? "    " : "│   ";
    const name =
      typeof node === "string" ? node : node.name || node.label || "?";

    const lines: string[] = [];
    if (!isRoot) {
      lines.push(prefix + connector + name);
    } else {
      lines.push(name);
    }

    const children = node.children || node.items;
    if (children && Array.isArray(children)) {
      children.forEach((child: any, index: number) => {
        const childIsLast = index === children.length - 1;
        const childPrefix = isRoot ? "" : prefix + extension;
        const childResult = this.renderTree(child, childPrefix, childIsLast);
        lines.push(childResult);
      });
    }

    return lines.join("\n");
  }

  private async renderFiglet(text: string, font?: string): Promise<string> {
    // 简化版 FIGlet - 使用预定义字体
    // 实际项目中应该使用 figlet 库
    const SIMPLE_FONT: Record<string, string[]> = {
      S: ["███╗", "█══╝", "███╗", "╚══█║", "███║"],
      O: ["╔═══╗", "║   ║", "║   ║", "║   ║", "╚═══╝"],
      L: ["█╗   ", "█║   ", "█║   ", "█║   ", "████╗"],
      A: [" ██╗ ", "█══█╗", "████║", "█  █║", "█  █║"],
      R: ["███╗ ", "█  █╗", "███╔╝", "█ █╗ ", "█  █╗"],
    };

    const chars = text.toUpperCase().split("");
    const height = 5;
    const lines: string[] = Array(height).fill("");

    for (const char of chars) {
      const charLines = SIMPLE_FONT[char] || Array(height).fill("?");
      for (let i = 0; i < height; i++) {
        lines[i] += (charLines[i] || "     ") + " ";
      }
    }

    return lines.join("\n");
  }

  private renderCowsay(text: string, cow?: string): string {
    // 计算气泡宽度
    const maxWidth = 40;
    const words = text.split(" ");
    const lines: string[] = [];
    let currentLine = "";

    for (const word of words) {
      if ((currentLine + " " + word).length > maxWidth) {
        lines.push(currentLine.trim());
        currentLine = word;
      } else {
        currentLine += " " + word;
      }
    }
    if (currentLine.trim()) lines.push(currentLine.trim());

    const bubbleWidth = Math.max(...lines.map((l) => l.length)) + 2;

    // 构建气泡
    const result: string[] = [];
    result.push(" " + repeat("_", bubbleWidth));

    if (lines.length === 1) {
      result.push(`< ${padEnd(lines[0], bubbleWidth - 2)} >`);
    } else {
      lines.forEach((line, i) => {
        const left = i === 0 ? "/" : i === lines.length - 1 ? "\\" : "|";
        const right = i === 0 ? "\\" : i === lines.length - 1 ? "/" : "|";
        result.push(`${left} ${padEnd(line, bubbleWidth - 2)} ${right}`);
      });
    }

    result.push(" " + repeat("-", bubbleWidth));

    // 牛
    const cowArt = cow === "solar" ? SOLAR_COW : DEFAULT_COW;
    result.push(...cowArt);

    return result.join("\n");
  }

  private renderAlert(data: any, style?: StyleOptions): string {
    const icons: Record<string, string> = {
      info: "ℹ️",
      warning: "⚠️",
      error: "❌",
      success: "✅",
    };

    const type = data.type || "info";
    const icon = icons[type] || "ℹ️";
    const message = data.message || "";

    return this.renderBox(
      {
        header: `${icon} ${type.charAt(0).toUpperCase() + type.slice(1)}`,
        content: message,
      },
      { ...style, width: style?.width || 50 },
    );
  }

  private renderList(items: string[], style?: StyleOptions): string {
    const bullet = style?.bullet || "•";
    const indent = style?.indent || 2;
    const numbered = style?.numbered || false;

    return items
      .map((item, i) => {
        const prefix = numbered ? `${i + 1}.` : bullet;
        return repeat(" ", indent) + prefix + " " + item;
      })
      .join("\n");
  }

  private renderDivider(label?: string, style?: StyleOptions): string {
    const char = style?.char || "─";
    const width = style?.width || 60;

    if (label) {
      const padding = Math.floor((width - label.length - 2) / 2);
      return (
        repeat(char, padding) +
        " " +
        label +
        " " +
        repeat(char, width - padding - label.length - 2)
      );
    }

    return repeat(char, width);
  }

  private renderCard(data: any, style?: StyleOptions): string {
    const width = style?.width || 30;
    const b = BORDERS[style?.border || "round"];

    // 构建卡片内容
    const items: Array<{ key: string; value: string }> = data.items || [];
    if (data.title && data.value !== undefined) {
      items.unshift({ key: data.title, value: String(data.value) });
    }

    // 计算 key 列宽度
    const keyWidth = Math.max(...items.map((i) => i.key.length)) + 1;
    const valueWidth = width - 4 - keyWidth - 3; // 边框 + padding + ": "

    const lines: string[] = [];

    // 顶部边框 (带标题)
    if (data.header) {
      const headerText = ` ${data.header} `;
      const leftPad = 2;
      const rightPad = width - 2 - leftPad - headerText.length;
      lines.push(
        b.tl + repeat(b.h, leftPad) + headerText + repeat(b.h, rightPad) + b.tr,
      );
    } else {
      lines.push(b.tl + repeat(b.h, width - 2) + b.tr);
    }

    // 内容行
    for (const item of items) {
      const keyPart = padEnd(item.key, keyWidth);
      const valPart = padEnd(String(item.value), valueWidth);
      lines.push(`${b.v} ${keyPart}: ${valPart} ${b.v}`);
    }

    // 底部边框
    lines.push(b.bl + repeat(b.h, width - 2) + b.br);

    return lines.join("\n");
  }

  // ==================== 辅助方法 ====================

  private miniProgressBar(percent: number, width: number): string {
    const filled = Math.round((width * percent) / 100);
    return "█".repeat(filled) + "░".repeat(width - filled);
  }

  private renderTemplate(template: string, data: any): string {
    // 简单的模板替换
    return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
      return data[key] !== undefined ? String(data[key]) : "";
    });
  }
}

// ==================== Cowsay 模板 ====================

const DEFAULT_COW = [
  "        \\   ^__^",
  "         \\  (oo)\\_______",
  "            (__)\\       )\\/\\",
  "                ||----w |",
  "                ||     ||",
];

const SOLAR_COW = [
  "        \\   ^__^",
  "         \\  (oo)\\_______",
  "            (__)\\       )\\/\\",
  "             ☀️ ||----w |",
  "                ||     ||",
];

// ==================== 便捷接口 ====================

let _engine: UIEngine | null = null;

export function getUIEngine(): UIEngine {
  if (!_engine) {
    _engine = new UIEngine();
  }
  return _engine;
}

/**
 * 将 UI 指令写入队列
 * LLM 调用此方法，Daemon 监控并渲染
 */
export function queueUI(command: Partial<UICommand>): string {
  const id = command.id || crypto.randomUUID();
  const fullCommand: UICommand = {
    id,
    type: command.type || "box",
    data: command.data || {},
    style: command.style,
    timestamp: new Date().toISOString(),
    priority: command.priority || "normal",
  };

  const queueDir = `${process.env.HOME}/.solar/ui/queue`;
  if (!existsSync(queueDir)) {
    mkdirSync(queueDir, { recursive: true });
  }

  const filepath = join(queueDir, `${id}.json`);
  writeFileSync(filepath, JSON.stringify(fullCommand, null, 2));

  return id;
}

/**
 * LLM 友好的便捷方法
 */
export const ui = {
  banner: (data: any, style?: StyleOptions) =>
    queueUI({ type: "banner", data, style }),

  box: (data: any, style?: StyleOptions) =>
    queueUI({ type: "box", data, style }),

  status: (data: any) => queueUI({ type: "status", data }),

  progress: (
    label: string,
    value: number,
    max: number = 100,
    style?: StyleOptions,
  ) => queueUI({ type: "progress", data: { label, value, max }, style }),

  alert: (type: "info" | "warning" | "error" | "success", message: string) =>
    queueUI({ type: "alert", data: { type, message } }),

  figlet: (text: string, font?: string) =>
    queueUI({ type: "figlet", data: { text }, style: { font } }),

  cowsay: (text: string, cow?: string) =>
    queueUI({ type: "cowsay", data: { text }, style: { cow } }),

  table: (headers: string[], rows: any[][], style?: StyleOptions) =>
    queueUI({ type: "table", data: { headers, rows }, style }),

  list: (items: string[], style?: StyleOptions) =>
    queueUI({ type: "list", data: { items }, style }),

  tree: (root: any) => queueUI({ type: "tree", data: { root } }),

  divider: (label?: string, style?: StyleOptions) =>
    queueUI({ type: "divider", data: { label }, style }),

  card: (
    header: string,
    items: Array<{ key: string; value: string }>,
    style?: StyleOptions,
  ) => queueUI({ type: "card", data: { header, items }, style }),

  // Agent 宣告便捷方法
  announce: (agent: string, emoji: string, task: string, plan: string[]) =>
    queueUI({
      type: "box",
      data: { agent, emoji, task, plan },
      style: { border: "round", width: 50 },
    }),
};
