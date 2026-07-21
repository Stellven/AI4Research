#!/usr/bin/env bun
/**
 * Demo Executor - 演示用消息执行器
 * 详细日志输出，方便调试
 */

import Database from 'bun:sqlite';
import { watch } from 'fs';
import { readdir, readFile, unlink, mkdir } from 'fs/promises';
import { join } from 'path';
import { ReplySender, type ReplyType, type Channel } from '../reply/reply-sender';
import { SmartScheduler } from '../executor/smart-scheduler';
import { SecurityMonitor } from '../security/security-monitor';
import { getGuardianEmails, getGuardianImessageHandle, getNotificationEmail } from '../config/privacy';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;
const IMESSAGE_DIR = `${process.env.HOME}/.solar/incoming/imessage`;
const POLL_INTERVAL = 3000; // 3 秒检查一次
const GUARDIAN_EMAILS = getGuardianEmails();
const GUARDIAN_IMESSAGE = getGuardianImessageHandle();

// 🔐 监护人白名单 - 只接受这些发送者的消息
const GUARDIAN_WHITELIST = [
  ...GUARDIAN_EMAILS,
  ...(GUARDIAN_IMESSAGE ? [GUARDIAN_IMESSAGE] : []),
  // 特殊标记
  'test',      // 测试用
];

// 验证是否是监护人
function isGuardian(sender: string): boolean {
  if (!sender) return false;
  const senderLower = sender.toLowerCase();
  return GUARDIAN_WHITELIST.some(pattern => senderLower.includes(pattern.toLowerCase()));
}

// 颜色输出
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  dim: '\x1b[2m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
};

function log(level: string, msg: string, data?: any) {
  const timestamp = new Date().toISOString().split('T')[1].slice(0, 8);
  const levelColors: Record<string, string> = {
    INFO: colors.green,
    WARN: colors.yellow,
    ERROR: colors.red,
    DEBUG: colors.dim,
    TASK: colors.cyan,
    EXEC: colors.magenta,
  };
  const color = levelColors[level] || colors.reset;
  console.log(`${colors.dim}[${timestamp}]${colors.reset} ${color}[${level}]${colors.reset} ${msg}`);
  if (data) {
    console.log(`${colors.dim}           └─${colors.reset}`, JSON.stringify(data, null, 2).split('\n').join('\n              '));
  }
}

// 触发规则 - 模糊匹配，自然语言优先
const TRIGGERS = [
  // P0: 具体可执行任务 (Shortcut) - 最高优先级
  { pattern: /天气|weather|气温|温度|下雨|晴天/i, action: 'solar_get_weather', boost: 25, name: 'Weather', type: 'shortcut', replyType: 'quick_answer' },
  { pattern: /提醒|remind|记得|别忘|待办|todo/i, action: 'solar_set_reminder', boost: 25, name: 'Reminder', type: 'shortcut', replyType: 'notification' },

  // P1: 紧急任务
  { pattern: /紧急|urgent|asap|马上|立刻|急/i, action: '@Coder', boost: 30, name: 'Urgent', type: 'agent', replyType: 'status' },

  // P2: 摘要类 - "总结"、"摘要"、"概括"
  { pattern: /总结|摘要|概括|要点|精华|核心|一句话/i, action: '@Researcher', boost: 20, name: 'Summary', type: 'agent', replyType: 'bullet_summary' },

  // P3: 分析类 - "分析"、"看看"、"了解"、"研究"
  { pattern: /分析|看看|了解|研究|深入|探索|调研/i, action: '@Researcher', boost: 18, name: 'Analyze', type: 'agent', replyType: 'insight' },

  // P4: 对比类 - "对比"、"比较"、"哪个好"
  { pattern: /对比|比较|哪个好|选择|优缺点|利弊/i, action: '@Researcher', boost: 18, name: 'Compare', type: 'agent', replyType: 'comparison' },

  // P5: 报告类 - "报告"、"方案"、"设计"
  { pattern: /报告|方案|设计|规划|计划|文档/i, action: '@Reporter', boost: 15, name: 'Report', type: 'agent', replyType: 'research_report' },

  // P6: 代码审查
  { pattern: /审查|review|检查代码|code review/i, action: '@Reviewer', boost: 15, name: 'Review', type: 'agent', replyType: 'review' },

  // P7: 行动类 - "该做什么"、"下一步"
  { pattern: /该做什么|下一步|行动|怎么办|建议|推荐/i, action: '@Researcher', boost: 12, name: 'Action', type: 'agent', replyType: 'action_items' },

  // P8: 自然语言意图 - "我要"、"我想"、"帮我"
  { pattern: /^(我要|我想|帮我|请|麻烦)/i, action: '@Coder', boost: 10, name: 'Request', type: 'agent', replyType: 'status' },

  // P9: 问答类 - 问号结尾
  { pattern: /[?？]$/i, action: '@Researcher', boost: 8, name: 'Question', type: 'agent', replyType: 'quick_answer' },

  // P10: 通用标签 (最低优先级)
  { pattern: /#solar|@solar/i, action: '@Coder', boost: 5, name: 'Solar Tag', type: 'agent', replyType: 'status' },
];

class DemoExecutor {
  private db: Database;
  private running = false;
  private replySender: ReplySender;
  private scheduler: SmartScheduler;
  private securityMonitor: SecurityMonitor;

  constructor() {
    this.db = new Database(DB_PATH);
    this.replySender = new ReplySender();
    this.scheduler = new SmartScheduler();
    this.securityMonitor = new SecurityMonitor({
      guardianEmail: getNotificationEmail(),
      minLevel: 'warning',
    });
  }

  async start() {
    this.running = true;

    console.log(`
${colors.cyan}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ${colors.bright}☀️  Solar Message Executor - Demo Mode${colors.reset}${colors.cyan}                    ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  监听目录: ~/.solar/incoming/imessage/                       ║
║  数据库:   ~/.solar/db/solar.db                              ║
║  轮询间隔: 3 秒                                              ║
║                                                              ║
║  ${colors.yellow}测试方法:${colors.reset}${colors.cyan}                                                    ║
║  1. 创建 JSON 文件到 incoming/imessage 目录                  ║
║  2. 或运行: bun run message-ingester.ts ingest ...           ║
║                                                              ║
║  ${colors.green}按 Ctrl+C 停止${colors.reset}${colors.cyan}                                              ║
╚══════════════════════════════════════════════════════════════╝
${colors.reset}`);

    // 确保目录存在
    await mkdir(IMESSAGE_DIR, { recursive: true });

    log('INFO', '启动 iMessage 目录监听...');
    log('INFO', '启动任务队列处理循环...');

    // 监听目录
    this.watchDirectory();

    // 处理队列
    this.processLoop();
  }

  private watchDirectory() {
    setInterval(async () => {
      try {
        const files = await readdir(IMESSAGE_DIR);
        const jsonFiles = files.filter(f => f.endsWith('.json'));

        for (const file of jsonFiles) {
          await this.processFile(join(IMESSAGE_DIR, file));
        }
      } catch (e) {
        // 忽略
      }
    }, 2000);
  }

  private async processFile(filepath: string) {
    try {
      const content = await readFile(filepath, 'utf-8');
      const payload = JSON.parse(content);

      log('TASK', `📨 收到新消息`, {
        id: payload.id,
        sender: payload.sender,
        text: payload.text?.slice(0, 50) + '...'
      });

      // 🔐 监护人验证 - 只接受白名单中的发送者
      if (!isGuardian(payload.sender)) {
        log('WARN', `🚫 拒绝非监护人消息`, { sender: payload.sender });

        // 记录安全事件
        await this.securityMonitor.logEvent({
          type: 'unauthorized_access',
          level: 'warning',
          source: payload.sender || 'unknown',
          description: '非授权用户尝试发送消息',
          details: {
            sender: payload.sender,
            contentPreview: payload.text?.slice(0, 100),
          },
          timestamp: new Date(),
        });

        await unlink(filepath);  // 删除文件
        return;
      }
      log('INFO', `✓ 监护人验证通过`);

      // 🛡️ 检测可疑内容
      const suspiciousEvent = this.securityMonitor.detectUnauthorizedAccess(
        payload.sender || 'unknown',
        payload.text || ''
      );
      if (suspiciousEvent) {
        log('WARN', `⚠️ 检测到可疑内容`, { type: suspiciousEvent.type });
        await this.securityMonitor.logEvent(suspiciousEvent);
      }

      // 分析触发器
      const matches = this.analyzeTriggers(payload.text || '');

      if (matches.length > 0) {
        log('INFO', `🎯 触发器匹配:`, matches.map(m => `${m.name} → ${m.action}`));
      }

      // 入队
      const result = this.ingestMessage('imessage', payload.id, payload.text, payload.sender);

      if (result.success) {
        log('TASK', `✓ 已入队 (ID: ${result.taskId}, Priority: ${result.priority})`, {
          intent: result.intent,
          estimatedTokens: result.estimatedTokens
        });
      } else if (result.duplicate) {
        log('WARN', `⚠ 重复消息，已跳过: ${payload.id}`);
      }

      // 删除已处理文件
      await unlink(filepath);

    } catch (e) {
      log('ERROR', `处理文件失败: ${filepath}`, { error: String(e) });
    }
  }

  private analyzeTriggers(content: string): Array<{ name: string; action: string; boost: number }> {
    const matches: Array<{ name: string; action: string; boost: number }> = [];

    for (const trigger of TRIGGERS) {
      if (trigger.pattern.test(content)) {
        matches.push({
          name: trigger.name,
          action: trigger.action,
          boost: trigger.boost
        });
      }
    }

    return matches;
  }

  private ingestMessage(source: string, sourceId: string, content: string, sender?: string): {
    success: boolean;
    duplicate?: boolean;
    taskId?: number;
    priority?: number;
    intent?: string;
    estimatedTokens?: number;
  } {
    // 去重检查
    const existing = this.db.prepare(
      'SELECT id FROM bl_message_tasks WHERE source = ? AND source_id = ?'
    ).get(source, sourceId);

    if (existing) {
      return { success: false, duplicate: true };
    }

    // 分析触发器 - 选择 boost 最高的作为主意图
    const matches = this.analyzeTriggers(content);
    const priorityBoost = matches.reduce((max, m) => Math.max(max, m.boost), 0);
    // 按 boost 降序排序，取最高的
    const sortedMatches = [...matches].sort((a, b) => b.boost - a.boost);
    const intent = sortedMatches.length > 0 ? sortedMatches[0].action : 'general';

    // 计算优先级
    const basePriority = source === 'imessage' ? 60 : source === 'gmail' ? 50 : 40;
    const priority = Math.min(100, basePriority + priorityBoost);

    // 估算 Token
    const estimatedTokens = Math.ceil(content.length / 4) * 5;

    // 插入
    const result = this.db.prepare(`
      INSERT INTO bl_message_tasks (source, source_id, sender, content, parsed_intent, priority, estimated_tokens)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(source, sourceId, sender, content, intent, priority, estimatedTokens);

    return {
      success: true,
      taskId: result.lastInsertRowid as number,
      priority,
      intent,
      estimatedTokens
    };
  }

  private async processLoop() {
    while (this.running) {
      await this.processNextTask();
      await Bun.sleep(POLL_INTERVAL);
    }
  }

  private async processNextTask() {
    // 获取下一个任务
    const task = this.db.prepare(`
      SELECT * FROM bl_message_tasks
      WHERE status IN ('pending', 'queued')
      ORDER BY priority DESC, created_at ASC
      LIMIT 1
    `).get() as any;

    if (!task) {
      return; // 无任务
    }

    // 🧠 智能调度决策
    const scheduleResult = this.scheduler.schedule({
      id: task.id,
      intent: task.parsed_intent,
      content: task.content,
      source: task.source,
      createdAt: new Date(task.created_at),
    });

    log('EXEC', `📊 调度决策`, {
      decision: scheduleResult.decision,
      reason: scheduleResult.reason,
      urgency: scheduleResult.urgency.level,
      estimatedTokens: scheduleResult.taskEstimate.estimatedTotalTokens,
      quotaRemaining: scheduleResult.quotaStatus.remainingTokens,
    });

    // 根据决策执行
    if (scheduleResult.decision === 'reject') {
      log('WARN', `⚠ 任务被拒绝: ${scheduleResult.reason}`);
      this.db.prepare(`
        UPDATE bl_message_tasks SET status = 'rejected', error = ? WHERE id = ?
      `).run(scheduleResult.reason, task.id);
      return;
    }

    if (scheduleResult.decision === 'delay_short' || scheduleResult.decision === 'delay_long') {
      log('INFO', `⏳ 任务延迟: ${scheduleResult.reason}`);
      this.db.prepare(`
        UPDATE bl_message_tasks SET status = 'delayed', error = ? WHERE id = ?
      `).run(scheduleResult.reason, task.id);
      return;
    }

    if (scheduleResult.decision === 'defer_to_reset') {
      log('INFO', `📅 任务推迟到配额重置: ${scheduleResult.reason}`);
      this.db.prepare(`
        UPDATE bl_message_tasks SET status = 'deferred', error = ? WHERE id = ?
      `).run(scheduleResult.reason, task.id);
      return;
    }

    // execute_now - 立即执行
    log('EXEC', `🚀 开始处理任务 #${task.id}`, {
      content: task.content.slice(0, 60) + '...',
      intent: task.parsed_intent,
      priority: task.priority,
      urgency: scheduleResult.urgency.level,
    });

    // 更新状态为处理中
    this.db.prepare(`UPDATE bl_message_tasks SET status = 'processing' WHERE id = ?`).run(task.id);

    try {
      // 分析任务类型
      const intent = task.parsed_intent;
      let result: any;

      if (intent.startsWith('@')) {
        // Agent 任务 - 需要 Claude 会话处理
        log('EXEC', `📋 Agent 任务: ${intent}`, { action: 'queued_for_claude_session' });
        result = { type: 'agent', agent: intent, status: 'queued_for_manual_processing' };
      } else if (intent === 'solar_get_weather') {
        // 天气查询 - 使用内置逻辑
        log('EXEC', `🌤️ 天气查询任务`, { action: 'query_weather' });
        result = await this.executeWeatherQuery(task.content);
      } else if (intent === 'solar_set_reminder') {
        // 提醒设置 - 使用 remindctl
        log('EXEC', `⏰ 提醒设置任务`, { action: 'set_reminder' });
        result = await this.executeReminder(task.content);
      } else if (intent.startsWith('solar_')) {
        // 其他 Shortcut 任务
        log('EXEC', `⚡ Shortcut 任务: ${intent}`, { action: 'execute_shortcut' });
        result = await this.executeShortcut(intent, task.content);
      } else {
        // 通用任务
        log('EXEC', `📝 通用任务`, { action: 'queued_for_manual_processing' });
        result = { type: 'general', status: 'queued_for_manual_processing' };
      }

      // 完成任务
      this.db.prepare(`
        UPDATE bl_message_tasks
        SET status = 'completed', result = ?, actual_tokens = ?
        WHERE id = ?
      `).run(JSON.stringify(result), result.tokensUsed || 0, task.id);

      log('EXEC', `✓ 任务完成 #${task.id}`, result);

      // 📤 原通道回复
      await this.sendReply(task, result);

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';

      // 检查重试
      if (task.retry_count < task.max_retries) {
        this.db.prepare(`
          UPDATE bl_message_tasks
          SET status = 'pending', retry_count = retry_count + 1, error = ?
          WHERE id = ?
        `).run(errorMsg, task.id);
        log('WARN', `⚠ 任务失败，将重试 (${task.retry_count + 1}/${task.max_retries})`, { error: errorMsg });
      } else {
        this.db.prepare(`
          UPDATE bl_message_tasks SET status = 'failed', error = ? WHERE id = ?
        `).run(errorMsg, task.id);
        log('ERROR', `✗ 任务失败 #${task.id}`, { error: errorMsg });
      }
    }
  }

  private async executeShortcut(shortcut: string, content: string): Promise<any> {
    log('EXEC', `执行 Shortcut: ${shortcut}`);

    // 提取参数
    let params = '{}';
    const jsonMatch = content.match(/\{.*\}/s);
    if (jsonMatch) {
      params = jsonMatch[0];
    }

    try {
      const proc = Bun.spawn(['shortcuts', 'run', shortcut, '-i', params], {
        stdout: 'pipe',
        stderr: 'pipe'
      });

      const output = await new Response(proc.stdout).text();
      const exitCode = await proc.exited;

      if (exitCode !== 0) {
        throw new Error(`Shortcut failed with code ${exitCode}`);
      }

      return { type: 'shortcut', shortcut, output: output.slice(0, 200), tokensUsed: 0 };
    } catch (e) {
      return { type: 'shortcut', shortcut, error: String(e), tokensUsed: 0 };
    }
  }

  private async executeWeatherQuery(content: string): Promise<any> {
    log('EXEC', `查询天气...`);

    // 提取城市名 (默认北京)
    let city = '北京';
    // 常见城市列表 - 优先匹配
    const knownCities = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '西安', '南京', '天津',
      '重庆', '苏州', '青岛', '大连', '厦门', '长沙', '沈阳', '哈尔滨', '济南', '郑州', '昆明', '合肥'];

    // 优先匹配已知城市
    for (const c of knownCities) {
      if (content.includes(c)) {
        city = c;
        break;
      }
    }

    // 如果没匹配到已知城市，尝试从 "XX天气" 格式提取 (只取2个字符)
    if (city === '北京') {
      const cityMatch = content.match(/([^\s#@明今后]{2})(?:的)?天气/);
      if (cityMatch && cityMatch[1]) {
        city = cityMatch[1];
      }
    }

    try {
      // 使用 wttr.in 获取天气 (简洁格式，加超时)
      const url = `wttr.in/${encodeURIComponent(city)}?format=%l:+%c+%t+%w+%h`;
      log('DEBUG', `天气 URL: ${url}`);

      const proc = Bun.spawn(['curl', '-s', '--max-time', '10', url], {
        stdout: 'pipe',
        stderr: 'pipe'
      });

      const output = await new Response(proc.stdout).text();
      const exitCode = await proc.exited;

      log('DEBUG', `curl 返回: exitCode=${exitCode}, output=${output.slice(0, 100)}`);

      if (exitCode !== 0 || !output.trim()) {
        throw new Error(`Weather query failed: exitCode=${exitCode}`);
      }

      // 解析输出: "北京: ☀️   +2°C ↗4km/h 41%"
      const parts = output.trim().split(/\s+/);
      const weather = {
        location: city,
        condition: parts[1] || '☀️',
        temperature: parts[2] || 'N/A',
        wind: parts[3] || 'N/A',
        humidity: parts[4] || 'N/A'
      };

      log('EXEC', `🌤️ 天气结果:`, weather);

      return {
        type: 'weather',
        city,
        weather: `${city}: ${weather.condition} ${weather.temperature} 风速${weather.wind} 湿度${weather.humidity}`,
        summary: output.trim(),
        tokensUsed: 0
      };
    } catch (e) {
      log('ERROR', `天气查询失败`, { error: String(e) });
      return { type: 'weather', city, error: String(e), tokensUsed: 0 };
    }
  }

  private async executeReminder(content: string): Promise<any> {
    log('EXEC', `设置提醒...`);

    // 简单解析提醒内容
    const titleMatch = content.match(/提醒[我]?(.+?)(?:在|于|$)/);
    const title = titleMatch ? titleMatch[1].trim() : content.slice(0, 50);

    try {
      // 使用 remindctl 添加提醒
      const proc = Bun.spawn(['remindctl', 'add', title], {
        stdout: 'pipe',
        stderr: 'pipe'
      });

      const output = await new Response(proc.stdout).text();
      const exitCode = await proc.exited;

      if (exitCode !== 0) {
        // 回退到 osascript
        const fallbackProc = Bun.spawn([
          'osascript', '-e',
          `tell application "Reminders" to make new reminder with properties {name:"${title.replace(/"/g, '\\"')}"}`
        ], {
          stdout: 'pipe',
          stderr: 'pipe'
        });

        await fallbackProc.exited;
        log('EXEC', `⏰ 提醒已设置 (via osascript):`, { title });
        return { type: 'reminder', title, method: 'osascript', tokensUsed: 0 };
      }

      log('EXEC', `⏰ 提醒已设置:`, { title, output: output.trim() });
      return { type: 'reminder', title, output: output.trim(), tokensUsed: 0 };
    } catch (e) {
      log('ERROR', `设置提醒失败`, { error: String(e) });
      return { type: 'reminder', title, error: String(e), tokensUsed: 0 };
    }
  }

  /**
   * 发送回复到原通道
   */
  private async sendReply(task: any, result: any): Promise<void> {
    // 确定回复类型
    const trigger = TRIGGERS.find(t => t.action === task.parsed_intent);
    const replyType = (trigger?.replyType || 'status') as ReplyType;

    // 格式化回复内容
    let replyContent: string;

    if (result.type === 'weather') {
      replyContent = result.weather || result.summary;
    } else if (result.type === 'reminder') {
      replyContent = result.error
        ? `❌ 提醒设置失败: ${result.error}`
        : `✓ 已设置提醒: ${result.title}`;
    } else if (result.type === 'agent') {
      replyContent = `📋 任务已收到，将由 ${result.agent} 处理\n\n内容: ${task.content.slice(0, 100)}...`;
    } else if (result.error) {
      replyContent = `❌ 处理失败: ${result.error}`;
    } else {
      replyContent = ReplySender.formatReply(replyType, result);
    }

    // 确定通道和收件人
    const channel = task.source as Channel;
    const recipient = task.sender;

    if (!recipient) {
      log('WARN', '⚠ 无法回复: 缺少发送者信息');
      return;
    }

    log('EXEC', `📤 发送回复`, { channel, recipient: recipient.slice(0, 30), replyType });

    // 发送回复
    const sendResult = await this.replySender.send({
      channel,
      recipient,
      replyType,
      content: replyContent,
      subject: task.source === 'gmail' ? `Re: Solar 回复` : undefined,
    });

    if (sendResult.success) {
      log('INFO', `✓ 回复已发送到 ${channel}`);
    } else {
      log('ERROR', `✗ 回复发送失败`, { error: sendResult.error });
    }
  }

  stop() {
    this.running = false;
    this.db.close();
    log('INFO', '👋 Executor 已停止');
  }
}

// 主入口
const executor = new DemoExecutor();

process.on('SIGINT', () => {
  console.log('\n');
  executor.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  executor.stop();
  process.exit(0);
});

executor.start();
