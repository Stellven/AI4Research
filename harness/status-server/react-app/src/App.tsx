import * as Dialog from "@radix-ui/react-dialog";
import * as Popover from "@radix-ui/react-popover";
import * as Switch from "@radix-ui/react-switch";
import * as Tooltip from "@radix-ui/react-tooltip";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Bot,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Circle,
  Clock3,
  Code2,
  Download,
  FileCheck2,
  FileText,
  Loader2,
  MessageSquarePlus,
  Minus,
  PanelRight,
  PauseCircle,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SquareTerminal,
  Workflow,
  X,
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
  deliverableUrl,
  fetchDeliverables,
  fetchDeliverableText,
  fetchEvents,
  fetchProjection,
  submitEvalVerdict,
  submitHandoff,
  fetchSettings,
  fetchSprints,
  fetchStatus,
  fetchUsage,
  openEventStream,
  saveSettings,
  submitIntake,
  submitPlanVerdict,
} from "./api";
import {
  ROLE_META,
  ROLE_ORDER,
  asString,
  compactNumber,
  eventActor,
  eventTimestamp,
  formatDateTime,
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
  DagNode,
  Deliverable,
  EventRecord,
  HumanGate,
  ProjectionAction,
  ProjectionResponse,
  SettingsPayload,
  StallSummary,
  SprintSummary,
  StatusPayload,
  UsagePayload,
} from "./types";

type LoadState = "loading" | "ready" | "error";

type SessionData = {
  status?: StatusPayload;
  projection?: ProjectionResponse;
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
  "status" | "projection" | "events" | "usage" | "deliverables"
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
  artifacts?: Deliverable[];
};

type DesignVariant = "relay" | "dispatch" | "console";

// Original lotus mark — five petals fanning from a common base. Uses
// currentColor so it inherits the brand accent. Not a reproduction of any
// existing trademark; inspired by the fanned-petal flower silhouette.
function BrandMark({ size = 40 }: { size?: number }) {
  // An upright lotus bloom: petals fan up from a single base (12,21). Outer petals
  // recede in the darkest red, mid petals a step lighter, the front/center petals the
  // bright brand red — the three shades give the bloom its depth. No glow/gradient.
  const petal = "M0 0C-2.5 -5.5 -2.2 -12.5 0 -16.5C2.2 -12.5 2.5 -5.5 0 0Z";
  // Painted back-to-front so lighter front petals overlap the darker rear ones.
  const petals = [
    { a: -58, s: 0.8, cls: "lotus-back" },
    { a: 58, s: 0.8, cls: "lotus-back" },
    { a: -33, s: 0.9, cls: "lotus-mid" },
    { a: 33, s: 0.9, cls: "lotus-mid" },
    { a: -15, s: 0.99, cls: "lotus-front" },
    { a: 15, s: 0.99, cls: "lotus-front" },
    { a: 0, s: 1.08, cls: "lotus-front" },
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
      {petals.map(({ a, s, cls }, index) => (
        <path
          key={index}
          className={cls}
          d={petal}
          transform={`translate(12 21) rotate(${a}) scale(${s})`}
        />
      ))}
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
  const isSettingsRoute = location.pathname === "/settings";

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
    // Live updates: refresh the sprint list the moment any event lands (debounced
    // so a burst of events coalesces into one refresh). Fall back to a slow poll
    // when SSE is unavailable or the stream drops.
    let pending: number | undefined;
    const scheduleRefresh = () => {
      if (pending) return;
      pending = window.setTimeout(() => {
        pending = undefined;
        void refreshSprints();
      }, 600);
    };
    const stream = openEventStream(undefined, scheduleRefresh, () => {});
    const id = window.setInterval(
      () => void refreshSprints(),
      stream ? 20000 : 5000,
    );
    return () => {
      if (pending) window.clearTimeout(pending);
      stream?.close();
      window.clearInterval(id);
    };
  }, [refreshSprints]);

  const onCreated = useCallback(
    async (sprintId: string) => {
      await refreshSprints();
      navigate(`/sessions/${encodeURIComponent(sprintId)}`);
    },
    [navigate, refreshSprints],
  );

  return (
    <div className={`app-shell ${isSettingsRoute ? "settings-shell-route" : ""}`}>
      {!isSettingsRoute && (
        <Sidebar
          sprints={sprints}
          selectedSprintId={selectedSprintId}
          state={state}
          error={error}
          onCreated={onCreated}
        />
      )}
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
  const sprint = sprints.find((item) => item.sprint_id === decodedSprintId);

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
  const [projection, setProjection] = useState<ProjectionResponse>();
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
        projection: undefined,
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
      fetchProjection(sprintId, "fast").then((projectionResponse) => {
        if (!isCurrent()) return;
        setProjection(projectionResponse);
        cachePatch({ projection: projectionResponse });
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
    const [projectionResult, , eventsResult] = results;
    const coreFailed =
      projectionResult.status === "rejected" &&
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
      setProjection(cached.projection);
      setEvents(cached.events);
      setUsage(cached.usage);
      setDeliverables(cached.deliverables);
      setState("ready");
      setError("");
    } else {
      setStatus(undefined);
      setProjection(undefined);
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
    // Live updates for the open session: stream events and refresh on arrival
    // (debounced). The interval is a safety net; when SSE is live it runs rarely,
    // and if SSE is unavailable we degrade to the original poll cadence.
    let pending: number | undefined;
    const scheduleRefresh = () => {
      if (pending) return;
      pending = window.setTimeout(() => {
        pending = undefined;
        void refresh();
        void onSprintChanged();
      }, 500);
    };
    const stream = openEventStream(
      sprintId,
      () => {
        setStreamState("live");
        scheduleRefresh();
      },
      () => setStreamState("retrying"),
    );
    setStreamState(stream ? "live" : "off");
    const id = window.setInterval(
      () => {
        void refresh();
        void onSprintChanged();
      },
      stream ? 15000 : 3500,
    );
    return () => {
      if (pending) window.clearTimeout(pending);
      stream?.close();
      window.clearInterval(id);
    };
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
    projection,
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
  const projection = projectionForSprint(session.projection, sprintId);
  const projectionData = projection?.data;
  const currentSprint = (projectionData?.sprint ||
    sprint || { sprint_id: sprintId }) as SprintSummary;
  const stall = projectionStall(projection) || sprint?.stall;
  const humanActionType = asString(
    projectionData?.human_action_required &&
      typeof projectionData.human_action_required === "object"
      ? (projectionData.human_action_required as { type?: unknown }).type
      : "",
  );
  const phase = asString(
    projectionData?.phase || currentSprint.phase || currentSprint.status,
  );
  const isBlocked = isSystemBlocked(stall, humanActionType);
  const projectionEvents =
    projectionData?.events && projectionData.events.length > 0
      ? projectionData.events
      : session.events;
  const processSteps = useMemo(
    () =>
      buildProcessSteps(
        projection,
        projectionEvents,
        session.deliverables,
        phase,
        { showStallSummary: isBlocked, stall },
      ),
    [
      projection,
      projectionEvents,
      isBlocked,
      session.deliverables,
      phase,
      stall,
    ],
  );
  const rail = useDeliverablesRail();

  return (
    <div className="workspace-scroll">
      <TopBar
        sprint={currentSprint}
        streamState={session.streamState}
        rail={rail}
        deliverableCount={session.deliverables.length}
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
            <PlanFlow projection={projection} isBlocked={isBlocked} />
            <div
              className={`process-results-layout ${rail.open ? "rail-open" : "rail-collapsed"}`}
            >
              <ProcessStream
                steps={processSteps}
                onOpenArtifact={rail.openArtifact}
                decision={
                  <DecisionZone
                    projection={projection}
                    sprintId={sprintId}
                    onRefresh={session.refresh}
                  />
                }
              />
              <DeliverablesRail
                rail={rail}
                sprintId={sprintId}
                deliverables={session.deliverables}
                usage={session.usage}
              />
              {rail.open && (
                <button
                  type="button"
                  className="rail-scrim"
                  aria-label="Collapse deliverables"
                  onClick={() => rail.setOpen(false)}
                />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function projectionForSprint(
  projection: ProjectionResponse | undefined,
  sprintId: string,
): ProjectionResponse | undefined {
  if (!projection) return undefined;
  const focus = asString(
    projection.data?.sprint_id || projection.data?.sprint?.sprint_id,
  );
  if (focus && focus !== sprintId) return undefined;
  return projection;
}

function projectionStall(
  projection: ProjectionResponse | undefined,
): StallSummary | undefined {
  const stall = projection?.data?.dispatch?.stall;
  return stall && typeof stall === "object" ? stall : undefined;
}

function isSystemBlocked(
  stall: StallSummary | undefined,
  humanActionType: string,
): boolean {
  if (!stall?.is_stalled) return false;
  if (
    ["plan_review", "eval_review", "handoff_submit"].includes(humanActionType)
  ) {
    return false;
  }
  return true;
}

// The signature element: the multi-agent relay. Each variant expresses the
// same subject (who acted, and where the capability gate held the work)
function planNodeLabel(node: DagNode): string {
  const id = asString(node.node_id || node.id);
  const short = id.replace(/^build-/, "");
  return short || asString(node.title) || id;
}

// Group the plan's DAG nodes by dependency depth so parallel siblings share a stage —
// an honest flow (it shows the real branch/merge) rather than a fake straight line.
function buildPlanLevels(nodes: DagNode[]): DagNode[][] {
  const byId = new Map<string, DagNode>();
  nodes.forEach((node) => byId.set(asString(node.node_id || node.id), node));
  const cache = new Map<string, number>();
  function depth(id: string, seen: Set<string>): number {
    const cached = cache.get(id);
    if (cached !== undefined) return cached;
    if (seen.has(id)) return 0; // cycle guard
    seen.add(id);
    const deps = (byId.get(id)?.depends_on || []).filter((dep) =>
      byId.has(dep),
    );
    const value = deps.length
      ? 1 + Math.max(...deps.map((dep) => depth(dep, seen)))
      : 0;
    seen.delete(id);
    cache.set(id, value);
    return value;
  }
  const levels: DagNode[][] = [];
  nodes.forEach((node) => {
    const level = depth(asString(node.node_id || node.id), new Set());
    (levels[level] ||= []).push(node);
  });
  return levels.filter((stage) => stage && stage.length);
}

// The Planner's plan made legible: the DAG nodes as a left-to-right flow of stages.
function PlanFlow({
  projection,
  isBlocked,
}: {
  projection?: ProjectionResponse;
  isBlocked: boolean;
}) {
  const projectionNodes =
    projection?.data?.task_graph?.nodes || projection?.data?.nodes || [];
  const nodes = projectionNodes;
  const levels = useMemo(() => buildPlanLevels(nodes), [nodes]);
  if (!levels.length) return null;
  return (
    <section className="plan-flow" aria-label="Plan" data-testid="plan-flow">
      <div className="plan-flow-head">
        <span className="plan-flow-title">Plan</span>
        <span className="plan-flow-meta">
          {nodes.length} steps
          {isBlocked ? " · blocked at a capability gate" : ""}
        </span>
      </div>
      <ol className="plan-flow-track">
        {levels.map((stage, index) => (
          <li className="plan-stage" key={index}>
            <div className="plan-stage-nodes">
              {stage.map((node) => {
                const id = asString(node.node_id || node.id);
                const tone = statusTone(asString(node.status));
                return (
                  <span
                    className={`plan-node tone-${tone}`}
                    key={id}
                    title={asString(node.title) || id}
                  >
                    <span className="plan-node-dot" aria-hidden="true" />
                    <span className="plan-node-label">
                      {planNodeLabel(node)}
                    </span>
                  </span>
                );
              })}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

type GateSpec = {
  title: string;
  description: string;
  primary: { actionId: string; label: string; pending: string };
  secondary?: {
    actionId: string;
    label: string;
    confirm: string;
    pending: string;
    reasonPlaceholder: string;
  };
};

// Copy is deliberately honest: a verdict records + advances state. It does NOT
// itself guarantee a fresh agent pass, so we never say "starts a new planning pass".
const GATE_KINDS: Record<string, GateSpec> = {
  plan_review: {
    title: "Review the plan",
    description:
      "The planner produced a DAG. Approve it to start the build, or request changes with guidance for the planner.",
    primary: {
      actionId: "plan_approve",
      label: "Approve plan",
      pending: "Approving",
    },
    secondary: {
      actionId: "plan_reject",
      label: "Request changes",
      confirm: "Send guidance",
      pending: "Sending",
      reasonPlaceholder: "What should the planner change?",
    },
  },
  handoff_submit: {
    title: "Review the builder's output",
    description:
      "The builder finished its work. Approve it to send the result into evaluation.",
    primary: {
      actionId: "handoff_submit",
      label: "Approve",
      pending: "Approving",
    },
  },
  eval_review: {
    title: "Review the result",
    description:
      "The evaluator finished its review. Accept the result, or send it back to the builder with a reason.",
    primary: {
      actionId: "eval_pass",
      label: "Accept result",
      pending: "Accepting",
    },
    secondary: {
      actionId: "eval_fail",
      label: "Request fixes",
      confirm: "Send for fixes",
      pending: "Sending",
      reasonPlaceholder: "What needs to change before this passes?",
    },
  },
};

function shortArtifact(path: string): string {
  return asString(path).split("/").pop() || asString(path);
}

function prettyActionLabel(id: string): string {
  return id.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function artifactPath(ref?: string | { rel_path?: unknown }): string {
  if (typeof ref === "string") return ref;
  return asString(ref?.rel_path);
}

function projectionGateArtifacts(
  data: ProjectionResponse["data"],
  kind: string,
  primaryArtifact: string,
): string[] {
  const fromProjection =
    kind === "plan_review"
      ? [
          artifactPath(data.requirements?.prd),
          artifactPath(data.requirements?.contract),
          artifactPath(data.plan?.design),
          artifactPath(data.plan?.plan),
          artifactPath(data.plan?.task_graph),
        ]
      : kind === "eval_review"
        ? [
            artifactPath(data.evaluation?.handoff),
            artifactPath(data.evaluation?.eval),
            artifactPath(data.evaluation?.coverage_report),
            artifactPath(data.evaluation?.acceptance_verdict),
            artifactPath(data.requirements?.requirement_trace),
          ]
        : kind === "handoff_submit"
          ? [primaryArtifact, artifactPath(data.evaluation?.handoff)]
          : [primaryArtifact];
  return Array.from(new Set(fromProjection.filter(Boolean)));
}

// One attention surface above the stream: the operator's current decision (a human
// gate) when one is open, otherwise an honest system-pause when the run is stalled.
function DecisionZone({
  projection,
  sprintId,
  onRefresh,
}: {
  projection?: ProjectionResponse;
  sprintId: string;
  onRefresh: () => Promise<void>;
}) {
  const data = projection?.data;
  if (!data) return null;
  const actions = data.available_actions || [];
  // human_action_required.type is the backend's single "what does the human do now"
  // signal — and the only one that covers handoff (which has no human_gates entry).
  const action = data.human_action_required || {};
  const actionType = asString(action.type);
  const primaryArtifact = artifactPath(action.primary_artifact);
  if (GATE_KINDS[actionType]) {
    const gate = (data.human_gates || []).find(
      (item) => asString(item.kind) === actionType,
    );
    return (
      <GateCard
        kind={actionType}
        gate={gate}
        fallbackArtifacts={projectionGateArtifacts(
          data,
          actionType,
          primaryArtifact,
        )}
        actions={actions}
        sprintId={sprintId}
        onRefresh={onRefresh}
      />
    );
  }
  const stall = projectionStall(projection);
  const mismatch = data.capability_mismatch;
  if (
    actionType === "capability_mismatch" ||
    actionType === "stall_review" ||
    stall?.is_stalled ||
    mismatch?.present
  ) {
    return <SystemStall mismatch={mismatch} actions={actions} />;
  }
  return null;
}

function GateCard({
  kind,
  gate,
  fallbackArtifacts,
  actions,
  sprintId,
  onRefresh,
}: {
  kind: string;
  gate?: HumanGate;
  fallbackArtifacts?: string[];
  actions: ProjectionAction[];
  sprintId: string;
  onRefresh: () => Promise<void>;
}) {
  const spec = GATE_KINDS[kind];
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [submitting, setSubmitting] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  if (!spec) return null;
  const primaryAction = actions.find((a) => a.id === spec.primary.actionId);
  const secondaryAction = spec.secondary
    ? actions.find((a) => a.id === spec.secondary!.actionId)
    : undefined;
  const gateArtifacts = (gate?.source_artifacts || []).filter(Boolean);
  const artifacts = gateArtifacts.length
    ? gateArtifacts
    : fallbackArtifacts || [];
  const busy = Boolean(submitting);

  async function run(target: "primary" | "secondary") {
    const cleanReason = reason.trim();
    if (target === "secondary" && !cleanReason) {
      setError("Add guidance before sending it back.");
      reasonRef.current?.focus();
      return;
    }
    setSubmitting(
      target === "primary" ? spec!.primary.actionId : spec!.secondary!.actionId,
    );
    setError("");
    setNotice("");
    try {
      let response;
      if (kind === "plan_review") {
        response = await submitPlanVerdict(
          sprintId,
          target === "primary" ? "approve" : "reject",
          cleanReason,
        );
      } else if (kind === "eval_review") {
        response = await submitEvalVerdict(
          sprintId,
          target === "primary" ? "pass" : "fail",
          cleanReason,
        );
      } else {
        response = await submitHandoff(sprintId);
      }
      if (!response.ok) {
        throw new Error(
          response.error || response.stdout_tail || "Action did not complete",
        );
      }
      setReason("");
      setRejecting(false);
      setNotice(
        target === "primary"
          ? "Recorded — Solar is advancing."
          : "Sent back with your guidance.",
      );
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setSubmitting("");
    }
  }

  function onSecondaryClick() {
    if (!spec!.secondary) return;
    if (!rejecting) {
      setRejecting(true);
      setError("");
      window.setTimeout(() => reasonRef.current?.focus(), 0);
      return;
    }
    void run("secondary");
  }

  return (
    <section
      className="decision-card decision-gate"
      data-testid="human-gate"
      aria-label={spec.title}
    >
      <div className="decision-head">
        <span className="decision-kicker">Your decision</span>
        <h2 className="decision-title">{spec.title}</h2>
      </div>
      <p className="decision-desc">{spec.description}</p>
      {artifacts.length > 0 && (
        <div className="decision-artifacts">
          <FileText size={13} aria-hidden="true" />
          <span>Review {artifacts.map(shortArtifact).join(" · ")}</span>
        </div>
      )}
      {rejecting && spec.secondary && (
        <textarea
          ref={reasonRef}
          className="decision-reason"
          rows={2}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
            setError("");
          }}
          placeholder={spec.secondary.reasonPlaceholder}
        />
      )}
      <div className="decision-actions">
        {!rejecting && (
          <button
            type="button"
            className="primary-button"
            disabled={!primaryAction?.enabled || busy}
            onClick={() => void run("primary")}
          >
            {submitting === spec.primary.actionId ? (
              <Loader2 className="spin" size={15} />
            ) : (
              <CheckCircle2 size={15} />
            )}
            <span>
              {submitting === spec.primary.actionId
                ? spec.primary.pending
                : spec.primary.label}
            </span>
          </button>
        )}
        {spec.secondary && (
          <button
            type="button"
            className={rejecting ? "primary-button" : "ghost-button"}
            disabled={(!secondaryAction?.enabled && !rejecting) || busy}
            onClick={onSecondaryClick}
          >
            {submitting === spec.secondary.actionId && (
              <Loader2 className="spin" size={15} />
            )}
            <span>
              {submitting === spec.secondary.actionId
                ? spec.secondary.pending
                : rejecting
                  ? spec.secondary.confirm
                  : spec.secondary.label}
            </span>
          </button>
        )}
        {rejecting && (
          <button
            type="button"
            className="text-button"
            disabled={busy}
            onClick={() => {
              setRejecting(false);
              setReason("");
              setError("");
            }}
          >
            Cancel
          </button>
        )}
      </div>
      {error && <div className="form-error">{error}</div>}
      {notice && <div className="form-notice">{notice}</div>}
    </section>
  );
}

function SystemStall({
  mismatch,
  actions,
}: {
  mismatch?: {
    present?: boolean;
    missing_capability?: string;
    blocked_node?: string;
  };
  actions: ProjectionAction[];
}) {
  const missing = asString(mismatch?.missing_capability);
  const unsafe = actions.filter(
    (action) =>
      action.enabled === false &&
      /retry|skip|cancel|repair|steer/i.test(asString(action.id)),
  );
  return (
    <section
      className="decision-card decision-stall"
      data-testid="system-stall"
      aria-label="System paused"
    >
      <h2 className="stall-title">
        <PauseCircle size={16} aria-hidden="true" />
        System paused
      </h2>
      <p className="stall-resolve">
        Connect a worker that provides{" "}
        {missing ? <code>{missing}</code> : "the missing capability"} and the
        run continues.
      </p>
      {unsafe.length > 0 && (
        <ul className="stall-unsafe">
          {unsafe.map((action) => (
            <li key={asString(action.id)}>
              <span className="stall-unsafe-name">
                {asString(action.label) ||
                  prettyActionLabel(asString(action.id))}
              </span>
              <span className="stall-unsafe-reason">
                {asString(action.reason) || "not safe yet"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ProcessStream({
  steps,
  decision,
  onOpenArtifact,
}: {
  steps: ProcessStep[];
  decision?: React.ReactNode;
  onOpenArtifact: (path: string) => void;
}) {
  return (
    <section className="process-stream-panel" data-testid="process-stream">
      <div className="process-step-list">
        {steps.length === 0 && (
          <EmptyInline label="Waiting for agent process events" />
        )}
        {steps.map((step) => (
          <ProcessStepItem
            key={step.id}
            step={step}
            onOpenArtifact={onOpenArtifact}
          />
        ))}
        {decision}
      </div>
    </section>
  );
}

// A static activity-log entry — no click-to-expand cards. Detail is inline,
// the way Linear/Stripe activity feeds read.
function ProcessStepItem({
  step,
  onOpenArtifact,
}: {
  step: ProcessStep;
  onOpenArtifact: (path: string) => void;
}) {
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
        {step.summary && step.summary !== step.title && (
          <p className="process-step-text">{step.summary}</p>
        )}
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
        {step.artifacts && step.artifacts.length > 0 && (
          <div className="process-artifacts">
            {step.artifacts.map((item) => (
              <button
                key={item.rel_path}
                type="button"
                className="process-artifact-link"
                onClick={() => onOpenArtifact(item.rel_path)}
              >
                <FileText size={13} aria-hidden="true" />
                <span>{item.name}</span>
              </button>
            ))}
          </div>
        )}
        {step.result && (
          <button
            type="button"
            className="step-result-link"
            onClick={() => onOpenArtifact(step.result!.rel_path)}
          >
            <FileCheck2 size={15} />
            <span>Open {step.result.name}</span>
          </button>
        )}
      </div>
    </article>
  );
}

const RAIL_STORAGE_KEY = "ai4r.rail.open";

// Open by default on desktop, collapsed on narrow/mobile; honor any stored choice.
// Preview state never persists.
function useDeliverablesRail() {
  const [open, setOpenState] = useState<boolean>(() => {
    try {
      const stored = window.localStorage.getItem(RAIL_STORAGE_KEY);
      if (stored === "1") return true;
      if (stored === "0") return false;
      return window.innerWidth > 1240;
    } catch {
      return true;
    }
  });
  const [previewPath, setPreviewPath] = useState<string | null>(null);

  const setOpen = useCallback((next: boolean) => {
    setOpenState(next);
    try {
      window.localStorage.setItem(RAIL_STORAGE_KEY, next ? "1" : "0");
    } catch {
      // localStorage unavailable (private mode) — open state stays in memory only.
    }
    if (!next) setPreviewPath(null);
  }, []);

  const toggle = useCallback(() => setOpen(!open), [open, setOpen]);
  const openPreview = useCallback((path: string) => setPreviewPath(path), []);
  const closePreview = useCallback(() => setPreviewPath(null), []);
  // Open a deliverable from anywhere (e.g. a log entry) — ensure the rail is open.
  const openArtifact = useCallback(
    (path: string) => {
      setOpen(true);
      setPreviewPath(path);
    },
    [setOpen],
  );

  return {
    open,
    setOpen,
    toggle,
    previewPath,
    openPreview,
    closePreview,
    openArtifact,
  };
}

type RailController = ReturnType<typeof useDeliverablesRail>;

function DeliverablesRail({
  rail,
  sprintId,
  deliverables,
  usage,
}: {
  rail: RailController;
  sprintId: string;
  deliverables: Deliverable[];
  usage?: UsagePayload;
}) {
  const activeItem = rail.previewPath
    ? deliverables.find((item) => item.rel_path === rail.previewPath)
    : undefined;
  const inPreview = Boolean(activeItem);
  const asideRef = useRef<HTMLElement>(null);
  const returnFocusPath = useRef<string | null>(null);

  // Remove the collapsed rail from the tab order / a11y tree without killing the
  // width transition (visibility/display would).
  useEffect(() => {
    const node = asideRef.current as (HTMLElement & { inert?: boolean }) | null;
    if (node) node.inert = !rail.open;
  }, [rail.open]);

  function handleOpenPreview(path: string) {
    returnFocusPath.current = path;
    rail.openPreview(path);
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    if (inPreview) rail.closePreview();
    else rail.setOpen(false);
  }

  return (
    <aside
      ref={asideRef}
      className={`deliverables-rail ${rail.open ? "is-open" : "is-collapsed"} ${inPreview ? "is-preview" : ""}`}
      data-testid="results-rail"
      aria-label="Deliverables"
      onKeyDown={handleKeyDown}
    >
      {inPreview && activeItem ? (
        <DeliverablePreview
          item={activeItem}
          sprintId={sprintId}
          onBack={rail.closePreview}
          onClose={() => rail.setOpen(false)}
        />
      ) : (
        <RailList
          deliverables={deliverables}
          usage={usage}
          onOpen={handleOpenPreview}
          onClose={() => rail.setOpen(false)}
          focusPath={returnFocusPath.current}
        />
      )}
    </aside>
  );
}

function RailList({
  deliverables,
  usage,
  onOpen,
  onClose,
  focusPath,
}: {
  deliverables: Deliverable[];
  usage?: UsagePayload;
  onOpen: (path: string) => void;
  onClose: () => void;
  focusPath: string | null;
}) {
  const focusRowRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (focusPath && focusRowRef.current) focusRowRef.current.focus();
  }, [focusPath]);

  return (
    <div className="rail-list" data-testid="deliverables-panel">
      <div className="rail-head">
        <div className="rail-head-title">
          <span>Deliverables</span>
          <span className="rail-count">{deliverables.length}</span>
        </div>
        <button
          type="button"
          className="rail-close"
          onClick={onClose}
          aria-label="Collapse deliverables"
        >
          <X size={15} />
        </button>
      </div>
      {deliverables.length === 0 ? (
        <EmptyInline label="No deliverables yet" />
      ) : (
        <div className="artifact-list">
          {deliverables.map((item) => (
            <button
              type="button"
              key={item.rel_path}
              ref={focusPath === item.rel_path ? focusRowRef : undefined}
              className="artifact-row"
              onClick={() => onOpen(item.rel_path)}
            >
              <FileText className="artifact-icon" size={15} />
              <span className="artifact-name">{item.name}</span>
              <span className="artifact-meta">{item.kind.toUpperCase()}</span>
              <ChevronRight size={14} className="artifact-chevron" />
            </button>
          ))}
        </div>
      )}
      <div className="rail-divider" />
      <UsagePanel usage={usage} />
    </div>
  );
}

function formatDeliverableTime(mtime?: number): string {
  if (!mtime) return "";
  const date = new Date(mtime * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    md: "Markdown",
    markdown: "Markdown",
    json: "JSON",
    txt: "Text",
    log: "Log",
    html: "HTML",
    png: "Image",
    jpg: "Image",
    jpeg: "Image",
  };
  return map[kind.toLowerCase()] || kind.toUpperCase();
}

const IMAGE_KINDS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);

function isImageKind(kind: string): boolean {
  return IMAGE_KINDS.has(kind.toLowerCase());
}

function canRenderKind(kind: string): boolean {
  const k = kind.toLowerCase();
  return k === "md" || k === "markdown" || k === "json";
}

// Tonal (not color-coded) JSON highlight: keys, strings, numbers, and literals each get a
// class so weight/tone can differentiate them while staying in the monochrome palette.
function highlightJson(src: string): React.ReactNode[] {
  const re =
    /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+\.?\d*(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g;
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(src))) {
    if (match.index > last) nodes.push(src.slice(last, match.index));
    if (match[1]) {
      nodes.push(
        <span key={key++} className={match[2] ? "json-key" : "json-str"}>
          {match[1]}
        </span>,
      );
      if (match[2]) nodes.push(match[2]);
    } else if (match[3]) {
      nodes.push(
        <span key={key++} className="json-num">
          {match[3]}
        </span>,
      );
    } else if (match[4]) {
      nodes.push(
        <span key={key++} className="json-lit">
          {match[4]}
        </span>,
      );
    }
    last = match.index + match[0].length;
  }
  if (last < src.length) nodes.push(src.slice(last));
  return nodes;
}

function DeliverableRendered({
  item,
  text,
  raw,
}: {
  item: Deliverable;
  text: string;
  raw: boolean;
}) {
  if (raw) return <pre className="dv-raw">{text}</pre>;
  const kind = item.kind.toLowerCase();
  if (kind === "md" || kind === "markdown") {
    return (
      <div className="dv-md">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    );
  }
  if (kind === "json") {
    let pretty = text;
    try {
      pretty = JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      // Not valid JSON — fall back to the raw text rather than throwing.
    }
    return <pre className="dv-json">{highlightJson(pretty)}</pre>;
  }
  return <pre className="dv-raw">{text}</pre>;
}

function DeliverablePreview({
  item,
  sprintId,
  onBack,
  onClose,
}: {
  item: Deliverable;
  sprintId: string;
  onBack: () => void;
  onClose: () => void;
}) {
  const url = deliverableUrl(sprintId, item);
  const isImage = isImageKind(item.kind);
  const canToggleRaw = canRenderKind(item.kind);
  const [state, setState] = useState<LoadState>(isImage ? "ready" : "loading");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [raw, setRaw] = useState(false);
  const backRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(() => {
    if (isImage) {
      setState("ready");
      return;
    }
    setState("loading");
    setError("");
    fetchDeliverableText(url)
      .then(({ text: body }) => {
        setText(body);
        setState("ready");
      })
      .catch((err) => {
        setError(
          err instanceof Error ? err.message : "Couldn’t load this file",
        );
        setState("error");
      });
  }, [url, isImage]);

  useEffect(() => {
    load();
  }, [load]);

  // Move focus into the preview on open (back to the originating row is handled by RailList).
  useEffect(() => {
    backRef.current?.focus();
  }, []);

  return (
    <div className="dv-preview" data-testid="deliverable-preview">
      <div className="dv-preview-head">
        <button
          type="button"
          ref={backRef}
          className="dv-back"
          onClick={onBack}
        >
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Deliverables</span>
        </button>
        <div className="dv-preview-actions">
          {canToggleRaw && (
            <button
              type="button"
              className={`dv-action ${raw ? "is-active" : ""}`}
              aria-pressed={raw}
              aria-label="Toggle raw source"
              onClick={() => setRaw((value) => !value)}
            >
              <Code2 size={15} />
            </button>
          )}
          <a
            className="dv-action"
            href={url}
            download={item.name}
            aria-label="Download file"
          >
            <Download size={15} />
          </a>
          <a
            className="dv-action"
            href={url}
            target="_blank"
            rel="noreferrer"
            aria-label="Open in new tab"
          >
            <ArrowUpRight size={15} />
          </a>
          <button
            type="button"
            className="dv-action"
            onClick={onClose}
            aria-label="Collapse deliverables"
          >
            <X size={15} />
          </button>
        </div>
      </div>
      <div className="dv-preview-title">
        <span className="dv-preview-name">{item.name}</span>
        <span className="dv-badge">{item.kind.toUpperCase()}</span>
      </div>
      <div className="dv-preview-body" tabIndex={0}>
        {state === "loading" && (
          <div className="dv-status">
            <Loader2 className="spin" size={16} />
            <span>Loading…</span>
          </div>
        )}
        {state === "error" && (
          <div className="dv-status dv-status-error">
            <AlertTriangle size={16} />
            <p>{error}</p>
            <button type="button" className="icon-text-button" onClick={load}>
              <RefreshCw size={14} />
              <span>Retry</span>
            </button>
          </div>
        )}
        {state === "ready" &&
          (isImage ? (
            <div className="dv-image-wrap">
              <img className="dv-image" src={url} alt={item.name} />
            </div>
          ) : (
            <DeliverableRendered item={item} text={text} raw={raw} />
          ))}
      </div>
      <div className="dv-preview-foot">
        {kindLabel(item.kind)}
        {item.mtime ? ` · updated ${formatDeliverableTime(item.mtime)}` : ""}
      </div>
    </div>
  );
}

const ARTIFACT_ROLE_KEYWORDS: Record<string, string[]> = {
  pm: ["prd", "spec", "intake", "scope"],
  planner: ["plan", "design", "task_graph", "task-graph", "dag", "closure"],
  builder: ["handoff", "build", "impl"],
  evaluator: ["eval", "verdict", "review", "acceptance"],
};

// The classifying token of a deliverable — its directory (e.g. "prd/foo.md" -> "prd")
// or the segment before the extension (e.g. "<sid>.design.md" -> "design"). Avoids
// matching the sprint id, which can itself contain words like "plan".
function artifactKindToken(item: Deliverable): string {
  const path = asString(item.rel_path || item.name).toLowerCase();
  const base = path.split("/").pop() || path;
  const dotParts = base.split(".");
  // "<sid>.<kind>.<ext>" -> the kind segment (ignores the sprint id, which can
  // itself contain words like "plan").
  if (dotParts.length >= 3) return dotParts[dotParts.length - 2];
  // Directory-based ("prd/foo.md") -> the directory names the kind.
  const dir = path.includes("/") ? path.split("/")[0] : "";
  if (dir && !["sprints", "sessions", "state", "config"].includes(dir)) {
    return dir;
  }
  return dotParts.length >= 2 ? dotParts[dotParts.length - 2] : base;
}

// Attach each deliverable to the most recent log step of its producing role, so the
// entry that produced a plan/handoff/eval file links straight to the rail preview.
function attachArtifactsToSteps(
  steps: ProcessStep[],
  deliverables: Deliverable[],
): void {
  deliverables.forEach((item) => {
    const token = artifactKindToken(item);
    const role = Object.keys(ARTIFACT_ROLE_KEYWORDS).find((key) =>
      ARTIFACT_ROLE_KEYWORDS[key].some(
        (keyword) => token.includes(keyword) || keyword.includes(token),
      ),
    );
    if (!role) return;
    let target: ProcessStep | undefined;
    for (const step of steps) {
      if (normalizeRole(step.actor) === role) target = step;
    }
    if (target) (target.artifacts ||= []).push(item);
  });
}

function buildProcessSteps(
  projection: ProjectionResponse | undefined,
  events: EventRecord[],
  deliverables: Deliverable[],
  phase: string,
  options: { showStallSummary?: boolean; stall?: StallSummary } = {},
): ProcessStep[] {
  const steps: ProcessStep[] = [];
  const orderedEvents = [...events].sort(
    (a, b) => eventTimeValue(a) - eventTimeValue(b),
  );

  orderedEvents.forEach((event, index) => {
    steps.push(processStepFromEvent(event, index === orderedEvents.length - 1));
  });

  const nodes =
    projection?.data?.task_graph?.nodes || projection?.data?.nodes || [];
  if (steps.length === 0 && nodes.length > 0) {
    nodes.forEach((node, index) => {
      steps.push(processStepFromNode(node, index === nodes.length - 1, phase));
    });
  }

  const stall =
    options.showStallSummary === false
      ? undefined
      : options.stall || projection?.data?.dispatch?.stall;
  if (stall?.is_stalled && !steps.some((step) => step.state === "blocked")) {
    steps.push({
      id: "stall-summary",
      actor: "Harness",
      title: "Dispatch is blocked",
      summary: stallCopy(stall),
      detail:
        stallCopy(stall) ||
        "The sprint is waiting on a dispatch gate or missing worker capability.",
      timestamp: projection?.generated_at || "",
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
        : projection?.generated_at || "",
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
  attachArtifactsToSteps(sorted, deliverables);
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

// Infer which agent a DAG node belongs to (node-based steps have no event actor),
// so node logs attach the right artifacts (build->Builder, review->Evaluator, ...).
function nodeActor(node: { [key: string]: unknown }): string {
  const caps = (
    Array.isArray(node.required_capabilities) ? node.required_capabilities : []
  )
    .map((cap) => asString(cap).toLowerCase())
    .join(" ");
  const text = `${asString(nodeId(node)).toLowerCase()} ${caps}`;
  if (/eval|review|verdict|gate|accept/.test(text)) return "Evaluator";
  if (/build|impl|code|frontend|backend|server|handoff/.test(text))
    return "Builder";
  if (/plan|design|dag|rout/.test(text)) return "Planner";
  if (/spec|prd|intake|scope|product/.test(text)) return "PM";
  return "Planner";
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
    actor: nodeActor(node),
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
  rail,
  deliverableCount,
}: {
  sprint: SprintSummary;
  streamState: string;
  rail: RailController;
  deliverableCount: number;
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
        <button
          type="button"
          className={`rail-toggle ${rail.open ? "is-open" : ""}`}
          aria-label="Deliverables"
          aria-expanded={rail.open}
          onClick={rail.toggle}
        >
          <PanelRight size={16} aria-hidden="true" />
          {deliverableCount > 0 && (
            <span className="rail-toggle-count">{deliverableCount}</span>
          )}
        </button>
      </div>
    </header>
  );
}

function UsagePanel({ usage }: { usage?: UsagePayload }) {
  const total = usage?.total_used_tokens_label || "0 tok";
  const models = usage?.models || [];
  return (
    <section className="panel usage-panel" data-testid="usage-panel">
      <div className="usage-head">
        <span>Usage</span>
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
        Per model, per day (account-wide) — runtime does not report per-sprint
        tokens.
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

// Activity heatmap (recovered from the Jun-18 build): bucket sprints into the last
// N calendar days for a git-contribution-style usage graph.
type ActivityDay = { date: string; count: number; sprints: SprintSummary[] };

function buildActivityDays(
  sprints: SprintSummary[],
  dayCount: number,
): ActivityDay[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const buckets = new Map<string, ActivityDay>();
  Array.from({ length: dayCount }, (_unused, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (dayCount - index - 1));
    const key = date.toISOString().slice(0, 10);
    buckets.set(key, { date: key, count: 0, sprints: [] });
  });
  sprints.forEach((sprint) => {
    // /sprints exposes mtime (unix seconds); fall back to updated_at if present.
    const mtime = sprint.mtime;
    const ts =
      typeof mtime === "number"
        ? mtime * 1000
        : Date.parse(asString(sprint.updated_at) || "");
    if (!ts) return;
    const key = new Date(ts).toISOString().slice(0, 10);
    const bucket = buckets.get(key);
    if (!bucket) return;
    bucket.sprints.push(sprint);
    bucket.count += 1;
  });
  return Array.from(buckets.values());
}

function activityLevel(count: number): number {
  if (count <= 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  if (count <= 6) return 3;
  return 4;
}

type SettingsSectionId =
  | "credentials"
  | "crew"
  | "usage"
  | "activity"
  | "about";
const SETTINGS_SECTIONS: Array<{ id: SettingsSectionId; label: string }> = [
  { id: "credentials", label: "Credentials" },
  { id: "crew", label: "Default crew" },
  { id: "usage", label: "Usage & limits" },
  { id: "activity", label: "Activity" },
  { id: "about", label: "About" },
];

function SettingsLotusMark() {
  return (
    <svg
      className="settings-lotus-mark"
      viewBox="0 0 48 48"
      role="img"
      aria-label="AI4Research lotus"
    >
      <defs>
        <linearGradient id="settings-lotus-front" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#ff4d65" />
          <stop offset="48%" stopColor="#cf0a2c" />
          <stop offset="100%" stopColor="#8f061d" />
        </linearGradient>
        <linearGradient id="settings-lotus-mid" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#e8324c" />
          <stop offset="100%" stopColor="#8f061d" />
        </linearGradient>
        <linearGradient id="settings-lotus-back" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#b80a27" />
          <stop offset="100%" stopColor="#5e0615" />
        </linearGradient>
        <radialGradient id="settings-lotus-glow" cx="50%" cy="54%" r="44%">
          <stop offset="0%" stopColor="rgba(207,10,44,0.34)" />
          <stop offset="100%" stopColor="rgba(207,10,44,0)" />
        </radialGradient>
      </defs>
      <circle cx="24" cy="26" r="18" fill="url(#settings-lotus-glow)" />
      <path
        d="M24 39C16.8 34.2 12.5 27.4 11.8 18.6C18.8 20.4 23.1 25.6 24 39Z"
        fill="url(#settings-lotus-back)"
      />
      <path
        d="M24 39C31.2 34.2 35.5 27.4 36.2 18.6C29.2 20.4 24.9 25.6 24 39Z"
        fill="url(#settings-lotus-back)"
      />
      <path
        d="M23.8 39C17.8 31.8 16.4 23.5 20.1 14.2C25.7 20.6 27.1 28.8 23.8 39Z"
        fill="url(#settings-lotus-mid)"
      />
      <path
        d="M24.2 39C30.2 31.8 31.6 23.5 27.9 14.2C22.3 20.6 20.9 28.8 24.2 39Z"
        fill="url(#settings-lotus-mid)"
      />
      <path
        d="M24 39C19.6 30.7 19.6 21.7 24 9C28.4 21.7 28.4 30.7 24 39Z"
        fill="url(#settings-lotus-front)"
      />
      <path
        d="M12 36.2C17.5 38.6 21.5 39.2 24 38.9C20.4 34.7 15.7 32.9 9.9 33.5C10.2 34.6 10.9 35.5 12 36.2Z"
        fill="#7a0a1d"
      />
      <path
        d="M36 36.2C30.5 38.6 26.5 39.2 24 38.9C27.6 34.7 32.3 32.9 38.1 33.5C37.8 34.6 37.1 35.5 36 36.2Z"
        fill="#7a0a1d"
      />
    </svg>
  );
}

function SettingsView() {
  const [settings, setSettings] = useState<SettingsPayload>();
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");

  const [roleModels, setRoleModels] = useState<Record<string, string>>({});
  const [agentOn, setAgentOn] = useState<Record<string, boolean>>({});
  const [labMode, setLabMode] = useState("all-claude");
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [usage, setUsage] = useState<UsagePayload>();
  const [sprints, setSprints] = useState<SprintSummary[]>([]);
  const [activeSection, setActiveSection] =
    useState<SettingsSectionId>("credentials");

  const refresh = useCallback(async () => {
    try {
      const response = await fetchSettings();
      setSettings(response);
      void fetchUsage()
        .then(setUsage)
        .catch(() => undefined);
      void fetchSprints()
        .then((res) => setSprints(res.data?.sprints || []))
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

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const save = useCallback(async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      const res = await saveSettings(roleModels, apiKeys);
      if (res.ok) {
        const n = res.written_keys?.length || 0;
        setSaveMsg(
          `Saved. Models applied${n ? `, ${n} key(s) stored` : ""}. Restart the cockpit to apply to running panes.`,
        );
        setApiKeys({}); // clear key inputs after persisting
        void refresh();
      } else {
        setSaveMsg(res.error || "Save failed");
      }
    } catch (err) {
      setSaveMsg(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [roleModels, apiKeys, refresh]);
  const section = SETTINGS_SECTIONS.find((item) => item.id === activeSection);

  return (
    <div className="workspace-scroll">
      <div className="settings-layout" data-testid="settings-view">
        {state === "loading" && <LoadingWorkbench />}
        {state === "error" && (
          <ErrorWorkbench message={error} onRetry={refresh} />
        )}
        {state === "ready" && (
          <div className="settings-shell">
            <aside className="settings-sidebar">
              <NavLink className="settings-back" to="/">
                <ArrowLeft size={14} />
                <span>Back to app</span>
              </NavLink>
              <div className="settings-sidebar-head">
                <SettingsLotusMark />
                <div>
                  <h1>AI4Research</h1>
                  <span>Settings</span>
                </div>
              </div>
              <nav className="settings-nav" aria-label="Settings sections">
                {SETTINGS_SECTIONS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`settings-nav-item ${activeSection === item.id ? "is-active" : ""}`}
                    aria-current={
                      activeSection === item.id ? "page" : undefined
                    }
                    onClick={() => setActiveSection(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </nav>
            </aside>
            <main className="settings-content">
              <div className="settings-content-head">
                <div>
                  <h2>{section?.label || "Settings"}</h2>
                </div>
                <button
                  type="button"
                  className="icon-text-button"
                  onClick={() => void refresh()}
                >
                  <RefreshCw size={15} />
                  <span>Reload</span>
                </button>
              </div>

              <SettingsNotice settings={settings} />
              {activeSection === "credentials" && (
                <CredentialsPane apiKeys={apiKeys} setApiKeys={setApiKeys} />
              )}
              {activeSection === "crew" && (
                <DefaultCrewPane
                  agentOn={agentOn}
                  applyLabMode={applyLabMode}
                  labMode={labMode}
                  onAgentChange={(role, value) =>
                    setAgentOn((prev) => ({ ...prev, [role]: value }))
                  }
                  onRoleModelChange={(role, value) => {
                    setRoleModels((prev) => ({ ...prev, [role]: value }));
                    setLabMode("custom");
                  }}
                  roleModels={roleModels}
                />
              )}
              {activeSection === "usage" && <UsageLimitsPane usage={usage} />}
              {activeSection === "activity" && <ActivityPane sprints={sprints} />}
              {activeSection === "about" && (
                <AboutPane settings={settings} usage={usage} />
              )}

              <div
                className="settings-actions"
                hidden={
                  activeSection !== "crew" && activeSection !== "credentials"
                }
              >
                <span className="settings-actions-note">
                  {saveMsg ||
                    "Writes models to the runtime config and API keys to local secrets. Restart the cockpit to apply to running panes."}
                </span>
                <button
                  type="button"
                  className="primary-button"
                  disabled={saving}
                  onClick={() => void save()}
                  title="Persist model selection + API keys to the local runtime"
                >
                  <span>{saving ? "Saving…" : "Save configuration"}</span>
                </button>
              </div>
            </main>
          </div>
        )}
      </div>
    </div>
  );
}

function SettingsNotice({ settings }: { settings?: SettingsPayload }) {
  return (
    <div className="settings-notice">
      <ShieldCheck size={15} aria-hidden="true" />
      <p>
        Read from the runtime ({settings?.source || "status-server"}). Save
        writes model/crew selection to the runtime config and API keys to local
        secrets; restart the cockpit to apply to running panes.
      </p>
    </div>
  );
}

function CredentialsPane({
  apiKeys,
  setApiKeys,
}: {
  apiKeys: Record<string, string>;
  setApiKeys: (next: (prev: Record<string, string>) => Record<string, string>) => void;
}) {
  return (
    <SettingsSection
      title="Credentials"
      detail="local secrets"
      description="Provider keys are stored only on this machine. Blank fields keep any existing key."
    >
      <div className="settings-row-list">
        {API_PROVIDERS.map((provider) => (
          <div className="settings-data-row credential-row" key={provider.id}>
            <div className="settings-row-main">
              <strong>{provider.label}</strong>
              <span>{provider.hint}</span>
            </div>
            <input
              type="password"
              className="key-input"
              placeholder="Leave blank to keep existing"
              autoComplete="off"
              value={apiKeys[provider.id] || ""}
              onChange={(event) =>
                setApiKeys((prev) => ({
                  ...prev,
                  [provider.id]: event.target.value,
                }))
              }
            />
            <span className="settings-status-pill">local</span>
          </div>
        ))}
      </div>
    </SettingsSection>
  );
}

function DefaultCrewPane({
  agentOn,
  applyLabMode,
  labMode,
  onAgentChange,
  onRoleModelChange,
  roleModels,
}: {
  agentOn: Record<string, boolean>;
  applyLabMode: (mode: string) => void;
  labMode: string;
  onAgentChange: (role: string, value: boolean) => void;
  onRoleModelChange: (role: string, value: string) => void;
  roleModels: Record<string, string>;
}) {
  return (
    <SettingsSection
      title="Default crew"
      detail={labMode}
      description="Default role models used by new runtime panes. Save persists these values to the local runtime config."
    >
      <div
        className="segmented settings-segmented"
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
      <div className="agent-config-list settings-agent-list">
        {ROLE_ORDER.map((role) => (
          <div
            className={`agent-config-row settings-agent-row ${agentOn[role] ? "" : "is-off"}`}
            key={role}
          >
            <Switch.Root
              className="switch-root"
              checked={Boolean(agentOn[role])}
              onCheckedChange={(value) => onAgentChange(role, value)}
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
                onChange={(event) => onRoleModelChange(role, event.target.value)}
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
    </SettingsSection>
  );
}

function UsageLimitsPane({ usage }: { usage?: UsagePayload }) {
  const models = usage?.models || [];
  return (
    <SettingsSection
      title="Usage & limits"
      detail={usage?.total_used_tokens_label || "unavailable"}
      description="Account-wide model-day token usage from the runtime quota scan. Per-run numbers stay on the session view."
    >
      {!usage && (
        <SettingsEmptyState
          title="Usage unavailable"
          detail="The /usage endpoint did not return model-day token rows."
        />
      )}
      <div className="settings-metric-grid">
        <MetricBox
          label="Today"
          value={usage?.total_used_tokens_label || "-"}
          detail={usage?.scope || "model-day estimate"}
        />
        <MetricBox label="Source" value={usage?.source || "not exposed"} />
      </div>
      <div className="usage-models settings-usage-models">
        {models.length === 0 && <EmptyInline label="No usage signal available" />}
        {models.map((model) => (
          <div
            className="usage-model"
            key={`${model.model_key}-${model.date ?? ""}`}
          >
            <span>{model.model_key}</span>
            <strong>{model.used_tokens_label}</strong>
          </div>
        ))}
      </div>
    </SettingsSection>
  );
}

function ActivityPane({ sprints }: { sprints: SprintSummary[] }) {
  const days = useMemo(() => buildActivityDays(sprints, 84), [sprints]);
  const [selectedDay, setSelectedDay] = useState(
    days[days.length - 1]?.date || "",
  );
  useEffect(() => {
    if (!selectedDay && days.length > 0) {
      setSelectedDay(days[days.length - 1].date);
    }
  }, [days, selectedDay]);
  const selected = days.find((day) => day.date === selectedDay);
  const selectedSprints = selected?.sprints || [];
  const sevenDayTotal = days.slice(-7).reduce((sum, day) => sum + day.count, 0);
  const active = sprints.filter((sprint) => sessionTone(sprint) === "working").length;
  const attention = sprints.filter((sprint) => sessionTone(sprint) === "blocked").length;
  const done = sprints.filter((sprint) => sessionTone(sprint) === "complete").length;
  const busiest = days.reduce(
    (best, day) => (day.count > best.count ? day : best),
    days[0] || { date: "", count: 0, sprints: [] },
  );

  return (
    <SettingsSection
      title="Activity"
      detail={`${sevenDayTotal} this week`}
      description="A read-only activity history from the real sprint index. Select a day to inspect sessions created or updated then."
    >
      {sprints.length === 0 && (
        <SettingsEmptyState
          title="No activity recorded"
          detail="The status-server did not return any sessions for the current harness."
        />
      )}
      <div className="activity-metrics" aria-label="Activity metrics">
        <MetricBox label="Sessions" value={String(sprints.length)} />
        <MetricBox label="Working" value={String(active)} />
        <MetricBox label="Needs you" value={String(attention)} />
        <MetricBox label="Done" value={String(done)} />
      </div>
      <div className="activity-heatmap" aria-label="Sprint activity by day">
        {days.map((day) => (
          <button
            key={day.date}
            type="button"
            className={`activity-day activity-level-${activityLevel(day.count)} ${selectedDay === day.date ? "is-selected" : ""}`}
            aria-label={`${day.date}: ${day.count} sessions`}
            title={`${day.date}: ${day.count} sessions`}
            aria-pressed={selectedDay === day.date}
            onClick={() => setSelectedDay(day.date)}
          />
        ))}
      </div>
      <div className="activity-summary-line">
        <span>
          Busiest day:{" "}
          <strong>
            {busiest.date ? `${busiest.date} (${busiest.count})` : "not available"}
          </strong>
        </span>
        <span>
          Selected:{" "}
          <strong>
            {selected ? `${selected.date} (${selected.count})` : "not available"}
          </strong>
        </span>
      </div>
      <div className="settings-row-list activity-session-list">
        {selectedSprints.length === 0 && (
          <div className="activity-empty-row">No sessions on the selected day.</div>
        )}
        {selectedSprints.slice(0, 10).map((sprint) => (
          <NavLink
            key={sprint.sprint_id}
            className="activity-session-row"
            to={`/sessions/${encodeURIComponent(sprint.sprint_id)}`}
          >
            <span className={`state-dot state-${sessionTone(sprint)}`} />
            <div>
              <strong>{titleForSprint(sprint)}</strong>
              <span>{sprint.sprint_id}</span>
            </div>
            <em>
              {formatDateTime(
                asString(sprint.updated_at) ||
                  asString(sprint.latest_event?.ts) ||
                  (typeof sprint.mtime === "number"
                    ? new Date(sprint.mtime * 1000).toISOString()
                    : ""),
              )}
            </em>
          </NavLink>
        ))}
      </div>
    </SettingsSection>
  );
}

function AboutPane({
  settings,
  usage,
}: {
  settings?: SettingsPayload;
  usage?: UsagePayload;
}) {
  return (
    <SettingsSection
      title="About"
      detail="runtime metadata"
      description="Only values exposed by the local status-server are shown."
    >
      <div className="settings-facts">
        <FactRow label="Settings source" value={settings?.source || "not exposed"} />
        <FactRow label="Settings generated" value={settings?.generated_at || "not exposed"} />
        <FactRow
          label="Settings writes"
          value={settings?.write_supported ? "supported" : "supported locally"}
        />
        <FactRow label="Usage source" value={usage?.source || "not exposed"} />
        <FactRow label="Usage scope" value={usage?.scope || "not exposed"} />
        <FactRow
          label="Lab matrix"
          value={asString(settings?.model_lab_matrix?.value) || "not exposed"}
        />
      </div>
    </SettingsSection>
  );
}

function SettingsSection({
  title,
  detail,
  description,
  children,
}: {
  title: string;
  detail?: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="settings-section" aria-label={title}>
      <div className="settings-section-intro">
        <p className="settings-help">{description}</p>
        {detail && <span>{detail}</span>}
      </div>
      {children}
    </section>
  );
}

function SettingsEmptyState({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="settings-empty-state">
      <Circle size={14} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
    </div>
  );
}

function MetricBox({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="settings-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <em>{detail}</em>}
    </div>
  );
}

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="settings-fact-row">
      <span>{label}</span>
      <strong>{value}</strong>
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

  function setRoleModel(role: string, value: string) {
    setRoleModels((prev) => ({ ...prev, [role]: value }));
  }

  return {
    open,
    setOpen,
    roleModels,
    setRoleModel,
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
      <div className="crew-agent-list">
        {ROLE_ORDER.map((role) => (
          <div className="crew-agent-row" key={role}>
            <strong className="crew-agent-name">
              {ROLE_META[role].title.split(" ")[0]}
            </strong>
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
