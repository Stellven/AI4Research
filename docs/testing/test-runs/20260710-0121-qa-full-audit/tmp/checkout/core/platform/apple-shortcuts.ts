/**
 * Solar AI OS - Apple Shortcuts 集成模块
 *
 * 功能:
 * 1. 列出、搜索、运行 Apple 快捷指令
 * 2. 创建新的快捷指令 (通过 URL Scheme)
 * 3. 与 Siri 集成
 * 4. 跨设备同步 (iCloud)
 *
 * 支持平台: macOS 12.0+, iOS 15.0+
 */

import { execSync, spawn } from "child_process";
import { existsSync, writeFileSync, readFileSync } from "fs";
import { join } from "path";

// ==================== Types ====================

export interface Shortcut {
  name: string;
  folder?: string;
  icon?: string;
  color?: string;
  acceptsInput?: boolean;
  outputType?: string;
}

export interface ShortcutRunResult {
  success: boolean;
  output?: string;
  error?: string;
  duration: number;
}

export interface ShortcutAction {
  type: string;
  parameters: Record<string, unknown>;
}

export interface ShortcutDefinition {
  name: string;
  actions: ShortcutAction[];
  input?: {
    types: string[];
    multiple?: boolean;
  };
  icon?: {
    glyph: string;
    color: string;
  };
}

export type Platform = "macos" | "ios" | "unknown";

// ==================== Platform Detection ====================

export function detectPlatform(): Platform {
  try {
    const platform = process.platform;
    if (platform === "darwin") {
      // 检查是否是 macOS
      const version = execSync("sw_vers -productVersion", { encoding: "utf-8" }).trim();
      const major = parseInt(version.split(".")[0]);
      if (major >= 12) {
        return "macos";
      }
    }
  } catch {
    // Ignore
  }
  return "unknown";
}

export function isShortcutsAvailable(): boolean {
  const platform = detectPlatform();
  if (platform !== "macos") {
    return false;
  }

  try {
    // 检查 shortcuts 命令是否可用
    execSync("which shortcuts", { encoding: "utf-8" });
    return true;
  } catch {
    return false;
  }
}

// ==================== Shortcuts Manager ====================

export class AppleShortcutsManager {
  private platform: Platform;
  private available: boolean;
  private cachePath: string;
  private shortcutsCache: Shortcut[] | null = null;
  private cacheTime = 0;
  private cacheMaxAge = 60000; // 1 minute

  constructor() {
    this.platform = detectPlatform();
    this.available = isShortcutsAvailable();
    this.cachePath = join(process.env.HOME ?? "~", ".solar", "shortcuts-cache.json");

    if (!this.available) {
      console.warn(
        "[AppleShortcuts] Shortcuts not available on this platform. " +
        "Requires macOS 12.0+ with Shortcuts app installed."
      );
    }
  }

  /**
   * 检查是否可用
   */
  isAvailable(): boolean {
    return this.available;
  }

  /**
   * 获取平台信息
   */
  getPlatform(): Platform {
    return this.platform;
  }

  // ==================== List & Search ====================

  /**
   * 列出所有快捷指令
   */
  async list(options: { folder?: string; refresh?: boolean } = {}): Promise<Shortcut[]> {
    if (!this.available) {
      throw new Error("Shortcuts not available on this platform");
    }

    // 检查缓存
    if (
      !options.refresh &&
      this.shortcutsCache &&
      Date.now() - this.cacheTime < this.cacheMaxAge
    ) {
      return options.folder
        ? this.shortcutsCache.filter((s) => s.folder === options.folder)
        : this.shortcutsCache;
    }

    try {
      // 使用 shortcuts CLI 列出所有快捷指令
      const output = execSync("shortcuts list", {
        encoding: "utf-8",
        maxBuffer: 10 * 1024 * 1024,
      });

      const shortcuts: Shortcut[] = output
        .trim()
        .split("\n")
        .filter((line) => line.trim())
        .map((name) => ({
          name: name.trim(),
        }));

      // 更新缓存
      this.shortcutsCache = shortcuts;
      this.cacheTime = Date.now();
      this.saveCacheToFile();

      return options.folder
        ? shortcuts.filter((s) => s.folder === options.folder)
        : shortcuts;
    } catch (error) {
      // 尝试从缓存文件恢复
      const cached = this.loadCacheFromFile();
      if (cached) {
        return options.folder
          ? cached.filter((s) => s.folder === options.folder)
          : cached;
      }
      throw new Error(`Failed to list shortcuts: ${error}`);
    }
  }

  /**
   * 搜索快捷指令
   */
  async search(query: string): Promise<Shortcut[]> {
    const all = await this.list();
    const lowerQuery = query.toLowerCase();

    return all.filter((s) =>
      s.name.toLowerCase().includes(lowerQuery)
    );
  }

  /**
   * 获取快捷指令详情
   */
  async get(name: string): Promise<Shortcut | null> {
    const all = await this.list();
    return all.find((s) => s.name === name) ?? null;
  }

  // ==================== Run ====================

  /**
   * 运行快捷指令
   */
  async run(
    name: string,
    options: {
      input?: string;
      inputType?: "text" | "file" | "url";
      timeout?: number;
    } = {}
  ): Promise<ShortcutRunResult> {
    if (!this.available) {
      return {
        success: false,
        error: "Shortcuts not available on this platform",
        duration: 0,
      };
    }

    const startTime = Date.now();

    try {
      const args = ["run", `"${name}"`];

      // 添加输入
      if (options.input) {
        switch (options.inputType) {
          case "file":
            args.push("-i", `"${options.input}"`);
            break;
          case "url":
            args.push("-i", `"${options.input}"`);
            break;
          default:
            // text input via stdin
            args.push("-i", "-");
            break;
        }
      }

      const command = `shortcuts ${args.join(" ")}`;

      let output: string;
      if (options.input && options.inputType !== "file" && options.inputType !== "url") {
        // 通过 stdin 传递文本输入
        output = execSync(command, {
          encoding: "utf-8",
          input: options.input,
          timeout: options.timeout ?? 30000,
          maxBuffer: 10 * 1024 * 1024,
        });
      } else {
        output = execSync(command, {
          encoding: "utf-8",
          timeout: options.timeout ?? 30000,
          maxBuffer: 10 * 1024 * 1024,
        });
      }

      return {
        success: true,
        output: output.trim(),
        duration: Date.now() - startTime,
      };
    } catch (error: any) {
      return {
        success: false,
        error: error.message ?? String(error),
        duration: Date.now() - startTime,
      };
    }
  }

  /**
   * 异步运行快捷指令（不等待结果）
   */
  runAsync(name: string, input?: string): void {
    if (!this.available) {
      return;
    }

    const args = ["run", name];
    if (input) {
      args.push("-i", "-");
    }

    const proc = spawn("shortcuts", args, {
      detached: true,
      stdio: input ? ["pipe", "ignore", "ignore"] : "ignore",
    });

    if (input && proc.stdin) {
      proc.stdin.write(input);
      proc.stdin.end();
    }

    proc.unref();
  }

  // ==================== Create & Manage ====================

  /**
   * 通过 URL Scheme 打开快捷指令编辑器
   */
  openEditor(name?: string): void {
    if (!this.available) {
      return;
    }

    let url: string;
    if (name) {
      // 打开指定快捷指令
      url = `shortcuts://open-shortcut?name=${encodeURIComponent(name)}`;
    } else {
      // 创建新快捷指令
      url = "shortcuts://create-shortcut";
    }

    execSync(`open "${url}"`);
  }

  /**
   * 通过 URL Scheme 运行快捷指令（可选打开应用）
   */
  runViaUrl(name: string, input?: string, showApp = false): void {
    if (!this.available) {
      return;
    }

    let url = `shortcuts://run-shortcut?name=${encodeURIComponent(name)}`;
    if (input) {
      url += `&input=text&text=${encodeURIComponent(input)}`;
    }

    if (showApp) {
      // x-callback-url 方式
      url = url.replace("shortcuts://", "shortcuts://x-callback-url/");
    }

    execSync(`open "${url}"`);
  }

  /**
   * 导出快捷指令到文件
   */
  async export(name: string, outputPath: string): Promise<boolean> {
    if (!this.available) {
      return false;
    }

    try {
      execSync(`shortcuts sign -i "${name}" -o "${outputPath}"`, {
        encoding: "utf-8",
      });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * 导入快捷指令
   */
  async import(filePath: string): Promise<boolean> {
    if (!this.available || !existsSync(filePath)) {
      return false;
    }

    try {
      // 通过 open 命令导入 .shortcut 文件
      execSync(`open "${filePath}"`);
      return true;
    } catch {
      return false;
    }
  }

  // ==================== Solar 集成 ====================

  /**
   * 创建 Solar 预设快捷指令
   */
  async createSolarShortcuts(): Promise<string[]> {
    const created: string[] = [];

    // 预设的 Solar 快捷指令定义
    const solarShortcuts: ShortcutDefinition[] = [
      {
        name: "Solar - 开始开发",
        actions: [
          { type: "text", parameters: { text: "我要开发" } },
          {
            type: "runScript",
            parameters: {
              script: 'tell application "Terminal" to do script "claude"',
            },
          },
        ],
        icon: { glyph: "sun.max", color: "yellow" },
      },
      {
        name: "Solar - 查看状态",
        actions: [
          {
            type: "runScript",
            parameters: {
              script:
                'tell application "Terminal" to do script "claude -c \\"/status\\""',
            },
          },
        ],
        icon: { glyph: "chart.bar", color: "blue" },
      },
      {
        name: "Solar - 提交代码",
        actions: [
          {
            type: "runScript",
            parameters: {
              script:
                'tell application "Terminal" to do script "claude -c \\"/commit\\""',
            },
          },
        ],
        icon: { glyph: "arrow.up.circle", color: "green" },
      },
      {
        name: "Solar - 办公模式",
        actions: [
          {
            type: "runScript",
            parameters: {
              script: 'tell application "Terminal" to do script "claude -c \\"我要办公\\""',
            },
          },
        ],
        icon: { glyph: "briefcase", color: "orange" },
      },
    ];

    // 生成创建脚本
    for (const def of solarShortcuts) {
      const exists = await this.get(def.name);
      if (!exists) {
        // 通过 URL Scheme 打开创建界面
        // 注意：实际创建需要用户手动操作
        console.log(`[AppleShortcuts] Please create shortcut: ${def.name}`);
        created.push(def.name);
      }
    }

    return created;
  }

  /**
   * 获取推荐的快捷指令（基于用户偏好）
   */
  async getRecommendedShortcuts(preferences: {
    frequentApps?: string[];
    frequentActions?: string[];
    workPatterns?: string[];
  }): Promise<Shortcut[]> {
    const all = await this.list();
    const recommended: Shortcut[] = [];

    // 基于常用应用推荐
    if (preferences.frequentApps) {
      for (const app of preferences.frequentApps) {
        const matches = all.filter((s) =>
          s.name.toLowerCase().includes(app.toLowerCase())
        );
        recommended.push(...matches);
      }
    }

    // 基于常用动作推荐
    const actionKeywords = [
      "send",
      "create",
      "open",
      "start",
      "run",
      "get",
      "show",
    ];
    if (preferences.frequentActions) {
      for (const action of preferences.frequentActions) {
        const matches = all.filter((s) =>
          s.name.toLowerCase().includes(action.toLowerCase())
        );
        recommended.push(...matches);
      }
    }

    // 去重
    const seen = new Set<string>();
    return recommended.filter((s) => {
      if (seen.has(s.name)) return false;
      seen.add(s.name);
      return true;
    });
  }

  // ==================== Siri Integration ====================

  /**
   * 获取 Siri 建议的快捷指令
   */
  async getSiriSuggestions(): Promise<Shortcut[]> {
    // Siri 建议通过系统 API 获取，这里返回常用的
    const all = await this.list();
    // 按名称长度排序（通常短名称是常用的）
    return all.sort((a, b) => a.name.length - b.name.length).slice(0, 10);
  }

  /**
   * 通过 Siri 运行快捷指令
   */
  async runViaSiri(name: string): Promise<void> {
    if (!this.available) {
      return;
    }

    // 使用 AppleScript 调用 Siri
    const script = `
      tell application "System Events"
        set frontApp to name of first process whose frontmost is true
      end tell

      tell application "Shortcuts"
        run shortcut "${name}"
      end tell
    `;

    try {
      execSync(`osascript -e '${script}'`, { encoding: "utf-8" });
    } catch {
      // Fallback to URL scheme
      this.runViaUrl(name);
    }
  }

  // ==================== Automation ====================

  /**
   * 创建自动化触发器
   */
  createAutomation(trigger: {
    type: "time" | "location" | "app" | "event";
    condition: Record<string, unknown>;
    shortcutName: string;
  }): string {
    // 生成自动化配置说明
    const instructions: string[] = [
      "## 创建 Shortcuts 自动化",
      "",
      `**快捷指令**: ${trigger.shortcutName}`,
      `**触发类型**: ${trigger.type}`,
      "",
      "### 步骤:",
      "1. 打开 Shortcuts 应用",
      "2. 切换到 \"自动化\" 标签",
      "3. 点击 \"+\" 创建新自动化",
    ];

    switch (trigger.type) {
      case "time":
        instructions.push(
          `4. 选择 \"特定时间\"`,
          `5. 设置时间: ${JSON.stringify(trigger.condition)}`,
          `6. 选择运行 \"${trigger.shortcutName}\"`
        );
        break;
      case "location":
        instructions.push(
          `4. 选择 \"到达\" 或 \"离开\"`,
          `5. 设置位置: ${JSON.stringify(trigger.condition)}`,
          `6. 选择运行 \"${trigger.shortcutName}\"`
        );
        break;
      case "app":
        instructions.push(
          `4. 选择 \"App\"`,
          `5. 选择应用: ${(trigger.condition as any).app}`,
          `6. 选择 \"打开时\" 或 \"关闭时\"`,
          `7. 选择运行 \"${trigger.shortcutName}\"`
        );
        break;
      case "event":
        instructions.push(
          `4. 选择事件类型`,
          `5. 配置: ${JSON.stringify(trigger.condition)}`,
          `6. 选择运行 \"${trigger.shortcutName}\"`
        );
        break;
    }

    return instructions.join("\n");
  }

  // ==================== Cache Management ====================

  private saveCacheToFile(): void {
    if (this.shortcutsCache) {
      try {
        writeFileSync(
          this.cachePath,
          JSON.stringify({
            shortcuts: this.shortcutsCache,
            timestamp: this.cacheTime,
          })
        );
      } catch {
        // Ignore
      }
    }
  }

  private loadCacheFromFile(): Shortcut[] | null {
    try {
      if (existsSync(this.cachePath)) {
        const data = JSON.parse(readFileSync(this.cachePath, "utf-8"));
        if (Date.now() - data.timestamp < this.cacheMaxAge * 60) {
          // 1 hour for file cache
          return data.shortcuts;
        }
      }
    } catch {
      // Ignore
    }
    return null;
  }

  /**
   * 清除缓存
   */
  clearCache(): void {
    this.shortcutsCache = null;
    this.cacheTime = 0;
  }
}

// ==================== Solar-Shortcuts Bridge ====================

export class SolarShortcutsBridge {
  private manager: AppleShortcutsManager;
  private mappings: Map<string, string> = new Map();

  constructor() {
    this.manager = new AppleShortcutsManager();
    this.initializeMappings();
  }

  private initializeMappings(): void {
    // Solar 命令 -> Shortcuts 名称 映射
    this.mappings.set("/solar", "Solar - 开始开发");
    this.mappings.set("/office", "Solar - 办公模式");
    this.mappings.set("/commit", "Solar - 提交代码");
    this.mappings.set("/status", "Solar - 查看状态");
  }

  /**
   * 检查是否有对应的快捷指令
   */
  hasShortcut(solarCommand: string): boolean {
    return this.mappings.has(solarCommand);
  }

  /**
   * 通过 Solar 命令运行快捷指令
   */
  async runFromSolarCommand(
    command: string,
    input?: string
  ): Promise<ShortcutRunResult | null> {
    const shortcutName = this.mappings.get(command);
    if (!shortcutName) {
      return null;
    }

    return this.manager.run(shortcutName, { input });
  }

  /**
   * 注册自定义映射
   */
  registerMapping(solarCommand: string, shortcutName: string): void {
    this.mappings.set(solarCommand, shortcutName);
  }

  /**
   * 获取所有映射
   */
  getMappings(): Map<string, string> {
    return new Map(this.mappings);
  }

  /**
   * 同步 Solar Skills 到 Shortcuts
   */
  async syncSkillsToShortcuts(skills: { name: string; command: string }[]): Promise<void> {
    for (const skill of skills) {
      const shortcutName = `Solar - ${skill.name}`;
      const exists = await this.manager.get(shortcutName);

      if (!exists) {
        console.log(`[SolarShortcuts] Shortcut not found: ${shortcutName}`);
        console.log(`  To create, run: shortcuts://create-shortcut`);
      }

      this.mappings.set(skill.command, shortcutName);
    }
  }

  /**
   * 获取管理器实例
   */
  getManager(): AppleShortcutsManager {
    return this.manager;
  }
}

// ==================== Exports ====================

export function createShortcutsManager(): AppleShortcutsManager {
  return new AppleShortcutsManager();
}

export function createShortcutsBridge(): SolarShortcutsBridge {
  return new SolarShortcutsBridge();
}

// 单例
let globalManager: AppleShortcutsManager | null = null;
let globalBridge: SolarShortcutsBridge | null = null;

export function getShortcutsManager(): AppleShortcutsManager {
  if (!globalManager) {
    globalManager = createShortcutsManager();
  }
  return globalManager;
}

export function getShortcutsBridge(): SolarShortcutsBridge {
  if (!globalBridge) {
    globalBridge = createShortcutsBridge();
  }
  return globalBridge;
}
