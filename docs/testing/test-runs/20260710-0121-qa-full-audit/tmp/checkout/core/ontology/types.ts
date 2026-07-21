/**
 * Solar Ontology Types
 * 本体 = 记忆库 + 个性
 */

// ==================== Memory Types ====================

export interface EpisodicMemory {
  memory_id: string;
  namespace: string;
  event_type: string;
  event_summary: string;
  event_details?: Record<string, unknown>;
  session_id?: string;
  related_files?: string[];
  related_resources?: string[];
  importance: number;
  sentiment?: 'positive' | 'negative' | 'neutral';
  outcome?: 'success' | 'failure' | 'partial';
  occurred_at: string;
  recall_count: number;
}

export interface SemanticMemory {
  memory_id: string;
  namespace: string;
  key: string;
  value: unknown;
  source_type?: 'inferred' | 'explicit' | 'imported';
  confidence: number;
  access_count: number;
  last_accessed_at?: string;
}

export interface ProceduralMemory {
  memory_id: string;
  namespace: string;
  procedure_name: string;
  procedure_type?: 'workflow' | 'pattern' | 'rule';
  description?: string;
  trigger_conditions: Record<string, unknown>;
  trigger_keywords?: string[];
  steps: string[];
  resources_needed?: string[];
  execution_count: number;
  success_count: number;
  avg_duration_seconds?: number;
}

// ==================== Personality Types ====================

export type PreferenceCategory = 'work_style' | 'communication' | 'priority' | 'risk';

export interface PreferenceDimension {
  dimension_id: string;
  category: PreferenceCategory;
  name: string;
  description?: string;
  value_type: 'continuous' | 'categorical' | 'ranking';
  value_range?: unknown[];
  default_value: number;
  current_value: number | null;
  confidence: number;
  sample_count: number;
  last_updated?: string;
  evidence?: string[];
}

export interface ValueDimension {
  dimension_id: string;
  name: string;
  description?: string;
  weight: number;
  conflicts_with?: string[];
  evidence?: string[];
  confidence: number;
}

export interface StyleDimension {
  dimension_id: string;
  category: string;
  name: string;
  description?: string;
  current_value?: string;
  alternatives?: string[];
  evidence?: string[];
  confidence: number;
}

export interface Relationship {
  relationship_id: string;
  entity_type: 'person' | 'project' | 'tool' | 'community';
  entity_name: string;
  relationship_type: 'guardian' | 'focus' | 'frequent' | 'trusted';
  importance: number;
  context?: Record<string, unknown>;
  last_interaction?: string;
  interaction_count: number;
}

// ==================== Agent Rules ====================

export type AgentRuleType = 'behavior' | 'output' | 'decision';

export interface AgentRule {
  rule_id?: number;
  agent_id: string;
  rule_type: AgentRuleType;
  rule_key: string;
  rule_value: unknown;
  source_dimension?: string;
  generated_at?: string;
  valid_until?: string;
}

export interface GlobalRule {
  rule_key: string;
  rule_value: unknown;
  source_dimension?: string;
  confidence: number;
}

export interface AgentContext {
  agent_id: string;
  rules: Record<string, unknown>;
  relevantMemories: EpisodicMemory[];
  focusMetrics: string[];
  successPatterns: string[];

  // 生成 prompt 注入内容
  toPrompt(): string;
}

// ==================== Ontology Snapshot ====================

export interface OntologySnapshot {
  version: string;
  created_at: string;

  // 记忆库
  memory: {
    episodic: EpisodicMemory[];
    semantic: SemanticMemory[];
    procedural: ProceduralMemory[];
  };

  // 个性
  personality: {
    preferences: PreferenceDimension[];
    values: ValueDimension[];
    styles: StyleDimension[];
    relationships: Relationship[];
  };

  // Agent 规则
  agentRules: Record<string, AgentRule[]>;
  globalRules: GlobalRule[];
}

// ==================== Preference Signal ====================

export interface PreferenceSignal {
  dimension_id: string;
  value: number;
  weight: number;
  source: 'session' | 'explicit' | 'feedback';
  timestamp: Date;
  evidence?: string;
}

// ==================== Ontology Config ====================

export interface OntologyConfig {
  // 学习参数
  learningRate: number;            // 基础学习率 (默认 0.1)
  recomputeThreshold: number;      // 触发重计算的偏好变化阈值 (默认 0.1)

  // 记忆参数
  maxEpisodicMemories: number;     // 最大情景记忆数
  maxRelevantMemories: number;     // Agent 上下文中的相关记忆数
  memoryDecayRate: number;         // 记忆衰减率

  // 版本参数
  maxVersions: number;             // 保留的最大版本数
}

export const DEFAULT_ONTOLOGY_CONFIG: OntologyConfig = {
  learningRate: 0.1,
  recomputeThreshold: 0.1,
  maxEpisodicMemories: 1000,
  maxRelevantMemories: 5,
  memoryDecayRate: 0.01,
  maxVersions: 10,
};
