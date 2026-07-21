/**
 * Solar Persona Engine
 *
 * Personality-based Prompt Steering System (PPSS)
 * Enhances AI reasoning through dynamic persona modulation
 *
 * Usage:
 *   import { personaEngine } from '~/Solar/core/persona';
 *
 *   // Auto-route based on task
 *   const prompt = personaEngine.enhance("Review this code for security issues");
 *
 *   // Explicit persona selection
 *   const prompt2 = personaEngine.enhance("Design a caching system", {
 *     personas: ['engineer', 'creative'],
 *     cognitive: ['divergent_thinking', 'verification']
 *   });
 *
 *   // Jekyll & Hyde mode for complex tasks
 *   const result = await personaEngine.executeEnsemble({
 *     task: "Solve this algorithm problem",
 *     generator: 'scientist',
 *     validator: 'reviewer'
 *   });
 */

import { PersonaProfile, PersonaMatch, ComposedPrompt, CognitiveFunction } from './types';
import { PersonaRouter, personaRouter } from './router';
import { PromptComposer, promptComposer } from './composer';
import { PERSONAS, getPersona, listPersonas, PERSONA_QUICK_REF } from './profiles';

export interface EnhanceOptions {
  personas?: string[];                    // Explicit persona IDs
  cognitive?: CognitiveFunction[];        // Additional cognitive functions
  minimal?: boolean;                      // Use minimal prompt format
}

export interface EnsembleOptions {
  task: string;
  generator?: string;                     // Default: scientist
  validator?: string;                     // Default: reviewer
  iterations?: number;                    // Default: 1
}

export class PersonaEngine {
  private router: PersonaRouter;
  private composer: PromptComposer;

  constructor() {
    this.router = personaRouter;
    this.composer = promptComposer;
  }

  /**
   * Enhance a task with persona-based prompting
   */
  enhance(taskDescription: string, options?: EnhanceOptions): ComposedPrompt {
    let match: PersonaMatch | null;

    if (options?.personas && options.personas.length > 0) {
      // Explicit persona selection
      match = this.router.routeExplicit(options.personas, options.cognitive);
    } else {
      // Auto-route based on task
      match = this.router.route(taskDescription);
    }

    if (!match) {
      // Fallback to engineer
      match = this.router.routeExplicit(['engineer'])!;
    }

    // Add additional cognitive functions if specified
    if (options?.cognitive) {
      match.cognitive_boost = [...match.cognitive_boost, ...options.cognitive];
    }

    // Compose prompt
    if (options?.minimal) {
      return this.composer.composeMinimal(match, taskDescription);
    }
    return this.composer.compose(match, taskDescription);
  }

  /**
   * Get routing result without composing prompt
   */
  route(taskDescription: string): PersonaMatch | null {
    return this.router.route(taskDescription);
  }

  /**
   * Get persona by ID
   */
  getPersona(id: string): PersonaProfile | undefined {
    return getPersona(id);
  }

  /**
   * List all available personas
   */
  listPersonas(): PersonaProfile[] {
    return listPersonas();
  }

  /**
   * Compose Jekyll & Hyde ensemble prompt
   */
  composeEnsemble(
    task: string,
    phase: 'generation' | 'validation',
    generatorId: string = 'scientist',
    validatorId: string = 'reviewer'
  ): ComposedPrompt {
    const generator = getPersona(generatorId) || getPersona('scientist')!;
    const validator = getPersona(validatorId) || getPersona('reviewer')!;
    return this.composer.composeEnsemble(generator, validator, phase, task);
  }

  /**
   * Print persona quick reference
   */
  printQuickRef(): void {
    console.log(PERSONA_QUICK_REF);
  }
}

// Singleton instance
export const personaEngine = new PersonaEngine();

// Re-export types and utilities
export * from './types';
export { PERSONAS, getPersona, listPersonas, PERSONA_QUICK_REF } from './profiles';
export { personaRouter } from './router';
export { promptComposer } from './composer';

// CLI interface
if (import.meta.main) {
  const args = process.argv.slice(2);
  const command = args[0];

  switch (command) {
    case 'list':
      console.log(PERSONA_QUICK_REF);
      break;

    case 'route': {
      const task = args.slice(1).join(' ') || 'implement a feature';
      const match = personaEngine.route(task);
      if (match) {
        console.log(`Task: "${task}"`);
        console.log(`Persona: ${match.persona.emoji} ${match.persona.name} (${match.persona.name_cn})`);
        console.log(`Confidence: ${(match.confidence * 100).toFixed(0)}%`);
        console.log(`Matched: ${match.matched_patterns.join(', ') || 'default'}`);
        console.log(`Cognitive: ${match.cognitive_boost.join(', ')}`);
        if (match.secondary_personas?.length) {
          console.log(`Secondary: ${match.secondary_personas.map(p => p.name).join(', ')}`);
        }
      }
      break;
    }

    case 'compose': {
      const task = args.slice(1).join(' ') || 'implement a feature';
      const result = personaEngine.enhance(task);
      console.log('=== COMPOSED PROMPT ===\n');
      console.log(result.system_prompt);
      console.log('\n=== METADATA ===');
      console.log(`Personas: ${result.personas_used.join(', ')}`);
      console.log(`Cognitive: ${result.cognitive_functions.join(', ')}`);
      console.log(`Focus: ${result.regulatory_focus}`);
      break;
    }

    case 'persona': {
      const id = args[1];
      const persona = getPersona(id);
      if (persona) {
        console.log(`${persona.emoji} ${persona.name} (${persona.name_cn})`);
        console.log(`Description: ${persona.description}`);
        console.log(`\nBig Five:`);
        console.log(`  Openness:          ${(persona.big_five.openness * 100).toFixed(0)}%`);
        console.log(`  Conscientiousness: ${(persona.big_five.conscientiousness * 100).toFixed(0)}%`);
        console.log(`  Extraversion:      ${(persona.big_five.extraversion * 100).toFixed(0)}%`);
        console.log(`  Agreeableness:     ${(persona.big_five.agreeableness * 100).toFixed(0)}%`);
        console.log(`  Neuroticism:       ${(persona.big_five.neuroticism * 100).toFixed(0)}%`);
        console.log(`\nFocus: ${persona.regulatory_focus}`);
        console.log(`Cognitive: ${persona.cognitive_forcing.join(', ')}`);
        console.log(`Domains: ${persona.task_domains.join(', ')}`);
      } else {
        console.log(`Unknown persona: ${id}`);
        console.log(`Available: ${Object.keys(PERSONAS).join(', ')}`);
      }
      break;
    }

    default:
      console.log(`
Solar Persona Engine - Personality-based Prompt Steering

Usage:
  bun persona/index.ts list              List all personas
  bun persona/index.ts route <task>      Route task to persona
  bun persona/index.ts compose <task>    Compose enhanced prompt
  bun persona/index.ts persona <id>      Show persona details

Examples:
  bun persona/index.ts route "review this code"
  bun persona/index.ts compose "design a caching system"
  bun persona/index.ts persona engineer
`);
  }
}
