/**
 * Solar Evolution Recorder Agent - 书记员 Agent
 *
 * 职责:
 * 1. 记录会议纪要
 * 2. 评估各 Agent 表现 (打分)
 * 3. 生成改进建议
 * 4. 追踪绩效趋势
 * 5. 触发 Agent 优化动作
 */

import Database from 'better-sqlite3';
import { EventEmitter } from 'events';

// Types
interface ReviewScores {
  relevance_score: number;
  quality_score: number;
  actionability_score: number;
  efficiency_score: number;
  innovation_score: number;
}

interface Assessment {
  contribution_score: number;
  accuracy_score: number;
  timeliness_score: number;
  collaboration_score: number;
  value_add_score: number;
  highlights: string[];
  concerns: string[];
  recommendations: string[];
  trend: 'improving' | 'stable' | 'declining';
}

interface LLMClient {
  chat(params: { model: string; system: string; messages: { role: 'user' | 'assistant'; content: string }[]; max_tokens: number; }): Promise<{ content: string; input_tokens: number; output_tokens: number; latency_ms: number; }>;
}

export class RecorderAgent extends EventEmitter {
  private db: Database.Database;
  private llm: LLMClient;
  private roleId = 'role:secretary';

  constructor(db: Database.Database, llm: LLMClient) {
    super();
    this.db = db;
    this.llm = llm;
  }

  // 1. Agent 互评
  async conductPeerReview(sessionId: string, reviewerRoleId: string, revieweeRoleId: string, revieweeOutput: string, context: { agenda: string; phase: string }): Promise<ReviewScores | null> {
    const rule = this.db.prepare(`SELECT * FROM evo_review_rules WHERE reviewer_role = ? AND reviewee_role = ? AND enabled = TRUE`).get(reviewerRoleId, revieweeRoleId) as any;
    if (!rule) return null;

    const reviewer = this.getRole(reviewerRoleId);
    if (!reviewer) return null;

    const prompt = `评价 ${context.phase} 阶段输出 (1-5分):
${revieweeOutput.substring(0, 2000)}

JSON格式: {"relevance_score":1-5,"quality_score":1-5,"actionability_score":1-5,"efficiency_score":1-5,"innovation_score":1-5,"strengths":[],"weaknesses":[],"adopted":bool}`;

    try {
      const response = await this.llm.chat({ model: this.selectModel(reviewer), system: '公正评审', messages: [{ role: 'user', content: prompt }], max_tokens: 500 });
      const parsed = this.parseJson(response.content);
      const scores: ReviewScores = {
        relevance_score: this.clamp(parsed.relevance_score, 1, 5),
        quality_score: this.clamp(parsed.quality_score, 1, 5),
        actionability_score: this.clamp(parsed.actionability_score, 1, 5),
        efficiency_score: this.clamp(parsed.efficiency_score, 1, 5),
        innovation_score: this.clamp(parsed.innovation_score, 1, 5),
      };

      this.db.prepare(`INSERT INTO evo_agent_reviews (review_id,session_id,reviewer_role_id,reviewee_role_id,relevance_score,quality_score,actionability_score,efficiency_score,innovation_score,strengths,weaknesses,adopted_suggestions,review_model,review_tokens,review_cost_usd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(
        `review:${Date.now()}`, sessionId, reviewerRoleId, revieweeRoleId,
        scores.relevance_score, scores.quality_score, scores.actionability_score, scores.efficiency_score, scores.innovation_score,
        JSON.stringify(parsed.strengths || []), JSON.stringify(parsed.weaknesses || []), parsed.adopted ? 1 : 0,
        this.selectModel(reviewer), response.input_tokens + response.output_tokens, this.calcCost(this.selectModel(reviewer), response.input_tokens, response.output_tokens)
      );
      this.emit('peer_review_completed', { session_id: sessionId, scores });
      return scores;
    } catch { return null; }
  }

  // 2. 会议纪要
  async generateMinutes(sessionId: string): Promise<any> {
    const session = this.db.prepare(`SELECT * FROM evo_council_sessions WHERE session_id = ?`).get(sessionId) as any;
    if (!session) return null;

    const speeches = this.db.prepare(`SELECT sp.*,r.role_name FROM evo_council_speeches sp JOIN evo_council_roles r ON sp.role_id=r.role_id WHERE sp.session_id=? ORDER BY sp.created_at`).all(sessionId) as any[];
    const votes = this.db.prepare(`SELECT v.*,r.role_name FROM evo_council_votes v JOIN evo_council_roles r ON v.role_id=r.role_id WHERE v.session_id=?`).all(sessionId) as any[];

    const rec = this.getRole(this.roleId);
    if (!rec) return null;

    const prompt = `会议纪要:议题${session.agenda},发言${speeches.length}次,投票${votes.map((v:any)=>`${v.role_name}:${v.vote}`).join(',')}。JSON:{"executive_summary":"","key_decisions":[],"action_items":[],"efficiency_rating":"good","improvement_suggestions":[]}`;

    try {
      const response = await this.llm.chat({ model: this.selectModel(rec), system: rec.system_prompt || '', messages: [{ role: 'user', content: prompt }], max_tokens: 1500 });
      const parsed = this.parseJson(response.content);
      this.db.prepare(`INSERT OR REPLACE INTO evo_meeting_minutes (minutes_id,session_id,executive_summary,key_decisions,action_items,participating_roles,total_speeches,efficiency_rating,improvement_suggestions,generated_by_model) VALUES (?,?,?,?,?,?,?,?,?,?)`).run(
        `minutes:${sessionId}`, sessionId, parsed.executive_summary || '', JSON.stringify(parsed.key_decisions || []), JSON.stringify(parsed.action_items || []),
        JSON.stringify([...new Set(speeches.map(s => s.role_id))]), speeches.length, parsed.efficiency_rating || 'fair', JSON.stringify(parsed.improvement_suggestions || []), this.selectModel(rec)
      );
      this.emit('minutes_generated', { session_id: sessionId });
      return parsed;
    } catch { return null; }
  }

  // 3. Agent 综合评定
  async assessPerformance(sessionId: string): Promise<void> {
    const roles = this.db.prepare(`SELECT DISTINCT role_id FROM evo_council_speeches WHERE session_id=?`).all(sessionId) as { role_id: string }[];
    for (const { role_id } of roles) {
      if (role_id === this.roleId) continue;

      const executions = this.db.prepare(`SELECT * FROM evo_agent_executions WHERE session_id=? AND role_id=?`).all(sessionId, role_id) as any[];
      const peerReviews = this.db.prepare(`SELECT * FROM evo_agent_reviews WHERE session_id=? AND reviewee_role_id=?`).all(sessionId, role_id) as any[];
      const baseline = this.db.prepare(`SELECT * FROM evo_agent_baselines WHERE role_id=?`).get(role_id) as any;
      const histAvg = this.db.prepare(`SELECT AVG(overall_score) as avg FROM evo_secretary_assessments WHERE role_id=? AND created_at>=datetime('now','-30 days')`).get(role_id) as any;

      const assessment = this.calcAssessment(executions, peerReviews, baseline, histAvg?.avg);
      this.db.prepare(`INSERT OR REPLACE INTO evo_secretary_assessments (assessment_id,session_id,role_id,contribution_score,accuracy_score,timeliness_score,collaboration_score,value_add_score,highlights,concerns,recommendations,trend) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).run(
        `assessment:${sessionId}:${role_id}`, sessionId, role_id,
        assessment.contribution_score, assessment.accuracy_score, assessment.timeliness_score, assessment.collaboration_score, assessment.value_add_score,
        JSON.stringify(assessment.highlights), JSON.stringify(assessment.concerns), JSON.stringify(assessment.recommendations), assessment.trend
      );
      this.emit('agent_assessed', { session_id: sessionId, role_id, assessment });
    }
  }

  private calcAssessment(executions: any[], peerReviews: any[], baseline: any, histAvg?: number): Assessment {
    const avgLatency = executions.length > 0 ? executions.reduce((s, e) => s + e.latency_ms, 0) / executions.length : 0;
    const avgQuality = peerReviews.length > 0 ? peerReviews.reduce((s, r) => s + (r.quality_score || 3), 0) / peerReviews.length : 3;
    const avgRelevance = peerReviews.length > 0 ? peerReviews.reduce((s, r) => s + (r.relevance_score || 3), 0) / peerReviews.length : 3;
    const adoptRate = peerReviews.length > 0 ? peerReviews.filter(r => r.adopted_suggestions).length / peerReviews.length : 0.5;

    const contribution_score = this.clamp(Math.round(avgRelevance), 1, 5);
    const accuracy_score = this.clamp(Math.round(avgQuality), 1, 5);
    const timeliness_score = this.clamp(baseline?.baseline_latency_ms ? Math.round(5 - 4 * (avgLatency / baseline.baseline_latency_ms - 1)) : (avgLatency < 3000 ? 5 : 3), 1, 5);
    const collaboration_score = this.clamp(Math.round(1 + adoptRate * 4), 1, 5);
    const value_add_score = peerReviews.length > 0 ? this.clamp(Math.round(peerReviews.reduce((s, r) => s + (r.innovation_score || 3), 0) / peerReviews.length), 1, 5) : 3;

    const overall = (contribution_score + accuracy_score + timeliness_score + collaboration_score + value_add_score) / 5;
    const trend: Assessment['trend'] = histAvg ? (overall > histAvg + 0.3 ? 'improving' : overall < histAvg - 0.3 ? 'declining' : 'stable') : 'stable';

    const highlights: string[] = [], concerns: string[] = [], recommendations: string[] = [];
    if (accuracy_score >= 4) highlights.push('分析质量高');
    if (accuracy_score <= 2) { concerns.push('质量需提升'); recommendations.push('升级模型'); }
    if (timeliness_score <= 2) { concerns.push('响应慢'); recommendations.push('检查网络或降级模型'); }

    return { contribution_score, accuracy_score, timeliness_score, collaboration_score, value_add_score, highlights, concerns, recommendations, trend };
  }

  // 4. 触发优化
  async checkOptimization(): Promise<void> {
    const agents = this.db.prepare(`SELECT * FROM v_evo_agents_need_optimization`).all() as any[];
    for (const a of agents) {
      this.emit('optimization_needed', a);
      if (a.issue_type === 'latency_high' && a.latency_delta_pct > 50) this.autoDowngrade(a.role_id);
    }
  }

  private autoDowngrade(roleId: string): void {
    const role = this.getRole(roleId);
    if (!role) return;
    const cur = role.current_model || role.default_model;
    const idx = role.allowed_models.indexOf(cur);
    if (idx < role.allowed_models.length - 1) {
      this.db.prepare(`UPDATE evo_council_roles SET current_model=? WHERE role_id=?`).run(role.allowed_models[idx + 1], roleId);
      this.emit('model_downgraded', { role_id: roleId, from: cur, to: role.allowed_models[idx + 1] });
    }
  }

  // Helpers
  private getRole(id: string): any { const r = this.db.prepare('SELECT * FROM evo_council_roles WHERE role_id=?').get(id) as any; return r ? { ...r, allowed_models: JSON.parse(r.allowed_models) } : null; }
  private selectModel(role: any): string { return role.current_model || role.default_model; }
  private calcCost(m: string, i: number, o: number): number { const p: Record<string, [number, number]> = { opus: [15, 75], sonnet: [3, 15], haiku: [0.8, 4] }; const [pi, po] = p[m] || [3, 15]; return (i * pi + o * po) / 1e6; }
  private parseJson(c: string): any { try { const m = c.match(/```json\s*([\s\S]*?)\s*```/); return JSON.parse(m ? m[1] : c); } catch { return {}; } }
  private clamp(v: number, min: number, max: number): number { return Math.max(min, Math.min(max, Math.round(v))); }
}

export function createRecorder(db: Database.Database, llm: LLMClient): RecorderAgent { return new RecorderAgent(db, llm); }
