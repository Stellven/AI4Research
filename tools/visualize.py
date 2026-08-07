#!/usr/bin/env python3
"""OmegaWiki — Visualization Generator.

Generates visualization artifacts for the OmegaWiki knowledge graph:
Obsidian graph config and curated Canvas views.

The standalone-HTML graph explorer was retired in favour of the SPA Graph
view at app/modules/graph.js (served via tools/serve.py). Cytoscape +
force layout + filters + BFS now live there as a real ES module.

Called by /visualize skill via: python3 tools/visualize.py <command> [args]

Commands:
    generate-obsidian-config <wiki_root>
        Write .obsidian/graph.json with per-entity-type color groups.
        Creates .obsidian/app.json only if it does not exist.

    generate-canvas <wiki_root> [--focus <node_id>] [--depth N] [--output <path>]
        Generate Obsidian Canvas (.canvas) from graph data with labeled edges.

    list-recommendations
        Print recommended Obsidian plugins and setup instructions.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from runtime.loader import ENTITY_DIRS  # noqa: E402

DERIVED_DIR = "graph"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

# Obsidian Canvas color indices (not RGB — Canvas uses built-in palette)
CANVAS_COLOR_MAP = {
    "papers": "4",        # blue
    "concepts": "6",      # purple
    "topics": "3",        # orange
    "people": "5",        # green
    "ideas": "3",         # orange
    "experiments": "1",   # red
    "methods": "6",       # purple
    "Summary": "5",       # green
    "foundations": "2",   # yellow
}

# Node dimensions for Canvas
CANVAS_NODE_SIZES = {
    "papers": (400, 300),
    "concepts": (350, 250),
}

DEFAULT_CANVAS_SIZE = (300, 200)

# Size scale factor per importance level (1..5). Only papers carry importance in
# the schema today; other types default to 3 (baseline 1.0x).
IMPORTANCE_SCALE = {1: 0.7, 2: 0.85, 3: 1.0, 4: 1.2, 5: 1.5}

# ---------------------------------------------------------------------------
# Helpers — JSONL loading (mirrors research_wiki.py patterns)
# ---------------------------------------------------------------------------

def _node_kind(node_id: str) -> str:
    return node_id.split("/", 1)[0] if "/" in node_id else ""


def load_edges(wiki_root: str) -> list[dict]:
    edges_path = Path(wiki_root) / DERIVED_DIR / "edges.jsonl"
    edges = []
    if not edges_path.exists():
        return edges
    for line in edges_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            edges.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return edges


def load_citations(wiki_root: str) -> list[dict]:
    citations_path = Path(wiki_root) / DERIVED_DIR / "citations.jsonl"
    citations = []
    if not citations_path.exists():
        return citations
    for line in citations_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            citations.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return citations


# ---------------------------------------------------------------------------
# Helpers — Frontmatter parsing (mirrors research_wiki.py)
# ---------------------------------------------------------------------------

def _parse_scalar(val: str):
    val = val.strip()
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _parse_block_value(block_lines: list[str]):
    if not block_lines:
        return ""
    result = []
    for bl in block_lines:
        stripped = bl.strip()
        if stripped.startswith("- "):
            result.append(stripped[2:].strip().strip("\"'"))
    if result:
        return result
    return "\n".join(block_lines).strip()


def _parse_yaml_block(text: str) -> dict:
    fm: dict = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue
        if line[0] == " ":
            i += 1
            continue
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip()
        if val:
            fm[key] = _parse_scalar(val)
            i += 1
        else:
            block_lines: list[str] = []
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if next_line and not next_line[0].isspace():
                    break
                block_lines.append(next_line)
                i += 1
            fm[key] = _parse_block_value(block_lines)
    return fm


def parse_frontmatter(path: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}
    return _parse_yaml_block(m.group(1))


def load_page_metadata(wiki_root: str) -> dict[str, dict]:
    """Scan all entity directories, return {node_id: frontmatter_dict}."""
    root = Path(wiki_root)
    metadata: dict[str, dict] = {}
    for entity_dir in ENTITY_DIRS:
        dir_path = root / entity_dir
        if not dir_path.is_dir():
            continue
        for md_file in dir_path.glob("*.md"):
            if md_file.name == ".gitkeep":
                continue
            slug = md_file.stem
            node_id = f"{entity_dir}/{slug}"
            fm = parse_frontmatter(md_file)
            if fm:
                metadata[node_id] = fm
    return metadata


# ---------------------------------------------------------------------------
# Helpers — Config loading
# ---------------------------------------------------------------------------

def load_visualize_config(repo_root: str) -> dict:
    config_path = Path(repo_root) / "config" / "visualize.json"
    if not config_path.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(config_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers — Force-directed layout for Canvas
# ---------------------------------------------------------------------------

def _force_layout(nodes: list[dict], edges: list[dict],
                  focus_node: str | None = None,
                  width: int = 3000, height: int = 2000) -> list[dict]:
    """Simple force-directed layout. Returns nodes with x/y assigned."""
    import random
    random.seed(42)

    n = len(nodes)
    if n == 0:
        return nodes

    # Assign initial positions — group by entity type in clusters
    kind_positions: dict[str, tuple[float, float]] = {}
    kind_counts: dict[str, int] = defaultdict(int)
    for nd in nodes:
        kind = _node_kind(nd["id"])
        kind_counts[kind] += 1

    # Place clusters in a circle
    unique_kinds = sorted(kind_counts.keys())
    cx, cy = width / 2, height / 2
    cluster_radius = min(width, height) * 0.3
    for i, kind in enumerate(unique_kinds):
        angle = 2 * math.pi * i / len(unique_kinds)
        kind_positions[kind] = (
            cx + cluster_radius * math.cos(angle),
            cy + cluster_radius * math.sin(angle),
        )

    # Initialize positions with jitter around cluster center
    pos: dict[str, tuple[float, float]] = {}
    for nd in nodes:
        kind = _node_kind(nd["id"])
        kx, ky = kind_positions[kind]
        pos[nd["id"]] = (
            kx + random.uniform(-100, 100),
            ky + random.uniform(-100, 100),
        )

    # If focus node, move it to center
    if focus_node and focus_node in pos:
        pos[focus_node] = (cx, cy)

    # Build adjacency for repulsion/attraction
    edge_pairs = [(e["from"], e["to"]) for e in edges if e["from"] in pos and e["to"] in pos]

    # Spring-electron simulation
    k = math.sqrt(width * height / max(n, 1)) * 0.8  # optimal distance
    temperature = width * 0.1
    cooling = 0.95

    for iteration in range(80):
        # Repulsive forces between all pairs
        disp: dict[str, tuple[float, float]] = {nid: (0.0, 0.0) for nid in pos}
        node_ids = list(pos.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                ni, nj = node_ids[i], node_ids[j]
                dx = pos[ni][0] - pos[nj][0]
                dy = pos[ni][1] - pos[nj][1]
                dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
                force = (k * k) / dist
                fx = (dx / dist) * force
                fy = (dy / dist) * force
                disp[ni] = (disp[ni][0] + fx, disp[ni][1] + fy)
                disp[nj] = (disp[nj][0] - fx, disp[nj][1] - fy)

        # Attractive forces along edges
        for ea, eb in edge_pairs:
            dx = pos[ea][0] - pos[eb][0]
            dy = pos[ea][1] - pos[eb][1]
            dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
            force = (dist * dist) / k
            fx = (dx / dist) * force
            fy = (dy / dist) * force
            disp[ea] = (disp[ea][0] - fx, disp[ea][1] - fy)
            disp[eb] = (disp[eb][0] + fx, disp[eb][1] + fy)

        # Apply displacements, clamped by temperature
        for nid in pos:
            dx, dy = disp[nid]
            dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
            scale = min(dist, temperature) / dist
            new_x = pos[nid][0] + dx * scale
            new_y = pos[nid][1] + dy * scale
            # Keep within bounds
            new_x = max(50, min(width - 50, new_x))
            new_y = max(50, min(height - 50, new_y))
            pos[nid] = (new_x, new_y)

        temperature *= cooling

    # Assign positions back
    for nd in nodes:
        if nd["id"] in pos:
            nd["x"] = int(pos[nd["id"]][0])
            nd["y"] = int(pos[nd["id"]][1])

    return nodes


def _radial_layout(nodes: list[dict], edges: list[dict],
                   focus_node: str,
                   width: int = 3000, height: int = 3000) -> list[dict]:
    """Concentric-ring layout centered on focus_node.

    Ring d holds nodes at BFS distance d from focus_node. Within a ring, nodes
    are sorted by (entity_type, id) so same-type nodes cluster on the circle.
    Ring radius grows with d and is bumped up if too many nodes would overlap.
    """
    if not nodes:
        return nodes

    node_ids = {nd["id"] for nd in nodes}
    if focus_node not in node_ids:
        # Fall back: place all nodes in a single outer ring around the canvas center.
        focus_node = nodes[0]["id"]

    # BFS distances from focus_node
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        a, b = e["from"], e["to"]
        if a in node_ids and b in node_ids:
            adj[a].append(b)
            adj[b].append(a)

    distance: dict[str, int] = {focus_node: 0}
    frontier = [focus_node]
    while frontier:
        next_frontier: list[str] = []
        for nid in frontier:
            for nb in adj.get(nid, []):
                if nb not in distance:
                    distance[nb] = distance[nid] + 1
                    next_frontier.append(nb)
        frontier = next_frontier

    max_known = max(distance.values()) if distance else 0
    rings: dict[int, list[dict]] = defaultdict(list)
    for nd in nodes:
        d = distance.get(nd["id"], max_known + 1)
        rings[d].append(nd)

    cx, cy = width / 2, height / 2

    base_radius = 700
    for ring_idx in sorted(rings.keys()):
        ring_nodes = sorted(rings[ring_idx], key=lambda n: (_node_kind(n["id"]), n["id"]))
        if ring_idx == 0:
            # Center the focus node by its center, not top-left
            for nd in ring_nodes:
                nd["x"] = int(cx - nd["width"] / 2)
                nd["y"] = int(cy - nd["height"] / 2)
            continue

        count = len(ring_nodes)
        if count == 0:
            continue
        max_w = max(nd["width"] for nd in ring_nodes)
        spacing = max_w * 1.3
        min_radius = (count * spacing) / (2 * math.pi)
        radius = max(base_radius * ring_idx, min_radius)

        for i, nd in enumerate(ring_nodes):
            angle = 2 * math.pi * i / count
            nx = cx + radius * math.cos(angle)
            ny = cy + radius * math.sin(angle)
            nd["x"] = int(nx - nd["width"] / 2)
            nd["y"] = int(ny - nd["height"] / 2)

    return nodes


def _canvas_edge_side(from_node: dict, to_node: dict) -> tuple[str, str]:
    """Determine fromSide/toSide based on relative positions."""
    fx, fy = from_node.get("x", 0), from_node.get("y", 0)
    tx, ty = to_node.get("x", 0), to_node.get("y", 0)
    dx = tx - fx
    dy = ty - fy
    if abs(dx) > abs(dy):
        return ("right", "left") if dx > 0 else ("left", "right")
    else:
        return ("bottom", "top") if dy > 0 else ("top", "bottom")


# ---------------------------------------------------------------------------
# Command: generate-obsidian-config
# ---------------------------------------------------------------------------

def cmd_generate_obsidian_config(wiki_root: str) -> None:
    """Write .obsidian/graph.json with per-entity-type color groups."""
    # Find repo root (parent of wiki/)
    wiki_path = Path(wiki_root).resolve()
    repo_root = wiki_path.parent
    config = load_visualize_config(str(repo_root))
    entity_colors = config.get("entity_colors", {})

    obsidian_dir = wiki_path / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)

    # Build color groups. Use a trailing slash so the path query matches the
    # directory boundary instead of any substring (Obsidian path: search is
    # otherwise a substring match across the full file path).
    color_groups = []
    for entity_type in ENTITY_DIRS:
        color_info = entity_colors.get(entity_type, {})
        rgb = color_info.get("rgb", 0)
        color_groups.append({
            "query": f"path:{entity_type}/",
            "color": {"a": 1, "rgb": rgb},
        })

    # Whitelist filter: only show nodes whose path is under one of the 9 entity
    # directories. This drops uncolored derived/top-level files like log.md,
    # index.md, graph/context_brief.md, graph/open_questions.md, and any
    # canvases/ or outputs/ artifacts from the graph view.
    search_query = " OR ".join(f"path:{e}/" for e in ENTITY_DIRS)

    graph_json = {
        "collapse-filter": False,
        "search": search_query,
        # Tag nodes share no colorGroup with the 9 entity types; hiding them
        # keeps the graph palette tied 1:1 to entity types.
        "showTags": False,
        "showAttachments": False,
        "hideUnresolved": False,
        "showOrphans": True,
        "collapse-color-groups": False,
        "colorGroups": color_groups,
        "collapse-display": False,
        "showArrow": True,
        "textFadeMultiplier": -2,
        "nodeSizeMultiplier": 1,
        "lineSizeMultiplier": 1,
        "collapse-forces": True,
        "centerStrength": 0.5,
        "repelStrength": 10,
        "linkStrength": 1,
        "linkDistance": 250,
    }

    graph_path = obsidian_dir / "graph.json"
    graph_path.write_text(json.dumps(graph_json, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {graph_path}")

    # app.json — only create if missing
    app_path = obsidian_dir / "app.json"
    if not app_path.exists():
        app_json = {
            "strictLineBreaks": False,
            "showFrontmatter": False,
            "defaultViewMode": "source",
            "livePreview": True,
        }
        app_path.write_text(json.dumps(app_json, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Written: {app_path} (new)")
    else:
        print(f"Skipped: {app_path} (already exists)")

    print("Done. Open wiki/ in Obsidian and check Graph View settings.")


# ---------------------------------------------------------------------------
# Command: generate-canvas
# ---------------------------------------------------------------------------

def _split_filter_values(raw: str | None) -> set[str]:
    return {item.strip() for item in str(raw or "").split(",") if item.strip()}


def _edge_type(raw: dict) -> str:
    return str(raw.get("type") or raw.get("relation") or raw.get("edge_type") or "related").strip()


def _edge_source(raw: dict) -> str:
    return str(raw.get("from") or raw.get("source") or "").strip()


def _edge_target(raw: dict) -> str:
    return str(raw.get("to") or raw.get("target") or "").strip()


def _filter_canvas_edges(
    edges: list[dict],
    *,
    node_types: set[str],
    edge_types: set[str],
) -> list[dict]:
    filtered: list[dict] = []
    for edge in edges:
        source = _edge_source(edge)
        target = _edge_target(edge)
        if edge_types and _edge_type(edge) not in edge_types:
            continue
        if node_types and (_node_kind(source) not in node_types or _node_kind(target) not in node_types):
            continue
        filtered.append(edge)
    return filtered


def cmd_generate_canvas(wiki_root: str, focus: str | None = None,
                        depth: int = 2, output: str | None = None,
                        types: str | None = None,
                        edge_types: str | None = None) -> None:
    """Generate Obsidian Canvas from graph data."""
    edges = load_edges(wiki_root)
    citations = load_citations(wiki_root)
    metadata = load_page_metadata(wiki_root)

    if not edges and not citations:
        print("No graph data found. Run /ingest first.", file=sys.stderr)
        sys.exit(1)

    type_filter = _split_filter_values(types)
    edge_type_filter = _split_filter_values(edge_types)
    all_edges = _filter_canvas_edges(
        edges + citations,
        node_types=type_filter,
        edge_types=edge_type_filter,
    )

    # Determine which nodes to include
    if focus:
        # BFS from focus node
        node_ids = _bfs_nodes(focus, all_edges, depth)
    else:
        # All nodes
        node_ids = set()
        for e in all_edges:
            node_ids.add(_edge_source(e))
            node_ids.add(_edge_target(e))
    if type_filter:
        node_ids = {node_id for node_id in node_ids if _node_kind(node_id) in type_filter}

    # Build node list
    node_map: dict[str, dict] = {}
    for nid in sorted(node_ids):
        kind = _node_kind(nid)
        base_w, base_h = CANVAS_NODE_SIZES.get(kind, DEFAULT_CANVAS_SIZE)
        fm = metadata.get(nid, {})
        title = fm.get("title", fm.get("name", nid.split("/", 1)[-1] if "/" in nid else nid))
        importance = fm.get("importance", 3)
        try:
            importance = max(1, min(5, int(importance)))
        except (TypeError, ValueError):
            importance = 3
        scale = IMPORTANCE_SCALE[importance]
        w, h = int(base_w * scale), int(base_h * scale)
        node_map[nid] = {
            "id": nid,
            "type": "file",
            "file": f"{nid}.md",
            "label": title,
            "x": 0,
            "y": 0,
            "width": w,
            "height": h,
            "color": CANVAS_COLOR_MAP.get(kind, "0"),
        }

    # Build edge list for layout
    layout_edges = []
    for e in all_edges:
        if _edge_source(e) in node_map and _edge_target(e) in node_map:
            layout_edges.append(e)

    # Layout: radial (concentric rings) when focused, force-directed otherwise.
    # Radial gives focus mode a clear center-out structure that force-directed
    # can't guarantee.
    nodes_list = list(node_map.values())
    if focus:
        _radial_layout(nodes_list, layout_edges, focus_node=focus)
    else:
        _force_layout(nodes_list, layout_edges, focus_node=focus)

    # Build Canvas edges with labels
    canvas_edges = []
    seen_edge_keys: set[tuple[str, str, str]] = set()
    edge_idx = 0
    for e in all_edges:
        src, dst = _edge_source(e), _edge_target(e)
        etype = _edge_type(e)
        key = (src, dst, etype)
        if key in seen_edge_keys:
            continue
        if src not in node_map or dst not in node_map:
            continue
        seen_edge_keys.add(key)

        from_node = node_map[src]
        to_node = node_map[dst]
        from_side, to_side = _canvas_edge_side(from_node, to_node)

        canvas_edges.append({
            "id": f"edge-{edge_idx}",
            "fromNode": src,
            "toNode": dst,
            "fromSide": from_side,
            "toSide": to_side,
            "label": etype,
        })
        edge_idx += 1

    canvas_data = {
        "nodes": list(node_map.values()),
        "edges": canvas_edges,
    }

    # Determine output path
    if output:
        out_path = Path(output)
    else:
        wiki_path = Path(wiki_root).resolve()
        canvases_dir = wiki_path / "canvases"
        canvases_dir.mkdir(parents=True, exist_ok=True)
        name = f"focus-{focus.replace('/', '-')}.canvas" if focus else "knowledge-map.canvas"
        out_path = canvases_dir / name

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(canvas_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {out_path}")
    print(f"  Nodes: {len(canvas_data['nodes'])}, Edges: {len(canvas_data['edges'])}")


def _bfs_nodes(start: str, edges: list[dict], depth: int) -> set[str]:
    """BFS from start node up to given depth."""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        src, dst = _edge_source(e), _edge_target(e)
        if not src or not dst:
            continue
        adj[src].append(dst)
        adj[dst].append(src)

    visited: set[str] = {start}
    current: set[str] = {start}
    for _ in range(depth):
        next_level: set[str] = set()
        for nid in current:
            for neighbor in adj.get(nid, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_level.add(neighbor)
        current = next_level
        if not current:
            break
    return visited




# ---------------------------------------------------------------------------
# Command: list-recommendations
# ---------------------------------------------------------------------------

def cmd_list_recommendations() -> None:
    """Print recommended Obsidian plugins and setup instructions."""
    print("""=== OmegaWiki Visualization Recommendations ===

Obsidian Plugins (install via Settings > Community Plugins):

1. Graph Analysis (HIGHLY RECOMMENDED)
   - Adds pathfinding, isolated cluster detection, and centrality metrics
   - Directly useful for identifying key nodes in the knowledge graph
   - Install: Settings > Community Plugins > Browse > "Graph Analysis"

2. Dataview (RECOMMENDED)
   - SQL-like queries over YAML frontmatter
   - Create dynamic views like "all training methods" or "ideas with novelty_score >= 4"
   - Example query: TABLE type, source_papers FROM "methods" WHERE type = "training"
   - Install: Settings > Community Plugins > Browse > "Dataview"

3. Excalidraw (OPTIONAL)
   - Annotate Canvas views with freehand diagrams and visual notes
   - Useful for brainstorming and presenting research ideas

Setup Instructions:

1. Open Obsidian
2. Click "Open another vault" > "Open folder as vault"
3. Select the wiki/ directory in your OmegaWiki repo
4. The .obsidian/graph.json config will be applied automatically
5. Open Graph View (Ctrl+G / Cmd+G) to see color-coded entity types

Canvas Usage:

1. Navigate to canvases/ in the file explorer
2. Open knowledge-map.canvas for the full graph overview
3. Open idea-evidence.canvas for the idea-centric research view
4. Generate focused canvases: python3 tools/visualize.py generate-canvas wiki/ --focus <node_id>

Standalone web Graph view:

1. python3 tools/serve.py            (starts the SPA on http://127.0.0.1:8765)
2. Open http://127.0.0.1:8765/#/graph
3. Click nodes for BFS highlight; double-click to open in the SPA Reader.
""")


# ---------------------------------------------------------------------------
# OpenSolar JSON ABI compatibility
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]


def default_wiki_root() -> Path:
    raw = os.environ.get("AUTOSCI_WIKI_ROOT") or os.environ.get("WIKI_ROOT")
    if raw:
        return Path(raw).expanduser()
    harness_dir = Path(os.environ.get("HARNESS_DIR", REPO_ROOT / "harness"))
    return harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"


def _compat_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _compat_title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                return line[2:].strip() or path.stem
    except OSError:
        pass
    return path.stem


def _compat_markdown_nodes(wiki_root: Path) -> list[dict]:
    nodes: list[dict] = []
    if not wiki_root.exists():
        return nodes
    for path in sorted(wiki_root.rglob("*.md")):
        if ".obsidian" in path.parts:
            continue
        node_id = _compat_rel(path, wiki_root)
        nodes.append({
            "id": node_id,
            "label": _compat_title(path),
            "group": path.parent.name,
            "path": node_id,
        })
    return nodes


def graph_data(wiki_root: Path | str) -> dict:
    root = Path(wiki_root).expanduser()
    nodes = _compat_markdown_nodes(root)
    node_ids = {node["id"] for node in nodes}
    edges: list[dict] = []
    for raw in load_edges(str(root)):
        source = str(raw.get("source") or raw.get("from") or "").strip()
        target = str(raw.get("target") or raw.get("to") or "").strip()
        relation = str(raw.get("relation") or raw.get("type") or raw.get("edge_type") or "related").strip()
        if not source or not target:
            continue
        for node_id in (source, target):
            if node_id not in node_ids:
                node_ids.add(node_id)
                nodes.append({"id": node_id, "label": node_id, "group": _node_kind(node_id) or "graph", "path": ""})
        edges.append({
            "source": source,
            "target": target,
            "relation": relation or "related",
            "operation": str(raw.get("operation") or "confirm"),
            "evidence_ids": [str(item) for item in raw.get("evidence_ids") or [] if str(item).strip()],
        })
    return {
        "schema": "autosci_web_graph.v1",
        "wiki_root": str(root.resolve()),
        "nodes": nodes,
        "edges": edges,
    }


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _compat_pop_value(argv: list[str], flag: str, default: str = "") -> tuple[list[str], str]:
    out: list[str] = []
    value = default
    skip = False
    for idx, item in enumerate(argv):
        if skip:
            skip = False
            continue
        if item == flag:
            if idx + 1 < len(argv):
                value = argv[idx + 1]
                skip = True
            continue
        out.append(item)
    return out, value


def _compat_reject_unknown(args: list[str], command: str) -> None:
    if not args:
        return
    print(
        json.dumps(
            {
                "ok": False,
                "status": "error",
                "error_type": "unsupported_cli_flag",
                "command": command,
                "unsupported_args": args,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    sys.exit(2)


def _compat_canvas_payload(data: dict) -> dict:
    nodes = []
    for index, node in enumerate(data.get("nodes") or []):
        nodes.append({
            "id": node["id"],
            "type": "text",
            "text": node.get("label") or node["id"],
            "x": (index % 6) * 260,
            "y": (index // 6) * 180,
            "width": 220,
            "height": 100,
        })
    return {
        "nodes": nodes,
        "edges": [
            {
                "id": f"edge-{index}",
                "fromNode": edge["source"],
                "toNode": edge["target"],
                "label": edge["relation"],
            }
            for index, edge in enumerate(data.get("edges") or [], start=1)
        ],
    }


def _compat_bfs_nodes(start: str, edges: list[dict], depth: int) -> set[str]:
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target:
            continue
        adj[source].append(target)
        adj[target].append(source)
    visited: set[str] = {start}
    current: set[str] = {start}
    for _ in range(max(depth, 0)):
        next_level: set[str] = set()
        for node_id in current:
            for neighbor in adj.get(node_id, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_level.add(neighbor)
        current = next_level
        if not current:
            break
    return visited


def _compat_filter_graph_data(
    data: dict,
    *,
    focus: str = "",
    depth: int = 2,
    types: str = "",
    edge_types: str = "",
) -> dict:
    type_filter = _split_filter_values(types)
    edge_type_filter = _split_filter_values(edge_types)
    nodes = [node for node in data.get("nodes") or [] if isinstance(node, dict)]
    edges = [edge for edge in data.get("edges") or [] if isinstance(edge, dict)]
    nodes_by_id = {str(node.get("id") or ""): node for node in nodes}
    if edge_type_filter:
        edges = [edge for edge in edges if str(edge.get("relation") or "related") in edge_type_filter]
    if type_filter:
        allowed_node_ids = {
            node_id
            for node_id, node in nodes_by_id.items()
            if str(node.get("group") or _node_kind(node_id)) in type_filter
        }
        edges = [
            edge
            for edge in edges
            if str(edge.get("source") or "") in allowed_node_ids
            and str(edge.get("target") or "") in allowed_node_ids
        ]
        nodes = [node for node in nodes if str(node.get("id") or "") in allowed_node_ids]
        nodes_by_id = {str(node.get("id") or ""): node for node in nodes}
    if focus:
        focus_ids = _compat_bfs_nodes(focus, edges, depth)
        edges = [
            edge
            for edge in edges
            if str(edge.get("source") or "") in focus_ids
            and str(edge.get("target") or "") in focus_ids
        ]
        nodes = [node for node in nodes if str(node.get("id") or "") in focus_ids]
        if focus in nodes_by_id and all(str(node.get("id") or "") != focus for node in nodes):
            nodes.append(nodes_by_id[focus])
    return {**data, "nodes": nodes, "edges": edges}


def _run_opensolar_json_compat(argv: list[str]) -> bool:
    if not argv:
        return False
    command = argv[0]
    if command == "graph-data":
        args, wiki_root = _compat_pop_value(argv[1:], "--wiki-root", str(default_wiki_root()))
        args, out = _compat_pop_value(args, "--out")
        args, focus = _compat_pop_value(args, "--focus")
        args, depth_text = _compat_pop_value(args, "--depth", "2")
        args, types = _compat_pop_value(args, "--types")
        args, edge_types = _compat_pop_value(args, "--edge-types")
        _compat_reject_unknown(args, command)
        try:
            depth = int(depth_text)
        except ValueError:
            depth = 2
        data = graph_data(Path(wiki_root))
        data = _compat_filter_graph_data(data, focus=focus, depth=depth, types=types, edge_types=edge_types)
        if out:
            write_json(Path(out).expanduser(), data)
        print(json.dumps({"ok": True, **data, "path": out}, ensure_ascii=False, indent=2, sort_keys=True))
        return True
    if command not in {"generate-obsidian-config", "generate-canvas"} or "--wiki-root" not in argv:
        return False

    args, wiki_root = _compat_pop_value(argv[1:], "--wiki-root", str(default_wiki_root()))
    args, out = _compat_pop_value(args, "--out")
    args, graph_out = _compat_pop_value(args, "--graph-out")
    args, focus = _compat_pop_value(args, "--focus")
    args, depth_text = _compat_pop_value(args, "--depth", "2")
    args, types = _compat_pop_value(args, "--types")
    args, edge_types = _compat_pop_value(args, "--edge-types")
    _compat_reject_unknown(args, command)
    try:
        depth = int(depth_text)
    except ValueError:
        depth = 2
    root = Path(wiki_root).expanduser()

    if command == "generate-obsidian-config":
        path = Path(out).expanduser() if out else root / ".obsidian" / "graph.json"
        app_path = path.parent / "app.json"
        payload = {
            "schema": "autosci_obsidian_graph_config.v1",
            "collapse-filter": False,
            "search": "",
            "showTags": True,
            "showAttachments": True,
            "hideUnresolved": False,
            "showOrphans": True,
            "colorGroups": [
                {"query": f"path:{entity}", "color": {"a": 1, "rgb": 3381759 + index * 1000}}
                for index, entity in enumerate(ENTITY_DIRS)
            ],
        }
        write_json(path, payload)
        app_created = False
        if not app_path.exists():
            write_json(
                app_path,
                {
                    "strictLineBreaks": False,
                    "showFrontmatter": False,
                    "defaultViewMode": "source",
                    "livePreview": True,
                },
            )
            app_created = True
        print(json.dumps({
            "ok": True,
            "path": str(path),
            "app_path": str(app_path),
            "app_created": app_created,
            "schema": payload["schema"],
        }, ensure_ascii=False, sort_keys=True))
        return True

    data = graph_data(root)
    data = _compat_filter_graph_data(data, focus=focus, depth=depth, types=types, edge_types=edge_types)
    canvas = _compat_canvas_payload(data)
    canvas_path = Path(out).expanduser() if out else root / DERIVED_DIR / "autosci.canvas"
    write_json(canvas_path, canvas)
    graph_path = Path(graph_out).expanduser() if graph_out else REPO_ROOT / "app" / "data" / "graph.json"
    write_json(graph_path, data)
    print(json.dumps({
        "ok": True,
        "path": str(canvas_path),
        "graph_data": str(graph_path),
        "nodes": len(data.get("nodes") or []),
        "edges": len(data.get("edges") or []),
    }, ensure_ascii=False, sort_keys=True))
    return True


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main() -> None:
    if _run_opensolar_json_compat(sys.argv[1:]):
        return

    parser = argparse.ArgumentParser(
        description="OmegaWiki Visualization Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # generate-obsidian-config
    p_obs = subparsers.add_parser("generate-obsidian-config",
                                  help="Write .obsidian/graph.json with entity-type color groups")
    p_obs.add_argument("wiki_root", help="Path to wiki/ directory")

    # generate-canvas
    p_canvas = subparsers.add_parser("generate-canvas",
                                     help="Generate Obsidian Canvas from graph data")
    p_canvas.add_argument("wiki_root", help="Path to wiki/ directory")
    p_canvas.add_argument("--focus", help="Center canvas on a specific node (e.g., methods/my-method)")
    p_canvas.add_argument("--depth", type=int, default=2, help="BFS depth for focused canvas (default: 2)")
    p_canvas.add_argument("--types", help="Comma-separated node/page types to include")
    p_canvas.add_argument("--edge-types", help="Comma-separated edge types to include")
    p_canvas.add_argument("--output", help="Custom output path")

    # list-recommendations
    subparsers.add_parser("list-recommendations",
                          help="Print recommended Obsidian plugins and setup instructions")

    args = parser.parse_args()

    if args.command == "generate-obsidian-config":
        cmd_generate_obsidian_config(args.wiki_root)
    elif args.command == "generate-canvas":
        cmd_generate_canvas(
            args.wiki_root,
            focus=args.focus,
            depth=args.depth,
            output=args.output,
            types=args.types,
            edge_types=args.edge_types,
        )
    elif args.command == "list-recommendations":
        cmd_list_recommendations()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
