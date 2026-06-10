/**
 * Solar Resource Selector
 * 资源选择引擎：本地优先 → 远程 → 发现 → LLM (最后手段)
 *
 * 核心原则：系统资源优先，LLM 是最后手段
 */

import Database from 'bun:sqlite';
import { discoverResources } from './discover-remote';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

//------------------------------------------------------------------------------
// 类型定义
//------------------------------------------------------------------------------

export interface Resource {
  resourceId: string;
  layer: 'local' | 'remote' | 'discovered';
  category: string;
  name: string;
  description: string;
  executor: string;
  commandTemplate: string;
  costType: string;
  costPerCall: number;
  latencyMs: number;
  availability: string;
  // 评分相关
  weight?: number;
  rankTier?: string;
  successRate?: number;
  totalCalls?: number;
}

export interface SelectionResult {
  found: boolean;
  resource?: Resource;
  alternatives: Resource[];
  searchedLayers: string[];
  shouldDiscover: boolean;
  fallbackToLLM: boolean;
  reason: string;
}

export interface ExecutionResult {
  success: boolean;
  output?: string;
  error?: string;
  latencyMs: number;
  costActual: number;
}

//------------------------------------------------------------------------------
// 关键词匹配
//------------------------------------------------------------------------------

const INTENT_KEYWORDS: Record<string, string[]> = {
  weather: ['天气', 'weather', '气温', '温度', '下雨', '晴天', '预报'],
  reminder: ['提醒', 'remind', '待办', 'todo', '记得', '别忘'],
  email: ['邮件', 'email', 'mail', '发送', 'send'],
  message: ['消息', 'message', '短信', 'imessage', 'sms'],
  calendar: ['日历', 'calendar', '日程', '事件', 'event'],
  note: ['笔记', 'note', '备忘', '记录'],
  search: ['搜索', 'search', '查找', 'find', '查询'],
  translate: ['翻译', 'translate', '英文', '中文'],
  calculate: ['计算', 'calculate', '算', '多少'],
  convert: ['转换', 'convert', '格式'],
  news: ['新闻', 'news', '资讯', 'hn', 'hackernews'],
  stock: ['股票', 'stock', '股价', '行情'],
  currency: ['汇率', 'currency', 'exchange', '货币'],
};

function extractIntent(text: string): string[] {
  const intents: string[] = [];
  const textLower = text.toLowerCase();

  for (const [intent, keywords] of Object.entries(INTENT_KEYWORDS)) {
    if (keywords.some(kw => textLower.includes(kw.toLowerCase()))) {
      intents.push(intent);
    }
  }

  return intents;
}

//------------------------------------------------------------------------------
// 资源选择器
//------------------------------------------------------------------------------

export class ResourceSelector {
  private db: Database;

  constructor() {
    this.db = new Database(DB_PATH);
  }

  /**
   * 选择最佳资源
   * 遵循原则：本地 → 远程 → 发现 → LLM
   */
  async select(intent: string): Promise<SelectionResult> {
    const searchedLayers: string[] = [];
    const alternatives: Resource[] = [];
    const intents = extractIntent(intent);

    console.log(`🎯 选择资源: "${intent}"`);
    console.log(`   意图: ${intents.join(', ') || '未识别'}`);

    // Step 1: 搜索本地资源
    searchedLayers.push('local');
    const localResources = this.searchResources('local', intent, intents);

    if (localResources.length > 0) {
      console.log(`   ✓ 本地命中: ${localResources[0].name}`);
      return {
        found: true,
        resource: localResources[0],
        alternatives: localResources.slice(1),
        searchedLayers,
        shouldDiscover: false,
        fallbackToLLM: false,
        reason: `本地资源: ${localResources[0].name}`,
      };
    }

    // Step 2: 搜索远程资源
    searchedLayers.push('remote');
    const remoteResources = this.searchResources('remote', intent, intents);

    if (remoteResources.length > 0) {
      console.log(`   ✓ 远程命中: ${remoteResources[0].name}`);
      return {
        found: true,
        resource: remoteResources[0],
        alternatives: remoteResources.slice(1),
        searchedLayers,
        shouldDiscover: false,
        fallbackToLLM: false,
        reason: `远程资源: ${remoteResources[0].name}`,
      };
    }

    // Step 3: 搜索已发现但未采纳的资源
    searchedLayers.push('discovered');
    const discoveredResources = this.searchDiscoveries(intent);

    if (discoveredResources.length > 0) {
      console.log(`   ⚡ 有已发现资源: ${discoveredResources[0].name}`);
      // 建议采纳
      return {
        found: false,
        alternatives: [],
        searchedLayers,
        shouldDiscover: true,
        fallbackToLLM: true,
        reason: `有已发现资源可采纳: ${discoveredResources[0].name}`,
      };
    }

    // Step 4: 触发在线搜索发现
    console.log(`   🔍 触发远程搜索...`);
    const newDiscoveries = await discoverResources(intent, { maxResults: 5 });

    if (newDiscoveries.length > 0) {
      console.log(`   ⚡ 发现新资源: ${newDiscoveries[0].name}`);
      return {
        found: false,
        alternatives: [],
        searchedLayers,
        shouldDiscover: true,
        fallbackToLLM: true,
        reason: `新发现资源: ${newDiscoveries[0].name}，建议评估采纳`,
      };
    }

    // Step 5: 无资源，回退到 LLM
    console.log(`   ⚠️ 无匹配资源，回退到 LLM`);
    this.logSearchMiss(intent);

    return {
      found: false,
      alternatives: [],
      searchedLayers,
      shouldDiscover: false,
      fallbackToLLM: true,
      reason: '无匹配资源，使用 LLM 处理',
    };
  }

  /**
   * 搜索资源 (带权重排序)
   * 优先选择: 权重高 + 成功率高 + 延迟低 + 成本低
   */
  private searchResources(layer: string, intent: string, intents: string[]): Resource[] {
    // 构建关键词搜索条件
    const keywordConditions = intents.map(i => `r.keywords LIKE '%${i}%'`).join(' OR ');
    const nameCondition = `r.name LIKE '%${intent}%' OR r.description LIKE '%${intent}%'`;

    const sql = `
      SELECT
        r.resource_id as resourceId,
        r.layer,
        r.resource_type as category,
        r.name,
        r.description,
        r.executor,
        r.command_template as commandTemplate,
        r.cost_type as costType,
        r.cost_per_call as costPerCall,
        r.latency_ms as latencyMs,
        r.availability,
        -- 评分数据
        COALESCE(s.weight, 1.0) as weight,
        COALESCE(s.rank_tier, 'B') as rankTier,
        COALESCE(s.success_rate, 1.0) as successRate,
        COALESCE(s.total_calls, 0) as totalCalls
      FROM sys_resources r
      LEFT JOIN sys_resource_scores s ON r.resource_id = s.resource_id
      WHERE r.layer = ?
        AND r.availability = 'available'
        AND r.status = 'active'
        AND (${keywordConditions || '1=0'} OR ${nameCondition})
      ORDER BY
        -- 综合排序: 权重×0.4 + 成功率×0.3 + 速度分×0.2 + 成本分×0.1
        (
          COALESCE(s.weight, 1.0) * 0.4 +
          COALESCE(s.success_rate, 1.0) * 0.3 +
          (1.0 / (1 + r.latency_ms / 1000.0)) * 0.2 +
          CASE r.cost_type WHEN 'free' THEN 1.0 ELSE 0.5 END * 0.1
        ) DESC,
        r.cost_per_call ASC
      LIMIT 5
    `;

    return this.db.query(sql).all(layer) as Resource[];
  }

  /**
   * 搜索已发现资源
   */
  private searchDiscoveries(intent: string): any[] {
    return this.db.query(`
      SELECT * FROM sys_resource_discoveries
      WHERE status = 'discovered'
        AND (name LIKE ? OR description LIKE ?)
      ORDER BY relevance_score DESC
      LIMIT 5
    `).all(`%${intent}%`, `%${intent}%`) as any[];
  }

  /**
   * 记录搜索未命中
   */
  private logSearchMiss(intent: string): void {
    this.db.run(`
      INSERT INTO sys_resource_search_log (user_intent, action_taken)
      VALUES (?, 'no_match')
    `, [intent]);
  }

  /**
   * 执行资源
   */
  async execute(resource: Resource, params: Record<string, string>): Promise<ExecutionResult> {
    const startTime = Date.now();

    try {
      let output: string;

      switch (resource.executor) {
        case 'shell':
          output = await this.executeShell(resource.commandTemplate, params);
          break;
        case 'shortcut':
          output = await this.executeShortcut(resource.name, params);
          break;
        case 'mcp':
          output = `[MCP] ${resource.name} - 需要 MCP 客户端执行`;
          break;
        default:
          output = `[Unknown executor] ${resource.executor}`;
      }

      const latencyMs = Date.now() - startTime;

      // 记录使用
      this.logUsage(resource.resourceId, true, latencyMs, resource.costPerCall, params);

      return {
        success: true,
        output,
        latencyMs,
        costActual: resource.costPerCall,
      };
    } catch (error: any) {
      const latencyMs = Date.now() - startTime;

      // 记录失败
      this.logUsage(resource.resourceId, false, latencyMs, 0, params, error.message);

      return {
        success: false,
        error: error.message,
        latencyMs,
        costActual: 0,
      };
    }
  }

  /**
   * 执行 Shell 命令
   */
  private async executeShell(template: string, params: Record<string, string>): Promise<string> {
    let command = template;

    // 替换参数
    for (const [key, value] of Object.entries(params)) {
      command = command.replace(new RegExp(`\\$${key}`, 'gi'), value);
    }

    const proc = Bun.spawn(['bash', '-c', command], {
      stdout: 'pipe',
      stderr: 'pipe',
    });

    const output = await new Response(proc.stdout).text();
    const exitCode = await proc.exited;

    if (exitCode !== 0) {
      const stderr = await new Response(proc.stderr).text();
      throw new Error(stderr || `Exit code: ${exitCode}`);
    }

    return output.trim();
  }

  /**
   * 执行 Shortcut
   */
  private async executeShortcut(name: string, params: Record<string, string>): Promise<string> {
    const input = JSON.stringify(params);
    const proc = Bun.spawn(['shortcuts', 'run', name], {
      stdin: new Response(input),
      stdout: 'pipe',
      stderr: 'pipe',
    });

    const output = await new Response(proc.stdout).text();
    return output.trim() || 'Shortcut executed';
  }

  /**
   * 记录使用并更新评分
   */
  private logUsage(
    resourceId: string,
    success: boolean,
    latencyMs: number,
    costActual: number,
    params: Record<string, string>,
    error?: string
  ): void {
    // 1. 记录使用日志
    this.db.run(`
      INSERT INTO sys_resource_usage (
        resource_id, success, latency_ms, cost_actual,
        input_summary, error
      ) VALUES (?, ?, ?, ?, ?, ?)
    `, [
      resourceId,
      success ? 1 : 0,
      latencyMs,
      costActual,
      JSON.stringify(params).slice(0, 200),
      error || null,
    ]);

    // 2. 增量更新评分 (高效: 不用重算全部)
    this.db.run(`
      INSERT INTO sys_resource_scores (
        resource_id, total_calls, success_count, failure_count,
        success_rate, avg_latency_ms, weight, last_calculated
      ) VALUES (?, 1, ?, ?, ?, ?, 1.0, datetime('now'))
      ON CONFLICT(resource_id) DO UPDATE SET
        total_calls = total_calls + 1,
        success_count = success_count + ?,
        failure_count = failure_count + ?,
        -- 滚动平均成功率
        success_rate = (success_rate * total_calls + ?) / (total_calls + 1),
        -- 滚动平均延迟
        avg_latency_ms = (avg_latency_ms * total_calls + ?) / (total_calls + 1),
        -- 动态调整权重: 成功+0.01, 失败-0.05 (惩罚更重)
        weight = MAX(0.2, MIN(2.0, weight + CASE WHEN ? THEN 0.01 ELSE -0.05 END)),
        last_calculated = datetime('now')
    `, [
      resourceId,
      success ? 1 : 0,
      success ? 0 : 1,
      success ? 1.0 : 0.0,
      latencyMs,
      success ? 1 : 0,
      success ? 0 : 1,
      success ? 1.0 : 0.0,
      latencyMs,
      success ? 1 : 0,
    ]);

    // 3. 失败时记录详情供分析
    if (!success && error) {
      console.log(`   ⚠️ 资源执行失败: ${resourceId}`);
      console.log(`      错误: ${error.slice(0, 100)}`);
    }
  }

  /**
   * 获取资源统计 (含评分排行)
   */
  getStats(): any {
    // 资源分布
    const stats = this.db.query(`
      SELECT
        layer,
        resource_type as category,
        COUNT(*) as count,
        SUM(CASE WHEN availability = 'available' THEN 1 ELSE 0 END) as available
      FROM sys_resources
      GROUP BY layer, resource_type
      ORDER BY layer, count DESC
    `).all();

    // 评级分布
    const tiers = this.db.query(`
      SELECT rank_tier, COUNT(*) as count
      FROM sys_resource_scores
      GROUP BY rank_tier
      ORDER BY rank_tier
    `).all();

    // Top 10 资源
    const topResources = this.db.query(`
      SELECT
        r.name,
        s.rank_tier as tier,
        ROUND(s.success_rate * 100, 1) as success_pct,
        s.total_calls as calls,
        ROUND(s.weight, 2) as weight,
        s.trend
      FROM sys_resource_scores s
      JOIN sys_resources r ON s.resource_id = r.resource_id
      WHERE s.total_calls > 0
      ORDER BY s.weight DESC, s.success_rate DESC
      LIMIT 10
    `).all();

    // 下降趋势的资源 (需关注)
    const degrading = this.db.query(`
      SELECT r.name, s.success_rate, s.recent_success_rate, s.total_calls
      FROM sys_resource_scores s
      JOIN sys_resources r ON s.resource_id = r.resource_id
      WHERE s.trend = 'degrading'
    `).all();

    // 能力缺口
    const gaps = this.db.query(`
      SELECT user_intent, request_count
      FROM v_capability_gaps
      LIMIT 5
    `).all();

    return { stats, tiers, topResources, degrading, gaps };
  }

  close(): void {
    this.db.close();
  }
}

//------------------------------------------------------------------------------
// CLI
//------------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  const selector = new ResourceSelector();

  try {
    switch (command) {
      case 'select':
        const intent = args.slice(1).join(' ');
        if (!intent) {
          console.log('Usage: resource-selector.ts select <intent>');
          process.exit(1);
        }
        const result = await selector.select(intent);
        console.log('\n📋 选择结果:');
        console.log(JSON.stringify(result, null, 2));
        break;

      case 'execute':
        const resourceId = args[1];
        const paramsJson = args[2] || '{}';
        if (!resourceId) {
          console.log('Usage: resource-selector.ts execute <resource_id> [params_json]');
          process.exit(1);
        }
        // 先查询资源
        const db = new Database(DB_PATH);
        const resource = db.query(`SELECT * FROM sys_resources WHERE resource_id = ?`).get(resourceId) as any;
        db.close();

        if (!resource) {
          console.log('Resource not found:', resourceId);
          process.exit(1);
        }

        const execResult = await selector.execute(
          {
            resourceId: resource.resource_id,
            layer: resource.layer,
            category: resource.category,
            name: resource.name,
            description: resource.description,
            executor: resource.executor,
            commandTemplate: resource.command_template,
            costType: resource.cost_type,
            costPerCall: resource.cost_per_call,
            latencyMs: resource.latency_ms,
            availability: resource.availability,
          },
          JSON.parse(paramsJson)
        );
        console.log('\n⚡ 执行结果:');
        console.log(JSON.stringify(execResult, null, 2));
        break;

      case 'stats':
        const stats = selector.getStats();
        console.log('\n📊 资源统计:');
        console.table(stats.stats);
        console.log('\n🔍 能力缺口:');
        console.table(stats.gaps);
        break;

      default:
        console.log('Solar Resource Selector');
        console.log('');
        console.log('Commands:');
        console.log('  select <intent>                    选择资源');
        console.log('  execute <resource_id> [params]     执行资源');
        console.log('  stats                              查看统计');
    }
  } finally {
    selector.close();
  }
}

main().catch(console.error);
