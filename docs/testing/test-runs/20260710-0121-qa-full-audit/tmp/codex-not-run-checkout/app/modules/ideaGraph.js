import { getGraph } from "./api.js";
import { ENTITY_LABEL, VALID_TYPES } from "./schema.js";
import { state } from "./state.js";

const ENTITY_COLORS = Object.freeze({
  papers: "#4A90D9",
  concepts: "#EC4899",
  topics: "#E67E22",
  people: "#2ECC71",
  ideas: "#F39C12",
  experiments: "#E74C3C",
  methods: "#84CC16",
  Summary: "#1ABC9C",
  foundations: "#95A5A6",
  outputs: "#64748B",
});

const EDGE_COLORS = Object.freeze({
  addresses_gap: "#F5A623",
  inspired_by: "#F5A623",
  tested_by: "#E6A23C",
  derived_from: "#999999",
  supports: "#59C189",
  contradicts: "#E74C3C",
  fm_ideas_origin_gaps: "#B8B8C8",
  fm_ideas_linked_experiments: "#B8B8C8",
  fm_experiments_linked_idea: "#B8B8C8",
  introduces_concept: "#5B8BD9",
  uses_concept: "#5B8BD9",
  fm_methods_source_papers: "#B8B8C8",
});

let cleanupIdeaGraph = null;

export async function viewIdeaGraph(mount) {
  destroyIdeaGraph();

  mount.innerHTML = `
    <div class="idea-graph-page">
      <aside class="idea-graph-sidebar">
        <div class="breadcrumb"><a href="#/">Reader</a> / Idea Graph</div>
        <h1>Idea Graph</h1>
        <p class="muted small">Idea-centered wiki graph built from semantic edges and projected frontmatter links.</p>

        <label class="idea-control">
          <span>Search</span>
          <input id="idea-graph-search" type="search" placeholder="title, slug, or edge type" autocomplete="off">
        </label>

        <h3>Status</h3>
        <div id="idea-status-filters" class="idea-filter-stack"></div>

        <h3>Display</h3>
        <label class="filter-toggle">
          <input id="idea-show-context" type="checkbox" checked>
          Include context edges
        </label>
        <label class="filter-toggle">
          <input id="idea-show-labels" type="checkbox" checked>
          Show node labels
        </label>

        <div class="idea-graph-actions">
          <button type="button" id="idea-fit">Fit</button>
          <button type="button" id="idea-zoom-in">+</button>
          <button type="button" id="idea-zoom-out">-</button>
        </div>

        <p id="idea-graph-stats" class="muted graph-stats">loading...</p>
      </aside>

      <section class="idea-graph-canvas-wrap">
        <svg id="idea-graph-canvas" class="idea-graph-canvas" role="img" aria-label="Idea connection graph"></svg>
      </section>

      <aside id="idea-node-detail" class="idea-node-detail">
        <h2>Selection</h2>
        <p class="muted">Select a node to inspect links and open its wiki page.</p>
      </aside>
    </div>
  `;

  let payload;
  try {
    payload = await getGraph();
  } catch (err) {
    mount.querySelector(".idea-graph-canvas-wrap").innerHTML =
      `<div class="graph-empty">Failed to load /api/graph: ${escapeHtml(err.message)}</div>`;
    return;
  }

  const graph = buildIdeaGraph(payload);
  if (graph.nodes.length === 0) {
    mount.querySelector(".idea-graph-canvas-wrap").innerHTML =
      `<div class="graph-empty">No idea pages or idea edges found yet.</div>`;
    return;
  }

  const uiState = {
    selectedId: null,
    search: "",
    showContext: true,
    showLabels: true,
    statuses: new Set(graph.statuses),
    viewBox: null,
    dragging: null,
    panning: null,
  };

  const svg = mount.querySelector("#idea-graph-canvas");
  buildStatusFilters(mount, graph, uiState, render);
  wireControls(mount, graph, uiState, render);
  cleanupIdeaGraph = wireSvgInteractions(svg, graph, uiState, render);
  render();

  function render() {
    const visible = filterGraph(graph, uiState);
    if (!uiState.viewBox) uiState.viewBox = fitViewBox(visible.nodes);
    renderSvg(svg, visible, uiState);
    renderStats(mount, graph, visible);
    renderDetail(mount, graph, visible, uiState.selectedId);
  }
}

export function destroyIdeaGraph() {
  if (cleanupIdeaGraph) {
    cleanupIdeaGraph();
    cleanupIdeaGraph = null;
  }
}

function buildIdeaGraph(payload) {
  const meta = buildMeta();
  const allEdges = [...(payload.edges || []), ...(payload.citations || [])]
    .filter((e) => e.from && e.to);

  const ideaIds = new Set((state.entitiesByType.ideas || [])
    .filter((e) => e.slug)
    .map((e) => `ideas/${e.slug}`));

  const directEdges = allEdges.filter((e) => ideaIds.has(e.from) || ideaIds.has(e.to));
  const nodeIds = new Set(ideaIds);
  directEdges.forEach((e) => {
    nodeIds.add(e.from);
    nodeIds.add(e.to);
  });

  const contextEdges = allEdges.filter((e) =>
    nodeIds.has(e.from) && nodeIds.has(e.to) &&
    !(ideaIds.has(e.from) || ideaIds.has(e.to))
  );
  const edges = dedupeEdges([...directEdges, ...contextEdges]);

  const nodes = Array.from(nodeIds).map((id) => {
    const [entity, ...rest] = id.split("/");
    const slug = rest.join("/");
    const item = meta.get(id) || {};
    return {
      id,
      entity,
      slug,
      title: item.title || item.name || slug || id,
      status: item.status || "",
      novelty: item.novelty_score || item.novelty || "",
      priority: Number(item.priority || 3),
      tags: Array.isArray(item.tags) ? item.tags : [],
      degree: 0,
    };
  });

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  edges.forEach((e) => {
    if (nodeMap.has(e.from)) nodeMap.get(e.from).degree++;
    if (nodeMap.has(e.to)) nodeMap.get(e.to).degree++;
  });
  computeLayout(nodes, edges);

  const statuses = Array.from(new Set(nodes
    .filter((n) => n.entity === "ideas")
    .map((n) => n.status || "unknown")))
    .sort(statusSort);

  return { nodes, edges, nodeMap, ideaIds, statuses };
}

function buildMeta() {
  const meta = new Map();
  for (const [entity, items] of Object.entries(state.entitiesByType || {})) {
    for (const item of items || []) {
      if (!item.slug) continue;
      meta.set(`${entity}/${item.slug}`, item);
    }
  }
  return meta;
}

function dedupeEdges(edges) {
  const seen = new Set();
  const result = [];
  for (const e of edges) {
    const type = e.type || "ref";
    const key = `${e.from}|${e.to}|${type}|${e.source || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({
      from: e.from,
      to: e.to,
      type,
      evidence: e.evidence || "",
      confidence: e.confidence || "",
      source: e.source || "",
      direct: e.from.startsWith("ideas/") || e.to.startsWith("ideas/"),
    });
  }
  return result;
}

function computeLayout(nodes, edges) {
  const groups = {
    ideas: { x: 540, y: 360 },
    concepts: { x: 280, y: 340 },
    papers: { x: 780, y: 250 },
    experiments: { x: 780, y: 520 },
    outputs: { x: 540, y: 650 },
    methods: { x: 980, y: 360 },
    topics: { x: 220, y: 560 },
    people: { x: 980, y: 560 },
    Summary: { x: 540, y: 100 },
    foundations: { x: 180, y: 120 },
  };
  const byEntity = new Map();
  nodes.forEach((node) => {
    const arr = byEntity.get(node.entity) || [];
    arr.push(node);
    byEntity.set(node.entity, arr);
  });
  for (const [entity, arr] of byEntity) {
    const target = groups[entity] || { x: 540, y: 360 };
    arr.forEach((node, i) => {
      const angle = (i / Math.max(arr.length, 1)) * Math.PI * 2 + seededAngle(node.id);
      const radius = entity === "ideas" ? 120 : 82 + arr.length * 5;
      node.x = target.x + Math.cos(angle) * radius;
      node.y = target.y + Math.sin(angle) * radius;
      node.vx = 0;
      node.vy = 0;
    });
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const links = edges
    .map((e) => ({ source: nodeMap.get(e.from), target: nodeMap.get(e.to), direct: e.direct }))
    .filter((e) => e.source && e.target);

  for (let iter = 0; iter < 360; iter++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) {
          dx = 1;
          dy = 0;
          d2 = 1;
        }
        const d = Math.sqrt(d2);
        const force = 6200 / d2;
        const fx = (dx / d) * force;
        const fy = (dy / d) * force;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }
    for (const link of links) {
      const dx = link.target.x - link.source.x;
      const dy = link.target.y - link.source.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const desired = link.direct ? 180 : 250;
      const force = (d - desired) * 0.012;
      const fx = (dx / d) * force;
      const fy = (dy / d) * force;
      link.source.vx += fx;
      link.source.vy += fy;
      link.target.vx -= fx;
      link.target.vy -= fy;
    }
    for (const node of nodes) {
      const target = groups[node.entity] || groups.ideas;
      node.vx += (target.x - node.x) * 0.006;
      node.vy += (target.y - node.y) * 0.006;
      node.vx *= 0.82;
      node.vy *= 0.82;
      node.x += Math.max(-16, Math.min(16, node.vx));
      node.y += Math.max(-16, Math.min(16, node.vy));
    }
  }
}

function filterGraph(graph, uiState) {
  const visibleIdeaIds = new Set();
  graph.nodes.forEach((node) => {
    if (node.entity === "ideas" && uiState.statuses.has(node.status || "unknown")) {
      visibleIdeaIds.add(node.id);
    }
  });

  const visibleEdges = graph.edges.filter((edge) => {
    if (edge.direct) {
      return visibleIdeaIds.has(edge.from) || visibleIdeaIds.has(edge.to);
    }
    return uiState.showContext;
  });

  const visibleNodeIds = new Set(visibleIdeaIds);
  visibleEdges.forEach((edge) => {
    const touchesVisibleIdea = visibleIdeaIds.has(edge.from) || visibleIdeaIds.has(edge.to);
    if (edge.direct && !touchesVisibleIdea) return;
    visibleNodeIds.add(edge.from);
    visibleNodeIds.add(edge.to);
  });

  const nodes = graph.nodes.filter((node) => visibleNodeIds.has(node.id));
  const nodeSet = new Set(nodes.map((n) => n.id));
  const edges = visibleEdges.filter((edge) => nodeSet.has(edge.from) && nodeSet.has(edge.to));
  return { nodes, edges, nodeSet };
}

function buildStatusFilters(mount, graph, uiState, render) {
  const stack = mount.querySelector("#idea-status-filters");
  const counts = new Map();
  graph.nodes
    .filter((n) => n.entity === "ideas")
    .forEach((n) => counts.set(n.status || "unknown", (counts.get(n.status || "unknown") || 0) + 1));

  stack.innerHTML = graph.statuses.map((status) => `
    <label class="idea-filter-row">
      <input type="checkbox" data-status="${escapeAttr(status)}" checked>
      <span>${escapeHtml(status)}</span>
      <span class="muted small">${counts.get(status) || 0}</span>
    </label>
  `).join("");

  stack.querySelectorAll("input[data-status]").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) uiState.statuses.add(cb.dataset.status);
      else uiState.statuses.delete(cb.dataset.status);
      uiState.viewBox = null;
      render();
    });
  });
}

function wireControls(mount, graph, uiState, render) {
  mount.querySelector("#idea-graph-search").addEventListener("input", (event) => {
    uiState.search = event.target.value.trim().toLowerCase();
    render();
  });
  mount.querySelector("#idea-show-context").addEventListener("change", (event) => {
    uiState.showContext = event.target.checked;
    uiState.viewBox = null;
    render();
  });
  mount.querySelector("#idea-show-labels").addEventListener("change", (event) => {
    uiState.showLabels = event.target.checked;
    render();
  });
  mount.querySelector("#idea-fit").addEventListener("click", () => {
    uiState.viewBox = fitViewBox(filterGraph(graph, uiState).nodes);
    render();
  });
  mount.querySelector("#idea-zoom-in").addEventListener("click", () => {
    zoomViewBox(uiState, 0.82);
    render();
  });
  mount.querySelector("#idea-zoom-out").addEventListener("click", () => {
    zoomViewBox(uiState, 1.22);
    render();
  });
}

function wireSvgInteractions(svg, graph, uiState, render) {
  const onClick = (event) => {
    const nodeEl = event.target.closest("[data-node-id]");
    if (!nodeEl) return;
    uiState.selectedId = nodeEl.dataset.nodeId;
    render();
  };
  const onPointerDown = (event) => {
    const nodeEl = event.target.closest("[data-node-id]");
    if (nodeEl) {
      uiState.dragging = nodeEl.dataset.nodeId;
      svg.setPointerCapture(event.pointerId);
      uiState.selectedId = uiState.dragging;
      render();
      event.preventDefault();
      return;
    }
    uiState.panning = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
    svg.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event) => {
    if (uiState.dragging) {
      const node = graph.nodeMap.get(uiState.dragging);
      if (!node) return;
      const p = svgPoint(svg, event.clientX, event.clientY);
      node.x = p.x;
      node.y = p.y;
      render();
      return;
    }
    if (uiState.panning) {
      const vb = uiState.viewBox || fitViewBox(graph.nodes);
      const dx = (event.clientX - uiState.panning.x) * (vb.w / Math.max(svg.clientWidth, 1));
      const dy = (event.clientY - uiState.panning.y) * (vb.h / Math.max(svg.clientHeight, 1));
      uiState.viewBox = { ...vb, x: vb.x - dx, y: vb.y - dy };
      uiState.panning.x = event.clientX;
      uiState.panning.y = event.clientY;
      render();
    }
  };
  const onPointerUp = () => {
    uiState.dragging = null;
    uiState.panning = null;
  };
  const onWheel = (event) => {
    event.preventDefault();
    zoomViewBox(uiState, event.deltaY > 0 ? 1.12 : 0.88);
    render();
  };

  svg.addEventListener("click", onClick);
  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", onPointerUp);
  svg.addEventListener("pointercancel", onPointerUp);
  svg.addEventListener("wheel", onWheel, { passive: false });

  return () => {
    svg.removeEventListener("click", onClick);
    svg.removeEventListener("pointerdown", onPointerDown);
    svg.removeEventListener("pointermove", onPointerMove);
    svg.removeEventListener("pointerup", onPointerUp);
    svg.removeEventListener("pointercancel", onPointerUp);
    svg.removeEventListener("wheel", onWheel);
  };
}

function renderSvg(svg, graph, uiState) {
  const nodeMap = new Map(graph.nodes.map((n) => [n.id, n]));
  const selected = uiState.selectedId;
  const neighbors = selected ? neighborhood(selected, graph.edges) : new Set();
  const query = uiState.search;
  const vb = uiState.viewBox || fitViewBox(graph.nodes);
  const labels = uiState.showLabels;

  svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  svg.innerHTML = `
    <defs>
      <marker id="idea-arrow" viewBox="0 0 10 10" refX="8" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z"></path>
      </marker>
    </defs>
    <rect class="idea-svg-bg" x="${vb.x - vb.w}" y="${vb.y - vb.h}"
          width="${vb.w * 3}" height="${vb.h * 3}"></rect>
    <g class="idea-edges">
      ${graph.edges.map((edge) => renderEdge(edge, nodeMap, selected, neighbors, query)).join("")}
    </g>
    <g class="idea-nodes">
      ${graph.nodes.map((node) => renderNode(node, selected, neighbors, query, labels)).join("")}
    </g>
  `;
}

function renderEdge(edge, nodeMap, selected, neighbors, query) {
  const from = nodeMap.get(edge.from);
  const to = nodeMap.get(edge.to);
  if (!from || !to) return "";
  const color = EDGE_COLORS[edge.type] || "#94A3B8";
  const dim = selected && from.id !== selected && to.id !== selected &&
    !neighbors.has(from.id) && !neighbors.has(to.id);
  const hit = query && edgeMatches(edge, query);
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const norm = Math.sqrt(dx * dx + dy * dy) || 1;
  const curve = edge.direct ? 28 : 16;
  const cx = mx - (dy / norm) * curve;
  const cy = my + (dx / norm) * curve;
  const classes = [
    "idea-edge",
    edge.direct ? "direct" : "context",
    dim ? "is-dim" : "",
    hit ? "is-search-hit" : "",
  ].filter(Boolean).join(" ");
  return `
    <path class="${classes}" d="M ${from.x.toFixed(1)} ${from.y.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${to.x.toFixed(1)} ${to.y.toFixed(1)}"
          stroke="${escapeAttr(color)}" style="color:${escapeAttr(color)}" marker-end="url(#idea-arrow)">
      <title>${escapeHtml(from.title)} -> ${escapeHtml(to.title)}\n${escapeHtml(edge.type)}${edge.evidence ? "\n" + escapeHtml(edge.evidence) : ""}</title>
    </path>
  `;
}

function renderNode(node, selected, neighbors, query, labels) {
  const color = ENTITY_COLORS[node.entity] || "#94A3B8";
  const radius = nodeRadius(node);
  const isSelected = selected === node.id;
  const isNeighbor = selected && neighbors.has(node.id);
  const isDim = selected && !isSelected && !isNeighbor;
  const isHit = query && nodeMatches(node, query);
  const classes = [
    "idea-node",
    `entity-${cssSafe(node.entity)}`,
    isSelected ? "is-selected" : "",
    isNeighbor ? "is-neighbor" : "",
    isDim ? "is-dim" : "",
    isHit ? "is-search-hit" : "",
  ].filter(Boolean).join(" ");
  return `
    <g class="${classes}" data-node-id="${escapeAttr(node.id)}" transform="translate(${node.x.toFixed(1)} ${node.y.toFixed(1)})">
      <circle r="${radius}" fill="${escapeAttr(color)}"></circle>
      <title>${escapeHtml(node.title)}\n${escapeHtml(node.id)}</title>
      ${labels ? `<text x="${radius + 7}" y="4">${escapeHtml(shortLabel(node.title))}</text>` : ""}
    </g>
  `;
}

function renderStats(mount, graph, visible) {
  const ideaCount = visible.nodes.filter((n) => n.entity === "ideas").length;
  mount.querySelector("#idea-graph-stats").textContent =
    `${ideaCount}/${graph.ideaIds.size} ideas - ${visible.nodes.length} nodes - ${visible.edges.length} edges`;
}

function renderDetail(mount, graph, visible, selectedId) {
  const panel = mount.querySelector("#idea-node-detail");
  const node = graph.nodeMap.get(selectedId);
  if (!node || !visible.nodeSet.has(node.id)) {
    panel.innerHTML = `
      <h2>Selection</h2>
      <p class="muted">Select a node to inspect links and open its wiki page.</p>
      <div class="idea-legend">${legendHtml(visible.nodes)}</div>
    `;
    return;
  }

  const links = visible.edges
    .filter((edge) => edge.from === node.id || edge.to === node.id)
    .map((edge) => {
      const otherId = edge.from === node.id ? edge.to : edge.from;
      const other = graph.nodeMap.get(otherId);
      const direction = edge.from === node.id ? "out" : "in";
      return { edge, other, direction };
    });

  panel.innerHTML = `
    <h2>${escapeHtml(node.title)}</h2>
    <p class="idea-node-meta">
      <span class="dot" style="background:${escapeAttr(ENTITY_COLORS[node.entity] || "#94A3B8")}"></span>
      ${escapeHtml(entityLabel(node.entity))} / ${escapeHtml(node.slug)}
    </p>
    ${node.entity === "ideas" ? ideaMetaHtml(node) : ""}
    ${openPageHtml(node)}
    <h3>Connections</h3>
    <div class="idea-connection-list">
      ${links.length ? links.map(({ edge, other, direction }) => connectionHtml(edge, other, direction)).join("") :
        '<p class="muted small">No visible connections.</p>'}
    </div>
  `;
}

function openPageHtml(node) {
  if (!VALID_TYPES.has(node.entity)) {
    return '<p class="muted small">This node is in the graph data but is not exposed as a reader route.</p>';
  }
  return `<a class="ghost-link" href="#/reader/${escapeAttr(node.entity)}/${escapeAttr(node.slug)}">Open page</a>`;
}

function ideaMetaHtml(node) {
  return `
    <div class="idea-node-fields">
      <span class="chip status">${escapeHtml(node.status || "unknown")}</span>
      ${node.novelty ? `<span class="chip">novelty ${escapeHtml(node.novelty)}</span>` : ""}
      <span class="chip">priority ${escapeHtml(node.priority)}</span>
    </div>
  `;
}

function connectionHtml(edge, other, direction) {
  const title = other ? other.title : (direction === "out" ? edge.to : edge.from);
  const id = other ? other.id : (direction === "out" ? edge.to : edge.from);
  return `
    <div class="idea-connection">
      <div>
        <span class="chip edge">${escapeHtml(edge.type)}</span>
        <span class="muted small">${direction}</span>
      </div>
      <strong>${escapeHtml(title)}</strong>
      <code>${escapeHtml(id)}</code>
      ${edge.evidence ? `<p class="muted small">${escapeHtml(edge.evidence)}</p>` : ""}
    </div>
  `;
}

function legendHtml(nodes) {
  const entities = Array.from(new Set(nodes.map((n) => n.entity))).sort();
  return entities.map((entity) => `
    <span class="idea-legend-item">
      <span class="dot" style="background:${escapeAttr(ENTITY_COLORS[entity] || "#94A3B8")}"></span>
      ${escapeHtml(entityLabel(entity))}
    </span>
  `).join("");
}

function fitViewBox(nodes) {
  if (!nodes.length) return { x: 0, y: 0, w: 1080, h: 760 };
  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = 230;
  return {
    x: minX - pad,
    y: minY - pad,
    w: Math.max(520, maxX - minX + pad * 2),
    h: Math.max(420, maxY - minY + pad * 2),
  };
}

function zoomViewBox(uiState, factor) {
  const vb = uiState.viewBox || { x: 0, y: 0, w: 1080, h: 760 };
  const cx = vb.x + vb.w / 2;
  const cy = vb.y + vb.h / 2;
  const w = Math.max(220, Math.min(2400, vb.w * factor));
  const h = Math.max(180, Math.min(1800, vb.h * factor));
  uiState.viewBox = { x: cx - w / 2, y: cy - h / 2, w, h };
}

function svgPoint(svg, clientX, clientY) {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

function neighborhood(id, edges) {
  const set = new Set();
  edges.forEach((edge) => {
    if (edge.from === id) set.add(edge.to);
    if (edge.to === id) set.add(edge.from);
  });
  return set;
}

function nodeRadius(node) {
  const base = node.entity === "ideas" ? 13 : 9;
  const priority = node.entity === "ideas" ? Math.max(1, Math.min(5, node.priority || 3)) : 3;
  return base + Math.sqrt(Math.max(0, node.degree)) * 2 + (priority - 3);
}

function nodeMatches(node, query) {
  if (!query) return false;
  return [
    node.id,
    node.title,
    node.status,
    node.entity,
    ...(node.tags || []),
  ].some((value) => String(value || "").toLowerCase().includes(query));
}

function edgeMatches(edge, query) {
  if (!query) return false;
  return [edge.type, edge.from, edge.to, edge.evidence]
    .some((value) => String(value || "").toLowerCase().includes(query));
}

function shortLabel(label) {
  const s = String(label || "");
  return s.length > 30 ? s.slice(0, 29) + "..." : s;
}

function entityLabel(entity) {
  if (entity === "outputs") return "Outputs";
  return ENTITY_LABEL[entity] || entity;
}

function statusSort(a, b) {
  const order = ["proposed", "in_progress", "tested", "validated", "failed", "unknown"];
  return order.indexOf(a) - order.indexOf(b);
}

function seededAngle(id) {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return (hash % 628) / 100;
}

function cssSafe(s) {
  return String(s).replace(/[^a-zA-Z0-9_-]/g, "-");
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function escapeAttr(s) {
  return escapeHtml(s);
}
