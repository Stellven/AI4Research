import * as Dialog from "@radix-ui/react-dialog";
import * as Popover from "@radix-ui/react-popover";
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
  Eye,
  EyeOff,
  FileCheck2,
  FileText,
  Loader2,
  MessageSquarePlus,
  Minus,
  PanelRight,
  Paperclip,
  PauseCircle,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Save,
  Settings,
  ShieldCheck,
  SquareTerminal,
  Workflow,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import {
  useCallback,
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
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
  fetchAuthLoginStatus,
  fetchAuthStatus,
  fetchDeliverables,
  fetchDeliverableText,
  fetchEvents,
  fetchProjection,
  reuseHostCreds,
  startAuthLogin,
  submitEvalVerdict,
  submitHandoff,
  fetchSettings,
  fetchSprints,
  fetchStatus,
  fetchUsage,
  openEventStream,
  openProjectionStream,
  saveSettings,
  submitIntake,
  submitPlanVerdict,
} from "./api";
import type { AuthLoginStatus, AuthStatus } from "./api";
import type { AgentRole } from "./format";
import { activeNodeActor, nodeActor } from "./nodeActor";
import { pipelineStages, type TerminalRunOutcome } from "./runPipeline";
import { perRunUsageLabel } from "./runUsage";
import {
  ROLE_META,
  ROLE_ORDER,
  asString,
  compactNumber,
  eventActor,
  eventType,
  eventTimestamp,
  formatDateTime,
  humanEvent,
  localTimeZoneName,
  mergeEvents,
  nodeId,
  nodeTitle,
  normalizeRole,
  payload,
  shortText,
  stallCopy,
  statusTone,
  titleForSprint,
  unwrapEvent,
} from "./format";
import type {
  DagNode,
  Deliverable,
  EventRecord,
  HumanGate,
  NarrativeStep,
  PlanGovernance,
  ProjectionAction,
  ProjectionData,
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
  provenance: SessionProvenance;
  state: LoadState;
  error: string;
  streamState: "connecting" | "live" | "retrying" | "off";
  refresh: () => Promise<void>;
};

type SessionProvenance = {
  sprintId: string;
  recentEventsScope?: string;
  recentEventsSource?: string;
  statusCache?: string;
  lastStatusAt?: string;
  lastEventsAt?: string;
  lastProjectionAt?: string;
  degradedSources?: string[];
  eventCount?: number;
};

type SessionCacheEntry = Pick<
  SessionData,
  "status" | "projection" | "events" | "usage" | "deliverables" | "provenance"
>;

const sessionDataCache = new Map<string, SessionCacheEntry>();

type ErrorBoundaryState = {
  error: string;
};

class AppErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: "" };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return {
      error:
        error instanceof Error
          ? error.message
          : "The session view hit a rendering error.",
    };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("Solar UI error boundary", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="app-fallback">
        <div className="empty-card">
          <AlertTriangle size={24} />
          <h2>Session view could not render</h2>
          <p>{this.state.error}</p>
          <div className="empty-actions">
            <button
              className="primary-button"
              type="button"
              onClick={() => window.location.reload()}
            >
              <RefreshCw size={16} />
              <span>Reload</span>
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => {
                this.setState({ error: "" });
                window.history.pushState({}, "", "/");
                window.dispatchEvent(new PopStateEvent("popstate"));
              }}
            >
              <ArrowLeft size={16} />
              <span>Back to sessions</span>
            </button>
          </div>
        </div>
      </div>
    );
  }
}

function emptySessionProvenance(sprintId: string): SessionProvenance {
  return { sprintId };
}

function isEventForSprint(event: EventRecord, sprintId: string): boolean {
  return asString(event.sprint_id) === sprintId;
}

function intakeErrorMessage(response: {
  error?: string;
  stdout_tail?: string;
  request_id?: string;
  attribution?: string;
  ambiguous?: boolean;
  candidate_sprint_ids?: string[];
}): string {
  if (response.ambiguous) {
    const candidates = (response.candidate_sprint_ids || []).filter(Boolean);
    return `Could not safely identify the new session for request ${asString(response.request_id, "(unknown)")}. Candidate sessions: ${candidates.join(", ") || "none"}.`;
  }
  return (
    response.error ||
    response.stdout_tail ||
    `Intake did not return a sprint id for request ${asString(response.request_id, "(unknown)")}`
  );
}

type ProcessStepState = "active" | "blocked" | "completed" | "pending";

type ProcessStep = {
  id: string;
  actor: string;
  node?: string;
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

const PROVIDER_LABEL: Record<string, string> = {
  codex: "OpenAI Codex",
  claude: "Claude (Anthropic)",
};

// Subscription-first sign-in. The automatic path wins by default: if the active runtime's
// provider is already authed (or detection is unavailable) we render the app with zero friction.
// Only an explicit "unauth" shows the sign-in card, and even then "Continue" never hard-blocks.
function AuthGate({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<"checking" | "ready" | "signin">(
    "checking",
  );
  const [provider, setProvider] = useState<"claude" | "codex">("claude");
  const [busy, setBusy] = useState(false);
  const [login, setLogin] = useState<AuthLoginStatus | null>(null);
  const [message, setMessage] = useState("");
  const pollRef = useRef<number | undefined>(undefined);

  const evaluate = useCallback(
    (auth: AuthStatus | null, runtime: "claude" | "codex") => {
      const state = auth?.[runtime];
      // Degrade OPEN: only a definite "unauth" blocks; detection gaps never trap the user.
      setPhase(state === "unauth" ? "signin" : "ready");
    },
    [],
  );

  const check = useCallback(async () => {
    try {
      const [auth, settings] = await Promise.all([
        fetchAuthStatus(),
        fetchSettings().catch(() => null),
      ]);
      const runtime: "claude" | "codex" =
        settings?.runtime?.value === "codex" ? "codex" : "claude";
      setProvider(runtime);
      evaluate(auth, runtime);
    } catch {
      setPhase("ready"); // status-server unreachable -> don't block the app
    }
  }, [evaluate]);

  useEffect(() => {
    void check();
  }, [check]);
  useEffect(
    () => () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    },
    [],
  );

  const recheck = useCallback(async () => {
    const auth = await fetchAuthStatus().catch(() => null);
    if (auth && auth[provider] === "ok") {
      setPhase("ready");
      return true;
    }
    return false;
  }, [provider]);

  const onReuse = useCallback(async () => {
    setBusy(true);
    setMessage("");
    try {
      const r = await reuseHostCreds(provider);
      if (r.reused) {
        const ok = await recheck();
        if (!ok)
          setMessage("Copied an existing sign-in, but it didn’t verify yet.");
      } else {
        setMessage(
          "No existing sign-in found on this machine — use a device code below.",
        );
      }
    } catch {
      setMessage("Couldn’t reuse an existing sign-in.");
    } finally {
      setBusy(false);
    }
  }, [provider, recheck]);

  const onDeviceLogin = useCallback(async () => {
    setBusy(true);
    setMessage("");
    setLogin(null);
    try {
      await startAuthLogin(provider);
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(async () => {
        const s = await fetchAuthLoginStatus(provider).catch(() => null);
        if (!s) return;
        setLogin(s);
        if (s.state === "done") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          await recheck();
        } else if (s.state === "failed") {
          if (pollRef.current) window.clearInterval(pollRef.current);
          setMessage("Sign-in didn’t complete — you can try again.");
        }
      }, 2000);
    } catch {
      setMessage("Couldn’t start sign-in.");
    } finally {
      setBusy(false);
    }
  }, [provider, recheck]);

  if (phase === "checking") {
    return (
      <div className="auth-gate" data-testid="auth-checking">
        <div className="auth-card auth-card-slim">
          <Loader2 className="spin" size={22} />
          <span>Checking your sign-in…</span>
        </div>
      </div>
    );
  }
  if (phase === "ready") return <>{children}</>;

  const pending = login?.state === "pending" || login?.state === "started";
  return (
    <div className="auth-gate" data-testid="auth-signin">
      <div className="auth-card">
        <BrandMark size={44} />
        <h1 className="auth-title">Sign in to run Solar</h1>
        <p className="auth-sub">
          Solar runs your work through{" "}
          <strong>{PROVIDER_LABEL[provider]}</strong> using your existing
          subscription. Sign in once on this machine.
        </p>

        <button
          className="auth-primary"
          onClick={onReuse}
          disabled={busy}
          data-testid="auth-reuse"
        >
          {busy ? (
            <Loader2 className="spin" size={16} />
          ) : (
            <ShieldCheck size={16} />
          )}
          Use my existing sign-in
        </button>

        <button
          className="auth-secondary"
          onClick={onDeviceLogin}
          disabled={busy}
          data-testid="auth-device"
        >
          Sign in with a device code
        </button>

        {pending && (
          <div className="auth-device-box" data-testid="auth-device-box">
            <p className="auth-device-hint">
              Open this link and enter the code:
            </p>
            {login?.url ? (
              <a
                href={login.url}
                target="_blank"
                rel="noreferrer"
                className="auth-link"
              >
                {login.url} <ArrowUpRight size={14} />
              </a>
            ) : null}
            {login?.code ? (
              <div className="auth-code" data-testid="auth-code">
                {login.code}
              </div>
            ) : null}
            {!login?.url && login?.tail ? (
              <pre className="auth-tail">{login.tail}</pre>
            ) : null}
            <div className="auth-waiting">
              <Loader2 className="spin" size={14} /> Waiting for you to finish…
            </div>
          </div>
        )}
        {login?.state === "done" && (
          <div className="auth-done" data-testid="auth-done">
            <CheckCircle2 size={16} /> Signed in. Loading…
          </div>
        )}

        {message && <p className="auth-message">{message}</p>}

        <div className="auth-foot">
          <button
            className="auth-ghost"
            onClick={() => {
              setPhase("ready");
              navigate("/settings");
            }}
          >
            Advanced: set provider API keys
          </button>
          <button className="auth-ghost" onClick={() => setPhase("ready")}>
            Continue without signing in
          </button>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <Tooltip.Provider delayDuration={220}>
      <AuthGate>
        <AppErrorBoundary>
          <Shell />
        </AppErrorBoundary>
      </AuthGate>
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

  // C2 sequence guard: refreshSprints fires from mount, the debounced SSE handler, AND the interval
  // poll, so calls overlap. Tag each call; if a newer call started while this fetch was in flight,
  // drop the result — otherwise a slow older response can land last and clobber the fresh list.
  const refreshSprintsSeq = useRef(0);
  const refreshSprints = useCallback(async () => {
    const seq = ++refreshSprintsSeq.current;
    try {
      const response = await fetchSprints();
      if (seq !== refreshSprintsSeq.current) return;
      setSprints(response.data?.sprints || []);
      setState("ready");
      setError("");
    } catch (err) {
      if (seq !== refreshSprintsSeq.current) return;
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
    // Poll fast when there's no live stream; slow when there is. If the stream drops we switch
    // back to the fast poll (so the list never silently stops updating) and speed down again on
    // reconnect.
    let pollId: number | undefined;
    const startPoll = (ms: number) => {
      if (pollId) window.clearInterval(pollId);
      pollId = window.setInterval(() => void refreshSprints(), ms);
    };
    const stream = openEventStream(undefined, scheduleRefresh, () =>
      startPoll(5000),
    );
    if (stream) stream.onopen = () => startPoll(20000);
    startPoll(stream ? 20000 : 5000);
    return () => {
      if (pending) window.clearTimeout(pending);
      stream?.close();
      if (pollId) window.clearInterval(pollId);
    };
  }, [refreshSprints]);

  const onCreated = useCallback(
    async (sprintId: string, requestId = "") => {
      await refreshSprints();
      const trace = requestId
        ? `?request_id=${encodeURIComponent(requestId)}`
        : "";
      navigate(`/sessions/${encodeURIComponent(sprintId)}${trace}`);
    },
    [navigate, refreshSprints],
  );

  return (
    <div
      className={`app-shell ${isSettingsRoute ? "settings-shell-route" : ""}`}
    >
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
  onCreated: (sprintId: string, requestId?: string) => Promise<void>;
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
  onCreated: (sprintId: string, requestId?: string) => Promise<void>;
  buttonClassName?: string;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [task, setTask] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const cleanTask = task.trim();
    if (!cleanTask && files.length === 0) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await submitIntake(cleanTask, files);
      if (!response.ok || !response.sprint_id) {
        throw new Error(intakeErrorMessage(response));
      }
      setTask("");
      setFiles([]);
      setOpen(false);
      await onCreated(response.sprint_id, response.request_id || "");
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
          <Dialog.Title id="new-task-dialog-title" className="dialog-title">
            Describe what you want done
          </Dialog.Title>
          <Dialog.Description id="new-task-dialog-description" className="dialog-description">
            This starts a real AI4Research intake via the existing CLI.
          </Dialog.Description>
          <form onSubmit={onSubmit} className="intake-form">
            <textarea
              aria-labelledby="new-task-dialog-title"
              aria-describedby="new-task-dialog-description"
              value={task}
              onChange={(event) => setTask(event.target.value)}
              placeholder="Build, investigate, verify, or produce an artifact..."
              autoFocus
              rows={7}
            />
            <IntakeAttachments
              files={files}
              onChange={setFiles}
              onError={setError}
              disabled={submitting}
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
                disabled={(!task.trim() && files.length === 0) || submitting}
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

const MAX_INTAKE_FILES = 8;
const MAX_INTAKE_FILE_BYTES = 5 * 1024 * 1024;
const MAX_INTAKE_TOTAL_BYTES = 10 * 1024 * 1024;

function readableFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function IntakeAttachments({
  files,
  onChange,
  onError,
  disabled = false,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  onError: (message: string) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  function addFiles(selected: File[]) {
    const combined = [...files, ...selected];
    if (combined.length > MAX_INTAKE_FILES) {
      onError(`Attach up to ${MAX_INTAKE_FILES} files per task.`);
      return;
    }
    const oversized = selected.find((file) => file.size > MAX_INTAKE_FILE_BYTES);
    if (oversized) {
      onError(`${oversized.name} is larger than 5 MB.`);
      return;
    }
    const total = combined.reduce((sum, file) => sum + file.size, 0);
    if (total > MAX_INTAKE_TOTAL_BYTES) {
      onError("Attachments may total up to 10 MB per task.");
      return;
    }
    onError("");
    onChange(combined);
  }

  return (
    <div className="intake-attachments">
      <input
        ref={inputRef}
        className="intake-file-input"
        type="file"
        multiple
        disabled={disabled}
        onChange={(event) => {
          addFiles(Array.from(event.target.files || []));
          event.target.value = "";
        }}
      />
      <button
        type="button"
        className="intake-attach-button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
      >
        <Paperclip size={14} aria-hidden="true" />
        <span>Attach files</span>
      </button>
      {files.length > 0 && (
        <div className="intake-file-list" aria-label="Attached files">
          {files.map((file, index) => (
            <span className="intake-file-chip" key={`${file.name}-${file.lastModified}-${index}`}>
              <span title={file.name}>{file.name}</span>
              <small>{readableFileSize(file.size)}</small>
              <button
                type="button"
                aria-label={`Remove ${file.name}`}
                onClick={() => onChange(files.filter((_, fileIndex) => fileIndex !== index))}
                disabled={disabled}
              >
                <X size={12} aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function SessionRoute({
  sprints,
  onCreated,
  onSprintChanged,
}: {
  sprints: SprintSummary[];
  onCreated: (sprintId: string, requestId?: string) => Promise<void>;
  onSprintChanged: () => Promise<void>;
}) {
  const { sprintId = "" } = useParams();
  const decodedSprintId = decodeURIComponent(sprintId);
  if (!decodedSprintId) {
    return <HomeLanding sprints={sprints} onCreated={onCreated} />;
  }
  // key by sprintId so switching sessions REMOUNTS the data owner: useSessionData state
  // (status/projection/events/provenance) and all child component state (GateCard verdict/notice,
  // deliverable preview) reset, instead of briefly painting the previous session's data into the
  // new one (the rapid-switch stale-paint / gate-state-leak class).
  return (
    <SessionRouteView
      key={decodedSprintId}
      sprintId={decodedSprintId}
      sprints={sprints}
      onCreated={onCreated}
      onSprintChanged={onSprintChanged}
    />
  );
}

function SessionRouteView({
  sprintId,
  sprints,
  onCreated,
  onSprintChanged,
}: {
  sprintId: string;
  sprints: SprintSummary[];
  onCreated: (sprintId: string) => Promise<void>;
  onSprintChanged: () => Promise<void>;
}) {
  const session = useSessionData(sprintId, onSprintChanged);
  const location = useLocation();
  const requestId = new URLSearchParams(location.search).get("request_id") || "";
  const sprint = sprints.find((item) => item.sprint_id === sprintId);
  return (
    <SessionView
      sprint={sprint as SprintSummary | undefined}
      sprintId={sprintId}
      session={session}
      onCreated={onCreated}
      requestId={requestId}
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
  const [provenance, setProvenance] = useState<SessionProvenance>(
    emptySessionProvenance(sprintId),
  );
  const [state, setState] = useState<LoadState>("ready");
  const [error, setError] = useState("");
  const [streamState, setStreamState] = useState<
    "connecting" | "live" | "retrying" | "off"
  >("connecting");
  const selectedSprintRef = useRef(sprintId);
  // G4 UI-rung run 6: a late poll response landed AFTER a fresher SSE delta
  // and regressed a node from active back to pending on screen for ~45s
  // (truthful-states UI_STALE). Projections apply MONOTONICALLY by
  // generated_at — a stale response is dropped, whatever path it came by.
  const lastProjectionAtRef = useRef("");
  const applyProjection = useCallback(
    (response: ProjectionResponse): boolean => {
      const at = asString(response.generated_at);
      if (at && lastProjectionAtRef.current && at < lastProjectionAtRef.current) {
        return false;
      }
      if (at) lastProjectionAtRef.current = at;
      setProjection(response);
      return true;
    },
    [],
  );

  useEffect(() => {
    selectedSprintRef.current = sprintId;
    lastProjectionAtRef.current = "";
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
        provenance: emptySessionProvenance(sprintId),
      };
      sessionDataCache.set(sprintId, { ...base, ...patch });
    };
    const patchProvenance = (patch: Partial<SessionProvenance>) => {
      setProvenance((prev) => {
        const next = { ...prev, sprintId, ...patch };
        cachePatch({ provenance: next });
        return next;
      });
    };

    setError("");
    setState(sessionDataCache.has(sprintId) ? "ready" : "loading");

    // Each endpoint applies its own slice as soon as it resolves. A slow
    // endpoint (e.g. /usage, /status) never holds back the process stream,
    // the DAG/plan, or the stall reason — those land the moment their own
    // request returns instead of waiting on the slowest of the batch.
    const results = await Promise.allSettled([
      fetchProjection(sprintId, "fast").then((projectionResponse) => {
        if (!isCurrent()) return;
        if (!applyProjection(projectionResponse)) return; // stale vs SSE
        cachePatch({ projection: projectionResponse });
        patchProvenance({
          lastProjectionAt:
            projectionResponse.generated_at || new Date().toISOString(),
          degradedSources: projectionResponse.degraded_sources || [],
        });
      }),
      fetchStatus(sprintId).then((statusResponse) => {
        if (!isCurrent()) return;
        setStatus(statusResponse);
        cachePatch({ status: statusResponse });
        patchProvenance({
          recentEventsScope: asString(statusResponse.recent_events_scope),
          recentEventsSource: asString(statusResponse.recent_events_source),
          statusCache: asString(statusResponse.status_cache),
          lastStatusAt: new Date().toISOString(),
        });
      }),
      fetchEvents(sprintId, 140).then((eventsResponse) => {
        if (!isCurrent()) return;
        const scopedEvents = eventsResponse.filter((event) =>
          isEventForSprint(event, sprintId),
        );
        setEvents((existing) => {
          const merged = mergeEvents(
            existing.filter((event) => isEventForSprint(event, sprintId)),
            scopedEvents,
          );
          cachePatch({ events: merged });
          return merged;
        });
        patchProvenance({
          eventCount: scopedEvents.length,
          lastEventsAt: new Date().toISOString(),
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
    } else {
      setState("ready");
    }
  }, [sprintId]);

  useEffect(() => {
    const cached = sessionDataCache.get(sprintId);
    if (cached) {
      setStatus(cached.status);
      lastProjectionAtRef.current = asString(cached.projection?.generated_at);
      setProjection(cached.projection);
      setEvents(cached.events);
      setUsage(cached.usage);
      setDeliverables(cached.deliverables);
      setProvenance(cached.provenance || emptySessionProvenance(sprintId));
      setState("ready");
      setError("");
    } else {
      setStatus(undefined);
      setProjection(undefined);
      setUsage(undefined);
      setDeliverables([]);
      setEvents([]);
      setProvenance(emptySessionProvenance(sprintId));
      setState("loading");
      setError("");
    }
    setStreamState("connecting");
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!sprintId) return undefined;
    // Live projection: the server streams a snapshot on connect, then a delta only when the
    // sprint's semantic signature changes (node status / phase / verdict / gate / stall). We
    // apply the authoritative fast projection in place — no refetching all five endpoints on
    // every raw event. A debounced secondary refresh pulls the non-streamed slices
    // (status / usage / deliverables) when something meaningful moves; a slow interval reconciles
    // everything as a safety net and becomes the sole poll when SSE is unavailable.
    let pending: number | undefined;
    const scheduleRefresh = () => {
      if (pending) return;
      pending = window.setTimeout(() => {
        pending = undefined;
        void refresh();
        void onSprintChanged();
      }, 500);
    };
    const isCurrent = () => selectedSprintRef.current === sprintId;
    const cacheProjection = (projectionResponse: ProjectionResponse) => {
      const base: SessionCacheEntry = sessionDataCache.get(sprintId) || {
        status: undefined,
        projection: undefined,
        events: [],
        usage: undefined,
        deliverables: [],
        provenance: emptySessionProvenance(sprintId),
      };
      sessionDataCache.set(sprintId, {
        ...base,
        projection: projectionResponse,
        provenance: {
          ...(base.provenance || emptySessionProvenance(sprintId)),
          lastProjectionAt:
            projectionResponse.generated_at || new Date().toISOString(),
        },
      });
    };
    const projStream = openProjectionStream(
      sprintId,
      (msg) => {
        if (!isCurrent()) return;
        if (msg.sprint_id !== sprintId) return; // require an exact sprint match (drop missing/other)
        setStreamState("live");
        const projectionResponse: ProjectionResponse = {
          ok: true,
          data: msg.data,
          generated_at: msg.generated_at,
          schema_version: msg.data?.projection_schema,
        };
        if (!applyProjection(projectionResponse)) return; // stale frame
        setProvenance((prev) => ({
          ...prev,
          sprintId,
          lastProjectionAt:
            projectionResponse.generated_at || new Date().toISOString(),
        }));
        cacheProjection(projectionResponse);
        const changed = msg.changed || {};
        const moved =
          msg.type === "snapshot" ||
          !!changed.phase ||
          !!changed.eval_verdict ||
          (Array.isArray(changed.nodes) && changed.nodes.length > 0) ||
          (Array.isArray(changed.gates) && changed.gates.length > 0);
        if (moved) scheduleRefresh();
      },
      () => setStreamState("retrying"),
    );
    setStreamState(projStream ? "live" : "off");
    const id = window.setInterval(
      () => {
        void refresh();
        void onSprintChanged();
      },
      projStream ? 20000 : 3500,
    );
    return () => {
      if (pending) window.clearTimeout(pending);
      projStream?.close();
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
        if (!isEventForSprint(event, selectedSprintRef.current)) {
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
              provenance: {
                ...(cached.provenance ||
                  emptySessionProvenance(selectedSprintRef.current)),
                eventCount: merged.length,
                lastEventsAt: new Date().toISOString(),
              },
            });
          }
          return merged;
        });
        setProvenance((prev) => ({
          ...prev,
          eventCount: Math.max(prev.eventCount || 0, 1),
          lastEventsAt: new Date().toISOString(),
        }));
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
    provenance,
    state,
    error,
    streamState,
    refresh,
  };
}

// Progress numbers straight from the projection summary the backend already computes,
// tolerating either a 0–1 fraction or a 0–100 percent for percent_complete.
function projectionProgress(projection?: ProjectionResponse): {
  total: number;
  done: number;
  percent: number;
} {
  const p = (projection?.data?.summary?.progress || {}) as Record<
    string,
    unknown
  >;
  const total = Number(p.total_nodes) || 0;
  const done = Number(p.passed_nodes ?? p.completed_nodes) || 0;
  const raw = Number(p.percent_complete);
  let percent = 0;
  if (Number.isFinite(raw) && raw > 0) {
    percent = raw <= 1 ? Math.round(raw * 100) : Math.round(raw);
  } else if (total > 0) {
    percent = Math.round((done / total) * 100);
  }
  return { total, done, percent: Math.min(100, Math.max(0, percent)) };
}

function terminalRunOutcome(status: string, phase: string): TerminalRunOutcome {
  const value = `${status} ${phase}`.toLowerCase();
  // Failure wins if legacy projections disagree (for example a stale
  // "completed" status paired with the current phase "failed").
  if (/\b(failed|error|cancelled|canceled)\b/.test(value)) {
    return "failure";
  }
  if (/\b(passed|done|completed|eval_pass|eval_passed)\b/.test(value)) {
    return "success";
  }
  return "";
}

function isTerminalRun(status: string, phase: string): boolean {
  return Boolean(terminalRunOutcome(status, phase));
}

// The one surface above the stream that answers: where are we, what's done, what's
// next, what's blocking, and — when there is one — where the result is.
function RunOverview({
  projection,
  isBlocked,
  stall,
  deliverables,
  onOpenResult,
  requestId = "",
}: {
  projection?: ProjectionResponse;
  isBlocked: boolean;
  stall?: StallSummary;
  deliverables: Deliverable[];
  onOpenResult: (path: string) => void;
  requestId?: string;
}) {
  const data = projection?.data;
  const phase = asString(data?.phase || data?.sprint?.phase || data?.status);
  const status = asString(data?.status || data?.sprint?.status);
  const humanAction = (data?.human_action_required || {}) as {
    type?: string;
    title?: string;
    detail?: string;
  };
  const actionType = asString(humanAction.type);
  const gate = GATE_KINDS[actionType];
  const activeNode = asString(data?.summary?.active_node);
  const graphNodes = data?.task_graph?.nodes || data?.nodes || [];
  const activeGraphNode = graphNodes.find(
    (node) => asString(node.id || node.node_id) === activeNode,
  );
  const activeRole: AgentRole | "" = activeGraphNode
    ? normalizeRole(activeNodeActor(activeGraphNode))
    : "";
  const progress = projectionProgress(projection);
  const result =
    deliverables.find((item) => item.result) ||
    deliverables.find((item) => item.primary);
  const terminalOutcome = terminalRunOutcome(status, phase);
  const failedNode = graphNodes.find(
    (node) => asString(node.status).trim().toLowerCase() === "failed",
  );
  const failedRole = failedNode ? normalizeRole(nodeActor(failedNode)) : "";
  const stages = pipelineStages(
    phase,
    status,
    isBlocked,
    terminalOutcome,
    actionType,
    failedRole,
    activeRole,
  );
  const governance = (data?.plan_governance || {}) as PlanGovernance;
  const governanceState = asString(governance.state);
  const bounces = Number(governance.plan_compile_bounces || 0);
  const bounceCodes = (governance.compile_error_codes || []).join(", ");

  let kicker = "In progress";
  let line = activeNode ? `Working on ${activeNode}` : "Agents are working…";
  let tone: "working" | "blocked" | "complete" | "decision" = "working";
  if (governanceState === "plan_compile_failed") {
    // Truthful terminal (G4 §3): bounces exhausted, plan never compiled.
    kicker = "Plan failed to compile";
    line = `The plan failed to compile after ${bounces || "several"} attempt${bounces === 1 ? "" : "s"}${bounceCodes ? ` (${bounceCodes})` : ""}.`;
    tone = "blocked";
  } else if (governanceState === "plan_certificate_invalid") {
    // Truthful terminal (G4 §3): certified plan was modified after validation.
    kicker = "Plan integrity failure";
    line = "The certified plan was modified after validation.";
    tone = "blocked";
  } else if (terminalOutcome === "failure") {
    kicker = "Run failed";
    line =
      "A required step failed. Review the failed step and evaluation evidence below.";
    tone = "blocked";
  } else if (terminalOutcome === "success") {
    kicker = "Done";
    line = result ? "The result is ready." : "Run complete.";
    tone = "complete";
  } else if (gate) {
    kicker = "Your decision";
    line = asString(humanAction.title) || gate.title;
    tone = "decision";
  } else if (isBlocked || stall?.is_stalled) {
    kicker = "Paused";
    line = stallCopy(stall) || "Blocked — needs your attention.";
    tone = "blocked";
  }

  return (
    <section className="run-overview" data-testid="run-overview">
      <div className="run-overview-main">
        <div className={`run-state run-state-${tone}`}>
          <span className="run-state-kicker">{kicker}</span>
          <strong className="run-state-line">{line}</strong>
          {gate && humanAction.detail && (
            <span className="run-state-detail">
              {asString(humanAction.detail)}
            </span>
          )}
          {governanceState === "certified" && (
            <span className="plan-badge plan-badge-certified" data-testid="plan-badge-certified" title={`Plan certificate PASS${governance.certificate?.validated_at ? ` · ${governance.certificate.validated_at}` : ""}`}>
              ✓ Certified plan
            </span>
          )}
          {governanceState === "compiling" && (
            <span className="plan-badge plan-badge-compiling" data-testid="plan-badge-compiling">
              Plan compiling…
            </span>
          )}
          {bounces > 0 && governanceState !== "plan_compile_failed" && (
            <span className="plan-badge plan-badge-bounce" data-testid="plan-badge-bounce" title={bounceCodes || undefined}>
              {bounces} compile bounce{bounces === 1 ? "" : "s"}
            </span>
          )}
        </div>
        {result && (
          <button
            type="button"
            className="run-result-cta"
            data-testid="run-result-cta"
            onClick={() => onOpenResult(result.rel_path)}
          >
            <FileCheck2 size={16} aria-hidden="true" />
            <span className="run-result-label">Open result</span>
            <span className="run-result-name">{deliverableLabel(result)}</span>
          </button>
        )}
      </div>
      <ol className="run-pipeline" aria-label="Pipeline progress">
        {stages.map((stage) => (
          <li key={stage.role} className={`run-stage run-stage-${stage.state}`}>
            <span className="run-stage-dot" aria-hidden="true" />
            <span className="run-stage-label">
              {ROLE_META[stage.role].title}
            </span>
            {stage.state === "active" && (
              <span className="run-stage-now">now</span>
            )}
          </li>
        ))}
      </ol>
      <div className="run-trace" data-testid="run-control-plane-trace">
        <span>Session: {asString(data?.sprint_id || data?.sprint?.sprint_id)}</span>
        {requestId && <span>Request: {requestId}</span>}
      </div>
      {progress.total > 0 && (
        <div className="run-progress" aria-label="Step progress">
          <div className="run-progress-track">
            <div
              className="run-progress-fill"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
          <span className="run-progress-label">
            {progress.done}/{progress.total} steps · {progress.percent}%
          </span>
        </div>
      )}
    </section>
  );
}

function SessionView({
  sprint,
  sprintId,
  session,
  onCreated,
  requestId = "",
}: {
  sprint?: SprintSummary;
  sprintId: string;
  session: SessionData;
  onCreated: (sprintId: string) => Promise<void>;
  requestId?: string;
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
  const status = asString(projectionData?.status || currentSprint.status);
  const gateOpen = Boolean(GATE_KINDS[humanActionType]);
  const terminal = isTerminalRun(status, phase);
  const isBlocked = !terminal && isSystemBlocked(stall, humanActionType);
  // The run is genuinely "active" (latest step spins) only when it isn't finished,
  // isn't paused on a human gate, and isn't blocked.
  const runActive = !terminal && !gateOpen && !isBlocked;
  const narrativeCount = projectionData?.narrative?.length || 0;
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
        { showStallSummary: isBlocked, stall, runActive },
      ),
    [
      projection,
      projectionEvents,
      isBlocked,
      session.deliverables,
      phase,
      stall,
      runActive,
    ],
  );
  const rail = useDeliverablesRail();

  return (
    <div className="workspace-scroll">
      <TopBar
        sprint={currentSprint}
        streamState={session.streamState}
        provenance={session.provenance}
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
            <RunOverview
              projection={projection}
              isBlocked={isBlocked}
              stall={stall}
              deliverables={session.deliverables}
              onOpenResult={rail.openArtifact}
              requestId={requestId}
            />
            <RunHealth projection={projection} usage={session.usage} />
            <PlanFlow projection={projection} isBlocked={isBlocked} />
            <div
              className={`process-results-layout ${rail.open ? "rail-open" : "rail-collapsed"}`}
            >
              <ProcessStream
                steps={processSteps}
                rawEventCount={narrativeCount || projectionEvents.length}
                onOpenArtifact={rail.openArtifact}
                decision={
                  <DecisionZone
                    projection={projection}
                    sprintId={sprintId}
                    onRefresh={session.refresh}
                    onOpenArtifact={rail.openArtifact}
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

// Blocked-reason for a node, from whatever the projection carries: an explicit
// blocked_reason, the missing capabilities, or a no-matching-worker route decision.
function nodeBlockedReason(node: DagNode): string {
  const missing = (
    Array.isArray(
      (node as { missing_capabilities?: unknown }).missing_capabilities,
    )
      ? ((node as { missing_capabilities?: unknown[] })
          .missing_capabilities as unknown[])
      : []
  )
    .map((cap) => asString(cap))
    .filter(Boolean);
  const route = asString(
    node.route_decision || (node as { decision?: unknown }).decision,
  );
  return (
    asString(node.blocked_reason) ||
    (missing.length ? `needs ${missing.join(", ")}` : "") ||
    (route.includes("no_matching") ? "no matching worker" : "")
  );
}

// Clicking a plan node jumps to its activity in the stream (anchored by data-node),
// falling back to the stream panel so the click is never a dead end.
function scrollToNode(id: string): void {
  const target =
    document.querySelector(`[data-node="${CSS.escape(id)}"]`) ||
    document.querySelector('[data-testid="process-stream"]');
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function PlanLegend() {
  const items: Array<{ tone: string; label: string }> = [
    { tone: "complete", label: "done" },
    { tone: "working", label: "active" },
    { tone: "blocked", label: "blocked" },
    { tone: "idle", label: "pending" },
  ];
  return (
    <span className="plan-legend" aria-hidden="true">
      {items.map((item) => (
        <span key={item.tone} className={`plan-legend-item tone-${item.tone}`}>
          <span className="plan-legend-dot" />
          {item.label}
        </span>
      ))}
    </span>
  );
}

// The Planner's plan made legible: the DAG nodes as a left-to-right flow of stages,
// each node showing its goal, owning role, live status, and — when blocked — why.
function PlanFlow({
  projection,
  isBlocked,
}: {
  projection?: ProjectionResponse;
  isBlocked: boolean;
}) {
  const data = projection?.data;
  const nodes = data?.task_graph?.nodes || data?.nodes || [];
  const levels = useMemo(() => buildPlanLevels(nodes), [nodes]);
  const activeId = asString(data?.summary?.active_node);
  if (!levels.length) return null;
  const total = nodes.length;
  const done = nodes.filter(
    (node) => statusTone(asString(node.status)) === "complete",
  ).length;
  // G4 UI-rung run 5: this meta fell through to "in progress" at TERMINAL —
  // the main card said DONE while this panel said in progress on the same
  // screen. Terminal truth wins over the fallthrough.
  const runStatus = asString(data?.status || data?.sprint?.status);
  const runPhase = asString(data?.phase || data?.sprint?.phase);
  const terminal = isTerminalRun(runStatus, runPhase);
  const outcome = terminalRunOutcome(runStatus, runPhase);
  const headMeta = terminal
    ? outcome === "success"
      ? "done"
      : `ended: ${runStatus || "failed"}`
    : isBlocked
      ? "blocked at a capability gate"
      : activeId
        ? `active: ${activeId}`
        : total
          ? "in progress"
          : "";

  return (
    <section className="plan-flow" aria-label="Plan" data-testid="plan-flow">
      <div className="plan-flow-head">
        <span className="plan-flow-title">Plan</span>
        <span className="plan-flow-meta">
          {done}/{total} steps{headMeta ? ` · ${headMeta}` : ""}
        </span>
        <PlanLegend />
      </div>
      <ol className="plan-flow-track">
        {levels.map((stage, index) => (
          <li className="plan-stage" key={index}>
            <div className="plan-stage-nodes">
              {stage.map((node) => {
                const id = asString(node.node_id || node.id);
                const tone = statusTone(asString(node.status));
                const status = asString(
                  node.workflow_status || node.status,
                  "pending",
                ).replace(/_/g, " ");
                // Only show a blocked reason for an actually-blocked node (a pending node
                // can carry a long missing_capabilities list that isn't a live blocker), and
                // keep it short so one node can't balloon the card.
                const blockedReason =
                  tone === "blocked"
                    ? shortText(nodeBlockedReason(node), 90)
                    : "";
                const deps = (node.depends_on || []).filter(Boolean);
                const isActive = Boolean(activeId) && id === activeId;
                return (
                  <button
                    type="button"
                    className={`plan-card tone-${tone} ${isActive ? "is-active" : ""}`}
                    key={id}
                    onClick={() => scrollToNode(id)}
                    title={nodeTitle(node)}
                  >
                    <span className="plan-card-head">
                      <span className="plan-card-dot" aria-hidden="true" />
                      <span className="plan-card-role">{nodeActor(node)}</span>
                      <span className="plan-card-status">{status}</span>
                    </span>
                    <span className="plan-card-title">
                      {shortText(nodeTitle(node), 120)}
                    </span>
                    {blockedReason && (
                      <span className="plan-card-blocked">{blockedReason}</span>
                    )}
                    {deps.length > 0 && (
                      <span className="plan-card-deps">
                        ← {deps.join(", ")}
                      </span>
                    )}
                  </button>
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

// Deliverable file names repeat the full sprint id (e.g.
// "sprint-20260623-…--de49b5a4.acceptance_verdict.json"). Strip that prefix so the
// list shows the meaningful part ("acceptance_verdict.json").
function deliverableLabel(item: { name?: string; rel_path?: string }): string {
  const base = asString(item.name || item.rel_path)
    .split("/")
    .pop() as string;
  // Strip the sprint-id prefix (handles single- or double-dash before the hash);
  // keep the real filename intact (no underscore→space mangling of code/data files).
  const stripped = base.replace(/^sprint-.*?-+[0-9a-f]{6,}\./i, "");
  return stripped || base;
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

// Deduplicated operator rows from whatever the projection carries (runtime_health
// and/or operators), keyed so the same worker isn't counted twice.
function collectOperatorRows(
  projection?: ProjectionData,
): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = [];
  const rh = (projection as { runtime_health?: unknown } | undefined)
    ?.runtime_health;
  const ops = projection?.operators;
  if (Array.isArray(rh)) rows.push(...(rh as Array<Record<string, unknown>>));
  if (Array.isArray(ops)) rows.push(...(ops as Array<Record<string, unknown>>));
  const seen = new Set<string>();
  const out: Array<Record<string, unknown>> = [];
  for (const row of rows) {
    const id = asString(
      row.pane_id || row.operator_id || row.actor_id || row.display_name,
    );
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    out.push(row);
  }
  return out;
}

function operatorReadiness(
  row: Record<string, unknown>,
): "ready" | "busy" | "blocked" | "unknown" {
  const r = asString(row.readiness).toLowerCase();
  if (r === "ready" || r === "busy" || r === "blocked") return r;
  if (row.available === false) return "blocked";
  const state = asString(row.runtime_state || row.state).toLowerCase();
  if (/auth|quota|blocked|error|permission/.test(state)) return "blocked";
  if (/run|busy|active|dispatch|progress/.test(state)) return "busy";
  if (/idle|ready|wait/.test(state) || row.available === true) return "ready";
  return "unknown";
}

function workerStats(projection?: ProjectionData): {
  total: number;
  ready: number;
  busy: number;
  blocked: number;
} {
  const rows = collectOperatorRows(projection);
  let ready = 0;
  let busy = 0;
  let blocked = 0;
  for (const row of rows) {
    const state = operatorReadiness(row);
    if (state === "ready") ready += 1;
    else if (state === "busy") busy += 1;
    else if (state === "blocked") blocked += 1;
  }
  return { total: rows.length, ready, busy, blocked };
}

// "ready" here means any worker that could pick work up (ready or busy); total 0
// means nothing is connected to act on a verdict at all.
function projectionWorkersReady(projection?: ProjectionData): {
  total: number;
  ready: number;
} {
  const stats = workerStats(projection);
  return { total: stats.total, ready: stats.ready + stats.busy };
}

// A compact health strip surfacing worker readiness, truthful per-run usage
// availability, and the active blocker.
function RunHealth({
  projection,
  usage,
}: {
  projection?: ProjectionResponse;
  usage?: UsagePayload;
}) {
  const data = projection?.data;
  if (!data) return null;
  const stats = workerStats(data);
  const mismatch = data.capability_mismatch;
  const status = asString(data.status || data.sprint?.status);
  const phase = asString(data.phase || data.sprint?.phase);
  const hasBlocker = !isTerminalRun(status, phase) && Boolean(mismatch?.present);
  const blockedNode = asString(mismatch?.blocked_node);
  const missing = asString(mismatch?.missing_capability);
  if (stats.total === 0 && !hasBlocker) return null;
  return (
    <section
      className="run-health"
      data-testid="run-health"
      aria-label="Run health"
    >
      <div className="run-health-item">
        <span className="run-health-label">Workers</span>
        {stats.total > 0 ? (
          <span className="run-health-value">
            {stats.ready} ready
            {stats.busy ? ` · ${stats.busy} busy` : ""}
            {stats.blocked ? ` · ${stats.blocked} blocked` : ""} / {stats.total}
          </span>
        ) : (
          <span className="run-health-value run-health-warn">
            none connected
          </span>
        )}
      </div>
      <div
        className="run-health-item"
        title="Solar only shows measured per-run usage here. Task-graph cost estimates are not provider billing records."
      >
        <span className="run-health-label">Usage</span>
        <span className="run-health-value">{perRunUsageLabel(usage)}</span>
      </div>
      {hasBlocker && (
        <div className="run-health-item run-health-blocker">
          <AlertTriangle size={13} aria-hidden="true" />
          <span>
            Blocked{blockedNode ? ` at ${blockedNode}` : ""}
            {missing ? ` — needs ${missing}` : ""}
          </span>
        </div>
      )}
    </section>
  );
}

// One attention surface above the stream: the operator's current decision (a human
// gate) when one is open, otherwise an honest system-pause when the run is stalled.

// Honest after-state for a verdict: what state it moved to and whether a worker is
// actually running to act on it (recording a verdict advances state; it does not by
// itself guarantee a fresh agent pass).
function gateOutcomeMessage(
  target: "primary" | "secondary",
  kind: string,
  projection?: ProjectionData,
): string {
  if (target === "secondary") {
    return kind === "plan_review"
      ? "Sent back to the planner with your guidance."
      : "Sent back to the builder with your guidance.";
  }
  const phase = asString(projection?.phase || projection?.status).replace(
    /_/g,
    " ",
  );
  const base =
    kind === "plan_review"
      ? "Plan approved."
      : kind === "eval_review"
        ? "Result accepted."
        : "Handoff submitted.";
  const now = phase ? ` Now ${phase}.` : "";
  const workers = projectionWorkersReady(projection);
  const worker =
    workers.total === 0
      ? " No worker is currently running to pick this up — connect one to continue."
      : workers.ready === 0
        ? " All workers are blocked (auth/quota); it will run once one is ready."
        : "";
  return `${base}${now}${worker}`;
}

function DecisionZone({
  projection,
  sprintId,
  onRefresh,
  onOpenArtifact,
}: {
  projection?: ProjectionResponse;
  sprintId: string;
  onRefresh: () => Promise<void>;
  onOpenArtifact: (path: string) => void;
}) {
  const data = projection?.data;
  if (!data) return null;
  const status = asString(data.status || data.sprint?.status);
  const phase = asString(data.phase || data.sprint?.phase);
  if (isTerminalRun(status, phase)) return null;
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
        data={data}
        fallbackArtifacts={projectionGateArtifacts(
          data,
          actionType,
          primaryArtifact,
        )}
        actions={actions}
        sprintId={sprintId}
        onRefresh={onRefresh}
        onOpenArtifact={onOpenArtifact}
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
    return <SystemStall mismatch={mismatch} actions={actions} data={data} />;
  }
  return null;
}

function GateCard({
  kind,
  gate,
  data,
  fallbackArtifacts,
  actions,
  sprintId,
  onRefresh,
  onOpenArtifact,
}: {
  kind: string;
  gate?: HumanGate;
  data?: ProjectionData;
  fallbackArtifacts?: string[];
  actions: ProjectionAction[];
  sprintId: string;
  onRefresh: () => Promise<void>;
  onOpenArtifact: (path: string) => void;
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
  const workers = projectionWorkersReady(data);
  const lastVerdict =
    gate?.last_verdict && typeof gate.last_verdict === "object"
      ? (gate.last_verdict as Record<string, unknown>)
      : null;
  const lastVerdictText = lastVerdict
    ? asString(
        lastVerdict.verdict ||
          lastVerdict.decision ||
          lastVerdict.requested_verdict,
      )
    : "";
  const lastVerdictReason = lastVerdict ? asString(lastVerdict.reason) : "";

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
      setNotice(gateOutcomeMessage(target, kind, response.projection));
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
      {lastVerdictText && (
        <div className="decision-last-verdict">
          Last verdict: <strong>{lastVerdictText}</strong>
          {lastVerdictReason ? ` — ${shortText(lastVerdictReason, 80)}` : ""}
        </div>
      )}
      {workers.total === 0 && (
        <div className="decision-worker-note">
          No worker is currently running — your decision is recorded, but it
          won’t execute until one connects.
        </div>
      )}
      {artifacts.length > 0 && (
        <div className="decision-artifacts">
          <span className="decision-artifacts-label">
            <FileText size={13} aria-hidden="true" /> Review
          </span>
          {artifacts.map((path) => (
            <button
              type="button"
              key={path}
              className="decision-artifact-chip"
              onClick={() => onOpenArtifact(path)}
              title={path}
            >
              {deliverableLabel({ rel_path: path })}
            </button>
          ))}
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
  data,
}: {
  mismatch?: {
    present?: boolean;
    missing_capability?: string;
    blocked_node?: string;
    [key: string]: unknown;
  };
  actions: ProjectionAction[];
  data?: ProjectionData;
}) {
  const missing = asString(mismatch?.missing_capability);
  const blockedNodes = Array.isArray(mismatch?.blocked_nodes)
    ? (mismatch!.blocked_nodes as Array<Record<string, unknown>>)
    : [];
  const primaryBlocked = blockedNodes[0] || {};
  const blockedNode = asString(
    mismatch?.blocked_node || primaryBlocked.node_id,
  );
  const waiting = (
    Array.isArray(primaryBlocked.waiting_nodes)
      ? (primaryBlocked.waiting_nodes as unknown[])
      : []
  )
    .map((node) => asString(node))
    .filter(Boolean);
  const diagnostics = (
    Array.isArray(
      (data?.dispatch as { blocker_diagnostics?: unknown })
        ?.blocker_diagnostics,
    )
      ? ((data!.dispatch as { blocker_diagnostics?: unknown[] })
          .blocker_diagnostics as unknown[])
      : []
  )
    .map((entry) =>
      typeof entry === "string"
        ? entry
        : asString((entry as { reason?: unknown })?.reason),
    )
    .filter(Boolean)
    .slice(0, 3);
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
        {blockedNode ? (
          <>
            Node <code>{blockedNode}</code> can’t run:{" "}
          </>
        ) : null}
        Connect a worker that provides{" "}
        {missing ? <code>{missing}</code> : "the missing capability"} and the
        run continues.
      </p>
      {waiting.length > 0 && (
        <p className="stall-waiting">
          {waiting.length} node{waiting.length > 1 ? "s" : ""} waiting on this:{" "}
          <span className="stall-waiting-ids">{waiting.join(", ")}</span>
        </p>
      )}
      {diagnostics.length > 0 && (
        <ul className="stall-diagnostics">
          {diagnostics.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}
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
  rawEventCount,
  decision,
  onOpenArtifact,
}: {
  steps: ProcessStep[];
  rawEventCount: number;
  decision?: React.ReactNode;
  onOpenArtifact: (path: string) => void;
}) {
  const shown =
    rawEventCount > 0 ? Math.min(steps.length, rawEventCount) : steps.length;
  return (
    <section className="process-stream-panel" data-testid="process-stream">
      <div className="process-stream-head">
        <h2>Session timeline</h2>
        <span>
          {rawEventCount > 0
            ? `${shown} shown / ${rawEventCount} events`
            : `${steps.length} steps`}
        </span>
      </div>
      <div className="process-step-list">
        {steps.length === 0 && (
          <EmptyInline label="Waiting for agent process events" />
        )}
        {groupProcessSteps(steps).map((group) => (
          <ProcessGroup
            key={group.key}
            group={group}
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
      data-node={step.node || undefined}
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

type StepGroup = {
  key: string;
  actor: string;
  node: string;
  steps: ProcessStep[];
};

// Collapse a run of consecutive same-actor/same-node steps into one group so a busy
// agent turn reads as "Builder · 6 steps" instead of six near-identical lines. Active
// and blocked steps never merge — they always stay prominent.
function groupProcessSteps(steps: ProcessStep[]): StepGroup[] {
  const groups: StepGroup[] = [];
  for (const step of steps) {
    const node = step.node || "";
    const last = groups[groups.length - 1];
    const lastStep = last?.steps[last.steps.length - 1];
    const mergeable =
      last &&
      lastStep &&
      last.actor === step.actor &&
      last.node === node &&
      step.state !== "blocked" &&
      step.state !== "active" &&
      lastStep.state !== "blocked" &&
      lastStep.state !== "active";
    if (mergeable) {
      last.steps.push(step);
    } else {
      groups.push({ key: step.id, actor: step.actor, node, steps: [step] });
    }
  }
  return groups;
}

function ProcessGroup({
  group,
  onOpenArtifact,
}: {
  group: StepGroup;
  onOpenArtifact: (path: string) => void;
}) {
  if (group.steps.length <= 1) {
    return (
      <ProcessStepItem step={group.steps[0]} onOpenArtifact={onOpenArtifact} />
    );
  }
  const earlier = group.steps.slice(0, -1);
  const latest = group.steps[group.steps.length - 1];
  return (
    <div className="process-group" data-node={group.node || undefined}>
      <details className="process-group-collapsed">
        <summary className="process-group-summary">
          {group.actor} · {earlier.length} earlier step
          {earlier.length > 1 ? "s" : ""}
        </summary>
        <div className="process-group-earlier">
          {earlier.map((step) => (
            <ProcessStepItem
              key={step.id}
              step={step}
              onOpenArtifact={onOpenArtifact}
            />
          ))}
        </div>
      </details>
      <ProcessStepItem step={latest} onOpenArtifact={onOpenArtifact} />
    </div>
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

  // Result hierarchy: the one canonical output floats to the top, process artifacts
  // sit in the middle (already pipeline-ordered by the server), raw source files are
  // tucked into a collapsed group so they never bury the result.
  const result = deliverables.find((item) => item.result);
  const rest = result
    ? deliverables.filter((item) => item !== result)
    : deliverables;
  const sourceFiles = rest.filter((item) => item.stage === "source");
  const processArtifacts = rest.filter((item) => item.stage !== "source");

  const renderRow = (item: Deliverable, emphasis = false) => (
    <button
      type="button"
      key={item.rel_path}
      ref={focusPath === item.rel_path ? focusRowRef : undefined}
      className={`artifact-row ${emphasis ? "is-result" : ""}`}
      onClick={() => onOpen(item.rel_path)}
    >
      {emphasis ? (
        <FileCheck2 className="artifact-icon" size={15} />
      ) : (
        <FileText className="artifact-icon" size={15} />
      )}
      <span className="artifact-name" title={item.name}>
        {deliverableLabel(item)}
      </span>
      <span className="artifact-meta">
        {stageLabel(item.stage) || item.kind.toUpperCase()}
      </span>
      <ChevronRight size={14} className="artifact-chevron" />
    </button>
  );

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
        <>
          {result && (
            <div className="artifact-group" data-testid="rail-result-group">
              <div className="artifact-group-label">Result</div>
              <div className="artifact-list">{renderRow(result, true)}</div>
            </div>
          )}
          {processArtifacts.length > 0 && (
            <div className="artifact-group">
              <div className="artifact-group-label">
                Process artifacts
                <span className="rail-count">{processArtifacts.length}</span>
              </div>
              <div className="artifact-list">
                {processArtifacts.map((item) => renderRow(item))}
              </div>
            </div>
          )}
          {sourceFiles.length > 0 && (
            <details className="artifact-group artifact-source-group">
              <summary className="artifact-group-label">
                Source files
                <span className="rail-count">{sourceFiles.length}</span>
              </summary>
              <div className="artifact-list">
                {sourceFiles.map((item) => renderRow(item))}
              </div>
            </details>
          )}
        </>
      )}
      <div className="rail-divider" />
      <UsagePanel usage={usage} />
    </div>
  );
}

const STAGE_LABELS: Record<string, string> = {
  report: "Report",
  prd: "PRD",
  design: "Design",
  plan: "Plan",
  task_graph: "Task graph",
  handoff: "Handoff",
  eval: "Eval",
  source: "Source",
};

function stageLabel(stage?: string): string {
  return stage ? STAGE_LABELS[stage] || "" : "";
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
  options: {
    showStallSummary?: boolean;
    stall?: StallSummary;
    runActive?: boolean;
  } = {},
): ProcessStep[] {
  const steps: ProcessStep[] = [];
  // Only spin the latest step while the run is genuinely live; a finished/paused run
  // must not leave a perpetual spinner on its last log line.
  const runActive = options.runActive !== false;
  const narrative = projection?.data?.narrative || [];

  if (narrative.length > 0) {
    // Authoritative server narrative: already de-noised + de-duplicated. Render it
    // directly instead of reverse-engineering the raw event wall on the client.
    narrative.forEach((entry, index) => {
      const step = processStepFromNarrative(
        entry,
        index === narrative.length - 1,
        runActive,
      );
      if (step) steps.push(step);
    });
  } else {
    const orderedEvents = [...events]
      .filter((event) => {
        // Drop internal autopilot diagnostics (kb_probe_failed, ipv4_unavailable, doctor_passed,
        // route_normalized, …) — machine noise, not part of the agent story the user reads.
        const u = unwrapEvent(event);
        const a = asString(u.actor);
        const kind = eventType(u);
        return a !== "solar-autopilot" && !kind.startsWith("autopilot_");
      })
      .sort((a, b) => eventTimeValue(a) - eventTimeValue(b));

    const visibleEvents = compactProcessEvents(orderedEvents);

    visibleEvents.forEach((event, index) => {
      steps.push(
        processStepFromEvent(
          event,
          index === visibleEvents.length - 1 && runActive,
        ),
      );
    });
  }

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

  // Surface the canonical result as a stream milestone regardless of file type
  // (was HTML-only, so a markdown/pdf/code result never got a "ready" step).
  const resultDeliverable =
    deliverables.find((item) => item.result) ||
    deliverables.find(
      (item) => item.kind === "html" || item.name.endsWith(".html"),
    );
  if (resultDeliverable && !stall?.is_stalled) {
    steps.push({
      id: `deliverable-${resultDeliverable.rel_path}`,
      actor: "Harness",
      title: "Result is ready",
      summary: `${deliverableLabel(resultDeliverable)} is ready to open.`,
      detail:
        "The output is separated from the process stream so review can happen without digging through agent telemetry.",
      timestamp: resultDeliverable.mtime
        ? new Date(resultDeliverable.mtime * 1000).toISOString()
        : projection?.generated_at || "",
      state: "completed",
      tone: "complete",
      defaultExpanded: false,
      facts: [
        { label: "kind", value: resultDeliverable.kind.toUpperCase() },
        {
          label: "size",
          value: `${compactNumber(resultDeliverable.size || 0)}B`,
        },
      ],
      result: resultDeliverable,
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

const PROCESS_EVENT_LIMIT = 28;

function isSignificantProcessEvent(event: EventRecord): boolean {
  const u = unwrapEvent(event);
  const type = eventType(u).toLowerCase();
  const body = payload(u);
  const decision = asString(body.decision || u.decision).toLowerCase();
  return (
    /intake|phase|dispatch|model_session|operator_result|handoff|deliverable|artifact|verdict|eval|gate|blocked|failed|error|complete|passed/.test(
      type,
    ) || decision.includes("no_matching")
  );
}

function compactProcessEvents(events: EventRecord[]): EventRecord[] {
  const significant = events.filter(isSignificantProcessEvent);
  const source = significant.length ? significant : events;
  if (source.length <= PROCESS_EVENT_LIMIT) return source;

  const keep = new Set<EventRecord>();
  const firstIntake = source.find((event) =>
    eventType(unwrapEvent(event)).toLowerCase().includes("intake"),
  );
  if (firstIntake) keep.add(firstIntake);
  source
    .filter((event) =>
      /blocked|failed|error|gate/.test(
        eventType(unwrapEvent(event)).toLowerCase(),
      ),
    )
    .forEach((event) => keep.add(event));
  source.slice(-PROCESS_EVENT_LIMIT).forEach((event) => keep.add(event));
  return source.filter((event) => keep.has(event));
}

// Map one server narrative step (already human-titled + de-duplicated) to a stream step.
function processStepFromNarrative(
  entry: NarrativeStep,
  latest: boolean,
  runActive: boolean,
): ProcessStep | null {
  const title = asString(entry.title);
  if (!title) return null;
  const tone = asString(entry.tone, "working");
  const node = asString(entry.node_id);
  const actor = asString(entry.role || entry.actor, "Harness");
  const blocked = tone === "blocked";
  const complete = tone === "complete";
  const state: ProcessStepState = blocked
    ? "blocked"
    : latest && runActive && !complete
      ? "active"
      : "completed";
  const facts = [
    node && { label: "node", value: node },
    entry.phase && {
      label: "phase",
      value: asString(entry.phase).replace(/_/g, " "),
    },
  ].filter(Boolean) as Array<{ label: string; value: string }>;
  return {
    id: asString(entry.id) || `${asString(entry.ts)}-${title}`,
    actor,
    node,
    title,
    summary: asString(entry.summary),
    detail: "",
    timestamp: asString(entry.ts),
    state,
    tone: blocked ? "blocked" : complete ? "complete" : "working",
    defaultExpanded: blocked || (latest && runActive && !complete),
    facts,
  };
}

function processStepFromEvent(
  event: EventRecord,
  latest: boolean,
): ProcessStep {
  event = unwrapEvent(event);
  const body = payload(event);
  const type = eventType(event);
  // Narrative: attribute the step to the AGENT the coordinator dispatched to (PM/Builder/
  // Evaluator/Planner) when the payload names a role, so the stream reads "PM did X, Builder did
  // Y" instead of everything being "coordinator".
  const stepRole = normalizeRole(body.role || body.target_role || event.role);
  const actor = stepRole ? ROLE_META[stepRole].title : eventActor(event);
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
    node,
    title,
    summary,
    detail: thought || readable.detail || "",
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
  const actor = nodeActor(node);
  const status = asString(node.workflow_status || node.status, "pending");
  const tone = statusTone(asString(node.status, status));
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
    actor,
    node: nodeId(node),
    title: `${nodeId(node)} is ${status.replace(/_/g, " ")}`,
    summary: nodeTitle(node),
    detail: `${actor} DAG node ${nodeId(node)} is currently ${status.replace(/_/g, " ")}.`,
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
  provenance,
  rail,
  deliverableCount,
}: {
  sprint: SprintSummary;
  streamState: string;
  provenance: SessionProvenance;
  rail: RailController;
  deliverableCount: number;
}) {
  const scope = asString(provenance.recentEventsScope);
  const source = asString(provenance.recentEventsSource);
  const cache = asString(provenance.statusCache);
  const updatedAt =
    provenance.lastEventsAt ||
    provenance.lastProjectionAt ||
    provenance.lastStatusAt ||
    "";
  const eventCount =
    typeof provenance.eventCount === "number" ? provenance.eventCount : 0;
  const tz = localTimeZoneName(updatedAt || new Date());
  return (
    <header className="topbar">
      <div className="topbar-title-block">
        <div className="topbar-title">
          <span>{titleForSprint(sprint)}</span>
        </div>
        <div className="topbar-provenance" aria-label="Session data provenance">
          <span className="tech-id">
            {asString(sprint.sprint_id, provenance.sprintId)}
          </span>
          {scope && (
            <span className={`provenance-chip scope-${scope}`}>
              events: {scope}
              {source ? `/${source}` : ""}
            </span>
          )}
          <span className="provenance-chip">{eventCount} events</span>
          {cache && (
            <span className="provenance-chip">status cache: {cache}</span>
          )}
          {updatedAt && (
            <span className="provenance-chip">
              refreshed {formatDateTime(updatedAt)}
            </span>
          )}
          {tz && <span className="provenance-chip">timezone: {tz}</span>}
        </div>
      </div>
      <div className="topbar-actions">
        <div className={`stream-chip stream-${streamState}`}>
          <Radio size={14} />
          <span>
            {streamState === "live"
              ? "live"
              : streamState === "retrying"
                ? "reconnecting"
                : streamState === "off"
                  ? "offline"
                  : streamState}
          </span>
        </div>
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
  const total =
    usage?.total_used_tokens_label ||
    (usage?.availability === "unavailable" ? "Unavailable" : "0 tok");
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
        {usage?.label ||
          "Per model, per day (account-wide) — runtime does not report per-sprint tokens."}
      </p>
    </section>
  );
}

const MODEL_OPTIONS = [
  "codex-gpt-5.5",
  "codex-gpt-5.3-spark",
  "claude-opus-4.x",
  "claude-sonnet-4.x",
  "claude-haiku-4.x",
  "glm-4.6",
];

const CREW_PRESETS = [
  {
    id: "all-codex",
    label: "All-Codex",
    hint: "Codex/OpenAI for PM, Planner, Builder, and Evaluator",
  },
  {
    id: "all-claude",
    label: "All-Claude",
    hint: "Claude Sonnet across every role",
  },
  { id: "fast", label: "Fast", hint: "Lower-latency mixed crew" },
  { id: "high-quality", label: "High-quality", hint: "Opus-led defaults" },
  { id: "custom", label: "Custom", hint: "Per-role model choices" },
];

const RUNTIME_OPTIONS = [
  {
    id: "claude",
    label: "Claude Code",
    hint: "Legacy cockpit panes using the Claude CLI",
  },
  {
    id: "codex",
    label: "Codex CLI",
    hint: "Uses already-configured Codex operators; no model picker here",
  },
];

const API_PROVIDERS = [
  { id: "openai", label: "OpenAI", hint: "Codex CLI / OpenAI models" },
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
    // Bucket by true creation time (created_ts from the sprint_id); fall back to
    // mtime/updated_at only when it is missing, so the activity map reflects real days.
    const createdTs = sprint.created_ts;
    const mtime = sprint.mtime;
    const ts =
      typeof createdTs === "number"
        ? createdTs * 1000
        : typeof mtime === "number"
          ? mtime * 1000
          : Date.parse(
              asString(sprint.created_at) || asString(sprint.updated_at) || "",
            );
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

function normalizeCrewPreset(value: string): string {
  const clean = value.trim().toLowerCase().replace(/_/g, "-");
  if (CREW_PRESETS.some((preset) => preset.id === clean)) return clean;
  if (
    clean.includes("codex") ||
    clean.includes("openai") ||
    clean.includes("gpt")
  )
    return "all-codex";
  if (clean.includes("fast") || clean.includes("glm")) return "fast";
  if (clean.includes("quality") || clean.includes("opus"))
    return "high-quality";
  if (clean.includes("claude")) return "all-claude";
  return "custom";
}

function presetRoleModels(mode: string): Record<string, string> | undefined {
  if (mode === "all-codex") {
    return Object.fromEntries(
      ROLE_ORDER.map((role) => [role, "codex-gpt-5.5"]),
    );
  }
  if (mode === "all-claude") {
    return Object.fromEntries(
      ROLE_ORDER.map((role) => [role, "claude-sonnet-4.x"]),
    );
  }
  if (mode === "fast") {
    return {
      pm: "claude-haiku-4.x",
      planner: "glm-4.6",
      builder: "glm-4.6",
      evaluator: "claude-haiku-4.x",
    };
  }
  if (mode === "high-quality") {
    return Object.fromEntries(
      ROLE_ORDER.map((role) => [role, "claude-opus-4.x"]),
    );
  }
  return undefined;
}

function inferCrewPreset(roleModels: Record<string, string>): string {
  const hasRoleModels = ROLE_ORDER.some((role) => Boolean(roleModels[role]));
  if (!hasRoleModels) return "";
  for (const preset of CREW_PRESETS) {
    const presetModels = presetRoleModels(preset.id);
    if (
      presetModels &&
      ROLE_ORDER.every((role) => roleModels[role] === presetModels[role])
    ) {
      return preset.id;
    }
  }
  return "custom";
}

type SettingsSectionId =
  "credentials" | "crew" | "usage" | "activity" | "about";
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
  const [labMode, setLabMode] = useState("all-claude");
  const [paneRuntime, setPaneRuntime] = useState("claude");
  const [codexSearch, setCodexSearch] = useState(true);
  const [codexEffort, setCodexEffort] = useState("medium");
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
      ROLE_ORDER.forEach((role) => {
        const model = asString(response.role_models?.[role]?.model);
        if (model) models[role] = model;
      });
      setRoleModels(models);
      setLabMode(
        normalizeCrewPreset(
          asString(response.model_lab_matrix?.value) || "all-claude",
        ),
      );
      const runtime = asString(response.runtime?.value).toLowerCase();
      setPaneRuntime(runtime === "codex" ? "codex" : "claude");
      setCodexSearch(response.codex?.search !== false);
      setCodexEffort(asString(response.codex?.effort) || "medium");
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

  function applyCrewPreset(mode: string) {
    setLabMode(mode);
    const presetModels = presetRoleModels(mode);
    if (presetModels) setRoleModels(presetModels);
    if (mode === "all-codex") setPaneRuntime("codex");
    if (mode === "all-claude") setPaneRuntime("claude");
  }

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const save = useCallback(async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      const res = await saveSettings(roleModels, apiKeys, paneRuntime, {
        search: codexSearch,
        effort: codexEffort,
      });
      if (res.ok) {
        const n = res.written_keys?.length || 0;
        const runtimeMsg = res.applied_runtime
          ? `, runtime default ${res.applied_runtime}`
          : "";
        setSaveMsg(
          `Saved. Models applied${runtimeMsg}${n ? `, ${n} key(s) stored` : ""}. Restart the cockpit to apply to running panes.`,
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
  }, [roleModels, apiKeys, paneRuntime, codexSearch, codexEffort, refresh]);
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
                <CredentialsPane
                  apiKeys={apiKeys}
                  onSave={save}
                  saving={saving}
                  setApiKeys={setApiKeys}
                />
              )}
              {activeSection === "crew" && (
                <DefaultCrewPane
                  applyCrewPreset={applyCrewPreset}
                  labMode={labMode}
                  onRoleModelChange={(role, value) => {
                    setRoleModels((prev) => ({ ...prev, [role]: value }));
                    setLabMode("custom");
                  }}
                  onRuntimeChange={setPaneRuntime}
                  paneRuntime={paneRuntime}
                  codexSearch={codexSearch}
                  onCodexSearchChange={setCodexSearch}
                  codexEffort={codexEffort}
                  onCodexEffortChange={setCodexEffort}
                  roleModels={roleModels}
                  settings={settings}
                />
              )}
              {activeSection === "usage" && <UsageLimitsPane usage={usage} />}
              {activeSection === "activity" && (
                <ActivityPane sprints={sprints} />
              )}
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
                    (activeSection === "crew" &&
                    settings?.runtime?.launch_supported !== true
                      ? "Writes model defaults and the stored runtime value. This checkout does not launch panes from the runtime value yet."
                      : "Writes model/runtime defaults to the runtime config and API keys to local secrets. Restart the cockpit to apply to running panes.")}
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
        Runtime source: {settings?.source || "status-server"}. Saves update the
        local config and local secrets only; restart the cockpit to apply
        changes to running panes.
      </p>
    </div>
  );
}

function CredentialsPane({
  apiKeys,
  onSave,
  saving,
  setApiKeys,
}: {
  apiKeys: Record<string, string>;
  onSave: () => Promise<void>;
  saving: boolean;
  setApiKeys: (
    next: (prev: Record<string, string>) => Record<string, string>,
  ) => void;
}) {
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  return (
    <SettingsSection
      title="Credentials"
      detail="local secrets"
      description="Provider keys are stored only on this machine. Leave a row blank to keep its existing key; use row Save for one key or Save configuration for all edited keys."
    >
      <div className="settings-row-list">
        {API_PROVIDERS.map((provider) => {
          const value = apiKeys[provider.id] || "";
          const visible = Boolean(visibleKeys[provider.id]);
          const edited = Boolean(value);
          return (
            <div className="settings-data-row credential-row" key={provider.id}>
              <div className="settings-row-main">
                <strong>{provider.label}</strong>
                <span>{provider.hint}</span>
              </div>
              <div className="credential-input-shell">
                <input
                  type={visible ? "text" : "password"}
                  className="key-input"
                  aria-label={`${provider.label} API key`}
                  placeholder="Leave blank to keep existing"
                  autoComplete="off"
                  value={value}
                  onChange={(event) =>
                    setApiKeys((prev) => ({
                      ...prev,
                      [provider.id]: event.target.value,
                    }))
                  }
                />
                <button
                  type="button"
                  className="credential-icon-button"
                  aria-label={`${visible ? "Hide" : "Show"} ${provider.label} key`}
                  disabled={!value}
                  title={visible ? "Hide key" : "Show key"}
                  onClick={() =>
                    setVisibleKeys((prev) => ({
                      ...prev,
                      [provider.id]: !prev[provider.id],
                    }))
                  }
                >
                  {visible ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
                <button
                  type="button"
                  className="credential-save-button"
                  disabled={!edited || saving}
                  title={
                    edited
                      ? `Save ${provider.label} key to local secrets`
                      : "Enter a key to enable row save"
                  }
                  onClick={() => void onSave()}
                >
                  <Save size={14} aria-hidden="true" />
                  <span>{saving ? "Saving" : "Save"}</span>
                </button>
              </div>
              <span
                className={`settings-status-pill ${edited ? "is-edited" : ""}`}
              >
                {edited ? "unsaved key" : "unchanged"}
              </span>
            </div>
          );
        })}
      </div>
    </SettingsSection>
  );
}

function DefaultCrewPane({
  applyCrewPreset,
  labMode,
  onRoleModelChange,
  onRuntimeChange,
  paneRuntime,
  codexSearch,
  onCodexSearchChange,
  codexEffort,
  onCodexEffortChange,
  roleModels,
  settings,
}: {
  applyCrewPreset: (mode: string) => void;
  labMode: string;
  onRoleModelChange: (role: string, value: string) => void;
  onRuntimeChange: (runtime: string) => void;
  paneRuntime: string;
  codexSearch: boolean;
  onCodexSearchChange: (value: boolean) => void;
  codexEffort: string;
  onCodexEffortChange: (value: string) => void;
  roleModels: Record<string, string>;
  settings?: SettingsPayload;
}) {
  const hasRoleModels = ROLE_ORDER.some((role) => Boolean(roleModels[role]));
  const runtimeLaunchSupported = settings?.runtime?.launch_supported === true;
  const activePreset = hasRoleModels
    ? inferCrewPreset(roleModels) || normalizeCrewPreset(labMode)
    : "";
  const activePresetHint =
    CREW_PRESETS.find((preset) => preset.id === activePreset)?.hint ||
    "Runtime model defaults";

  return (
    <SettingsSection
      title="Default crew"
      detail={hasRoleModels ? activePreset : "unavailable"}
      description="Cockpit restart defaults for PM, Planner, Builder, and Evaluator. Save persists these defaults to the local runtime config; the main-page crew picker remains a preview."
    >
      <div className="settings-runtime-panel">
        <div className="settings-runtime-head">
          <div>
            <span>Launch runtime</span>
            <strong>
              {paneRuntime === "codex" ? "Codex CLI" : "Claude Code"}
            </strong>
          </div>
          <span
            className={`settings-status-pill ${runtimeLaunchSupported ? "is-ok" : ""}`}
          >
            {runtimeLaunchSupported
              ? "restart applies"
              : "launch wiring pending"}
          </span>
        </div>
        <div
          className="segmented settings-runtime-segmented"
          role="group"
          aria-label="Launch runtime"
          aria-disabled={!runtimeLaunchSupported}
        >
          {RUNTIME_OPTIONS.map((runtime) => (
            <button
              key={runtime.id}
              type="button"
              className={`segmented-option ${paneRuntime === runtime.id ? "is-active" : ""}`}
              aria-pressed={paneRuntime === runtime.id}
              disabled={!runtimeLaunchSupported}
              title={runtime.hint}
              onClick={() => onRuntimeChange(runtime.id)}
            >
              {runtime.label}
            </button>
          ))}
        </div>
        <p className="settings-runtime-note">
          {runtimeLaunchSupported
            ? "Saved runtime defaults apply after restarting the cockpit. Codex uses its configured operator pool; Claude model defaults stay below."
            : settings?.runtime?.note ||
              "The runtime default is stored in config, but this checkout does not yet launch panes from that field."}
        </p>
        {paneRuntime === "codex" && (
          <div className="settings-codex-options">
            <label className="settings-codex-toggle">
              <input
                type="checkbox"
                checked={codexSearch}
                disabled={!runtimeLaunchSupported}
                onChange={(e) => onCodexSearchChange(e.target.checked)}
              />
              <span>
                Web search (<code>--search</code>) — required for research runs
              </span>
            </label>
            <label className="settings-codex-effort">
              <span>Reasoning effort</span>
              <select
                value={codexEffort}
                disabled={!runtimeLaunchSupported}
                onChange={(e) => onCodexEffortChange(e.target.value)}
              >
                {["minimal", "low", "medium", "high", "xhigh"].map((eff) => (
                  <option key={eff} value={eff}>
                    {eff}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </div>
      {!hasRoleModels && (
        <SettingsEmptyState
          title="Model defaults unavailable"
          detail="No role_models were returned by /settings. The dropdowns stay unavailable until runtime model defaults exist."
        />
      )}
      <div className="settings-preset-note">
        <span>Preset</span>
        <strong>{activePresetHint}</strong>
      </div>
      <div
        className="segmented settings-segmented"
        role="group"
        aria-label="Crew preset"
      >
        {CREW_PRESETS.map((mode) => (
          <button
            key={mode.id}
            type="button"
            className={`segmented-option ${activePreset === mode.id ? "is-active" : ""}`}
            aria-pressed={activePreset === mode.id}
            disabled={!hasRoleModels}
            title={mode.hint}
            onClick={() => applyCrewPreset(mode.id)}
          >
            {mode.label}
          </button>
        ))}
      </div>
      <div className="agent-config-list settings-agent-list">
        {ROLE_ORDER.map((role) => {
          const model = roleModels[role] || "";
          const savedModel = asString(settings?.role_models?.[role]?.model);
          const source = asString(settings?.role_models?.[role]?.source);
          const changed = Boolean(model && savedModel && model !== savedModel);
          return (
            <div className="agent-config-row settings-agent-row" key={role}>
              <div className="agent-config-id">
                <strong>{ROLE_META[role].title.split(" ")[0]}</strong>
                <span>
                  {changed
                    ? "edited, not saved"
                    : source
                      ? `source: ${source}`
                      : ROLE_META[role].subtitle}
                </span>
              </div>
              <div className="model-select">
                <select
                  aria-label={`${ROLE_META[role].title} model`}
                  value={model}
                  disabled={!hasRoleModels}
                  onChange={(event) =>
                    onRoleModelChange(role, event.target.value)
                  }
                >
                  {!model && <option value="">Unavailable</option>}
                  {MODEL_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} aria-hidden="true" />
              </div>
              <span
                className={`settings-status-pill ${changed ? "is-edited" : ""}`}
              >
                {changed ? "edited" : "default"}
              </span>
            </div>
          );
        })}
      </div>
    </SettingsSection>
  );
}

function UsageLimitsPane({ usage }: { usage?: UsagePayload }) {
  const models = usage?.models || [];
  const hasUsageRows = models.length > 0;
  return (
    <SettingsSection
      title="Usage & limits"
      detail={usage?.total_used_tokens_label || "unavailable"}
      description="Account-wide model-day token usage from the selected runtime when that provider exposes it. Per-run evidence stays on the session view."
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
      {usage && !hasUsageRows && (
        <SettingsEmptyState
          title={
            usage.availability === "unavailable"
              ? `Usage unavailable for ${usage.runtime === "codex" ? "Codex" : "the selected runtime"}`
              : "No usage rows in this harness"
          }
          detail={
            usage.label ||
            "The /usage endpoint is reachable, but it has no model-day rows for the current harness data."
          }
        />
      )}
      <div className="usage-models settings-usage-models">
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
  // Keep the selected day valid as `days` changes: keep the current pick if it still exists,
  // otherwise fall back to the latest. Depends only on `days` (the functional update reads the
  // current value), so it doesn't re-run on every selection change.
  useEffect(() => {
    if (days.length === 0) return;
    setSelectedDay((cur) =>
      cur && days.some((day) => day.date === cur)
        ? cur
        : days[days.length - 1].date,
    );
  }, [days]);
  const selected = days.find((day) => day.date === selectedDay);
  const selectedSprints = selected?.sprints || [];
  const sevenDayTotal = days.slice(-7).reduce((sum, day) => sum + day.count, 0);
  const active = sprints.filter(
    (sprint) => sessionTone(sprint) === "working",
  ).length;
  const attention = sprints.filter(
    (sprint) => sessionTone(sprint) === "blocked",
  ).length;
  const done = sprints.filter(
    (sprint) => sessionTone(sprint) === "complete",
  ).length;
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
            {busiest.date
              ? `${busiest.date} (${busiest.count})`
              : "not available"}
          </strong>
        </span>
        <span>
          Selected:{" "}
          <strong>
            {selected
              ? `${selected.date} (${selected.count})`
              : "not available"}
          </strong>
        </span>
      </div>
      <div className="settings-row-list activity-session-list">
        {selectedSprints.length === 0 && (
          <div className="activity-empty-row">
            No sessions on the selected day.
          </div>
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
                asString(sprint.created_at) ||
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
        <FactRow
          label="Settings source"
          value={settings?.source || "not exposed"}
        />
        <FactRow
          label="Settings generated"
          value={settings?.generated_at || "not exposed"}
        />
        <FactRow
          label="Settings writes"
          value={settings?.write_supported ? "supported" : "not advertised"}
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
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function start() {
    const clean = task.trim();
    if ((!clean && files.length === 0) || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await submitIntake(clean, files);
      if (!response.ok || !response.sprint_id) {
        throw new Error(intakeErrorMessage(response));
      }
      setTask("");
      setFiles([]);
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
        <h1 id="home-task-heading">What do you want done?</h1>
        <p id="home-task-instructions" className="home-sub">
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
            aria-labelledby="home-task-heading"
            aria-describedby="home-task-instructions"
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
          <IntakeAttachments
            files={files}
            onChange={setFiles}
            onError={setError}
            disabled={submitting}
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
              disabled={(!task.trim() && files.length === 0) || submitting}
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
          Starts a real intake via the existing CLI <kbd>Ctrl/Cmd + Enter</kbd>
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
