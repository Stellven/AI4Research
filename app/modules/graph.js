const graphEl = document.querySelector("#graph");
const summaryEl = document.querySelector("#summary");
const detailsEl = document.querySelector("#details");
const searchEl = document.querySelector("#search");

const groupColors = new Map([
  ["papers", "#2f6fed"],
  ["ideas", "#0f8f70"],
  ["experiments", "#b45f06"],
  ["outputs", "#7c3aed"],
  ["graph", "#667085"],
]);

function point(index, total, width, height) {
  const radius = Math.max(120, Math.min(width, height) * 0.36);
  const angle = (Math.PI * 2 * index) / Math.max(total, 1) - Math.PI / 2;
  return {
    x: width / 2 + Math.cos(angle) * radius,
    y: height / 2 + Math.sin(angle) * radius,
  };
}

function render(data, filter = "") {
  const width = graphEl.clientWidth || 900;
  const height = graphEl.clientHeight || 640;
  const filterText = filter.trim().toLowerCase();
  const nodes = (data.nodes || []).filter((node) => {
    if (!filterText) return true;
    return `${node.id} ${node.label} ${node.group}`.toLowerCase().includes(filterText);
  });
  const visible = new Set(nodes.map((node) => node.id));
  const edges = (data.edges || []).filter((edge) => visible.has(edge.source) && visible.has(edge.target));
  const positions = new Map(nodes.map((node, index) => [node.id, point(index, nodes.length, width, height)]));

  graphEl.setAttribute("viewBox", `0 0 ${width} ${height}`);
  graphEl.innerHTML = "";

  for (const edge of edges) {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) continue;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("class", "edge");
    line.setAttribute("x1", source.x);
    line.setAttribute("y1", source.y);
    line.setAttribute("x2", target.x);
    line.setAttribute("y2", target.y);
    graphEl.appendChild(line);
  }

  for (const node of nodes) {
    const pos = positions.get(node.id);
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("class", "node");
    group.setAttribute("transform", `translate(${pos.x}, ${pos.y})`);
    group.addEventListener("click", () => {
      detailsEl.textContent = JSON.stringify(node, null, 2);
    });

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", 18);
    circle.setAttribute("fill", groupColors.get(node.group) || "#2f6fed");
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", 24);
    label.setAttribute("y", 4);
    label.textContent = node.label || node.id;
    group.append(circle, label);
    graphEl.appendChild(group);
  }

  summaryEl.textContent = `${nodes.length} nodes, ${edges.length} edges`;
}

async function main() {
  const response = await fetch("./data/graph.json", { cache: "no-store" });
  const data = await response.json();
  render(data);
  searchEl.addEventListener("input", () => render(data, searchEl.value));
}

main().catch((error) => {
  summaryEl.textContent = "Unable to load graph data";
  detailsEl.textContent = String(error);
});
