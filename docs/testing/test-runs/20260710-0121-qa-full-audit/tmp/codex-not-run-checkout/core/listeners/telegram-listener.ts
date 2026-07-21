/**
 * Telegram Bot Listener
 * 使用 Bot API long-polling
 *
 * 配置:
 * 1. 创建 Bot: @BotFather → /newbot
 * 2. 获取 Token
 * 3. 配置 ~/.solar/config.json: { "telegram_bot_token": "YOUR_TOKEN" }
 */

import { MessageIngester } from './message-ingester';

const CONFIG_PATH = `${process.env.HOME}/.solar/config.json`;
const POLL_TIMEOUT = 30; // Long-polling timeout in seconds

interface TelegramUpdate {
  update_id: number;
  message?: {
    message_id: number;
    from?: {
      id: number;
      username?: string;
      first_name?: string;
    };
    chat: {
      id: number;
      type: string;
    };
    date: number;
    text?: string;
  };
}

interface TelegramConfig {
  telegram_bot_token?: string;
  telegram_allowed_users?: number[]; // Whitelist user IDs
}

export class TelegramListener {
  private ingester: MessageIngester;
  private running: boolean = false;
  private token: string = '';
  private allowedUsers: Set<number> = new Set();
  private lastUpdateId: number = 0;

  constructor() {
    this.ingester = new MessageIngester();
  }

  async start(): Promise<void> {
    if (this.running) return;

    // Load config
    try {
      const configFile = Bun.file(CONFIG_PATH);
      if (await configFile.exists()) {
        const config: TelegramConfig = await configFile.json();
        this.token = config.telegram_bot_token || '';
        if (config.telegram_allowed_users) {
          this.allowedUsers = new Set(config.telegram_allowed_users);
        }
      }
    } catch (error) {
      console.error('[Telegram] Error loading config:', error);
    }

    if (!this.token) {
      console.error('[Telegram] No bot token configured. Set telegram_bot_token in ~/.solar/config.json');
      return;
    }

    this.running = true;
    console.log('[Telegram] Starting bot listener');

    // Start polling loop
    this.pollLoop();
  }

  stop(): void {
    this.running = false;
    this.ingester.close();
    console.log('[Telegram] Stopped');
  }

  private async pollLoop(): Promise<void> {
    while (this.running) {
      try {
        const updates = await this.getUpdates();

        for (const update of updates) {
          await this.processUpdate(update);
          this.lastUpdateId = update.update_id;
        }
      } catch (error) {
        console.error('[Telegram] Poll error:', error);
        // Wait before retrying
        await Bun.sleep(5000);
      }
    }
  }

  private async getUpdates(): Promise<TelegramUpdate[]> {
    const url = `https://api.telegram.org/bot${this.token}/getUpdates`;
    const params = new URLSearchParams({
      offset: String(this.lastUpdateId + 1),
      timeout: String(POLL_TIMEOUT),
      allowed_updates: JSON.stringify(['message'])
    });

    const response = await fetch(`${url}?${params}`);
    const data = await response.json() as { ok: boolean; result: TelegramUpdate[] };

    if (!data.ok) {
      throw new Error('Telegram API error');
    }

    return data.result;
  }

  private async processUpdate(update: TelegramUpdate): Promise<void> {
    const message = update.message;
    if (!message?.text) return;

    const userId = message.from?.id;
    const username = message.from?.username || message.from?.first_name || 'unknown';

    // Check whitelist if configured
    if (this.allowedUsers.size > 0 && userId && !this.allowedUsers.has(userId)) {
      console.log(`[Telegram] Blocked message from non-whitelisted user: ${userId}`);
      await this.sendReply(message.chat.id, '抱歉，您没有权限使用此 Bot。');
      return;
    }

    // Ingest message
    const result = await this.ingester.ingest({
      source: 'telegram',
      sourceId: `${message.message_id}`,
      sender: username,
      content: message.text,
      timestamp: new Date(message.date * 1000),
      metadata: {
        chat_id: message.chat.id,
        user_id: userId,
        chat_type: message.chat.type
      }
    });

    if (result.success) {
      console.log(`[Telegram] Ingested: ${message.message_id} from @${username}`);
      // Acknowledge receipt
      await this.sendReply(message.chat.id, `✓ 已收到任务 #${result.taskId}`);
    } else if (result.duplicate) {
      console.log(`[Telegram] Duplicate: ${message.message_id}`);
    } else {
      console.error(`[Telegram] Failed: ${result.error}`);
      await this.sendReply(message.chat.id, `❌ 处理失败: ${result.error}`);
    }
  }

  private async sendReply(chatId: number, text: string): Promise<void> {
    try {
      const url = `https://api.telegram.org/bot${this.token}/sendMessage`;
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text
        })
      });
    } catch (error) {
      console.error('[Telegram] Failed to send reply:', error);
    }
  }
}

// CLI / standalone mode
if (import.meta.main) {
  const listener = new TelegramListener();

  process.on('SIGINT', () => {
    listener.stop();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    listener.stop();
    process.exit(0);
  });

  listener.start().then(() => {
    console.log('[Telegram] Listener started. Press Ctrl+C to stop.');
  });
}
