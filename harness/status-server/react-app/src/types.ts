export type JsonRecord = Record<string, unknown>;

export type StatusPayload = {
  current_sprint?: SprintStatus | null;
  panes?: PaneState[];
  recent_events?: EventRecord[];
  kpi?: JsonRecord;
  physical_operators?: JsonRecord;
  lab_screen?: JsonRecord;
};

export type SprintStatus = {
  sprint_id?: string;
  id?: string;
  title?: string;
  status?: string;
  phase?: string;
  epic_id?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type PaneState = {
  id?: string;
  pane_id?: string;
  role?: string;
  state?: string;
  status?: string;
  model?: string;
  current_activity?: string;
  [key: string]: unknown;
};

export type EventRecord = {
  ts?: string;
  timestamp?: string;
  time?: string;
  sprint_id?: string;
  type?: string;
  event?: string;
  actor?: string;
  role?: string;
  message?: string;
  payload?: JsonRecord;
  [key: string]: unknown;
};

export type SprintIndexResponse = {
  ok: boolean;
  generated_at?: string;
  degraded_sources?: string[];
  data: {
    sprints: SprintSummary[];
    count?: number;
    active_sprints?: string[];
  };
};

export type SprintSummary = {
  sprint_id: string;
  title?: string;
  status?: string;
  phase?: string;
  is_active?: boolean;
  updated_at?: string;
  node_status_counts?: Record<string, number>;
  progress?: JsonRecord;
  stall?: StallSummary;
  latest_event?: EventRecord;
  [key: string]: unknown;
};

export type DashboardResponse = {
  ok: boolean;
  generated_at?: string;
  schema_version?: string;
  degraded_sources?: string[];
  data: DashboardData;
};

export type ProjectionResponse = {
  ok: boolean;
  generated_at?: string;
  schema_version?: string;
  degraded_sources?: string[];
  data: ProjectionData;
};

export type ProjectionData = {
  projection_schema?: string;
  projection_mode?: string;
  lazy_slices?: {
    events?: string;
    deliverables?: string;
    usage?: string;
    [key: string]: unknown;
  };
  sprint_id?: string;
  title?: string;
  status?: string;
  phase?: string;
  sprint?: SprintStatus;
  requirements?: {
    present?: boolean;
    prd?: ProjectionArtifactRef;
    contract?: ProjectionArtifactRef;
    requirement_trace?: ProjectionArtifactRef;
    coverage_report?: ProjectionArtifactRef;
    acceptance_verdict?: ProjectionArtifactRef;
    coverage_summary?: JsonRecord;
    verdict?: string;
    verdict_reasons?: string[];
    [key: string]: unknown;
  };
  plan?: {
    present?: boolean;
    complete?: boolean;
    status?: string;
    design?: ProjectionArtifactRef;
    plan?: ProjectionArtifactRef;
    task_graph?: ProjectionArtifactRef;
    graph_source?: string;
    [key: string]: unknown;
  };
  task_graph?: {
    present?: boolean;
    nodes?: DagNode[];
    edges?: DagEdge[];
    [key: string]: unknown;
  };
  nodes?: DagNode[];
  dependencies?: DagEdge[];
  dispatch?: {
    stall?: StallSummary;
    capability_mismatch?: JsonRecord;
    [key: string]: unknown;
  };
  human_gates?: HumanGate[];
  operators?: JsonRecord[];
  evaluation?: {
    status?: string;
    phase?: string;
    handoff?: ProjectionArtifactRef;
    eval?: ProjectionArtifactRef;
    coverage_report?: ProjectionArtifactRef;
    acceptance_verdict?: ProjectionArtifactRef;
    verdict?: string;
    requested_verdict?: string;
    reasons?: string[];
    coverage_summary?: JsonRecord;
    [key: string]: unknown;
  };
  events?: EventRecord[];
  summary?: {
    progress?: JsonRecord;
    stall?: StallSummary;
    active_node?: string;
    [key: string]: unknown;
  };
  human_action_required?: {
    type?: string;
    primary_artifact?: string | ProjectionArtifactRef;
    [key: string]: unknown;
  };
  available_actions?: ProjectionAction[];
  capability_mismatch?: {
    present?: boolean;
    missing_capability?: string;
    blocked_node?: string;
    [key: string]: unknown;
  };
  artifacts?: ProjectionArtifact[];
  [key: string]: unknown;
};

export type ProjectionArtifactRef = {
  name?: string;
  kind?: string;
  stage?: string;
  rel_path?: string;
  view_url?: string;
  reviewable?: boolean;
  [key: string]: unknown;
};

export type ProjectionArtifact = ProjectionArtifactRef & {
  size?: number;
  mtime?: number;
};

export type HumanGate = {
  kind?: string;
  status?: string;
  allowed_actions?: string[];
  source_artifacts?: string[];
  last_verdict?: JsonRecord | null;
  missing_artifacts?: string[];
  reason?: string;
  [key: string]: unknown;
};

export type ProjectionAction = {
  id?: string;
  label?: string;
  availability?: string;
  safe?: boolean;
  enabled?: boolean;
  endpoint?: string;
  method?: string;
  cli_command?: string;
  effect?: string;
  reason?: string;
  [key: string]: unknown;
};

export type ActionResponse = {
  ok: boolean;
  status?: string;
  error?: string;
  sprint_id?: string;
  projection?: ProjectionData;
  stdout_tail?: string;
  returncode?: number;
  [key: string]: unknown;
};

export type DashboardData = {
  focus_sprint_id?: string;
  sprint?: SprintStatus;
  phase?: string;
  progress?: {
    total_nodes?: number;
    completed_nodes?: number;
    passed_nodes?: number;
    active_nodes?: number;
    running_nodes?: number;
    blocked_nodes?: number;
    failed_nodes?: number;
    pending_nodes?: number;
    percent_complete?: number;
    status_counts?: Record<string, number>;
    [key: string]: unknown;
  };
  dag?: {
    nodes?: DagNode[];
    edges?: DagEdge[];
    [key: string]: unknown;
  };
  blocked_nodes?: DagNode[];
  capabilities?: {
    demand?: Record<string, number>;
    role_demand?: Record<string, number>;
    pane_supply?: PaneSupply[];
    [key: string]: unknown;
  };
  resources?: {
    estimated_total_cost?: number;
    cost_by_status?: Record<string, number>;
    routing_records_for_sprint?: number;
    routing_records_total?: number;
    busy_panes?: string[];
    [key: string]: unknown;
  };
  blocker_diagnostics?: JsonRecord;
  stall?: StallSummary;
  sprint_usage?: {
    total_tokens?: number;
    total_tokens_label?: string;
    models?: UsageModel[];
  };
  [key: string]: unknown;
};

export type DagNode = {
  id?: string;
  node_id?: string;
  title?: string;
  goal?: string;
  status?: string;
  depends_on?: string[];
  required_capabilities?: string[];
  route_decision?: string;
  blocked_reason?: string;
  target_pane?: string;
  estimated_cost?: number;
  [key: string]: unknown;
};

export type DagEdge = {
  from?: string;
  to?: string;
  source?: string;
  target?: string;
  [key: string]: unknown;
};

export type PaneSupply = {
  pane_id?: string;
  role?: string;
  state?: string;
  model?: string;
  provided_capabilities?: string[];
  actor_id?: string;
  lease_state?: string;
  [key: string]: unknown;
};

export type StallSummary = {
  is_stalled?: boolean;
  state?: string;
  reason?: string;
  reasons?: string[];
  blocked_nodes?: string[];
  explanation?: string;
  [key: string]: unknown;
};

export type UsagePayload = {
  ok: boolean;
  source: string;
  scope: string;
  label: string;
  not_per_sprint: boolean;
  not_per_agent: boolean;
  total_used_tokens?: number;
  total_used_tokens_label?: string;
  models?: UsageModel[];
};

export type UsageModel = {
  model_key?: string;
  date?: string;
  used_tokens?: number;
  used_tokens_label?: string;
  cache_path?: string;
};

export type DeliverablesPayload = {
  ok: boolean;
  sprint_id: string;
  items: Deliverable[];
};

export type Deliverable = {
  name: string;
  rel_path: string;
  kind: string;
  size?: number;
  mtime?: number;
  view_url: string;
};

export type IntakeResponse = {
  ok: boolean;
  status?: string;
  sprint_id?: string;
  error?: string;
  stdout_tail?: string;
  returncode?: number;
};

export type SettingsPayload = {
  ok: boolean;
  generated_at?: string;
  source?: string;
  sources?: JsonRecord;
  write_supported?: boolean;
  write_note?: string;
  model_lab_matrix?: {
    value?: string;
    source?: string;
  };
  role_models?: Record<string, { model?: string; source?: string }>;
  physical_operators?: { count?: number; available?: number; busy?: number };
};
