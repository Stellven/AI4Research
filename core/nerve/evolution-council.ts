/**
 * Solar Evolution Council - 多 Agent 决策委员会引擎
 *
 * 核心理念：策略由 AI 自主发现、讨论、制定，而非硬编码
 *
 * 决策流程:
 * 1. Observer (Haiku) - 持续监控，发现异常
 * 2. Analyst (Sonnet) - 深度分析，找出根因
 * 3. Strategist (Opus) - 制定策略，设计方案
 * 4. Guardian (Sonnet) - 风险评估，安全把关
 * 5. 投票 - 加权投票，达成共识
 * 6. Executor (Haiku) - 执行决策
 */

import Database from 'better-sqlite3';
import Anthropic from '@anthropic-ai/sdk';
import { EventEmitter } from 'events';

// ============================================================================
// Types
// ============================================================================

interface CouncilRole {
  role_id: string;
  role_name: string;
  role_description: string;
  default_model: string;
  allowed_models: string[];
  current_model: string | null;
  responsibilities: string[];
  system_prompt: string;
  max_tokens_per_call: number;
  max_calls_per_hour: number;
  priority: number;
  vote_weight: number;
  enabled: boolean;
}

interface CouncilSession {
  session_id: string;
  trigger_type: string;
  trigger_context: Record<string, unknown>;
  agenda: string;
  scope: string;
  status: string;
  budget_limit_usd: number;
  budget_used_usd: number;
}

interface Speech {
  role_id: string;
  phase: string;
  model_used: string;
  input_prompt: string;
  output_content: string;
  structured_output: Record<string, unknown>;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
}

interface DynamicStrategy {
  strategy_id: string;
  strategy_name: string;
  strategy_description: string;
  trigger_condition_sql: string | null;
  trigger_condition_nl: string;
  action_plan: Record<string, unknown>;
  success_criteria_sql: string | null;
  rollback_plan: Record<string, unknown> | null;
  confidence: number;
}

interface Budget {
  budget_limit_usd: number;
  budget_used_usd: number;
  budget_remaining_usd: number;
  overspend_action: 'block' | 'downgrade' | 'skip_low_priority' | 'alert_only';
  role_allocations: Record<string, number>;
}

interface ModelPricing {
  model_id: string;
  model_name: string;
  input_price_per_1m: number;
  output_price_per_1m: number;
}

interface LLMClient {
  chat(params: {
    model: string;
    system: string;
    messages: { role: 'user' | 'assistant'; content: string }[];
    max_tokens: number;
  }): Promise<{
    content: string;
    input_tokens: number;
    output_tokens: number;
    latency_ms: number;
  }>;
}

// ============================================================================
// Multi-Model Client Abstraction
// ============================================================================

class MultiModelClient implements LLMClient {
  private anthropic: Anthropic;
  private modelMapping: Record<string, string> = {
    'opus': 'claude-opus-4-5-20251101',
    'sonnet': 'claude-sonnet-4-20250514',
    'haiku': 'claude-3-5-haiku-20241022',
  };

  constructor() {
    this.anthropic = new Anthropic();
  }

  async chat(params: {
    model: string;
    system: string;
    messages: { role: 'user' | 'assistant'; content: string }[];
    max_tokens: number;
  }): Promise<{
    content: string;
    input_tokens: number;
    output_tokens: number;
    latency_ms: number;
  }> {
    const startTime = Date.now();

    // Map model alias to full model ID
    const modelId = this.modelMapping[params.model] || params.model;

    const response = await this.anthropic.messages.create({
      model: modelId,
      max_tokens: params.max_tokens,
      system: params.system,
      messages: params.messages,
    });

    const latency_ms = Date.now() - startTime;

    return {
      content: response.content[0].type === 'text' ? response.content[0].text : '',
      input_tokens: response.usage.input_tokens,
      output_tokens: response.usage.output_tokens,
      latency_ms,
    };
  }
}

// ============================================================================
// Evolution Council Engine
// ============================================================================

export class EvolutionCouncil extends EventEmitter {
  private db: Database.Database;
  private llm: LLMClient;
  private running = false;
  private checkInterval: NodeJS.Timeout | null = null;

  constructor(dbPath: string, llmClient?: LLMClient) {
    super();
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.llm = llmClient || new MultiModelClient();
  }

  // ============================================================================
  // Lifecycle
  // ============================================================================

  start(intervalMs = 300000): void {  // 默认 5 分钟检查一次
    if (this.running) return;
    this.running = true;

    this.emit('started');
    console.log(`[Council] Started with ${intervalMs}ms interval`);

    // 立即检查一次
    this.checkForTriggers();

    // 定期检查
    this.checkInterval = setInterval(() => {
      this.checkForTriggers();
    }, intervalMs);
  }

  stop(): void {
    this.running = false;
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
    this.emit('stopped');
  }

  // ============================================================================
  // Trigger Detection
  // ============================================================================

  private async checkForTriggers(): Promise<void> {
    try {
      // 检查预算
      const budget = this.getCurrentBudget();
      if (budget.budget_remaining_usd <= 0) {
        this.emit('budget_exhausted', budget);
        return;
      }

      // 收集系统指标
      const metrics = await this.collectMetrics();

      // 让 Observer 分析是否需要召开会议
      const shouldConvene = await this.shouldConveneCouncil(metrics);

      if (shouldConvene.convene) {
        await this.conveneSession({
          trigger_type: shouldConvene.trigger_type,
          trigger_context: shouldConvene.context,
          agenda: shouldConvene.agenda,
          scope: shouldConvene.scope,
        });
      }

    } catch (error) {
      console.error('[Council] Check error:', error);
      this.emit('error', error);
    }
  }

  private async shouldConveneCouncil(metrics: Record<string, unknown>): Promise<{
    convene: boolean;
    trigger_type: string;
    agenda: string;
    scope: string;
    context: Record<string, unknown>;
  }> {
    const observer = this.getRole('role:observer');
    if (!observer || !observer.enabled) {
      return { convene: false, trigger_type: '', agenda: '', scope: '', context: {} };
    }

    const model = this.selectModel(observer);
    const prompt = `分析以下系统指标，判断是否需要召开决策会议：

${JSON.stringify(metrics, null, 2)}

如果发现以下情况之一，建议召开会议：
1. 成本异常（超出预期 20% 以上）
2. 延迟异常（P95 超过 5 秒）
3. 错误率上升（超过 5%）
4. 质量下降（负面反馈增加）
5. 资源使用异常

输出 JSON 格式：
\`\`\`json
{
  "convene": true/false,
  "trigger_type": "anomaly|threshold_breach|scheduled",
  "agenda": "讨论议题",
  "scope": "cost|quality|latency|memory|routing|general",
  "severity": 1-5,
  "observations": ["观察1", "观察2"]
}
\`\`\``;

    try {
      const response = await this.llm.chat({
        model,
        system: observer.system_prompt,
        messages: [{ role: 'user', content: prompt }],
        max_tokens: observer.max_tokens_per_call,
      });

      // 记录发言（用于审计和学习）
      await this.recordSpeech(null, observer.role_id, 'observation', model, prompt, response);

      const parsed = this.parseJsonResponse(response.content);

      return {
        convene: parsed.convene || false,
        trigger_type: parsed.trigger_type || 'anomaly',
        agenda: parsed.agenda || '系统优化讨论',
        scope: parsed.scope || 'general',
        context: { metrics, observations: parsed.observations },
      };

    } catch (error) {
      console.error('[Council] Observer error:', error);
      return { convene: false, trigger_type: '', agenda: '', scope: '', context: {} };
    }
  }

  // ============================================================================
  // Session Management
  // ============================================================================

  async conveneSession(params: {
    trigger_type: string;
    trigger_context: Record<string, unknown>;
    agenda: string;
    scope: string;
    budget_limit_usd?: number;
  }): Promise<string> {
    const sessionId = `session:${Date.now()}:${Math.random().toString(36).substr(2, 9)}`;

    const budget = this.getCurrentBudget();
    const sessionBudget = params.budget_limit_usd || Math.min(1.0, budget.budget_remaining_usd);

    // 创建会议
    this.db.prepare(`
      INSERT INTO evo_council_sessions (
        session_id, trigger_type, trigger_context, agenda, scope,
        status, budget_limit_usd
      ) VALUES (?, ?, ?, ?, ?, 'initiated', ?)
    `).run(
      sessionId,
      params.trigger_type,
      JSON.stringify(params.trigger_context),
      params.agenda,
      params.scope,
      sessionBudget
    );

    this.emit('session_started', { session_id: sessionId, agenda: params.agenda });

    // 执行会议流程
    try {
      await this.runSessionFlow(sessionId);
    } catch (error) {
      this.updateSessionStatus(sessionId, 'failed');
      this.emit('session_failed', { session_id: sessionId, error });
    }

    return sessionId;
  }

  private async runSessionFlow(sessionId: string): Promise<void> {
    const session = this.getSession(sessionId);
    if (!session) throw new Error('Session not found');

    // Phase 1: Analysis
    this.updateSessionStatus(sessionId, 'analyzing');
    const analysis = await this.runAnalysisPhase(session);

    if (!analysis.proceed) {
      this.updateSessionStatus(sessionId, 'completed');
      this.emit('session_completed', { session_id: sessionId, reason: 'No action needed' });
      return;
    }

    // Phase 2: Proposal
    this.updateSessionStatus(sessionId, 'proposing');
    const proposal = await this.runProposalPhase(session, analysis);

    if (!proposal.strategy) {
      this.updateSessionStatus(sessionId, 'completed');
      return;
    }

    // Phase 3: Review
    this.updateSessionStatus(sessionId, 'reviewing');
    const review = await this.runReviewPhase(session, proposal);

    // Phase 4: Voting
    this.updateSessionStatus(sessionId, 'voting');
    const voteResult = await this.runVotingPhase(session, proposal, review);

    if (!voteResult.approved) {
      this.updateSessionStatus(sessionId, 'rejected');
      this.emit('session_rejected', { session_id: sessionId, reason: voteResult.reason });
      return;
    }

    // Phase 5: Create Strategy
    this.updateSessionStatus(sessionId, 'approved');
    const strategy = await this.createDynamicStrategy(session, proposal);

    // Phase 6: Execute
    this.updateSessionStatus(sessionId, 'executing');
    await this.executeStrategy(session, strategy);

    // Phase 7: Validate
    this.updateSessionStatus(sessionId, 'validating');
    await this.validateExecution(session, strategy);

    this.updateSessionStatus(sessionId, 'completed');
    this.emit('session_completed', { session_id: sessionId, strategy_id: strategy.strategy_id });
  }

  // ============================================================================
  // Phase Implementations
  // ============================================================================

  private async runAnalysisPhase(session: CouncilSession): Promise<{
    proceed: boolean;
    root_causes: { cause: string; confidence: number }[];
    impact: Record<string, unknown>;
  }> {
    const analyst = this.getRole('role:analyst');
    if (!analyst || !analyst.enabled || !this.checkBudget(session, analyst)) {
      return { proceed: false, root_causes: [], impact: {} };
    }

    const model = this.selectModel(analyst);
    const prompt = `会议议题: ${session.agenda}
范围: ${session.scope}
触发上下文:
${JSON.stringify(session.trigger_context, null, 2)}

请进行深度分析，找出根本原因，并评估影响。`;

    const response = await this.llm.chat({
      model,
      system: analyst.system_prompt,
      messages: [{ role: 'user', content: prompt }],
      max_tokens: analyst.max_tokens_per_call,
    });

    await this.recordSpeech(session.session_id, analyst.role_id, 'analysis', model, prompt, response);

    const parsed = this.parseJsonResponse(response.content);

    return {
      proceed: (parsed.root_causes?.length || 0) > 0,
      root_causes: parsed.root_causes || [],
      impact: parsed.impact_assessment || {},
    };
  }

  private async runProposalPhase(
    session: CouncilSession,
    analysis: { root_causes: { cause: string; confidence: number }[]; impact: Record<string, unknown> }
  ): Promise<{
    strategy: Record<string, unknown> | null;
    execution_plan: Record<string, unknown> | null;
    risks: { risk: string; mitigation: string }[];
  }> {
    const strategist = this.getRole('role:strategist');
    if (!strategist || !strategist.enabled || !this.checkBudget(session, strategist)) {
      return { strategy: null, execution_plan: null, risks: [] };
    }

    const model = this.selectModel(strategist);
    const prompt = `会议议题: ${session.agenda}
范围: ${session.scope}

分析结果:
根本原因: ${JSON.stringify(analysis.root_causes, null, 2)}
影响评估: ${JSON.stringify(analysis.impact, null, 2)}

请制定优化策略。注意：
1. 策略必须是通用的、可自动执行的
2. 需要明确的触发条件（SQL 或自然语言）
3. 需要验证成功的标准
4. 需要回滚计划`;

    const response = await this.llm.chat({
      model,
      system: strategist.system_prompt,
      messages: [{ role: 'user', content: prompt }],
      max_tokens: strategist.max_tokens_per_call,
    });

    await this.recordSpeech(session.session_id, strategist.role_id, 'proposal', model, prompt, response);

    const parsed = this.parseJsonResponse(response.content);

    return {
      strategy: parsed.strategy || null,
      execution_plan: parsed.execution_plan || null,
      risks: parsed.risks || [],
    };
  }

  private async runReviewPhase(
    session: CouncilSession,
    proposal: { strategy: Record<string, unknown> | null; risks: { risk: string; mitigation: string }[] }
  ): Promise<{
    risk_level: string;
    safety_passed: boolean;
    required_modifications: string[];
    veto: boolean;
    veto_reason: string | null;
  }> {
    const guardian = this.getRole('role:guardian');
    if (!guardian || !guardian.enabled || !this.checkBudget(session, guardian)) {
      // 没有 Guardian 审核时，默认通过但标记为高风险
      return { risk_level: 'high', safety_passed: true, required_modifications: [], veto: false, veto_reason: null };
    }

    const model = this.selectModel(guardian);
    const prompt = `请审核以下策略提案：

策略: ${JSON.stringify(proposal.strategy, null, 2)}
已识别风险: ${JSON.stringify(proposal.risks, null, 2)}

请评估：
1. 整体风险等级
2. 安全检查是否通过
3. 是否需要修改
4. 是否需要否决`;

    const response = await this.llm.chat({
      model,
      system: guardian.system_prompt,
      messages: [{ role: 'user', content: prompt }],
      max_tokens: guardian.max_tokens_per_call,
    });

    await this.recordSpeech(session.session_id, guardian.role_id, 'review', model, prompt, response);

    const parsed = this.parseJsonResponse(response.content);

    return {
      risk_level: parsed.risk_assessment?.overall_risk || 'medium',
      safety_passed: parsed.safety_checks?.every((c: { passed: boolean }) => c.passed) ?? true,
      required_modifications: parsed.required_modifications || [],
      veto: parsed.veto || false,
      veto_reason: parsed.veto_reason || null,
    };
  }

  private async runVotingPhase(
    session: CouncilSession,
    proposal: { strategy: Record<string, unknown> | null },
    review: { veto: boolean; veto_reason: string | null; risk_level: string }
  ): Promise<{
    approved: boolean;
    reason: string;
    votes: { role_id: string; vote: string; weight: number }[];
  }> {
    // Guardian 否决直接拒绝
    if (review.veto) {
      return {
        approved: false,
        reason: `Guardian veto: ${review.veto_reason}`,
        votes: [{ role_id: 'role:guardian', vote: 'reject', weight: 10 }],  // 否决权
      };
    }

    const proposalId = `proposal:${session.session_id}`;
    const votes: { role_id: string; vote: string; weight: number; reasoning: string }[] = [];

    // 收集各角色投票
    const votingRoles = ['role:observer', 'role:analyst', 'role:guardian'];

    for (const roleId of votingRoles) {
      const role = this.getRole(roleId);
      if (!role || !role.enabled) continue;

      // 简化投票：基于风险等级自动投票
      let vote: 'approve' | 'reject' | 'abstain';
      let reasoning: string;

      if (review.risk_level === 'critical') {
        vote = roleId === 'role:guardian' ? 'reject' : 'abstain';
        reasoning = 'Risk level too high';
      } else if (review.risk_level === 'high') {
        vote = 'abstain';
        reasoning = 'Need more information';
      } else {
        vote = 'approve';
        reasoning = 'Risk acceptable';
      }

      votes.push({ role_id: roleId, vote, weight: role.vote_weight, reasoning });

      // 记录投票
      this.db.prepare(`
        INSERT INTO evo_council_votes (vote_id, session_id, role_id, proposal_id, vote, vote_weight, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(
        `vote:${session.session_id}:${roleId}`,
        session.session_id,
        roleId,
        proposalId,
        vote,
        role.vote_weight,
        reasoning
      );
    }

    // 计算加权投票结果
    const approveWeight = votes.filter(v => v.vote === 'approve').reduce((sum, v) => sum + v.weight, 0);
    const rejectWeight = votes.filter(v => v.vote === 'reject').reduce((sum, v) => sum + v.weight, 0);
    const totalWeight = votes.reduce((sum, v) => sum + v.weight, 0);

    const approved = approveWeight > rejectWeight && approveWeight >= totalWeight * 0.5;

    return {
      approved,
      reason: approved ? 'Majority approved' : 'Majority rejected or abstained',
      votes,
    };
  }

  // ============================================================================
  // Strategy Creation & Execution
  // ============================================================================

  private async createDynamicStrategy(
    session: CouncilSession,
    proposal: { strategy: Record<string, unknown> | null; execution_plan: Record<string, unknown> | null }
  ): Promise<DynamicStrategy> {
    const strategyId = `strategy:${session.session_id}:${Date.now()}`;
    const strategy = proposal.strategy as Record<string, unknown>;

    const dynamicStrategy: DynamicStrategy = {
      strategy_id: strategyId,
      strategy_name: (strategy?.name as string) || session.agenda,
      strategy_description: (strategy?.description as string) || '',
      trigger_condition_sql: (strategy?.trigger_condition as string) || null,
      trigger_condition_nl: (strategy?.trigger_condition as string) || '',
      action_plan: (strategy?.actions as Record<string, unknown>) || {},
      success_criteria_sql: (strategy?.success_criteria as string) || null,
      rollback_plan: (strategy?.rollback_plan as Record<string, unknown>) || null,
      confidence: 0.5,  // 新策略初始置信度
    };

    // 保存到数据库
    this.db.prepare(`
      INSERT INTO evo_dynamic_strategies (
        strategy_id, created_by_session, created_by_role,
        strategy_name, strategy_description, strategy_type,
        trigger_condition_sql, trigger_condition_nl, trigger_condition_type,
        action_plan, action_type,
        success_criteria_sql, rollback_plan,
        confidence, status
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
    `).run(
      dynamicStrategy.strategy_id,
      session.session_id,
      'role:strategist',
      dynamicStrategy.strategy_name,
      dynamicStrategy.strategy_description,
      session.scope,
      dynamicStrategy.trigger_condition_sql,
      dynamicStrategy.trigger_condition_nl,
      dynamicStrategy.trigger_condition_sql ? 'sql' : 'llm_eval',
      JSON.stringify(dynamicStrategy.action_plan),
      'config_change',
      dynamicStrategy.success_criteria_sql,
      JSON.stringify(dynamicStrategy.rollback_plan),
      dynamicStrategy.confidence
    );

    this.emit('strategy_created', dynamicStrategy);

    return dynamicStrategy;
  }

  private async executeStrategy(session: CouncilSession, strategy: DynamicStrategy): Promise<void> {
    const executor = this.getRole('role:executor');

    if (executor && executor.enabled && this.checkBudget(session, executor)) {
      const model = this.selectModel(executor);
      const prompt = `请将以下策略转化为具体的执行步骤：

策略: ${strategy.strategy_name}
描述: ${strategy.strategy_description}
动作计划: ${JSON.stringify(strategy.action_plan, null, 2)}

生成可执行的 SQL 语句或配置变更。`;

      const response = await this.llm.chat({
        model,
        system: executor.system_prompt,
        messages: [{ role: 'user', content: prompt }],
        max_tokens: executor.max_tokens_per_call,
      });

      await this.recordSpeech(session.session_id, executor.role_id, 'consensus', model, prompt, response);

      const parsed = this.parseJsonResponse(response.content);

      // 执行生成的步骤
      if (parsed.execution_steps) {
        for (const step of parsed.execution_steps) {
          await this.executeStep(step);
        }
      }
    }

    // 更新策略执行时间
    this.db.prepare(`
      UPDATE evo_dynamic_strategies
      SET last_executed = CURRENT_TIMESTAMP
      WHERE strategy_id = ?
    `).run(strategy.strategy_id);
  }

  private async executeStep(step: { type: string; command: string }): Promise<void> {
    if (step.type === 'sql') {
      try {
        this.db.exec(step.command);
      } catch (error) {
        console.error('[Council] SQL execution error:', error);
        throw error;
      }
    } else if (step.type === 'config') {
      // 配置变更逻辑
      console.log('[Council] Config change:', step.command);
    }
  }

  private async validateExecution(session: CouncilSession, strategy: DynamicStrategy): Promise<boolean> {
    if (!strategy.success_criteria_sql) {
      return true;  // 没有验证条件，默认成功
    }

    try {
      const result = this.db.prepare(strategy.success_criteria_sql).get();
      const success = !!result;

      // 更新策略统计
      this.db.prepare(`
        UPDATE evo_dynamic_strategies
        SET
          execution_count = execution_count + 1,
          success_count = success_count + ?,
          computed_success_rate = 1.0 * (success_count + ?) / (execution_count + 1),
          confidence = 0.7 * confidence + 0.3 * ?
        WHERE strategy_id = ?
      `).run(success ? 1 : 0, success ? 1 : 0, success ? 1 : 0, strategy.strategy_id);

      if (!success && strategy.rollback_plan) {
        // 执行回滚
        this.emit('rollback', { strategy_id: strategy.strategy_id });
      }

      return success;

    } catch (error) {
      console.error('[Council] Validation error:', error);
      return false;
    }
  }

  // ============================================================================
  // Helpers
  // ============================================================================

  private getRole(roleId: string): CouncilRole | null {
    const row = this.db.prepare('SELECT * FROM evo_council_roles WHERE role_id = ?').get(roleId) as any;
    if (!row) return null;

    return {
      ...row,
      allowed_models: JSON.parse(row.allowed_models),
      responsibilities: JSON.parse(row.responsibilities),
      enabled: !!row.enabled,
    };
  }

  private getSession(sessionId: string): CouncilSession | null {
    const row = this.db.prepare('SELECT * FROM evo_council_sessions WHERE session_id = ?').get(sessionId) as any;
    if (!row) return null;

    return {
      ...row,
      trigger_context: JSON.parse(row.trigger_context || '{}'),
    };
  }

  private getCurrentBudget(): Budget {
    const row = this.db.prepare(`
      SELECT * FROM evo_council_budget
      WHERE budget_type = 'daily'
        AND period_start <= date('now')
        AND period_end > date('now')
    `).get() as any;

    if (!row) {
      return {
        budget_limit_usd: 5.0,
        budget_used_usd: 0,
        budget_remaining_usd: 5.0,
        overspend_action: 'downgrade',
        role_allocations: {},
      };
    }

    return {
      budget_limit_usd: row.budget_limit_usd,
      budget_used_usd: row.budget_used_usd,
      budget_remaining_usd: row.budget_limit_usd - row.budget_used_usd,
      overspend_action: row.overspend_action,
      role_allocations: JSON.parse(row.role_allocations || '{}'),
    };
  }

  private checkBudget(session: CouncilSession, role: CouncilRole): boolean {
    // 检查会议预算
    if (session.budget_used_usd >= session.budget_limit_usd) {
      return false;
    }

    // 检查总预算
    const budget = this.getCurrentBudget();
    if (budget.budget_remaining_usd <= 0) {
      return false;
    }

    return true;
  }

  private selectModel(role: CouncilRole): string {
    // 优先使用用户配置的模型
    if (role.current_model) {
      return role.current_model;
    }

    // 检查预算，必要时降级
    const budget = this.getCurrentBudget();
    if (budget.budget_remaining_usd < budget.budget_limit_usd * 0.2) {
      // 预算紧张，使用最便宜的允许模型
      return role.allowed_models[role.allowed_models.length - 1] || role.default_model;
    }

    return role.default_model;
  }

  private async collectMetrics(): Promise<Record<string, unknown>> {
    // 收集过去 24 小时的系统指标
    const costMetrics = this.db.prepare(`
      SELECT
        SUM(total_cost_usd) as total_cost_24h,
        AVG(total_cost_usd) as avg_cost_per_session,
        COUNT(*) as session_count
      FROM evo_sessions
      WHERE started_at >= datetime('now', '-24 hours')
    `).get();

    const latencyMetrics = this.db.prepare(`
      SELECT
        AVG(latency_ms) as avg_latency_ms,
        MAX(latency_ms) as max_latency_ms
      FROM evo_llm_calls
      WHERE created_at >= datetime('now', '-1 hour')
    `).get();

    const errorMetrics = this.db.prepare(`
      SELECT
        COUNT(*) as total_calls,
        SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count
      FROM evo_tool_calls
      WHERE created_at >= datetime('now', '-1 hour')
    `).get();

    const feedbackMetrics = this.db.prepare(`
      SELECT
        AVG(rating) as avg_rating,
        COUNT(*) as feedback_count
      FROM evo_feedback
      WHERE created_at >= datetime('now', '-24 hours')
    `).get();

    return {
      cost: costMetrics,
      latency: latencyMetrics,
      errors: errorMetrics,
      feedback: feedbackMetrics,
      collected_at: new Date().toISOString(),
    };
  }

  private async recordSpeech(
    sessionId: string | null,
    roleId: string,
    phase: string,
    model: string,
    prompt: string,
    response: { content: string; input_tokens: number; output_tokens: number; latency_ms: number }
  ): Promise<void> {
    const cost = this.calculateCost(model, response.input_tokens, response.output_tokens);
    const speechId = `speech:${Date.now()}:${Math.random().toString(36).substr(2, 9)}`;

    const parsed = this.parseJsonResponse(response.content);

    this.db.prepare(`
      INSERT INTO evo_council_speeches (
        speech_id, session_id, role_id, phase,
        model_used, input_prompt, output_content, structured_output,
        input_tokens, output_tokens, cost_usd, latency_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      speechId,
      sessionId,
      roleId,
      phase,
      model,
      prompt,
      response.content,
      JSON.stringify(parsed),
      response.input_tokens,
      response.output_tokens,
      cost,
      response.latency_ms
    );
  }

  private calculateCost(model: string, inputTokens: number, outputTokens: number): number {
    const pricing = this.db.prepare(`
      SELECT input_price_per_1m, output_price_per_1m FROM evo_model_pricing
      WHERE model_id LIKE ? OR model_name LIKE ?
    `).get(`%${model}%`, `%${model}%`) as ModelPricing | undefined;

    if (!pricing) {
      // 默认价格估算
      return (inputTokens * 3 + outputTokens * 15) / 1_000_000;
    }

    return (inputTokens * pricing.input_price_per_1m + outputTokens * pricing.output_price_per_1m) / 1_000_000;
  }

  private updateSessionStatus(sessionId: string, status: string): void {
    this.db.prepare(`
      UPDATE evo_council_sessions
      SET status = ?, ${status === 'completed' || status === 'failed' || status === 'rejected' ? 'completed_at = datetime("now"),' : ''} updated_at = datetime('now')
      WHERE session_id = ?
    `.replace(/,\s*updated_at/, ', updated_at')).run(status, sessionId);

    this.emit('status_changed', { session_id: sessionId, status });
  }

  private parseJsonResponse(content: string): Record<string, unknown> {
    try {
      // 尝试提取 JSON 块
      const jsonMatch = content.match(/```json\s*([\s\S]*?)\s*```/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[1]);
      }

      // 尝试直接解析
      return JSON.parse(content);
    } catch {
      return { raw: content };
    }
  }

  // ============================================================================
  // Public API: 手动触发会议
  // ============================================================================

  async requestCouncilSession(agenda: string, scope: string = 'general'): Promise<string> {
    return this.conveneSession({
      trigger_type: 'user_request',
      trigger_context: { requested_by: 'user', requested_at: new Date().toISOString() },
      agenda,
      scope,
    });
  }

  // ============================================================================
  // Public API: 配置角色模型
  // ============================================================================

  setRoleModel(roleId: string, model: string): void {
    const role = this.getRole(roleId);
    if (!role) throw new Error(`Role not found: ${roleId}`);

    if (!role.allowed_models.includes(model)) {
      throw new Error(`Model ${model} not allowed for role ${roleId}. Allowed: ${role.allowed_models.join(', ')}`);
    }

    this.db.prepare(`
      UPDATE evo_council_roles
      SET current_model = ?, updated_at = datetime('now')
      WHERE role_id = ?
    `).run(model, roleId);
  }

  // ============================================================================
  // Public API: 调整预算
  // ============================================================================

  setBudget(budgetType: 'daily' | 'per_session', limitUsd: number): void {
    this.db.prepare(`
      UPDATE evo_council_budget
      SET budget_limit_usd = ?, updated_at = datetime('now')
      WHERE budget_type = ?
    `).run(limitUsd, budgetType);
  }
}

// ============================================================================
// CLI Entry
// ============================================================================

if (require.main === module) {
  const dbPath = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

  const council = new EvolutionCouncil(dbPath);

  council.on('started', () => console.log('🏛️ Council started'));
  council.on('session_started', (e) => console.log('📋 Session started:', e.agenda));
  council.on('strategy_created', (e) => console.log('💡 Strategy created:', e.strategy_name));
  council.on('session_completed', (e) => console.log('✅ Session completed:', e));
  council.on('session_rejected', (e) => console.log('❌ Session rejected:', e.reason));
  council.on('budget_exhausted', () => console.log('💰 Budget exhausted'));
  council.on('error', (e) => console.error('❌ Error:', e));

  council.start(300000);  // 5 分钟检查一次

  process.on('SIGINT', () => {
    console.log('\nShutting down...');
    council.stop();
    process.exit(0);
  });
}
