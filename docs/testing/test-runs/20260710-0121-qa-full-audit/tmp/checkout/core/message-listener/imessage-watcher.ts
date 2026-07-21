#!/usr/bin/env bun
/**
 * iMessage 数据库监听器
 * 直接监听 iMessage 数据库变化，自动处理新消息
 */

import Database from "bun:sqlite";
import { MessageHandler } from "./message-handler";
import { watch } from "fs";

const IMESSAGE_DB = `${process.env.HOME}/Library/Messages/chat.db`;
const CHECK_INTERVAL = 2000; // 每 2 秒检查一次

interface Message {
  guid: string;
  text: string;
  handle_id: string;
  date: number;
  is_from_me: number;
}

class IMessageWatcher {
  private handler: MessageHandler;
  private lastChecked: number;
  private processedMessages: Set<string>;

  constructor() {
    this.handler = new MessageHandler();
    this.lastChecked = Date.now() - 60000; // 从 1 分钟前开始
    this.processedMessages = new Set();
  }

  /**
   * 启动监听
   */
  async start() {
    console.log("╭────────────────────────────────────────────────────╮");
    console.log("│     Solar iMessage 监听器启动                      │");
    console.log("╰────────────────────────────────────────────────────╯");
    console.log(`监听数据库: ${IMESSAGE_DB}`);
    console.log(`检查间隔: ${CHECK_INTERVAL}ms`);
    console.log("等待新消息...\n");

    // 定期检查新消息
    setInterval(() => this.checkNewMessages(), CHECK_INTERVAL);
  }

  /**
   * 检查新消息
   */
  private async checkNewMessages() {
    try {
      const db = new Database(IMESSAGE_DB, { readonly: true });

      // 查询最近的消息
      const messages = db
        .prepare(
          `
        SELECT
          m.guid,
          m.text,
          m.handle_id,
          m.date,
          m.is_from_me
        FROM message m
        WHERE m.date > ?
          AND m.is_from_me = 0
          AND m.text IS NOT NULL
          AND m.text != ''
        ORDER BY m.date DESC
        LIMIT 10
      `,
        )
        .all(this.getAppleTimestamp(this.lastChecked)) as Message[];

      db.close();

      for (const msg of messages.reverse()) {
        // 跳过已处理的消息
        if (this.processedMessages.has(msg.guid)) {
          continue;
        }

        // 标记为已处理
        this.processedMessages.add(msg.guid);

        // 获取发送者信息
        const sender = await this.getSender(msg.handle_id);

        console.log(`\n[${new Date().toLocaleTimeString()}] 收到消息:`);
        console.log(`  发送者: ${sender}`);
        console.log(`  内容: ${msg.text}`);

        // 处理消息
        const result = await this.handler.processMessage(sender, msg.text, msg.guid);

        if (result.success) {
          console.log(`  ✓ 处理成功: ${result.result?.substring(0, 50)}...`);
        } else {
          console.log(`  ✗ 处理失败: ${result.error}`);
        }
      }

      // 更新最后检查时间
      if (messages.length > 0) {
        this.lastChecked = Date.now();
      }

      // 清理旧的已处理消息记录 (保留最近 100 条)
      if (this.processedMessages.size > 100) {
        const arr = Array.from(this.processedMessages);
        this.processedMessages = new Set(arr.slice(-100));
      }
    } catch (error: any) {
      if (error.message.includes("authorization denied")) {
        console.error(
          "\n❌ 错误: 无法访问 iMessage 数据库\n" +
            "需要授予 Full Disk Access 权限:\n" +
            "  1. 系统设置 → Privacy & Security → Full Disk Access\n" +
            "  2. 添加 Terminal.app (或 iTerm.app)\n" +
            "  3. 重启终端后重新运行\n",
        );
        process.exit(1);
      }
      // 其他错误静默处理
    }
  }

  /**
   * 获取发送者信息
   */
  private async getSender(handleId: number): Promise<string> {
    try {
      const db = new Database(IMESSAGE_DB, { readonly: true });
      const handle = db
        .prepare(
          `
        SELECT id FROM handle WHERE ROWID = ?
      `,
        )
        .get(handleId) as { id: string } | undefined;
      db.close();

      return handle?.id || "unknown";
    } catch {
      return "unknown";
    }
  }

  /**
   * 转换为 Apple 时间戳
   * Apple 时间从 2001-01-01 00:00:00 开始计算
   */
  private getAppleTimestamp(unixTimestamp: number): number {
    const appleEpoch = 978307200000; // 2001-01-01 in Unix epoch
    return (unixTimestamp - appleEpoch) * 1000000; // Apple 用纳秒
  }

  /**
   * 关闭监听
   */
  close() {
    this.handler.close();
  }
}

// ============================================================
// 启动监听器
// ============================================================

if (import.meta.main) {
  const watcher = new IMessageWatcher();

  // 处理退出信号
  process.on("SIGINT", () => {
    console.log("\n\n正在关闭监听器...");
    watcher.close();
    process.exit(0);
  });

  process.on("SIGTERM", () => {
    watcher.close();
    process.exit(0);
  });

  // 启动监听
  watcher.start();
}
