#!/usr/bin/env bun
/**
 * Solar Security Monitor - 安全预警子系统
 *
 * 监控风险并通过邮件/iMessage 发送预警
 *
 * 风险类型:
 * 1. 非授权访问尝试
 * 2. 配额异常消耗
 * 3. 可疑消息模式
 * 4. 系统异常
 * 5. 外部 API 异常
 */

import Database from 'bun:sqlite';
import { $ } from 'bun';
import { ReplySender } from '../reply/reply-sender';
import { getGuardianImessageHandle, getNotificationEmail } from '../config/privacy';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

// 风险级别
type RiskLevel = 'info' | 'warning' | 'critical' | 'emergency';

// 风险类型
type RiskType =
  | 'unauthorized_access'    // 非授权访问
  | 'quota_anomaly'          // 配额异常
  | 'suspicious_message'     // 可疑消息
  | 'system_error'           // 系统错误
  | 'api_failure'            // API 故障
  | 'rate_limit'             // 频率限制
  | 'data_breach_attempt';   // 数据泄露尝试

// 风险事件
interface SecurityEvent {
  type: RiskType;
  level: RiskLevel;
  source: string;
  description: string;
  details: Record<string, any>;
  timestamp: Date;
}

// 预警配置
interface AlertConfig {
  minLevel: RiskLevel;        // 最低预警级别
  channels: string[];         // 预警通道
  cooldown: number;           // 冷却时间 (秒)
  guardianEmail: string;      // 监护人邮箱
  guardianPhone?: string;     // 监护人电话
}

const DEFAULT_CONFIG: AlertConfig = {
  minLevel: 'warning',
  channels: ['imessage', 'gmail'],
  cooldown: 300,  // 5分钟
  guardianEmail: getNotificationEmail(),
  guardianPhone: getGuardianImessageHandle(),
};

// 风险级别权重
const RISK_WEIGHTS: Record<RiskLevel, number> = {
  info: 1,
  warning: 2,
  critical: 3,
  emergency: 4,
};

/**
 * 安全监控器
 */
export class SecurityMonitor {
  private db: Database;
  private replySender: ReplySender;
  private config: AlertConfig;
  private lastAlerts: Map<string, number> = new Map();  // 用于冷却

  constructor(config?: Partial<AlertConfig>) {
    this.db = new Database(DB_PATH);
    this.replySender = new ReplySender();
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.ensureTables();
  }

  private ensureTables() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sec_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        risk_level TEXT NOT NULL,
        source TEXT,
        description TEXT,
        details TEXT,
        alert_sent INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sec_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER REFERENCES sec_events(id),
        channel TEXT NOT NULL,
        recipient TEXT,
        content TEXT,
        status TEXT DEFAULT 'pending',
        sent_at DATETIME,
        error TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // 风险统计视图
    this.db.exec(`
      CREATE VIEW IF NOT EXISTS v_security_stats AS
      SELECT
        event_type,
        risk_level,
        COUNT(*) as event_count,
        SUM(CASE WHEN alert_sent = 1 THEN 1 ELSE 0 END) as alerts_sent,
        MAX(created_at) as last_occurrence
      FROM sec_events
      WHERE created_at > datetime('now', '-7 days')
      GROUP BY event_type, risk_level
      ORDER BY event_count DESC
    `);
  }

  /**
   * 记录安全事件
   */
  async logEvent(event: SecurityEvent): Promise<number> {
    const result = this.db.prepare(`
      INSERT INTO sec_events (event_type, risk_level, source, description, details)
      VALUES (?, ?, ?, ?, ?)
    `).run(
      event.type,
      event.level,
      event.source,
      event.description,
      JSON.stringify(event.details)
    );

    const eventId = result.lastInsertRowid as number;

    console.log(`[Security] 📝 事件记录: ${event.type} (${event.level})`);

    // 判断是否需要预警
    if (this.shouldAlert(event)) {
      await this.sendAlert(eventId, event);
    }

    return eventId;
  }

  /**
   * 判断是否需要发送预警
   */
  private shouldAlert(event: SecurityEvent): boolean {
    // 检查级别
    if (RISK_WEIGHTS[event.level] < RISK_WEIGHTS[this.config.minLevel]) {
      return false;
    }

    // 检查冷却
    const key = `${event.type}:${event.level}`;
    const lastAlert = this.lastAlerts.get(key);
    if (lastAlert && (Date.now() - lastAlert) < this.config.cooldown * 1000) {
      console.log(`[Security] ⏳ 冷却中，跳过预警: ${key}`);
      return false;
    }

    return true;
  }

  /**
   * 发送预警
   */
  private async sendAlert(eventId: number, event: SecurityEvent): Promise<void> {
    // 更新冷却
    const key = `${event.type}:${event.level}`;
    this.lastAlerts.set(key, Date.now());

    // 生成预警内容
    const alertContent = this.formatAlertContent(event);

    console.log(`[Security] 🚨 发送预警: ${event.type}`);

    // 发送到所有配置的通道
    for (const channel of this.config.channels) {
      try {
        let recipient: string;
        let result: any;

        if (channel === 'gmail') {
          recipient = this.config.guardianEmail;
          result = await this.replySender.send({
            channel: 'gmail',
            recipient,
            replyType: 'notification',
            content: alertContent,
            subject: `⚠️ Solar 安全预警: ${event.type}`,
          });
        } else if (channel === 'imessage' && this.config.guardianPhone) {
          recipient = this.config.guardianPhone;
          result = await this.replySender.send({
            channel: 'imessage',
            recipient,
            replyType: 'notification',
            content: alertContent,
          });
        } else {
          continue;
        }

        // 记录预警
        this.db.prepare(`
          INSERT INTO sec_alerts (event_id, channel, recipient, content, status, sent_at)
          VALUES (?, ?, ?, ?, ?, datetime('now'))
        `).run(eventId, channel, recipient, alertContent, result.success ? 'sent' : 'failed');

        // 更新事件
        this.db.prepare(`UPDATE sec_events SET alert_sent = 1 WHERE id = ?`).run(eventId);

        if (result.success) {
          console.log(`[Security] ✓ 预警已发送到 ${channel}`);
        } else {
          console.error(`[Security] ✗ 预警发送失败: ${result.error}`);
        }
      } catch (e) {
        console.error(`[Security] ✗ 预警发送异常:`, e);
      }
    }
  }

  /**
   * 格式化预警内容
   */
  private formatAlertContent(event: SecurityEvent): string {
    const levelEmoji: Record<RiskLevel, string> = {
      info: 'ℹ️',
      warning: '⚠️',
      critical: '🚨',
      emergency: '🆘',
    };

    return `${levelEmoji[event.level]} Solar 安全预警

类型: ${event.type}
级别: ${event.level.toUpperCase()}
来源: ${event.source}
时间: ${event.timestamp.toLocaleString('zh-CN')}

描述:
${event.description}

详情:
${JSON.stringify(event.details, null, 2)}

---
Solar Security Monitor`;
  }

  // ========== 预定义检测器 ==========

  /**
   * 检测非授权访问
   */
  detectUnauthorizedAccess(sender: string, content: string): SecurityEvent | null {
    // 已在 demo-executor 中实现基本检查
    // 这里添加额外的模式检测

    // 检测可疑模式
    const suspiciousPatterns = [
      /inject|eval|exec|system|shell/i,
      /password|密码|token|key|secret/i,
      /drop\s+table|delete\s+from|truncate/i,
      /<script|javascript:|data:/i,
    ];

    for (const pattern of suspiciousPatterns) {
      if (pattern.test(content)) {
        return {
          type: 'suspicious_message',
          level: 'warning',
          source: sender,
          description: '检测到可疑消息内容',
          details: { pattern: pattern.source, content: content.slice(0, 200) },
          timestamp: new Date(),
        };
      }
    }

    return null;
  }

  /**
   * 检测配额异常
   */
  async detectQuotaAnomaly(): Promise<SecurityEvent | null> {
    // 检查配额使用情况
    const quota = this.db.prepare(`
      SELECT * FROM v_quota_realtime WHERE period_type = 'daily' LIMIT 1
    `).get() as any;

    if (!quota) return null;

    // 检查是否即将超限
    if (quota.status === 'critical') {
      return {
        type: 'quota_anomaly',
        level: 'warning',
        source: 'quota_monitor',
        description: '配额使用接近临界值',
        details: {
          usagePct: quota.usage_pct,
          usedTokens: quota.used_tokens,
          maxTokens: quota.max_tokens,
        },
        timestamp: new Date(),
      };
    }

    if (quota.status === 'exceeded') {
      return {
        type: 'quota_anomaly',
        level: 'critical',
        source: 'quota_monitor',
        description: '配额已超限',
        details: {
          usagePct: quota.usage_pct,
          usedTokens: quota.used_tokens,
          maxTokens: quota.max_tokens,
        },
        timestamp: new Date(),
      };
    }

    // 检查异常消耗速度
    const recentUsage = this.db.prepare(`
      SELECT
        COUNT(*) as task_count,
        SUM(actual_tokens) as total_tokens
      FROM bl_message_tasks
      WHERE created_at > datetime('now', '-1 hour')
        AND status = 'completed'
    `).get() as any;

    if (recentUsage && recentUsage.total_tokens > quota.max_tokens * 0.3) {
      return {
        type: 'quota_anomaly',
        level: 'warning',
        source: 'quota_monitor',
        description: '过去1小时配额消耗异常',
        details: {
          hourlyUsage: recentUsage.total_tokens,
          taskCount: recentUsage.task_count,
          threshold: quota.max_tokens * 0.3,
        },
        timestamp: new Date(),
      };
    }

    return null;
  }

  /**
   * 检测系统健康
   */
  async detectSystemHealth(): Promise<SecurityEvent | null> {
    // 检查数据库大小
    try {
      const dbSize = await $`stat -f%z ${DB_PATH}`.quiet();
      const sizeBytes = parseInt(dbSize.stdout.toString());
      const sizeMB = sizeBytes / 1024 / 1024;

      if (sizeMB > 500) {
        return {
          type: 'system_error',
          level: 'warning',
          source: 'system_monitor',
          description: '数据库文件过大',
          details: { sizeMB: sizeMB.toFixed(2) },
          timestamp: new Date(),
        };
      }
    } catch (e) {
      // 忽略
    }

    // 检查失败任务
    const failedTasks = this.db.prepare(`
      SELECT COUNT(*) as count FROM bl_message_tasks
      WHERE status = 'failed'
        AND created_at > datetime('now', '-1 hour')
    `).get() as any;

    if (failedTasks && failedTasks.count > 10) {
      return {
        type: 'system_error',
        level: 'warning',
        source: 'system_monitor',
        description: '过去1小时失败任务过多',
        details: { failedCount: failedTasks.count },
        timestamp: new Date(),
      };
    }

    return null;
  }

  /**
   * 运行所有检测
   */
  async runAllChecks(): Promise<SecurityEvent[]> {
    const events: SecurityEvent[] = [];

    // 配额检测
    const quotaEvent = await this.detectQuotaAnomaly();
    if (quotaEvent) {
      await this.logEvent(quotaEvent);
      events.push(quotaEvent);
    }

    // 系统健康检测
    const systemEvent = await this.detectSystemHealth();
    if (systemEvent) {
      await this.logEvent(systemEvent);
      events.push(systemEvent);
    }

    return events;
  }

  /**
   * 获取安全统计
   */
  getStats(): any[] {
    return this.db.prepare(`SELECT * FROM v_security_stats`).all();
  }

  close() {
    this.db.close();
  }
}

// CLI 测试
if (import.meta.main) {
  const monitor = new SecurityMonitor({
    minLevel: 'warning',
    guardianEmail: getNotificationEmail(),
  });

  const args = process.argv.slice(2);
  const command = args[0] || 'check';

  switch (command) {
    case 'check':
      console.log('运行安全检测...');
      monitor.runAllChecks().then(events => {
        console.log(`检测到 ${events.length} 个风险事件`);
        events.forEach(e => console.log(`- ${e.type}: ${e.description}`));
        monitor.close();
      });
      break;

    case 'stats':
      console.log('安全统计:');
      console.table(monitor.getStats());
      monitor.close();
      break;

    case 'test':
      console.log('发送测试预警...');
      monitor.logEvent({
        type: 'system_error',
        level: 'warning',
        source: 'test',
        description: '这是一条测试预警',
        details: { test: true },
        timestamp: new Date(),
      }).then(() => {
        console.log('测试预警已发送');
        monitor.close();
      });
      break;

    default:
      console.log('Usage: security-monitor.ts [check|stats|test]');
      monitor.close();
  }
}
