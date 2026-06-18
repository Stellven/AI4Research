import * as Dialog from "@radix-ui/react-dialog";
import * as Popover from "@radix-ui/react-popover";
import * as Switch from "@radix-ui/react-switch";
import * as Tooltip from "@radix-ui/react-tooltip";
import {
  AlertTriangle,
  ArrowUpRight,
  Bot,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Circle,
  Clock3,
  FileCheck2,
  FileText,
  ListTree,
  Loader2,
  MessageSquarePlus,
  Minus,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SquareTerminal,
  Workflow,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  fetchDashboard,
  fetchDeliverables,
  fetchEvents,
  fetchSettings,
  fetchSprints,
  fetchStatus,
  fetchUsage,
  openEventStream,
  submitIntake,
} from "./api";
import {
  AgentCardModel,
  PHASES,
  ROLE_META,
  ROLE_ORDER,
  asString,
  compactNumber,
  eventActor,
  eventTimestamp,
  formatDateTime,
  formatTime,
  humanEvent,
  mergeEvents,
  nodeId,
  nodeTitle,
  normalizeRole,
  payload,
  shortText,
  stallCopy,
  statusTone,
  titleForSprint,
} from "./format";
import type {
  DashboardResponse,
  Deliverable,
  EventRecord,
  SettingsPayload,
  SprintSummary,
  StatusPayload,
  UsagePayload,
} from "./types";

type LoadState = "loading" | "ready" | "error";

type SessionData = {
  status?: StatusPayload;
  dashboard?: DashboardResponse;
  events: EventRecord[];
  usage?: UsagePayload;
  deliverables: Deliverable[];
  state: LoadState;
  error: string;
  streamState: "connecting" | "live" | "retrying" | "off";
  refresh: () => Promise<void>;
};

type SessionCacheEntry = Pick<
  SessionData,
  "status" | "dashboard" | "events" | "usage" | "deliverables"
>;

const sessionDataCache = new Map<string, SessionCacheEntry>();

type ProcessStepState = "active" | "blocked" | "completed" | "pending";

type ProcessStep = {
  id: string;
  actor: string;
  title: string;
  summary: string;
  detail: string;
  timestamp: string;
  state: ProcessStepState;
  tone: "working" | "blocked" | "complete" | "idle";
  defaultExpanded: boolean;
  facts: Array<{ label: string; value: string }>;
  result?: Deliverable;
};

type DesignVariant = "relay" | "dispatch" | "console";

type StageState = "passed" | "active" | "blocked" | "pending";

type PlanStage = {
  id: string;
  label: string;
  state: StageState;
  detail: string;
};

// Original lotus mark — five petals fanning from a common base. Uses
// currentColor so it inherits the brand accent. Not a reproduction of any
// existing trademark; inspired by the fanned-petal flower silhouette.
function BrandMark({ size = 40 }: { size?: number }) {
  // One teardrop petal, pivot at (12,13), tip near the viewport top — wide enough that
  // adjacent petals (72deg apart) overlap. Depth = back-to-front paint order + 3 red
  // lightness steps (darker rear petals occluded by the lighter front one), no glow/bevel.
  const petal = "M12 13C7.7 9.6 8.4 4.2 12 2.6C15.6 4.2 16.3 9.6 12 13Z";
  const petals = [
    { angle: 144, cls: "lotus-back" },
    { angle: 216, cls: "lotus-back" },
    { angle: 72, cls: "lotus-mid" },
    { angle: 288, cls: "lotus-mid" },
    { angle: 0, cls: "lotus-front" },
  ];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      {petals.map(({ angle, cls }) => (
        <path
          key={angle}
          className={cls}
          d={petal}
          transform={`rotate(${angle} 12 13)`}
        />
      ))}
      <circle className="lotus-front" cx="12" cy="13" r="2.4" />
    </svg>
  );
}

function App() {
  return (
    <Tooltip.Provider delayDuration={220}>
      <Shell />
    </Tooltip.Provider>
  );
}

function Shell() {
  const [sprints, setSprints] = useState<SprintSummary[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const selectedSprintId = selectedSprintFromPath(location.pathname);

  const refreshSprints = useCallback(async () => {
    try {
      const response = await fetchSprints();
      setSprints(response.data?.sprints || []);
      setState("ready");
      setError("");
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Unable to load sprints");
    }
  }, []);

  useEffect(() => {
    void refreshSprints();
    const id = window.setInterval(() => void refreshSprints(), 5000);
    return () => window.clearInterval(id);
  }, [refreshSprints]);

  const onCreated = useCallback(
    async (sprintId: string) => {
      await refreshSprints();
      navigate(`/sessions/${encodeURIComponent(sprintId)}`);
    },
    [navigate, refreshSprints],
  );

  return (
    <div className="app-shell">
      <Sidebar
        sprints={sprints}
        selectedSprintId={selectedSprintId}
        state={state}
        error={error}
        onCreated={onCreated}
      />
      <main
        className="main-workspace"
        aria-label="AI4Research session workspace"
      >
        <Routes>
          <Route
            path="/"
            element={<HomeLanding sprints={sprints} onCreated={onCreated} />}
          />
          <Route
            path="/sessions/:sprintId"
            element={
              <SessionRoute
                sprints={sprints}
                onCreated={onCreated}
                onSprintChanged={refreshSprints}
              />
            }
          />
          <Route path="/settings" element={<SettingsView />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function selectedSprintFromPath(pathname: string): string {
  const match = pathname.match(/^\/sessions\/(.+)$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function designVariantFromSearch(search: string): DesignVariant {
  const value = new URLSearchParams(search).get("variant");
  if (value === "dispatch" || value === "console") return value;
  return "relay";
}

function Sidebar({
  sprints,
  selectedSprintId,
  state,
  error,
  onCreated,
}: {
  sprints: SprintSummary[];
  selectedSprintId: string;
  state: LoadState;
  error: string;
  onCreated: (sprintId: string) => Promise<void>;
}) {
  return (
    <aside className="sidebar">
      <NavLink to="/" className="brand-row" aria-label="AI4Research home">
        <div className="brand-mark" aria-hidden="true">
          <BrandMark size={40} />
        </div>
        <div>
          <div className="brand-name">AI4Research</div>
          <div className="brand-subtitle">Multi-agent runtime</div>
        </div>
      </NavLink>

      <NewTaskDialog onCreated={onCreated} buttonClassName="new-task-button" />

      <div className="sidebar-section">
        <div className="sidebar-heading">
          <span>Sessions</span>
        </div>
        <div className="session-list" data-testid="session-list">
          {state === "loading" && <SidebarSkeleton />}
          {state === "error" && <div className="sidebar-error">{error}</div>}
          {state === "ready" && sprints.length === 0 && (
            <div className="sidebar-empty">No sessions yet</div>
          )}
          {sprints.map((sprint) => (
            <NavLink
              key={sprint.sprint_id}
              to={`/sessions/${encodeURIComponent(sprint.sprint_id)}`}
              className={({ isActive }) =>
                `session-link ${isActive || selectedSprintId === sprint.sprint_id ? "is-active" : ""}`
              }
            >
              <span className="session-copy">
                <span className="session-title">{titleForSprint(sprint)}</span>
                <span
                  className={`session-meta ${sprint.stall?.is_stalled ? "is-stalled" : ""}`}
                >
                  {sprint.stall?.is_stalled
                    ? "Stalled"
                    : asString(
                        sprint.phase || sprint.status,
                        "unknown",
                      ).replace(/_/g, " ")}
                </span>
              </span>
            </NavLink>
          ))}
        </div>
      </div>

      <div className="sidebar-footer">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `settings-link ${isActive ? "is-active" : ""}`
          }
        >
          <Settings size={16} />
          <span>Settings</span>
        </NavLink>
      </div>
    </aside>
  );
}

function SidebarSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }, (_, index) => (
        <div className="session-skeleton" key={index}>
          <span />
          <div>
            <i />
            <b />
          </div>
        </div>
      ))}
    </>
  );
}

function sessionTone(
  sprint: SprintSummary,
): "idle" | "working" | "blocked" | "complete" {
  if (sprint.stall?.is_stalled) return "blocked";
  return statusTone(asString(sprint.status || sprint.phase));
}

function NewTaskDialog({
  onCreated,
  buttonClassName,
  compact = false,
}: {
  onCreated: (sprintId: string) => Promise<void>;
  buttonClassName?: string;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const cleanTask = task.trim();
    if (!cleanTask) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await submitIntake(cleanTask);
      if (!response.ok || !response.sprint_id) {
        throw new Error(
          response.error ||
            response.stdout_tail ||
            "Intake did not return a sprint id",
        );
      }
      setTask("");
      setOpen(false);
      await onCreated(response.sprint_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create sprint");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button className={buttonClassName || "primary-button"} type="button">
          <MessageSquarePlus size={compact ? 16 : 18} />
          <span>New task</span>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content">
          <Dialog.Title className="dialog-title">
            Describe what you want done
          </Dialog.Title>
          <Dialog.Description className="dialog-description">
            This starts a real AI4Research intake via the existing CLI.
          </Dialog.Description>
          <form onSubmit={onSubmit} className="intake-form">
            <textarea
              value={task}
              onChange={(event) => setTask(event.target.value)}
              placeholder="Build, investigate, verify, or produce an artifact..."
              autoFocus
              rows={7}
            />
            {error && <div className="form-error">{error}</div>}
            <div className="dialog-actions">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={submitting}
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                className="primary-button"
                disabled={!task.trim() || submitting}
              >
                {submitting ? (
                  <Loader2 className="spin" size={16} />
                ) : (
                  <Play size={16} />
                )}
                <span>{submitting ? "Starting" : "Start work"}</span>
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function SessionRoute({
  sprints,
  onCreated,
  onSprintChanged,
}: {
  sprints: SprintSummary[];
  onCreated: (sprintId: string) => Promise<void>;
  onSprintChanged: () => Promise<void>;
}) {
  const { sprintId = "" } = useParams();
  const decodedSprintId = decodeURIComponent(sprintId);
  const session = useSessionData(decodedSprintId, onSprintChanged);
  const sprint =
    sprints.find((item) => item.sprint_id === decodedSprintId) ||
    session.dashboard?.data?.sprint;

  if (!decodedSprintId) {
    return <HomeLanding sprints={sprints} onCreated={onCreated} />;
  }

  return (
    <SessionView
      sprint={sprint as SprintSummary | undefined}
      sprintId={decodedSprintId}
      session={session}
      onCreated={onCreated}
    />
  );
}

function useSessionData(
  sprintId: string,
  onSprintChanged: () => Promise<void>,
): SessionData {
  const [status, setStatus] = useState<StatusPayload>();
  const [dashboard, setDashboard] = useState<DashboardResponse>();
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [usage, setUsage] = useState<UsagePayload>();
  const [deliverables, setDeliverables] = useState<Deliverable[]>([]);
  const [state, setState] = useState<LoadState>("ready");
  const [error, setError] = useState("");
  const [streamState, setStreamState] = useState<
    "connecting" | "live" | "retrying" | "off"
  >("connecting");
  const selectedSprintRef = useRef(sprintId);

  useEffect(() => {
    selectedSprintRef.current = sprintId;
  }, [sprintId]);

  const refresh = useCallback(async () => {
    if (!sprintId) return;
    const isCurrent = () => selectedSprintRef.current === sprintId;
    const cachePatch = (patch: Partial<SessionCacheEntry>) => {
      const base: SessionCacheEntry = sessionDataCache.get(sprintId) || {
        status: undefined,
        dashboard: undefined,
        events: [],
        usage: undefined,
        deliverables: [],
      };
      sessionDataCache.set(sprintId, { ...base, ...patch });
    };

    setError("");
    setState("ready");

    // Each endpoint applies its own slice as soon as it resolves. A slow
    // endpoint (e.g. /usage, /status) never holds back the process stream,
    // the DAG/plan, or the stall reason — those land the moment their own
    // request returns instead of waiting on the slowest of the batch.
    const results = await Promise.allSettled([
      fetchDashboard(sprintId).then((dashboardResponse) => {
        if (!isCurrent()) return;
        setDashboard(dashboardResponse);
        cachePatch({ dashboard: dashboardResponse });
      }),
      fetchStatus(sprintId).then((statusResponse) => {
        if (!isCurrent()) return;
        setStatus(statusResponse);
        cachePatch({ status: statusResponse });
      }),
      fetchEvents(sprintId, 140).then((eventsResponse) => {
        if (!isCurrent()) return;
        const scopedEvents = eventsResponse.filter(
          (event) => !event.sprint_id || event.sprint_id === sprintId,
        );
        setEvents((existing) => {
          const merged = mergeEvents(
            existing.filter(
              (event) => !event.sprint_id || event.sprint_id === sprintId,
            ),
            scopedEvents,
          );
          cachePatch({ events: merged });
          return merged;
        });
      }),
      fetchUsage().then((usageResponse) => {
        if (!isCurrent()) return;
        setUsage(usageResponse);
        cachePatch({ usage: usageResponse });
      }),
      fetchDeliverables(sprintId).then((deliverablesResponse) => {
        if (!isCurrent()) return;
        const nextDeliverables = deliverablesResponse.items || [];
        setDeliverables(nextDeliverables);
        cachePatch({ deliverables: nextDeliverables });
      }),
    ]);

    if (!isCurrent()) return;
    // Only surface the hard-error screen when the core data is unreachable and
    // there is nothing already on screen to keep.
    const [dashboardResult, , eventsResult] = results;
    const coreFailed =
      dashboardResult.status === "rejected" &&
      eventsResult.status === "rejected";
    if (coreFailed && !sessionDataCache.get(sprintId)?.events?.length) {
      const rejection = results.find(
        (item): item is PromiseRejectedResult => item.status === "rejected",
      );
      const reason = rejection?.reason;
      setError(
        reason instanceof Error ? reason.message : "Unable to load session",
      );
      setState("error");
    }
  }, [sprintId]);

  useEffect(() => {
    const cached = sessionDataCache.get(sprintId);
    if (cached) {
      setStatus(cached.status);
      setDashboard(cached.dashboard);
      setEvents(cached.events);
      setUsage(cached.usage);
      setDeliverables(cached.deliverables);
      setState("ready");
      setError("");
    } else {
      setStatus(undefined);
      setDashboard(undefined);
      setUsage(undefined);
      setDeliverables([]);
      setEvents([]);
      setState("ready");
      setError("");
    }
    setStreamState("connecting");
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!sprintId) return undefined;
    const id = window.setInterval(() => {
      void refresh();
      void onSprintChanged();
    }, 3500);
    return () => window.clearInterval(id);
  }, [onSprintChanged, refresh, sprintId]);

  useEffect(() => {
    if (!sprintId) {
      setStreamState("off");
      return undefined;
    }
    const source = openEventStream(
      sprintId,
      (event) => {
        if (event.sprint_id && event.sprint_id !== selectedSprintRef.current) {
          return;
        }
        setStreamState("live");
        setEvents((existing) => {
          const merged = mergeEvents(existing, [event]);
          const cached = sessionDataCache.get(selectedSprintRef.current);
          if (cached) {
            sessionDataCache.set(selectedSprintRef.current, {
              ...cached,
              events: merged,
            });
          }
          return merged;
        });
      },
      () => setStreamState("retrying"),
    );
    if (!source) {
      setStreamState("off");
      return undefined;
    }
    source.onopen = () => setStreamState("live");
    return () => source.close();
  }, [sprintId]);

  return {
    status,
    dashboard,
    events,
    usage,
    deliverables,
    state,
    error,
    streamState,
    refresh,
  };
}

function SessionView({
  sprint,
  sprintId,
  session,
  onCreated,
}: {
  sprint?: SprintSummary;
  sprintId: string;
  session: SessionData;
  onCreated: (sprintId: string) => Promise<void>;
}) {
  const dashboard = dashboardForSprint(session.dashboard, sprintId);
  const data = dashboard?.data;
  const currentSprint = (data?.sprint ||
    sprint || { sprint_id: sprintId }) as SprintSummary;
  const stall = data?.stall || sprint?.stall;
  const agents = useMemo(
    () => buildAgents(session.status, dashboard, session.events),
    [session.status, dashboard, session.events],
  );
  const phase = asString(
    data?.phase || currentSprint.phase || currentSprint.status,
  );
  const isBlocked = Boolean(stall?.is_stalled);
  const isComplete =
    statusTone(asString(currentSprint.status || phase)) === "complete";
  const gate = useMemo(() => buildGate(dashboard), [dashboard]);
  const processSteps = useMemo(
    () =>
      buildProcessSteps(dashboard, session.events, session.deliverables, phase),
    [dashboard, session.deliverables, session.events, phase],
  );

  return (
    <div className="workspace-scroll">
      <TopBar
        sprint={currentSprint}
        streamState={session.streamState}
        onCreated={onCreated}
      />
      <AnimatePresence mode="popLayout">
        {session.state === "loading" && <LoadingWorkbench key="loading" />}
        {session.state === "error" && (
          <ErrorWorkbench
            key="error"
            message={session.error}
            onRetry={session.refresh}
          />
        )}
        {session.state === "ready" && (
          <motion.div
            key="ready"
            className="process-workbench"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            <AgentSignature agents={agents} gate={gate} isBlocked={isBlocked} />
            <div className="process-results-layout">
              <ProcessStream steps={processSteps} />
              <ResultsRail
                deliverables={session.deliverables}
                usage={session.usage}
                dashboard={dashboard}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function dashboardForSprint(
  dashboard: DashboardResponse | undefined,
  sprintId: string,
): DashboardResponse | undefined {
  if (!dashboard) return undefined;
  const focus = asString(
    dashboard.data?.focus_sprint_id || dashboard.data?.sprint?.sprint_id,
  );
  if (focus && focus !== sprintId) return undefined;
  return dashboard;
}

function stalledPlainLanguage(
  dashboard: DashboardResponse | undefined,
  stallText: string,
): string {
  const raw = [
    stallText,
    ...(dashboard?.data?.stall?.reasons || []),
    dashboard?.data?.stall?.reason,
    dashboard?.data?.stall?.explanation,
  ]
    .map((item) => asString(item))
    .join(" ")
    .toLowerCase();

  if (
    raw.includes("no_matching_worker") ||
    raw.includes("no matching worker") ||
    raw.includes("missing worker")
  ) {
    const capability = missingCapability(dashboard);
    return capability
      ? `No agent provides ${capability}.`
      : "No agent provides the required capability.";
  }

  const capability = missingCapability(dashboard);
  if (capability && dashboard?.data?.stall?.is_stalled) {
    return `No agent provides ${capability}.`;
  }

  return (
    stallText
      .replace(/\bno_matching_worker\b/g, "")
      .replace(/\s*:\s*$/g, "")
      .trim() || "The sprint is waiting on a dispatch gate."
  );
}

function missingCapability(dashboard: DashboardResponse | undefined): string {
  const blockedNode = dashboard?.data?.blocked_nodes?.[0];
  const nodeCapability = blockedNode?.required_capabilities?.[0];
  if (nodeCapability) return nodeCapability;
  const demand = dashboard?.data?.capabilities?.demand || {};
  const demanded = Object.keys(demand).find((key) => key.trim());
  if (demanded) return demanded;
  const nodes = dashboard?.data?.dag?.nodes || [];
  const blockedDagNode = nodes.find(
    (node) => statusTone(asString(node.status)) === "blocked",
  );
  return blockedDagNode?.required_capabilities?.[0] || "";
}

function technicalDetailsForStall(
  dashboard: DashboardResponse | undefined,
  stallText: string,
): string[] {
  const stall = dashboard?.data?.stall;
  if (!stall?.is_stalled) return [];
  const details = [
    asString(stall.state) && `state: ${asString(stall.state)}`,
    stallText && `summary: ${stallText}`,
    ...((stall.reasons || []).map((reason) => `reason: ${reason}`) || []),
    ...((stall.blocked_nodes || []).map((node) => `blocked node: ${node}`) ||
      []),
  ].filter(Boolean) as string[];

  const blockedNodes = [
    ...(dashboard?.data?.blocked_nodes || []),
    ...((dashboard?.data?.dag?.nodes || []).filter(
      (node) => statusTone(asString(node.status)) === "blocked",
    ) || []),
  ];
  blockedNodes.slice(0, 4).forEach((node) => {
    const id = nodeId(node);
    if (node.route_decision) {
      details.push(`route decision ${id}: ${asString(node.route_decision)}`);
    }
    if (node.blocked_reason) {
      details.push(`blocked reason ${id}: ${asString(node.blocked_reason)}`);
    }
    (node.required_capabilities || []).slice(0, 3).forEach((capability) => {
      details.push(`required capability ${id}: ${capability}`);
    });
  });

  return Array.from(new Set(details)).slice(0, 10);
}

function CompactSessionHeader({
  sprint,
  phase,
  isBlocked,
  isComplete,
}: {
  sprint: SprintSummary;
  phase: string;
  isBlocked: boolean;
  isComplete: boolean;
}) {
  const label = isBlocked
    ? "Stalled"
    : isComplete
      ? "Complete"
      : asString(sprint.status || phase, "Active").replace(/_/g, " ");
  const phaseLabel = phase.replace(/_/g, " ");
  const tone = isBlocked ? "blocked" : isComplete ? "complete" : "working";

  return (
    <section className="context-bar" data-testid="process-header">
      <div className="context-main">
        <span className="task-kicker">Task</span>
        <h2 className="context-title">{titleForSprint(sprint)}</h2>
      </div>
      <div className="context-facts">
        <span className={`status-badge tone-${tone}`}>
          {isBlocked ? (
            <AlertTriangle size={13} />
          ) : isComplete ? (
            <CheckCircle2 size={13} />
          ) : (
            <Loader2 className="spin-soft" size={13} />
          )}
          <span>{label}</span>
        </span>
        {phaseLabel && <span className="context-fact">{phaseLabel} phase</span>}
      </div>
    </section>
  );
}

// The single most-important state, pinned at the head of the stream (the hero
// zone) — not a giant title. Amber owns 'stalled' so brand red stays the signal.
function StallCallout({
  dashboard,
  stallText,
}: {
  dashboard?: DashboardResponse;
  stallText: string;
}) {
  const reason = stalledPlainLanguage(dashboard, stallText);
  const technicalDetails = technicalDetailsForStall(dashboard, stallText);
  return (
    <div className="stall-callout" role="status">
      <AlertTriangle size={18} />
      <div className="stall-callout-body">
        <strong>Stalled</strong>
        <p>{reason}</p>
        {technicalDetails.length > 0 && (
          <details className="technical-details">
            <summary>Technical details</summary>
            <ul>
              {technicalDetails.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}

type GateInfo = {
  nodeId: string;
  nodeTitle: string;
  capability: string;
  reason: string;
};

function buildGate(dashboard?: DashboardResponse): GateInfo {
  const nodes = dashboard?.data?.dag?.nodes || [];
  const blocked =
    dashboard?.data?.blocked_nodes?.[0] ||
    nodes.find((node) => statusTone(asString(node.status)) === "blocked");
  return {
    nodeId: blocked ? nodeId(blocked) : "",
    nodeTitle: blocked ? nodeTitle(blocked) : "",
    capability: missingCapability(dashboard),
    reason:
      asString(blocked?.blocked_reason) ||
      asString(dashboard?.data?.stall?.reason),
  };
}

function agentShortName(role: AgentCardModel["role"]): string {
  return ROLE_META[role].title.split(" ")[0];
}

// The signature element: the multi-agent relay. Each variant expresses the
// same subject (who acted, and where the capability gate held the work)
// differently — a handoff spine, a supply/demand ledger, or an operator log.
function AgentSignature({
  agents,
  gate,
  isBlocked,
}: {
  agents: AgentCardModel[];
  gate: GateInfo;
  isBlocked: boolean;
}) {
  // The relay breaks after the last agent that actually advanced the work.
  // A non-sequential status roster — the agents' real current states, with no
  // directional flow/arrows (the orchestration is a DAG, not a line). The actual
  // non-linear handoffs live in the process stream below.
  return (
    <section
      className="agent-signature sig-roster"
      data-testid="agent-presence"
    >
      {agents.map((agent) => (
        <div className={`roster-agent tone-${agent.state}`} key={agent.role}>
          <span className={`state-dot tone-${agent.state}`} />
          <div className="roster-copy">
            <strong>{agentShortName(agent.role)}</strong>
            <span className="roster-state">
              {agent.state === "idle"
                ? "waiting"
                : agent.state === "complete"
                  ? "done"
                  : agent.state}
            </span>
          </div>
        </div>
      ))}
    </section>
  );
}

function ProcessStream({ steps }: { steps: ProcessStep[] }) {
  return (
    <section className="process-stream-panel" data-testid="process-stream">
      <div className="process-step-list">
        {steps.length === 0 && (
          <EmptyInline label="Waiting for agent process events" />
        )}
        {steps.map((step) => (
          <ProcessStepItem key={step.id} step={step} />
        ))}
      </div>
    </section>
  );
}

// A static activity-log entry — no click-to-expand cards. Detail is inline,
// the way Linear/Stripe activity feeds read.
function ProcessStepItem({ step }: { step: ProcessStep }) {
  const icon =
    step.state === "blocked" ? (
      <AlertTriangle size={16} />
    ) : step.state === "completed" ? (
      <CheckCircle2 size={16} />
    ) : step.state === "active" ? (
      <Loader2 className="spin-soft" size={16} />
    ) : (
      <Circle size={15} />
    );
  return (
    <article
      className={`process-step process-step-${step.state}`}
      data-testid={`process-step-${step.state}`}
    >
      <span className="process-step-icon">{icon}</span>
      <div className="process-step-main">
        <div className="process-step-head">
          <strong>{step.title}</strong>
          <span className="process-step-time">
            {formatDateTime(step.timestamp)}
          </span>
        </div>
        {step.summary && <p className="process-step-text">{step.summary}</p>}
        {step.facts.length > 0 && (
          <div className="process-facts">
            {step.facts.map((fact) => (
              <span key={`${fact.label}-${fact.value}`}>
                <small>{fact.label}</small>
                <code>{fact.value}</code>
              </span>
            ))}
          </div>
        )}
        {step.result && (
          <a
            className="step-result-link"
            href={step.result.view_url}
            target="_blank"
            rel="noreferrer"
          >
            <FileCheck2 size={15} />
            <span>Open {step.result.name}</span>
            <ArrowUpRight size={13} />
          </a>
        )}
      </div>
    </article>
  );
}

function ResultsRail({
  deliverables,
  usage,
  dashboard,
}: {
  deliverables: Deliverable[];
  usage?: UsagePayload;
  dashboard?: DashboardResponse;
}) {
  return (
    <aside className="results-rail" data-testid="results-rail">
      <DeliverablesPanel deliverables={deliverables} />
      <UsagePanel usage={usage} dashboard={dashboard} />
    </aside>
  );
}

function buildPlanStages(
  phase: string,
  isBlocked: boolean,
  isComplete: boolean,
): PlanStage[] {
  const currentIndex = PHASES.findIndex((item) => phase.includes(item));
  const normalizedIndex = currentIndex >= 0 ? currentIndex : 0;
  const blockedIndex = isBlocked
    ? Math.min(
        PHASES.length - 1,
        phase.includes("build_complete")
          ? normalizedIndex
          : normalizedIndex + 1,
      )
    : -1;

  return [
    { id: "spec", label: "Spec", complete: "Request accepted" },
    { id: "prd_ready", label: "PRD", complete: "Requirements shaped" },
    { id: "planning_complete", label: "Plan", complete: "DAG prepared" },
    { id: "build_complete", label: "Build", complete: "Output produced" },
  ].map((stage, index) => {
    let state: StageState = "pending";
    if (isComplete || index < normalizedIndex) state = "passed";
    if (!isComplete && index === normalizedIndex) state = "active";
    if (index === blockedIndex) state = "blocked";
    if (isBlocked && index < blockedIndex) state = "passed";
    return {
      id: stage.id,
      label: stage.label,
      state,
      detail:
        state === "passed"
          ? stage.complete
          : state === "blocked"
            ? "Blocked by dispatch capability"
            : state === "active"
              ? "Current stage"
              : "Waiting",
    };
  });
}

function GraphSummaryPanel({
  dashboard,
  phase,
  isBlocked,
  isComplete,
}: {
  dashboard?: DashboardResponse;
  phase: string;
  isBlocked: boolean;
  isComplete: boolean;
}) {
  const nodes = dashboard?.data?.dag?.nodes || [];
  const active = nodes.find(
    (node) => statusTone(asString(node.status)) === "working",
  );
  const blocked = nodes.filter(
    (node) => statusTone(asString(node.status)) === "blocked",
  );
  const stages = buildPlanStages(phase, isBlocked, isComplete);
  return (
    <section className="panel graph-summary-panel" data-testid="graph-summary">
      <SectionHeader
        icon={<ListTree size={17} />}
        title="Plan"
        detail={`${nodes.length} nodes`}
      />
      <div className="stage-list" aria-label="Discrete sprint stages">
        {stages.map((stage) => (
          <div className={`stage-row stage-${stage.state}`} key={stage.id}>
            <span className="stage-marker" aria-hidden="true">
              {stage.state === "passed" ? <CheckCircle2 size={14} /> : null}
            </span>
            <div>
              <strong>{stage.label}</strong>
              <p>{stage.detail}</p>
            </div>
          </div>
        ))}
      </div>
      {nodes.length === 0 && <EmptyInline label="No DAG available" />}
      {active && (
        <div className="plan-focus">
          <span className="state-dot tone-working" />
          <div>
            <strong>{nodeId(active)}</strong>
            <p>{nodeTitle(active)}</p>
          </div>
        </div>
      )}
      {blocked.length > 0 && (
        <div className="plan-focus blocked">
          <span className="state-dot tone-blocked" />
          <div>
            <strong>{blocked.length} blocked</strong>
            <p>
              {shortText(blocked.map((node) => nodeId(node)).join(", "), 96)}
            </p>
          </div>
        </div>
      )}
      <div className="mini-node-list">
        {nodes.slice(0, 6).map((node) => (
          <div key={nodeId(node)}>
            <span
              className={`state-dot tone-${statusTone(asString(node.status))}`}
            />
            <span>{nodeId(node)}</span>
            <strong>
              {asString(node.status, "pending").replace(/_/g, " ")}
            </strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function buildProcessSteps(
  dashboard: DashboardResponse | undefined,
  events: EventRecord[],
  deliverables: Deliverable[],
  phase: string,
): ProcessStep[] {
  const steps: ProcessStep[] = [];
  const orderedEvents = [...events].sort(
    (a, b) => eventTimeValue(a) - eventTimeValue(b),
  );

  orderedEvents.forEach((event, index) => {
    steps.push(processStepFromEvent(event, index === orderedEvents.length - 1));
  });

  const nodes = dashboard?.data?.dag?.nodes || [];
  if (steps.length === 0 && nodes.length > 0) {
    nodes.forEach((node, index) => {
      steps.push(processStepFromNode(node, index === nodes.length - 1, phase));
    });
  }

  const stall = dashboard?.data?.stall;
  if (stall?.is_stalled && !steps.some((step) => step.state === "blocked")) {
    steps.push({
      id: "stall-summary",
      actor: "Harness",
      title: "Dispatch is blocked",
      summary: stallCopy(stall),
      detail:
        stallCopy(stall) ||
        "The sprint is waiting on a dispatch gate or missing worker capability.",
      timestamp: dashboard?.generated_at || "",
      state: "blocked",
      tone: "blocked",
      defaultExpanded: true,
      facts: [
        {
          label: "state",
          value: asString(stall.state, "stalled").replace(/_/g, " "),
        },
        { label: "phase", value: phase.replace(/_/g, " ") },
      ],
    });
  }

  const primaryDeliverable = deliverables.find(
    (item) => item.kind === "html" || item.name.endsWith(".html"),
  );
  if (primaryDeliverable && !stall?.is_stalled) {
    steps.push({
      id: `deliverable-${primaryDeliverable.rel_path}`,
      actor: "Harness",
      title: "Deliverable is ready",
      summary: `${primaryDeliverable.name} is ready to open.`,
      detail:
        "The output is separated from the process stream so review can happen without digging through agent telemetry.",
      timestamp: primaryDeliverable.mtime
        ? new Date(primaryDeliverable.mtime * 1000).toISOString()
        : dashboard?.generated_at || "",
      state: "completed",
      tone: "complete",
      defaultExpanded: false,
      facts: [
        { label: "kind", value: primaryDeliverable.kind.toUpperCase() },
        {
          label: "size",
          value: `${compactNumber(primaryDeliverable.size || 0)}B`,
        },
      ],
      result: primaryDeliverable,
    });
  }

  if (steps.length === 0) {
    return [];
  }

  // Oldest -> newest: read the run as a narrative top-down (the relay carries
  // the current state, so the stream doesn't need newest-first).
  const sorted = steps.sort(
    (a, b) => timestampValue(a.timestamp) - timestampValue(b.timestamp),
  );
  return sorted.map((step, index) => ({
    ...step,
    defaultExpanded:
      step.defaultExpanded ||
      step.state === "blocked" ||
      (index === sorted.length - 1 && step.state === "active"),
  }));
}

function processStepFromEvent(
  event: EventRecord,
  latest: boolean,
): ProcessStep {
  const body = payload(event);
  const type = event.type || event.event || "event";
  const actor = eventActor(event);
  const node = asString(body.node_id || body.node || event.node_id);
  const phase = asString(body.phase || event.phase);
  const decision = asString(body.decision || event.decision);
  const target = asString(body.target_pane || body.pane || event.target_pane);
  const reason = asString(body.reason || body.blocked_reason || event.reason);
  const model = asString(body.model || event.model);
  const thought = asString(
    body.thought || body.summary || body.message || event.message,
  );
  const readable = humanEvent(event);
  const blocked =
    readable.tone === "blocked" ||
    String(type).includes("blocked") ||
    decision.includes("no_matching");
  const completed =
    readable.tone === "complete" ||
    String(type).includes("completed") ||
    String(type).includes("ended") ||
    String(type).includes("passed");
  const state: ProcessStepState = blocked
    ? "blocked"
    : latest && !completed
      ? "active"
      : completed
        ? "completed"
        : "completed";
  const title = processTitle(type, actor, { node, phase, decision, target });
  const summary =
    processSummary(type, { node, phase, decision, target, reason, thought }) ||
    readable.detail ||
    readable.title;
  const facts = [
    node && { label: "node", value: node },
    phase && { label: "phase", value: phase.replace(/_/g, " ") },
    decision && { label: "decision", value: decision.replace(/_/g, " ") },
    target && { label: "target", value: target },
    model && { label: "model", value: model },
    reason && { label: "reason", value: shortText(reason, 80) },
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  return {
    id: `${eventTimestamp(event) || "event"}-${type}-${actor}-${node || facts.length}`,
    actor,
    title,
    summary,
    detail:
      thought ||
      readable.detail ||
      "The harness recorded this process step from the live event stream.",
    timestamp: eventTimestamp(event),
    state,
    tone: blocked ? "blocked" : completed ? "complete" : "working",
    defaultExpanded: blocked || (latest && !completed),
    facts,
  };
}

function processStepFromNode(
  node: { [key: string]: unknown },
  latest: boolean,
  phase: string,
): ProcessStep {
  const status = asString(node.status, "pending");
  const tone = statusTone(status);
  const state: ProcessStepState =
    tone === "blocked"
      ? "blocked"
      : tone === "working"
        ? "active"
        : tone === "complete"
          ? "completed"
          : "pending";
  return {
    id: `node-${nodeId(node)}`,
    actor: "Planner",
    title: `${nodeId(node)} is ${status.replace(/_/g, " ")}`,
    summary: nodeTitle(node),
    detail: `Planner DAG node ${nodeId(node)} is currently ${status.replace(/_/g, " ")}.`,
    timestamp: "",
    state,
    tone:
      tone === "complete"
        ? "complete"
        : tone === "blocked"
          ? "blocked"
          : tone === "working"
            ? "working"
            : "idle",
    defaultExpanded: state === "blocked" || state === "active",
    facts: [
      { label: "phase", value: phase.replace(/_/g, " ") },
      { label: "status", value: status.replace(/_/g, " ") },
    ],
  };
}

function processTitle(
  type: unknown,
  actor: string,
  values: { node: string; phase: string; decision: string; target: string },
): string {
  const eventType = asString(type);
  if (eventType.includes("intake")) return `${actor} scoped the request`;
  if (eventType.includes("phase"))
    return `${actor} moved the sprint to ${values.phase.replace(/_/g, " ") || "the next phase"}`;
  if (eventType.includes("dispatch") && values.decision.includes("dispatched"))
    return `${actor} routed ${values.node || "work"}${values.target ? ` to ${values.target}` : ""}`;
  if (eventType.includes("dispatch"))
    return `${actor} made a dispatch decision`;
  if (eventType.includes("model_session_started"))
    return `${actor} started work${values.node ? ` on ${values.node}` : ""}`;
  if (eventType.includes("model_session_ended"))
    return `${actor} finished a model session`;
  if (eventType.includes("gate") || eventType.includes("blocked"))
    return `Dispatch blocked${values.node ? ` for ${values.node}` : ""}`;
  if (eventType.includes("milestone") || eventType.includes("complete"))
    return `${actor} recorded a result`;
  return humanizeToken(eventType);
}

function processSummary(
  type: unknown,
  values: {
    node: string;
    phase: string;
    decision: string;
    target: string;
    reason: string;
    thought: string;
  },
): string {
  const eventType = asString(type);
  if (values.reason) return shortText(values.reason, 120);
  if (values.thought) return shortText(values.thought, 120);
  if (eventType.includes("phase"))
    return `Sprint phase is now ${values.phase.replace(/_/g, " ")}.`;
  if (eventType.includes("dispatch"))
    return [
      values.node && `node ${values.node}`,
      values.decision && values.decision.replace(/_/g, " "),
      values.target && `target ${values.target}`,
    ]
      .filter(Boolean)
      .join(" · ");
  if (eventType.includes("model_session_started"))
    return values.node
      ? `The agent is working on ${values.node}.`
      : "An agent model session started.";
  return "";
}

function humanizeToken(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function eventTimeValue(event: EventRecord): number {
  return timestampValue(eventTimestamp(event));
}

function timestampValue(value: string): number {
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function TopBar({
  sprint,
  streamState,
  onCreated,
}: {
  sprint: SprintSummary;
  streamState: string;
  onCreated: (sprintId: string) => Promise<void>;
}) {
  return (
    <header className="topbar">
      <div className="topbar-title-block">
        <div className="topbar-title">
          <span>{titleForSprint(sprint)}</span>
        </div>
      </div>
      <div className="topbar-actions">
        {streamState !== "live" && (
          <div className={`stream-chip stream-${streamState}`}>
            <Radio size={14} />
            <span>
              {streamState === "retrying"
                ? "reconnecting"
                : streamState === "off"
                  ? "offline"
                  : streamState}
            </span>
          </div>
        )}
        <NewTaskDialog
          onCreated={onCreated}
          buttonClassName="primary-button topbar-new-task"
          compact
        />
      </div>
    </header>
  );
}

function buildAgents(
  status?: StatusPayload,
  dashboard?: DashboardResponse,
  events: EventRecord[] = [],
): AgentCardModel[] {
  const panes = [
    ...(status?.panes || []),
    ...((dashboard?.data?.capabilities?.pane_supply || []).map((pane) => ({
      id: pane.pane_id,
      pane_id: pane.pane_id,
      role: pane.role,
      state: pane.state,
      status: pane.state,
      current_activity: "",
      model: pane.model,
      provided_capabilities: pane.provided_capabilities,
    })) || []),
  ];

  return ROLE_ORDER.map((role) => {
    const meta = ROLE_META[role];
    const pane = panes.find((item) => normalizeRole(item.role) === role);
    const recent = events.find(
      (event) => normalizeRole(eventActor(event)) === role,
    );
    const readable = recent ? humanEvent(recent) : undefined;
    const paneState = asString(pane?.state || pane?.status);
    const eventState = readable?.tone || "";
    const state =
      eventState === "blocked"
        ? "blocked"
        : eventState === "complete"
          ? "complete"
          : statusTone(paneState || eventState);
    return {
      role,
      title: meta.title,
      subtitle: meta.subtitle,
      state,
      activity:
        asString(pane?.current_activity) ||
        readable?.title ||
        "Waiting for harness activity",
      model: asString(pane?.model),
      pane: asString(pane?.id || pane?.pane_id),
      lastEvent: readable
        ? `${formatTime(eventTimestamp(recent as EventRecord))} · ${readable.detail || readable.title}`
        : "No recent event",
      provides: Array.isArray(pane?.provided_capabilities)
        ? (pane?.provided_capabilities as string[])
        : [],
    };
  });
}

function DeliverablesPanel({ deliverables }: { deliverables: Deliverable[] }) {
  return (
    <section
      className="panel deliverables-panel"
      data-testid="deliverables-panel"
    >
      <div className="panel-head">
        <h2>Deliverables</h2>
        <span>{deliverables.length}</span>
      </div>
      {deliverables.length === 0 ? (
        <EmptyInline label="No artifacts produced yet" />
      ) : (
        <div className="artifact-list">
          {deliverables.slice(0, 6).map((item) => (
            <a
              className="artifact-row"
              href={item.view_url}
              target="_blank"
              rel="noreferrer"
              key={item.rel_path}
            >
              <FileText className="artifact-icon" size={15} />
              <span className="artifact-name">{item.name}</span>
              <span className="artifact-meta">{item.kind.toUpperCase()}</span>
              <ArrowUpRight size={14} />
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

function UsagePanel({
  usage,
  dashboard,
}: {
  usage?: UsagePayload;
  dashboard?: DashboardResponse;
}) {
  const sprintUsage = dashboard?.data?.sprint_usage;
  const scoped = Boolean(
    sprintUsage &&
    (sprintUsage.total_tokens_label || sprintUsage.models?.length),
  );
  const total = scoped
    ? sprintUsage?.total_tokens_label || "0 tok"
    : usage?.total_used_tokens_label || "0 tok";
  const models = (scoped ? sprintUsage?.models : usage?.models) || [];
  return (
    <section className="panel usage-panel" data-testid="usage-panel">
      <div className="usage-head">
        <span>{scoped ? "This sprint" : "Usage"}</span>
        <strong>{total}</strong>
      </div>
      <div className="usage-models">
        {models.slice(0, 4).map((model) => (
          <div
            className="usage-model"
            key={`${model.model_key}-${model.date ?? ""}`}
          >
            <span>{model.model_key}</span>
            <strong>{model.used_tokens_label}</strong>
          </div>
        ))}
      </div>
      <p className="usage-foot">
        {scoped
          ? "Tokens used by this sprint, per model."
          : "Per model, per day (account-wide) — runtime does not report per-sprint tokens."}
      </p>
    </section>
  );
}

const MODEL_OPTIONS = [
  "claude-opus-4.x",
  "claude-sonnet-4.x",
  "claude-haiku-4.x",
  "glm-4.6",
];

const LAB_MODES = [
  { id: "all-claude", label: "All-Claude" },
  { id: "all-glm", label: "All-GLM" },
  { id: "custom", label: "Custom" },
];

const API_PROVIDERS = [
  { id: "anthropic", label: "Anthropic", hint: "Claude models" },
  { id: "zai", label: "Z.ai", hint: "GLM models" },
];

function SettingsView() {
  const [settings, setSettings] = useState<SettingsPayload>();
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");

  const [roleModels, setRoleModels] = useState<Record<string, string>>({});
  const [agentOn, setAgentOn] = useState<Record<string, boolean>>({});
  const [labMode, setLabMode] = useState("all-claude");
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [usage, setUsage] = useState<UsagePayload>();

  const refresh = useCallback(async () => {
    try {
      const response = await fetchSettings();
      setSettings(response);
      void fetchUsage()
        .then(setUsage)
        .catch(() => undefined);
      const models: Record<string, string> = {};
      const on: Record<string, boolean> = {};
      ROLE_ORDER.forEach((role) => {
        models[role] =
          asString(response.role_models?.[role]?.model) || MODEL_OPTIONS[0];
        on[role] = true;
      });
      setRoleModels(models);
      setAgentOn(on);
      setLabMode(asString(response.model_lab_matrix?.value) || "all-claude");
      setState("ready");
      setError("");
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Unable to load settings");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function applyLabMode(mode: string) {
    setLabMode(mode);
    if (mode === "all-claude") {
      setRoleModels(
        Object.fromEntries(ROLE_ORDER.map((role) => [role, "claude-opus-4.x"])),
      );
    } else if (mode === "all-glm") {
      setRoleModels(
        Object.fromEntries(ROLE_ORDER.map((role) => [role, "glm-4.6"])),
      );
    }
  }

  return (
    <div className="workspace-scroll">
      <header className="topbar">
        <div className="topbar-title">
          <Settings size={17} />
          <span>Settings</span>
        </div>
        <button
          type="button"
          className="icon-text-button"
          onClick={() => void refresh()}
        >
          <RefreshCw size={15} />
          <span>Reload from runtime</span>
        </button>
      </header>
      <div className="settings-layout" data-testid="settings-view">
        <section className="compact-session-header">
          <div className="compact-title-block">
            <div className="task-eyebrow">
              <span className="task-kicker">Configuration</span>
            </div>
            <h1>Agents, models &amp; keys</h1>
          </div>
        </section>

        <div className="settings-notice">
          <ShieldCheck size={15} />
          <p>
            Read from the runtime ({settings?.source || "status-server"}). Edits
            here are staged in this view only — AI4Research P0 has no write path
            yet, so nothing is persisted to the runtime or sent anywhere.
          </p>
        </div>

        {state === "loading" && <LoadingWorkbench />}
        {state === "error" && (
          <ErrorWorkbench message={error} onRetry={refresh} />
        )}
        {state === "ready" && (
          <>
            <section className="settings-block">
              <SectionHeader
                icon={<SquareTerminal size={17} />}
                title="Lab matrix"
                detail={labMode}
              />
              <p className="settings-help">
                How agents map to model families. Custom lets you set each agent
                below.
              </p>
              <div
                className="segmented"
                role="group"
                aria-label="Lab matrix mode"
              >
                {LAB_MODES.map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    className={`segmented-option ${labMode === mode.id ? "is-active" : ""}`}
                    aria-pressed={labMode === mode.id}
                    onClick={() => applyLabMode(mode.id)}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
            </section>

            <section className="settings-block">
              <SectionHeader
                icon={<Bot size={17} />}
                title="Agents & models"
                detail={`${ROLE_ORDER.length} agents`}
              />
              <div className="agent-config-list">
                {ROLE_ORDER.map((role) => (
                  <div
                    className={`agent-config-row ${agentOn[role] ? "" : "is-off"}`}
                    key={role}
                  >
                    <Switch.Root
                      className="switch-root"
                      checked={Boolean(agentOn[role])}
                      onCheckedChange={(value) =>
                        setAgentOn((prev) => ({ ...prev, [role]: value }))
                      }
                      aria-label={`Enable ${ROLE_META[role].title}`}
                    >
                      <Switch.Thumb className="switch-thumb" />
                    </Switch.Root>
                    <div className="agent-config-id">
                      <strong>{ROLE_META[role].title.split(" ")[0]}</strong>
                      <span>{ROLE_META[role].subtitle}</span>
                    </div>
                    <div className="model-select">
                      <select
                        aria-label={`${ROLE_META[role].title} model`}
                        value={roleModels[role] || MODEL_OPTIONS[0]}
                        disabled={!agentOn[role]}
                        onChange={(event) => {
                          const value = event.target.value;
                          setRoleModels((prev) => ({ ...prev, [role]: value }));
                          setLabMode("custom");
                        }}
                      >
                        {MODEL_OPTIONS.map((model) => (
                          <option key={model} value={model}>
                            {model}
                          </option>
                        ))}
                      </select>
                      <ChevronDown size={14} aria-hidden="true" />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="settings-block">
              <SectionHeader
                icon={<ShieldCheck size={17} />}
                title="Provider API keys"
                detail="local only"
              />
              <p className="settings-help">
                Held in this view only; never transmitted until a runtime write
                path exists.
              </p>
              <div className="key-list">
                {API_PROVIDERS.map((provider) => (
                  <div className="key-row" key={provider.id}>
                    <div className="key-id">
                      <strong>{provider.label}</strong>
                      <span>{provider.hint}</span>
                    </div>
                    <input
                      type="password"
                      className="key-input"
                      placeholder="sk-…"
                      autoComplete="off"
                      value={apiKeys[provider.id] || ""}
                      onChange={(event) =>
                        setApiKeys((prev) => ({
                          ...prev,
                          [provider.id]: event.target.value,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </section>

            <section className="settings-block">
              <SectionHeader
                icon={<Clock3 size={17} />}
                title="Account token usage"
                detail={usage?.total_used_tokens_label || "—"}
              />
              <p className="settings-help">
                Total across all sprints, per model, today — the account-wide
                quota signal. (Per-sprint usage shows on each session.)
              </p>
              <div className="usage-models">
                {(usage?.models || []).length === 0 && (
                  <EmptyInline label="No usage signal available" />
                )}
                {(usage?.models || []).map((model) => (
                  <div
                    className="usage-model"
                    key={`${model.model_key}-${model.date ?? ""}`}
                  >
                    <span>{model.model_key}</span>
                    <strong>{model.used_tokens_label}</strong>
                  </div>
                ))}
              </div>
            </section>

            <div className="settings-actions">
              <span className="settings-actions-note">
                Saving to the runtime is not enabled in P0.
              </span>
              <button
                type="button"
                className="primary-button"
                disabled
                title="Runtime write path not enabled in P0"
              >
                <span>Save configuration</span>
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function defaultRoleModels(): Record<string, string> {
  return Object.fromEntries(ROLE_ORDER.map((role) => [role, MODEL_OPTIONS[0]]));
}

// Staged-only crew config for the launcher. Seeds from the runtime (read-only) so the
// shown models are real, not invented; nothing here is sent with the intake or persisted
// — P0 has no write path, and "Start work" launches on the runtime's configured crew.
const MAX_BUILD_PANES_FALLBACK = 4;

function useCrew() {
  const [open, setOpen] = useState(false);
  const [labMode, setLabMode] = useState("all-claude");
  const [roleModels, setRoleModels] =
    useState<Record<string, string>>(defaultRoleModels);
  // Build-pane parallelism. maxPanes is the runtime's real operator budget
  // (physical_operators.count); the chosen count is staged like the rest of the crew.
  const [buildPanes, setBuildPanesRaw] = useState(1);
  const [maxPanes, setMaxPanes] = useState(MAX_BUILD_PANES_FALLBACK);

  useEffect(() => {
    let alive = true;
    void fetchSettings()
      .then((res) => {
        if (!alive) return;
        const models: Record<string, string> = {};
        ROLE_ORDER.forEach((role) => {
          models[role] =
            asString(res.role_models?.[role]?.model) || MODEL_OPTIONS[0];
        });
        setRoleModels(models);
        setLabMode(asString(res.model_lab_matrix?.value) || "all-claude");
        const ops = Number(res.physical_operators?.count);
        if (Number.isFinite(ops) && ops >= 1) setMaxPanes(ops);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  function setBuildPanes(next: number) {
    setBuildPanesRaw(Math.max(1, Math.min(maxPanes, next)));
  }

  function applyPreset(mode: string) {
    setLabMode(mode);
    if (mode === "all-claude") {
      setRoleModels(
        Object.fromEntries(ROLE_ORDER.map((role) => [role, "claude-opus-4.x"])),
      );
    } else if (mode === "all-glm") {
      setRoleModels(
        Object.fromEntries(ROLE_ORDER.map((role) => [role, "glm-4.6"])),
      );
    }
  }

  function setRoleModel(role: string, value: string) {
    setRoleModels((prev) => ({ ...prev, [role]: value }));
    setLabMode("custom");
  }

  const presetLabel =
    LAB_MODES.find((mode) => mode.id === labMode)?.label ?? "Custom";

  return {
    open,
    setOpen,
    labMode,
    roleModels,
    applyPreset,
    setRoleModel,
    presetLabel,
    buildPanes,
    maxPanes,
    setBuildPanes,
  };
}

type Crew = ReturnType<typeof useCrew>;

function CrewPanel({ crew }: { crew: Crew }) {
  return (
    <section className="crew-panel" id="crew-panel" aria-label="Crew">
      <div className="crew-panel-head">
        <span className="crew-panel-title">Crew</span>
        <span className="crew-panel-count">{ROLE_ORDER.length} agents</span>
      </div>
      <div className="segmented" role="group" aria-label="Crew preset">
        {LAB_MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            className={`segmented-option ${crew.labMode === mode.id ? "is-active" : ""} ${mode.id === "custom" ? "is-computed" : ""}`}
            aria-pressed={crew.labMode === mode.id}
            onClick={() => crew.applyPreset(mode.id)}
          >
            {mode.label}
          </button>
        ))}
      </div>
      <div className="crew-agent-list">
        {ROLE_ORDER.map((role) => (
          <div className="crew-agent-row" key={role}>
            <div className="crew-agent-id">
              <strong>{ROLE_META[role].title.split(" ")[0]}</strong>
              <span>{ROLE_META[role].subtitle}</span>
            </div>
            <div className="model-select">
              <select
                aria-label={`${ROLE_META[role].title} model`}
                value={crew.roleModels[role] || MODEL_OPTIONS[0]}
                onChange={(event) =>
                  crew.setRoleModel(role, event.target.value)
                }
              >
                {MODEL_OPTIONS.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} aria-hidden="true" />
            </div>
          </div>
        ))}
      </div>
      <div className="crew-panes-row">
        <div className="crew-agent-id">
          <strong>Build panes</strong>
          <span>Parallel build workers · up to {crew.maxPanes}</span>
        </div>
        <div className="crew-stepper" role="group" aria-label="Build panes">
          <button
            type="button"
            className="crew-stepper-btn"
            onClick={() => crew.setBuildPanes(crew.buildPanes - 1)}
            disabled={crew.buildPanes <= 1}
            aria-label="Fewer build panes"
          >
            <Minus size={14} aria-hidden="true" />
          </button>
          <span className="crew-stepper-value">{crew.buildPanes}</span>
          <button
            type="button"
            className="crew-stepper-btn"
            onClick={() => crew.setBuildPanes(crew.buildPanes + 1)}
            disabled={crew.buildPanes >= crew.maxPanes}
            aria-label="More build panes"
          >
            <Plus size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
      <p className="crew-panel-note">
        Staged preview — the crew and build panes you set here aren’t wired to
        the run yet, so “Start work” launches on the runtime’s configured crew.
        Set them for real in Settings once a write path exists.
      </p>
    </section>
  );
}

function HomeLanding({
  sprints,
  onCreated,
}: {
  sprints: SprintSummary[];
  onCreated: (sprintId: string) => Promise<void>;
}) {
  const crew = useCrew();
  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function start() {
    const clean = task.trim();
    if (!clean || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await submitIntake(clean);
      if (!response.ok || !response.sprint_id) {
        throw new Error(
          response.error ||
            response.stdout_tail ||
            "Intake did not return a sprint id",
        );
      }
      setTask("");
      await onCreated(response.sprint_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start work");
    } finally {
      setSubmitting(false);
    }
  }

  const recent = sprints.slice(0, 6);

  return (
    <div className="home-landing" data-testid="home-landing">
      <div className="home-inner">
        <h1>What do you want done?</h1>
        <p className="home-sub">
          Describe a task. AI4Research routes it through PM, Planner, Builder,
          and Evaluator agents — and tells you plainly when it stalls.
        </p>
        <form
          className="home-prompt"
          onSubmit={(event) => {
            event.preventDefault();
            void start();
          }}
        >
          <textarea
            value={task}
            onChange={(event) => setTask(event.target.value)}
            placeholder="Build, investigate, verify, or produce an artifact…"
            rows={3}
            autoFocus
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                void start();
              }
            }}
          />
          <div className="home-prompt-foot">
            <Popover.Root open={crew.open} onOpenChange={crew.setOpen}>
              <Popover.Trigger asChild>
                <button
                  type="button"
                  className="crew-pill"
                  aria-label="Crew and build panes"
                >
                  <Bot
                    size={13}
                    className="crew-pill-icon"
                    aria-hidden="true"
                  />
                  <span className="crew-pill-label">Crew</span>
                  <ChevronDown
                    size={12}
                    className="crew-caret"
                    aria-hidden="true"
                  />
                </button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content
                  className="crew-popover"
                  side="top"
                  align="start"
                  sideOffset={8}
                  collisionPadding={16}
                >
                  <CrewPanel crew={crew} />
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
            <button
              type="submit"
              className="primary-button"
              disabled={!task.trim() || submitting}
            >
              {submitting ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <Play size={16} />
              )}
              <span>{submitting ? "Starting" : "Start work"}</span>
            </button>
          </div>
          {error && <div className="form-error">{error}</div>}
        </form>

        <p className="home-caption">
          Starts a real intake via the existing CLI <kbd>⌘ ↵</kbd>
          <span className="home-caption-note">
            · crew is staged, not yet applied to runs
          </span>
        </p>

        {recent.length > 0 && (
          <div className="home-recent">
            <div className="home-recent-head">Recent sessions</div>
            <div className="home-recent-list">
              {recent.map((sprint) => (
                <NavLink
                  key={sprint.sprint_id}
                  to={`/sessions/${encodeURIComponent(sprint.sprint_id)}`}
                  className="home-recent-row"
                >
                  <span className="home-recent-title">
                    {titleForSprint(sprint)}
                  </span>
                  <span
                    className={`home-recent-meta ${sprint.stall?.is_stalled ? "is-stalled" : ""}`}
                  >
                    {sprint.stall?.is_stalled
                      ? "Stalled"
                      : asString(
                          sprint.phase || sprint.status,
                          "unknown",
                        ).replace(/_/g, " ")}
                  </span>
                </NavLink>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function LoadingWorkbench() {
  return (
    <motion.div
      className="loading-workbench"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      {Array.from({ length: 4 }, (_, index) => (
        <div className="loading-panel" key={index} />
      ))}
    </motion.div>
  );
}

function ErrorWorkbench({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => Promise<void>;
}) {
  return (
    <div className="error-panel">
      <AlertTriangle size={20} />
      <div>
        <h2>Unable to load this view</h2>
        <p>{message}</p>
      </div>
      <button
        type="button"
        className="icon-text-button"
        onClick={() => void onRetry()}
      >
        <RefreshCw size={15} />
        <span>Retry</span>
      </button>
    </div>
  );
}

function EmptyInline({ label }: { label: string }) {
  return (
    <div className="empty-inline">
      <Search size={14} />
      <span>{label}</span>
    </div>
  );
}

function SectionHeader({
  icon,
  title,
  detail,
}: {
  icon: React.ReactNode;
  title: string;
  detail?: string;
}) {
  return (
    <div className="section-header">
      <div>
        {icon}
        <h2>{title}</h2>
      </div>
      {detail && <span>{detail}</span>}
    </div>
  );
}

export default App;
