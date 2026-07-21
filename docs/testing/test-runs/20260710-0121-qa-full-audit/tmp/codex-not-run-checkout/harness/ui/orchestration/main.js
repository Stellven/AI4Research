/* Solar orchestration Hero dashboard */
(function () {
  "use strict";

  const BASE = localStorage.getItem("ORCHESTRATION_BASE") || "/orchestration";
  const state = { sprintId: new URLSearchParams(location.search).get("sprint_id") || "" };

  function esc(value) {
    return String(value == null || value === "" ? "N/A" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function shortText(value, max) {
    const text = String(value || "N/A");
    return text.length > max ? `${text.slice(0, max - 1)}...` : text;
  }

  async function fetchDashboard() {
    const query = state.sprintId ? `?sprint_id=${encodeURIComponent(state.sprintId)}` : "";
    const response = await fetch(`${BASE}/dashboard${query}`, { cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function badge(status) {
    const normalized = String(status || "pending").toLowerCase();
    return `<span class="badge ${esc(normalized)}">${esc(normalized)}</span>`;
  }

  function renderSelect(data) {
    const select = document.getElementById("sprint-select");
    const options = data.active_sprints || [];
    if (!options.includes(data.focus_sprint_id) && data.focus_sprint_id) options.unshift(data.focus_sprint_id);
    select.innerHTML = options.length
      ? options.map((sid) => `<option value="${esc(sid)}"${sid === data.focus_sprint_id ? " selected" : ""}>${esc(shortText(sid, 96))}</option>`).join("")
      : '<option value="">N/A</option>';
    select.onchange = () => {
      state.sprintId = select.value;
      const next = state.sprintId ? `?sprint_id=${encodeURIComponent(state.sprintId)}` : location.pathname;
      history.replaceState(null, "", next);
      refresh();
    };
  }

  function renderHero(data) {
    const progress = data.progress || {};
    const resources = data.resources || {};
    document.getElementById("hero-subtitle").textContent =
      `${data.title || "N/A"} · ${data.focus_sprint_id || "N/A"} · status=${data.sprint_status || "N/A"} · phase=${data.phase || "N/A"}`;
    document.getElementById("metric-nodes").textContent = progress.total_nodes ?? "N/A";
    document.getElementById("metric-passed").textContent = progress.passed_nodes ?? "N/A";
    document.getElementById("metric-blocked").textContent = progress.blocked_nodes ?? "N/A";
    document.getElementById("metric-cost").textContent = resources.estimated_total_cost ?? "N/A";
  }

  function renderDag(data) {
    const dag = data.dag || {};
    const nodes = dag.nodes || [];
    document.getElementById("gate-summary").textContent = (dag.required_gates || []).join(" / ") || "N/A";
    document.getElementById("dag-flow").innerHTML = nodes.length ? nodes.map((node) => {
      const caps = (node.required_capabilities || []).map((cap) => `<span class="chip">${esc(cap)}</span>`).join("");
      const deps = (node.depends_on || []).join(", ") || "ROOT";
      const paneCarrier = node.pane_carrier || {};
      return `<section class="dag-node">
        <div class="node-top"><span class="node-id">${esc(node.id)}</span>${badge(node.status)}</div>
        <div class="node-goal">${esc(shortText(node.goal, 170))}</div>
        <div class="node-meta">
          <span>depends: ${esc(deps)}</span>
          <span>gate: ${esc(node.gate || "N/A")}</span>
          <span>route_decision: ${esc(node.route_decision || node.decision || "N/A")}</span>
          <span>blocked_reason: ${esc(node.blocked_reason || "N/A")}</span>
          <span>actor_id: ${esc(node.actor_id || "N/A")} · host_id: ${esc(node.host_id || "N/A")}</span>
          <span>host_type: ${esc(node.host_type || "unknown")} · lease_state: ${esc(node.lease_state || "unknown")}</span>
          <span>pane_carrier: ${esc(paneCarrier.pane_id || node.target_pane || "N/A")}</span>
          <span>cost: ${esc(node.estimated_cost ?? "N/A")}</span>
        </div>
        <div class="chips">${caps || '<span class="chip">N/A</span>'}</div>
      </section>`;
    }).join("") : '<div class="muted">No task graph nodes available.</div>';
  }

  function renderStack(targetId, rows, formatter) {
    const target = document.getElementById(targetId);
    const entries = Object.entries(rows || {});
    const max = Math.max(1, ...entries.map(([, count]) => Number(count) || 0));
    target.innerHTML = entries.length ? entries.map(([name, count]) => {
      const width = Math.max(6, Math.round(((Number(count) || 0) / max) * 100));
      return `<div class="stack-row">
        <div><strong>${esc(formatter ? formatter(name) : name)}</strong><div class="bar"><span style="width:${width}%"></span></div></div>
        <span>${esc(count)}</span>
      </div>`;
    }).join("") : '<div class="muted">N/A</div>';
  }

  function renderCapabilities(data) {
    const caps = (data.capabilities || {}).demand || {};
    const total = Object.values(caps).reduce((sum, item) => sum + (Number(item) || 0), 0);
    document.getElementById("capability-total").textContent = `${total} demand`;
    renderStack("capability-list", caps);
  }

  function renderResources(data) {
    const resources = data.resources || {};
    document.getElementById("routing-count").textContent = `${resources.routing_records_for_sprint || 0} sprint routes`;
    renderStack("resource-list", resources.cost_by_status || {});
  }

  function field(label, value) {
    return `<div class="field"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function renderRoutes(data) {
    const nodes = ((data.dag || {}).nodes || []);
    const routed = nodes.filter((node) =>
      node.route_decision || node.decision || node.blocked_reason || (node.pane_carrier || {}).pane_id
    );
    document.getElementById("route-count").textContent = `${routed.length} decisions`;
    document.getElementById("route-list").innerHTML = routed.length ? routed.map((node) => {
      const paneCarrier = node.pane_carrier || {};
      return `<section class="evidence-card ${esc(node.route_decision || node.decision || "pending")}">
        <div class="evidence-title">
          <strong>${esc(node.id || "N/A")}</strong>
          ${badge(node.route_decision || node.decision || "pending")}
        </div>
        <div class="field-grid">
          ${field("route_decision", node.route_decision || node.decision || "N/A")}
          ${field("blocked_reason", node.blocked_reason || "N/A")}
          ${field("target_pane", node.target_pane || "N/A")}
          ${field("pane_carrier.source", paneCarrier.source || "N/A")}
        </div>
      </section>`;
    }).join("") : '<div class="muted">No route decisions available.</div>';
  }

  function renderActorHosts(data) {
    const panes = ((data.capabilities || {}).pane_supply || []);
    document.getElementById("actorhost-count").textContent = `${panes.length} hosts`;
    document.getElementById("actorhost-list").innerHTML = panes.length ? panes.map((pane) => {
      const actorhost = pane.actorhost || {};
      const match = pane.capability_match || actorhost.capability_match || {};
      const missing = (match.missing || []).map((cap) => `<span class="chip warn-chip">${esc(cap)}</span>`).join("");
      const observed = (match.observed || pane.provided_capabilities || []).slice(0, 8)
        .map((cap) => `<span class="chip">${esc(cap)}</span>`).join("");
      return `<section class="evidence-card">
        <div class="evidence-title">
          <strong>${esc(pane.actor_id || actorhost.actor_id || "N/A")}</strong>
          ${badge(pane.lease_state || actorhost.lease_state || "unknown")}
        </div>
        <div class="field-grid">
          ${field("actor_id", pane.actor_id || actorhost.actor_id || "N/A")}
          ${field("host_id", pane.host_id || actorhost.host_id || "N/A")}
          ${field("host_type", pane.host_type || actorhost.host_type || "unknown")}
          ${field("lease_state", pane.lease_state || actorhost.lease_state || "unknown")}
          ${field("resolution_source", actorhost.resolution_source || "N/A")}
          ${field("canonical_host_type", actorhost.canonical_host_type ?? "N/A")}
        </div>
        <div class="chips" aria-label="observed capabilities">${observed || '<span class="chip">N/A</span>'}</div>
        <div class="chips" aria-label="missing capabilities">${missing}</div>
      </section>`;
    }).join("") : '<div class="muted">No ActorHost taxonomy records available.</div>';
  }

  function renderDiagnostics(data) {
    const items = data.blocker_diagnostics || [];
    document.getElementById("blocker-count").textContent = `${items.length} findings`;
    document.getElementById("blocker-list").innerHTML = items.length ? items.map((item) => {
      const guidance = (item.guidance || []).map((step) => `<li>${esc(step)}</li>`).join("");
      return `<section class="diagnostic ${esc(item.severity || "warn")}">
        <h3>${esc(item.title || item.kind || "Diagnostic")}</h3>
        <p>${esc(item.detail || "N/A")}</p>
        <ol>${guidance || "<li>N/A</li>"}</ol>
      </section>`;
    }).join("") : '<div class="diagnostic"><h3>No active blockers detected</h3><p>Current status and graph files do not report unresolved dependencies.</p><ol><li>Keep graph validation and handoff evidence attached before closing the node.</li></ol></div>';
  }

  function renderDegraded(envelope) {
    const items = envelope.degraded_sources || [];
    document.getElementById("degraded-count").textContent = items.length ? `${items.length} degraded` : "ok";
    document.getElementById("degraded-list").innerHTML = items.length ? items.map((item) =>
      `<section class="diagnostic degraded">
        <h3>degraded_source</h3>
        <p>${esc(item)}</p>
        <ol><li>Keep this visible until the upstream file or service recovers.</li></ol>
      </section>`
    ).join("") : '<div class="diagnostic ok"><h3>No degraded sources</h3><p>Dashboard API reported a complete evidence envelope.</p><ol><li>Continue graph validation before closing the node.</li></ol></div>';
  }

  function renderPanes(data) {
    const panes = ((data.capabilities || {}).pane_supply || []);
    document.getElementById("pane-count").textContent = `${panes.length} panes`;
    document.getElementById("pane-supply").innerHTML = panes.length ? panes.map((pane) => {
      const caps = (pane.provided_capabilities || []).slice(0, 6).map((cap) => `<span class="chip">${esc(cap)}</span>`).join("");
      const carrier = pane.pane_carrier || {};
      return `<section class="pane-card">
        <strong>Pane Carrier: ${esc(carrier.pane_id || pane.pane_id || "N/A")}</strong>
        <span class="muted">role=${esc(carrier.role || pane.role || "N/A")} · model=${esc(carrier.model || pane.model || "N/A")} · state=${esc(carrier.state || pane.state || "N/A")}</span>
        <div class="field-grid compact">
          ${field("actor_id", pane.actor_id || "N/A")}
          ${field("host_id", pane.host_id || "N/A")}
          ${field("host_type", pane.host_type || "unknown")}
          ${field("lease_state", pane.lease_state || "unknown")}
        </div>
        <div class="chips">${caps || '<span class="chip">N/A</span>'}</div>
      </section>`;
    }).join("") : '<div class="muted">N/A</div>';
  }

  async function refresh() {
    const marker = document.getElementById("refresh-state");
    marker.textContent = "pending";
    try {
      const envelope = await fetchDashboard();
      const data = envelope.data || {};
      renderSelect(data);
      renderHero(data);
      renderDag(data);
      renderCapabilities(data);
      renderResources(data);
      renderRoutes(data);
      renderActorHosts(data);
      renderDiagnostics(data);
      renderDegraded(envelope);
      renderPanes(data);
      marker.textContent = `ok · ${envelope.generated_at || new Date().toISOString()}`;
    } catch (error) {
      marker.textContent = `error · ${error.message}`;
      document.getElementById("blocker-list").innerHTML =
        `<div class="diagnostic error"><h3>Dashboard API unreachable</h3><p>${esc(error.message)}</p><ol><li>Check that status-server is running on port 8765.</li><li>Open /healthz and run the orchestration route tests.</li></ol></div>`;
      document.getElementById("degraded-list").innerHTML =
        `<div class="diagnostic error"><h3>degraded_source</h3><p>dashboard_api:${esc(error.message)}</p><ol><li>Recover the API before trusting rendered orchestration state.</li></ol></div>`;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    refresh();
    setInterval(refresh, 15000);
  });
})();
