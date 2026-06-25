import type {
  ActionResponse,
  DeliverablesPayload,
  EventRecord,
  IntakeResponse,
  ProjectionData,
  ProjectionResponse,
  SettingsPayload,
  SprintIndexResponse,
  StatusPayload,
  UsagePayload,
} from "./types";

// Bundled desktop builds (Electron loadFile, file:// origin) set VITE_API_BASE to
// the absolute runtime URL (e.g. http://127.0.0.1:8765) so cross-origin API calls
// resolve. Served/dev builds leave it empty, keeping calls same-origin relative.
const API_BASE =
  (typeof location !== "undefined" &&
    new URLSearchParams(location.search).get("api")) ||
  (import.meta.env.VITE_API_BASE as string | undefined) ||
  "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      typeof payload?.error === "string"
        ? payload.error
        : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export function fetchStatus(sprintId?: string): Promise<StatusPayload> {
  const query = sprintId ? `?sprint_id=${encodeURIComponent(sprintId)}` : "";
  return requestJson<StatusPayload>(`/status${query}`);
}

export function fetchSprints(limit = 120): Promise<SprintIndexResponse> {
  return requestJson<SprintIndexResponse>(`/sprints?limit=${limit}`);
}

export function fetchProjection(
  sprintId: string,
  mode: "fast" | "full" = "fast",
): Promise<ProjectionResponse> {
  const params = new URLSearchParams({ mode });
  return requestJson<ProjectionResponse>(
    `/api/sprints/${encodeURIComponent(sprintId)}/projection?${params.toString()}`,
  );
}

export function fetchEvents(
  sprintId?: string,
  limit = 120,
): Promise<EventRecord[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (sprintId) {
    params.set("sprint_id", sprintId);
  }
  return requestJson<EventRecord[]>(`/events?${params.toString()}`);
}

export function fetchUsage(): Promise<UsagePayload> {
  return requestJson<UsagePayload>("/usage");
}

export function fetchDeliverables(
  sprintId: string,
): Promise<DeliverablesPayload> {
  return requestJson<DeliverablesPayload>(
    `/sprints/${encodeURIComponent(sprintId)}/deliverables`,
  );
}

export function fetchSettings(): Promise<SettingsPayload> {
  return requestJson<SettingsPayload>("/settings");
}

export interface AuthStatus {
  ok: boolean;
  codex: string;
  claude: string;
  glm: string;
  source?: string;
  detail?: Record<string, boolean>;
}

export type AuthLoginState = "idle" | "started" | "pending" | "done" | "failed";

export interface AuthLoginStatus {
  ok: boolean;
  provider: string;
  state: AuthLoginState;
  url?: string | null;
  code?: string | null;
  tail?: string;
  exit_code?: number;
  note?: string;
  auth?: AuthStatus;
  error?: string;
}

// Subscription-first auth: detect provider sign-in state (no token values ever returned).
export function fetchAuthStatus(): Promise<AuthStatus> {
  return requestJson<AuthStatus>("/auth/status");
}

// Zero-step path (WSL): copy creds the user already has on the Windows side.
export function reuseHostCreds(
  provider: string,
): Promise<{ ok: boolean; provider: string; reused: boolean }> {
  return requestJson("/auth/reuse-host-creds", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

// Start a headless device-code login; poll fetchAuthLoginStatus for the URL+code and completion.
export function startAuthLogin(provider: string): Promise<AuthLoginStatus> {
  return requestJson<AuthLoginStatus>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

export function fetchAuthLoginStatus(
  provider: string,
): Promise<AuthLoginStatus> {
  return requestJson<AuthLoginStatus>(
    `/auth/login/status?provider=${encodeURIComponent(provider)}`,
  );
}

// The read-only content URL for a deliverable. Prefer the server-provided view_url
// (real status-server already exposes it); fall back to the documented path query.
export function deliverableUrl(
  sprintId: string,
  item: { rel_path: string; view_url?: string },
): string {
  if (item.view_url && item.view_url.startsWith("/")) return item.view_url;
  return `/sprints/${encodeURIComponent(sprintId)}/deliverables?path=${encodeURIComponent(item.rel_path)}`;
}

export async function fetchDeliverableText(
  url: string,
): Promise<{ text: string; contentType: string }> {
  const response = await fetch(url, { headers: { Accept: "text/plain, */*" } });
  if (!response.ok) {
    throw new Error(`Couldn’t load this file (HTTP ${response.status})`);
  }
  return {
    text: await response.text(),
    contentType: response.headers.get("Content-Type") || "",
  };
}

export function submitIntake(task: string): Promise<IntakeResponse> {
  return requestJson<IntakeResponse>("/intake", {
    method: "POST",
    body: JSON.stringify({ task }),
  });
}

export interface SaveSettingsResponse {
  ok: boolean;
  applied_models?: Record<string, string>;
  applied_runtime?: string;
  written_keys?: string[];
  note?: string;
  error?: string;
}

// Persist model/crew selection (-> solar-user-config.json) and provider API keys
// (-> ~/.solar/secrets/solar-user-secrets.env). Empty key values are ignored
// server-side, so unchanged password fields don't overwrite existing secrets.
export function saveSettings(
  roleModels: Record<string, string>,
  apiKeys: Record<string, string>,
  runtime?: string,
): Promise<SaveSettingsResponse> {
  return requestJson<SaveSettingsResponse>("/settings", {
    method: "POST",
    body: JSON.stringify({
      role_models: roleModels,
      api_keys: apiKeys,
      runtime,
    }),
  });
}

export function submitPlanVerdict(
  sprintId: string,
  verdict: "approve" | "reject",
  reason = "",
): Promise<ActionResponse> {
  return requestJson<ActionResponse>(
    `/api/sprints/${encodeURIComponent(sprintId)}/plan-verdict`,
    {
      method: "POST",
      body: JSON.stringify({ verdict, reason }),
    },
  );
}

export function submitEvalVerdict(
  sprintId: string,
  verdict: "pass" | "fail",
  reason = "",
): Promise<ActionResponse> {
  return requestJson<ActionResponse>(
    `/api/sprints/${encodeURIComponent(sprintId)}/eval-verdict`,
    {
      method: "POST",
      body: JSON.stringify({ verdict, reason }),
    },
  );
}

// Submit the approved Builder handoff into Evaluator review. Wraps the existing
// `solar harness handoff-submit` command — it records and advances state; it does
// not itself guarantee a fresh agent pass.
export function submitHandoff(sprintId: string): Promise<ActionResponse> {
  return requestJson<ActionResponse>(
    `/api/sprints/${encodeURIComponent(sprintId)}/handoff-submit`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export function openEventStream(
  sprintId: string | undefined,
  onEvent: (event: EventRecord) => void,
  onError: () => void,
): EventSource | null {
  if (typeof EventSource === "undefined") {
    return null;
  }
  const params = new URLSearchParams({ stream: "1", limit: "160" });
  if (sprintId) {
    params.set("sprint_id", sprintId);
  }
  const source = new EventSource(`${API_BASE}/events?${params.toString()}`);
  source.addEventListener("solar-event", (message) => {
    try {
      onEvent(JSON.parse((message as MessageEvent).data));
    } catch {
      // Ignore malformed stream fragments; the next event can still render.
    }
  });
  source.onerror = onError;
  return source;
}

export interface ProjectionStreamMessage {
  type: "snapshot" | "delta";
  sprint_id: string;
  generated_at?: string;
  data: ProjectionData;
  // What moved since the previous push — node status transitions plus phase/verdict/gate/stall
  // changes. Empty on the initial snapshot. The dashboard uses this to know what to highlight.
  changed?: {
    nodes?: Array<{ id: string; from?: string | null; to?: string | null }>;
    gates?: Array<{ id: string; from?: string | null; to?: string | null }>;
    phase?: { from?: string; to?: string };
    eval_verdict?: { from?: string; to?: string };
    [key: string]: unknown;
  };
}

// Live projection over SSE. The server pushes a full `snapshot` on connect, then a `delta`
// (full fast `data` + a `changed` summary) only when the projection's semantic signature
// changes — so a quiet sprint produces no traffic. Replaces refetch-on-every-raw-event.
export function openProjectionStream(
  sprintId: string,
  onMessage: (msg: ProjectionStreamMessage) => void,
  onError: () => void,
): EventSource | null {
  if (typeof EventSource === "undefined") {
    return null;
  }
  const source = new EventSource(
    `${API_BASE}/api/sprints/${encodeURIComponent(sprintId)}/projection?stream=1`,
  );
  source.addEventListener("projection", (message) => {
    try {
      onMessage(JSON.parse((message as MessageEvent).data));
    } catch {
      // Ignore malformed fragments; the next push still reconciles state.
    }
  });
  source.onerror = onError;
  return source;
}
