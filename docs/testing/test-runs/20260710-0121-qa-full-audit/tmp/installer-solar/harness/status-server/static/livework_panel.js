/* Solar Harness — Live Work Panel JS
   Vanilla fetch + DOM, no frameworks. */

(function () {
  var BASE = "/api";

  function $(id) { return document.getElementById(id); }

  function setContent(cardId, html) {
    var el = $(cardId);
    if (!el) return;
    var content = el.querySelector(".card-content");
    if (content) content.innerHTML = html;
  }

  function setSourceTs(cardId, ts) {
    var el = $(cardId);
    if (!el) return;
    var tag = el.querySelector(".source-tag");
    if (tag && ts) tag.textContent = "\u6765\u6e90: events.jsonl@" + ts;
  }

  function formatIdle(data) {
    if (data.is_idle) {
      return '<span style="color:#ffa726">No active work</span> (idle since ' +
        (data.idle_since || "unknown") + ")";
    }
    var panes = data.active_panes || [];
    return "Active panes: " + (panes.length ? panes.join(", ") : "unknown") +
      " | queue: " + data.queue_depth;
  }

  function formatNextStep(data) {
    var nodes = data.nodes || [];
    var lines = ["Phase: " + (data.phase || "unknown"),
      "Next: " + (data.next_action || "unknown")];
    nodes.forEach(function (n) {
      lines.push("  " + n.id + " [" + n.status + "] " + (n.goal || ""));
    });
    return lines.join("<br>");
  }

  function formatDeadlocks(data) {
    var alerts = data.active_deadlocks || [];
    if (!alerts.length) return "No deadlocks detected";
    return alerts.map(function (a) {
      return "Pane " + a.pane_id + " stuck " + a.elapsed_seconds + "s";
    }).join("<br>");
  }

  function formatRequirementCoverage(data) {
    if (!data || data.status === "missing") return "No requirement coverage yet";
    return [
      "Sprint: " + (data.sprint_id || "unknown"),
      "Verdict: " + (data.acceptance_verdict || "N/A"),
      "done/total: " + (data.done || 0) + "/" + (data.total || 0),
      "partial: " + (data.partial || 0) + " | missing: " + (data.missing || 0),
      "graph_complete: " + (data.graph_complete ? "true" : "false"),
    ].join("<br>");
  }

  function formatEventsTail(data) {
    if (!data || !data.length) return "No recent events";
    return data.slice(-10).map(function (e) {
      var ts = e.ts || e.timestamp || "?";
      var type = e.type || e.event || "?";
      return '<div class="event-line">' + ts + " " + type + "</div>";
    }).join("");
  }

  var FALLBACK_COLORS = {
    L1: "color:#2e7d32",
    L2: "color:#f9a825",
    L3: "color:#ef6c00",
    L4: "color:#c62828",
    unknown: "color:#9e9e9e",
  };

  function formatFallbackLevel(level) {
    var key = level || "unknown";
    var style = FALLBACK_COLORS[key] || FALLBACK_COLORS.unknown;
    return '<span class="badge badge-fallback-' + key + '" style="' + style + '">' + key + "</span>";
  }

  function formatStateTransition(data) {
    var state = data && data.state ? data.state : "unknown";
    var el = $("s04-state-badge");
    if (el) {
      el.style.transition = "opacity 0.4s ease, transform 0.4s ease";
      el.style.opacity = "0.35";
      el.style.transform = "translateY(-2px)";
      requestAnimationFrame(function () {
        el.textContent = state;
        el.style.opacity = "1";
        el.style.transform = "translateY(0)";
      });
    }
    return '<span class="state-badge">' + state + "</span>";
  }

  function formatResearchMetrics(data) {
    if (!data) return "unknown";
    var rows = [
      "usage_source: " + (data.usage_source || "unknown"),
      "estimated: " + (data.estimated === true ? "true" : data.estimated === false ? "false" : "unknown"),
      "fallback_reason: " + (data.fallback_reason || "none"),
      "fallback_level: " + formatFallbackLevel(data.fallback_level),
    ];
    return rows.join("<br>");
  }

  function fetchJSON(path, cb) {
    fetch(BASE + path)
      .then(function (r) { return r.json(); })
      .then(cb)
      .catch(function () { cb(null); });
  }

  function refresh() {
    fetchJSON("/idle-state", function (d) {
      setContent("no-active-work-card", d ? formatIdle(d) : "unknown");
      if (d && d.last_heartbeat_ts) setSourceTs("no-active-work-card", d.last_heartbeat_ts);
    });

    fetchJSON("/sprints/_default/next-step", function (d) {
      setContent("role-next-step-card", d ? formatNextStep(d) : "unknown");
    });

    fetchJSON("/deadlock-alerts", function (d) {
      setContent("deadlock-alerts-card", d ? formatDeadlocks(d) : "unknown");
      if (d && d.checked_at) setSourceTs("deadlock-alerts-card", d.checked_at);
    });

    fetchJSON("/requirement-coverage", function (d) {
      setContent("requirement-coverage-card", d ? formatRequirementCoverage(d) : "unknown");
    });

    fetchJSON("/events/tail", function (d) {
      setContent("events-tail-card", d ? formatEventsTail(d) : "unknown");
    });
  }

  refresh();
  setInterval(refresh, 30000);
})();
