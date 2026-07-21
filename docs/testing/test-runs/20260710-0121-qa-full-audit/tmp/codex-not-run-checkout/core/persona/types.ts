/**
 * Persona Engine Types
 *
 * Personality-based Prompt Steering System (PPSS)
 * Enhances AI reasoning through dynamic persona modulation
 */

// Big Five Personality Dimensions (0.0 - 1.0)
export interface BigFive {
  openness: number;           // 开放性: 创意、好奇、探索
  conscientiousness: number;  // 尽责性: 严谨、有条理、坚持
  extraversion: number;       // 外向性: 积极、自信、健谈
  agreeableness: number;      // 宜人性: 合作、友善、信任
  neuroticism: number;        // 神经质: 敏感、焦虑 vs 稳定
}

// Regulatory Focus (Higgins, 1997)
export type RegulatoryFocus = 'promotion' | 'prevention' | 'balanced';

// Cognitive Forcing Functions
export type CognitiveFunction =
  | 'chain_of_thought'       // 强制分步推理
  | 'self_consistency'       // 多路径投票
  | 'devils_advocate'        // 强制反驳
  | 'hypothesis_testing'     // 假设检验
  | 'divergent_thinking'     // 发散思维
  | 'verification'           // 强制自检
  | 'threat_modeling'        // 威胁建模
  | 'user_story_thinking'    // 用户故事思维
  | 'step_by_step'           // 分步实现
  | 'edge_case_analysis'     // 边界分析
  | 'systematic_checklist';  // 系统检查表

// Persona Profile Definition
export interface PersonaProfile {
  id: string;
  name: string;
  name_cn: string;           // 中文名
  description: string;
  emoji: string;

  // Personality parameters
  big_five: BigFive;
  regulatory_focus: RegulatoryFocus;

  // Cognitive enhancements
  cognitive_forcing: CognitiveFunction[];

  // Behavioral traits (injected into prompts)
  behavioral_traits: string[];

  // Applicable task domains
  task_domains: string[];

  // System prompt template
  system_prompt_template: string;

  // Metadata
  created_at?: string;
  updated_at?: string;
  usage_count?: number;
  success_rate?: number;
}

// Routing Rule
export interface RoutingRule {
  id: string;
  task_patterns: string[];           // Keywords to match
  primary_persona_id: string;
  secondary_persona_ids?: string[];  // For ensemble mode
  cognitive_boost?: CognitiveFunction[];
  priority: number;
}

// Persona Match Result
export interface PersonaMatch {
  persona: PersonaProfile;
  confidence: number;
  matched_patterns: string[];
  cognitive_boost: CognitiveFunction[];
  secondary_personas?: PersonaProfile[];
}

// Composed Prompt
export interface ComposedPrompt {
  system_prompt: string;
  personas_used: string[];
  cognitive_functions: CognitiveFunction[];
  regulatory_focus: RegulatoryFocus;
}

// Execution History
export interface PersonaExecution {
  id?: number;
  session_id: string;
  task_type: string;
  persona_ids: string[];
  cognitive_functions: CognitiveFunction[];
  success: boolean;
  quality_score?: number;
  created_at?: string;
}

// Cognitive Function Prompts
export const COGNITIVE_PROMPTS: Record<CognitiveFunction, string> = {
  chain_of_thought: 'Think step by step, showing your reasoning process clearly.',
  self_consistency: 'Consider multiple approaches and verify consistency across them.',
  devils_advocate: 'Actively seek reasons why your solution might be wrong.',
  hypothesis_testing: 'Form hypotheses and test them against evidence before concluding.',
  divergent_thinking: 'Generate multiple diverse ideas before converging on a solution.',
  verification: 'Verify your output meets all requirements before finishing.',
  threat_modeling: 'Systematically identify and assess potential threats and risks.',
  user_story_thinking: 'Frame problems in terms of user needs and delivered value.',
  step_by_step: 'Break implementation into small, testable steps.',
  edge_case_analysis: 'Consider edge cases and failure modes at each step.',
  systematic_checklist: 'Use systematic checklists to ensure complete coverage.',
};

// Regulatory Focus Prompts
export const REGULATORY_PROMPTS: Record<RegulatoryFocus, string> = {
  promotion: 'FOCUS: Pursue opportunities and possibilities. Ask "What could we achieve?"',
  prevention: 'FOCUS: Prevent problems and risks. Ask "What could go wrong?"',
  balanced: 'FOCUS: Balance opportunity pursuit with risk mitigation.',
};
