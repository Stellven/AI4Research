/**
 * Solar Plugin Host - 插件管理器
 * 加载、卸载、管理插件生命周期
 */

import type { StateManager } from "../nerve/state-manager";
import { existsSync, readdirSync } from "fs";
import { join } from "path";

// ==================== 类型定义 ====================

export type PluginType = "skill" | "hook" | "agent" | "model" | "custom";

export interface PluginManifest {
  name: string;
  version: string;
  type: PluginType;
  description?: string;
  author?: string;
  entry: string;
  config?: Record<string, ConfigField>;
  dependencies?: Record<string, string>;
}

export interface ConfigField {
  type: "string" | "number" | "boolean" | "select";
  description: string;
  default?: any;
  required?: boolean;
  options?: string[];
}

export interface PluginContext {
  state: StateManager;
  config: Record<string, any>;
  log: (level: string, message: string, data?: any) => void;
  emit: (event: string, data: any) => void;
}

export interface Plugin {
  manifest: PluginManifest;
  instance: any;
  context: PluginContext;
  status: "loaded" | "active" | "error" | "disabled";
  error?: string;
}

// ==================== Plugin Host ====================

export class PluginHost {
  private pluginDir: string;
  private state: StateManager;
  private plugins: Map<string, Plugin> = new Map();
  private eventHandlers: Map<string, Set<(data: any) => void>> = new Map();

  constructor(pluginDir: string, state: StateManager) {
    this.pluginDir = pluginDir;
    this.state = state;
  }

  // ==================== 生命周期 ====================

  /**
   * 加载所有插件
   */
  async loadAll(): Promise<void> {
    if (!existsSync(this.pluginDir)) {
      return;
    }

    // 遍历插件类型目录
    const types: PluginType[] = ["skill", "hook", "agent", "model", "custom"];

    for (const type of types) {
      const typeDir = join(this.pluginDir, `${type}s`);
      if (!existsSync(typeDir)) continue;

      const pluginDirs = readdirSync(typeDir, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .map((d) => d.name);

      for (const name of pluginDirs) {
        try {
          await this.load(name);
        } catch (e) {
          console.error(`Failed to load plugin ${name}:`, e);
        }
      }
    }
  }

  /**
   * 卸载所有插件
   */
  async unloadAll(): Promise<void> {
    for (const [name] of this.plugins) {
      await this.unload(name);
    }
  }

  /**
   * 加载插件
   */
  async load(name: string): Promise<{ success: boolean; error?: string }> {
    // 查找插件目录
    const pluginPath = await this.findPluginPath(name);
    if (!pluginPath) {
      return { success: false, error: `Plugin not found: ${name}` };
    }

    // 读取 manifest
    const manifestPath = join(pluginPath, "manifest.json");
    if (!existsSync(manifestPath)) {
      return {
        success: false,
        error: `manifest.json not found for plugin: ${name}`,
      };
    }

    let manifest: PluginManifest;
    try {
      manifest = await Bun.file(manifestPath).json();
    } catch (e) {
      return { success: false, error: `Invalid manifest.json: ${e}` };
    }

    // 加载配置
    const config = await this.loadConfig(name, manifest.config);

    // 创建上下文
    const context = this.createContext(name, config);

    // 加载入口模块
    const entryPath = join(pluginPath, manifest.entry);
    if (!existsSync(entryPath)) {
      return {
        success: false,
        error: `Entry file not found: ${manifest.entry}`,
      };
    }

    let instance: any;
    try {
      const module = await import(entryPath);
      instance = module.default || module;

      // 调用 activate
      if (typeof instance.activate === "function") {
        await instance.activate(context);
      }
    } catch (e) {
      return { success: false, error: `Failed to load plugin: ${e}` };
    }

    // 注册插件
    const plugin: Plugin = {
      manifest,
      instance,
      context,
      status: "active",
    };

    this.plugins.set(name, plugin);

    // 注册到数据库
    this.registerInDb(manifest, pluginPath, config);

    console.log(`Plugin loaded: ${name} v${manifest.version}`);
    return { success: true };
  }

  /**
   * 卸载插件
   */
  async unload(name: string): Promise<void> {
    const plugin = this.plugins.get(name);
    if (!plugin) return;

    try {
      // 调用 deactivate
      if (typeof plugin.instance.deactivate === "function") {
        await plugin.instance.deactivate();
      }
    } catch (e) {
      console.error(`Error deactivating plugin ${name}:`, e);
    }

    this.plugins.delete(name);
    console.log(`Plugin unloaded: ${name}`);
  }

  /**
   * 健康检查
   */
  async healthCheck(): Promise<void> {
    for (const [name, plugin] of this.plugins) {
      if (plugin.status === "error") continue;

      try {
        if (typeof plugin.instance.healthCheck === "function") {
          await plugin.instance.healthCheck();
        }
      } catch (e) {
        console.error(`Plugin ${name} health check failed:`, e);
        plugin.status = "error";
        plugin.error = String(e);
      }
    }
  }

  // ==================== 插件调用 ====================

  /**
   * 执行 Skill
   */
  async executeSkill(name: string, args: string): Promise<string> {
    const plugin = this.plugins.get(name);
    if (!plugin) {
      throw new Error(`Skill not found: ${name}`);
    }

    if (plugin.manifest.type !== "skill") {
      throw new Error(`Plugin ${name} is not a skill`);
    }

    if (typeof plugin.instance.execute !== "function") {
      throw new Error(`Skill ${name} does not have execute method`);
    }

    return await plugin.instance.execute(args, plugin.context);
  }

  /**
   * 触发 Hook
   */
  async triggerHook(
    event: string,
    data: any,
  ): Promise<Array<{ continue: boolean; systemMessage?: string }>> {
    const results: Array<{ continue: boolean; systemMessage?: string }> = [];

    for (const [name, plugin] of this.plugins) {
      if (plugin.manifest.type !== "hook") continue;

      if (typeof plugin.instance.handle !== "function") continue;

      // 检查事件匹配
      const events = plugin.instance.events || [];
      if (!events.includes(event)) continue;

      try {
        const result = await plugin.instance.handle(
          event,
          data,
          plugin.context,
        );
        results.push(result);

        // 如果 continue 为 false，停止后续 hook
        if (!result.continue) break;
      } catch (e) {
        console.error(`Hook ${name} error:`, e);
      }
    }

    return results;
  }

  /**
   * 获取 Agent 定义
   */
  getAgentDefinition(name: string): any {
    const plugin = this.plugins.get(name);
    if (!plugin || plugin.manifest.type !== "agent") {
      return null;
    }
    return plugin.instance;
  }

  /**
   * 获取 Model 适配器
   */
  getModelAdapter(name: string): any {
    const plugin = this.plugins.get(name);
    if (!plugin || plugin.manifest.type !== "model") {
      return null;
    }
    return plugin.instance.adapter;
  }

  // ==================== 辅助方法 ====================

  private async findPluginPath(name: string): Promise<string | null> {
    const types = ["skills", "hooks", "agents", "models", "custom"];

    for (const type of types) {
      const path = join(this.pluginDir, type, name);
      if (existsSync(path)) {
        return path;
      }
    }

    // 直接在 pluginDir 下查找
    const directPath = join(this.pluginDir, name);
    if (existsSync(directPath)) {
      return directPath;
    }

    return null;
  }

  private async loadConfig(
    name: string,
    schema?: Record<string, ConfigField>,
  ): Promise<Record<string, any>> {
    // 从数据库加载
    const db = this.state.getDb();
    const row = db
      .query("SELECT config FROM plugins WHERE name = ?")
      .get([name]) as { config: string } | null;

    let config: Record<string, any> = {};
    if (row?.config) {
      try {
        config = JSON.parse(row.config);
      } catch {}
    }

    // 应用默认值
    if (schema) {
      for (const [key, field] of Object.entries(schema)) {
        if (!(key in config) && field.default !== undefined) {
          config[key] = field.default;
        }
      }
    }

    return config;
  }

  private createContext(
    name: string,
    config: Record<string, any>,
  ): PluginContext {
    return {
      state: this.state,
      config,
      log: (level, message, data) => {
        const content = { message, data };
        this.state.run(
          `INSERT INTO messages (type, source, level, content) VALUES (?, ?, ?, ?)`,
          ["plugin", name, level, JSON.stringify(content)],
        );
      },
      emit: (event, data) => {
        this.emitEvent(`${name}:${event}`, data);
      },
    };
  }

  private registerInDb(
    manifest: PluginManifest,
    path: string,
    config: Record<string, any>,
  ): void {
    this.state.run(
      `
      INSERT INTO plugins (name, version, type, path, description, config)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(name) DO UPDATE SET
        version = excluded.version,
        path = excluded.path,
        description = excluded.description,
        config = excluded.config,
        enabled = TRUE,
        updated_at = CURRENT_TIMESTAMP
    `,
      [
        manifest.name,
        manifest.version,
        manifest.type,
        path,
        manifest.description,
        JSON.stringify(config),
      ],
    );
  }

  // ==================== 事件系统 ====================

  on(event: string, handler: (data: any) => void): () => void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set());
    }
    this.eventHandlers.get(event)!.add(handler);

    return () => {
      this.eventHandlers.get(event)?.delete(handler);
    };
  }

  private emitEvent(event: string, data: any): void {
    this.eventHandlers.get(event)?.forEach((handler) => {
      try {
        handler(data);
      } catch (e) {
        console.error(`Event handler error for ${event}:`, e);
      }
    });

    // 通配符监听
    this.eventHandlers.get("*")?.forEach((handler) => {
      try {
        handler({ event, data });
      } catch (e) {
        console.error(`Global event handler error:`, e);
      }
    });
  }

  // ==================== 查询方法 ====================

  getLoadedCount(): number {
    return this.plugins.size;
  }

  getLoadedPlugins(): string[] {
    return Array.from(this.plugins.keys());
  }

  getPluginStatus(name: string): Plugin | undefined {
    return this.plugins.get(name);
  }

  listPlugins(): Array<{
    name: string;
    version: string;
    type: PluginType;
    status: string;
  }> {
    return Array.from(this.plugins.values()).map((p) => ({
      name: p.manifest.name,
      version: p.manifest.version,
      type: p.manifest.type,
      status: p.status,
    }));
  }
}
