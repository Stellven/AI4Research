/**
 * Message Executor Module - 消息驱动执行器
 * 集成到现有 SolarDaemon，添加消息监听和配额调度功能
 */

import { iMessageListener } from '../listeners/imessage-listener';
import { GmailListener } from '../listeners/gmail-listener';
import { TelegramListener } from '../listeners/telegram-listener';
import { QuotaScheduler } from '../executor/quota-scheduler';
import { BacklogManager } from '../backlog/backlog-manager';
import { ReplySender, Channel } from '../reply/reply-sender';
import Database from 'bun:sqlite';
import { $ } from 'bun';
import { SkillDispatcher } from './skill-dispatcher';
import { Orchestrator } from '../orchestrator';
import { OrchestrationEvent, TaskGraph } from '../orchestrator/types';
import { RetryPolicy, DEFAULT_RETRY_POLICY, computeBackoffMs } from '../orchestrator/retry-policy';

export interface MessageExecutorConfig {
  listeners: {
    imessage: boolean;
    gmail: boolean;
    telegram: boolean;
  };
  scheduler: {
    interval: number;
    maxWorkers: number;
  };
  telegramBotToken?: string;
}

const DEFAULT_CONFIG: MessageExecutorConfig = {
  listeners: {
    imessage: true,
    gmail: true,
    telegram: false
  },
  scheduler: {
    interval: 5000,
    maxWorkers: 4
  }
};

type RetryState = {
  taskId: string;
  nodeId: string;
  attemptCount: number;
  lastError?: string;
  nextRetryAt?: string;
  status: 'pending_retry' | 'retrying' | 'exhausted' | 'handed_to_repair_branch' | 'completed';
  branchSuggestion?: string;
  updatedAt: string;
};

/**
 * MessageExecutor - 消息驱动任务执行器
 * 可作为独立服务运行，或集成到 SolarDaemon
 */
export class MessageExecutor {
  private config: MessageExecutorConfig;
  private iMessageListener?: iMessageListener;
  private gmailListener?: GmailListener;
  private telegramListener?: TelegramListener;
  private scheduler: QuotaScheduler;
  private backlog: BacklogManager;
  private replySender: ReplySender;
  private skillDispatcher: SkillDispatcher;
  private orchestrator: Orchestrator;
  private retryPolicy: RetryPolicy;
  private orchestrationEvents: OrchestrationEvent[] = [];
  private activeGraphs: Map<string, TaskGraph> = new Map();
  private db: Database;
  private running: boolean = false;
  private workerInterval?: Timer;

  constructor(config: Partial<MessageExecutorConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.scheduler = new QuotaScheduler();
    this.backlog = new BacklogManager();
    this.replySender = new ReplySender();
    this.skillDispatcher = new SkillDispatcher();
    this.orchestrator = new Orchestrator({
      defaultDebateRounds: 1,
      highRiskThreshold: 0.7,
      voteMode: 'weighted',
      onEvent: (event) => {
        this.recordOrchestrationEvent(event);
        const nodePart = event.nodeId ? ` node=${event.nodeId}` : '';
        console.log(`[Orchestrator] ${event.type} task=${event.taskId}${nodePart}`);
      },
    });
    this.db = new Database(process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`);
    this.ensureMessageTaskIdIntegrity();
    this.ensureOrchestrationSchema();
    this.retryPolicy = this.loadRetryPolicy();
  }

  /**
   * 启动消息执行器
   */
  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;

    console.log('[MessageExecutor] Starting...');

    // 启动监听器
    await this.startListeners();

    // 启动调度器
    this.scheduler.start(this.config.scheduler.interval);

    // 启动 Worker 循环
    this.workerInterval = setInterval(
      () => this.processNextTask(),
      this.config.scheduler.interval
    );

    console.log('[MessageExecutor] Running');
  }

  /**
   * 停止消息执行器
   */
  stop(): void {
    if (!this.running) return;
    this.running = false;

    console.log('[MessageExecutor] Stopping...');

    // 停止监听器
    this.iMessageListener?.stop();
    this.gmailListener?.stop();
    this.telegramListener?.stop();

    // 停止调度器
    this.scheduler.stop();

    // 停止 Worker 循环
    if (this.workerInterval) {
      clearInterval(this.workerInterval);
      this.workerInterval = undefined;
    }

    // 清理资源
    this.scheduler.close();
    this.backlog.close();

    console.log('[MessageExecutor] Stopped');
  }

  /**
   * 启动所有配置的监听器
   */
  private async startListeners(): Promise<void> {
    if (this.config.listeners.imessage) {
      this.iMessageListener = new iMessageListener();
      await this.iMessageListener.start();
      console.log('[MessageExecutor] iMessage listener started');
    }

    if (this.config.listeners.gmail) {
      this.gmailListener = new GmailListener();
      await this.gmailListener.start();
      console.log('[MessageExecutor] Gmail listener started');
    }

    if (this.config.listeners.telegram && this.config.telegramBotToken) {
      this.telegramListener = new TelegramListener();
      await this.telegramListener.start();
      console.log('[MessageExecutor] Telegram listener started');
    }
  }

  /**
   * 处理下一个任务
   */
  private async processNextTask(): Promise<void> {
    if (!this.running) return;
    this.releaseDueRetries();

    const decision = this.scheduler.getSchedulerDecision();

    if (!decision.canExecute) {
      return;
    }

    const tasks = this.scheduler.getNextTasks(1);

    if (tasks.length === 0) {
      return;
    }

    const task = tasks[0];
    const execution = this.scheduler.startTask(task.id);

    if (!execution) {
      return;
    }

    try {
      const result = await this.executeTask(task);
      this.scheduler.completeTask(task.id, result, result.tokensUsed || 0);

      // 发送回复给用户
      await this.sendReplyToUser(task.id, result);
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      this.scheduler.failTask(task.id, errorMsg);
    }
  }

  /**
   * 执行任务
   */
  private async executeTask(task: {
    id: number | string;
    content: string;
    parsedIntent: string;
    estimatedTokens: number;
  }): Promise<any> {
    console.log(`[MessageExecutor] Executing task ${task.id}: ${task.content.slice(0, 50)}...`);

    const taskId = String(task.id);
    const graph = this.orchestrator.buildGraph(taskId, task.content, task.parsedIntent);
    this.activeGraphs.set(taskId, graph);
    this.saveTaskGraph(taskId, graph);
    const execution = await this.orchestrator.executeGraph(graph, async ({ node }) => {
      return this.executeTaskNode(node.intent, node.content);
    });
    this.activeGraphs.set(taskId, graph);
    this.saveTaskGraph(taskId, graph);

    return {
      type: 'orchestrated',
      output: execution.output,
      tokensUsed: execution.tokensUsed,
      nodes: execution.nodeResults.length,
    };
  }

  private recordOrchestrationEvent(event: OrchestrationEvent): void {
    this.db.prepare(`
      INSERT INTO bl_orchestration_events (task_id, node_id, event_type, payload_json, created_at)
      VALUES (?, ?, ?, ?, ?)
    `).run(
      event.taskId,
      event.nodeId ?? null,
      event.type,
      JSON.stringify(event.payload ?? {}),
      event.at
    );

    this.orchestrationEvents.push(event);
    if (this.orchestrationEvents.length > 1000) {
      this.orchestrationEvents = this.orchestrationEvents.slice(-500);
    }

    // Retry state machine hooks
    if (event.type === 'node_failed' && event.nodeId) {
      this.handleNodeFailure(event.taskId, event.nodeId, String((event.payload as any)?.error || 'unknown error'));
    }
    if (event.type === 'node_completed' && event.nodeId) {
      this.markRetryCompleted(event.taskId, event.nodeId);
    }
  }

  private loadRetryPolicy(): RetryPolicy {
    const row = this.db.prepare(`
      SELECT base_delay_ms, max_delay_ms, max_attempts, jitter_ratio, retryable_error_patterns_json
      FROM bl_orchestration_retry_policy
      WHERE id = 1
    `).get() as {
      base_delay_ms: number;
      max_delay_ms: number;
      max_attempts: number;
      jitter_ratio: number;
      retryable_error_patterns_json: string | null;
    } | null;
    if (!row) {
      return { ...DEFAULT_RETRY_POLICY };
    }
    let patterns = DEFAULT_RETRY_POLICY.retryableErrorPatterns;
    if (row.retryable_error_patterns_json) {
      try {
        const parsed = JSON.parse(row.retryable_error_patterns_json);
        if (Array.isArray(parsed)) {
          patterns = parsed.map((x) => String(x).toLowerCase());
        }
      } catch {
        patterns = DEFAULT_RETRY_POLICY.retryableErrorPatterns;
      }
    }
    return {
      baseDelayMs: row.base_delay_ms || DEFAULT_RETRY_POLICY.baseDelayMs,
      maxDelayMs: row.max_delay_ms || DEFAULT_RETRY_POLICY.maxDelayMs,
      maxAttempts: row.max_attempts || DEFAULT_RETRY_POLICY.maxAttempts,
      jitterRatio: typeof row.jitter_ratio === 'number' ? row.jitter_ratio : DEFAULT_RETRY_POLICY.jitterRatio,
      retryableErrorPatterns: patterns,
    };
  }

  private upsertRetryState(state: RetryState): void {
    this.db.prepare(`
      INSERT INTO bl_orchestration_retries (
        task_id, node_id, attempt_count, last_error, next_retry_at, retry_status, branch_suggestion, updated_at
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(task_id, node_id) DO UPDATE SET
        attempt_count = excluded.attempt_count,
        last_error = excluded.last_error,
        next_retry_at = excluded.next_retry_at,
        retry_status = excluded.retry_status,
        branch_suggestion = excluded.branch_suggestion,
        updated_at = excluded.updated_at
    `).run(
      state.taskId,
      state.nodeId,
      state.attemptCount,
      state.lastError ?? null,
      state.nextRetryAt ?? null,
      state.status,
      state.branchSuggestion ?? null,
      state.updatedAt,
    );
  }

  private getRetryState(taskId: string, nodeId: string): RetryState | null {
    const row = this.db.prepare(`
      SELECT task_id, node_id, attempt_count, last_error, next_retry_at, retry_status, branch_suggestion, updated_at
      FROM bl_orchestration_retries
      WHERE task_id = ? AND node_id = ?
      LIMIT 1
    `).get(taskId, nodeId) as {
      task_id: string;
      node_id: string;
      attempt_count: number;
      last_error: string | null;
      next_retry_at: string | null;
      retry_status: RetryState['status'];
      branch_suggestion: string | null;
      updated_at: string;
    } | null;
    if (!row) return null;
    return {
      taskId: row.task_id,
      nodeId: row.node_id,
      attemptCount: row.attempt_count || 0,
      lastError: row.last_error ?? undefined,
      nextRetryAt: row.next_retry_at ?? undefined,
      status: row.retry_status,
      branchSuggestion: row.branch_suggestion ?? undefined,
      updatedAt: row.updated_at,
    };
  }

  private getRetryStatesForTask(taskId: string): Map<string, RetryState> {
    const rows = this.db.prepare(`
      SELECT task_id, node_id, attempt_count, last_error, next_retry_at, retry_status, branch_suggestion, updated_at
      FROM bl_orchestration_retries
      WHERE task_id = ?
    `).all(taskId) as Array<{
      task_id: string;
      node_id: string;
      attempt_count: number;
      last_error: string | null;
      next_retry_at: string | null;
      retry_status: RetryState['status'];
      branch_suggestion: string | null;
      updated_at: string;
    }>;
    const out = new Map<string, RetryState>();
    for (const row of rows) {
      out.set(row.node_id, {
        taskId: row.task_id,
        nodeId: row.node_id,
        attemptCount: row.attempt_count || 0,
        lastError: row.last_error ?? undefined,
        nextRetryAt: row.next_retry_at ?? undefined,
        status: row.retry_status,
        branchSuggestion: row.branch_suggestion ?? undefined,
        updatedAt: row.updated_at,
      });
    }
    return out;
  }

  private isRetryableError(error: string): boolean {
    const low = error.toLowerCase();
    return this.retryPolicy.retryableErrorPatterns.some((p) => low.includes(p.toLowerCase()));
  }

  private handleNodeFailure(taskId: string, nodeId: string, error: string): void {
    const nowIso = new Date().toISOString();
    const current = this.getRetryState(taskId, nodeId);
    const nextAttempt = (current?.attemptCount || 0) + 1;
    const branchSuggestion = this.suggestFixBranch(taskId, nodeId);

    if (!this.isRetryableError(error)) {
      this.upsertRetryState({
        taskId,
        nodeId,
        attemptCount: current?.attemptCount || 0,
        lastError: error,
        status: 'exhausted',
        branchSuggestion,
        updatedAt: nowIso,
      });
      this.recordOrchestrationEvent({
        type: 'retry_exhausted',
        taskId,
        nodeId,
        payload: {
          reason: 'non_retryable_error',
          error,
          branchSuggestion,
        },
        at: nowIso,
      });
      this.queueRepairBranchTask(taskId, nodeId, error, branchSuggestion);
      return;
    }

    if (nextAttempt > this.retryPolicy.maxAttempts) {
      this.upsertRetryState({
        taskId,
        nodeId,
        attemptCount: current?.attemptCount || 0,
        lastError: error,
        status: 'exhausted',
        branchSuggestion,
        updatedAt: nowIso,
      });
      this.recordOrchestrationEvent({
        type: 'retry_exhausted',
        taskId,
        nodeId,
        payload: {
          maxAttempts: this.retryPolicy.maxAttempts,
          error,
          branchSuggestion,
        },
        at: nowIso,
      });
      this.queueRepairBranchTask(taskId, nodeId, error, branchSuggestion);
      return;
    }

    const delayMs = computeBackoffMs(this.retryPolicy, nextAttempt);
    const nextRetryAt = new Date(Date.now() + delayMs).toISOString();
    this.upsertRetryState({
      taskId,
      nodeId,
      attemptCount: nextAttempt,
      lastError: error,
      nextRetryAt,
      status: 'pending_retry',
      branchSuggestion,
      updatedAt: nowIso,
    });
    this.recordOrchestrationEvent({
      type: 'retry_scheduled',
      taskId,
      nodeId,
      payload: {
        attempt: nextAttempt,
        maxAttempts: this.retryPolicy.maxAttempts,
        delayMs,
        nextRetryAt,
      },
      at: nowIso,
    });
  }

  private markRetryCompleted(taskId: string, nodeId: string): void {
    const nowIso = new Date().toISOString();
    const current = this.getRetryState(taskId, nodeId);
    if (!current) return;
    this.upsertRetryState({
      taskId,
      nodeId,
      attemptCount: current.attemptCount,
      lastError: current.lastError,
      status: 'completed',
      branchSuggestion: current.branchSuggestion,
      updatedAt: nowIso,
    });
  }

  private releaseDueRetries(): void {
    const nowIso = new Date().toISOString();
    const rows = this.db.prepare(`
      SELECT task_id, node_id, attempt_count
      FROM bl_orchestration_retries
      WHERE retry_status = 'pending_retry'
        AND next_retry_at IS NOT NULL
        AND next_retry_at <= ?
      ORDER BY updated_at ASC
      LIMIT 10
    `).all(nowIso) as Array<{
      task_id: string;
      node_id: string;
      attempt_count: number;
    }>;

    for (const row of rows) {
      const result = this.retryNode(row.task_id, row.node_id, {
        auto: true,
        attempt: row.attempt_count,
      });
      if (!result.queued) {
        this.upsertRetryState({
          taskId: row.task_id,
          nodeId: row.node_id,
          attemptCount: row.attempt_count,
          status: 'exhausted',
          updatedAt: new Date().toISOString(),
        });
        this.recordOrchestrationEvent({
          type: 'retry_exhausted',
          taskId: row.task_id,
          nodeId: row.node_id,
          payload: {
            reason: result.reason || 'retry_dispatch_failed',
          },
          at: new Date().toISOString(),
        });
        continue;
      }
      this.upsertRetryState({
        taskId: row.task_id,
        nodeId: row.node_id,
        attemptCount: row.attempt_count,
        status: 'retrying',
        updatedAt: new Date().toISOString(),
      });
    }
  }

  private queueRepairBranchTask(taskId: string, nodeId: string, error: string, branchSuggestion: string): string | null {
    const content = [
      `Repair workflow required for failed node.`,
      `taskId=${taskId}`,
      `nodeId=${nodeId}`,
      `branch=${branchSuggestion}`,
      `error=${error}`,
      `Please create fix branch and route to /review after patch.`,
    ].join('\n');
    const sourceId = `repair:${taskId}:${nodeId}:${Date.now()}`;
    const repairTaskId = this.makeDerivedTaskId('repair', taskId, nodeId);
    const metadata = JSON.stringify({
      repair_of: { taskId, nodeId },
      branch_suggestion: branchSuggestion,
      created_by: 'orchestrator_repair_flow',
    });
    const ins = this.db.prepare(`
      INSERT INTO bl_message_tasks (
        task_id, source, source_id, sender, content, parsed_intent, priority, status, estimated_tokens, metadata
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
    `).run(repairTaskId, 'manual', sourceId, 'system', content, '/review', 90, 500, metadata);
    const newTaskId = ins.changes > 0 ? repairTaskId : null;

    this.upsertRetryState({
      taskId,
      nodeId,
      attemptCount: this.getRetryState(taskId, nodeId)?.attemptCount || this.retryPolicy.maxAttempts,
      status: 'handed_to_repair_branch',
      branchSuggestion,
      updatedAt: new Date().toISOString(),
    });
    this.recordOrchestrationEvent({
      type: 'repair_branch_queued',
      taskId,
      nodeId,
      payload: { branchSuggestion, newTaskId },
      at: new Date().toISOString(),
    });
    return newTaskId;
  }

  getOrchestrationEvents(
    limit: number = 100,
    taskId?: string,
    eventType?: string,
    sinceIso?: string
  ): OrchestrationEvent[] {
    const boundedLimit = Math.max(1, Math.min(limit, 1000));
    const where: string[] = [];
    const params: Array<string | number> = [];
    if (taskId) {
      where.push('task_id = ?');
      params.push(taskId);
    }
    if (eventType) {
      where.push('event_type = ?');
      params.push(eventType);
    }
    if (sinceIso) {
      where.push('created_at >= ?');
      params.push(sinceIso);
    }
    const whereSql = where.length > 0 ? `WHERE ${where.join(' AND ')}` : '';
    const query = `
      SELECT task_id, node_id, event_type, payload_json, created_at
      FROM bl_orchestration_events
      ${whereSql}
      ORDER BY id DESC
      LIMIT ?
    `;
    params.push(boundedLimit);
    const rows = this.db.prepare(query).all(...params) as Array<{
      task_id: string;
      node_id: string | null;
      event_type: OrchestrationEvent['type'];
      payload_json: string | null;
      created_at: string;
    }>;

    return rows.reverse().map((r) => ({
      type: r.event_type,
      taskId: r.task_id,
      nodeId: r.node_id ?? undefined,
      payload: (() => {
        try {
          return r.payload_json ? JSON.parse(r.payload_json) : {};
        } catch {
          return {};
        }
      })(),
      at: r.created_at,
    }));
  }

  getOrchestrationState(): {
    activeTaskIds: string[];
    recentEvents: OrchestrationEvent[];
  } {
    return {
      activeTaskIds: Array.from(this.activeGraphs.keys()),
      recentEvents: this.getOrchestrationEvents(50),
    };
  }

  getTaskGraph(taskId: string): TaskGraph | null {
    const mem = this.activeGraphs.get(taskId);
    if (mem) return mem;
    const row = this.db.prepare(`
      SELECT graph_json
      FROM bl_orchestration_graphs
      WHERE task_id = ?
      ORDER BY id DESC
      LIMIT 1
    `).get(taskId) as { graph_json: string } | null;
    if (!row?.graph_json) return null;
    try {
      return JSON.parse(row.graph_json) as TaskGraph;
    } catch {
      return null;
    }
  }

  listKnownTaskIds(limit: number = 50): string[] {
    const boundedLimit = Math.max(1, Math.min(limit, 500));
    const eventRows = this.db.prepare(`
      SELECT task_id, MAX(id) AS last_id
      FROM bl_orchestration_events
      GROUP BY task_id
      ORDER BY last_id DESC
      LIMIT ?
    `).all(boundedLimit) as Array<{ task_id: string }>;
    const graphRows = this.db.prepare(`
      SELECT task_id, MAX(id) AS last_id
      FROM bl_orchestration_graphs
      GROUP BY task_id
      ORDER BY last_id DESC
      LIMIT ?
    `).all(boundedLimit) as Array<{ task_id: string }>;

    const ids = [...eventRows.map(r => r.task_id), ...graphRows.map(r => r.task_id)];
    const unique: string[] = [];
    for (const id of ids) {
      if (!unique.includes(id)) unique.push(id);
    }
    for (const id of this.activeGraphs.keys()) {
      if (!unique.includes(id)) unique.unshift(id);
    }
    return unique.slice(0, boundedLimit);
  }

  getTaskDiagnostics(taskId: string): {
    taskId: string;
    aggregate: {
      totalTokens: number;
      completedNodes: number;
      failedNodes: number;
      avgDurationMs: number;
    };
    timeline: Array<{
      nodeId: string;
      status: 'completed' | 'failed' | 'running' | 'pending';
      startedAt?: string;
      endedAt?: string;
      durationMs?: number;
      tokensUsed?: number;
      intent?: string;
      riskScore?: number;
      outputPreview?: string;
      attemptCount?: number;
      nextRetryAt?: string;
      retryStatus?: string;
    }>;
    failures: Array<{
      nodeId: string;
      at: string;
      error: string;
      durationMs?: number;
      likelyCause: string;
      suggestion: string;
      branchSuggestion: string;
      attemptCount?: number;
      nextRetryAt?: string;
      retryStatus?: string;
    }>;
  } {
    const events = this.getOrchestrationEvents(2000, taskId);
    const graph = this.getTaskGraph(taskId);
    const retryStates = this.getRetryStatesForTask(taskId);
    const nodeMeta = new Map<string, { intent?: string; riskScore?: number }>();
    for (const n of graph?.nodes || []) {
      nodeMeta.set(n.id, { intent: n.intent, riskScore: n.riskScore });
    }

    const nodeMap = new Map<string, {
      nodeId: string;
      status: 'completed' | 'failed' | 'running' | 'pending';
      startedAt?: string;
      endedAt?: string;
      durationMs?: number;
      tokensUsed?: number;
      intent?: string;
      riskScore?: number;
      outputPreview?: string;
      attemptCount?: number;
      nextRetryAt?: string;
      retryStatus?: string;
    }>();

    const failures: Array<{
      nodeId: string;
      at: string;
      error: string;
      durationMs?: number;
      likelyCause: string;
      suggestion: string;
      branchSuggestion: string;
      attemptCount?: number;
      nextRetryAt?: string;
      retryStatus?: string;
    }> = [];

    for (const e of events) {
      const nodeId = e.nodeId;
      if (!nodeId) continue;
      const base = nodeMap.get(nodeId) || {
        nodeId,
        status: 'pending' as const,
        intent: nodeMeta.get(nodeId)?.intent,
        riskScore: nodeMeta.get(nodeId)?.riskScore,
        attemptCount: retryStates.get(nodeId)?.attemptCount,
        nextRetryAt: retryStates.get(nodeId)?.nextRetryAt,
        retryStatus: retryStates.get(nodeId)?.status,
      };

      if (e.type === 'node_started') {
        base.status = 'running';
        base.startedAt = e.at;
        if (typeof (e.payload as any)?.risk === 'number') base.riskScore = (e.payload as any).risk;
        if (typeof (e.payload as any)?.intent === 'string') base.intent = (e.payload as any).intent;
      } else if (e.type === 'node_completed') {
        base.status = 'completed';
        base.endedAt = e.at;
        if (typeof (e.payload as any)?.durationMs === 'number') base.durationMs = (e.payload as any).durationMs;
        if (typeof (e.payload as any)?.tokensUsed === 'number') base.tokensUsed = (e.payload as any).tokensUsed;
        if (typeof (e.payload as any)?.outputPreview === 'string') base.outputPreview = (e.payload as any).outputPreview;
      } else if (e.type === 'node_failed') {
        base.status = 'failed';
        base.endedAt = e.at;
        if (typeof (e.payload as any)?.durationMs === 'number') base.durationMs = (e.payload as any).durationMs;
        const error = String((e.payload as any)?.error || 'unknown error');
        failures.push({
          nodeId,
          at: e.at,
          error,
          durationMs: base.durationMs,
          likelyCause: this.inferFailureCause(error),
          suggestion: this.suggestFailureFix(error),
          branchSuggestion: this.suggestFixBranch(taskId, nodeId),
          attemptCount: retryStates.get(nodeId)?.attemptCount,
          nextRetryAt: retryStates.get(nodeId)?.nextRetryAt,
          retryStatus: retryStates.get(nodeId)?.status,
        });
      }

      nodeMap.set(nodeId, base);
    }

    // Ensure nodes from graph appear even if no events yet
    for (const n of graph?.nodes || []) {
      if (!nodeMap.has(n.id)) {
        nodeMap.set(n.id, {
          nodeId: n.id,
          status: (n.status as 'completed' | 'failed' | 'running' | 'pending') || 'pending',
          intent: n.intent,
          riskScore: n.riskScore,
          attemptCount: retryStates.get(n.id)?.attemptCount,
          nextRetryAt: retryStates.get(n.id)?.nextRetryAt,
          retryStatus: retryStates.get(n.id)?.status,
        });
      }
    }

    const timeline = Array.from(nodeMap.values()).sort((a, b) => a.nodeId.localeCompare(b.nodeId));
    const totalTokens = timeline.reduce((acc, n) => acc + (n.tokensUsed || 0), 0);
    const completedNodes = timeline.filter(n => n.status === 'completed').length;
    const failedNodes = timeline.filter(n => n.status === 'failed').length;
    const durations = timeline.map(n => n.durationMs).filter((x): x is number => typeof x === 'number' && x >= 0);
    const avgDurationMs = durations.length > 0
      ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
      : 0;

    return {
      taskId,
      aggregate: { totalTokens, completedNodes, failedNodes, avgDurationMs },
      timeline,
      failures,
    };
  }

  pauseTask(taskId: string): void {
    this.orchestrator.pause(taskId);
  }

  resumeTask(taskId: string): void {
    this.orchestrator.resume(taskId);
  }

  rerouteNode(taskId: string, nodeId: string, target: string): void {
    this.orchestrator.reroute(taskId, nodeId, target);
  }

  setDebateRounds(taskId: string, rounds: number, nodeId?: string): void {
    this.orchestrator.setDebateRounds(taskId, rounds, nodeId);
  }

  retryNode(
    taskId: string,
    nodeId: string,
    options?: { auto?: boolean; attempt?: number }
  ): { queued: boolean; newTaskId?: string; reason?: string } {
    const graph = this.getTaskGraph(taskId);
    if (!graph) {
      return { queued: false, reason: `Task graph not found for taskId=${taskId}` };
    }
    const node = graph.nodes.find(n => n.id === nodeId);
    if (!node) {
      return { queued: false, reason: `Node not found: ${nodeId}` };
    }

    const source = 'manual';
    const sourceId = `retry:${taskId}:${nodeId}:${Date.now()}`;
    const retryTaskId = this.makeDerivedTaskId('retry', taskId, nodeId);
    const content = node.content;
    const parsedIntent = node.intent;
    const attempt = options?.attempt || this.getRetryState(taskId, nodeId)?.attemptCount || 0;
    const metadata = JSON.stringify({
      retry_of: { taskId, nodeId },
      retry_attempt: attempt,
      auto_retry: !!options?.auto,
      branch_suggestion: this.suggestFixBranch(taskId, nodeId),
      created_by: 'orchestrator_retry',
    });

    const ins = this.db.prepare(`
      INSERT INTO bl_message_tasks (
        task_id, source, source_id, sender, content, parsed_intent, priority, status, estimated_tokens, metadata
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
    `).run(retryTaskId, source, sourceId, 'system', content, parsedIntent, 88, 300, metadata);
    const newTaskId = ins.changes > 0 ? retryTaskId : undefined;

    this.recordOrchestrationEvent({
      type: 'intervention_applied',
      taskId,
      nodeId,
      payload: {
        action: 'retry_node',
        newTaskId: newTaskId ?? null,
        parsedIntent,
        auto: !!options?.auto,
        attempt,
      },
      at: new Date().toISOString(),
    });

    return { queued: true, newTaskId };
  }

  createRepairTask(
    taskId: string,
    nodeId: string,
    options?: { error?: string; branchSuggestion?: string }
  ): { queued: boolean; newTaskId?: string; reason?: string; branchSuggestion?: string } {
    const graph = this.getTaskGraph(taskId);
    if (!graph) {
      return { queued: false, reason: `Task graph not found for taskId=${taskId}` };
    }
    const node = graph.nodes.find(n => n.id === nodeId);
    if (!node) {
      return { queued: false, reason: `Node not found: ${nodeId}` };
    }

    let error = String(options?.error || '').trim();
    if (!error) {
      const row = this.db.prepare(`
        SELECT payload_json
        FROM bl_orchestration_events
        WHERE task_id = ? AND node_id = ? AND event_type = 'node_failed'
        ORDER BY id DESC
        LIMIT 1
      `).get(taskId, nodeId) as { payload_json: string | null } | null;
      if (row?.payload_json) {
        try {
          const payload = JSON.parse(row.payload_json);
          error = String(payload?.error || '').trim();
        } catch {
          error = '';
        }
      }
    }
    if (!error) error = 'manual repair requested';

    const branchSuggestion = String(options?.branchSuggestion || this.suggestFixBranch(taskId, nodeId));
    const newTaskId = this.queueRepairBranchTask(taskId, nodeId, error, branchSuggestion) || undefined;
    return { queued: true, newTaskId, branchSuggestion };
  }

  updateOrchestrationPolicy(policy: {
    defaultDebateRounds?: number;
    highRiskThreshold?: number;
    voteMode?: 'majority' | 'weighted';
  }): void {
    this.orchestrator.updatePolicy(policy);
  }

  getRetryPolicy(): RetryPolicy {
    return { ...this.retryPolicy };
  }

  updateRetryPolicy(policy: Partial<RetryPolicy>): RetryPolicy {
    const next: RetryPolicy = {
      baseDelayMs: Math.max(100, Math.floor(policy.baseDelayMs ?? this.retryPolicy.baseDelayMs)),
      maxDelayMs: Math.max(1000, Math.floor(policy.maxDelayMs ?? this.retryPolicy.maxDelayMs)),
      maxAttempts: Math.max(0, Math.floor(policy.maxAttempts ?? this.retryPolicy.maxAttempts)),
      jitterRatio: Math.max(0, Math.min(1, Number(policy.jitterRatio ?? this.retryPolicy.jitterRatio))),
      retryableErrorPatterns: Array.isArray(policy.retryableErrorPatterns)
        ? policy.retryableErrorPatterns.map((x) => String(x).toLowerCase())
        : this.retryPolicy.retryableErrorPatterns,
    };
    if (next.maxDelayMs < next.baseDelayMs) {
      next.maxDelayMs = next.baseDelayMs;
    }
    this.db.prepare(`
      UPDATE bl_orchestration_retry_policy
      SET
        base_delay_ms = ?,
        max_delay_ms = ?,
        max_attempts = ?,
        jitter_ratio = ?,
        retryable_error_patterns_json = ?,
        updated_at = ?
      WHERE id = 1
    `).run(
      next.baseDelayMs,
      next.maxDelayMs,
      next.maxAttempts,
      next.jitterRatio,
      JSON.stringify(next.retryableErrorPatterns),
      new Date().toISOString(),
    );
    this.retryPolicy = next;
    return { ...next };
  }

  private ensureOrchestrationSchema(): void {
    this.db.run(`
      CREATE TABLE IF NOT EXISTS bl_orchestration_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        node_id TEXT,
        event_type TEXT NOT NULL,
        payload_json TEXT,
        created_at TEXT NOT NULL
      )
    `);
    this.db.run(`
      CREATE INDEX IF NOT EXISTS idx_orch_events_task_id
      ON bl_orchestration_events(task_id)
    `);
    this.db.run(`
      CREATE INDEX IF NOT EXISTS idx_orch_events_created_at
      ON bl_orchestration_events(created_at)
    `);
    this.db.run(`
      CREATE TABLE IF NOT EXISTS bl_orchestration_graphs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        graph_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
    `);
    this.db.run(`
      CREATE INDEX IF NOT EXISTS idx_orch_graphs_task_id
      ON bl_orchestration_graphs(task_id)
    `);
    this.db.run(`
      CREATE TABLE IF NOT EXISTS bl_orchestration_retries (
        task_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        next_retry_at TEXT,
        retry_status TEXT NOT NULL DEFAULT 'pending_retry',
        branch_suggestion TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (task_id, node_id)
      )
    `);
    this.db.run(`
      CREATE INDEX IF NOT EXISTS idx_orch_retries_status_next
      ON bl_orchestration_retries(retry_status, next_retry_at)
    `);
    this.db.run(`
      CREATE TABLE IF NOT EXISTS bl_orchestration_retry_policy (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        base_delay_ms INTEGER NOT NULL,
        max_delay_ms INTEGER NOT NULL,
        max_attempts INTEGER NOT NULL,
        jitter_ratio REAL NOT NULL,
        retryable_error_patterns_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    this.db.prepare(`
      INSERT OR IGNORE INTO bl_orchestration_retry_policy (
        id, base_delay_ms, max_delay_ms, max_attempts, jitter_ratio, retryable_error_patterns_json, updated_at
      ) VALUES (1, ?, ?, ?, ?, ?, ?)
    `).run(
      DEFAULT_RETRY_POLICY.baseDelayMs,
      DEFAULT_RETRY_POLICY.maxDelayMs,
      DEFAULT_RETRY_POLICY.maxAttempts,
      DEFAULT_RETRY_POLICY.jitterRatio,
      JSON.stringify(DEFAULT_RETRY_POLICY.retryableErrorPatterns),
      new Date().toISOString(),
    );
  }

  private ensureMessageTaskIdIntegrity(): void {
    const tableExists = this.db.prepare(`
      SELECT 1 AS ok
      FROM sqlite_master
      WHERE type = 'table' AND name = 'bl_message_tasks'
      LIMIT 1
    `).get() as { ok: number } | null;
    if (!tableExists) return;

    const hasTaskIdColumn = this.db.prepare(`
      SELECT 1 AS ok
      FROM pragma_table_info('bl_message_tasks')
      WHERE name = 'task_id'
      LIMIT 1
    `).get() as { ok: number } | null;
    if (!hasTaskIdColumn) return;

    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.db.run(`
        CREATE TABLE IF NOT EXISTS bl_message_tasks_taskid_backfill (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          rowid_ref INTEGER NOT NULL,
          old_task_id TEXT,
          source TEXT,
          source_id TEXT,
          sender TEXT,
          created_at TEXT,
          backfilled_at TEXT NOT NULL
        )
      `);

      this.db.run(`
        INSERT INTO bl_message_tasks_taskid_backfill (
          rowid_ref, old_task_id, source, source_id, sender, created_at, backfilled_at
        )
        SELECT rowid, task_id, source, source_id, sender, created_at, ?
        FROM bl_message_tasks
        WHERE task_id IS NULL OR TRIM(task_id) = ''
      `, new Date().toISOString());

      this.db.run(`
        UPDATE bl_message_tasks
        SET task_id = printf('legacy-%s-%016x', strftime('%Y%m%d%H%M%f','now'), rowid)
        WHERE task_id IS NULL OR TRIM(task_id) = ''
      `);

      this.db.run(`
        CREATE TRIGGER IF NOT EXISTS tr_bl_message_tasks_taskid_insert_guard
        BEFORE INSERT ON bl_message_tasks
        FOR EACH ROW
        WHEN NEW.task_id IS NULL OR TRIM(NEW.task_id) = ''
        BEGIN
          SELECT RAISE(ABORT, 'bl_message_tasks.task_id must be non-empty');
        END
      `);

      this.db.run(`
        CREATE TRIGGER IF NOT EXISTS tr_bl_message_tasks_taskid_update_guard
        BEFORE UPDATE OF task_id ON bl_message_tasks
        FOR EACH ROW
        WHEN NEW.task_id IS NULL OR TRIM(NEW.task_id) = ''
        BEGIN
          SELECT RAISE(ABORT, 'bl_message_tasks.task_id must be non-empty');
        END
      `);

      this.db.exec('COMMIT');
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  private inferFailureCause(error: string): string {
    const e = error.toLowerCase();
    if (e.includes('skill') && e.includes('not found')) return 'Skill entrypoint missing or dispatcher mismatch';
    if (e.includes('permission') || e.includes('denied')) return 'Permission denied by environment or policy';
    if (e.includes('timeout')) return 'Execution timeout or external dependency latency';
    if (e.includes('curl') || e.includes('connect')) return 'Daemon/socket or network connectivity issue';
    if (e.includes('json')) return 'Input/output payload malformed';
    return 'Unhandled runtime error in node execution path';
  }

  private suggestFailureFix(error: string): string {
    const e = error.toLowerCase();
    if (e.includes('skill') && e.includes('not found')) return 'Verify skill files and dispatcher root resolution, then reroute to available skill';
    if (e.includes('permission') || e.includes('denied')) return 'Lower-risk path or adjust runtime permission policy before retry';
    if (e.includes('timeout')) return 'Split node into smaller steps or increase timeout and retry';
    if (e.includes('curl') || e.includes('connect')) return 'Check daemon status/socket, restart daemon, then resume task';
    if (e.includes('json')) return 'Validate structured payload and schema before dispatch';
    return 'Inspect node event payload, patch failing handler, rerun node with /review guard';
  }

  private suggestFixBranch(taskId: string, nodeId: string): string {
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const safeTask = taskId.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 28);
    const safeNode = nodeId.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 20);
    return `codex/fix-${safeTask}-${safeNode}-${stamp}`;
  }

  private makeDerivedTaskId(kind: 'retry' | 'repair', taskId: string, nodeId: string): string {
    const safeTask = taskId.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 32) || 'task';
    const safeNode = nodeId.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 24) || 'node';
    return `${kind}-${safeTask}-${safeNode}-${Date.now()}`;
  }

  private saveTaskGraph(taskId: string, graph: TaskGraph): void {
    this.db.prepare(`
      INSERT INTO bl_orchestration_graphs (task_id, graph_json, created_at)
      VALUES (?, ?, ?)
    `).run(taskId, JSON.stringify(graph), new Date().toISOString());
  }

  private async executeTaskNode(intent: string, content: string): Promise<{ output: string; tokensUsed?: number }> {
    if (intent.startsWith('/')) {
      const r = await this.executeSkill(intent, content);
      return { output: r.output ?? JSON.stringify(r), tokensUsed: r.tokensUsed };
    }
    if (intent.startsWith('@')) {
      const r = await this.queueForAgent(intent, content);
      return { output: JSON.stringify(r), tokensUsed: r.tokensUsed };
    }
    if (intent.startsWith('solar_')) {
      const r = await this.executeShortcut(intent, content);
      return { output: r.output ?? JSON.stringify(r), tokensUsed: r.tokensUsed };
    }
    const r = await this.queueForManual(content);
    return { output: JSON.stringify(r), tokensUsed: r.tokensUsed };
  }

  /**
   * 执行 Skill
   */
  private async executeSkill(skill: string, content: string): Promise<any> {
    try {
      const skillName = skill.startsWith('/') ? skill.slice(1) : skill;
      const dispatch = await this.skillDispatcher.execute(skillName, content);
      return {
        type: 'skill',
        skill: skillName,
        output: dispatch.output,
        executionMode: dispatch.mode,
        entry: dispatch.entry,
        tokensUsed: 100,
      };
    } catch (error) {
      throw new Error(`Skill execution failed: ${error}`);
    }
  }

  /**
   * 执行 Shortcut
   */
  private async executeShortcut(shortcut: string, content: string): Promise<any> {
    try {
      let params = '{}';
      const jsonMatch = content.match(/\{.*\}/s);
      if (jsonMatch) {
        params = jsonMatch[0];
      }

      const result = await $`shortcuts run ${shortcut} -i ${params}`.text();
      return { type: 'shortcut', shortcut, output: result, tokensUsed: 0 };
    } catch (error) {
      throw new Error(`Shortcut execution failed: ${error}`);
    }
  }

  /**
   * 排队等待 Agent 处理
   */
  private async queueForAgent(agent: string, content: string): Promise<any> {
    console.log(`[MessageExecutor] Queuing for agent ${agent}: ${content.slice(0, 50)}`);
    return { type: 'agent', agent, status: 'queued_for_claude_session', tokensUsed: 0 };
  }

  /**
   * 排队等待手动处理
   */
  private async queueForManual(content: string): Promise<any> {
    console.log(`[MessageExecutor] Queuing for manual: ${content.slice(0, 50)}`);
    return { type: 'general', status: 'queued_for_manual', tokensUsed: 0 };
  }

  /**
   * 发送回复给用户
   */
  private async sendReplyToUser(taskId: number | string, result: any): Promise<void> {
    try {
      // 获取任务的发送者和来源信息
      const task = this.db.prepare(`
        SELECT sender, source FROM bl_message_tasks WHERE task_id = ?
      `).get(taskId) as { sender: string; source: string } | null;

      if (!task || !task.sender) {
        console.log(`[MessageExecutor] No sender info for task ${taskId}, skipping reply`);
        return;
      }

      // 格式化回复内容
      const content = result.output || result.answer ||
                      (typeof result === 'string' ? result : JSON.stringify(result, null, 2));

      const source = String(task.source || '').toLowerCase();
      if (source !== 'imessage' && source !== 'gmail' && source !== 'telegram') {
        console.log(`[MessageExecutor] Skip reply for unsupported source=${task.source} task=${taskId}`);
        return;
      }

      // 发送回复
      const reply = await this.replySender.send({
        channel: source as Channel,
        recipient: task.sender,
        replyType: 'quick_answer',
        content: content.slice(0, 2000) // 限制长度
      });

      if (reply.success) {
        console.log(`[MessageExecutor] ✓ Reply sent to ${task.sender} via ${task.source}`);
      } else {
        console.log(`[MessageExecutor] ✗ Reply failed: ${reply.error}`);
      }
    } catch (error) {
      console.error(`[MessageExecutor] Error sending reply:`, error);
    }
  }

  /**
   * 获取状态
   */
  getStatus(): {
    running: boolean;
    listeners: Record<string, boolean>;
    scheduler: ReturnType<QuotaScheduler['getStats']>;
  } {
    return {
      running: this.running,
      listeners: {
        imessage: !!this.iMessageListener,
        gmail: !!this.gmailListener,
        telegram: !!this.telegramListener
      },
      scheduler: this.scheduler.getStats()
    };
  }
}

// CLI / Standalone 模式
if (import.meta.main) {
  const configPath = `${process.env.HOME}/.solar/config.json`;
  let config: Partial<MessageExecutorConfig> = {};

  try {
    const configFile = Bun.file(configPath);
    if (await configFile.exists()) {
      config = await configFile.json();
    }
  } catch {}

  const executor = new MessageExecutor(config);

  process.on('SIGINT', () => {
    executor.stop();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    executor.stop();
    process.exit(0);
  });

  const cmd = process.argv[2];

  switch (cmd) {
    case 'start':
    case undefined:
      executor.start().then(() => {
        console.log('[MessageExecutor] Press Ctrl+C to stop');
      });
      break;
    case 'status':
      console.log(JSON.stringify(executor.getStatus(), null, 2));
      process.exit(0);
      break;
    default:
      console.log(`
Message Executor

Usage:
  bun run message-executor.ts [start]  Start the executor
  bun run message-executor.ts status   Show status

Configuration: ~/.solar/config.json
`);
  }
}
