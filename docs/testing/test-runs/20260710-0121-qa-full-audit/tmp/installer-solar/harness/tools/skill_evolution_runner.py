#!/usr/bin/env python3
"""Harness-native skill evolution runner.

This runner connects skill healthcheck, MemRL feedback, SkillRL-style
trajectory gating, eval packs, and promotion/demotion records into one
auditable state machine. It is intentionally conservative: by default it
records proposed evolutions and blocks stable promotion unless all gates pass.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
STATE_DB = Path(os.environ.get("HARNESS_STATE_DB", HARNESS_DIR / "run" / "state.db"))
RUN_LOG = HARNESS_DIR / "logs" / "skill-evolution-runs.jsonl"
STATE_DIR = HARNESS_DIR / "state" / "skill-evolution"
# The runner must not default to the skill-healthcheck-evolution pack because
# that pack itself tests the runner. Use the small base pack to avoid recursive
# eval spawning.
DEFAULT_EVAL_PACK = HARNESS_DIR / "evals" / "packs" / "s5-basic" / "eval.json"

sys.path.insert(0, str(HARNESS_DIR / "lib"))
import skill_healthcheck  # type: ignore  # noqa: E402
from eval_runner import run_pack  # type: ignore  # noqa: E402


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug_ts(ts: str) -> str:
    return ts.replace("-", "").replace(":", "").replace("Z", "Z")


def _conn() -> sqlite3.Connection:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS skill_evolution_runs (
            id TEXT PRIMARY KEY,
            candidate TEXT NOT NULL,
            phase TEXT NOT NULL,
            verdict TEXT NOT NULL,
            reward REAL NOT NULL DEFAULT 0,
            promoted INTEGER NOT NULL DEFAULT 0,
            demoted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            payload TEXT
        );
        CREATE TABLE IF NOT EXISTS skill_evolution_registry (
            skill TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            last_run_id TEXT,
            last_reward REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            payload TEXT
        );
        """
    )
    conn.commit()
    return conn


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def _run_healthcheck(update_memrl: bool, no_remote: bool) -> dict[str, Any]:
    args = SimpleNamespace(
        json=True,
        force=True,
        allow_daytime=False,
        allow_battery=False,
        no_remote=no_remote,
        update_memrl=update_memrl,
    )
    return skill_healthcheck.run_healthcheck(args)


def _candidate_by_name(health: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in health.get("skill_candidates", []):
        if item.get("name") == name:
            return item
    return None


def _select_candidates(health: dict[str, Any], selector: str, limit: int) -> list[dict[str, Any]]:
    candidates = list(health.get("skill_candidates", []))
    if selector and selector not in {"auto", "all"}:
        item = _candidate_by_name(health, selector)
        return [item] if item else []
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    candidates.sort(key=lambda c: (priority_rank.get(str(c.get("priority")), 9), not bool(c.get("exists")), -int(c.get("hit_count", 0))))
    if selector == "all":
        return candidates[:limit]
    return candidates[:1]


def _promotion_decision(candidate: dict[str, Any], health: dict[str, Any], eval_result: dict[str, Any]) -> dict[str, Any]:
    gate = health.get("evolution_gate", {}) if isinstance(health.get("evolution_gate"), dict) else {}
    blockers: list[str] = []
    if not candidate:
        blockers.append("candidate_not_found")
    if not candidate.get("exists"):
        blockers.append("candidate_skill_not_implemented")
    if not health.get("memrl_status", {}).get("ready"):
        blockers.append("memrl_not_ready")
    if not health.get("evolution_engine", {}).get("ok"):
        blockers.append("evolution_engine_not_ok")
    if gate.get("regressions"):
        blockers.extend(str(x) for x in gate.get("regressions", []))
    if not eval_result.get("ok"):
        blockers.append("eval_pack_failed")
    promoted = not blockers
    reward = 1.0 if promoted else (0.5 if eval_result.get("ok") and not gate.get("regressions") else 0.0)
    verdict = "promoted" if promoted else "proposed"
    if gate.get("regressions") or not eval_result.get("ok"):
        verdict = "blocked"
    gate_blockers = set(gate.get("promotion_blockers") or [])
    if eval_result.get("ok"):
        gate_blockers.discard("external_eval_pack_not_passed")
    effective_gate = {
        "promotion_allowed": promoted,
        "promotion_blockers": sorted(gate_blockers | set(blockers)),
        "external_eval_ok": bool(eval_result.get("ok")),
        "raw_promotion_allowed": bool(gate.get("promotion_allowed")),
    }
    return {
        "promoted": promoted,
        "verdict": verdict,
        "reward": reward,
        "blockers": sorted(set(blockers)),
        "effective_gate": effective_gate,
        "policy": "stable promotion requires implemented skill, MemRL ready, evolution engine ok, no regression, and eval pack pass",
    }


def _persist_run(run: dict[str, Any]) -> None:
    conn = _conn()
    conn.execute(
        """INSERT OR REPLACE INTO skill_evolution_runs
           (id, candidate, phase, verdict, reward, promoted, demoted, updated_at, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run["id"],
            run["candidate"],
            run["phase"],
            run["verdict"],
            float(run.get("reward", 0)),
            1 if run.get("promoted") else 0,
            1 if run.get("demoted") else 0,
            run["ts"],
            json.dumps(run, ensure_ascii=False),
        ),
    )
    status = "stable" if run.get("promoted") else "candidate" if run.get("verdict") == "proposed" else "blocked"
    conn.execute(
        """INSERT INTO skill_evolution_registry
           (skill, status, last_run_id, last_reward, updated_at, payload)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(skill) DO UPDATE SET
             status=excluded.status,
             last_run_id=excluded.last_run_id,
             last_reward=excluded.last_reward,
             updated_at=excluded.updated_at,
             payload=excluded.payload""",
        (
            run["candidate"],
            status,
            run["id"],
            float(run.get("reward", 0)),
            run["ts"],
            json.dumps(run, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    _append_jsonl(RUN_LOG, run)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "latest.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    ts = _now()
    health = _run_healthcheck(update_memrl=args.update_memrl, no_remote=args.no_remote)
    selected = _select_candidates(health, args.candidate, args.limit)
    eval_pack = Path(args.eval_pack)
    if not eval_pack.is_absolute():
        eval_pack = HARNESS_DIR / eval_pack
    eval_result = run_pack(eval_pack)
    runs: list[dict[str, Any]] = []
    for candidate in selected:
        decision = _promotion_decision(candidate, health, eval_result)
        run_id = f"skill-evo-{_slug_ts(ts)}-{candidate['name']}"
        run = {
            "ok": True,
            "id": run_id,
            "ts": ts,
            "phase": "evaluated",
            "candidate": candidate["name"],
            "candidate_payload": candidate,
            "health_report_path": health.get("report_path"),
            "health_gate": health.get("evolution_gate"),
            "memrl_status": {
                "ready": health.get("memrl_status", {}).get("ready"),
                "feedback": health.get("memrl_feedback"),
            },
            "skillrl_status": health.get("skillrl_status"),
            "eval": {
                "ok": eval_result.get("ok"),
                "pack": eval_result.get("pack"),
                "passed": eval_result.get("passed"),
                "failed": eval_result.get("failed"),
                "path": eval_result.get("path"),
            },
            **decision,
            "demoted": False,
        }
        _persist_run(run)
        runs.append(run)
    return {
        "ok": bool(selected) and all(r.get("ok") for r in runs),
        "ts": ts,
        "selected_count": len(selected),
        "runs": runs,
        "eval": eval_result,
        "health_report_path": health.get("report_path"),
        "current_problem": "skill evolution candidate blocked until implementation/eval gates pass" if any(r.get("blockers") for r in runs) else "selected skill can be promoted",
        "next_step": "implement blocked P0 candidate as a concrete skill, then rerun skill evolution" if any(r.get("blockers") for r in runs) else "keep nightly evolution gate active",
    }


def status(limit: int = 20) -> dict[str, Any]:
    conn = _conn()
    rows = conn.execute(
        "SELECT id, candidate, phase, verdict, reward, promoted, demoted, updated_at FROM skill_evolution_runs ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    registry = conn.execute(
        "SELECT skill, status, last_run_id, last_reward, updated_at FROM skill_evolution_registry ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return {
        "ok": True,
        "runs": [dict(r) for r in rows],
        "registry": [dict(r) for r in registry],
        "log": str(RUN_LOG),
        "latest": str(STATE_DIR / "latest.json"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="skill_evolution_runner.py")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run")
    p.add_argument("--candidate", default="auto", help="auto, all, or a specific skill candidate name")
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--eval-pack", default=str(DEFAULT_EVAL_PACK))
    p.add_argument("--update-memrl", action="store_true")
    p.add_argument("--no-remote", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("status")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd == "run":
        data = run_once(args)
    elif args.cmd == "status":
        data = status(limit=args.limit)
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
