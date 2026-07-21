#!/usr/bin/env bun
/**
 * Reply Sender - 原通道回复发送器
 *
 * 支持通道:
 * - iMessage: 通过 AppleScript
 * - Gmail: 通过 himalaya
 * - Telegram: 通过 Bot API
 */

import { $ } from 'bun';
import { getFromEmail } from '../config/privacy';

// 回复类型定义
export type ReplyType =
  | 'ack'              // 确认收到
  | 'quick_answer'     // 快速回答
  | 'status'           // 状态更新
  | 'notification'     // 通知
  | 'tldr'             // 一句话总结
  | 'bullet_summary'   // 要点摘要
  | 'insight'          // 洞察分析
  | 'comparison'       // 对比分析
  | 'research_report'  // 研究报告
  | 'review'           // 评审报告
  | 'action_items'     // 行动项
  | 'recommendation';  // 推荐建议

// 通道类型
export type Channel = 'imessage' | 'gmail' | 'telegram';

// 回复配置
export interface ReplyConfig {
  channel: Channel;
  recipient: string;      // 收件人 (邮箱/电话/chat_id)
  replyType: ReplyType;
  content: string;
  subject?: string;       // 邮件主题
  inReplyTo?: string;     // 回复的消息 ID
}

// 通道限制
const CHANNEL_LIMITS: Record<Channel, { maxLength: number; format: string }> = {
  imessage: { maxLength: 2000, format: 'plain' },
  gmail: { maxLength: 50000, format: 'html' },
  telegram: { maxLength: 4096, format: 'markdown' },
};

/**
 * 回复发送器
 */
export class ReplySender {
  private telegramToken?: string;

  constructor() {
    this.telegramToken = process.env.TELEGRAM_BOT_TOKEN;
  }

  /**
   * 发送回复
   */
  async send(config: ReplyConfig): Promise<{ success: boolean; error?: string }> {
    const { channel, recipient, content } = config;

    // 内容适配
    const adaptedContent = this.adaptContent(content, channel);

    console.log(`[Reply] 发送到 ${channel}: ${recipient.slice(0, 20)}...`);

    try {
      switch (channel) {
        case 'imessage':
          return await this.sendIMessage(recipient, adaptedContent);
        case 'gmail':
          return await this.sendGmail(recipient, adaptedContent, config.subject, config.inReplyTo);
        case 'telegram':
          return await this.sendTelegram(recipient, adaptedContent);
        default:
          return { success: false, error: `Unknown channel: ${channel}` };
      }
    } catch (e) {
      return { success: false, error: String(e) };
    }
  }

  /**
   * 内容适配 - 根据通道限制调整内容
   */
  private adaptContent(content: string, channel: Channel): string {
    const limit = CHANNEL_LIMITS[channel];

    // 截断过长内容
    if (content.length > limit.maxLength) {
      const truncated = content.slice(0, limit.maxLength - 50);
      return truncated + '\n\n...(内容已截断)';
    }

    return content;
  }

  /**
   * 发送 iMessage
   */
  private async sendIMessage(recipient: string, content: string): Promise<{ success: boolean; error?: string }> {
    // 转义内容中的引号
    const escapedContent = content.replace(/"/g, '\\"').replace(/\n/g, '\\n');

    const script = `
      tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "${recipient}" of targetService
        send "${escapedContent}" to targetBuddy
      end tell
    `;

    try {
      await $`osascript -e ${script}`.quiet();
      console.log(`[Reply] ✓ iMessage 已发送到 ${recipient}`);
      return { success: true };
    } catch (e) {
      // 尝试备用方法 - 使用 buddy
      try {
        const altScript = `
          tell application "Messages"
            send "${escapedContent}" to buddy "${recipient}"
          end tell
        `;
        await $`osascript -e ${altScript}`.quiet();
        console.log(`[Reply] ✓ iMessage 已发送到 ${recipient} (备用方法)`);
        return { success: true };
      } catch (e2) {
        return { success: false, error: String(e2) };
      }
    }
  }

  /**
   * 发送 Gmail
   */
  private async sendGmail(
    recipient: string,
    content: string,
    subject?: string,
    inReplyTo?: string
  ): Promise<{ success: boolean; error?: string }> {
    const subjectLine = subject || 'Re: Solar 回复';

    // 方法1: 使用 Mail.app (最可靠)
    try {
      const escapedContent = content.replace(/"/g, '\\"').replace(/\\/g, '\\\\');
      const escapedSubject = subjectLine.replace(/"/g, '\\"');

      const script = `
        tell application "Mail"
          set newMessage to make new outgoing message with properties {subject:"${escapedSubject}", content:"${escapedContent}", visible:false}
          tell newMessage
            make new to recipient at end of to recipients with properties {address:"${recipient}"}
          end tell
          send newMessage
        end tell
      `;

      await $`osascript -e ${script}`.quiet();
      console.log(`[Reply] ✓ Gmail 已发送到 ${recipient} (Mail.app)`);
      return { success: true };
    } catch (e) {
      // 方法2: himalaya 备用
      try {
        const rawMessage = `From: ${getFromEmail()}
To: ${recipient}
Subject: ${subjectLine}

${content}`;
        await $`himalaya message send ${rawMessage}`.quiet();
        console.log(`[Reply] ✓ Gmail 已发送到 ${recipient} (himalaya)`);
        return { success: true };
      } catch (e2) {
        return { success: false, error: `Mail.app: ${e} | himalaya: ${e2}` };
      }
    }
  }

  /**
   * 发送 Telegram
   */
  private async sendTelegram(chatId: string, content: string): Promise<{ success: boolean; error?: string }> {
    if (!this.telegramToken) {
      return { success: false, error: 'Telegram token not configured' };
    }

    try {
      const url = `https://api.telegram.org/bot${this.telegramToken}/sendMessage`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text: content,
          parse_mode: 'Markdown',
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        return { success: false, error };
      }

      console.log(`[Reply] ✓ Telegram 已发送到 ${chatId}`);
      return { success: true };
    } catch (e) {
      return { success: false, error: String(e) };
    }
  }

  /**
   * 生成回复内容
   */
  static formatReply(replyType: ReplyType, data: Record<string, any>): string {
    switch (replyType) {
      case 'ack':
        return `收到，${data.action || '正在处理中'}...`;

      case 'quick_answer':
        return data.answer || data.content || '已处理';

      case 'status':
        return `状态: ${data.status || '处理中'}\n${data.detail || ''}`;

      case 'notification':
        return `✓ ${data.message || '任务完成'}`;

      case 'tldr':
        return `📌 ${data.summary || data.content}`;

      case 'bullet_summary':
        const points = data.points || [];
        return `📋 摘要:\n${points.map((p: string) => `• ${p}`).join('\n')}`;

      case 'insight':
        return `🔍 分析结果:\n\n${data.summary || ''}\n\n关键发现:\n${
          (data.findings || []).map((f: string, i: number) => `${i + 1}. ${f}`).join('\n')
        }\n\n结论: ${data.conclusion || ''}`;

      case 'comparison':
        return `⚖️ 对比分析:\n\n${data.comparison || ''}\n\n建议: ${data.recommendation || ''}`;

      case 'research_report':
        return `📊 研究报告: ${data.title || ''}\n\n${data.content || ''}`;

      case 'review':
        return `👁️ 评审结果:\n\n${data.content || ''}\n\n建议: ${data.suggestions || ''}`;

      case 'action_items':
        const items = data.items || [];
        return `📝 行动项:\n${items.map((item: string, i: number) => `${i + 1}. ${item}`).join('\n')}`;

      case 'recommendation':
        return `💡 推荐: ${data.recommendation || ''}\n\n理由: ${data.reason || ''}`;

      default:
        return data.content || '已处理';
    }
  }
}

// CLI 测试
if (import.meta.main) {
  const sender = new ReplySender();
  const args = process.argv.slice(2);

  if (args.length < 3) {
    console.log('Usage: reply-sender.ts <channel> <recipient> <message>');
    console.log('Channels: imessage, gmail, telegram');
    process.exit(1);
  }

  const [channel, recipient, ...messageParts] = args;
  const message = messageParts.join(' ');

  sender.send({
    channel: channel as Channel,
    recipient,
    replyType: 'quick_answer',
    content: message,
  }).then(result => {
    if (result.success) {
      console.log('✓ 发送成功');
    } else {
      console.error('✗ 发送失败:', result.error);
    }
  });
}
