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

// Loopback auth token (security M1): the server injects window.__SOLAR_TOKEN__ into the served
// dashboard, and the desktop's app:// fallback passes it via ?token=. Sent as a header on fetch
// and a query param on EventSource (which can't set headers). The server only ENFORCES it when it
// binds beyond loopback (WSL NAT); it's harmless to send everywhere else.
const AUTH_TOKEN =
  (typeof window !== "undefined" &&
    (window as { __SOLAR_TOKEN__?: string }).__SOLAR_TOKEN__) ||
  (typeof location !== "undefined" &&
    new URLSearchParams(location.search).get("token")) ||
  "";

function withToken(url: string): string {
  if (!AUTH_TOKEN) return url;
  return (
    url +
    (url.includes("?") ? "&" : "?") +
    "token=" +
    encodeURIComponent(AUTH_TOKEN)
  );
}

// Bound every request so a hung backend (first-run auth, a wedged runtime) can't freeze the
// UI forever. Read endpoints return fast, so 30s is plenty. But the SHELL-OUT endpoints
// (intake, plan/eval verdicts, handoff) run a CLI synchronously that can take 1-3 minutes —
// they pass LONG_REQUEST_TIMEOUT_MS so a slow-but-succeeding intake isn't killed at 30s.
const REQUEST_TIMEOUT_MS = 30000;
const LONG_REQUEST_TIMEOUT_MS = 210000;

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(AUTH_TOKEN ? { "X-Solar-Token": AUTH_TOKEN } : {}),
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers || {}),
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
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
  const rel =
    item.view_url && item.view_url.startsWith("/")
      ? item.view_url
      : `/sprints/${encodeURIComponent(sprintId)}/deliverables?path=${encodeURIComponent(item.rel_path)}`;
  // Absolute against the runtime API base — in the desktop the dashboard origin is the
  // bundled file/app, so a bare relative URL "failed to fetch". Same-origin web builds
  // leave API_BASE empty, so this stays relative there.
  return withToken(`${API_BASE}${rel}`);
}

export async function fetchDeliverableText(
  url: string,
): Promise<{ text: string; contentType: string }> {
  const response = await fetch(url, {
    headers: {
      Accept: "text/plain, */*",
      ...(AUTH_TOKEN ? { "X-Solar-Token": AUTH_TOKEN } : {}),
    },
  });
  if (!response.ok) {
    throw new Error(`Couldn’t load this file (HTTP ${response.status})`);
  }
  return {
    text: await response.text(),
    contentType: response.headers.get("Content-Type") || "",
  };
}

function newRequestId(prefix: string): string {
  const cryptoApi = typeof crypto !== "undefined" ? crypto : undefined;
  const raw =
    cryptoApi && "randomUUID" in cryptoApi
      ? cryptoApi.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}-${raw}`;
}

// Dashboard-initiated CONTRACTED runs (P4): a task whose first line is
//   /workflow <workflow_id> [key=value ...]
// is routed through the registered workflow contract instead of the generic
// planner. The server's /intake already accepts workflow_id/workflow_inputs
// (fail-closed on unknown ids); this parses the directive out of the task
// text so both intake entry points support it without extra form chrome.
export function parseIntakeDirectives(raw: string): {
  task: string;
  workflowId?: string;
  workflowInputs?: Record<string, string>;
} {
  const text = String(raw ?? "");
  const newline = text.indexOf("\n");
  const firstLine = (newline === -1 ? text : text.slice(0, newline)).trim();
  if (!firstLine.startsWith("/workflow ")) {
    return { task: text.trim() };
  }
  const rest = newline === -1 ? "" : text.slice(newline + 1);
  const parts = firstLine.slice("/workflow ".length).trim().split(/\s+/);
  const workflowId = (parts.shift() ?? "").replace(/[^A-Za-z0-9_.-]/g, "");
  const workflowInputs: Record<string, string> = {};
  for (const part of parts) {
    const eq = part.indexOf("=");
    if (eq > 0) {
      const key = part.slice(0, eq);
      if (/^[a-z_][a-z0-9_]*$/.test(key)) {
        workflowInputs[key] = part.slice(eq + 1);
      }
    }
  }
  if (!workflowId) {
    return { task: text.trim() };
  }
  return {
    task: rest.trim() || `Contracted run: ${workflowId}`,
    workflowId,
    workflowInputs: Object.keys(workflowInputs).length
      ? workflowInputs
      : undefined,
  };
}

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

export async function submitIntake(
  rawTask: string,
  files: File[] = [],
): Promise<IntakeResponse> {
  const { task, workflowId, workflowInputs } = parseIntakeDirectives(rawTask);
  const body: Record<string, unknown> = {
    task,
    request_id: newRequestId("webapp-intake"),
  };
  if (files.length) {
    body.attachments = await Promise.all(
      files.map(async (file) => ({
        name: file.name,
        mime_type: file.type || "application/octet-stream",
        size: file.size,
        last_modified: file.lastModified,
        content_base64: await fileToBase64(file),
      })),
    );
  }
  if (workflowId) {
    body.workflow_id = workflowId;
    if (workflowInputs) {
      body.workflow_inputs = workflowInputs;
    }
  }
  return requestJson<IntakeResponse>(
    "/intake",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    LONG_REQUEST_TIMEOUT_MS,
  );
}

export interface SaveSettingsResponse {
  ok: boolean;
  applied_models?: Record<string, string>;
  applied_runtime?: string;
  applied_codex?: { search?: boolean; effort?: string };
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
  codex?: { search?: boolean; effort?: string },
): Promise<SaveSettingsResponse> {
  return requestJson<SaveSettingsResponse>("/settings", {
    method: "POST",
    body: JSON.stringify({
      role_models: roleModels,
      api_keys: apiKeys,
      runtime,
      codex,
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
    LONG_REQUEST_TIMEOUT_MS,
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
    LONG_REQUEST_TIMEOUT_MS,
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
    LONG_REQUEST_TIMEOUT_MS,
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
  const source = new EventSource(
    withToken(`${API_BASE}/events?${params.toString()}`),
  );
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
    withToken(
      `${API_BASE}/api/sprints/${encodeURIComponent(sprintId)}/projection?stream=1`,
    ),
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
