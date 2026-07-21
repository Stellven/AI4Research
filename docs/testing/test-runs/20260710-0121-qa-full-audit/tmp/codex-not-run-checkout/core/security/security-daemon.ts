#!/usr/bin/env bun
/**
 * Solar Security Daemon - 定时安全守护进程
 *
 * 定时运行安全检测，发现风险立即预警
 *
 * 检测频率:
 * - 高频 (1分钟): 异常访问、API 故障
 * - 中频 (5分钟): 配额监控、任务失败率
 * - 低频 (1小时): 系统健康、日志分析
 * - 每日 (凌晨): 全面安全审计
 */

import Database from 'bun:sqlite';
import { $ } from 'bun';
import { SecurityMonitor } from './security-monitor';
import { getNotificationEmail } from '../config/privacy';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

// 检测间隔配置
const CHECK_INTERVALS = {
  high: 60 * 1000,       // 1 分钟
  medium: 5 * 60 * 1000, // 5 分钟
  low: 60 * 60 * 1000,   // 1 小时
  daily: 24 * 60 * 60 * 1000, // 每日
};

// 颜色输出
const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  dim: '\x1b[2m',
};

function log(level: string, msg: string, data?: any) {
  const timestamp = new Date().toISOString().split('T')[1].slice(0, 8);
  const levelColors: Record<string, string> = {
    INFO: colors.green,
    WARN: colors.yellow,
    ERROR: colors.red,
    SCAN: colors.cyan,
    ALERT: colors.magenta,
  };
  const color = levelColors[level] || colors.reset;
  console.log(`${colors.dim}[${timestamp}]${colors.reset} ${color}[${level}]${colors.reset} ${msg}`);
  if (data) {
    console.log(`${colors.dim}           └─${colors.reset}`, JSON.stringify(data, null, 2).split('\n').join('\n              '));
  }
}

/**
 * 安全守护进程
 */
class SecurityDaemon {
  private db: Database;
  private monitor: SecurityMonitor;
  private running = false;
  private timers: Timer[] = [];

  constructor() {
    this.db = new Database(DB_PATH);
    this.monitor = new SecurityMonitor({
      guardianEmail: getNotificationEmail(),
      minLevel: 'warning',
    });
    this.ensureTables();
  }

  private ensureTables() {
    // 安全扫描日志
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sec_scan_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_type TEXT NOT NULL,
        frequency TEXT NOT NULL,
        events_found INTEGER DEFAULT 0,
        alerts_sent INTEGER DEFAULT 0,
        duration_ms INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // 访问频率追踪
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sec_access_rate (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        source TEXT,
        access_count INTEGER DEFAULT 1,
        window_start DATETIME DEFAULT CURRENT_TIMESTAMP,
        window_end DATETIME
      )
    `);
  }

  async start() {
    this.running = true;

    console.log(`
${colors.cyan}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ${colors.magenta}🛡️  Solar Security Daemon${colors.reset}${colors.cyan}                                ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  检测频率:                                                   ║
║  • 高频 (1分钟):  异常访问、API 故障                         ║
║  • 中频 (5分钟):  配额监控、任务失败率                       ║
║  • 低频 (1小时):  系统健康、日志分析                         ║
║  • 每日 (凌晨):   全面安全审计                               ║
║                                                              ║
║  ${colors.green}按 Ctrl+C 停止${colors.reset}${colors.cyan}                                              ║
╚══════════════════════════════════════════════════════════════╝
${colors.reset}`);

    log('INFO', '启动安全守护进程...');

    // 立即运行一次全面检测
    await this.runFullScan();

    // 设置定时检测
    this.scheduleHighFrequencyChecks();
    this.scheduleMediumFrequencyChecks();
    this.scheduleLowFrequencyChecks();
    this.scheduleDailyAudit();

    log('INFO', '所有定时检测已启动');
  }

  /**
   * 高频检测 (1分钟)
   */
  private scheduleHighFrequencyChecks() {
    const timer = setInterval(async () => {
      if (!this.running) return;

      const startTime = Date.now();
      let eventsFound = 0;
      let alertsSent = 0;

      try {
        // 1. 检测异常访问频率
        const rateEvent = await this.checkAccessRate();
        if (rateEvent) {
          await this.monitor.logEvent(rateEvent);
          eventsFound++;
          alertsSent++;
        }

        // 2. 检测 API 故障
        const apiEvent = await this.checkApiHealth();
        if (apiEvent) {
          await this.monitor.logEvent(apiEvent);
          eventsFound++;
          alertsSent++;
        }

        // 记录扫描日志
        this.logScan('access_rate_api', 'high', eventsFound, alertsSent, Date.now() - startTime);

        if (eventsFound > 0) {
          log('SCAN', `高频检测完成`, { eventsFound, alertsSent });
        }
      } catch (e) {
        log('ERROR', `高频检测失败`, { error: String(e) });
      }
    }, CHECK_INTERVALS.high);

    this.timers.push(timer);
    log('INFO', '高频检测已启动 (间隔: 1分钟)');
  }

  /**
   * 中频检测 (5分钟)
   */
  private scheduleMediumFrequencyChecks() {
    const timer = setInterval(async () => {
      if (!this.running) return;

      const startTime = Date.now();
      let eventsFound = 0;
      let alertsSent = 0;

      try {
        // 1. 配额监控
        const quotaEvent = await this.monitor.detectQuotaAnomaly();
        if (quotaEvent) {
          await this.monitor.logEvent(quotaEvent);
          eventsFound++;
          alertsSent++;
        }

        // 2. 任务失败率
        const failureEvent = await this.checkTaskFailureRate();
        if (failureEvent) {
          await this.monitor.logEvent(failureEvent);
          eventsFound++;
          alertsSent++;
        }

        // 3. 消息队列积压
        const backlogEvent = await this.checkMessageBacklog();
        if (backlogEvent) {
          await this.monitor.logEvent(backlogEvent);
          eventsFound++;
          alertsSent++;
        }

        this.logScan('quota_failure_backlog', 'medium', eventsFound, alertsSent, Date.now() - startTime);

        if (eventsFound > 0) {
          log('SCAN', `中频检测完成`, { eventsFound, alertsSent });
        }
      } catch (e) {
        log('ERROR', `中频检测失败`, { error: String(e) });
      }
    }, CHECK_INTERVALS.medium);

    this.timers.push(timer);
    log('INFO', '中频检测已启动 (间隔: 5分钟)');
  }

  /**
   * 低频检测 (1小时)
   */
  private scheduleLowFrequencyChecks() {
    const timer = setInterval(async () => {
      if (!this.running) return;

      const startTime = Date.now();
      let eventsFound = 0;
      let alertsSent = 0;

      try {
        // 1. 系统健康
        const systemEvent = await this.monitor.detectSystemHealth();
        if (systemEvent) {
          await this.monitor.logEvent(systemEvent);
          eventsFound++;
          alertsSent++;
        }

        // 2. 磁盘空间
        const diskEvent = await this.checkDiskSpace();
        if (diskEvent) {
          await this.monitor.logEvent(diskEvent);
          eventsFound++;
          alertsSent++;
        }

        // 3. 安全事件趋势
        const trendEvent = await this.analyzeSecurityTrends();
        if (trendEvent) {
          await this.monitor.logEvent(trendEvent);
          eventsFound++;
          alertsSent++;
        }

        this.logScan('system_disk_trends', 'low', eventsFound, alertsSent, Date.now() - startTime);

        log('SCAN', `低频检测完成`, { eventsFound, alertsSent });
      } catch (e) {
        log('ERROR', `低频检测失败`, { error: String(e) });
      }
    }, CHECK_INTERVALS.low);

    this.timers.push(timer);
    log('INFO', '低频检测已启动 (间隔: 1小时)');
  }

  /**
   * 每日审计 (凌晨3点)
   */
  private scheduleDailyAudit() {
    // 计算到下一个凌晨3点的时间
    const now = new Date();
    const next3am = new Date(now);
    next3am.setHours(3, 0, 0, 0);
    if (next3am <= now) {
      next3am.setDate(next3am.getDate() + 1);
    }
    const msUntil3am = next3am.getTime() - now.getTime();

    // 首次延迟到凌晨3点
    setTimeout(() => {
      this.runDailyAudit();
      // 之后每24小时运行一次
      const timer = setInterval(() => {
        if (this.running) {
          this.runDailyAudit();
        }
      }, CHECK_INTERVALS.daily);
      this.timers.push(timer);
    }, msUntil3am);

    log('INFO', `每日审计已安排 (下次运行: ${next3am.toLocaleString('zh-CN')})`);
  }

  /**
   * 运行每日审计
   */
  private async runDailyAudit() {
    log('SCAN', '开始每日安全审计...');
    const startTime = Date.now();
    let eventsFound = 0;

    try {
      // 1. 汇总昨日安全事件
      const yesterdayStats = this.db.prepare(`
        SELECT
          event_type,
          risk_level,
          COUNT(*) as count
        FROM sec_events
        WHERE created_at > datetime('now', '-1 day')
        GROUP BY event_type, risk_level
        ORDER BY count DESC
      `).all() as any[];

      // 2. 检测异常模式
      const anomalies = this.db.prepare(`
        SELECT
          source,
          COUNT(*) as attempt_count
        FROM sec_events
        WHERE event_type = 'unauthorized_access'
          AND created_at > datetime('now', '-1 day')
        GROUP BY source
        HAVING COUNT(*) >= 5
      `).all() as any[];

      if (anomalies.length > 0) {
        await this.monitor.logEvent({
          type: 'unauthorized_access',
          level: 'warning',
          source: 'daily_audit',
          description: `发现 ${anomalies.length} 个来源有多次未授权访问`,
          details: { anomalies },
          timestamp: new Date(),
        });
        eventsFound++;
      }

      // 3. 生成每日安全报告
      if (yesterdayStats.length > 0) {
        log('ALERT', '每日安全摘要', {
          totalEvents: yesterdayStats.reduce((sum, s) => sum + s.count, 0),
          byType: yesterdayStats,
        });
      }

      this.logScan('daily_audit', 'daily', eventsFound, eventsFound > 0 ? 1 : 0, Date.now() - startTime);

      log('SCAN', '每日安全审计完成');
    } catch (e) {
      log('ERROR', '每日审计失败', { error: String(e) });
    }
  }

  /**
   * 立即运行全面扫描
   */
  async runFullScan() {
    log('SCAN', '运行全面安全扫描...');
    const events = await this.monitor.runAllChecks();
    log('SCAN', `全面扫描完成`, { eventsFound: events.length });
    return events;
  }

  // ========== 具体检测方法 ==========

  /**
   * 检测访问频率异常
   */
  private async checkAccessRate(): Promise<any> {
    // 检查过去5分钟内是否有异常高频访问
    const rate = this.db.prepare(`
      SELECT
        sender,
        COUNT(*) as access_count
      FROM bl_message_tasks
      WHERE created_at > datetime('now', '-5 minutes')
      GROUP BY sender
      HAVING COUNT(*) > 20
    `).get() as any;

    if (rate) {
      return {
        type: 'rate_limit',
        level: 'warning',
        source: rate.sender,
        description: `异常访问频率: ${rate.access_count} 次/5分钟`,
        details: rate,
        timestamp: new Date(),
      };
    }

    return null;
  }

  /**
   * 检测 API 健康状态
   */
  private async checkApiHealth(): Promise<any> {
    // 检查最近的 API 调用是否有大量失败
    const failures = this.db.prepare(`
      SELECT COUNT(*) as count
      FROM bl_message_tasks
      WHERE status = 'failed'
        AND error LIKE '%API%'
        AND created_at > datetime('now', '-5 minutes')
    `).get() as any;

    if (failures && failures.count > 5) {
      return {
        type: 'api_failure',
        level: 'warning',
        source: 'api_monitor',
        description: `API 失败率异常: ${failures.count} 次/5分钟`,
        details: { failureCount: failures.count },
        timestamp: new Date(),
      };
    }

    return null;
  }

  /**
   * 检测任务失败率
   */
  private async checkTaskFailureRate(): Promise<any> {
    const stats = this.db.prepare(`
      SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
      FROM bl_message_tasks
      WHERE created_at > datetime('now', '-1 hour')
    `).get() as any;

    if (stats && stats.total > 0) {
      const failureRate = stats.failed / stats.total;
      if (failureRate > 0.3) {
        return {
          type: 'system_error',
          level: 'warning',
          source: 'task_monitor',
          description: `任务失败率过高: ${(failureRate * 100).toFixed(1)}%`,
          details: { total: stats.total, failed: stats.failed, rate: failureRate },
          timestamp: new Date(),
        };
      }
    }

    return null;
  }

  /**
   * 检测消息队列积压
   */
  private async checkMessageBacklog(): Promise<any> {
    const backlog = this.db.prepare(`
      SELECT COUNT(*) as count
      FROM bl_message_tasks
      WHERE status IN ('pending', 'queued')
    `).get() as any;

    if (backlog && backlog.count > 50) {
      return {
        type: 'system_error',
        level: 'warning',
        source: 'queue_monitor',
        description: `消息队列积压: ${backlog.count} 条待处理`,
        details: { pendingCount: backlog.count },
        timestamp: new Date(),
      };
    }

    return null;
  }

  /**
   * 检测磁盘空间
   */
  private async checkDiskSpace(): Promise<any> {
    try {
      const result = await $`df -h ~/.solar | tail -1 | awk '{print $5}'`.quiet();
      const usageStr = result.stdout.toString().trim().replace('%', '');
      const usage = parseInt(usageStr);

      if (usage > 90) {
        return {
          type: 'system_error',
          level: 'critical',
          source: 'disk_monitor',
          description: `磁盘空间不足: ${usage}% 已使用`,
          details: { usagePct: usage },
          timestamp: new Date(),
        };
      } else if (usage > 80) {
        return {
          type: 'system_error',
          level: 'warning',
          source: 'disk_monitor',
          description: `磁盘空间警告: ${usage}% 已使用`,
          details: { usagePct: usage },
          timestamp: new Date(),
        };
      }
    } catch (e) {
      // 忽略
    }

    return null;
  }

  /**
   * 分析安全趋势
   */
  private async analyzeSecurityTrends(): Promise<any> {
    // 比较本周和上周的安全事件
    const thisWeek = this.db.prepare(`
      SELECT COUNT(*) as count
      FROM sec_events
      WHERE created_at > datetime('now', '-7 days')
    `).get() as any;

    const lastWeek = this.db.prepare(`
      SELECT COUNT(*) as count
      FROM sec_events
      WHERE created_at > datetime('now', '-14 days')
        AND created_at <= datetime('now', '-7 days')
    `).get() as any;

    if (thisWeek && lastWeek && lastWeek.count > 0) {
      const increase = (thisWeek.count - lastWeek.count) / lastWeek.count;
      if (increase > 0.5) {
        return {
          type: 'system_error',
          level: 'warning',
          source: 'trend_analyzer',
          description: `安全事件增加 ${(increase * 100).toFixed(0)}% (本周 vs 上周)`,
          details: {
            thisWeek: thisWeek.count,
            lastWeek: lastWeek.count,
            increase: `${(increase * 100).toFixed(0)}%`,
          },
          timestamp: new Date(),
        };
      }
    }

    return null;
  }

  /**
   * 记录扫描日志
   */
  private logScan(scanType: string, frequency: string, eventsFound: number, alertsSent: number, durationMs: number) {
    this.db.prepare(`
      INSERT INTO sec_scan_log (scan_type, frequency, events_found, alerts_sent, duration_ms)
      VALUES (?, ?, ?, ?, ?)
    `).run(scanType, frequency, eventsFound, alertsSent, durationMs);
  }

  stop() {
    this.running = false;
    this.timers.forEach(timer => clearInterval(timer));
    this.timers = [];
    this.monitor.close();
    this.db.close();
    log('INFO', '👋 安全守护进程已停止');
  }
}

// 主入口
if (import.meta.main) {
  const daemon = new SecurityDaemon();

  process.on('SIGINT', () => {
    console.log('\n');
    daemon.stop();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    daemon.stop();
    process.exit(0);
  });

  daemon.start();
}

export { SecurityDaemon };
