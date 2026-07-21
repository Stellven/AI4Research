/**
 * Solar Evolver - 自我优化引擎
 *
 * 核心职责: 让 Solar 越来越强，不等用户提
 */

import { Database } from "bun:sqlite";

interface OptimizationStrategy {
  strategy_id: string;
  name: string;
  category: string;
  trigger_condition: string;
  action_spec: any;
  success_condition: string;
  confidence: number;
  risk_level: string;
  enabled: boolean;
}

interface OptimizationResult {
  strategy_id: string;
  executed: boolean;
  success: boolean;
  message: string;
  metrics_before?: any;
  metrics_after?: any;
}

export class SolarEvolver {
  private db: Database;

  constructor(dbPath?: string) {
    this.db = new Database(dbPath ?? process.env.SOLAR_DB_PATH ?? `${process.env.HOME}/.solar/db/solar.db`);
  }

  /**
   * 健康检查 - 发现问题
   */
  async healthCheck(): Promise<{
    status: "healthy" | "warning" | "critical";
    issues: string[];
    opportunities: string[];
  }> {
    const issues: string[] = [];
    const opportunities: string[] = [];

    // 1. 检查优化执行情况
    const health = this.db
      .query("SELECT * FROM v_evo_self_optimization_health")
      .get() as any;

    if (health) {
      if (health.pending_optimizations > 0) {
        issues.push(`有 ${health.pending_optimizations} 个待执行的优化策略`);
      }
      if (health.executed_count === 0) {
        issues.push("从未执行过自动优化");
      }
    }

    // 2. 检查成本
    const costCheck = this.db
      .query(`
        SELECT SUM(total_cost_usd) as today_cost
        FROM evo_daily_cost_summary
        WHERE date_bucket = date('now')
      `)
      .get() as any;

    if (costCheck?.today_cost > 15) {
      issues.push(`今日成本 $${costCheck.today_cost.toFixed(2)} 超过阈值`);
      opportunities.push("可启用模型降级策略");
    }

    // 3. 检查错误率
    const errorCheck = this.db
      .query(`
        SELECT
          COUNT(*) as total,
          SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors
        FROM evo_tool_calls
        WHERE created_at > datetime('now', '-1 hour')
      `)
      .get() as any;

    if (errorCheck && errorCheck.total > 0) {
      const errorRate = errorCheck.errors / errorCheck.total;
      if (errorRate > 0.05) {
        issues.push(`错误率 ${(errorRate * 100).toFixed(1)}% 超过 5%`);
      }
    }

    // 4. 检查记忆利用率
    const memoryCheck = this.db
      .query(`
        SELECT
          (SELECT COUNT(*) FROM evo_memory_semantic WHERE confidence > 0.3) as active_semantic,
          (SELECT COUNT(*) FROM evo_memory_semantic) as total_semantic
      `)
      .get() as any;

    if (memoryCheck && memoryCheck.total_semantic > 0) {
      const utilization = memoryCheck.active_semantic / memoryCheck.total_semantic;
      if (utilization < 0.2) {
        opportunities.push("记忆利用率低，建议整理");
      }
    }

    // 5. 检查未使用的能力
    const unusedSkills = this.db
      .query(`
        SELECT COUNT(*) as cnt
        FROM sys_skills s
        LEFT JOIN sys_invocations i ON s.skill_id = i.resource_id
        WHERE i.resource_id IS NULL
      `)
      .get() as any;

    if (unusedSkills?.cnt > 5) {
      opportunities.push(`有 ${unusedSkills.cnt} 个技能从未使用`);
    }

    const status =
      issues.length === 0
        ? "healthy"
        : issues.length <= 2
        ? "warning"
        : "critical";

    return { status, issues, opportunities };
  }

  /**
   * 获取待执行的优化策略
   */
  getPendingOptimizations(): OptimizationStrategy[] {
    const strategies = this.db
      .query(`
        SELECT s.*
        FROM evo_optimization_strategies s
        WHERE s.enabled = 1
        AND NOT EXISTS (
          SELECT 1 FROM evo_optimization_executions e
          WHERE e.strategy_id = s.strategy_id
          AND e.executed_at > datetime('now', '-' || s.cooldown_seconds || ' seconds')
        )
      `)
      .all() as any[];

    return strategies.map((s) => ({
      ...s,
      action_spec: s.action_spec ? JSON.parse(s.action_spec) : {},
    }));
  }

  /**
   * 检查策略触发条件
   */
  checkTriggerCondition(strategy: OptimizationStrategy): boolean {
    try {
      const result = this.db.query(strategy.trigger_condition).get();
      return result !== null;
    } catch (e) {
      console.error(`[Evolver] 触发条件检查失败: ${strategy.strategy_id}`, e);
      return false;
    }
  }

  /**
   * 执行单个优化策略
   */
  async executeStrategy(strategy: OptimizationStrategy): Promise<OptimizationResult> {
    console.log(`[Evolver] 执行策略: ${strategy.name}`);

    const executionId = `exec_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;

    try {
      // 记录开始执行
      this.db.run(
        `
        INSERT INTO evo_optimization_executions (
          execution_id, strategy_id, trigger_details, status, started_at
        ) VALUES (?, ?, ?, 'running', CURRENT_TIMESTAMP)
        `,
        [executionId, strategy.strategy_id, JSON.stringify({ triggered_by: "evolver" })]
      );

      // 执行优化动作
      const actionSpec = strategy.action_spec;
      let success = false;
      let message = "";

      switch (actionSpec.type) {
        case "update_routing_rule":
          success = await this.executeRoutingUpdate(actionSpec);
          message = success ? "路由规则已更新" : "路由规则更新失败";
          break;

        case "stabilize_system_prompt":
          success = await this.executePromptStabilization(actionSpec);
          message = success ? "提示词已稳定" : "提示词稳定失败";
          break;

        case "adjust_routing":
          success = await this.executeRoutingAdjustment(actionSpec);
          message = success ? "路由已调整" : "路由调整失败";
          break;

        case "upgrade_model":
          success = await this.executeModelUpgrade(actionSpec);
          message = success ? "模型已升级" : "模型升级失败";
          break;

        case "cleanup_memory":
          success = await this.executeMemoryCleanup(actionSpec);
          message = success ? "记忆已清理" : "记忆清理失败";
          break;

        default:
          message = `未知的优化类型: ${actionSpec.type}`;
      }

      // 更新执行记录
      this.db.run(
        `
        UPDATE evo_optimization_executions
        SET status = ?, completed_at = CURRENT_TIMESTAMP, result_summary = ?
        WHERE execution_id = ?
        `,
        [success ? "success" : "failed", message, executionId]
      );

      // 记录到本体学习事件
      this.db.run(
        `
        INSERT INTO ont_learning_events (event_id, event_type, details, source_type)
        VALUES (?, 'self_optimization', ?, 'evolver')
        `,
        [
          `evt_${Date.now()}`,
          JSON.stringify({
            strategy_id: strategy.strategy_id,
            success,
            message,
          }),
        ]
      );

      return {
        strategy_id: strategy.strategy_id,
        executed: true,
        success,
        message,
      };
    } catch (error: any) {
      // 记录失败
      this.db.run(
        `
        UPDATE evo_optimization_executions
        SET status = 'failed', completed_at = CURRENT_TIMESTAMP, result_summary = ?
        WHERE execution_id = ?
        `,
        [error.message, executionId]
      );

      return {
        strategy_id: strategy.strategy_id,
        executed: true,
        success: false,
        message: `执行失败: ${error.message}`,
      };
    }
  }

  /**
   * 执行路由规则更新
   */
  private async executeRoutingUpdate(spec: any): Promise<boolean> {
    try {
      for (const action of spec.actions || []) {
        this.db.run(
          `
          UPDATE evo_model_routing_rules
          SET target_model = COALESCE(?, target_model),
              enabled = COALESCE(?, enabled),
              updated_at = CURRENT_TIMESTAMP
          WHERE rule_id = ?
          `,
          [action.changes?.target_model, action.changes?.enabled, action.rule_id]
        );
      }

      for (const config of spec.config_updates || []) {
        this.db.run(
          `
          INSERT OR REPLACE INTO evo_runtime_config (config_key, config_value, updated_at)
          VALUES (?, ?, CURRENT_TIMESTAMP)
          `,
          [config.key, JSON.stringify(config.value)]
        );
      }

      return true;
    } catch {
      return false;
    }
  }

  /**
   * 执行提示词稳定化
   */
  private async executePromptStabilization(spec: any): Promise<boolean> {
    try {
      for (const config of spec.config_updates || []) {
        this.db.run(
          `
          INSERT OR REPLACE INTO evo_runtime_config (config_key, config_value, updated_at)
          VALUES (?, ?, CURRENT_TIMESTAMP)
          `,
          [config.key, JSON.stringify(config.value)]
        );
      }
      return true;
    } catch {
      return false;
    }
  }

  /**
   * 执行路由调整
   */
  private async executeRoutingAdjustment(spec: any): Promise<boolean> {
    try {
      for (const action of spec.actions || []) {
        if (action.action === "enable_fallback_model") {
          this.db.run(
            `
            INSERT OR REPLACE INTO evo_runtime_config (config_key, config_value, updated_at)
            VALUES ('fallback_model_enabled', ?, CURRENT_TIMESTAMP)
            `,
            [JSON.stringify({ primary: action.primary, fallback: action.fallback })]
          );
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  /**
   * 执行模型升级
   */
  private async executeModelUpgrade(spec: any): Promise<boolean> {
    try {
      for (const action of spec.actions || []) {
        if (action.action === "switch_model") {
          this.db.run(
            `
            UPDATE evo_model_routing_rules
            SET target_model = ?
            WHERE target_model = ?
            `,
            [action.to, action.from]
          );
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  /**
   * 执行记忆清理
   */
  private async executeMemoryCleanup(spec: any): Promise<boolean> {
    try {
      for (const action of spec.actions || []) {
        switch (action.action) {
          case "archive_low_importance_episodic":
            this.db.run(
              `
              UPDATE evo_memory_episodic
              SET importance = importance * 0.5
              WHERE importance < ?
              AND occurred_at < datetime('now', '-' || ? || ' days')
              `,
              [action.threshold, action.older_than_days]
            );
            break;

          case "prune_unused_procedural":
            this.db.run(
              `
              DELETE FROM evo_memory_procedural
              WHERE execution_count < ?
              AND created_at < datetime('now', '-' || ? || ' days')
              `,
              [action.execution_count_below, action.older_than_days]
            );
            break;
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  /**
   * 执行所有待定优化
   */
  async runOptimizations(): Promise<OptimizationResult[]> {
    console.log("[Evolver] 开始自我优化...");

    const results: OptimizationResult[] = [];
    const strategies = this.getPendingOptimizations();

    console.log(`[Evolver] 发现 ${strategies.length} 个待检查策略`);

    for (const strategy of strategies) {
      // 检查触发条件
      const shouldTrigger = this.checkTriggerCondition(strategy);

      if (shouldTrigger) {
        console.log(`[Evolver] 策略 ${strategy.name} 触发条件满足，执行优化`);
        const result = await this.executeStrategy(strategy);
        results.push(result);
      } else {
        results.push({
          strategy_id: strategy.strategy_id,
          executed: false,
          success: false,
          message: "触发条件不满足",
        });
      }
    }

    console.log(`[Evolver] 优化完成，执行 ${results.filter((r) => r.executed).length} 个策略`);

    return results;
  }

  /**
   * 生成演进报告
   */
  generateReport(): string {
    const health = this.healthCheck();

    // 获取执行历史
    const executions = this.db
      .query(`
        SELECT strategy_id, status, result_summary, executed_at
        FROM evo_optimization_executions
        ORDER BY executed_at DESC
        LIMIT 10
      `)
      .all() as any[];

    // 获取学习事件
    const learnings = this.db
      .query(`
        SELECT event_type, details, occurred_at
        FROM ont_learning_events
        WHERE source_type = 'evolver'
        ORDER BY occurred_at DESC
        LIMIT 5
      `)
      .all() as any[];

    let report = `
╔═══════════════════════════════════════════════════════════════╗
║           🧬 Solar 自我演进报告                                ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  健康状态: ${health.status.toUpperCase().padEnd(10)}                               ║
║                                                               ║`;

    if (health.issues.length > 0) {
      report += `\n║  发现问题:                                                    ║`;
      for (const issue of health.issues) {
        report += `\n║  • ${issue.padEnd(57)}║`;
      }
    }

    if (health.opportunities.length > 0) {
      report += `\n║                                                               ║`;
      report += `\n║  优化机会:                                                    ║`;
      for (const opp of health.opportunities) {
        report += `\n║  • ${opp.padEnd(57)}║`;
      }
    }

    report += `\n║                                                               ║`;
    report += `\n║  最近执行:                                                    ║`;

    if (executions.length === 0) {
      report += `\n║  (无执行记录)                                                 ║`;
    } else {
      for (const exec of executions.slice(0, 5)) {
        const status = exec.status === "success" ? "✓" : "✗";
        report += `\n║  ${status} ${exec.strategy_id.slice(0, 25).padEnd(25)} ${exec.executed_at?.slice(0, 10) || ""}  ║`;
      }
    }

    report += `\n║                                                               ║`;
    report += `\n╚═══════════════════════════════════════════════════════════════╝`;

    return report;
  }

  close() {
    this.db.close();
  }
}

// ==================== CLI ====================

if (import.meta.main) {
  const evolver = new SolarEvolver();
  const command = process.argv[2] || "check";

  switch (command) {
    case "check":
      console.log("[Evolver] 健康检查...\n");
      evolver.healthCheck().then((health) => {
        console.log(`状态: ${health.status}`);
        console.log("\n问题:", health.issues.length ? health.issues.join("\n  ") : "无");
        console.log("\n机会:", health.opportunities.length ? health.opportunities.join("\n  ") : "无");
        evolver.close();
      });
      break;

    case "optimize":
      console.log("[Evolver] 执行优化...\n");
      evolver.runOptimizations().then((results) => {
        console.log("\n结果:");
        for (const r of results) {
          const icon = r.executed ? (r.success ? "✓" : "✗") : "○";
          console.log(`  ${icon} ${r.strategy_id}: ${r.message}`);
        }
        evolver.close();
      });
      break;

    case "report":
      console.log(evolver.generateReport());
      evolver.close();
      break;

    default:
      console.log("用法: bun run optimize.ts [check|optimize|report]");
      evolver.close();
  }
}
