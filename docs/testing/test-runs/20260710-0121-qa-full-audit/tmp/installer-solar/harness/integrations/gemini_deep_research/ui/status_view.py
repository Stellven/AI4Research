"""U2 — status UI surfacing for the Gemini Deep Research epic.

Read-only assembly of:
- the epic -> child-sprint -> DAG-node tree (from *.status.json + *.task_graph.json),
- capability usage per sprint (required_capabilities aggregated from task graphs),
- blocker reasons (sprint history `blocked_by` + DR run waiting_human projections).

Pure projection over existing harness artifacts; writes nothing, so existing
status/wake/dispatch behavior is unchanged.
"""

from __future__ import annotations

import glob
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HARNESS_DIR = Path(__file__).resolve().parents[3]
_SPRINTS = _HARNESS_DIR / "sprints"
for _p in (str(_HARNESS_DIR / "lib"), str(_HARNESS_DIR / "lib" / "capabilities")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@dataclass
class NodeView:
    node_id: str
    status: str
    gate: str | None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class SprintView:
    sprint_id: str
    title: str
    status: str
    phase: str | None
    blockers: list[str] = field(default_factory=list)
    nodes: list[NodeView] = field(default_factory=list)

    @property
    def capabilities(self) -> list[str]:
        seen: list[str] = []
        for n in self.nodes:
            for c in n.capabilities:
                if c not in seen:
                    seen.append(c)
        return seen


@dataclass
class EpicTree:
    epic_id: str
    sprints: list[SprintView] = field(default_factory=list)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _node_status(graph: dict[str, Any], node_id: str, declared: str) -> str:
    nr = graph.get("node_results", {}).get(node_id, {})
    return nr.get("status", declared)


def _is_waiting(status: dict[str, Any]) -> bool:
    """True only when the sprint is genuinely waiting, not merely mid-build.

    Avoids surfacing a stale historical `blocked_by` on a sprint that has since
    been activated (status active / phase planning_complete).
    """
    st = str(status.get("status", "")).lower()
    phase = str(status.get("phase", "")).lower()
    if st in ("queued", "blocked", "waiting", "waiting_human"):
        return True
    return any(k in phase for k in ("waiting", "blocked", "dependency"))


def _extract_blockers(status: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not _is_waiting(status):
        return blockers
    history = status.get("history", []) or []
    for ev in reversed(history):
        bb = ev.get("blocked_by")
        if bb:
            blockers.append("blocked_by:" + ",".join(b.split("-")[-1] for b in bb))
            break
    return blockers


def build_sprint_view(sprint_id: str) -> SprintView | None:
    status_path = _SPRINTS / f"{sprint_id}.status.json"
    if not status_path.exists():
        return None
    status = _read_json(status_path)
    graph = _read_json(_SPRINTS / f"{sprint_id}.task_graph.json")
    nodes: list[NodeView] = []
    for n in graph.get("nodes", []):
        nodes.append(
            NodeView(
                node_id=n["id"],
                status=_node_status(graph, n["id"], n.get("status", "pending")),
                gate=n.get("gate"),
                capabilities=list(n.get("required_capabilities", [])),
            )
        )
    return SprintView(
        sprint_id=sprint_id,
        title=status.get("title", ""),
        status=status.get("status", "unknown"),
        phase=status.get("phase"),
        blockers=_extract_blockers(status),
        nodes=nodes,
    )


def build_epic_tree(epic_id: str) -> EpicTree:
    tree = EpicTree(epic_id=epic_id)
    seen: set[str] = set()
    for p in sorted(glob.glob(str(_SPRINTS / "*.status.json"))):
        st = _read_json(Path(p))
        if st.get("epic_id") != epic_id:
            continue
        sid = st.get("sprint_id") or Path(p).stem.replace(".status", "")
        if sid in seen:
            continue
        seen.add(sid)
        sv = build_sprint_view(sid)
        if sv:
            tree.sprints.append(sv)
    return tree


def render_text(tree: EpicTree) -> str:
    lines = [f"EPIC {tree.epic_id}"]
    for sp in tree.sprints:
        slug = sp.sprint_id.split("-2-")[-1] if "-2-" in sp.sprint_id else sp.sprint_id[-20:]
        lines.append(f"  └─ [{sp.status}] {slug}  ({sp.phase or '-'})")
        for n in sp.nodes:
            caps = ("  caps=" + ",".join(n.capabilities)) if n.capabilities else ""
            lines.append(f"        • {n.node_id} [{n.status}] gate={n.gate}{caps}")
        for b in sp.blockers:
            lines.append(f"        ! BLOCKER: {b}")
    return "\n".join(lines)


def render_run_blockers(run_ref: str, event_log: Any) -> dict[str, Any]:
    """Surface a single DR run's blocker via the C3 status projection."""
    from gemini_deep_research.compat import project_status

    return project_status(run_ref, event_log)


def to_dict(tree: EpicTree) -> dict[str, Any]:
    return {
        "epic_id": tree.epic_id,
        "sprints": [
            {
                "sprint_id": sp.sprint_id,
                "status": sp.status,
                "phase": sp.phase,
                "capabilities": sp.capabilities,
                "blockers": sp.blockers,
                "nodes": [
                    {"node_id": n.node_id, "status": n.status, "gate": n.gate}
                    for n in sp.nodes
                ],
            }
            for sp in tree.sprints
        ],
    }
