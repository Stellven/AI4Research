/**
 * Gmail Listener
 * 使用 himalaya CLI 轮询邮件
 *
 * 工作流程:
 * 1. 定期运行 himalaya list --unread
 * 2. 解析新邮件 → 发送到 Ingester
 * 3. 标记为已读（可选）
 */

import { $ } from 'bun';
import { MessageIngester } from './message-ingester';

const POLL_INTERVAL = 60000; // 60 seconds
const MAX_EMAILS_PER_POLL = 10;

interface HimalayaEnvelope {
  id: string;
  subject: string;
  from: { name?: string; addr: string };
  to: { name?: string; addr: string };
  date: string;
  flags: string[];
  has_attachment: boolean;
}

export class GmailListener {
  private ingester: MessageIngester;
  private running: boolean = false;
  private pollTimer?: Timer;
  private lastSeenIds: Set<string> = new Set();

  constructor() {
    this.ingester = new MessageIngester();
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;

    // Check himalaya is available
    try {
      await $`himalaya --version`.quiet();
    } catch {
      console.error('[Gmail] himalaya not found. Install with: brew install himalaya');
      this.running = false;
      return;
    }

    console.log('[Gmail] Starting listener (polling every 60s)');

    // Initial poll
    await this.poll();

    // Start polling
    this.pollTimer = setInterval(() => this.poll(), POLL_INTERVAL);
  }

  stop(): void {
    this.running = false;
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = undefined;
    }
    this.ingester.close();
    console.log('[Gmail] Stopped');
  }

  private async poll(): Promise<void> {
    if (!this.running) return;

    try {
      // List recent envelopes (himalaya v1.x API)
      const result = await $`himalaya envelope list --folder INBOX -o json`.quiet();
      const output = result.stdout.toString();

      if (!output.trim()) {
        return;
      }

      let emails: HimalayaEnvelope[];
      try {
        emails = JSON.parse(output);
      } catch {
        // himalaya might return non-JSON for empty results
        return;
      }

      if (!Array.isArray(emails)) {
        return;
      }

      // Process new emails
      for (const email of emails.slice(0, MAX_EMAILS_PER_POLL)) {
        if (this.lastSeenIds.has(email.id)) {
          continue;
        }

        await this.processEmail(email);
        this.lastSeenIds.add(email.id);
      }

      // Cleanup old IDs (keep last 1000)
      if (this.lastSeenIds.size > 1000) {
        const idsArray = Array.from(this.lastSeenIds);
        this.lastSeenIds = new Set(idsArray.slice(-500));
      }

    } catch (error) {
      console.error('[Gmail] Poll error:', error);
    }
  }

  private async processEmail(email: HimalayaEnvelope): Promise<void> {
    try {
      // Get email body
      let body = email.subject; // Default to subject if body fetch fails

      try {
        const bodyResult = await $`himalaya message read ${email.id} --no-headers --preview`.quiet();
        body = bodyResult.stdout.toString().slice(0, 2000); // Limit body size
      } catch {
        // Use subject as content
      }

      // Check for Solar triggers in subject
      const content = `Subject: ${email.subject}\n\n${body}`;
      const senderStr = email.from.name ? `${email.from.name} <${email.from.addr}>` : email.from.addr;

      // Ingest
      const result = await this.ingester.ingest({
        source: 'gmail',
        sourceId: email.id,
        sender: senderStr,
        content,
        timestamp: new Date(email.date),
        metadata: {
          subject: email.subject,
          flags: email.flags
        }
      });

      if (result.success) {
        console.log(`[Gmail] Ingested: ${email.id} - ${email.subject.slice(0, 50)}`);
      } else if (!result.duplicate) {
        console.error(`[Gmail] Failed: ${result.error}`);
      }

    } catch (error) {
      console.error(`[Gmail] Error processing ${email.id}:`, error);
    }
  }
}

// CLI / standalone mode
if (import.meta.main) {
  const listener = new GmailListener();

  process.on('SIGINT', () => {
    listener.stop();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    listener.stop();
    process.exit(0);
  });

  listener.start().then(() => {
    console.log('[Gmail] Listener started. Press Ctrl+C to stop.');
  });
}
