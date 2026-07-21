/**
 * Persona Router
 *
 * Routes tasks to appropriate personas based on patterns and context
 */

import {
  PersonaProfile,
  PersonaMatch,
  RoutingRule,
  CognitiveFunction,
} from './types';
import { PERSONAS, getPersona } from './profiles';

// Default routing rules
const DEFAULT_RULES: RoutingRule[] = [
  // Code implementation
  {
    id: 'code-impl',
    task_patterns: ['implement', 'code', 'build', 'create', 'develop', 'write code', '代码', '实现', '开发'],
    primary_persona_id: 'engineer',
    cognitive_boost: ['step_by_step', 'verification'],
    priority: 10,
  },

  // Code review
  {
    id: 'code-review',
    task_patterns: ['review', 'audit', 'check code', 'look at', '审查', '检查', 'PR'],
    primary_persona_id: 'reviewer',
    secondary_persona_ids: ['redteam'],
    cognitive_boost: ['devils_advocate', 'systematic_checklist'],
    priority: 10,
  },

  // Security
  {
    id: 'security',
    task_patterns: ['security', 'vulnerability', 'exploit', 'attack', 'hack', '安全', '漏洞', 'XSS', 'SQL injection'],
    primary_persona_id: 'redteam',
    cognitive_boost: ['threat_modeling', 'devils_advocate'],
    priority: 15,
  },

  // Research & Analysis
  {
    id: 'research',
    task_patterns: ['research', 'analyze', 'investigate', 'study', 'understand', '研究', '分析', '调查'],
    primary_persona_id: 'scientist',
    cognitive_boost: ['hypothesis_testing', 'chain_of_thought'],
    priority: 10,
  },

  // Creative tasks
  {
    id: 'creative',
    task_patterns: ['design', 'brainstorm', 'ideate', 'innovate', 'creative', 'name', '设计', '创意', '脑暴', '命名'],
    primary_persona_id: 'creative',
    cognitive_boost: ['divergent_thinking'],
    priority: 10,
  },

  // Product & Requirements
  {
    id: 'product',
    task_patterns: ['requirement', 'user story', 'feature', 'prioritize', 'product', '需求', '功能', '优先级'],
    primary_persona_id: 'pm',
    cognitive_boost: ['user_story_thinking'],
    priority: 10,
  },

  // Debugging
  {
    id: 'debug',
    task_patterns: ['debug', 'fix', 'bug', 'error', 'issue', '修复', 'bug', '问题', '报错'],
    primary_persona_id: 'engineer',
    secondary_persona_ids: ['scientist'],
    cognitive_boost: ['hypothesis_testing', 'step_by_step'],
    priority: 12,
  },

  // Testing
  {
    id: 'testing',
    task_patterns: ['test', 'verify', 'validate', 'qa', '测试', '验证'],
    primary_persona_id: 'reviewer',
    cognitive_boost: ['systematic_checklist', 'edge_case_analysis'],
    priority: 10,
  },

  // Complex reasoning (Jekyll & Hyde mode)
  {
    id: 'complex',
    task_patterns: ['complex', 'tricky', 'difficult', 'challenging', '复杂', '困难'],
    primary_persona_id: 'scientist',
    secondary_persona_ids: ['reviewer'],
    cognitive_boost: ['chain_of_thought', 'self_consistency', 'verification'],
    priority: 5,
  },
];

export class PersonaRouter {
  private rules: RoutingRule[];

  constructor(customRules?: RoutingRule[]) {
    this.rules = customRules || DEFAULT_RULES;
    // Sort by priority (higher first)
    this.rules.sort((a, b) => b.priority - a.priority);
  }

  /**
   * Route a task to the best matching persona(s)
   */
  route(taskDescription: string): PersonaMatch | null {
    const normalizedTask = taskDescription.toLowerCase();

    for (const rule of this.rules) {
      const matchedPatterns = rule.task_patterns.filter(pattern =>
        normalizedTask.includes(pattern.toLowerCase())
      );

      if (matchedPatterns.length > 0) {
        const primary = getPersona(rule.primary_persona_id);
        if (!primary) continue;

        const secondaries = rule.secondary_persona_ids
          ?.map(id => getPersona(id))
          .filter((p): p is PersonaProfile => p !== undefined);

        // Calculate confidence based on match count
        const confidence = Math.min(0.5 + matchedPatterns.length * 0.15, 1.0);

        return {
          persona: primary,
          confidence,
          matched_patterns: matchedPatterns,
          cognitive_boost: rule.cognitive_boost || [],
          secondary_personas: secondaries,
        };
      }
    }

    // Default to engineer if no match
    const defaultPersona = getPersona('engineer')!;
    return {
      persona: defaultPersona,
      confidence: 0.3,
      matched_patterns: [],
      cognitive_boost: ['verification'],
    };
  }

  /**
   * Route with explicit persona selection
   */
  routeExplicit(
    personaIds: string[],
    cognitiveBoost?: CognitiveFunction[]
  ): PersonaMatch | null {
    const primary = getPersona(personaIds[0]);
    if (!primary) return null;

    const secondaries = personaIds
      .slice(1)
      .map(id => getPersona(id))
      .filter((p): p is PersonaProfile => p !== undefined);

    return {
      persona: primary,
      confidence: 1.0,
      matched_patterns: ['explicit'],
      cognitive_boost: cognitiveBoost || primary.cognitive_forcing,
      secondary_personas: secondaries,
    };
  }

  /**
   * Get all available routing rules
   */
  getRules(): RoutingRule[] {
    return this.rules;
  }

  /**
   * Add a custom routing rule
   */
  addRule(rule: RoutingRule): void {
    this.rules.push(rule);
    this.rules.sort((a, b) => b.priority - a.priority);
  }
}

// Singleton instance
export const personaRouter = new PersonaRouter();
