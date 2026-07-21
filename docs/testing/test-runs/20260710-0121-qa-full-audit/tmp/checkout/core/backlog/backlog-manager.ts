/**
 * Solar Backlog Manager
 * 项目 → 特性 → 任务 三层结构管理
 */

import Database from 'bun:sqlite';
import { randomUUID } from 'crypto';

// Types
export interface Feature {
  feature_id: string;
  project_id: string;
  title: string;
  description?: string;
  priority: number;
  status: 'open' | 'in_progress' | 'done' | 'blocked' | 'archived';
  created_at: string;
  updated_at: string;
  due_date?: string;
  tags?: string[];
}

export interface Task {
  task_id: string;
  feature_id: string;
  title: string;
  description?: string;
  priority: number;
  status: 'pending' | 'in_progress' | 'done' | 'blocked' | 'cancelled';
  estimated_tokens?: number;
  actual_tokens?: number;
  assigned_agent?: string;
  created_at: string;
  completed_at?: string;
  tags?: string[];
}

export interface ProjectBacklog {
  project_id: string;
  feature_id: string;
  feature_title: string;
  feature_status: string;
  feature_priority: number;
  total_tasks: number;
  completed_tasks: number;
  active_tasks: number;
  pending_tasks: number;
  progress_pct: number;
  created_at: string;
  due_date?: string;
}

export interface MessageTask {
  id: number;
  source: 'imessage' | 'gmail' | 'telegram' | 'webhook' | 'manual';
  source_id: string;
  sender?: string;
  content: string;
  parsed_intent?: string;
  priority: number;
  status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  estimated_tokens?: number;
  actual_tokens?: number;
  result?: any;
  error?: string;
  created_at: string;
  retry_count: number;
}

// Backlog Manager Class
export class BacklogManager {
  private db: Database;

  constructor(dbPath: string = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`) {
    this.db = new Database(dbPath);
    this.db.exec('PRAGMA journal_mode = WAL');
  }

  // ============================================================
  // FEATURE OPERATIONS
  // ============================================================

  addFeature(projectId: string, title: string, options: Partial<Feature> = {}): Feature {
    const featureId = options.feature_id || `${projectId}:${this.generateShortId()}`;

    const stmt = this.db.prepare(`
      INSERT INTO bl_features (feature_id, project_id, title, description, priority, status, due_date, tags)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      featureId,
      projectId,
      title,
      options.description || null,
      options.priority || 50,
      options.status || 'open',
      options.due_date || null,
      options.tags ? JSON.stringify(options.tags) : null
    );

    return this.getFeature(featureId)!;
  }

  getFeature(featureId: string): Feature | null {
    const row = this.db.prepare('SELECT * FROM bl_features WHERE feature_id = ?').get(featureId) as any;
    if (!row) return null;
    return this.parseFeature(row);
  }

  updateFeature(featureId: string, updates: Partial<Feature>): Feature | null {
    const setClauses: string[] = [];
    const values: any[] = [];

    if (updates.title !== undefined) { setClauses.push('title = ?'); values.push(updates.title); }
    if (updates.description !== undefined) { setClauses.push('description = ?'); values.push(updates.description); }
    if (updates.priority !== undefined) { setClauses.push('priority = ?'); values.push(updates.priority); }
    if (updates.status !== undefined) { setClauses.push('status = ?'); values.push(updates.status); }
    if (updates.due_date !== undefined) { setClauses.push('due_date = ?'); values.push(updates.due_date); }
    if (updates.tags !== undefined) { setClauses.push('tags = ?'); values.push(JSON.stringify(updates.tags)); }

    if (setClauses.length === 0) return this.getFeature(featureId);

    values.push(featureId);
    this.db.prepare(`UPDATE bl_features SET ${setClauses.join(', ')} WHERE feature_id = ?`).run(...values);

    return this.getFeature(featureId);
  }

  listFeatures(projectId?: string, status?: string): Feature[] {
    let sql = 'SELECT * FROM bl_features WHERE 1=1';
    const params: any[] = [];

    if (projectId) { sql += ' AND project_id = ?'; params.push(projectId); }
    if (status) { sql += ' AND status = ?'; params.push(status); }

    sql += ' ORDER BY priority DESC, created_at DESC';

    const rows = this.db.prepare(sql).all(...params) as any[];
    return rows.map(r => this.parseFeature(r));
  }

  // ============================================================
  // TASK OPERATIONS
  // ============================================================

  addTask(featureId: string, title: string, options: Partial<Task> = {}): Task {
    const taskId = options.task_id || `${featureId}:${this.generateShortId()}`;

    const stmt = this.db.prepare(`
      INSERT INTO bl_tasks (task_id, feature_id, title, description, priority, status, estimated_tokens, assigned_agent, tags)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      taskId,
      featureId,
      title,
      options.description || null,
      options.priority || 50,
      options.status || 'pending',
      options.estimated_tokens || null,
      options.assigned_agent || null,
      options.tags ? JSON.stringify(options.tags) : null
    );

    return this.getTask(taskId)!;
  }

  getTask(taskId: string): Task | null {
    const row = this.db.prepare('SELECT * FROM bl_tasks WHERE task_id = ?').get(taskId) as any;
    if (!row) return null;
    return this.parseTask(row);
  }

  updateTask(taskId: string, updates: Partial<Task>): Task | null {
    const setClauses: string[] = [];
    const values: any[] = [];

    if (updates.title !== undefined) { setClauses.push('title = ?'); values.push(updates.title); }
    if (updates.description !== undefined) { setClauses.push('description = ?'); values.push(updates.description); }
    if (updates.priority !== undefined) { setClauses.push('priority = ?'); values.push(updates.priority); }
    if (updates.status !== undefined) { setClauses.push('status = ?'); values.push(updates.status); }
    if (updates.estimated_tokens !== undefined) { setClauses.push('estimated_tokens = ?'); values.push(updates.estimated_tokens); }
    if (updates.actual_tokens !== undefined) { setClauses.push('actual_tokens = ?'); values.push(updates.actual_tokens); }
    if (updates.assigned_agent !== undefined) { setClauses.push('assigned_agent = ?'); values.push(updates.assigned_agent); }
    if (updates.tags !== undefined) { setClauses.push('tags = ?'); values.push(JSON.stringify(updates.tags)); }

    if (setClauses.length === 0) return this.getTask(taskId);

    values.push(taskId);
    this.db.prepare(`UPDATE bl_tasks SET ${setClauses.join(', ')} WHERE task_id = ?`).run(...values);

    return this.getTask(taskId);
  }

  completeTask(taskId: string, actualTokens?: number): Task | null {
    return this.updateTask(taskId, {
      status: 'done',
      actual_tokens: actualTokens
    });
  }

  listTasks(featureId?: string, status?: string): Task[] {
    let sql = 'SELECT * FROM bl_tasks WHERE 1=1';
    const params: any[] = [];

    if (featureId) { sql += ' AND feature_id = ?'; params.push(featureId); }
    if (status) { sql += ' AND status = ?'; params.push(status); }

    sql += ' ORDER BY priority DESC, created_at ASC';

    const rows = this.db.prepare(sql).all(...params) as any[];
    return rows.map(r => this.parseTask(r));
  }

  // ============================================================
  // PROJECT BACKLOG VIEW
  // ============================================================

  getProjectBacklog(projectId?: string): ProjectBacklog[] {
    let sql = 'SELECT * FROM v_project_backlog WHERE 1=1';
    const params: any[] = [];

    if (projectId) { sql += ' AND project_id = ?'; params.push(projectId); }

    return this.db.prepare(sql).all(...params) as ProjectBacklog[];
  }

  // ============================================================
  // SESSION TASK EXTRACTION
  // ============================================================

  extractFromSession(sessionId: string, tasks: Array<{ title: string; featureId: string; context?: string }>): Task[] {
    const created: Task[] = [];

    for (const t of tasks) {
      const task = this.addTask(t.featureId, t.title);

      this.db.prepare(`
        INSERT INTO bl_session_tasks (session_id, task_id, source, context)
        VALUES (?, ?, 'auto_extract', ?)
      `).run(sessionId, task.task_id, t.context || null);

      created.push(task);
    }

    return created;
  }

  getSessionTasks(sessionId: string): Task[] {
    const rows = this.db.prepare(`
      SELECT t.* FROM bl_tasks t
      JOIN bl_session_tasks st ON t.task_id = st.task_id
      WHERE st.session_id = ?
      ORDER BY st.extracted_at DESC
    `).all(sessionId) as any[];

    return rows.map(r => this.parseTask(r));
  }

  // ============================================================
  // MESSAGE TASK OPERATIONS
  // ============================================================

  ingestMessage(
    source: MessageTask['source'],
    sourceId: string,
    content: string,
    sender?: string,
    metadata?: any
  ): MessageTask | null {
    // Dedup check
    const existing = this.db.prepare(
      'SELECT id FROM bl_message_tasks WHERE source = ? AND source_id = ?'
    ).get(source, sourceId);

    if (existing) return null;

    // Parse intent and calculate priority
    const { intent, priorityBoost } = this.parseIntent(content);
    const basePriority = this.calculateBasePriority(source, sender);
    const priority = Math.min(100, basePriority + priorityBoost);

    // Estimate tokens
    const estimatedTokens = Math.ceil(content.length / 4) * 10; // rough estimate

    const stmt = this.db.prepare(`
      INSERT INTO bl_message_tasks (source, source_id, sender, content, parsed_intent, priority, estimated_tokens, metadata)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const result = stmt.run(
      source,
      sourceId,
      sender,
      content,
      intent,
      priority,
      estimatedTokens,
      metadata ? JSON.stringify(metadata) : null
    );

    return this.getMessageTask(result.lastInsertRowid as number);
  }

  getMessageTask(id: number): MessageTask | null {
    const row = this.db.prepare('SELECT * FROM bl_message_tasks WHERE id = ?').get(id) as any;
    if (!row) return null;
    return this.parseMessageTask(row);
  }

  getMessageQueue(limit: number = 10): MessageTask[] {
    const rows = this.db.prepare(`
      SELECT * FROM bl_message_tasks
      WHERE status IN ('pending', 'queued')
      ORDER BY priority DESC, created_at ASC
      LIMIT ?
    `).all(limit) as any[];

    return rows.map(r => this.parseMessageTask(r));
  }

  updateMessageTaskStatus(
    id: number,
    status: MessageTask['status'],
    result?: any,
    error?: string,
    actualTokens?: number
  ): void {
    const updates: string[] = ['status = ?'];
    const values: any[] = [status];

    if (result !== undefined) { updates.push('result = ?'); values.push(JSON.stringify(result)); }
    if (error !== undefined) { updates.push('error = ?'); values.push(error); }
    if (actualTokens !== undefined) { updates.push('actual_tokens = ?'); values.push(actualTokens); }

    values.push(id);
    this.db.prepare(`UPDATE bl_message_tasks SET ${updates.join(', ')} WHERE id = ?`).run(...values);
  }

  retryMessageTask(id: number): boolean {
    const task = this.getMessageTask(id);
    if (!task || task.retry_count >= task.max_retries) return false;

    this.db.prepare(`
      UPDATE bl_message_tasks
      SET status = 'pending', retry_count = retry_count + 1, error = NULL
      WHERE id = ?
    `).run(id);

    return true;
  }

  // ============================================================
  // SEARCH
  // ============================================================

  search(query: string, projectId?: string): { features: Feature[]; tasks: Task[] } {
    const pattern = `%${query}%`;

    let featureSql = `
      SELECT * FROM bl_features
      WHERE (title LIKE ? OR description LIKE ? OR tags LIKE ?)
    `;
    const featureParams: any[] = [pattern, pattern, pattern];

    if (projectId) {
      featureSql += ' AND project_id = ?';
      featureParams.push(projectId);
    }

    const features = (this.db.prepare(featureSql).all(...featureParams) as any[]).map(r => this.parseFeature(r));

    let taskSql = `
      SELECT t.* FROM bl_tasks t
      JOIN bl_features f ON t.feature_id = f.feature_id
      WHERE (t.title LIKE ? OR t.description LIKE ? OR t.tags LIKE ?)
    `;
    const taskParams: any[] = [pattern, pattern, pattern];

    if (projectId) {
      taskSql += ' AND f.project_id = ?';
      taskParams.push(projectId);
    }

    const tasks = (this.db.prepare(taskSql).all(...taskParams) as any[]).map(r => this.parseTask(r));

    return { features, tasks };
  }

  // ============================================================
  // HELPER METHODS
  // ============================================================

  private generateShortId(): string {
    return randomUUID().substring(0, 8);
  }

  private parseFeature(row: any): Feature {
    return {
      ...row,
      tags: row.tags ? JSON.parse(row.tags) : undefined
    };
  }

  private parseTask(row: any): Task {
    return {
      ...row,
      tags: row.tags ? JSON.parse(row.tags) : undefined
    };
  }

  private parseMessageTask(row: any): MessageTask {
    return {
      ...row,
      result: row.result ? JSON.parse(row.result) : undefined,
      metadata: row.metadata ? JSON.parse(row.metadata) : undefined
    };
  }

  private parseIntent(content: string): { intent: string; priorityBoost: number } {
    const triggers = this.db.prepare(
      'SELECT * FROM bl_message_triggers WHERE enabled = 1'
    ).all() as any[];

    let intent = 'general';
    let priorityBoost = 0;

    for (const trigger of triggers) {
      let matches = false;

      if (trigger.pattern_type === 'keyword') {
        matches = content.toLowerCase().includes(trigger.pattern.toLowerCase());
      } else if (trigger.pattern_type === 'regex') {
        try {
          matches = new RegExp(trigger.pattern, 'i').test(content);
        } catch {}
      }

      if (matches) {
        intent = trigger.action_target;
        priorityBoost = Math.max(priorityBoost, trigger.priority_boost);
      }
    }

    return { intent, priorityBoost };
  }

  private calculateBasePriority(source: MessageTask['source'], sender?: string): number {
    // Source-based priority
    const sourcePriority: Record<string, number> = {
      imessage: 60,
      telegram: 55,
      gmail: 50,
      webhook: 45,
      manual: 40
    };

    return sourcePriority[source] || 50;
  }

  // ============================================================
  // STATS
  // ============================================================

  getStats(projectId?: string): {
    totalFeatures: number;
    openFeatures: number;
    totalTasks: number;
    pendingTasks: number;
    completedTasks: number;
    messageQueueSize: number;
  } {
    let featureWhere = projectId ? 'WHERE project_id = ?' : '';
    let taskWhere = projectId ? 'WHERE f.project_id = ?' : '';
    const params = projectId ? [projectId] : [];

    const featureStats = this.db.prepare(`
      SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open
      FROM bl_features ${featureWhere}
    `).get(...params) as any;

    const taskStats = this.db.prepare(`
      SELECT
        COUNT(*) as total,
        SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as completed
      FROM bl_tasks t
      JOIN bl_features f ON t.feature_id = f.feature_id
      ${taskWhere}
    `).get(...params) as any;

    const queueSize = this.db.prepare(`
      SELECT COUNT(*) as count FROM bl_message_tasks WHERE status IN ('pending', 'queued')
    `).get() as any;

    return {
      totalFeatures: featureStats.total,
      openFeatures: featureStats.open,
      totalTasks: taskStats.total,
      pendingTasks: taskStats.pending,
      completedTasks: taskStats.completed,
      messageQueueSize: queueSize.count
    };
  }

  close(): void {
    this.db.close();
  }
}

// CLI support
if (import.meta.main) {
  const manager = new BacklogManager();
  const [cmd, ...args] = process.argv.slice(2);

  switch (cmd) {
    case 'list':
      console.log(JSON.stringify(manager.getProjectBacklog(args[0]), null, 2));
      break;
    case 'stats':
      console.log(JSON.stringify(manager.getStats(args[0]), null, 2));
      break;
    case 'queue':
      console.log(JSON.stringify(manager.getMessageQueue(parseInt(args[0]) || 10), null, 2));
      break;
    default:
      console.log('Usage: backlog-manager.ts <list|stats|queue> [args]');
  }

  manager.close();
}
