"""Query layer for Solar Experience Memory.

Returns top success and failure memories with match reasons.
p95 < 100ms target (deterministic SQLite queries).
"""
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

from .index import init_db, query_by_trigger, query_by_pattern, query_fts, stats as index_stats

logger = logging.getLogger(__name__)

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")


def _make_trigger_sig_from_sid(sid: str) -> Optional[str]:
    """Derive trigger sig from a sprint's status.json."""
    import json as _json
    path = os.path.join(SPRINTS_DIR, f"{sid}.status.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = _json.load(f)
        parts = [
            data.get("status", ""),
            data.get("phase", ""),
            str(data.get("round", 0)),
        ]
        triggers = data.get("triggers", [])
        if isinstance(triggers, list):
            parts.extend(triggers)
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    except Exception as e:
        logger.warning("could not derive trigger_sig for %s: %s", sid, e)
        return None


def _load_status_for_question(sid: str) -> Dict[str, Any]:
    path = os.path.join(SPRINTS_DIR, f"{sid}.status.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _should_include_mia(include_mia: Optional[bool]) -> bool:
    if include_mia is not None:
        return include_mia
    raw = os.environ.get("SOLAR_EXPERIENCE_MIA", "1").strip().lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def _mia_for_question(question: str, limit: int) -> Dict[str, Any]:
    try:
        from . import mia_adapter

        return mia_adapter.memory_context(question, limit=limit)
    except Exception as exc:
        return {"ok": False, "status": "adapter_error", "reason": str(exc)[:300]}


def query_for_sprint(sid: str, limit: int = 5, include_mia: Optional[bool] = None) -> Dict[str, Any]:
    """Main query API. Returns top success and failure memories for a sprint.

    Result format: {"sid": ..., "memories": [...], "ok": true}
    """
    init_db()
    trigger_sig = _make_trigger_sig_from_sid(sid)

    results = []

    if trigger_sig:
        # Exact trigger match first
        exact = query_by_trigger(trigger_sig, limit=limit)
        for r in exact:
            results.append({**r, "match_reason": "trigger_sig_exact"})

    # Always include terminal_phase_wake + status_corruption advisories
    for pattern in ("terminal_phase_wake", "status_corruption", "mis_dispatch",
                    "c_u_storm", "queue_block"):
        if len(results) >= limit * 2:
            break
        rows = query_by_pattern(pattern, limit=2)
        for r in rows:
            if not any(x["entry_id"] == r["entry_id"] for x in results):
                results.append({**r, "match_reason": f"pattern:{pattern}"})

    # Include success workflows
    success = query_by_pattern("success_workflow", limit=2)
    for r in success:
        if not any(x["entry_id"] == r["entry_id"] for x in results):
            results.append({**r, "match_reason": "success_workflow"})

    # Deserialize tags/source_sids JSON strings
    for r in results:
        for field in ("tags", "source_sids"):
            if isinstance(r.get(field), str):
                try:
                    r[field] = json.loads(r[field])
                except Exception:
                    r[field] = []

    result = {
        "sid": sid,
        "memories": results[:limit * 2],
        "backend": "sqlite_fts",
        "ok": True,
    }
    if _should_include_mia(include_mia):
        status_data = _load_status_for_question(sid)
        question_parts = [
            f"Sprint {sid}",
            f"status={status_data.get('status', '')}",
            f"phase={status_data.get('phase', '')}",
            f"handoff_to={status_data.get('handoff_to', '')}",
            str(status_data.get("title") or status_data.get("summary") or ""),
        ]
        result["mia"] = _mia_for_question(" | ".join(p for p in question_parts if p), limit)
        result["backend"] = "mia+sqlite_fts" if result["mia"].get("ok") else "sqlite_fts"
    return result


def query_fts_memories(query_text: str, limit: int = 10, include_mia: Optional[bool] = None) -> Dict[str, Any]:
    """FTS query returning matching memories."""
    init_db()
    rows = query_fts(query_text, limit=limit)
    for r in rows:
        for field in ("tags", "source_sids"):
            if isinstance(r.get(field), str):
                try:
                    r[field] = json.loads(r[field])
                except Exception:
                    r[field] = []
    result = {"query": query_text, "memories": rows, "backend": "sqlite_fts", "ok": True}
    if _should_include_mia(include_mia):
        result["mia"] = _mia_for_question(query_text, limit)
        result["backend"] = "mia+sqlite_fts" if result["mia"].get("ok") else "sqlite_fts"
    return result


def get_stats() -> Dict[str, Any]:
    """Return aggregate statistics."""
    init_db()
    return index_stats()
