export const CORE_TO_HARNESS_SCHEMA_VERSION = "solar.core_to_harness.v1" as const;

export type CoreToHarnessSchemaVersion = typeof CORE_TO_HARNESS_SCHEMA_VERSION;

export type CoreToHarnessMode =
  | "delivery"
  | "debug"
  | "strategy"
  | "research"
  | "monitor"
  | "review";

export type CoreToHarnessUrgency = "low" | "normal" | "high" | "urgent";

export interface CoreToHarnessSource {
  channel: string;
  actor: string;
  device?: string;
  session_id?: string;
  thread_ref?: string;
  source_trust: string;
}

export interface CoreToHarnessWorkspace {
  repo: string;
  cwd?: string;
  knowledge_query?: string;
}

export interface CoreToHarnessRouting {
  mode: CoreToHarnessMode;
  urgency: CoreToHarnessUrgency;
  allow_autodispatch: boolean;
  requires_human_confirm: boolean;
  require_research_artifact: boolean;
}

export interface CoreToHarnessRawInput {
  text: string;
  attachments?: string[];
  quoted_context?: string[];
}

export interface CoreToHarnessAnalysis {
  title?: string;
  objective?: string;
  problem?: string;
  outcome?: string;
  constraints?: string[];
  non_goals?: string[];
  acceptance?: string[];
  suggested_logical_operators?: string[];
}

export interface CoreToHarnessResearch {
  artifact?: string;
  project_name?: string;
  conversation_id?: string;
  source_url?: string;
}

export interface CoreToHarnessConsumePolicy {
  enabled: boolean;
  sprint_id?: string;
  dispatch_planner?: boolean;
  auto_dispatch_planner?: boolean;
}

export interface CoreToHarnessRequest {
  schema_version: CoreToHarnessSchemaVersion;
  request_id: string;
  created_at?: string;
  source: CoreToHarnessSource;
  workspace: CoreToHarnessWorkspace;
  routing: CoreToHarnessRouting;
  raw_input: CoreToHarnessRawInput;
  core_analysis?: CoreToHarnessAnalysis;
  research?: CoreToHarnessResearch;
  consume?: CoreToHarnessConsumePolicy;
}

export interface HarnessCaptureResult {
  ok: boolean;
  intent_id?: string;
  title?: string;
  lane?: string;
  rewrite_method?: string;
  raw_intent?: string;
  rewritten_intent?: string;
  requirement_ir?: string;
  requirement_trace?: string;
  stdout?: string;
  stderr?: string;
  error?: string;
}

export interface HarnessConsumeItem {
  ok?: boolean;
  status?: string;
  intent_id?: string;
  sprint_id?: string;
  planner_runtime_submit?: boolean;
  planner_handoff?: Record<string, unknown>;
  artifacts?: Record<string, string>;
  stdout_tail?: string;
  stderr_tail?: string;
}

export interface HarnessConsumeResult {
  ok: boolean;
  count?: number;
  results?: HarnessConsumeItem[];
  stdout?: string;
  stderr?: string;
  error?: string;
}

export interface CoreToHarnessResult {
  ok: boolean;
  request_id: string;
  intent_id?: string;
  capture?: HarnessCaptureResult;
  consume?: HarnessConsumeResult;
  envelope_path?: string;
  warnings?: string[];
  error?: string;
}

export interface HarnessClientOptions {
  harnessDir?: string;
  pythonBin?: string;
  tempDir?: string;
  dryRun?: boolean;
  keepEnvelope?: boolean;
  env?: Record<string, string>;
}

