(function () {
  "use strict";

  const roles = [
    { key: "PM", label: "PM Product", aliases: ["pm", "product"] },
    { key: "Planner", label: "Planner", aliases: ["planner", "plan"] },
    { key: "Builder", label: "Builder", aliases: ["builder", "build"] },
    { key: "Evaluator", label: "Evaluator", aliases: ["evaluator", "eval", "review"] },
  ];
  const phases = [
    { key: "spec", label: "Spec" },
    { key: "prd_ready", label: "PRD ready" },
    { key: "planning_complete", label: "Planning complete" },
    { key: "build_complete", label: "Build complete" },
  ];
  const state = {
    sprintId: new URLSearchParams(location.search).get("sprint_id") || "",
    events: new Map(),
    eventSource: null,
    refreshTimer: null,
    userSelectedSprint: Boolean(new URLSearchParams(location.search).get("sprint_id")),
    lastStatus: null,
    lastDashboard: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return String(value == null || value === "" ? "N/A" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function short(value, max) {
    const text = String(value || "N/A").replace(/\s+/g, " ").trim();
    return text.length > max ? `${text.slice(0, max - 1).trim()}...` : text;
  }

  async function jsonFetch(url, options) {
    const extraHeaders = (options && options.headers) || {};
    const res = await fetch(url, {
      cache: "no-store",
      ...options,
      headers: { Accept: "application/json", ...extraHeaders },
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.error || body.status || `HTTP ${res.status}`);
    }
    return body;
  }

  function statusClass(value) {
    return String(value || "unknown").toLowerCase().replace(/[^a-z0-9_-]+/g, "_");
  }

  function eventPayload(event) {
    return (event && typeof event.payload === "object" && event.payload)
      || (event && typeof event.data === "object" && event.data)
      || {};
  }

  function eventType(event) {
    return String((event && (event.type || event.event || event.event_type)) || "event");
  }

  function eventTime(event) {
    return String((event && (event.ts || event.timestamp || event.time)) || "");
  }

  function eventKey(event) {
    return [
      eventTime(event),
      event.sprint_id || "",
      eventType(event),
      JSON.stringify(eventPayload(event)),
    ].join("|");
  }

  function eventCategory(event) {
    const type = eventType(event).toLowerCase();
    const payload = eventPayload(event);
    const text = `${type} ${JSON.stringify(payload)}`.toLowerCase();
    if (text.includes("error") || text.includes("failed")) return "error";
    if (text.includes("gate") || text.includes("blocked") || text.includes("no_matching_worker")) return "gate";
    if (text.includes("dispatch") || text.includes("routing") || text.includes("lease")) return "dispatch";
    if (text.includes("model") || text.includes("session_started") || text.includes("session_ended")) return "model";
    if (text.includes("phase") || text.includes("status") || text.includes("planning_complete") || text.includes("prd_ready")) return "phase";
    if (text.includes("intake") || text.includes("sprint created")) return "milestone";
    if (text.includes("artifact") || text.includes("deliverable") || text.includes("report")) return "milestone";
    return "event";
  }

  function eventRole(event) {
    const payload = eventPayload(event);
    const raw = [
      event.actor,
      event.role,
      payload.actor,
      payload.role,
      payload.persona,
      payload.target_role,
      payload.logical_operator,
      payload.target_pane,
      payload.pane,
    ].filter(Boolean).join(" ").toLowerCase();
    if (raw.includes(":0.0") || raw.includes("pm") || raw.includes("product")) return "PM";
    if (raw.includes(":0.1") || raw.includes("planner") || raw.includes("plan")) return "Planner";
    if (raw.includes(":0.2") || raw.includes("builder") || raw.includes("build")) return "Builder";
    if (raw.includes(":0.3") || raw.includes("evaluator") || raw.includes("eval") || raw.includes("review")) return "Evaluator";
    return "";
  }

  function humanType(type) {
    const clean = String(type || "event").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
    return clean.charAt(0).toUpperCase() + clean.slice(1);
  }

  function eventLine(event) {
    const payload = eventPayload(event);
    const type = eventType(event);
    const category = eventCategory(event);
    const role = eventRole(event);
    const actor = role || event.actor || event.role || payload.actor || payload.persona || "runtime";
    const bits = [];
    for (const key of ["message", "status", "phase", "node_id", "target_pane", "decision", "reason", "blocked_reason"]) {
      if (payload[key]) bits.push(`${key}: ${payload[key]}`);
    }
    if (event.sprint_id) bits.push(`sprint: ${event.sprint_id}`);
    if (!bits.length) bits.push(short(JSON.stringify(payload), 180));
    return {
      title: `${actor} / ${humanType(type)}`,
      detail: bits.join(" / "),
      category,
      role,
      node: payload.node_id || event.node_id || "",
      time: eventTime(event),
    };
  }

  function setSprint(sid, options) {
    const opts = options || {};
    if (!sid || sid === state.sprintId) return;
    state.sprintId = sid;
    if (opts.user) state.userSelectedSprint = true;
    state.events.clear();
    renderEvents();
    const next = `${location.pathname}?sprint_id=${encodeURIComponent(sid)}`;
    history.replaceState(null, "", next);
    connectEvents();
  }

  function formatTime(value) {
    if (!value) return "N/A";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return short(value, 24);
    return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function formatBucket(value) {
    if (!value) return "Undated";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "Undated";
    return parsed.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function latestEventForRole(roleKey) {
    const events = Array.from(state.events.values()).sort((a, b) => String(eventTime(b)).localeCompare(String(eventTime(a))));
    return events.find((event) => eventRole(event) === roleKey) || null;
  }

  function agentDisplayState(runtime, lastEvent) {
    const normalized = statusClass(runtime);
    const category = lastEvent ? eventCategory(lastEvent) : "";
    if (["blocked", "gate_blocked", "prompt_residue", "error", "failed"].includes(normalized)) return normalized;
    if (["gate", "error"].includes(category)) return category === "gate" ? "blocked" : "error";
    if (["active", "running"].includes(normalized)) return "working";
    if (["dispatch", "model", "phase", "milestone"].includes(category)) return normalized === "idle" ? "observing" : normalized;
    return normalized || "unknown";
  }

  function renderAgentTimeline(displayState) {
    const st = statusClass(displayState);
    const idleOn = ["idle", "ready", "unknown", "observing"].includes(st);
    const workingOn = ["working", "active", "running", "dispatch", "model"].includes(st);
    const blockedOn = ["blocked", "gate", "gate_blocked", "prompt_residue", "error", "failed"].includes(st);
    return `<div class="agent-timeline">
      <span class="${idleOn ? "on" : ""}">idle</span>
      <span class="${workingOn ? "on" : ""}">working</span>
      <span class="${blockedOn ? "on" : ""}">blocked</span>
    </div>`;
  }

  function renderAgents(status) {
    const main = (status && status.main_screen && status.main_screen.panes) || [];
    const byRole = new Map(main.map((pane) => [pane.role, pane]));
    $("agents").innerHTML = roles.map((role) => {
      const pane = byRole.get(role.key) || {};
      const runtime = pane.runtime_state || pane.state || "unknown";
      const artifact = pane.artifact || {};
      const call = pane.model_call || {};
      const assignment = pane.assignment || (pane.assignment_meta && pane.assignment_meta.sprint_id) || "";
      const lastEvent = latestEventForRole(role.key);
      const line = lastEvent ? eventLine(lastEvent) : null;
      const displayState = agentDisplayState(runtime, lastEvent);
      const model = call.model || call.model_flag || pane.title || "not observed";
      const activity = line
        ? `${line.title}: ${line.detail}`
        : (runtime === "idle" ? "Waiting at prompt." : `Runtime state: ${runtime}`);
      return `<article class="agent-card">
        <div>
          <strong>${esc(role.label)}</strong>
          <div class="sub">${esc(pane.target || "not attached")}</div>
        </div>
        <span class="state-pill ${esc(statusClass(displayState))}">${esc(displayState)}</span>
        ${renderAgentTimeline(displayState)}
        <div class="agent-detail">
          <b>Current activity</b>
          <div class="agent-activity">${esc(short(activity, 160))}</div>
        </div>
        <div class="sub">model: ${esc(short(model, 72))}</div>
        <div class="sub">sprint: ${esc(short(assignment || state.sprintId || "unassigned", 56))}</div>
        <div class="sub">artifact: ${esc(artifact.state || "N/A")} / last event: ${esc(line ? formatTime(line.time) : "N/A")}</div>
      </article>`;
    }).join("");
    $("agent-refresh").textContent = new Date().toLocaleTimeString();
  }

  function renderTopline(status, dashboard) {
    const sprint = (status && status.current_sprint) || {};
    const data = (dashboard && dashboard.data) || {};
    const progress = data.progress || {};
    const sid = data.focus_sprint_id || sprint.sprint_id || state.sprintId || "";
    if (sid && !state.userSelectedSprint) setSprint(sid);
    $("current-sprint").textContent = sid || "N/A";
    $("current-phase").textContent = data.phase || sprint.phase || "N/A";
    $("node-total").textContent = progress.total_nodes == null ? "0" : progress.total_nodes;
    $("blocked-total").textContent = progress.blocked_nodes == null ? "0" : progress.blocked_nodes;
  }

  function phaseRank(phase) {
    const normalized = String(phase || "").toLowerCase();
    let rank = phases.findIndex((item) => normalized.includes(item.key));
    if (rank >= 0) return rank;
    if (normalized.includes("prd")) return 1;
    if (normalized.includes("planning")) return 2;
    if (normalized.includes("build")) return 3;
    return -1;
  }

  function renderStall(dashboard) {
    const stall = ((dashboard && dashboard.data) || {}).stall || {};
    const target = $("stall-callout");
    const severity = statusClass(stall.severity || (stall.is_stalled ? "warn" : "ok"));
    target.className = `stall-callout ${severity}`;
    const reasons = Array.isArray(stall.reasons) && stall.reasons.length
      ? ` Reasons: ${stall.reasons.slice(0, 4).join(", ")}.`
      : "";
    target.innerHTML = `<strong>${esc(stall.title || "No explicit stall reported")}</strong>
      <p>${esc((stall.detail || "Waiting for current sprint evidence.") + reasons)}</p>`;
  }

  function renderNodeGraph(nodes) {
    $("node-graph").innerHTML = nodes.length ? nodes.map((node) => {
      const status = node.status || "pending";
      const deps = Array.isArray(node.depends_on) && node.depends_on.length ? node.depends_on : ["root"];
      const missing = Array.isArray(node.missing_capabilities) && node.missing_capabilities.length
        ? `missing: ${node.missing_capabilities.join(", ")}`
        : "";
      const route = node.route_decision || node.decision || "N/A";
      const blocker = node.blocked_reason || missing || "";
      return `<article class="node-card ${esc(statusClass(status))}">
        <div class="node-head">
          <strong>${esc(node.id || "N/A")}</strong>
          <span class="state-pill ${esc(statusClass(status))}">${esc(status)}</span>
        </div>
        <div class="node-goal">${esc(short(node.goal || "No node goal recorded.", 140))}</div>
        <div class="node-deps">${deps.map((dep) => `<span>after ${esc(dep)}</span>`).join("")}</div>
        <div class="node-meta">route: ${esc(route)} / pane: ${esc(node.target_pane || "unassigned")}</div>
        ${blocker ? `<div class="node-meta">blocker: ${esc(short(blocker, 130))}</div>` : ""}
      </article>`;
    }).join("") : '<div class="empty">No DAG nodes found for this sprint.</div>';
  }

  function renderDag(dashboard) {
    const data = (dashboard && dashboard.data) || {};
    const progress = data.progress || {};
    const dag = data.dag || {};
    const nodes = Array.isArray(dag.nodes) ? dag.nodes : [];
    const rank = phaseRank(data.phase || data.sprint_status || "");
    $("phase-track").innerHTML = phases.map((phase, index) => {
      const cls = index === rank ? "current" : (rank > index ? "passed" : "");
      return `<div class="phase-step ${cls}">
        <span>${esc(phase.label)}</span>
        <strong>${index === rank ? "current" : (rank > index ? "observed" : "pending")}</strong>
      </div>`;
    }).join("");

    const active = nodes.find((node) => ["active", "running", "dispatched"].includes(statusClass(node.status)))
      || nodes.find((node) => ["blocked", "gate_blocked", "failed"].includes(statusClass(node.status)))
      || nodes.find((node) => statusClass(node.status) === "pending")
      || {};
    const counts = Object.entries(progress.status_counts || {})
      .map(([key, value]) => `${key}:${value}`)
      .join(" / ");
    $("active-node").textContent = active.id || "N/A";
    $("status-counts").textContent = counts || "N/A";
    renderStall(dashboard);
    renderNodeGraph(nodes);

    const blocked = nodes.filter((node) => {
      const st = statusClass(node.status);
      return st === "blocked" || st === "gate_blocked" || st === "failed" || node.blocked_reason || (node.missing_capabilities || []).length;
    });
    $("blocked-nodes").innerHTML = blocked.length ? blocked.map((node) => {
      const reason = node.blocked_reason
        || ((node.missing_capabilities || []).length ? `missing capabilities: ${(node.missing_capabilities || []).join(", ")}` : "blocked");
      return `<div class="blocked-item">
        <strong>${esc(node.id || "N/A")} / ${esc(node.status || "blocked")}</strong>
        <p>${esc(short(reason, 220))}</p>
      </div>`;
    }).join("") : '<div class="empty">No blocked nodes reported.</div>';
    $("dashboard-refresh").textContent = new Date().toLocaleTimeString();
  }

  function addEvent(event, options) {
    if (!event || typeof event !== "object") return;
    const key = eventKey(event);
    state.events.set(key, event);
    while (state.events.size > 220) {
      state.events.delete(state.events.keys().next().value);
    }
    renderEvents(Boolean(options && options.live));
    if (state.lastStatus) renderAgents(state.lastStatus);
  }

  function renderEvents(fromLive) {
    const stream = $("activity-stream");
    const events = Array.from(state.events.values()).sort((a, b) => String(eventTime(b)).localeCompare(String(eventTime(a))));
    let lastBucket = "";
    const html = [];
    for (const event of events) {
      const line = eventLine(event);
      const bucket = formatBucket(line.time);
      if (bucket !== lastBucket) {
        html.push(`<div class="event-date">${esc(bucket)}</div>`);
        lastBucket = bucket;
      }
      const meta = [
        `<span class="event-kind ${esc(line.category)}">${esc(line.category)}</span>`,
        line.role ? `<span class="event-kind">${esc(line.role)}</span>` : "",
        line.node ? `<span class="event-kind">node ${esc(line.node)}</span>` : "",
      ].filter(Boolean).join("");
      html.push(`<article class="event-row">
        <div class="event-head">
          <strong>${esc(short(line.title, 104))}</strong>
          <time>${esc(formatTime(line.time))}</time>
        </div>
        <div class="event-meta">${meta}</div>
        <p>${esc(short(line.detail, 260))}</p>
      </article>`);
    }
    stream.innerHTML = html.length ? html.join("") : '<div class="empty">No events observed yet.</div>';
    if (fromLive) stream.scrollTop = 0;
  }

  async function loadEventsSnapshot() {
    const query = state.sprintId ? `?sprint_id=${encodeURIComponent(state.sprintId)}&limit=120` : "?limit=120";
    const events = await jsonFetch(`/events${query}`);
    if (Array.isArray(events)) events.forEach((event) => addEvent(event));
  }

  function connectEvents() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    const query = new URLSearchParams({ stream: "1", limit: "120" });
    if (state.sprintId) query.set("sprint_id", state.sprintId);
    if (!window.EventSource) {
      $("stream-state").textContent = "polling";
      return;
    }
    const source = new EventSource(`/events?${query.toString()}`);
    state.eventSource = source;
    source.addEventListener("open", () => { $("stream-state").textContent = "live"; });
    source.addEventListener("error", () => { $("stream-state").textContent = "reconnecting"; });
    source.addEventListener("solar-event", (message) => {
      try {
        addEvent(JSON.parse(message.data), { live: true });
      } catch (_) {
        return;
      }
    });
  }

  async function refreshSprints() {
    const payload = await jsonFetch("/sprints?limit=120");
    const sprints = (((payload || {}).data || {}).sprints) || [];
    const select = $("sprint-select");
    state.sprints = sprints;
    if (!state.sprintId) {
      const first = sprints[0] || {};
      if (first.sprint_id) setSprint(first.sprint_id);
    }
    select.innerHTML = sprints.length ? sprints.map((row) => {
      const bits = [row.status || "unknown", row.phase || "no_phase", `${row.node_count || 0} nodes`].join(" / ");
      return `<option value="${esc(row.sprint_id)}"${row.sprint_id === state.sprintId ? " selected" : ""}>
        ${esc(short(row.title || row.sprint_id, 72))} (${esc(bits)})
      </option>`;
    }).join("") : '<option value="">No sprints found</option>';
  }

  async function refreshStatusAndDag() {
    const sprintQuery = state.sprintId ? `?sprint_id=${encodeURIComponent(state.sprintId)}` : "";
    const [status, dashboard] = await Promise.all([
      jsonFetch(`/status${sprintQuery}`),
      jsonFetch(`/orchestration/dashboard${sprintQuery}`),
    ]);
    state.lastStatus = status;
    state.lastDashboard = dashboard;
    renderTopline(status, dashboard);
    renderDag(dashboard);
    renderAgents(status);
  }

  async function refreshDeliverables() {
    if (!state.sprintId) {
      $("deliverables").innerHTML = '<div class="empty">No sprint selected.</div>';
      $("deliverable-count").textContent = "0 files";
      return;
    }
    const payload = await jsonFetch(`/sprints/${encodeURIComponent(state.sprintId)}/deliverables`);
    const items = Array.isArray(payload.items) ? payload.items : [];
    const sorted = items.slice().sort((a, b) => {
      const ah = ["html", "htm"].includes(String(a.kind || "").toLowerCase()) ? 0 : 1;
      const bh = ["html", "htm"].includes(String(b.kind || "").toLowerCase()) ? 0 : 1;
      return ah - bh || Number(b.mtime || 0) - Number(a.mtime || 0);
    });
    $("deliverable-count").textContent = `${items.length} files`;
    $("deliverables").innerHTML = sorted.length ? sorted.map((item, index) => {
      const featured = index === 0 && ["html", "htm"].includes(String(item.kind || "").toLowerCase());
      return `<div class="deliverable-item ${featured ? "featured" : ""}">
        <a href="${esc(item.view_url)}" target="_blank" rel="noreferrer">${featured ? "Open report: " : ""}${esc(item.name)}</a>
        <span>${esc(item.kind)} / ${esc(item.size)} bytes</span>
      </div>`;
    }).join("") : '<div class="empty">No deliverables found for this sprint.</div>';
  }

  async function refreshUsage() {
    const payload = await jsonFetch("/usage");
    $("usage-total").textContent = `${payload.total_used_tokens_label || 0} tok`;
    $("usage-label").textContent = payload.label || "source: Claude log scan / quota-footer; scope: model-day estimate; not per-sprint or per-agent";
    const rows = Array.isArray(payload.models) ? payload.models : [];
    $("usage-models").innerHTML = rows.length ? rows.map((row) => (
      `<div class="usage-row">
        <strong>${esc(row.model_key)}</strong>
        <span>${esc(row.used_tokens_label)} tok</span>
      </div>`
    )).join("") : '<div class="empty">No quota-footer cache for today.</div>';
    $("usage-refresh").textContent = new Date().toLocaleTimeString();
  }

  async function refreshAll() {
    try {
      await refreshSprints();
    } catch (error) {
      $("sprint-select").innerHTML = `<option value="">Sprint list error: ${esc(error.message)}</option>`;
    }
    try {
      await refreshStatusAndDag();
    } catch (error) {
      $("agent-refresh").textContent = `error: ${error.message}`;
      $("dashboard-refresh").textContent = `error: ${error.message}`;
    }
    try {
      await loadEventsSnapshot();
    } catch (_) {
      $("stream-state").textContent = "snapshot unavailable";
    }
    try {
      await refreshDeliverables();
    } catch (error) {
      $("deliverables").innerHTML = `<div class="empty">${esc(error.message)}</div>`;
    }
    try {
      await refreshUsage();
    } catch (error) {
      $("usage-refresh").textContent = `error: ${error.message}`;
    }
  }

  async function submitIntake(event) {
    event.preventDefault();
    const input = $("task-input");
    const button = event.target.querySelector("button");
    const task = input.value.trim();
    if (!task) return;
    $("intake-state").textContent = "Submitting";
    button.disabled = true;
    try {
      const payload = await jsonFetch("/intake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task }),
      });
      if (payload.sprint_id) setSprint(payload.sprint_id, { user: true });
      $("intake-state").textContent = payload.sprint_id ? `Created ${payload.sprint_id}` : "Submitted";
      input.value = "";
      await refreshAll();
    } catch (error) {
      $("intake-state").textContent = `Error: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("intake-form").addEventListener("submit", submitIntake);
    $("sprint-select").addEventListener("change", (event) => {
      const sid = event.target.value;
      if (!sid) return;
      setSprint(sid, { user: true });
      refreshAll();
    });
    renderAgents({});
    renderEvents();
    connectEvents();
    refreshAll();
    state.refreshTimer = setInterval(refreshAll, 5000);
  });
})();
