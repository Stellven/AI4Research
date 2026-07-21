/**
 * Persona Profiles Index
 *
 * 6 Core Personas for different task domains
 */

export { scientist } from './scientist';
export { engineer } from './engineer';
export { redteam } from './redteam';
export { creative } from './creative';
export { pm } from './pm';
export { reviewer } from './reviewer';

import { scientist } from './scientist';
import { engineer } from './engineer';
import { redteam } from './redteam';
import { creative } from './creative';
import { pm } from './pm';
import { reviewer } from './reviewer';
import { PersonaProfile } from '../types';

// All personas as a map
export const PERSONAS: Record<string, PersonaProfile> = {
  scientist,
  engineer,
  redteam,
  creative,
  pm,
  reviewer,
};

// Get persona by ID
export function getPersona(id: string): PersonaProfile | undefined {
  return PERSONAS[id];
}

// List all personas
export function listPersonas(): PersonaProfile[] {
  return Object.values(PERSONAS);
}

// Quick reference for persona selection
export const PERSONA_QUICK_REF = `
┌─────────────────────────────────────────────────────────────────┐
│                    PERSONA QUICK REFERENCE                       │
├─────────────────────────────────────────────────────────────────┤
│  ID          Name        Focus           Best For               │
│  ─────────────────────────────────────────────────────────────  │
│  scientist   🔬 科学家   balanced        研究、分析、调查       │
│  engineer    💻 工程师   prevention      代码、调试、优化       │
│  redteam     🛡️ 红队     prevention      安全、审计、风险       │
│  creative    🎨 创意者   promotion       脑暴、设计、创新       │
│  pm          📋 产品     balanced        需求、优先级、沟通     │
│  reviewer    🔍 审查者   prevention      审查、QA、验证         │
└─────────────────────────────────────────────────────────────────┘
`;
