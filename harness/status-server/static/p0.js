(function () {
  "use strict";

  const roles = [
    { key: "PM", label: "PM 产品经理" },
    { key: "Planner", label: "Planner 规划者" },
    { key: "Builder", label: "Builder 主建设者" },
    { key: "Evaluator", label: "Evaluator 审判官" },
  ];
  const phases = ["spec", "prd_ready", "planning_complete", "build_complete"];
  const state = {
    sprintId: new URLSearchParams(location.search).get("sprint_id") || "",
    events: new Map(),
    eventSource: null,
    refreshTimer: null,
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

  function eventKey(event) {
    return [
      event.ts || event.timestamp || event.time || "",
      event.sprint_id || "",
      event.type || event.event || event.event_type || "",
      JSON.stringify(event.payload || event.data || {}),
    ].join("|");
  }

  function statusClass(value) {
    return String(value || "unknown").toLowerCase().replace(/[^a-z0-9_-]+/g, "_");
  }

  function setSprint(sid) {
    if (!sid || sid === state.sprintId) return;
    state.sprintId = sid;
    const next = `${location.pathname}?sprint_id=${encodeURIComponent(sid)}`;
    history.replaceState(null, "", next);
    connectEvents();
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
      return `<article class="agent-card">
        <div>
          <strong>${esc(role.label)}</strong>
          <div class="sub">${esc(pane.target || "not attached")}</div>
        </div>
        <span class="state-pill ${esc(statusClass(runtime))}">${esc(runtime)}</span>
        <div class="sub">sprint: ${esc(short(assignment || state.sprintId || "unassigned", 48))}</div>
        <div class="sub">artifact: ${esc(artifact.state || "N/A")}</div>
        <div class="sub">model event: ${esc(call.status || "not observed")}</div>
      </article>`;
    }).join("");
    $("agent-refresh").textContent = new Date().toLocaleTimeString();
  }

  function renderTopline(status, dashboard) {
    const sprint = (status && status.current_sprint) || {};
    const data = (dashboard && dashboard.data) || {};
    const progress = data.progress || {};
    const sid = data.focus_sprint_id || sprint.sprint_id || state.sprintId || "";
    if (sid) setSprint(sid);
    $("current-sprint").textContent = sid || "N/A";
    $("current-phase").textContent = data.phase || sprint.phase || "N/A";
    $("node-total").textContent = progress.total_nodes == null ? "0" : progress.total_nodes;
    $("blocked-total").textContent = progress.blocked_nodes == null ? "0" : progress.blocked_nodes;
  }

  function phaseRank(phase) {
    const normalized = String(phase || "").toLowerCase();
    let rank = phases.findIndex((item) => normalized.includes(item));
    if (rank >= 0) return rank;
    if (normalized.includes("prd")) return 1;
    if (normalized.includes("planning")) return 2;
    if (normalized.includes("build")) return 3;
    return -1;
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
        <span>${esc(phase)}</span>
        <strong>${index === rank ? "current" : (rank > index ? "observed" : "pending")}</strong>
      </div>`;
    }).join("");

    const active = nodes.find((node) => statusClass(node.status) === "active")
      || nodes.find((node) => ["blocked", "gate_blocked"].includes(statusClass(node.status)))
      || nodes.find((node) => statusClass(node.status) === "pending")
      || {};
    const counts = Object.entries(progress.status_counts || {})
      .map(([key, value]) => `${key}:${value}`)
      .join(" · ");
    $("active-node").textContent = active.id || "N/A";
    $("status-counts").textContent = counts || "N/A";

    const blocked = nodes.filter((node) => {
      const st = statusClass(node.status);
      return st === "blocked" || st === "gate_blocked" || node.blocked_reason || (node.missing_capabilities || []).length;
    });
    $("blocked-nodes").innerHTML = blocked.length ? blocked.map((node) => {
      const reason = node.blocked_reason
        || ((node.missing_capabilities || []).length ? `missing capabilities: ${(node.missing_capabilities || []).join(", ")}` : "blocked");
      return `<div class="blocked-item">
        <strong>${esc(node.id || "N/A")} · ${esc(node.status || "blocked")}</strong>
        <p>${esc(short(reason, 220))}</p>
      </div>`;
    }).join("") : '<div class="empty">No blocked nodes reported.</div>';
    $("dashboard-refresh").textContent = new Date().toLocaleTimeString();
  }

  function eventLine(event) {
    const payload = event.payload || event.data || {};
    const type = event.type || event.event || event.event_type || "event";
    const actor = event.actor || event.role || payload.actor || payload.persona || "runtime";
    const bits = [];
    for (const key of ["message", "status", "phase", "node_id", "target_pane", "decision", "reason"]) {
      if (payload[key]) bits.push(`${key}: ${payload[key]}`);
    }
    if (event.sprint_id) bits.push(`sprint: ${event.sprint_id}`);
    return { title: `${actor} · ${type}`, detail: bits.join(" · ") || short(JSON.stringify(payload), 180) };
  }

  function addEvent(event) {
    if (!event || typeof event !== "object") return;
    const key = eventKey(event);
    state.events.set(key, event);
    while (state.events.size > 160) {
      state.events.delete(state.events.keys().next().value);
    }
    renderEvents();
  }

  function renderEvents() {
    const events = Array.from(state.events.values()).sort((a, b) =>
      String(b.ts || b.timestamp || "").localeCompare(String(a.ts || a.timestamp || ""))
    );
    $("activity-stream").innerHTML = events.length ? events.map((event) => {
      const line = eventLine(event);
      return `<article class="event-row">
        <div class="event-head">
          <strong>${esc(short(line.title, 96))}</strong>
          <time>${esc(short(event.ts || event.timestamp || "", 32))}</time>
        </div>
        <p>${esc(short(line.detail, 220))}</p>
      </article>`;
    }).join("") : '<div class="empty">No events observed yet.</div>';
  }

  async function loadEventsSnapshot() {
    const query = state.sprintId ? `?sprint_id=${encodeURIComponent(state.sprintId)}&limit=80` : "?limit=80";
    const events = await jsonFetch(`/events${query}`);
    if (Array.isArray(events)) events.forEach(addEvent);
  }

  function connectEvents() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    const query = new URLSearchParams({ stream: "1", limit: "80" });
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
        addEvent(JSON.parse(message.data));
      } catch (_) {
        return;
      }
    });
  }

  async function refreshStatusAndDag() {
    const sprintQuery = state.sprintId ? `?sprint_id=${encodeURIComponent(state.sprintId)}` : "";
    const [status, dashboard] = await Promise.all([
      jsonFetch(`/status${sprintQuery}`),
      jsonFetch(`/orchestration/dashboard${sprintQuery}`),
    ]);
    renderAgents(status);
    renderTopline(status, dashboard);
    renderDag(dashboard);
  }

  async function refreshDeliverables() {
    if (!state.sprintId) {
      $("deliverables").innerHTML = '<div class="empty">No sprint selected.</div>';
      $("deliverable-count").textContent = "0 files";
      return;
    }
    const payload = await jsonFetch(`/sprints/${encodeURIComponent(state.sprintId)}/deliverables`);
    const items = Array.isArray(payload.items) ? payload.items : [];
    $("deliverable-count").textContent = `${items.length} files`;
    $("deliverables").innerHTML = items.length ? items.map((item) => (
      `<div class="deliverable-item">
        <a href="${esc(item.view_url)}" target="_blank" rel="noreferrer">${esc(item.name)}</a>
        <span>${esc(item.kind)} · ${esc(item.size)} bytes</span>
      </div>`
    )).join("") : '<div class="empty">No deliverables found for this sprint.</div>';
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
      if (payload.sprint_id) setSprint(payload.sprint_id);
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
    renderAgents({});
    renderEvents();
    connectEvents();
    refreshAll();
    state.refreshTimer = setInterval(refreshAll, 5000);
  });
})();
