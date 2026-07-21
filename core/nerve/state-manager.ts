/**
 * Solar Core - State Manager
 * 神经系统状态管理器 - 基于 SQLite 的 KV 存储
 */

import { Database } from "bun:sqlite";
import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";

export interface StateManagerConfig {
  dbPath: string;
  autoInit?: boolean;
}

type StateListener = (key: string, value: any, oldValue: any) => void;

export class StateManager {
  private db: Database;
  private cache: Map<string, any> = new Map();
  private listeners: Map<string, Set<StateListener>> = new Map();
  private globalListeners: Set<StateListener> = new Set();

  constructor(config: StateManagerConfig) {
    const { dbPath, autoInit = true } = config;

    // 确保目录存在
    const dir = dirname(dbPath);
    if (!existsSync(dir)) {
      Bun.spawnSync(["mkdir", "-p", dir]);
    }

    // 打开数据库
    this.db = new Database(dbPath);
    this.db.exec("PRAGMA journal_mode = WAL");
    this.db.exec("PRAGMA synchronous = NORMAL");

    // 自动初始化
    if (autoInit) {
      this.initSchema();
    }

    // 加载缓存
    this.loadCache();
  }

  /**
   * 初始化数据库 Schema
   */
  private initSchema() {
    const schemaPath = join(dirname(import.meta.path), "schema.sql");
    if (existsSync(schemaPath)) {
      const schema = readFileSync(schemaPath, "utf-8");
      this.db.exec(schema);
    }
  }

  /**
   * 加载所有状态到缓存
   */
  private loadCache() {
    const rows = this.db.query("SELECT key, value FROM state").all() as Array<{
      key: string;
      value: string;
    }>;
    for (const row of rows) {
      try {
        this.cache.set(row.key, JSON.parse(row.value));
      } catch {
        this.cache.set(row.key, row.value);
      }
    }
  }

  // ==================== 基础 CRUD ====================

  /**
   * 获取状态值
   */
  get<T = any>(key: string, defaultValue?: T): T | undefined {
    if (this.cache.has(key)) {
      return this.cache.get(key) as T;
    }
    return defaultValue;
  }

  /**
   * 设置状态值
   */
  set(key: string, value: any): void {
    const oldValue = this.cache.get(key);
    this.cache.set(key, value);

    this.db.run(
      `
      INSERT INTO state (key, value, updated_at)
      VALUES (?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(key) DO UPDATE SET
        value = excluded.value,
        updated_at = CURRENT_TIMESTAMP
    `,
      [key, JSON.stringify(value)],
    );

    // 通知监听器
    this.notifyListeners(key, value, oldValue);
  }

  /**
   * 删除状态
   */
  delete(key: string): boolean {
    const existed = this.cache.has(key);
    if (existed) {
      const oldValue = this.cache.get(key);
      this.cache.delete(key);
      this.db.run("DELETE FROM state WHERE key = ?", [key]);
      this.notifyListeners(key, undefined, oldValue);
    }
    return existed;
  }

  /**
   * 检查是否存在
   */
  has(key: string): boolean {
    return this.cache.has(key);
  }

  // ==================== 批量操作 ====================

  /**
   * 批量获取 (按前缀)
   */
  getByPrefix(prefix: string): Record<string, any> {
    const result: Record<string, any> = {};
    for (const [key, value] of this.cache) {
      if (key.startsWith(prefix)) {
        result[key] = value;
      }
    }
    return result;
  }

  /**
   * 批量设置
   */
  setMany(entries: Record<string, any>): void {
    const stmt = this.db.prepare(`
      INSERT INTO state (key, value, updated_at)
      VALUES (?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(key) DO UPDATE SET
        value = excluded.value,
        updated_at = CURRENT_TIMESTAMP
    `);

    this.db.transaction(() => {
      for (const [key, value] of Object.entries(entries)) {
        const oldValue = this.cache.get(key);
        this.cache.set(key, value);
        stmt.run(key, JSON.stringify(value));
        this.notifyListeners(key, value, oldValue);
      }
    })();
  }

  /**
   * 删除前缀匹配的所有状态
   */
  deleteByPrefix(prefix: string): number {
    let count = 0;
    for (const [key] of this.cache) {
      if (key.startsWith(prefix)) {
        this.delete(key);
        count++;
      }
    }
    return count;
  }

  // ==================== 订阅机制 ====================

  /**
   * 订阅特定 key 的变更
   */
  subscribe(key: string, listener: StateListener): () => void {
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key)!.add(listener);

    // 返回取消订阅函数
    return () => {
      this.listeners.get(key)?.delete(listener);
    };
  }

  /**
   * 订阅所有变更
   */
  subscribeAll(listener: StateListener): () => void {
    this.globalListeners.add(listener);
    return () => {
      this.globalListeners.delete(listener);
    };
  }

  /**
   * 通知监听器
   */
  private notifyListeners(key: string, value: any, oldValue: any) {
    // 通知特定 key 的监听器
    this.listeners.get(key)?.forEach((listener) => {
      try {
        listener(key, value, oldValue);
      } catch (e) {
        console.error(`State listener error for key ${key}:`, e);
      }
    });

    // 通知全局监听器
    this.globalListeners.forEach((listener) => {
      try {
        listener(key, value, oldValue);
      } catch (e) {
        console.error(`Global state listener error:`, e);
      }
    });
  }

  // ==================== 便捷方法 ====================

  /**
   * 增加数值
   */
  increment(key: string, amount: number = 1): number {
    const current = this.get<number>(key, 0) || 0;
    const newValue = current + amount;
    this.set(key, newValue);
    return newValue;
  }

  /**
   * 追加到数组
   */
  push(key: string, ...items: any[]): number {
    const arr = this.get<any[]>(key, []) || [];
    arr.push(...items);
    this.set(key, arr);
    return arr.length;
  }

  /**
   * 获取所有 keys
   */
  keys(): string[] {
    return Array.from(this.cache.keys());
  }

  /**
   * 获取状态数量
   */
  size(): number {
    return this.cache.size;
  }

  /**
   * 导出所有状态
   */
  export(): Record<string, any> {
    const result: Record<string, any> = {};
    for (const [key, value] of this.cache) {
      result[key] = value;
    }
    return result;
  }

  /**
   * 导入状态
   */
  import(data: Record<string, any>, merge: boolean = true): void {
    if (!merge) {
      this.db.run("DELETE FROM state");
      this.cache.clear();
    }
    this.setMany(data);
  }

  // ==================== 数据库访问 ====================

  /**
   * 获取底层数据库实例 (用于高级查询)
   */
  getDb(): Database {
    return this.db;
  }

  /**
   * 执行原始 SQL 查询
   */
  query<T = any>(sql: string, params?: any[]): T[] {
    return this.db.query(sql).all(params || []) as T[];
  }

  /**
   * 执行原始 SQL 语句
   */
  run(sql: string, params?: any[]): void {
    this.db.run(sql, params || []);
  }

  /**
   * 关闭数据库连接
   */
  close(): void {
    this.db.close();
  }
}

// ==================== 快捷查询类 ====================

export class SolarQueries {
  constructor(private state: StateManager) {}

  private get db(): Database {
    return this.state.getDb();
  }

  // ---------- Tasks ----------

  getActiveTasks(project?: string) {
    const sql = project
      ? `SELECT * FROM tasks WHERE status = 'in_progress' AND project = ?`
      : `SELECT * FROM tasks WHERE status = 'in_progress'`;
    return this.db.query(sql).all(project ? [project] : []);
  }

  getTaskById(id: number) {
    return this.db.query("SELECT * FROM tasks WHERE id = ?").get([id]);
  }

  createTask(data: {
    project: string;
    description: string;
    complexity?: string;
  }) {
    const result = this.db.run(
      `
      INSERT INTO tasks (project, description, complexity, status)
      VALUES (?, ?, ?, 'pending')
    `,
      [data.project, data.description, data.complexity || "medium"],
    );
    return result.lastInsertRowid;
  }

  updateTaskStatus(id: number, status: string, agent?: string, phase?: string) {
    this.db.run(
      `
      UPDATE tasks SET status = ?, current_agent = ?, current_phase = ?
      WHERE id = ?
    `,
      [status, agent, phase, id],
    );
  }

  // ---------- Messages ----------

  logMessage(
    type: string,
    source: string,
    content: any,
    level: string = "info",
  ) {
    this.db.run(
      `
      INSERT INTO messages (type, source, content, level)
      VALUES (?, ?, ?, ?)
    `,
      [type, source, JSON.stringify(content), level],
    );
  }

  getRecentMessages(limit: number = 50, type?: string) {
    const where = type ? "WHERE type = ?" : "";
    return this.db
      .query(
        `
      SELECT * FROM messages ${where}
      ORDER BY timestamp DESC LIMIT ?
    `,
      )
      .all(type ? [type, limit] : [limit]);
  }

  getUnprocessedMessages(limit: number = 100) {
    return this.db
      .query(
        `
      SELECT * FROM messages WHERE processed = FALSE
      ORDER BY timestamp ASC LIMIT ?
    `,
      )
      .all([limit]);
  }

  markMessagesProcessed(ids: number[]) {
    if (ids.length === 0) return;
    const placeholders = ids.map(() => "?").join(",");
    this.db.run(
      `UPDATE messages SET processed = TRUE WHERE id IN (${placeholders})`,
      ids,
    );
  }

  // ---------- Token Usage ----------

  recordTokenUsage(
    model: string,
    provider: string,
    input: number,
    output: number,
    cost: number,
  ) {
    this.db.run(
      `
      INSERT INTO token_usage (date, model, provider, input_tokens, output_tokens, requests, cost_usd)
      VALUES (date('now'), ?, ?, ?, ?, 1, ?)
      ON CONFLICT(date, model) DO UPDATE SET
        input_tokens = input_tokens + excluded.input_tokens,
        output_tokens = output_tokens + excluded.output_tokens,
        requests = requests + 1,
        cost_usd = cost_usd + excluded.cost_usd
    `,
      [model, provider, input, output, cost],
    );

    // 更新今日统计
    const todayTotal = this.db
      .query(
        `
      SELECT SUM(cost_usd) as cost, SUM(input_tokens + output_tokens) as tokens
      FROM token_usage WHERE date = date('now')
    `,
      )
      .get() as { cost: number; tokens: number };

    this.state.set("token_usage.today_cost", todayTotal?.cost || 0);
    this.state.set("token_usage.today_tokens", todayTotal?.tokens || 0);
  }

  getTokenUsage(days: number = 7) {
    return this.db
      .query(
        `
      SELECT date, model, provider,
             SUM(input_tokens) as input_tokens,
             SUM(output_tokens) as output_tokens,
             SUM(requests) as requests,
             SUM(cost_usd) as cost_usd
      FROM token_usage
      WHERE date >= date('now', '-' || ? || ' days')
      GROUP BY date, model
      ORDER BY date DESC
    `,
      )
      .all([days]);
  }

  getTodayUsage() {
    return this.db
      .query(
        `
      SELECT model, provider, input_tokens, output_tokens, requests, cost_usd
      FROM token_usage WHERE date = date('now')
    `,
      )
      .all();
  }

  // ---------- Agent Runs ----------

  startAgentRun(taskId: number, agent: string, phase: string, input?: any) {
    const result = this.db.run(
      `
      INSERT INTO agent_runs (task_id, agent, phase, input)
      VALUES (?, ?, ?, ?)
    `,
      [taskId, agent, phase, input ? JSON.stringify(input) : null],
    );
    return result.lastInsertRowid;
  }

  endAgentRun(
    id: number,
    status: string,
    output?: any,
    tokensUsed?: number,
    model?: string,
    cost?: number,
  ) {
    this.db.run(
      `
      UPDATE agent_runs SET
        ended_at = CURRENT_TIMESTAMP,
        status = ?,
        output = ?,
        tokens_used = ?,
        model_used = ?,
        cost_usd = ?
      WHERE id = ?
    `,
      [
        status,
        output ? JSON.stringify(output) : null,
        tokensUsed || 0,
        model,
        cost || 0,
        id,
      ],
    );
  }

  getAgentStats(taskId?: number) {
    const where = taskId ? "WHERE task_id = ?" : "";
    return this.db
      .query(
        `
      SELECT agent,
             COUNT(*) as total_runs,
             SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
             SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
             AVG(tokens_used) as avg_tokens,
             SUM(cost_usd) as total_cost
      FROM agent_runs
      ${where}
      GROUP BY agent
    `,
      )
      .all(taskId ? [taskId] : []);
  }

  // ---------- Workflow ----------

  recordTransition(
    taskId: number,
    fromPhase: string,
    toPhase: string,
    fromAgent: string,
    toAgent: string,
    gate?: string,
    passed?: boolean,
  ) {
    this.db.run(
      `
      INSERT INTO workflow_transitions (task_id, from_phase, to_phase, from_agent, to_agent, gate_name, gate_passed)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `,
      [taskId, fromPhase, toPhase, fromAgent, toAgent, gate, passed],
    );
  }

  getWorkflowHistory(taskId: number) {
    return this.db
      .query(
        `
      SELECT * FROM workflow_transitions
      WHERE task_id = ?
      ORDER BY timestamp ASC
    `,
      )
      .all([taskId]);
  }

  // ---------- Plugins ----------

  registerPlugin(
    name: string,
    version: string,
    type: string,
    path: string,
    description?: string,
    config?: any,
  ) {
    this.db.run(
      `
      INSERT INTO plugins (name, version, type, path, description, config)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(name) DO UPDATE SET
        version = excluded.version,
        path = excluded.path,
        description = excluded.description,
        config = excluded.config,
        enabled = TRUE
    `,
      [
        name,
        version,
        type,
        path,
        description,
        config ? JSON.stringify(config) : null,
      ],
    );
  }

  getEnabledPlugins(type?: string) {
    const where = type
      ? "WHERE enabled = TRUE AND type = ?"
      : "WHERE enabled = TRUE";
    return this.db
      .query(`SELECT * FROM plugins ${where}`)
      .all(type ? [type] : []);
  }

  disablePlugin(name: string) {
    this.db.run("UPDATE plugins SET enabled = FALSE WHERE name = ?", [name]);
  }

  // ---------- Sessions ----------

  startSession(project: string) {
    const result = this.db.run(
      `
      INSERT INTO sessions (project) VALUES (?)
    `,
      [project],
    );
    const id = result.lastInsertRowid;
    this.state.set("session.active", true);
    this.state.set("session.id", id);
    return id;
  }

  endSession(id: number, summary?: string) {
    const session = this.db
      .query("SELECT started_at FROM sessions WHERE id = ?")
      .get([id]) as { started_at: string };
    if (session) {
      const startTime = new Date(session.started_at).getTime();
      const duration = Math.round((Date.now() - startTime) / 1000);

      // 计算总 tokens 和 cost
      const stats = this.db
        .query(
          `
        SELECT SUM(tokens_used) as tokens, SUM(cost_usd) as cost
        FROM agent_runs WHERE task_id IN (SELECT id FROM tasks WHERE id IN (
          SELECT DISTINCT task_id FROM agent_runs WHERE started_at >= ?
        ))
      `,
        )
        .get([session.started_at]) as { tokens: number; cost: number };

      this.db.run(
        `
        UPDATE sessions SET
          ended_at = CURRENT_TIMESTAMP,
          duration_seconds = ?,
          total_tokens = ?,
          total_cost_usd = ?,
          summary = ?
        WHERE id = ?
      `,
        [duration, stats?.tokens || 0, stats?.cost || 0, summary, id],
      );
    }

    this.state.set("session.active", false);
    this.state.set("session.id", null);
  }

  // ---------- Projects ----------

  registerProject(name: string, path: string, settings?: any) {
    this.db.run(
      `
      INSERT INTO projects (name, path, settings, last_opened_at)
      VALUES (?, ?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(name) DO UPDATE SET
        path = excluded.path,
        settings = COALESCE(excluded.settings, settings),
        last_opened_at = CURRENT_TIMESTAMP
    `,
      [name, path, settings ? JSON.stringify(settings) : null],
    );
  }

  getRecentProjects(limit: number = 10) {
    return this.db
      .query(
        `
      SELECT * FROM projects
      ORDER BY last_opened_at DESC
      LIMIT ?
    `,
      )
      .all([limit]);
  }
}

// ==================== 导出单例工厂 ====================

let _instance: StateManager | null = null;

export function getStateManager(config?: StateManagerConfig): StateManager {
  if (!_instance) {
    const defaultConfig: StateManagerConfig = {
      dbPath: process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`,
      autoInit: true,
    };
    _instance = new StateManager(config || defaultConfig);
  }
  return _instance;
}

export function getQueries(): SolarQueries {
  return new SolarQueries(getStateManager());
}
