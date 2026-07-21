/**
 * Persona Evaluator
 *
 * Task analysis, persona matching, and performance tracking
 *
 * Based on PersonaGym (EMNLP 2025) and Multi-LLM Evaluator research
 */

import { Database } from 'bun:sqlite';
import { PersonaProfile, CognitiveFunction } from './types';
import { PERSONAS, getPersona, listPersonas } from './profiles';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

// ============================================
// Types
// ============================================

export interface TaskProfile {
  domain: 'code' | 'security' | 'research' | 'creative' | 'product' | 'debug' | 'testing' | 'complex';
  domain_confidence: number;

  complexity: number;  // 1-10
  complexity_factors: {
    multi_step: boolean;
    requires_context: boolean;
    ambiguity_level: number;
    domain_expertise_required: number;
  };

  cognitive_requirements: CognitiveFunction[];
  regulatory_lean: 'promotion' | 'prevention' | 'balanced';
  risk_tolerance: 'high' | 'medium' | 'low';
  innovation_accuracy_tradeoff: number;  // -1 to +1
}

export interface PersonaSelection {
  persona_id: string;
  affinity_score: number;
  normalized_weight: number;
  role: 'primary' | 'secondary' | 'validator';
}

export interface PersonaPrior {
  persona_id: string;
  domain: string;
  alpha: number;
  beta: number;
}

// ============================================
// Task Analyzer
// ============================================

export class TaskAnalyzer {
  private domainPatterns: Record<string, string[]> = {
    code: ['implement', 'build', 'create', 'develop', 'write code', '代码', '实现', '开发', 'function', 'class'],
    security: ['security', 'vulnerab', 'exploit', 'attack', 'hack', '安全', '漏洞', 'xss', 'injection', 'audit', 'pentest', 'cve'],
    research: ['research', 'analyze', 'investigate', 'study', 'understand', '研究', '分析', 'paper', 'theory'],
    creative: ['design', 'brainstorm', 'ideate', 'innovate', 'creative', 'name', '设计', '创意', '脑暴', '命名'],
    product: ['requirement', 'user story', 'feature', 'prioritize', 'product', '需求', '功能', 'roadmap', 'spec'],
    debug: ['debug', 'fix', 'bug', 'error', 'issue', '修复', 'crash', 'exception', '问题', '报错'],
    testing: ['test', 'verify', 'validate', 'qa', '测试', '验证', 'coverage', 'unit test'],
    complex: ['complex', 'tricky', 'difficult', 'challenging', '复杂', '困难', 'optimize', 'architecture', 'distributed', 'scalab', 'system design', 'high availability', '分布式', '架构', '高可用', '扩展性', '微服务', '缓存'],
  };

  private cognitivePatterns: Record<CognitiveFunction, string[]> = {
    chain_of_thought: ['step by step', 'think through', '一步步', 'reasoning'],
    self_consistency: ['verify', 'double check', '验证', 'confirm'],
    hypothesis_testing: ['hypothesis', 'test', 'experiment', '假设', 'theory'],
    devils_advocate: ['challenge', 'critique', 'counter', '质疑', 'argue against'],
    divergent_thinking: ['brainstorm', 'alternatives', 'options', '多种方案'],
    systematic_checklist: ['checklist', 'systematic', 'comprehensive', '清单'],
    threat_modeling: ['threat', 'risk', 'attack surface', '威胁', '风险'],
    user_story_thinking: ['user', 'persona', 'journey', '用户', 'scenario'],
    verification: ['verify', 'check', 'validate', '验证', 'confirm'],
    edge_case_analysis: ['edge case', 'corner case', 'boundary', '边界'],
  };

  analyze(taskDescription: string): TaskProfile {
    const text = taskDescription.toLowerCase();

    // Domain detection
    const domainScores = this.detectDomain(text);
    const topDomain = Object.entries(domainScores).sort((a, b) => b[1] - a[1])[0];

    // Cognitive requirements
    const cognitiveReqs = this.detectCognitiveRequirements(text);

    // Complexity estimation
    const complexity = this.estimateComplexity(text);

    // Regulatory lean
    const regulatory = this.detectRegulatoryLean(text);

    return {
      domain: topDomain[0] as TaskProfile['domain'],
      domain_confidence: topDomain[1],

      complexity: complexity.score,
      complexity_factors: complexity.factors,

      cognitive_requirements: cognitiveReqs,
      regulatory_lean: regulatory,
      risk_tolerance: this.inferRiskTolerance(topDomain[0], complexity.score),
      innovation_accuracy_tradeoff: this.inferInnovationAccuracy(topDomain[0]),
    };
  }

  private detectDomain(text: string): Record<string, number> {
    const scores: Record<string, number> = {};

    for (const [domain, patterns] of Object.entries(this.domainPatterns)) {
      const matches = patterns.filter(p => text.includes(p)).length;
      scores[domain] = Math.min(matches / 3, 1);  // Normalize to 0-1
    }

    // Ensure at least one domain has a score
    const maxScore = Math.max(...Object.values(scores));
    if (maxScore === 0) {
      scores['code'] = 0.3;  // Default fallback
    }

    return scores;
  }

  private detectCognitiveRequirements(text: string): CognitiveFunction[] {
    const required: CognitiveFunction[] = [];

    for (const [func, patterns] of Object.entries(this.cognitivePatterns)) {
      if (patterns.some(p => text.includes(p))) {
        required.push(func as CognitiveFunction);
      }
    }

    // Default cognitive requirements based on common patterns
    if (required.length === 0) {
      required.push('chain_of_thought', 'verification');
    }

    return required;
  }

  private estimateComplexity(text: string): { score: number; factors: TaskProfile['complexity_factors'] } {
    const factors = {
      multi_step: text.includes('then') || text.includes('后') || text.includes('步骤'),
      requires_context: text.includes('based on') || text.includes('根据') || text.includes('considering'),
      ambiguity_level: this.estimateAmbiguity(text),
      domain_expertise_required: this.estimateExpertise(text),
    };

    // Score 1-10
    let score = 3;  // Base
    if (factors.multi_step) score += 2;
    if (factors.requires_context) score += 1;
    score += factors.ambiguity_level * 2;
    score += factors.domain_expertise_required * 2;

    return { score: Math.min(10, Math.max(1, score)), factors };
  }

  private estimateAmbiguity(text: string): number {
    const ambiguousWords = ['maybe', 'might', 'could', 'possibly', '可能', '也许', 'somehow'];
    const specificWords = ['exactly', 'must', 'should', '必须', '一定', 'specifically'];

    const ambiguousCount = ambiguousWords.filter(w => text.includes(w)).length;
    const specificCount = specificWords.filter(w => text.includes(w)).length;

    return Math.min(1, Math.max(0, (ambiguousCount - specificCount + 1) / 3));
  }

  private estimateExpertise(text: string): number {
    const expertTerms = ['algorithm', 'architecture', 'distributed', 'concurrent', 'optimization',
                        '算法', '架构', '分布式', '并发', '优化', 'protocol', 'kernel'];
    const matches = expertTerms.filter(t => text.includes(t)).length;
    return Math.min(1, matches / 3);
  }

  private detectRegulatoryLean(text: string): 'promotion' | 'prevention' | 'balanced' {
    const promotionWords = ['create', 'innovate', 'explore', 'new', '创新', '探索', '新'];
    const preventionWords = ['secure', 'safe', 'avoid', 'prevent', '安全', '避免', '防止', 'risk'];

    const promotionScore = promotionWords.filter(w => text.includes(w)).length;
    const preventionScore = preventionWords.filter(w => text.includes(w)).length;

    if (promotionScore > preventionScore + 1) return 'promotion';
    if (preventionScore > promotionScore + 1) return 'prevention';
    return 'balanced';
  }

  private inferRiskTolerance(domain: string, complexity: number): 'high' | 'medium' | 'low' {
    const lowRiskDomains = ['security', 'testing'];
    const highRiskDomains = ['creative'];

    if (lowRiskDomains.includes(domain)) return 'low';
    if (highRiskDomains.includes(domain) && complexity < 5) return 'high';
    return 'medium';
  }

  private inferInnovationAccuracy(domain: string): number {
    const innovationDomains: Record<string, number> = {
      creative: 0.8,
      research: 0.4,
      product: 0.3,
      code: 0,
      debug: -0.3,
      testing: -0.5,
      security: -0.7,
      complex: 0.1,
    };
    return innovationDomains[domain] ?? 0;
  }
}

// ============================================
// Persona Matcher
// ============================================

export class PersonaMatcher {
  private db: Database;
  private taskAnalyzer: TaskAnalyzer;

  constructor() {
    this.db = new Database(DB_PATH);
    this.db.run('PRAGMA busy_timeout = 5000');
    this.taskAnalyzer = new TaskAnalyzer();
  }

  /**
   * Analyze task and select top-N personas with weights
   */
  selectPersonas(taskDescription: string, n: number = 3): {
    task_profile: TaskProfile;
    selections: PersonaSelection[];
  } {
    const taskProfile = this.taskAnalyzer.analyze(taskDescription);
    const personas = listPersonas();

    // Calculate affinity scores
    const scored = personas.map(p => ({
      persona_id: p.id,
      affinity_score: this.computeAffinityScore(taskProfile, p),
    }));

    // Sort and select top-N
    scored.sort((a, b) => b.affinity_score - a.affinity_score);
    const topN = scored.slice(0, n);

    // Softmax normalization
    const temperature = 1.0;
    const expScores = topN.map(s => Math.exp(s.affinity_score / temperature));
    const sumExp = expScores.reduce((a, b) => a + b, 0);

    const selections: PersonaSelection[] = topN.map((s, i) => ({
      persona_id: s.persona_id,
      affinity_score: s.affinity_score,
      normalized_weight: expScores[i] / sumExp,
      role: i === 0 ? 'primary' : (i === n - 1 && n >= 2) ? 'validator' : 'secondary',
    }));

    return { task_profile: taskProfile, selections };
  }

  /**
   * Compute overall affinity score
   */
  private computeAffinityScore(task: TaskProfile, persona: PersonaProfile): number {
    const bigFiveScore = this.computeBigFiveAffinity(task, persona);
    const domainScore = this.computeDomainAffinity(task, persona);
    const cognitiveScore = this.computeCognitiveAffinity(task, persona);
    const priorScore = this.getPriorWeight(persona.id, task.domain);

    // Weighted combination
    const weights = { bigFive: 0.25, domain: 0.35, cognitive: 0.25, prior: 0.15 };

    return (
      weights.bigFive * bigFiveScore +
      weights.domain * domainScore +
      weights.cognitive * cognitiveScore +
      weights.prior * priorScore
    );
  }

  private computeBigFiveAffinity(task: TaskProfile, persona: PersonaProfile): number {
    let score = 0;

    // Innovation需求 → 高Openness
    if (task.innovation_accuracy_tradeoff > 0) {
      score += 0.3 * persona.big_five.openness;
    } else {
      score += 0.3 * persona.big_five.conscientiousness;
    }

    // 低风险容忍 → 低Neuroticism
    if (task.risk_tolerance === 'low') {
      score += 0.2 * (1 - persona.big_five.neuroticism);
    }

    // 高复杂度 → 高Conscientiousness
    if (task.complexity > 7) {
      score += 0.3 * persona.big_five.conscientiousness;
    }

    // Regulatory focus match
    if (task.regulatory_lean === persona.regulatory_focus) {
      score += 0.2;
    } else if (task.regulatory_lean === 'balanced') {
      score += 0.1;
    }

    return Math.min(1, score);
  }

  private computeDomainAffinity(task: TaskProfile, persona: PersonaProfile): number {
    const domainPersonaMap: Record<string, string[]> = {
      code: ['engineer', 'scientist'],
      security: ['redteam', 'reviewer'],
      research: ['scientist', 'creative'],
      creative: ['creative', 'pm'],
      product: ['pm', 'engineer'],
      debug: ['engineer', 'scientist'],
      testing: ['reviewer', 'engineer'],
      complex: ['scientist', 'reviewer'],
    };

    const preferred = domainPersonaMap[task.domain] || [];
    const rank = preferred.indexOf(persona.id);

    if (rank === 0) return 1.0;
    if (rank === 1) return 0.75;
    if (preferred.includes(persona.id)) return 0.5;
    return 0.25;
  }

  private computeCognitiveAffinity(task: TaskProfile, persona: PersonaProfile): number {
    if (task.cognitive_requirements.length === 0) return 0.5;

    const required = new Set(task.cognitive_requirements);
    const provided = new Set(persona.cognitive_forcing);

    const intersection = [...required].filter(x => provided.has(x));
    return intersection.length / required.size;
  }

  private getPriorWeight(personaId: string, domain: string): number {
    try {
      const row = this.db.query(
        'SELECT alpha, beta FROM persona_priors WHERE persona_id = ? AND domain = ?'
      ).get(personaId, domain) as { alpha: number; beta: number } | null;

      if (row) {
        return row.alpha / (row.alpha + row.beta);  // Beta distribution mean
      }
    } catch (e) {
      // Table might not exist yet
    }
    return 0.5;  // Uniform prior
  }
}

// ============================================
// Performance Tracker
// ============================================

export class PerformanceTracker {
  private db: Database;

  constructor() {
    this.db = new Database(DB_PATH);
    this.db.run('PRAGMA busy_timeout = 5000');
  }

  /**
   * Record an execution
   */
  recordExecution(data: {
    execution_id: string;
    task_id: string;
    task_profile: TaskProfile;
    selected_personas: PersonaSelection[];
    ensemble_mode: string;
    status: string;
    duration_ms: number;
    task_success_score?: number;
    response_quality_score?: number;
    persona_consistency_score?: number;
    user_feedback?: string;
  }): void {
    this.db.run(
      `INSERT INTO persona_executions (
        execution_id, task_id, task_profile, selected_personas, ensemble_mode,
        status, duration_ms, task_success_score, response_quality_score,
        persona_consistency_score, user_feedback
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        data.execution_id,
        data.task_id,
        JSON.stringify(data.task_profile),
        JSON.stringify(data.selected_personas),
        data.ensemble_mode,
        data.status,
        data.duration_ms,
        data.task_success_score ?? null,
        data.response_quality_score ?? null,
        data.persona_consistency_score ?? null,
        data.user_feedback ?? null,
      ]
    );

    // Update priors if we have success score
    if (data.task_success_score !== undefined) {
      this.updatePriors(
        data.selected_personas,
        data.task_profile.domain,
        data.task_success_score >= 0.7  // Success threshold
      );
    }
  }

  /**
   * Bayesian update of persona priors
   */
  private updatePriors(
    selections: PersonaSelection[],
    domain: string,
    success: boolean
  ): void {
    for (const sel of selections) {
      // Weight the update by the persona's role weight
      const updateWeight = sel.normalized_weight;

      if (success) {
        this.db.run(
          `UPDATE persona_priors SET alpha = alpha + ?, updated_at = datetime('now')
           WHERE persona_id = ? AND domain = ?`,
          [updateWeight, sel.persona_id, domain]
        );
      } else {
        this.db.run(
          `UPDATE persona_priors SET beta = beta + ?, updated_at = datetime('now')
           WHERE persona_id = ? AND domain = ?`,
          [updateWeight, sel.persona_id, domain]
        );
      }
    }
  }

  /**
   * Get performance summary
   */
  getPerformanceSummary(): any[] {
    return this.db.query(`
      SELECT * FROM v_persona_performance
    `).all();
  }

  /**
   * Get prior weights
   */
  getPriorWeights(domain?: string): any[] {
    const sql = domain
      ? `SELECT persona_id, domain, alpha, beta, ROUND(alpha/(alpha+beta), 3) as weight
         FROM persona_priors WHERE domain = ? ORDER BY weight DESC`
      : `SELECT persona_id, domain, alpha, beta, ROUND(alpha/(alpha+beta), 3) as weight
         FROM persona_priors ORDER BY domain, weight DESC`;

    return domain
      ? this.db.query(sql).all(domain)
      : this.db.query(sql).all();
  }
}

// ============================================
// Exports
// ============================================

export const taskAnalyzer = new TaskAnalyzer();
export const personaMatcher = new PersonaMatcher();
export const performanceTracker = new PerformanceTracker();

// ============================================
// CLI
// ============================================

if (import.meta.main) {
  const args = process.argv.slice(2);
  const command = args[0];

  switch (command) {
    case 'analyze': {
      const task = args.slice(1).join(' ') || 'implement a caching system';
      const profile = taskAnalyzer.analyze(task);
      console.log('Task:', task);
      console.log('\nProfile:');
      console.log(JSON.stringify(profile, null, 2));
      break;
    }

    case 'select': {
      const task = args.slice(1).join(' ') || 'review this code for security issues';
      const n = 3;
      const result = personaMatcher.selectPersonas(task, n);
      console.log('Task:', task);
      console.log('\nTask Profile:');
      console.log(`  Domain: ${result.task_profile.domain} (${(result.task_profile.domain_confidence * 100).toFixed(0)}%)`);
      console.log(`  Complexity: ${result.task_profile.complexity}/10`);
      console.log(`  Regulatory: ${result.task_profile.regulatory_lean}`);
      console.log(`  Risk Tolerance: ${result.task_profile.risk_tolerance}`);
      console.log('\nSelected Personas (Top-3):');
      for (const sel of result.selections) {
        const persona = getPersona(sel.persona_id)!;
        console.log(`  ${persona.emoji} ${sel.persona_id.padEnd(10)} | ` +
          `Affinity: ${(sel.affinity_score * 100).toFixed(1)}% | ` +
          `Weight: ${(sel.normalized_weight * 100).toFixed(1)}% | ` +
          `Role: ${sel.role}`);
      }
      break;
    }

    case 'priors': {
      const domain = args[1];
      const priors = performanceTracker.getPriorWeights(domain);
      console.log('Persona Priors:');
      console.log('─'.repeat(60));
      for (const p of priors) {
        console.log(`${p.persona_id.padEnd(10)} | ${p.domain.padEnd(10)} | ` +
          `α=${p.alpha.toFixed(1)} β=${p.beta.toFixed(1)} | Weight: ${(p.weight * 100).toFixed(1)}%`);
      }
      break;
    }

    case 'performance': {
      const perf = performanceTracker.getPerformanceSummary();
      if (perf.length === 0) {
        console.log('No execution data yet.');
      } else {
        console.log('Performance Summary:');
        console.log(JSON.stringify(perf, null, 2));
      }
      break;
    }

    default:
      console.log(`
Persona Evaluator - Task Analysis & Persona Selection

Usage:
  bun evaluator.ts analyze <task>     Analyze task profile
  bun evaluator.ts select <task>      Select top-3 personas for task
  bun evaluator.ts priors [domain]    Show persona prior weights
  bun evaluator.ts performance        Show performance summary

Examples:
  bun evaluator.ts analyze "implement a distributed cache"
  bun evaluator.ts select "review this code for security"
  bun evaluator.ts priors security
`);
  }
}
