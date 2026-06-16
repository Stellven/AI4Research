import * as Dialog from "@radix-ui/react-dialog";
import * as Switch from "@radix-ui/react-switch";
import * as Tooltip from "@radix-ui/react-tooltip";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  Circle,
  Clock3,
  Command,
  FileText,
  GitBranch,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  Play,
  Radio,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  Zap
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
  useParams
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
  submitIntake
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
  titleForSprint
} from "./format";
import type {
  DashboardResponse,
  Deliverable,
  EventRecord,
  SettingsPayload,
  SprintSummary,
  StatusPayload,
  UsagePayload
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

  useEffect(() => {
    if (location.pathname === "/" && sprints.length > 0) {
      navigate(`/sessions/${encodeURIComponent(sprints[0].sprint_id)}`, { replace: true });
    }
  }, [location.pathname, navigate, sprints]);

  const onCreated = useCallback(
    async (sprintId: string) => {
      await refreshSprints();
      navigate(`/sessions/${encodeURIComponent(sprintId)}`);
    },
    [navigate, refreshSprints]
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
      <main className="main-workspace" aria-label="Solar Harness session workspace">
        <Routes>
          <Route
            path="/"
            element={sprints.length ? <Navigate to={`/sessions/${encodeURIComponent(sprints[0].sprint_id)}`} replace /> : <EmptyState onCreated={onCreated} />}
          />
          <Route path="/sessions/:sprintId" element={<SessionRoute sprints={sprints} onCreated={onCreated} onSprintChanged={refreshSprints} />} />
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

function Sidebar({
  sprints,
  selectedSprintId,
  state,
  error,
  onCreated
}: {
  sprints: SprintSummary[];
  selectedSprintId: string;
  state: LoadState;
  error: string;
  onCreated: (sprintId: string) => Promise<void>;
}) {
  return (
    <aside className="sidebar">
      <div className="brand-row">
        <div className="brand-mark" aria-hidden="true">
          <Command size={18} />
        </div>
        <div>
          <div className="brand-name">Solar Harness</div>
          <div className="brand-subtitle">Agent runtime</div>
        </div>
      </div>

      <NewTaskDialog onCreated={onCreated} buttonClassName="new-task-button" />

      <div className="sidebar-section">
        <div className="sidebar-heading">
          <span>Sessions</span>
          <span>{sprints.length}</span>
        </div>
        <div className="session-list" data-testid="session-list">
          {state === "loading" && <SidebarSkeleton />}
          {state === "error" && <div className="sidebar-error">{error}</div>}
          {state === "ready" && sprints.length === 0 && <div className="sidebar-empty">No sessions yet</div>}
          {sprints.map((sprint) => (
            <NavLink
              key={sprint.sprint_id}
              to={`/sessions/${encodeURIComponent(sprint.sprint_id)}`}
              className={({ isActive }) => `session-link ${isActive || selectedSprintId === sprint.sprint_id ? "is-active" : ""}`}
            >
              <span className={`session-dot tone-${sessionTone(sprint)}`} />
              <span className="session-copy">
                <span className="session-title">{titleForSprint(sprint)}</span>
                <span className="session-meta">
                  {asString(sprint.phase || sprint.status, "unknown").replace(/_/g, " ")}
                </span>
              </span>
            </NavLink>
          ))}
        </div>
      </div>

      <div className="sidebar-footer">
        <NavLink to="/settings" className={({ isActive }) => `settings-link ${isActive ? "is-active" : ""}`}>
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

function sessionTone(sprint: SprintSummary): "idle" | "working" | "blocked" | "complete" {
  if (sprint.stall?.is_stalled) return "blocked";
  return statusTone(asString(sprint.status || sprint.phase));
}

function NewTaskDialog({
  onCreated,
  buttonClassName,
  compact = false
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
        throw new Error(response.error || response.stdout_tail || "Intake did not return a sprint id");
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
          <Dialog.Title className="dialog-title">Describe what you want done</Dialog.Title>
          <Dialog.Description className="dialog-description">
            This starts a real Solar Harness intake via the existing CLI.
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
                <button type="button" className="ghost-button" disabled={submitting}>
                  Cancel
                </button>
              </Dialog.Close>
              <button type="submit" className="primary-button" disabled={!task.trim() || submitting}>
                {submitting ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
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
  onSprintChanged
}: {
  sprints: SprintSummary[];
  onCreated: (sprintId: string) => Promise<void>;
  onSprintChanged: () => Promise<void>;
}) {
  const { sprintId = "" } = useParams();
  const decodedSprintId = decodeURIComponent(sprintId);
  const session = useSessionData(decodedSprintId, onSprintChanged);
  const sprint = sprints.find((item) => item.sprint_id === decodedSprintId) || session.dashboard?.data?.sprint;

  if (!decodedSprintId) {
    return <EmptyState onCreated={onCreated} />;
  }

  return <SessionView sprint={sprint as SprintSummary | undefined} sprintId={decodedSprintId} session={session} onCreated={onCreated} />;
}

function useSessionData(sprintId: string, onSprintChanged: () => Promise<void>): SessionData {
  const [status, setStatus] = useState<StatusPayload>();
  const [dashboard, setDashboard] = useState<DashboardResponse>();
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [usage, setUsage] = useState<UsagePayload>();
  const [deliverables, setDeliverables] = useState<Deliverable[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const [streamState, setStreamState] = useState<"connecting" | "live" | "retrying" | "off">("connecting");
  const selectedSprintRef = useRef(sprintId);

  useEffect(() => {
    selectedSprintRef.current = sprintId;
  }, [sprintId]);

  const refresh = useCallback(async () => {
    if (!sprintId) return;
    try {
      const [statusResponse, dashboardResponse, eventsResponse, usageResponse, deliverablesResponse] = await Promise.all([
        fetchStatus(sprintId),
        fetchDashboard(sprintId),
        fetchEvents(sprintId, 140),
        fetchUsage(),
        fetchDeliverables(sprintId)
      ]);
      if (selectedSprintRef.current !== sprintId) {
        return;
      }
      setStatus(statusResponse);
      setDashboard(dashboardResponse);
      const scopedEvents = eventsResponse.filter((event) => !event.sprint_id || event.sprint_id === sprintId);
      setEvents((existing) => mergeEvents(existing.filter((event) => !event.sprint_id || event.sprint_id === sprintId), scopedEvents));
      setUsage(usageResponse);
      setDeliverables(deliverablesResponse.items || []);
      setState("ready");
      setError("");
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Unable to load session");
    }
  }, [sprintId]);

  useEffect(() => {
    setState("loading");
    setStatus(undefined);
    setDashboard(undefined);
    setUsage(undefined);
    setDeliverables([]);
    setEvents([]);
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
        setEvents((existing) => mergeEvents(existing, [event]));
      },
      () => setStreamState("retrying")
    );
    if (!source) {
      setStreamState("off");
      return undefined;
    }
    source.onopen = () => setStreamState("live");
    return () => source.close();
  }, [sprintId]);

  return { status, dashboard, events, usage, deliverables, state, error, streamState, refresh };
}

function SessionView({
  sprint,
  sprintId,
  session,
  onCreated
}: {
  sprint?: SprintSummary;
  sprintId: string;
  session: SessionData;
  onCreated: (sprintId: string) => Promise<void>;
}) {
  const dashboard = dashboardForSprint(session.dashboard, sprintId);
  const data = dashboard?.data;
  const currentSprint = (data?.sprint || sprint || { sprint_id: sprintId }) as SprintSummary;
  const stall = data?.stall || sprint?.stall;
  const agents = useMemo(() => buildAgents(session.status, dashboard, session.events), [session.status, dashboard, session.events]);
  const phase = asString(data?.phase || currentSprint.phase || currentSprint.status);
  const isBlocked = Boolean(stall?.is_stalled);
  const isComplete = statusTone(asString(currentSprint.status || phase)) === "complete";

  return (
    <div className="workspace-scroll">
      <TopBar sprint={currentSprint} usage={session.usage} streamState={session.streamState} onCreated={onCreated} />
      <AnimatePresence mode="popLayout">
        {session.state === "loading" && <LoadingWorkbench key="loading" />}
        {session.state === "error" && <ErrorWorkbench key="error" message={session.error} onRetry={session.refresh} />}
        {session.state === "ready" && (
          <motion.div key="ready" className="workbench" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
            <HeroStatus sprint={currentSprint} phase={phase} isBlocked={isBlocked} isComplete={isComplete} stallText={stallCopy(stall)} dashboard={dashboard} />
            <AgentPanel agents={agents} />
            <div className="two-column-grid">
              <SprintProgress phase={phase} dashboard={dashboard} />
              <DagPanel dashboard={dashboard} />
            </div>
            <div className="two-column-grid lower">
              <ActivityStream events={session.events} streamState={session.streamState} />
              <div className="stacked-panels">
                <DeliverablesPanel deliverables={session.deliverables} />
                <UsagePanel usage={session.usage} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function dashboardForSprint(dashboard: DashboardResponse | undefined, sprintId: string): DashboardResponse | undefined {
  if (!dashboard) return undefined;
  const focus = asString(dashboard.data?.focus_sprint_id || dashboard.data?.sprint?.sprint_id);
  if (focus && focus !== sprintId) return undefined;
  return dashboard;
}

function TopBar({
  sprint,
  usage,
  streamState,
  onCreated
}: {
  sprint: SprintSummary;
  usage?: UsagePayload;
  streamState: string;
  onCreated: (sprintId: string) => Promise<void>;
}) {
  return (
    <header className="topbar">
      <div className="topbar-title">
        <PanelLeft size={17} />
        <span>{titleForSprint(sprint)}</span>
      </div>
      <div className="topbar-actions">
        <div className={`stream-chip stream-${streamState}`}>
          <Radio size={14} />
          <span>{streamState}</span>
        </div>
        <div className="usage-chip">
          <Zap size={14} />
          <span>{usage?.total_used_tokens_label || "0 tok"}</span>
        </div>
        <NewTaskDialog onCreated={onCreated} buttonClassName="icon-text-button" compact />
      </div>
    </header>
  );
}

function HeroStatus({
  sprint,
  phase,
  isBlocked,
  isComplete,
  stallText,
  dashboard
}: {
  sprint: SprintSummary;
  phase: string;
  isBlocked: boolean;
  isComplete: boolean;
  stallText: string;
  dashboard?: DashboardResponse;
}) {
  const progress = dashboard?.data?.progress;
  const total = Number(progress?.total_nodes || 0);
  const done = Number(progress?.completed_nodes || progress?.passed_nodes || progress?.status_counts?.passed || 0);
  const percentage = total > 0 ? Math.round((done / total) * 100) : 0;
  const status = isBlocked ? "Stalled" : isComplete ? "Complete" : asString(sprint.status || phase, "Active").replace(/_/g, " ");

  return (
    <section className={`hero-status ${isBlocked ? "is-blocked" : ""} ${isComplete ? "is-complete" : ""}`} data-testid="hero-status">
      <div className="hero-main">
        <div className="eyebrow-row">
          <span className={`state-orb tone-${isBlocked ? "blocked" : isComplete ? "complete" : "working"}`} />
          <span>{status}</span>
          <span>{asString(sprint.sprint_id)}</span>
        </div>
        <h1>{titleForSprint(sprint)}</h1>
        <p>{isBlocked ? stallText : isComplete ? "Build phase is marked complete by the harness." : `Current phase: ${phase.replace(/_/g, " ") || "detecting"}`}</p>
      </div>
      <div className="hero-metrics">
        <Metric value={`${percentage}%`} label="DAG progress" />
        <Metric value={compactNumber(total)} label="nodes" />
        <Metric value={compactNumber(progress?.blocked_nodes || 0)} label="blocked" tone={isBlocked ? "blocked" : "default"} />
      </div>
    </section>
  );
}

function Metric({ value, label, tone = "default" }: { value: string; label: string; tone?: "default" | "blocked" }) {
  return (
    <div className={`metric tone-${tone}`}>
      <span>{value}</span>
      <small>{label}</small>
    </div>
  );
}

function AgentPanel({ agents }: { agents: AgentCardModel[] }) {
  return (
    <section className="agent-panel" data-testid="agent-panel">
      <SectionHeader icon={<Activity size={17} />} title="Agents" detail="PM, planner, builder, evaluator" />
      <div className="agent-grid">
        {agents.map((agent) => (
          <motion.article layout className={`agent-card agent-${agent.state}`} key={agent.role}>
            <div className="agent-card-top">
              <div>
                <h2>{agent.title}</h2>
                <span>{agent.subtitle}</span>
              </div>
              <AgentState state={agent.state} />
            </div>
            <p className="agent-activity">{agent.activity}</p>
            <div className="agent-meta">
              <span>{agent.model || "model unknown"}</span>
              <span>{agent.pane || "no pane"}</span>
            </div>
            <div className="last-event">{agent.lastEvent}</div>
          </motion.article>
        ))}
      </div>
    </section>
  );
}

function AgentState({ state }: { state: AgentCardModel["state"] }) {
  const icon = state === "blocked" ? <AlertTriangle size={14} /> : state === "complete" ? <CheckCircle2 size={14} /> : state === "working" ? <Loader2 className="spin-soft" size={14} /> : <Circle size={12} />;
  return (
    <div className={`agent-state tone-${state}`}>
      {icon}
      <span>{state}</span>
    </div>
  );
}

function buildAgents(status?: StatusPayload, dashboard?: DashboardResponse, events: EventRecord[] = []): AgentCardModel[] {
  const panes = [
    ...(status?.panes || []),
    ...((dashboard?.data?.capabilities?.pane_supply || []).map((pane) => ({
      id: pane.pane_id,
      pane_id: pane.pane_id,
      role: pane.role,
      state: pane.state,
      status: pane.state,
      current_activity: "",
      model: pane.model
    })) || [])
  ];

  return ROLE_ORDER.map((role) => {
    const meta = ROLE_META[role];
    const pane = panes.find((item) => normalizeRole(item.role) === role);
    const recent = events.find((event) => normalizeRole(eventActor(event)) === role);
    const readable = recent ? humanEvent(recent) : undefined;
    const paneState = asString(pane?.state || pane?.status);
    const eventState = readable?.tone || "";
    const state = eventState === "blocked" ? "blocked" : eventState === "complete" ? "complete" : statusTone(paneState || eventState);
    return {
      role,
      title: meta.title,
      subtitle: meta.subtitle,
      state,
      activity: asString(pane?.current_activity) || readable?.title || "Waiting for harness activity",
      model: asString(pane?.model),
      pane: asString(pane?.id || pane?.pane_id),
      lastEvent: readable ? `${formatTime(eventTimestamp(recent as EventRecord))} · ${readable.detail || readable.title}` : "No recent event"
    };
  });
}

function SprintProgress({ phase, dashboard }: { phase: string; dashboard?: DashboardResponse }) {
  const progress = dashboard?.data?.progress;
  const counts = progress?.status_counts || {};
  const currentIndex = Math.max(0, PHASES.findIndex((item) => phase.includes(item)));

  return (
    <section className="panel phase-panel" data-testid="phase-panel">
      <SectionHeader icon={<GitBranch size={17} />} title="Sprint journey" detail="Spec to build" />
      <div className="phase-line">
        {PHASES.map((item, index) => {
          const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "pending";
          return (
            <div className={`phase-step phase-${state}`} key={item}>
              <span>{index < currentIndex ? <CheckCircle2 size={16} /> : <Circle size={14} />}</span>
              <div>{item.replace(/_/g, " ")}</div>
            </div>
          );
        })}
      </div>
      <div className="status-counts">
        {Object.entries(counts).length === 0 && <EmptyInline label="No node counts yet" />}
        {Object.entries(counts).map(([key, value]) => (
          <div key={key} className={`count-row tone-${statusTone(key)}`}>
            <span>{key.replace(/_/g, " ")}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function DagPanel({ dashboard }: { dashboard?: DashboardResponse }) {
  const nodes = dashboard?.data?.dag?.nodes || [];
  return (
    <section className="panel dag-panel" data-testid="dag-panel">
      <SectionHeader icon={<Boxes size={17} />} title="DAG" detail={`${nodes.length} nodes`} />
      <div className="dag-list">
        {nodes.length === 0 && <EmptyInline label="No task graph available" />}
        {nodes.map((node) => {
          const status = asString(node.status, "pending");
          return (
            <article className={`dag-node tone-${statusTone(status)}`} key={nodeId(node)}>
              <div className="dag-node-line">
                <span className={`state-dot tone-${statusTone(status)}`} />
                <div>
                  <h3>{nodeId(node)}</h3>
                  <p>{nodeTitle(node)}</p>
                </div>
                <strong>{status.replace(/_/g, " ")}</strong>
              </div>
              <div className="dag-node-meta">
                {(node.depends_on || []).slice(0, 4).map((dep) => (
                  <span key={dep}>after {dep}</span>
                ))}
                {(node.required_capabilities || []).slice(0, 4).map((cap) => (
                  <span key={cap}>{cap}</span>
                ))}
                {node.route_decision && <span>{asString(node.route_decision).replace(/_/g, " ")}</span>}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ActivityStream({ events, streamState }: { events: EventRecord[]; streamState: string }) {
  return (
    <section className="panel activity-panel" data-testid="activity-stream">
      <SectionHeader icon={<Radio size={17} />} title="Activity stream" detail={streamState} />
      <div className="event-list">
        {events.length === 0 && <EmptyInline label="Waiting for runtime events" />}
        {events.map((event, index) => {
          const readable = humanEvent(event);
          return (
            <motion.article
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`event-row tone-${readable.tone}`}
              key={`${eventTimestamp(event)}-${eventActor(event)}-${index}`}
            >
              <div className="event-time">{formatTime(eventTimestamp(event))}</div>
              <div className="event-body">
                <div className="event-title-row">
                  <strong>{readable.title}</strong>
                  <span>{eventActor(event)}</span>
                </div>
                {readable.detail && <p>{readable.detail}</p>}
              </div>
            </motion.article>
          );
        })}
      </div>
    </section>
  );
}

function DeliverablesPanel({ deliverables }: { deliverables: Deliverable[] }) {
  const primary = deliverables.find((item) => item.kind === "html" || item.name.endsWith(".html")) || deliverables[0];
  return (
    <section className="panel deliverables-panel" data-testid="deliverables-panel">
      <SectionHeader icon={<FileText size={17} />} title="Deliverables" detail={`${deliverables.length} artifacts`} />
      {deliverables.length === 0 && <EmptyInline label="No artifacts produced yet" />}
      {primary && (
        <a className="primary-deliverable" href={primary.view_url} target="_blank" rel="noreferrer">
          <FileText size={18} />
          <span>
            <strong>{primary.name}</strong>
            <small>{primary.kind.toUpperCase()} · {compactNumber(primary.size || 0)}B</small>
          </span>
          <ArrowUpRight size={16} />
        </a>
      )}
      <div className="deliverable-list">
        {deliverables.filter((item) => item !== primary).slice(0, 5).map((item) => (
          <a href={item.view_url} target="_blank" rel="noreferrer" key={item.rel_path}>
            <span>{item.name}</span>
            <ArrowUpRight size={13} />
          </a>
        ))}
      </div>
    </section>
  );
}

function UsagePanel({ usage }: { usage?: UsagePayload }) {
  return (
    <section className="panel usage-panel" data-testid="usage-panel">
      <SectionHeader icon={<Zap size={17} />} title="Usage" detail={usage?.total_used_tokens_label || "0 tok"} />
      <p className="usage-label">{usage?.label || "source: Claude log scan / quota-footer; scope: model-day estimate; not per-sprint or per-agent"}</p>
      <div className="usage-models">
        {(usage?.models || []).slice(0, 4).map((model) => (
          <div className="usage-model" key={`${model.model_key}-${model.date}`}>
            <span>{model.model_key}</span>
            <strong>{model.used_tokens_label}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function SettingsView() {
  const [settings, setSettings] = useState<SettingsPayload>();
  const [status, setStatus] = useState<StatusPayload>();
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [settingsResponse, statusResponse] = await Promise.all([fetchSettings(), fetchStatus()]);
      setSettings(settingsResponse);
      setStatus(statusResponse);
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

  const physical = settings?.physical_operators || status?.physical_operators || {};
  const roleModels = Object.entries(settings?.role_models || {});

  return (
    <div className="workspace-scroll">
      <header className="topbar">
        <div className="topbar-title">
          <Settings size={17} />
          <span>Settings</span>
        </div>
        <button type="button" className="icon-text-button" onClick={() => void refresh()}>
          <RefreshCw size={15} />
          <span>Refresh</span>
        </button>
      </header>
      <div className="settings-layout" data-testid="settings-view">
        <section className="hero-status settings-hero">
          <div className="hero-main">
            <div className="eyebrow-row">
              <span className="state-orb tone-idle" />
              <span>Read-only</span>
              <span>{settings?.source || "status-server"}</span>
            </div>
            <h1>Model and lab configuration</h1>
            <p>{settings?.write_note || "P0 exposes current configuration without inventing a new write path."}</p>
          </div>
          <div className="hero-metrics">
            <Metric value={compactNumber(physical.count || 0)} label="operators" />
            <Metric value={compactNumber(physical.available || 0)} label="available" />
            <Metric value={compactNumber(physical.busy || 0)} label="busy" />
          </div>
        </section>

        {state === "loading" && <LoadingWorkbench />}
        {state === "error" && <ErrorWorkbench message={error} onRetry={refresh} />}
        {state === "ready" && (
          <div className="two-column-grid">
            <section className="panel">
              <SectionHeader icon={<SquareTerminal size={17} />} title="Lab matrix" detail={settings?.model_lab_matrix?.source || "unset"} />
              <div className="setting-row">
                <span>All-Claude / GLM lab matrix</span>
                <Switch.Root className="switch-root" checked={Boolean(settings?.model_lab_matrix?.value)} disabled>
                  <Switch.Thumb className="switch-thumb" />
                </Switch.Root>
              </div>
              <code className="code-block">{settings?.model_lab_matrix?.value || "No lab matrix value found in env/config scan."}</code>
            </section>
            <section className="panel">
              <SectionHeader icon={<ShieldCheck size={17} />} title="Role models" detail={`${roleModels.length} configured`} />
              <div className="settings-list">
                {roleModels.length === 0 && <EmptyInline label="No role model overrides found" />}
                {roleModels.map(([role, info]) => (
                  <div className="setting-row" key={role}>
                    <span>{role}</span>
                    <strong>{info.model || "unset"}</strong>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({ onCreated }: { onCreated: (sprintId: string) => Promise<void> }) {
  return (
    <div className="empty-page" data-testid="empty-state">
      <div className="empty-mark">
        <Sparkles size={28} />
      </div>
      <h1>No harness sessions</h1>
      <p>Start a real intake to create a sprint and watch agents, events, DAG progress, deliverables, and usage populate here.</p>
      <NewTaskDialog onCreated={onCreated} buttonClassName="primary-button" />
    </div>
  );
}

function LoadingWorkbench() {
  return (
    <motion.div className="loading-workbench" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      {Array.from({ length: 4 }, (_, index) => (
        <div className="loading-panel" key={index} />
      ))}
    </motion.div>
  );
}

function ErrorWorkbench({ message, onRetry }: { message: string; onRetry: () => Promise<void> }) {
  return (
    <div className="error-panel">
      <AlertTriangle size={20} />
      <div>
        <h2>Unable to load this view</h2>
        <p>{message}</p>
      </div>
      <button type="button" className="icon-text-button" onClick={() => void onRetry()}>
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

function SectionHeader({ icon, title, detail }: { icon: React.ReactNode; title: string; detail?: string }) {
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
