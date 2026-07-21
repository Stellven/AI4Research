/**
 * Prompt Composer
 *
 * Composes enhanced system prompts from persona profiles
 */

import {
  PersonaProfile,
  PersonaMatch,
  ComposedPrompt,
  CognitiveFunction,
  RegulatoryFocus,
  COGNITIVE_PROMPTS,
  REGULATORY_PROMPTS,
} from './types';

export class PromptComposer {
  /**
   * Compose a system prompt from persona match
   */
  compose(match: PersonaMatch, taskContext?: string): ComposedPrompt {
    const parts: string[] = [];
    const personas = [match.persona, ...(match.secondary_personas || [])];
    const cognitives = this.mergeCognitives(match);

    // 1. Primary persona identity
    const primary = match.persona;
    parts.push(`You are a ${primary.name} (${primary.name_cn}): ${primary.description}`);
    parts.push('');

    // 2. Big Five influenced behavioral traits
    parts.push('BEHAVIORAL TRAITS:');
    for (const trait of primary.behavioral_traits) {
      parts.push(`- ${trait}`);
    }
    parts.push('');

    // 3. Secondary persona perspectives (for ensemble mode)
    if (match.secondary_personas && match.secondary_personas.length > 0) {
      parts.push('ADDITIONAL PERSPECTIVES:');
      for (const secondary of match.secondary_personas) {
        parts.push(`- Also consider the ${secondary.name} (${secondary.name_cn}) viewpoint: ${secondary.description}`);
      }
      parts.push('');
    }

    // 4. Cognitive forcing functions
    if (cognitives.length > 0) {
      parts.push('COGNITIVE APPROACH:');
      for (const func of cognitives) {
        parts.push(`- ${COGNITIVE_PROMPTS[func]}`);
      }
      parts.push('');
    }

    // 5. Regulatory focus
    parts.push(REGULATORY_PROMPTS[primary.regulatory_focus]);
    parts.push('');

    // 6. System prompt template (core expertise)
    parts.push('EXPERTISE:');
    parts.push(primary.system_prompt_template);
    parts.push('');

    // 7. Task context (if provided)
    if (taskContext) {
      parts.push('CURRENT TASK:');
      parts.push(taskContext);
    }

    return {
      system_prompt: parts.join('\n'),
      personas_used: personas.map(p => p.id),
      cognitive_functions: cognitives,
      regulatory_focus: primary.regulatory_focus,
    };
  }

  /**
   * Compose a minimal prompt (just persona + task)
   */
  composeMinimal(match: PersonaMatch, taskContext: string): ComposedPrompt {
    const parts: string[] = [];
    const primary = match.persona;
    const cognitives = match.cognitive_boost.length > 0
      ? match.cognitive_boost
      : primary.cognitive_forcing.slice(0, 2);

    // Brief identity
    parts.push(`As a ${primary.name}: ${primary.description}`);
    parts.push('');

    // Key cognitive approaches only
    parts.push('Approach:');
    for (const func of cognitives) {
      parts.push(`- ${COGNITIVE_PROMPTS[func]}`);
    }
    parts.push('');

    // Task
    parts.push('Task:');
    parts.push(taskContext);

    return {
      system_prompt: parts.join('\n'),
      personas_used: [primary.id],
      cognitive_functions: cognitives,
      regulatory_focus: primary.regulatory_focus,
    };
  }

  /**
   * Compose Jekyll & Hyde ensemble prompt
   */
  composeEnsemble(
    generatorPersona: PersonaProfile,
    validatorPersona: PersonaProfile,
    phase: 'generation' | 'validation',
    taskContext: string
  ): ComposedPrompt {
    const parts: string[] = [];

    if (phase === 'generation') {
      // Generation phase - promotion focused
      parts.push(`You are a ${generatorPersona.name} (${generatorPersona.name_cn}): ${generatorPersona.description}`);
      parts.push('');
      parts.push('GENERATION PHASE:');
      parts.push('- Focus on creating a solution');
      parts.push('- Explore possibilities');
      parts.push('- Be thorough but not overly critical at this stage');
      parts.push('');
      for (const trait of generatorPersona.behavioral_traits) {
        parts.push(`- ${trait}`);
      }
    } else {
      // Validation phase - prevention focused
      parts.push(`You are a ${validatorPersona.name} (${validatorPersona.name_cn}): ${validatorPersona.description}`);
      parts.push('');
      parts.push('VALIDATION PHASE:');
      parts.push('- Critically examine the proposed solution');
      parts.push('- Find flaws, edge cases, and improvements');
      parts.push('- Be constructively critical');
      parts.push('');
      for (const trait of validatorPersona.behavioral_traits) {
        parts.push(`- ${trait}`);
      }
    }

    parts.push('');
    parts.push('TASK:');
    parts.push(taskContext);

    const persona = phase === 'generation' ? generatorPersona : validatorPersona;
    return {
      system_prompt: parts.join('\n'),
      personas_used: [generatorPersona.id, validatorPersona.id],
      cognitive_functions: persona.cognitive_forcing,
      regulatory_focus: phase === 'generation' ? 'promotion' : 'prevention',
    };
  }

  /**
   * Merge cognitive functions from persona and boost
   */
  private mergeCognitives(match: PersonaMatch): CognitiveFunction[] {
    const seen = new Set<CognitiveFunction>();
    const result: CognitiveFunction[] = [];

    // Add boost functions first (higher priority)
    for (const func of match.cognitive_boost) {
      if (!seen.has(func)) {
        seen.add(func);
        result.push(func);
      }
    }

    // Add persona's default functions
    for (const func of match.persona.cognitive_forcing) {
      if (!seen.has(func)) {
        seen.add(func);
        result.push(func);
      }
    }

    // Limit to 4 functions to avoid prompt bloat
    return result.slice(0, 4);
  }
}

// Singleton instance
export const promptComposer = new PromptComposer();
