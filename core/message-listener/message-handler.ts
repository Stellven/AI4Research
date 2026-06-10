#!/usr/bin/env bun
/**
 * Solar 消息处理器
 * 处理来自 iMessage 的任务请求
 */

import Database from "bun:sqlite";
import { randomUUID } from "crypto";
import { TaskScheduler, type TaskPriority } from "./task-scheduler";

// ============================================================
// Types
// ============================================================

interface Intent {
  type: "task" | "query" | "control" | "unknown";
  action: string;
  params: Record<string, any>;
  confidence: number;
}

interface ProcessResult {
  success: boolean;
  result?: string;
  error?: string;
  execution_time_ms?: number;
}

// ============================================================
// Message Handler Class
// ============================================================

export class MessageHandler {
  private db: Database;
  private scheduler: TaskScheduler;

  constructor(dbPath: string = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`) {
    this.db = new Database(dbPath);
    this.scheduler = new TaskScheduler(dbPath);
    this.ensureSchema();
  }

  /**
   * 确保 Schema 存在
   */
  private ensureSchema() {
    const schemaPath = `${process.env.HOME}/Solar/core/message-listener/schema.sql`;
    try {
      const schema = Bun.file(schemaPath).text();
      this.db.exec(schema.toString());
    } catch (error) {
      console.warn("Schema file not found, skipping initialization");
    }
  }

  /**
   * 处理消息 (主入口)
   */
  async processMessage(
    sender: string,
    content: string,
    messageId?: string,
  ): Promise<ProcessResult> {
    const taskId = randomUUID().slice(0, 16);
    const startTime = Date.now();

    // 1. 检查白名单
    if (!this.isAuthorized(sender)) {
      return {
        success: false,
        error: "未授权的发送者",
      };
    }

    // 2. 意图分类
    const intent = this.classifyIntent(content);

    // 3. 优先级分析
    const priority = this.scheduler.analyzePriority(content);

    // 4. Token 预估
    const estimatedTokens = this.scheduler.estimateTokens(content, intent.action);

    // 5. 记录任务
    this.db
      .prepare(
        `
      INSERT INTO bl_message_tasks (
        task_id, message_id, sender, content,
        priority, intent_type, intent_action, intent_params,
        estimated_tokens, status
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    `,
      )
      .run(
        taskId,
        messageId || taskId,
        sender,
        content,
        priority,
        intent.type,
        intent.action,
        JSON.stringify(intent.params),
        estimatedTokens,
      );

    try {
      // 6. 执行决策
      const decision = await this.scheduler.decide({
        task_id: taskId,
        priority,
        estimated_tokens: estimatedTokens,
        description: content,
      });

      // 7. 根据决策执行或延迟
      if (!decision.should_execute) {
        // 延迟执行
        const deferredUntil = decision.recommended_time
          ? new Date(Date.now() + (decision.estimated_wait_time_sec || 0) * 1000)
          : null;

        this.db
          .prepare(
            `
          UPDATE bl_message_tasks
          SET status = 'deferred',
              deferred_reason = ?,
              deferred_until = ?
          WHERE task_id = ?
        `,
          )
          .run(decision.reason, deferredUntil?.toISOString() || null, taskId);

        return {
          success: true,
          result: `任务已延迟执行\n原因: ${decision.reason}\n${decision.recommended_time ? `推荐时间: ${decision.recommended_time}` : ""}`,
        };
      }

      // 8. 执行任务
      this.db
        .prepare(
          `
        UPDATE bl_message_tasks
        SET status = 'running', started_at = datetime('now')
        WHERE task_id = ?
      `,
        )
        .run(taskId);

      const result = await this.executeIntent(intent);

      const executionTime = Date.now() - startTime;

      // 9. 更新结果并记录 Token 使用
      const actualTokens = estimatedTokens; // TODO: 从实际执行中获取

      this.db
        .prepare(
          `
        UPDATE bl_message_tasks
        SET status = ?,
            result = ?,
            execution_time_ms = ?,
            execution_tokens = ?,
            completed_at = datetime('now')
        WHERE task_id = ?
      `,
        )
        .run(
          result.success ? "done" : "failed",
          result.result || result.error,
          executionTime,
          actualTokens,
          taskId,
        );

      // 10. 记录 Token 使用到调度器
      this.scheduler.recordExecution(taskId, actualTokens);

      return {
        ...result,
        execution_time_ms: executionTime,
      };
    } catch (error: any) {
      const executionTime = Date.now() - startTime;

      this.db
        .prepare(
          `
        UPDATE bl_message_tasks
        SET status = 'failed', error = ?, execution_time_ms = ?, completed_at = datetime('now')
        WHERE task_id = ?
      `,
        )
        .run(error.message, executionTime, taskId);

      return {
        success: false,
        error: error.message,
        execution_time_ms: executionTime,
      };
    }
  }

  /**
   * 检查发送者是否在白名单中
   */
  private isAuthorized(sender: string): boolean {
    const trigger = this.db
      .prepare(
        `
      SELECT enabled FROM bl_message_triggers
      WHERE (contact_phone = ? OR contact_email = ?) AND enabled = true
    `,
      )
      .get(sender, sender) as { enabled: number } | undefined;

    // 如果没有配置白名单，默认拒绝
    return trigger !== undefined;
  }

  /**
   * 意图分类
   */
  private classifyIntent(message: string): Intent {
    const msg = message.toLowerCase().trim();

    // 查询类关键词
    if (
      this.matchKeywords(msg, [
        "状态",
        "进度",
        "列表",
        "backlog",
        "list",
        "有哪些",
        "查看",
      ])
    ) {
      if (msg.includes("backlog") || msg.includes("任务")) {
        return {
          type: "query",
          action: "list_backlog",
          params: {},
          confidence: 0.9,
        };
      }
      if (msg.includes("状态") || msg.includes("进度")) {
        return {
          type: "query",
          action: "show_status",
          params: {},
          confidence: 0.9,
        };
      }
    }

    // 任务类关键词
    if (
      this.matchKeywords(msg, [
        "帮我",
        "查",
        "执行",
        "运行",
        "搜索",
        "找",
        "获取",
      ])
    ) {
      // 天气查询
      if (msg.includes("天气")) {
        const cityMatch = msg.match(
          /(北京|上海|深圳|广州|杭州|成都|[a-zA-Z\u4e00-\u9fa5]{2,})(天气|的天气)?/,
        );
        const city = cityMatch ? cityMatch[1] : "北京";
        return {
          type: "task",
          action: "weather_query",
          params: { city },
          confidence: 0.95,
        };
      }

      // HN 查询
      if (
        msg.includes("hn") ||
        msg.includes("hacker") ||
        msg.includes("技术新闻")
      ) {
        return {
          type: "task",
          action: "hn_fetch",
          params: {},
          confidence: 0.9,
        };
      }

      // 邮件搜索
      if (
        msg.includes("邮件") ||
        msg.includes("email") ||
        msg.includes("mail")
      ) {
        const keywordMatch = msg.match(
          /(["\'](.+?)["\']|包含\s*(.+?)(?:\s|$)|主题\s*(.+?)(?:\s|$))/,
        );
        const keyword = keywordMatch
          ? keywordMatch[2] || keywordMatch[3] || keywordMatch[4]
          : "";
        return {
          type: "task",
          action: "email_search",
          params: { keyword },
          confidence: 0.85,
        };
      }

      // 文件搜索
      if (msg.includes("文件") || msg.includes("搜索")) {
        const keywordMatch = msg.match(/搜索\s*(.+?)(?:\s|$)/);
        const keyword = keywordMatch ? keywordMatch[1] : "";
        return {
          type: "task",
          action: "file_search",
          params: { keyword },
          confidence: 0.8,
        };
      }
    }

    // 控制类关键词
    if (this.matchKeywords(msg, ["停止", "取消", "暂停", "stop", "cancel"])) {
      return {
        type: "control",
        action: "stop_task",
        params: {},
        confidence: 0.9,
      };
    }

    // 未知意图
    return {
      type: "unknown",
      action: "unknown",
      params: { original_message: message },
      confidence: 0.0,
    };
  }

  /**
   * 匹配关键词
   */
  private matchKeywords(text: string, keywords: string[]): boolean {
    return keywords.some((kw) => text.includes(kw));
  }

  /**
   * 执行意图
   */
  private async executeIntent(intent: Intent): Promise<ProcessResult> {
    switch (intent.action) {
      case "list_backlog":
        return await this.handleListBacklog();

      case "show_status":
        return await this.handleShowStatus();

      case "weather_query":
        return await this.handleWeatherQuery(intent.params.city);

      case "hn_fetch":
        return await this.handleHNFetch();

      case "email_search":
        return await this.handleEmailSearch(intent.params.keyword);

      case "file_search":
        return await this.handleFileSearch(intent.params.keyword);

      case "stop_task":
        return { success: true, result: "任务已停止" };

      default:
        return {
          success: false,
          error: `未知动作: ${intent.action}\n\n支持的命令:\n• backlog 列表\n• 查天气 <城市>\n• HN 头条\n• 搜索邮件 <关键词>`,
        };
    }
  }

  /**
   * 处理 Backlog 列表查询
   */
  private async handleListBacklog(): Promise<ProcessResult> {
    const features = this.db
      .prepare(
        `
      SELECT
        f.title,
        COUNT(t.task_id) as task_count,
        SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as completed
      FROM bl_features f
      LEFT JOIN bl_tasks t ON f.feature_id = t.feature_id
      WHERE f.status != 'archived'
      GROUP BY f.feature_id, f.title
      ORDER BY task_count DESC
    `,
      )
      .all() as Array<{ title: string; task_count: number; completed: number }>;

    if (features.length === 0) {
      return { success: true, result: "Backlog 为空" };
    }

    const lines = ["Backlog 当前状态:\n"];
    for (const f of features) {
      lines.push(`• ${f.title} - ${f.completed}/${f.task_count} 已完成`);
    }

    return { success: true, result: lines.join("\n") };
  }

  /**
   * 处理状态查询
   */
  private async handleShowStatus(): Promise<ProcessResult> {
    const stats = this.db
      .prepare(
        `
      SELECT * FROM v_message_tasks_today
    `,
      )
      .get() as any;

    const result =
      `今日消息任务:\n` +
      `• 总计: ${stats.total}\n` +
      `• 完成: ${stats.completed}\n` +
      `• 失败: ${stats.failed}\n` +
      `• 运行中: ${stats.running}\n` +
      `• 平均耗时: ${stats.avg_time_ms ? stats.avg_time_ms.toFixed(0) : 0}ms`;

    return { success: true, result };
  }

  /**
   * 处理天气查询
   */
  private async handleWeatherQuery(city: string): Promise<ProcessResult> {
    try {
      const proc = Bun.spawn(
        [
          "bun",
          `${process.env.HOME}/.claude/core/ree/scripts/9416537535f2.ts`,
          city,
        ],
        {
          stdout: "pipe",
          stderr: "pipe",
        },
      );

      const output = await new Response(proc.stdout).text();
      await proc.exited;

      if (proc.exitCode === 0) {
        return { success: true, result: output.trim() };
      } else {
        return { success: false, error: "天气查询失败" };
      }
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  }

  /**
   * 处理 HN 抓取
   */
  private async handleHNFetch(): Promise<ProcessResult> {
    try {
      const proc = Bun.spawn(
        ["bun", `${process.env.HOME}/.claude/skills/hn-monitor/fetch.ts`],
        {
          stdout: "pipe",
          stderr: "pipe",
        },
      );

      const output = await new Response(proc.stdout).text();
      await proc.exited;

      // 提取前5条标题
      const lines = output
        .split("\n")
        .filter((l) => l.trim().length > 0)
        .slice(0, 5);

      return { success: true, result: "HN 热门:\n" + lines.join("\n") };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  }

  /**
   * 处理邮件搜索
   */
  private async handleEmailSearch(keyword: string): Promise<ProcessResult> {
    // TODO: 实现邮件搜索 (需要 email-search skill)
    return {
      success: false,
      error: "邮件搜索功能开发中",
    };
  }

  /**
   * 处理文件搜索
   */
  private async handleFileSearch(keyword: string): Promise<ProcessResult> {
    if (!keyword) {
      return { success: false, error: "请提供搜索关键词" };
    }

    const files = this.db
      .prepare(
        `
      SELECT file_path, title, description
      FROM smi_files
      WHERE title LIKE ? OR description LIKE ? OR file_path LIKE ?
      LIMIT 5
    `,
      )
      .all(`%${keyword}%`, `%${keyword}%`, `%${keyword}%`) as Array<any>;

    if (files.length === 0) {
      return { success: true, result: `未找到包含"${keyword}"的文件` };
    }

    const lines = [`找到 ${files.length} 个文件:\n`];
    for (const f of files) {
      lines.push(`• ${f.title || f.file_path}`);
    }

    return { success: true, result: lines.join("\n") };
  }

  close() {
    this.db.close();
    this.scheduler.close();
  }
}

// ============================================================
// CLI Entry Point
// ============================================================

if (import.meta.main) {
  const args = process.argv.slice(2);
  const sender = args[0];
  const message = args.slice(1).join(" ");

  if (!sender || !message) {
    console.error("Usage: message-handler.ts <sender> <message>");
    console.error('Example: message-handler.ts "+8613800138000" "查天气 北京"');
    process.exit(1);
  }

  const handler = new MessageHandler();

  handler
    .processMessage(sender, message)
    .then((result) => {
      if (result.success) {
        console.log(result.result);
      } else {
        console.error("Error:", result.error);
        process.exit(1);
      }
      handler.close();
    })
    .catch((error) => {
      console.error("Fatal error:", error);
      handler.close();
      process.exit(1);
    });
}
