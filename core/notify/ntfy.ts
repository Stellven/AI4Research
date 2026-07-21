#!/usr/bin/env bun
/**
 * ntfy.sh 通知发送器
 * 免费、无需注册
 */

const NTFY_SERVER = 'https://ntfy.sh';
const DEFAULT_TOPIC = process.env.SOLAR_NTFY_TOPIC || 'solar-notify';

interface NtfyMessage {
  topic?: string;
  title?: string;
  message: string;
  priority?: 1 | 2 | 3 | 4 | 5;  // 1=min, 5=max
  tags?: string[];  // emoji tags like ["tada", "robot"]
  click?: string;   // URL to open on click
}

export async function sendNtfy(msg: NtfyMessage): Promise<{ success: boolean; error?: string }> {
  const topic = msg.topic || process.env.NTFY_TOPIC || DEFAULT_TOPIC;

  try {
    // 使用 JSON API 以支持 UTF-8 标题
    const payload: Record<string, any> = {
      topic,
      message: msg.message,
    };

    if (msg.title) payload.title = msg.title;
    if (msg.priority) payload.priority = msg.priority;
    if (msg.tags?.length) payload.tags = msg.tags;
    if (msg.click) payload.click = msg.click;

    const response = await fetch(NTFY_SERVER, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (response.ok) {
      console.log(`[ntfy] ✓ 已发送到 ${topic}`);
      return { success: true };
    } else {
      const error = await response.text();
      return { success: false, error };
    }
  } catch (e: any) {
    return { success: false, error: e.message };
  }
}

// CLI
if (import.meta.main) {
  const [title, ...messageParts] = process.argv.slice(2);

  if (!title) {
    console.log(`Usage: ntfy.ts <title> <message>

Example:
  bun ntfy.ts "Solar" "任务完成！"
  bun ntfy.ts "邮件通知" "收到新邮件"
`);
    process.exit(1);
  }

  const message = messageParts.join(' ') || title;
  const actualTitle = messageParts.length > 0 ? title : undefined;

  sendNtfy({
    title: actualTitle,
    message,
    tags: ['robot'],
  }).then(result => {
    if (!result.success) {
      console.error('发送失败:', result.error);
      process.exit(1);
    }
  });
}
