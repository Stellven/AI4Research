import type {
  ActionResponse,
  DeliverablesPayload,
  EventRecord,
  IntakeResponse,
  ProjectionResponse,
  SettingsPayload,
  SprintIndexResponse,
  StatusPayload,
  UsagePayload,
} from "./types";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
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
  const source = new EventSource(`/events?${params.toString()}`);
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
