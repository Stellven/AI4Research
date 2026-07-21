#!/usr/bin/env bun
/**
 * Pushover 通知发送器
 * https://pushover.net/api
 */

const PUSHOVER_API = 'https://api.pushover.net/1/messages.json';

interface PushoverConfig {
  userKey: string;    // Your User Key
  apiToken: string;   // Application API Token
}

interface PushoverMessage {
  title?: string;
  message: string;
  priority?: -2 | -1 | 0 | 1 | 2;  // -2=lowest, 2=emergency
  sound?: string;
  url?: string;
  urlTitle?: string;
  html?: boolean;
}

// 从环境变量或配置文件读取
function getConfig(): PushoverConfig {
  const userKey = process.env.PUSHOVER_USER_KEY;
  const apiToken = process.env.PUSHOVER_API_TOKEN;

  if (!userKey || !apiToken) {
    throw new Error('请设置环境变量 PUSHOVER_USER_KEY 和 PUSHOVER_API_TOKEN');
  }

  return { userKey, apiToken };
}

export async function sendPushover(msg: PushoverMessage): Promise<{ success: boolean; error?: string }> {
  try {
    const config = getConfig();

    const body = new URLSearchParams({
      token: config.apiToken,
      user: config.userKey,
      message: msg.message,
      ...(msg.title && { title: msg.title }),
      ...(msg.priority !== undefined && { priority: String(msg.priority) }),
      ...(msg.sound && { sound: msg.sound }),
      ...(msg.url && { url: msg.url }),
      ...(msg.urlTitle && { url_title: msg.urlTitle }),
      ...(msg.html && { html: '1' }),
    });

    const response = await fetch(PUSHOVER_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });

    const result = await response.json();

    if (result.status === 1) {
      console.log('[Pushover] ✓ 通知已发送');
      return { success: true };
    } else {
      return { success: false, error: result.errors?.join(', ') || 'Unknown error' };
    }
  } catch (e: any) {
    return { success: false, error: e.message };
  }
}

// CLI
if (import.meta.main) {
  const [title, ...messageParts] = process.argv.slice(2);

  if (!title) {
    console.log(`Usage: pushover.ts <title> <message>

Environment variables required:
  PUSHOVER_USER_KEY   - Your Pushover user key
  PUSHOVER_API_TOKEN  - Your application API token

Example:
  export PUSHOVER_USER_KEY="xxx"
  export PUSHOVER_API_TOKEN="yyy"
  bun pushover.ts "Solar" "任务完成！"
`);
    process.exit(1);
  }

  const message = messageParts.join(' ') || title;
  const actualTitle = messageParts.length > 0 ? title : 'Solar';

  sendPushover({
    title: actualTitle,
    message: message,
    sound: 'pushover',
  }).then(result => {
    if (!result.success) {
      console.error('发送失败:', result.error);
      process.exit(1);
    }
  });
}
