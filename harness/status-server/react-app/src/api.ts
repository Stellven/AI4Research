import type {
  DashboardResponse,
  DeliverablesPayload,
  EventRecord,
  IntakeResponse,
  SettingsPayload,
  SprintIndexResponse,
  StatusPayload,
  UsagePayload
} from "./types";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {})
    }
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof payload?.error === "string" ? payload.error : `HTTP ${response.status}`;
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

export function fetchDashboard(sprintId?: string): Promise<DashboardResponse> {
  const query = sprintId ? `?sprint_id=${encodeURIComponent(sprintId)}` : "";
  return requestJson<DashboardResponse>(`/orchestration/dashboard${query}`);
}

export function fetchEvents(sprintId?: string, limit = 120): Promise<EventRecord[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (sprintId) {
    params.set("sprint_id", sprintId);
  }
  return requestJson<EventRecord[]>(`/events?${params.toString()}`);
}

export function fetchUsage(): Promise<UsagePayload> {
  return requestJson<UsagePayload>("/usage");
}

export function fetchDeliverables(sprintId: string): Promise<DeliverablesPayload> {
  return requestJson<DeliverablesPayload>(`/sprints/${encodeURIComponent(sprintId)}/deliverables`);
}

export function fetchSettings(): Promise<SettingsPayload> {
  return requestJson<SettingsPayload>("/settings");
}

export function submitIntake(task: string): Promise<IntakeResponse> {
  return requestJson<IntakeResponse>("/intake", {
    method: "POST",
    body: JSON.stringify({ task })
  });
}

export function openEventStream(sprintId: string | undefined, onEvent: (event: EventRecord) => void, onError: () => void): EventSource | null {
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
