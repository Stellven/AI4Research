#!/usr/bin/env python3
"""Solar evolution engine: score, evaluate, promote, and demote capabilities."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
STATE_DB = Path(os.environ.get("HARNESS_STATE_DB", HARNESS_DIR / "run" / "state.db"))

sys.path.insert(0, str(HARNESS_DIR / "lib"))
from capability_registry import LEVEL_REVERSE, _open_db as open_capability_db  # type: ignore  # noqa: E402
from eval_runner import run_pack  # type: ignore  # noqa: E402
from failure_miner import mine as mine_failures  # type: ignore  # noqa: E402
try:
    from runtime_bridge import record_legacy_event  # type: ignore  # noqa: E402
except Exception:
    record_legacy_event = None  # type: ignore

LEVEL_RANK = {"dead_end": 1, "basic_usable": 2, "default_usable": 3, "closed_loop": 4}
RANK_LEVEL = {v: k for k, v in LEVEL_RANK.items()}
RUNTIME_BONUS = {
    "full_runtime_usable": 0.75,
    "runtime_usable": 0.50,
    "basic_usable": 0.0,
    "pending": -0.25,
}
EVENTS_FILE = HARNESS_DIR / "events" / "all.jsonl"
SPRINTS_DIR = HARNESS_DIR / "sprints"


def _now() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn() -> sqlite3.Connection:
    conn = open_capability_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS capability_scorecards (
        capability TEXT NOT NULL,
        provider TEXT NOT NULL,
        score REAL NOT NULL,
        level TEXT NOT NULL,
        status TEXT NOT NULL,
        eval_passed INTEGER NOT NULL DEFAULT 0,
        regression_passed INTEGER NOT NULL DEFAULT 0,
        failures INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        payload TEXT,
        PRIMARY KEY (capability, provider)
    );
    CREATE TABLE IF NOT EXISTS evolution_experiments (
        id TEXT PRIMARY KEY,
        capability TEXT NOT NULL,
        hypothesis TEXT NOT NULL,
        before_score REAL NOT NULL,
        after_score REAL NOT NULL,
        verdict TEXT NOT NULL,
        rollback TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload TEXT
    );
    """)
    conn.commit()
    return conn


def _load_external_health() -> dict[str, dict[str, Any]]:
    """Map provider/capability names to health probe evidence.

    This is intentionally fail-open: evolution scoring should still work if the
    UI health probe is slow or temporarily unavailable.
    """
    probe = HARNESS_DIR / "lib" / "external-integrations-health.py"
    if not probe.exists():
        return {}
    try:
        proc = subprocess.run(
            ["python3", str(probe), "--json", "--max-age", "120"],
            text=True,
            capture_output=True,
            timeout=15,
        )
        if proc.returncode != 0:
            return {}
        data = json.loads(proc.stdout)
    except Exception:
        return {}

    out: dict[str, dict[str, Any]] = {}
    aliases = {
        "ruflo": ["ruflo"],
        "gstack": ["gstack"],
        "superpowers": ["superpowers"],
        "browser-use": ["browser-use"],
        "codex-bridge": ["codex bridge", "pane3 bridge"],
        "openai-agents-python": ["openai-agents-python"],
        "empirical-research": ["empirical research"],
        "addy-agent-skills": ["addyosmani/agent-skills", "agent-skills"],
        "markitdown": ["markitdown"],
        "owl": ["camel-ai/owl", "owl"],
        "agency-agents": ["agency-agents persona"],
        "mirage": ["mirage"],
        "qmd": ["qmd"],
        "mineru": ["mineru"],
        "obsidian": ["obsidian-wiki"],
    }
    for item in data.get("integrations", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).lower()
        evidence = item.get("evidence", {}) if isinstance(item.get("evidence"), dict) else {}
        cap = str(evidence.get("dispatch_capability", "")).strip()
        if cap:
            out[f"cap:{cap}"] = item
        for provider, needles in aliases.items():
            if any(needle in name for needle in needles):
                out[f"provider:{provider}"] = item
    return out


def _health_for(provider: str, capability: str, health: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return health.get(f"cap:{capability}") or health.get(f"provider:{provider}") or {}


def _effective_level(registry_level: str, health_item: dict[str, Any]) -> str:
    health_level = str(health_item.get("status_label") or "")
    if LEVEL_RANK.get(health_level, 0) > LEVEL_RANK.get(registry_level, 0):
        return health_level
    return registry_level


def _runtime_bonus(health_item: dict[str, Any]) -> float:
    evidence = health_item.get("evidence", {}) if isinstance(health_item.get("evidence"), dict) else {}
    runtime_level = str(evidence.get("runtime_level") or "")
    bonus = RUNTIME_BONUS.get(runtime_level, 0.0)
    if health_item.get("status") == "ok":
        bonus += 0.10
    health = health_item.get("health", {}) if isinstance(health_item.get("health"), dict) else {}
    if health.get("complete_closed_loop") == "ok":
        bonus += 0.15
    if health.get("dead_ends") == "warn" or health_item.get("dead_ends"):
        bonus -= 0.50
    return bonus


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_event(sprint_id: str, event: str, severity: str, payload: dict[str, Any]) -> None:
    obj = {
        "ts": _now(),
        "sprint_id": sprint_id,
        "actor": "solar-evolution-engine",
        "event": event,
        "severity": severity,
        "data": payload,
    }
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    if sprint_id:
        sprint_events = SPRINTS_DIR / f"{sprint_id}.events.jsonl"
        with sprint_events.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        if record_legacy_event is not None:
            try:
                # Bridge sprint-scoped legacy events into session-log v2 so
                # evolution telemetry cannot drift away from runtime state.
                record_legacy_event(
                    sprint_id,
                    event,
                    "solar-evolution-engine",
                    {"severity": severity, **payload},
                    harness_dir=HARNESS_DIR,
                )
            except Exception:
                pass


def _event_counts(event_names: set[str]) -> dict[str, int]:
    counts = {name: 0 for name in event_names}
    if not EVENTS_FILE.exists():
        return counts
    for line in EVENTS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        name = str(item.get("event") or item.get("event_type") or "")
        if name in counts:
            counts[name] += 1
    return counts


def _node_requires_deepresearch_quality_gate(node: dict[str, Any]) -> bool:
    explicit = node.get("research_quality_gate_required")
    if explicit is False:
        return False
    if explicit is True:
        return True
    caps: set[str] = set()
    for key in ("required_capabilities", "capabilities"):
        raw = node.get(key, [])
        if isinstance(raw, str):
            caps.add(raw)
        elif isinstance(raw, list):
            caps.update(str(item) for item in raw if str(item))
    gate_capability_re = re.compile(
        r"^research\.(?:"
        r"factuality|citation|claim(?:[_\.]|$)|evidence(?:[_\.]|$)|"
        r"report(?:[_\.](?:ast|finalize|quality|review)|_ast)|"
        r"survey(?:[_\.](?:chief_editor|finalize|quality|review))"
        r")",
        re.I,
    )
    if caps & {"citation.verify", "factuality.evaluate"}:
        return True
    if any(gate_capability_re.match(cap) for cap in caps):
        return True
    artifact_values: list[str] = []
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    artifact_values.extend(str(value) for value in artifacts.values())
    for key in (
        "research_eval",
        "research_eval_json",
        "eval_artifacts_json",
        "report_ast",
        "final_report",
        "final_md",
    ):
        if node.get(key):
            artifact_values.append(str(node.get(key)))
    raw_scope = node.get("write_scope", [])
    if isinstance(raw_scope, str):
        artifact_values.append(raw_scope)
    elif isinstance(raw_scope, list):
        artifact_values.extend(str(item) for item in raw_scope)
    artifact_text = " ".join(artifact_values).lower()
    return bool(re.search(r"research_eval|report_ast|final\.md|final_report|evidence\.jsonl|claims\.jsonl", artifact_text))


def _node_result_status(graph: dict[str, Any], node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    results = graph.get("node_results") if isinstance(graph.get("node_results"), dict) else {}
    row = results.get(node_id) if isinstance(results, dict) else {}
    if isinstance(row, dict) and row.get("status"):
        return str(row.get("status")).lower()
    return str(node.get("status") or "").lower()


def _deepresearch_quality_gate_ok(gate: dict[str, Any]) -> bool:
    return bool(gate.get("ok")) or str(gate.get("verdict") or "").upper() == "PASS"


def _deepresearch_quality_gate_scorecard() -> dict[str, Any]:
    total = ok_count = missing_terminal = failed_terminal = auto_run_count = repair_requested = 0
    examples: list[dict[str, Any]] = []
    for graph_path in sorted(SPRINTS_DIR.glob("sprint-*.task_graph.json")):
        graph = _read_json(graph_path)
        if not graph:
            continue
        sid = str(graph.get("sprint_id") or graph_path.name.removesuffix(".task_graph.json"))
        for node in graph.get("nodes", []) or []:
            if not isinstance(node, dict) or not _node_requires_deepresearch_quality_gate(node):
                continue
            status = _node_result_status(graph, node)
            if status not in {"passed", "failed"}:
                continue
            total += 1
            gate = node.get("research_quality_gate") if isinstance(node.get("research_quality_gate"), dict) else {}
            gate_ok = _deepresearch_quality_gate_ok(gate)
            if gate_ok:
                ok_count += 1
            elif gate:
                failed_terminal += 1
            else:
                missing_terminal += 1
            if gate.get("auto_run"):
                auto_run_count += 1
            if node.get("quality_gate_repair_requested_at"):
                repair_requested += 1
            if len(examples) < 8 and (not gate_ok or node.get("quality_gate_repair_requested_at")):
                examples.append({
                    "sprint_id": sid,
                    "node_id": node.get("id", ""),
                    "node_status": status,
                    "gate_ok": gate_ok,
                    "gate_verdict": gate.get("verdict", "MISSING" if not gate else ""),
                    "repair_requested_at": node.get("quality_gate_repair_requested_at", ""),
                })
    event_counts = _event_counts({
        "autopilot_deepresearch_quality_gate_repair",
        "autopilot_deepresearch_quality_gate_repair_failed",
    })
    defects = missing_terminal + failed_terminal
    coverage = round(ok_count / total, 4) if total else 1.0
    repair_count = event_counts.get("autopilot_deepresearch_quality_gate_repair", 0) + repair_requested
    repair_failures = event_counts.get("autopilot_deepresearch_quality_gate_repair_failed", 0)
    score = round(max(1.0, min(5.0, 1.0 + coverage * 3.0 + (0.5 if auto_run_count else 0.0) - min(1.0, defects * 0.2 + repair_failures * 0.25))), 2)
    level = "closed_loop" if total and defects == 0 and auto_run_count else "default_usable" if total and defects == 0 else "basic_usable" if total else "pending"
    status = "active" if defects == 0 and repair_failures == 0 else "degraded"
    return {
        "capability": "deepresearch.quality_gate",
        "provider": "solar-harness",
        "score": score,
        "level": level,
        "status": status,
        "failures": defects + repair_failures,
        "total_terminal_nodes": total,
        "ok_count": ok_count,
        "coverage": coverage,
        "missing_terminal": missing_terminal,
        "failed_terminal": failed_terminal,
        "auto_run_count": auto_run_count,
        "repair_count": repair_count,
        "repair_failures": repair_failures,
        "examples": examples,
    }


def repair_deepresearch_gates(apply: bool = False, limit: int = 0) -> dict[str, Any]:
    """Reopen terminal DeepResearch graph nodes whose quality gate is missing/bad.

    This is a historical debt migration, not a greenwashing path. It downgrades
    stale terminal nodes back to reviewing so the normal evaluator/autopilot path
    can regenerate evidence.
    """
    candidates: list[dict[str, Any]] = []
    repaired: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    touched_graphs: dict[Path, dict[str, Any]] = {}

    for graph_path in sorted(SPRINTS_DIR.glob("sprint-*.task_graph.json")):
        graph = _read_json(graph_path)
        if not graph:
            continue
        sid = str(graph.get("sprint_id") or graph_path.name.removesuffix(".task_graph.json"))
        changed = False
        for node in graph.get("nodes", []) or []:
            if not isinstance(node, dict) or not _node_requires_deepresearch_quality_gate(node):
                continue
            node_id = str(node.get("id") or "")
            status = _node_result_status(graph, node)
            if status not in {"passed", "failed"}:
                continue
            gate = node.get("research_quality_gate") if isinstance(node.get("research_quality_gate"), dict) else {}
            if gate and _deepresearch_quality_gate_ok(gate):
                continue
            gate_status = "missing" if not gate else "failed"
            item = {
                "sprint_id": sid,
                "node_id": node_id,
                "graph_path": str(graph_path),
                "node_status": status,
                "gate_status": gate_status,
            }
            candidates.append(item)
            if limit and len(repaired) >= limit:
                skipped.append({**item, "reason": "limit_reached"})
                continue
            if not apply:
                continue

            node["status"] = "reviewing"
            node["updated_at"] = _now()
            node["quality_gate_repair_requested_at"] = _now()
            node["quality_gate_repair_reason"] = gate_status
            node.pop("research_quality_gate", None)
            node.pop("eval_assigned_to", None)
            node.pop("eval_dispatch_id", None)
            node.pop("eval_dispatched_at", None)

            node_results = graph.get("node_results") if isinstance(graph.get("node_results"), dict) else {}
            if not isinstance(node_results, dict):
                node_results = {}
            result = node_results.get(node_id) if isinstance(node_results.get(node_id), dict) else {}
            result["status"] = "reviewing"
            result["gate_status"] = "reviewing"
            result["updated_at"] = _now()
            result["note"] = "evolution engine reopened DeepResearch quality gate debt"
            result.pop("research_quality_gate", None)
            node_results[node_id] = result
            graph["node_results"] = node_results
            graph["updated_at"] = _now()
            changed = True
            repaired.append(item)
            _append_event(sid, "evolution_deepresearch_quality_gate_repair_requested", "warn", item)
        if changed:
            touched_graphs[graph_path] = graph

    if apply:
        for graph_path, graph in touched_graphs.items():
            _write_json(graph_path, graph)

    return {
        "ok": True,
        "apply": apply,
        "limit": limit,
        "candidate_count": len(candidates),
        "repaired_count": len(repaired),
        "skipped_count": len(skipped),
        "candidates": candidates,
        "repaired": repaired,
        "skipped": skipped,
    }


def _deepresearch_repair_original_status(sprint_id: str, node_id: str) -> str:
    status = ""
    for path in (SPRINTS_DIR / f"{sprint_id}.events.jsonl", EVENTS_FILE):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if str(item.get("event") or "") != "evolution_deepresearch_quality_gate_repair_requested":
                continue
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            if str(data.get("sprint_id") or item.get("sprint_id") or "") != sprint_id:
                continue
            if str(data.get("node_id") or "") != node_id:
                continue
            status = str(data.get("node_status") or status or "").lower()
    return status if status in {"passed", "failed", "skipped"} else "passed"


def restore_nonrequired_deepresearch_repairs(apply: bool = False, limit: int = 0) -> dict[str, Any]:
    """Undo over-broad historical repairs after gate classification tightens."""
    candidates: list[dict[str, Any]] = []
    restored: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    touched_graphs: dict[Path, dict[str, Any]] = {}

    for graph_path in sorted(SPRINTS_DIR.glob("sprint-*.task_graph.json")):
        graph = _read_json(graph_path)
        if not graph:
            continue
        sid = str(graph.get("sprint_id") or graph_path.name.removesuffix(".task_graph.json"))
        changed = False
        for node in graph.get("nodes", []) or []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "")
            if not node_id or not node.get("quality_gate_repair_requested_at"):
                continue
            if _node_requires_deepresearch_quality_gate(node):
                continue
            current = _node_result_status(graph, node)
            if current != "reviewing":
                continue
            original_status = _deepresearch_repair_original_status(sid, node_id)
            item = {
                "sprint_id": sid,
                "node_id": node_id,
                "graph_path": str(graph_path),
                "current_status": current,
                "restored_status": original_status,
            }
            candidates.append(item)
            if limit and len(restored) >= limit:
                skipped.append({**item, "reason": "limit_reached"})
                continue
            if not apply:
                continue

            node["status"] = original_status
            node["updated_at"] = _now()
            node["quality_gate_repair_restored_at"] = _now()
            node["quality_gate_repair_restored_reason"] = "quality_gate_not_required_after_classifier_tightening"
            node.pop("quality_gate_repair_requested_at", None)
            node.pop("quality_gate_repair_reason", None)

            node_results = graph.get("node_results") if isinstance(graph.get("node_results"), dict) else {}
            if not isinstance(node_results, dict):
                node_results = {}
            result = node_results.get(node_id) if isinstance(node_results.get(node_id), dict) else {}
            result["status"] = original_status
            result["gate_status"] = original_status
            result["updated_at"] = _now()
            result["note"] = "evolution engine restored node after DeepResearch gate classifier tightening"
            node_results[node_id] = result
            graph["node_results"] = node_results
            graph["updated_at"] = _now()
            changed = True
            restored.append(item)
            _append_event(sid, "evolution_deepresearch_quality_gate_repair_restored", "info", item)
        if changed:
            touched_graphs[graph_path] = graph

    if apply:
        for graph_path, graph in touched_graphs.items():
            _write_json(graph_path, graph)

    return {
        "ok": True,
        "apply": apply,
        "limit": limit,
        "candidate_count": len(candidates),
        "restored_count": len(restored),
        "skipped_count": len(skipped),
        "candidates": candidates,
        "restored": restored,
        "skipped": skipped,
    }


def _write_scorecard_row(conn: sqlite3.Connection, item: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO capability_scorecards
           (capability, provider, score, level, status, failures, updated_at, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(capability, provider) DO UPDATE SET
             score=excluded.score, level=excluded.level, status=excluded.status,
             failures=excluded.failures, updated_at=excluded.updated_at, payload=excluded.payload""",
        (
            item["capability"],
            item["provider"],
            float(item["score"]),
            item["level"],
            item["status"],
            int(item.get("failures", 0)),
            _now(),
            json.dumps(item, ensure_ascii=False),
        ),
    )


def scorecard(write: bool = True) -> dict[str, Any]:
    conn = _conn()
    rows = conn.execute(
        "SELECT capability, provider, level, status FROM plugin_capabilities WHERE status='active'"
    ).fetchall()
    failures = mine_failures(limit=20)
    failure_count = int(failures.get("failures", 0))
    health = _load_external_health()
    entries = []
    for row in rows:
        level_int = int(row["level"])
        registry_level = LEVEL_REVERSE.get(level_int, "dead_end")
        health_item = _health_for(str(row["provider"]), str(row["capability"]), health)
        level = _effective_level(registry_level, health_item)
        level_int = LEVEL_RANK.get(level, level_int)
        penalty = min(1.0, failure_count / 200.0)
        runtime_bonus = _runtime_bonus(health_item)
        score = max(1.0, min(5.0, round(float(level_int) + runtime_bonus - penalty, 2)))
        status = "active" if score >= 2 else "degraded"
        evidence = health_item.get("evidence", {}) if isinstance(health_item.get("evidence"), dict) else {}
        item = {
            "capability": row["capability"],
            "provider": row["provider"],
            "score": score,
            "level": level,
            "registry_level": registry_level,
            "runtime_level": evidence.get("runtime_level", ""),
            "runtime_backend": evidence.get("runtime_backend", ""),
            "runtime_version": evidence.get("runtime_version", ""),
            "health_status": health_item.get("status", ""),
            "health_label": health_item.get("status_label", ""),
            "status": status,
            "failures": failure_count,
        }
        entries.append(item)
        if write:
            _write_scorecard_row(conn, item)
    deepresearch_gate = _deepresearch_quality_gate_scorecard()
    entries.append(deepresearch_gate)
    if write:
        _write_scorecard_row(conn, deepresearch_gate)
    conn.commit()
    conn.close()
    weighted = round(sum(item["score"] for item in entries) / max(len(entries), 1), 2)
    return {"ok": True, "total": len(entries), "weighted_score": weighted, "scorecards": entries}


def promote(capability: str, eval_pass: bool, regression_pass: bool) -> dict[str, Any]:
    if not eval_pass or not regression_pass:
        return {
            "ok": False,
            "promoted": False,
            "capability": capability,
            "reason": "promotion_requires_eval_pass_and_regression_pass",
        }
    conn = _conn()
    conn.execute(
        """UPDATE capability_scorecards
           SET status='promoted', eval_passed=1, regression_passed=1, updated_at=?
           WHERE capability=?""",
        (_now(), capability),
    )
    changed = conn.total_changes
    conn.commit()
    conn.close()
    return {"ok": True, "promoted": changed > 0, "capability": capability}


def demote_degraded(threshold: float = 2.0) -> dict[str, Any]:
    conn = _conn()
    rows = conn.execute(
        "SELECT capability, provider, score, level FROM capability_scorecards WHERE score < ?",
        (threshold,),
    ).fetchall()
    demoted = []
    for row in rows:
        conn.execute(
            "UPDATE capability_scorecards SET status='demoted', updated_at=? WHERE capability=? AND provider=?",
            (_now(), row["capability"], row["provider"]),
        )
        demoted.append({"capability": row["capability"], "provider": row["provider"], "score": row["score"]})
    conn.commit()
    conn.close()
    return {"ok": True, "demoted": demoted, "count": len(demoted)}


def recommend(capability: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Return runtime-aware capability recommendations for dispatch/autopilot."""
    latest = scorecard(write=True)
    cards = latest.get("scorecards", [])
    if capability:
        cards = [item for item in cards if item.get("capability") == capability]
    cards = sorted(cards, key=lambda item: (-float(item.get("score", 0)), str(item.get("provider", ""))))[:limit]
    return {
        "ok": True,
        "capability": capability or "",
        "count": len(cards),
        "recommendations": cards,
        "generated_at": _now(),
    }


def run_loop(pack: str) -> dict[str, Any]:
    before = scorecard(write=True)
    clusters = mine_failures(limit=1)
    eval_result = run_pack(pack)
    regression_passed = bool(eval_result.get("ok"))
    eval_passed = bool(eval_result.get("ok"))
    cap = "vfs.search"
    promotion = promote(cap, eval_pass=eval_passed, regression_pass=regression_passed)
    after = scorecard(write=True)
    exp_id = f"exp-{_now().replace(':', '').replace('-', '')}-s5"
    hypothesis = "If S4 extension and Mirage regressions pass, promote vfs.search as a stable default capability."
    rollback = "solar-harness integrations disable mirage; restore previous product snapshot if regression fails."
    conn = _conn()
    conn.execute(
        """INSERT OR REPLACE INTO evolution_experiments
           (id, capability, hypothesis, before_score, after_score, verdict, rollback, updated_at, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            exp_id,
            cap,
            hypothesis,
            float(before.get("weighted_score", 0)),
            float(after.get("weighted_score", 0)),
            "promoted" if promotion.get("promoted") else "evaluated",
            rollback,
            _now(),
            json.dumps({"clusters": clusters, "eval": eval_result, "promotion": promotion}, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    return {
        "ok": bool(eval_result.get("ok")) and bool(promotion.get("ok")),
        "experiment_id": exp_id,
        "clusters": clusters,
        "eval": eval_result,
        "promotion": promotion,
        "before": before,
        "after": after,
    }


def status() -> dict[str, Any]:
    conn = _conn()
    rows = conn.execute(
        "SELECT capability, provider, score, level, status, failures, updated_at, payload FROM capability_scorecards ORDER BY score DESC, capability LIMIT 80"
    ).fetchall()
    critical_rows = conn.execute(
        """SELECT capability, provider, score, level, status, failures, updated_at, payload
           FROM capability_scorecards
           WHERE status IN ('degraded', 'demoted')
              OR capability IN ('deepresearch.quality_gate')
           ORDER BY score ASC, capability
           LIMIT 20"""
    ).fetchall()
    experiments = conn.execute(
        "SELECT id, capability, verdict, updated_at FROM evolution_experiments ORDER BY updated_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    seen = {(row["capability"], row["provider"]) for row in rows}
    rows = list(rows) + [row for row in critical_rows if (row["capability"], row["provider"]) not in seen]
    scorecards = []
    for row in rows:
        item = dict(row)
        payload = item.pop("payload", "")
        try:
            if payload:
                extra = json.loads(payload)
                item.update({k: v for k, v in extra.items() if k not in item or item[k] in ("", None)})
        except Exception:
            item["payload_error"] = "invalid_json"
        scorecards.append(item)
    return {
        "ok": True,
        "scorecards": scorecards,
        "experiments": [dict(r) for r in experiments],
        "total_scorecards": len(rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="evolution_engine.py")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("scorecard").add_argument("--json", action="store_true")
    p = sub.add_parser("recommend")
    p.add_argument("--capability", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("run-loop")
    p.add_argument("--pack", default=str(HARNESS_DIR / "evals" / "packs" / "s5-basic" / "eval.json"))
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("promote")
    p.add_argument("--capability", required=True)
    p.add_argument("--eval-pass", action="store_true")
    p.add_argument("--regression-pass", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("demote-degraded")
    p.add_argument("--threshold", type=float, default=2.0)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("repair-deepresearch-gates")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("restore-nonrequired-deepresearch-repairs")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--json", action="store_true")
    sub.add_parser("status").add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd == "scorecard":
        data = scorecard(write=True)
    elif args.cmd == "recommend":
        data = recommend(args.capability or None, args.limit)
    elif args.cmd == "run-loop":
        data = run_loop(args.pack)
    elif args.cmd == "promote":
        data = promote(args.capability, args.eval_pass, args.regression_pass)
    elif args.cmd == "demote-degraded":
        data = demote_degraded(args.threshold)
    elif args.cmd == "repair-deepresearch-gates":
        data = repair_deepresearch_gates(apply=args.apply, limit=args.limit)
    elif args.cmd == "restore-nonrequired-deepresearch-repairs":
        data = restore_nonrequired_deepresearch_repairs(apply=args.apply, limit=args.limit)
    elif args.cmd == "status":
        data = status()
    else:
        ap.print_help()
        return 1
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False))
    return 0 if data.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
