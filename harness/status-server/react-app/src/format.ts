import type {
  DagNode,
  EventRecord,
  JsonRecord,
  SprintSummary,
  StallSummary,
} from "./types";

export const PHASES = [
  "spec",
  "prd_ready",
  "planning_complete",
  "build_complete",
];

export const ROLE_ORDER = ["pm", "planner", "builder", "evaluator"] as const;

export type AgentRole = (typeof ROLE_ORDER)[number];

export type AgentCardModel = {
  role: AgentRole;
  title: string;
  subtitle: string;
  state: "idle" | "working" | "blocked" | "complete";
  activity: string;
  model: string;
  pane: string;
  lastEvent: string;
  provides: string[];
};

export const ROLE_META: Record<AgentRole, { title: string; subtitle: string }> =
  {
    pm: { title: "PM", subtitle: "Intake and scope" },
    planner: { title: "Planner", subtitle: "Plan and routing" },
    builder: { title: "Builder", subtitle: "Implementation" },
    evaluator: { title: "Evaluator", subtitle: "Review and gates" },
  };

export function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

const PLAN_LABEL_ACRONYMS = new Set([
  "ai",
  "api",
  "csv",
  "e2e",
  "html",
  "json",
  "kv",
  "llm",
  "pdf",
  "poc",
  "ui",
  "url",
]);

function humanizePlanStep(value: string): string {
  return value
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) =>
      PLAN_LABEL_ACRONYMS.has(part.toLowerCase())
        ? part.toUpperCase()
        : `${part.charAt(0).toUpperCase()}${part.slice(1)}`,
    )
    .join(" ");
}

export function planNodeLabel(node: DagNode): string {
  const id = asString(node.node_id || node.id).replace(/^build[-_]/i, "");
  if (!id) return asString(node.title, "Untitled step");

  const [base, composition = ""] = id.split("__", 2);
  const label = humanizePlanStep(base);
  const component = composition.match(/_c(\d+)$/i);
  if (component) {
    return `${label} · Part ${Number(component[1])}`;
  }
  return label || asString(node.title, "Untitled step");
}

export function normalizeRole(value: unknown): AgentRole | "" {
  const text = asString(value).toLowerCase();
  if (text.includes("planner") || text.includes("规划")) return "planner";
  if (text.includes("builder") || text.includes("建设")) return "builder";
  if (
    text.includes("evaluator") ||
    text.includes("审判") ||
    text.includes("judge") ||
    text.includes("review")
  )
    return "evaluator";
  if (
    text === "pm" ||
    text.includes("product") ||
    text.includes("manager") ||
    text.includes("经理")
  )
    return "pm";
  return "";
}

// Events arrive wrapped in a generic "log_message" envelope. The real event is in
// payload.legacy_event — sometimes a kind STRING ("plan_verdict"), sometimes the full nested
// event OBJECT ({event, actor, payload, …}). Flatten both so the stream shows the real story.
export function unwrapEvent(event: EventRecord): EventRecord {
  const le = payload(event).legacy_event;
  if (le && typeof le === "object" && !Array.isArray(le)) {
    return { ...event, ...(le as Partial<EventRecord>), type: "" };
  }
  if (typeof le === "string" && le) {
    return { ...event, type: "", event: le };
  }
  return event;
}

export function eventType(event: EventRecord): string {
  const e = unwrapEvent(event);
  return asString(e.type || e.event, "event");
}

export function eventTimestamp(event: EventRecord): string {
  return asString(event.ts || event.timestamp || event.time);
}

function parseDate(value: unknown): Date | null {
  const raw = asString(value);
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function localTimeZoneName(value: unknown = new Date()): string {
  const parsed = parseDate(value) || new Date();
  const part = new Intl.DateTimeFormat([], { timeZoneName: "short" })
    .formatToParts(parsed)
    .find((item) => item.type === "timeZoneName");
  return part?.value || "";
}

export function formatTime(value: unknown): string {
  const raw = asString(value);
  if (!raw) return "pending";
  const parsed = parseDate(raw);
  if (!parsed) return raw;
  return parsed.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  });
}

export function formatDateTime(value: unknown): string {
  const raw = asString(value);
  if (!raw) return "pending";
  const parsed = parseDate(raw);
  if (!parsed) return raw;
  return parsed.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function compactNumber(value: unknown): string {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return "0";
  if (Math.abs(number) >= 1_000_000)
    return `${(number / 1_000_000).toFixed(1)}M`;
  if (Math.abs(number) >= 1_000) return `${(number / 1_000).toFixed(1)}K`;
  return String(Math.round(number));
}

export function titleForSprint(sprint?: Partial<SprintSummary> | null): string {
  return asString(
    sprint?.title,
    asString(sprint?.sprint_id, "No sprint selected"),
  );
}

export function statusTone(
  status?: string,
): "idle" | "working" | "blocked" | "complete" {
  const value = asString(status).toLowerCase();
  if (
    value.includes("blocked") ||
    value.includes("failed") ||
    value.includes("error") ||
    value.includes("stall")
  )
    return "blocked";
  if (
    value.includes("complete") ||
    value.includes("passed") ||
    value.includes("done") ||
    value.includes("build_complete")
  )
    return "complete";
  if (
    value.includes("active") ||
    value.includes("running") ||
    value.includes("working") ||
    value.includes("progress") ||
    value.includes("review")
  )
    return "working";
  return "idle";
}

export function nodeId(node: DagNode): string {
  return asString(node.id || node.node_id, "node");
}

export function nodeTitle(node: DagNode): string {
  return asString(
    node.goal || node.title || node.id || node.node_id,
    "Untitled node",
  );
}

export function shortText(value: unknown, max = 92): string {
  const text = asString(value).replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

export function payload(event: EventRecord): JsonRecord {
  const p: unknown = event.payload;
  if (p && typeof p === "object") return p as JsonRecord;
  // The harness sometimes emits payload as a stringified dict — JSON, or a Python
  // repr ({'k': 'v', 'n': None, 'b': True}). Parse tolerantly so the detail isn't lost.
  if (typeof p === "string" && p.trim().startsWith("{")) {
    const s = p.trim();
    try {
      return JSON.parse(s) as JsonRecord;
    } catch {
      try {
        const j = s
          .replace(/'/g, '"')
          .replace(/\bNone\b/g, "null")
          .replace(/\bTrue\b/g, "true")
          .replace(/\bFalse\b/g, "false");
        const parsed = JSON.parse(j);
        if (parsed && typeof parsed === "object") return parsed as JsonRecord;
      } catch {
        /* leave empty — fall through */
      }
    }
  }
  return {};
}

export function eventActor(event: EventRecord): string {
  return asString(
    event.actor || event.role || payload(event).actor || payload(event).role,
    "Harness",
  );
}

export function humanEvent(event: EventRecord): {
  title: string;
  detail: string;
  tone: string;
} {
  const type = eventType(event);
  const body = payload(event);
  const node = asString(body.node_id || body.node || event.node_id);
  const phase = asString(body.phase || event.phase);
  const decision = asString(body.decision || event.decision);
  const reason = asString(body.reason || body.blocked_reason || event.reason);
  const target = asString(body.target_pane || body.pane || event.target_pane);
  const model = asString(body.model || event.model);
  const message = asString(event.message || body.message);
  const status = asString(body.status);
  const stage = asString(body.stage);
  const role = asString(body.role);
  const intent = asString(body.intent);
  const handoffTo = asString(body.handoff_to || body.target_role);
  const toState = asString(body.to);
  const severity = asString((event as { severity?: unknown }).severity);
  // A compact, human detail pulled from whatever the payload carries, so events read
  // like "stage prd · reason: invalid prd" instead of the generic fallback line.
  const summary =
    [
      stage && `stage ${stage}`,
      phase && `phase ${phase}`,
      role && `role ${role}`,
      intent && intent.replace(/_/g, " "),
      status && status.replace(/_/g, " "),
      node && `node ${node}`,
      target && `pane ${target}`,
      handoffTo && `→ ${handoffTo}`,
      reason && `reason: ${reason.replace(/_/g, " ")}`,
    ]
      .filter(Boolean)
      .join(" · ") || message;
  // Title-case the event kind: dispatch_failed -> "Dispatch failed".
  const humanTitle =
    type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) || "Event";
  const sevTone = severity === "warn" || severity === "error" ? "blocked" : "";

  if (type.includes("phase")) {
    return {
      title: `Phase advanced to ${phase || "next phase"}`,
      detail: message || "Sprint state changed.",
      tone: "working",
    };
  }
  if (type.includes("dispatch")) {
    return {
      title: humanTitle,
      detail: summary,
      tone:
        sevTone ||
        (decision.includes("no_matching") || type.includes("fail")
          ? "blocked"
          : "working"),
    };
  }
  if (
    type.includes("gate") ||
    type.includes("blocked") ||
    decision.includes("no_matching")
  ) {
    return {
      title: "Gate blocked",
      detail:
        summary ||
        reason ||
        message ||
        [node && `node ${node}`, phase && `phase ${phase}`]
          .filter(Boolean)
          .join(" · "),
      tone: "blocked",
    };
  }
  if (type.includes("model_session_started")) {
    return {
      title: "Model session started",
      detail: [model, node && `node ${node}`].filter(Boolean).join(" · "),
      tone: "working",
    };
  }
  if (type.includes("model_session_ended")) {
    return {
      title: "Model session ended",
      detail: [model, node && `node ${node}`].filter(Boolean).join(" · "),
      tone: "complete",
    };
  }
  if (type.includes("intake")) {
    return {
      title: "Task intake created",
      detail: message || "A new sprint was accepted by the harness.",
      tone: "working",
    };
  }
  if (
    type.includes("milestone") ||
    type.includes("complete") ||
    type.includes("passed")
  ) {
    return {
      title: humanTitle,
      detail:
        summary ||
        [node && `node ${node}`, phase && `phase ${phase}`]
          .filter(Boolean)
          .join(" · "),
      tone: "complete",
    };
  }
  if (type.includes("state_chang") || type.includes("state_transition")) {
    // `to` looks like "<sid>:<status>:<phase>:<role>:<hash>" — surface the move.
    const parts = toState.split(":");
    const toStatus = parts[1] || status;
    const toPhase = parts[2] || phase;
    const moved = [toStatus, toPhase]
      .filter((x) => x && x !== "_" && x !== "None")
      .join(" / ");
    return {
      title: type.includes("transition") ? "State transition" : "State changed",
      detail: moved ? `→ ${moved}` : summary,
      tone: statusTone(toStatus || status),
    };
  }
  return {
    title: humanTitle,
    detail: summary || message || "",
    tone:
      sevTone || statusTone(asString(event.status || body.status || status)),
  };
}

const UNTYPED_FAILURE_CODES = new Set(["failed", "error", "unknown", ""]);

export function failureCodeIsTyped(code?: string | null): boolean {
  return !UNTYPED_FAILURE_CODES.has(asString(code).trim().toLowerCase());
}

export function stallCopy(stall?: StallSummary): string {
  if (!stall?.is_stalled) return "";
  const state = asString(stall.state, "stalled").replace(/_/g, " ");
  const typed = stall.failure;
  if (typed && failureCodeIsTyped(typed.code)) {
    const stage = asString(typed.stage).replace(/_/g, " ");
    return stage
      ? `${state}: ${typed.code} during ${stage}`
      : `${state}: ${typed.code}`;
  }
  const reasons = Array.isArray(stall.reasons)
    ? stall.reasons.map((item) => asString(item)).filter(Boolean)
    : [];
  const reason =
    asString(stall.reason || stall.explanation) ||
    reasons.find((item) => failureCodeIsTyped(item)) ||
    (typed || reasons.length
      ? "The runtime reported no typed cause."
      : "The harness is waiting on a gate or missing worker capability.");
  return `${state}: ${reason}`;
}

export type FailureFact = { label: string; value: string };

export function typedFailureFacts(stall?: StallSummary): FailureFact[] {
  const typed = stall?.failure;
  if (!typed) return [];
  const facts: FailureFact[] = [];
  const stage = asString(typed.stage).replace(/_/g, " ");
  if (stage) facts.push({ label: "stage", value: stage });
  facts.push({
    label: "cause",
    value: failureCodeIsTyped(typed.code)
      ? asString(typed.code)
      : "no typed cause reported",
  });
  if (typeof typed.before_execution === "boolean") {
    facts.push({
      label: "when",
      value: typed.before_execution ? "before execution" : "during execution",
    });
  }
  if (typeof typed.retry_safe === "boolean") {
    facts.push({
      label: "retry",
      value: typed.retry_safe ? "safe to retry" : "retry will not help",
    });
  }
  if (asString(typed.node_id)) {
    facts.push({ label: "node", value: asString(typed.node_id) });
  }
  if (asString(typed.operator_id)) {
    facts.push({ label: "operator", value: asString(typed.operator_id) });
  }
  if (asString(typed.receipt_ref)) {
    facts.push({ label: "receipt", value: asString(typed.receipt_ref) });
  }
  return facts;
}

export function mergeEvents(
  existing: EventRecord[],
  incoming: EventRecord[],
): EventRecord[] {
  const seen = new Set<string>();
  const rows = [...incoming, ...existing].filter((event) => {
    const key = JSON.stringify([
      event.sprint_id,
      eventTimestamp(event),
      eventType(event),
      eventActor(event),
      payload(event),
    ]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  rows.sort((a, b) => {
    const at = new Date(eventTimestamp(a)).getTime();
    const bt = new Date(eventTimestamp(b)).getTime();
    return (Number.isFinite(bt) ? bt : 0) - (Number.isFinite(at) ? at : 0);
  });
  return rows.slice(0, 220);
}
