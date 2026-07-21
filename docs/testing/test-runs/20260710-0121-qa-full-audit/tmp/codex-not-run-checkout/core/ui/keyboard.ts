/**
 * Solar UI Keyboard Handler
 *
 * 终端快捷键支持
 */

import * as readline from "readline";

// ==================== Types ====================

export type KeyHandler = (key: string, ctrl: boolean, meta: boolean) => void;

export interface KeyBinding {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  description: string;
  handler: () => void;
}

// ==================== Key Codes ====================

// 特殊键码映射
export const KEY_CODES: Record<string, string> = {
  // Function keys
  "\x1bOP": "F1",
  "\x1bOQ": "F2",
  "\x1bOR": "F3",
  "\x1bOS": "F4",
  "\x1b[15~": "F5",
  "\x1b[17~": "F6",
  "\x1b[18~": "F7",
  "\x1b[19~": "F8",
  "\x1b[20~": "F9",
  "\x1b[21~": "F10",
  "\x1b[23~": "F11",
  "\x1b[24~": "F12",

  // Arrow keys
  "\x1b[A": "UP",
  "\x1b[B": "DOWN",
  "\x1b[C": "RIGHT",
  "\x1b[D": "LEFT",

  // Other special keys
  "\x1b[H": "HOME",
  "\x1b[F": "END",
  "\x1b[5~": "PAGEUP",
  "\x1b[6~": "PAGEDOWN",
  "\x1b[2~": "INSERT",
  "\x1b[3~": "DELETE",

  // Common
  "\r": "ENTER",
  "\n": "ENTER",
  "\t": "TAB",
  "\x1b": "ESC",
  "\x7f": "BACKSPACE",
  " ": "SPACE",
};

// ==================== Keyboard Handler ====================

export class KeyboardHandler {
  private bindings: Map<string, KeyBinding> = new Map();
  private enabled: boolean = false;
  private rl: readline.Interface | null = null;

  /**
   * 注册快捷键
   */
  bind(binding: KeyBinding): this {
    const keyId = this.getKeyId(binding.key, binding.ctrl, binding.meta);
    this.bindings.set(keyId, binding);
    return this;
  }

  /**
   * 批量注册快捷键
   */
  bindAll(bindings: KeyBinding[]): this {
    for (const binding of bindings) {
      this.bind(binding);
    }
    return this;
  }

  /**
   * 获取所有绑定
   */
  getBindings(): KeyBinding[] {
    return Array.from(this.bindings.values());
  }

  /**
   * 启动键盘监听
   */
  start(): void {
    if (this.enabled) return;

    // 设置 stdin 为 raw 模式
    if (process.stdin.isTTY) {
      process.stdin.setRawMode(true);
    }
    process.stdin.resume();
    process.stdin.setEncoding("utf8");

    process.stdin.on("data", (data: string) => {
      this.handleInput(data);
    });

    this.enabled = true;
  }

  /**
   * 停止键盘监听
   */
  stop(): void {
    if (!this.enabled) return;

    if (process.stdin.isTTY) {
      process.stdin.setRawMode(false);
    }
    process.stdin.pause();

    this.enabled = false;
  }

  /**
   * 处理输入
   */
  private handleInput(data: string): void {
    // 检查是否是特殊键
    const specialKey = KEY_CODES[data];

    // 检查 Ctrl 组合键 (Ctrl+A = \x01, Ctrl+Z = \x1a)
    const isCtrl = data.length === 1 && data.charCodeAt(0) < 27;
    const ctrlKey = isCtrl ? String.fromCharCode(data.charCodeAt(0) + 96) : null;

    // 尝试匹配绑定
    let keyId: string;

    if (specialKey) {
      keyId = this.getKeyId(specialKey, false, false);
    } else if (ctrlKey) {
      keyId = this.getKeyId(ctrlKey, true, false);
    } else {
      // 保留原始大小写，以区分 'l' 和 'L' (Shift+L)
      keyId = this.getKeyId(data, false, false);
    }

    const binding = this.bindings.get(keyId);
    if (binding) {
      binding.handler();
    }
  }

  /**
   * 生成键 ID
   * @param key 键名 (保留大小写以区分 Shift 组合)
   */
  private getKeyId(key: string, ctrl?: boolean, meta?: boolean): string {
    const parts: string[] = [];
    if (ctrl) parts.push("Ctrl");
    if (meta) parts.push("Meta");
    // 对于特殊键 (多字符) 使用大写，对于普通字符保留原始大小写
    parts.push(key.length > 1 ? key.toUpperCase() : key);
    return parts.join("+");
  }
}

// ==================== Help Panel ====================

/**
 * 生成帮助面板
 */
export function renderHelpPanel(bindings: KeyBinding[], width: number = 50): string[] {
  const lines: string[] = [];
  const innerWidth = width - 4;

  lines.push("┌" + "─".repeat(width - 2) + "┐");
  lines.push("│" + " KEYBOARD SHORTCUTS ".padStart((innerWidth + 20) / 2).padEnd(innerWidth) + "  │");
  lines.push("├" + "─".repeat(width - 2) + "┤");

  for (const binding of bindings) {
    const keyStr = [
      binding.ctrl ? "Ctrl+" : "",
      binding.meta ? "Meta+" : "",
      binding.key,
    ].join("");

    const line = `  ${keyStr.padEnd(12)} ${binding.description}`;
    lines.push("│" + line.padEnd(innerWidth) + "  │");
  }

  lines.push("├" + "─".repeat(width - 2) + "┤");
  lines.push("│" + "  Press any key to close".padEnd(innerWidth) + "  │");
  lines.push("└" + "─".repeat(width - 2) + "┘");

  return lines;
}

// ==================== Export ====================

export const keyboard = new KeyboardHandler();
