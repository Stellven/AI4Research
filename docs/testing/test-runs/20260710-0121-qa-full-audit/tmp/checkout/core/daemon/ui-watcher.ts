/**
 * Solar UI Watcher - 监控 UI 指令队列并渲染
 * Daemon 组件，监听 ~/.solar/ui/queue/ 目录
 *
 * 支持两种格式:
 * 1. TVS Semantic IR (推荐) - 新的 Terminal Visual System
 * 2. Legacy UICommand - 旧版兼容
 */

import {
  watch,
  existsSync,
  readFileSync,
  unlinkSync,
  readdirSync,
  mkdirSync,
} from "fs";
import { join } from "path";
import { UIEngine, UICommand, RenderResult } from "../engine/ui-engine";
import { tvs, SemanticIR } from "tvs";

export class UIWatcher {
  private engine: UIEngine;
  private queueDir: string;
  private outputCallback?: (result: RenderResult) => void;
  private isRunning = false;

  constructor(queueDir?: string) {
    this.queueDir = queueDir || `${process.env.HOME}/.solar/ui/queue`;
    this.engine = new UIEngine();

    // 确保队列目录存在
    if (!existsSync(this.queueDir)) {
      mkdirSync(this.queueDir, { recursive: true });
    }
  }

  /**
   * 设置输出回调 (可选，默认输出到 console)
   */
  onOutput(callback: (result: RenderResult) => void) {
    this.outputCallback = callback;
  }

  /**
   * 启动监听
   */
  start() {
    if (this.isRunning) return;
    this.isRunning = true;

    console.log(`🎨 UI Watcher started, monitoring: ${this.queueDir}`);

    // 处理已存在的指令
    this.processExisting();

    // 监听新指令
    watch(this.queueDir, async (event, filename) => {
      if (!filename?.endsWith(".json")) return;
      if (event !== "rename" && event !== "change") return;

      const filepath = join(this.queueDir, filename);

      // 等待文件写入完成
      await new Promise((resolve) => setTimeout(resolve, 50));

      if (!existsSync(filepath)) return;

      try {
        await this.processCommand(filepath);
      } catch (e) {
        console.error(`🎨 UI render error: ${e}`);
      }
    });
  }

  /**
   * 停止监听
   */
  stop() {
    this.isRunning = false;
    console.log("🎨 UI Watcher stopped");
  }

  /**
   * 处理已存在的指令文件
   */
  private async processExisting() {
    if (!existsSync(this.queueDir)) return;

    const files = readdirSync(this.queueDir)
      .filter((f) => f.endsWith(".json"))
      .sort(); // 按名称排序 (时间戳顺序)

    for (const file of files) {
      try {
        await this.processCommand(join(this.queueDir, file));
      } catch (e) {
        console.error(`🎨 Error processing ${file}: ${e}`);
      }
    }
  }

  /**
   * 处理单个指令
   */
  private async processCommand(filepath: string) {
    // 读取指令
    const content = readFileSync(filepath, "utf-8");
    let data: any;

    try {
      data = JSON.parse(content);
    } catch (e) {
      console.error(`🎨 Invalid JSON in ${filepath}`);
      unlinkSync(filepath);
      return;
    }

    // 检测格式并渲染
    let result: RenderResult;

    if (this.isTVSFormat(data)) {
      // TVS Semantic IR 格式
      result = this.renderTVS(data);
    } else {
      // Legacy UICommand 格式
      result = await this.engine.render(data as UICommand);
    }

    // 输出
    if (this.outputCallback) {
      this.outputCallback(result);
    } else {
      console.log(result.output);
    }

    // 删除已处理的指令
    try {
      unlinkSync(filepath);
    } catch (e) {
      // 文件可能已被删除
    }
  }

  /**
   * 检测是否为 TVS 格式
   */
  private isTVSFormat(data: any): boolean {
    // TVS 队列格式: { id, ir: SemanticIR, timestamp }
    if (data.ir && data.ir.root) {
      return true;
    }
    // 直接的 SemanticIR 格式: { root, canvas?, style? }
    if (data.root && typeof data.root === "object" && data.root.type) {
      return true;
    }
    return false;
  }

  /**
   * 使用 TVS 渲染
   */
  private renderTVS(data: any): RenderResult {
    try {
      // 提取 IR (支持队列格式和直接格式)
      const ir: SemanticIR = data.ir || data;

      // 渲染
      const output = tvs.render(ir);
      const lines = output.split("\n");

      return {
        output,
        width: Math.max(...lines.map((l) => l.length)),
        height: lines.length,
      };
    } catch (e) {
      const errorMsg = `[TVS Error] ${e}`;
      return {
        output: errorMsg,
        width: errorMsg.length,
        height: 1,
      };
    }
  }

  /**
   * 手动渲染一个指令 (不通过队列)
   */
  async renderDirect(command: UICommand): Promise<RenderResult> {
    return this.engine.render(command);
  }

  /**
   * 使用 TVS 直接渲染 Semantic IR (不通过队列)
   */
  renderIR(ir: SemanticIR, options?: { colors?: boolean }): string {
    return tvs.render(ir, options);
  }

  /**
   * 获取 TVS 实例 (用于高级操作)
   */
  getTVS() {
    return tvs;
  }
}

// ==================== 独立运行入口 ====================

if (import.meta.main) {
  const watcher = new UIWatcher();
  watcher.start();

  // 优雅退出
  process.on("SIGINT", () => {
    watcher.stop();
    process.exit(0);
  });

  process.on("SIGTERM", () => {
    watcher.stop();
    process.exit(0);
  });

  console.log("🎨 UI Watcher running, press Ctrl+C to stop");
}
