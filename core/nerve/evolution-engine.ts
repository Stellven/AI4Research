/**
 * Solar Self-Evolution Engine
 *
 * 自主优化执行引擎 - 读取数据库决策，执行系统优化
 *
 * 核心职责:
 * 1. 定期检查待执行的优化
 * 2. 执行已批准的优化动作
 * 3. 验证优化效果
 * 4. 自动回滚失败的优化
 * 5. 生成学习信号
 */

import Database from 'better-sqlite3';
import { EventEmitter } from 'events';

// ============================================================================
// Types
// ============================================================================

interface OptimizationExecution {
  execution_id: string;
  strategy_id: string;
  recommendation_id: string | null;
  status: 'pending' | 'approved' | 'executing' | 'validating' | 'success' | 'failed' | 'rolled_back';
  execution_mode: 'auto' | 'supervised' | 'manual';
  pre_state: Record<string, unknown>;
  executed_action: Record<string, unknown> | null;
  post_state: Record<string, unknown> | null;
  confidence: number;
}

interface OptimizationStrategy {
  strategy_id: string;
  strategy_name: string;
  strategy_type: string;
  action_template: ActionTemplate;
  success_condition: string | null;
  rollback_template: ActionTemplate | null;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
}

interface ActionTemplate {
  type: string;
  actions: ActionItem[];
  config_updates?: ConfigUpdate[];
  duration_hours?: number;
}

interface ActionItem {
  action: string;
  [key: string]: unknown;
}

interface ConfigUpdate {
  key: string;
  value: unknown;
}

interface RuntimeConfig {
  [key: string]: unknown;
}

// ============================================================================
// Evolution Engine
// ============================================================================

export class EvolutionEngine extends EventEmitter {
  private db: Database.Database;
  private running = false;
  private checkInterval: NodeJS.Timeout | null = null;
  private validationTimers: Map<string, NodeJS.Timeout> = new Map();

  // 验证窗口 (默认 5 分钟)
  private validationWindowMs = 5 * 60 * 1000;

  constructor(dbPath: string) {
    super();
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
  }

  // ============================================================================
  // Lifecycle
  // ============================================================================

  /**
   * 启动自优化引擎
   */
  start(intervalMs = 60000): void {
    if (this.running) return;

    this.running = true;
    this.emit('started');

    // 立即执行一次检查
    this.checkAndExecute();

    // 定期检查
    this.checkInterval = setInterval(() => {
      this.checkAndExecute();
    }, intervalMs);

    console.log(`[EvolutionEngine] Started with ${intervalMs}ms interval`);
  }

  /**
   * 停止引擎
   */
  stop(): void {
    this.running = false;

    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }

    // 清理所有验证定时器
    for (const timer of this.validationTimers.values()) {
      clearTimeout(timer);
    }
    this.validationTimers.clear();

    this.emit('stopped');
    console.log('[EvolutionEngine] Stopped');
  }

  // ============================================================================
  // Core Loop
  // ============================================================================

  /**
   * 主循环: 检查并执行优化
   */
  private async checkAndExecute(): Promise<void> {
    try {
      // 1. 检查是否启用自动优化
      if (!this.isAutoOptimizationEnabled()) {
        return;
      }

      // 2. 处理待执行的优化
      const pendingExecutions = this.getPendingExecutions();

      for (const execution of pendingExecutions) {
        await this.processExecution(execution);
      }

      // 3. 检查需要验证的优化
      const validatingExecutions = this.getValidatingExecutions();

      for (const execution of validatingExecutions) {
        await this.validateExecution(execution);
      }

      // 4. 触发策略检查 (主动发现优化机会)
      await this.checkStrategies();

    } catch (error) {
      console.error('[EvolutionEngine] Check cycle error:', error);
      this.emit('error', error);
    }
  }

  // ============================================================================
  // Execution Processing
  // ============================================================================

  /**
   * 处理单个优化执行
   */
  private async processExecution(execution: OptimizationExecution): Promise<void> {
    const strategy = this.getStrategy(execution.strategy_id);
    if (!strategy) {
      this.markExecutionFailed(execution.execution_id, 'Strategy not found');
      return;
    }

    // 检查置信度
    const minConfidence = this.getConfig<number>('min_auto_execute_confidence', 0.8);

    if (execution.status === 'pending') {
      // 根据风险等级和置信度决定是否自动批准
      if (this.shouldAutoApprove(strategy, execution.confidence, minConfidence)) {
        this.approveExecution(execution.execution_id);
        execution.status = 'approved';
      } else {
        // 需要人工审批，发出事件
        this.emit('approval_required', {
          execution_id: execution.execution_id,
          strategy: strategy.strategy_name,
          confidence: execution.confidence,
          risk_level: strategy.risk_level
        });
        return;
      }
    }

    if (execution.status === 'approved') {
      // 执行优化
      await this.executeOptimization(execution, strategy);
    }
  }

  /**
   * 执行优化动作
   */
  private async executeOptimization(
    execution: OptimizationExecution,
    strategy: OptimizationStrategy
  ): Promise<void> {
    this.emit('executing', {
      execution_id: execution.execution_id,
      strategy: strategy.strategy_name
    });

    try {
      // 标记为执行中
      this.db.prepare(`
        UPDATE evo_optimization_executions
        SET status = 'executing', executed_at = datetime('now')
        WHERE execution_id = ?
      `).run(execution.execution_id);

      // 执行动作
      const results = await this.executeActions(strategy.action_template);

      // 记录执行结果
      const postState = this.captureSystemState();

      this.db.prepare(`
        UPDATE evo_optimization_executions
        SET
          executed_action = ?,
          post_state = ?,
          status = 'validating'
        WHERE execution_id = ?
      `).run(
        JSON.stringify(results),
        JSON.stringify(postState),
        execution.execution_id
      );

      // 设置验证定时器
      this.scheduleValidation(execution.execution_id, strategy);

      this.emit('executed', {
        execution_id: execution.execution_id,
        results
      });

    } catch (error) {
      this.markExecutionFailed(execution.execution_id, String(error));
      this.emit('execution_failed', {
        execution_id: execution.execution_id,
        error
      });
    }
  }

  /**
   * 执行具体动作
   */
  private async executeActions(template: ActionTemplate): Promise<Record<string, unknown>> {
    const results: Record<string, unknown> = {
      type: template.type,
      actions_executed: [],
      config_updates: []
    };

    // 执行动作列表
    for (const action of template.actions) {
      const result = await this.executeAction(action);
      (results.actions_executed as unknown[]).push({
        action: action.action,
        success: result.success,
        result: result.data
      });
    }

    // 执行配置更新
    if (template.config_updates) {
      for (const update of template.config_updates) {
        this.updateConfig(update.key, update.value, 'system:evolution_engine');
        (results.config_updates as unknown[]).push({
          key: update.key,
          value: update.value
        });
      }
    }

    return results;
  }

  /**
   * 执行单个动作
   */
  private async executeAction(action: ActionItem): Promise<{ success: boolean; data?: unknown }> {
    switch (action.action) {
      case 'switch_model':
        return this.actionSwitchModel(action.from as string, action.to as string);

      case 'enable_fallback_model':
        return this.actionEnableFallback(action.primary as string, action.fallback as string);

      case 'update_routing_weight':
        return this.actionUpdateRoutingWeight(action.tool as string, action.weight_delta as number);

      case 'pin_system_prompt_version':
        return this.actionPinSystemPrompt(action.duration_hours as number);

      case 'disable_dynamic_context_injection':
        return this.actionDisableDynamicContext(action.scope as string);

      case 'reduce_max_tokens':
        return this.actionReduceMaxTokens(action.reduction_percent as number);

      case 'archive_low_importance_episodic':
        return this.actionArchiveEpisodicMemory(
          action.threshold as number,
          action.older_than_days as number
        );

      case 'consolidate_semantic_duplicates':
        return this.actionConsolidateSemanticMemory(action.similarity_threshold as number);

      case 'prune_unused_procedural':
        return this.actionPruneProceduralMemory(
          action.execution_count_below as number,
          action.older_than_days as number
        );

      case 'create_procedural_memory':
        return this.actionCreateProceduralMemory(action.pattern as string);

      case 'add_pre_check':
        return this.actionAddPreCheck(action.tool as string, action.check_type as string);

      default:
        console.warn(`[EvolutionEngine] Unknown action: ${action.action}`);
        return { success: false, data: { error: 'Unknown action' } };
    }
  }

  // ============================================================================
  // Action Implementations
  // ============================================================================

  private actionSwitchModel(from: string, to: string): { success: boolean; data?: unknown } {
    try {
      // 更新路由规则
      this.db.prepare(`
        UPDATE evo_model_routing_rules
        SET target_model = ?, updated_at = datetime('now'), last_modified_by = 'system:evolution'
        WHERE target_model = ? AND enabled = TRUE
      `).run(to, from);

      // 更新默认模型配置
      if (from === this.getConfig('default_model', 'sonnet')) {
        this.updateConfig('default_model', to, 'system:evolution');
      }

      return { success: true, data: { from, to } };
    } catch (error) {
      return { success: false, data: { error: String(error) } };
    }
  }

  private actionEnableFallback(primary: string, fallback: string): { success: boolean; data?: unknown } {
    try {
      this.db.prepare(`
        UPDATE evo_model_routing_rules
        SET fallback_model = ?, updated_at = datetime('now')
        WHERE target_model = ?
      `).run(fallback, primary);

      return { success: true, data: { primary, fallback } };
    } catch (error) {
      return { success: false, data: { error: String(error) } };
    }
  }

  private actionUpdateRoutingWeight(tool: string, weightDelta: number): { success: boolean; data?: unknown } {
    try {
      this.db.prepare(`
        UPDATE evo_model_routing_rules
        SET
          traffic_weight = MAX(0, MIN(1, traffic_weight + ?)),
          updated_at = datetime('now')
        WHERE condition_expression LIKE ?
      `).run(weightDelta, `%${tool}%`);

      return { success: true, data: { tool, weightDelta } };
    } catch (error) {
      return { success: false, data: { error: String(error) } };
    }
  }

  private actionPinSystemPrompt(durationHours: number): { success: boolean; data?: unknown } {
    this.updateConfig('system_prompt_pinned', true, 'system:evolution');
    this.updateConfig('system_prompt_pin_until',
      new Date(Date.now() + durationHours * 3600 * 1000).toISOString(),
      'system:evolution'
    );
    return { success: true, data: { durationHours } };
  }

  private actionDisableDynamicContext(scope: string): { success: boolean; data?: unknown } {
    this.updateConfig(`dynamic_context_${scope}_enabled`, false, 'system:evolution');
    return { success: true, data: { scope } };
  }

  private actionReduceMaxTokens(reductionPercent: number): { success: boolean; data?: unknown } {
    const currentMax = this.getConfig<number>('max_output_tokens', 4096);
    const newMax = Math.floor(currentMax * (1 - reductionPercent / 100));
    this.updateConfig('max_output_tokens', newMax, 'system:evolution');
    return { success: true, data: { from: currentMax, to: newMax } };
  }

  private actionArchiveEpisodicMemory(threshold: number, olderThanDays: number): { success: boolean; data?: unknown } {
    try {
      const result = this.db.prepare(`
        DELETE FROM evo_memory_episodic
        WHERE importance < ?
          AND last_retrieved < datetime('now', '-' || ? || ' days')
      `).run(threshold, olderThanDays);

      return { success: true, data: { deleted: result.changes } };
    } catch (error) {
      return { success: false, data: { error: String(error) } };
    }
  }

  private actionConsolidateSemanticMemory(similarityThreshold: number): { success: boolean; data?: unknown } {
    // 实际实现需要向量相似度计算，这里简化处理
    try {
      const result = this.db.prepare(`
        DELETE FROM evo_memory_semantic
        WHERE memory_id IN (
          SELECT m2.memory_id
          FROM evo_memory_semantic m1
          JOIN evo_memory_semantic m2 ON m1.namespace = m2.namespace
            AND m1.key = m2.key
            AND m1.memory_id < m2.memory_id
            AND m1.confidence >= m2.confidence
        )
      `).run();

      return { success: true, data: { consolidated: result.changes } };
    } catch (error) {
      return { success: false, data: { error: String(error) } };
    }
  }

  private actionPruneProceduralMemory(executionCountBelow: number, olderThanDays: number): { success: boolean; data?: unknown } {
    try {
      const result = this.db.prepare(`
        DELETE FROM evo_memory_procedural
        WHERE execution_count < ?
          AND created_at < datetime('now', '-' || ? || ' days')
      `).run(executionCountBelow, olderThanDays);

      return { success: true, data: { pruned: result.changes } };
    } catch (error) {
      return { success: false, data: { error: String(error) } };
    }
  }

  private actionCreateProceduralMemory(pattern: string): { success: boolean; data?: unknown } {
    try {
      const memoryId = `proc:${pattern}:${Date.now()}`;
      this.db.prepare(`
        INSERT INTO evo_memory_procedural (
          memory_id, procedure_name, trigger_conditions, steps
        ) VALUES (?, ?, ?, ?)
      `).run(
        memoryId,
        pattern,
        JSON.stringify({ type: 'auto_learned', pattern }),
        JSON.stringify([{ step: 'execute_learned_pattern', pattern }])
      );

      return { success: true, data: { memory_id: memoryId } };
    } catch (error) {
      return { success: false, data: { error: String(error) } };
    }
  }

  private actionAddPreCheck(tool: string, checkType: string): { success: boolean; data?: unknown } {
    // 记录到工具配置
    this.updateConfig(`tool_precheck_${tool}`, {
      enabled: true,
      check_type: checkType,
      created_at: new Date().toISOString()
    }, 'system:evolution');

    return { success: true, data: { tool, checkType } };
  }

  // ============================================================================
  // Validation
  // ============================================================================

  /**
   * 安排验证
   */
  private scheduleValidation(executionId: string, strategy: OptimizationStrategy): void {
    const timer = setTimeout(() => {
      this.validateExecution({ execution_id: executionId } as OptimizationExecution);
      this.validationTimers.delete(executionId);
    }, this.validationWindowMs);

    this.validationTimers.set(executionId, timer);
  }

  /**
   * 验证优化效果
   */
  private async validateExecution(execution: { execution_id: string }): Promise<void> {
    const fullExecution = this.db.prepare(`
      SELECT * FROM evo_optimization_executions WHERE execution_id = ?
    `).get(execution.execution_id) as OptimizationExecution;

    if (!fullExecution || fullExecution.status !== 'validating') {
      return;
    }

    const strategy = this.getStrategy(fullExecution.strategy_id);
    if (!strategy) {
      this.markExecutionFailed(execution.execution_id, 'Strategy not found during validation');
      return;
    }

    try {
      // 执行验证条件
      let passed = true;
      let reason = 'Validation successful';

      if (strategy.success_condition) {
        const result = this.db.prepare(strategy.success_condition).get();
        passed = !!result;
        reason = passed ? 'Success condition met' : 'Success condition not met';
      }

      // 更新验证结果
      const validationResult = {
        passed,
        reason,
        validated_at: new Date().toISOString(),
        pre_state: fullExecution.pre_state,
        post_state: this.captureSystemState()
      };

      this.db.prepare(`
        UPDATE evo_optimization_executions
        SET
          validation_result = ?,
          validation_passed = ?,
          validated_at = datetime('now')
        WHERE execution_id = ?
      `).run(
        JSON.stringify(validationResult),
        passed ? 1 : 0,
        execution.execution_id
      );

      if (!passed && strategy.rollback_template) {
        // 执行回滚
        await this.executeActions(strategy.rollback_template);
        this.emit('rolled_back', {
          execution_id: execution.execution_id,
          reason
        });
      } else if (passed) {
        this.emit('validation_passed', {
          execution_id: execution.execution_id
        });
      }

    } catch (error) {
      this.markExecutionFailed(execution.execution_id, `Validation error: ${error}`);
    }
  }

  // ============================================================================
  // Strategy Checking
  // ============================================================================

  /**
   * 主动检查所有策略，发现优化机会
   */
  private async checkStrategies(): Promise<void> {
    const strategies = this.db.prepare(`
      SELECT * FROM evo_optimization_strategies WHERE enabled = TRUE
    `).all() as OptimizationStrategy[];

    for (const strategy of strategies) {
      // 检查冷却期
      const recentExecution = this.db.prepare(`
        SELECT 1 FROM evo_optimization_executions
        WHERE strategy_id = ?
          AND status IN ('executing', 'validating', 'success')
          AND created_at >= datetime('now', '-' || ? || ' seconds')
        LIMIT 1
      `).get(strategy.strategy_id, (strategy as any).cooldown_seconds);

      if (recentExecution) continue;

      // 检查触发条件
      try {
        const triggered = this.db.prepare((strategy as any).trigger_condition).get();

        if (triggered) {
          // 生成建议并创建执行记录
          this.createOptimizationExecution(strategy);
        }
      } catch (error) {
        console.error(`[EvolutionEngine] Strategy check error for ${strategy.strategy_id}:`, error);
      }
    }
  }

  /**
   * 创建优化执行记录
   */
  private createOptimizationExecution(strategy: OptimizationStrategy): void {
    const executionId = `exec:${strategy.strategy_id}:${Date.now()}`;
    const confidence = this.calculateConfidence(strategy);

    this.db.prepare(`
      INSERT INTO evo_optimization_executions (
        execution_id, strategy_id, status, execution_mode,
        pre_state, confidence
      ) VALUES (?, ?, ?, ?, ?, ?)
    `).run(
      executionId,
      strategy.strategy_id,
      'pending',
      strategy.risk_level === 'low' ? 'auto' : 'supervised',
      JSON.stringify(this.captureSystemState()),
      confidence
    );

    this.emit('optimization_created', {
      execution_id: executionId,
      strategy: strategy.strategy_name,
      confidence
    });
  }

  // ============================================================================
  // Helpers
  // ============================================================================

  private isAutoOptimizationEnabled(): boolean {
    const config = this.db.prepare(`
      SELECT config_value FROM evo_runtime_config WHERE config_key = 'auto_optimization_enabled'
    `).get() as { config_value: string } | undefined;

    return config?.config_value === 'true';
  }

  private getPendingExecutions(): OptimizationExecution[] {
    return this.db.prepare(`
      SELECT * FROM evo_optimization_executions
      WHERE status IN ('pending', 'approved')
      ORDER BY created_at
    `).all() as OptimizationExecution[];
  }

  private getValidatingExecutions(): OptimizationExecution[] {
    return this.db.prepare(`
      SELECT * FROM evo_optimization_executions
      WHERE status = 'validating'
        AND validated_at IS NULL
        AND executed_at < datetime('now', '-5 minutes')
    `).all() as OptimizationExecution[];
  }

  private getStrategy(strategyId: string): OptimizationStrategy | null {
    const row = this.db.prepare(`
      SELECT * FROM evo_optimization_strategies WHERE strategy_id = ?
    `).get(strategyId) as any;

    if (!row) return null;

    return {
      ...row,
      action_template: JSON.parse(row.action_template),
      rollback_template: row.rollback_template ? JSON.parse(row.rollback_template) : null
    };
  }

  private getConfig<T>(key: string, defaultValue: T): T {
    const row = this.db.prepare(`
      SELECT config_value FROM evo_runtime_config WHERE config_key = ?
    `).get(key) as { config_value: string } | undefined;

    if (!row) return defaultValue;

    try {
      return JSON.parse(row.config_value) as T;
    } catch {
      return row.config_value as unknown as T;
    }
  }

  private updateConfig(key: string, value: unknown, changedBy: string): void {
    const jsonValue = JSON.stringify(value);

    this.db.prepare(`
      INSERT INTO evo_runtime_config (config_id, config_key, config_value, changed_by, changed_at)
      VALUES (?, ?, ?, ?, datetime('now'))
      ON CONFLICT(config_key) DO UPDATE SET
        config_value = excluded.config_value,
        changed_by = excluded.changed_by,
        changed_at = excluded.changed_at,
        updated_at = datetime('now')
    `).run(`config:${key}`, key, jsonValue, changedBy);
  }

  private shouldAutoApprove(
    strategy: OptimizationStrategy,
    confidence: number,
    minConfidence: number
  ): boolean {
    if (confidence < minConfidence) return false;

    switch (strategy.risk_level) {
      case 'low':
        return true;
      case 'medium':
        return confidence >= 0.85;
      case 'high':
        return confidence >= 0.95;
      case 'critical':
        return false; // 永远需要人工审批
      default:
        return false;
    }
  }

  private approveExecution(executionId: string): void {
    this.db.prepare(`
      UPDATE evo_optimization_executions
      SET status = 'approved', approved_at = datetime('now'), approver = 'system'
      WHERE execution_id = ?
    `).run(executionId);
  }

  private markExecutionFailed(executionId: string, error: string): void {
    this.db.prepare(`
      UPDATE evo_optimization_executions
      SET status = 'failed', error_message = ?, completed_at = datetime('now')
      WHERE execution_id = ?
    `).run(error, executionId);
  }

  private calculateConfidence(strategy: OptimizationStrategy): number {
    // 基于历史成功率计算置信度
    const stats = this.db.prepare(`
      SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
      FROM evo_optimization_executions
      WHERE strategy_id = ?
    `).get(strategy.strategy_id) as { total: number; success: number };

    if (stats.total === 0) {
      // 新策略，使用默认阈值
      return (strategy as any).auto_execute_threshold || 0.8;
    }

    // 历史成功率
    const historicalRate = stats.success / stats.total;

    // 混合历史成功率和策略默认阈值
    return 0.7 * historicalRate + 0.3 * ((strategy as any).auto_execute_threshold || 0.8);
  }

  private captureSystemState(): Record<string, unknown> {
    // 捕获当前系统状态快照
    const dailyCost = this.db.prepare(`
      SELECT total_cost_usd FROM evo_daily_cost_summary
      WHERE date_bucket = date('now')
    `).get() as { total_cost_usd: number } | undefined;

    const routingRules = this.db.prepare(`
      SELECT rule_id, target_model, enabled FROM evo_model_routing_rules
    `).all();

    const configs = this.db.prepare(`
      SELECT config_key, config_value FROM evo_runtime_config
    `).all();

    return {
      captured_at: new Date().toISOString(),
      daily_cost_usd: dailyCost?.total_cost_usd || 0,
      routing_rules: routingRules,
      configs: configs
    };
  }
}

// ============================================================================
// Export singleton
// ============================================================================

let engineInstance: EvolutionEngine | null = null;

export function getEvolutionEngine(dbPath?: string): EvolutionEngine {
  if (!engineInstance && dbPath) {
    engineInstance = new EvolutionEngine(dbPath);
  }
  if (!engineInstance) {
    throw new Error('EvolutionEngine not initialized. Call with dbPath first.');
  }
  return engineInstance;
}

// ============================================================================
// CLI Entry
// ============================================================================

if (require.main === module) {
  const dbPath = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

  const engine = new EvolutionEngine(dbPath);

  // 事件监听
  engine.on('started', () => console.log('🚀 Evolution Engine started'));
  engine.on('optimization_created', (e) => console.log('📋 Optimization created:', e));
  engine.on('executing', (e) => console.log('⚡ Executing:', e));
  engine.on('executed', (e) => console.log('✅ Executed:', e));
  engine.on('validation_passed', (e) => console.log('✓ Validation passed:', e));
  engine.on('rolled_back', (e) => console.log('↩️ Rolled back:', e));
  engine.on('approval_required', (e) => console.log('⏳ Approval required:', e));
  engine.on('error', (e) => console.error('❌ Error:', e));

  // 启动引擎 (每分钟检查一次)
  engine.start(60000);

  // 优雅退出
  process.on('SIGINT', () => {
    console.log('\nShutting down...');
    engine.stop();
    process.exit(0);
  });
}
