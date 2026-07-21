#!/usr/bin/env python3
"""Health, audit, and circuit breaker for Solar Knowledge ingest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import knowledge_ingest_registry as registry


DEFAULT_PAUSE_FILE = Path.home() / "Knowledge" / "_registry" / "extract_queue.paused.json"


def _connect(db_path: Path):
    registry.migrate(db_path)
    return registry.connect(db_path)


def audit(db_path: Path) -> dict[str, Any]:
    with _connect(db_path) as conn:
        orphan_spans = conn.execute(
            """
            SELECT COUNT(*)
            FROM spans s
            LEFT JOIN documents d ON d.doc_id=s.doc_id
            WHERE d.doc_id IS NULL
            """
        ).fetchone()[0]
        orphan_qmd = conn.execute(
            """
            SELECT COUNT(*)
            FROM qmd_index_events q
            LEFT JOIN documents d ON d.doc_id=q.doc_id
            WHERE d.doc_id IS NULL
            """
        ).fetchone()[0]
        counts = {row["current_state"]: row["n"] for row in conn.execute("SELECT current_state, COUNT(*) AS n FROM documents GROUP BY current_state")}
    return {"ok": orphan_spans == 0 and orphan_qmd == 0, "orphan_count": orphan_spans + orphan_qmd, "orphan_spans": orphan_spans, "orphan_qmd_events": orphan_qmd, "states": counts}


def validation_window(db_path: Path, limit: int) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = list(
            conn.execute(
                "SELECT passed, error_code, ts FROM validation_results ORDER BY ts DESC, result_id DESC LIMIT ?",
                (limit,),
            )
        )
    total = len(rows)
    failed = sum(1 for row in rows if int(row["passed"]) == 0)
    consecutive = 0
    for row in rows:
        if int(row["passed"]) == 0:
            consecutive += 1
        else:
            break
    error_codes: dict[str, int] = {}
    for row in rows:
        if int(row["passed"]) == 0:
            key = row["error_code"] or "unknown"
            error_codes[key] = error_codes.get(key, 0) + 1
    fail_rate = (failed / total) if total else 0.0
    return {"total": total, "failed": failed, "fail_rate": fail_rate, "consecutive_failures": consecutive, "error_codes": error_codes}


def circuit_check(
    *,
    db_path: Path,
    window: int,
    max_fail_rate: float,
    max_consecutive_failures: int,
    pause_file: Path,
) -> dict[str, Any]:
    stats = validation_window(db_path, window)
    should_pause = False
    reasons: list[str] = []
    if stats["total"] >= max(1, min(window, 5)) and stats["fail_rate"] > max_fail_rate:
        should_pause = True
        reasons.append(f"fail_rate {stats['fail_rate']:.2f} > {max_fail_rate:.2f}")
    if stats["consecutive_failures"] > max_consecutive_failures:
        should_pause = True
        reasons.append(f"consecutive_failures {stats['consecutive_failures']} > {max_consecutive_failures}")
    payload = {
        "ok": True,
        "paused": should_pause,
        "pause_file": str(pause_file),
        "reasons": reasons,
        "window": stats,
    }
    if should_pause:
        pause_file.parent.mkdir(parents=True, exist_ok=True)
        pause_file.write_text(json.dumps({**payload, "created_at": registry.now_iso()}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def health(db_path: Path, pause_file: Path, window: int) -> dict[str, Any]:
    registry_status = registry.status(db_path)
    audit_result = audit(db_path)
    validations = validation_window(db_path, window)
    paused = pause_file.exists()
    if paused:
        status = "red"
    elif validations["fail_rate"] > 0.20:
        status = "red"
    elif validations["fail_rate"] > 0.05:
        status = "yellow"
    else:
        status = "green"
    return {
        "ok": status != "red",
        "status": status,
        "paused": paused,
        "pause_file": str(pause_file),
        "registry": registry_status,
        "audit": audit_result,
        "validation_window": validations,
    }


def cmd_audit(args: argparse.Namespace) -> int:
    result = audit(Path(args.db).expanduser())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def cmd_circuit(args: argparse.Namespace) -> int:
    result = circuit_check(
        db_path=Path(args.db).expanduser(),
        window=args.window,
        max_fail_rate=args.max_fail_rate,
        max_consecutive_failures=args.max_consecutive_failures,
        pause_file=Path(args.pause_file).expanduser(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    result = health(Path(args.db).expanduser(), Path(args.pause_file).expanduser(), args.window)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solar Knowledge ingest health")
    parser.add_argument("--db", default=str(registry.DEFAULT_DB))
    parser.add_argument("--pause-file", default=str(DEFAULT_PAUSE_FILE))
    sub = parser.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("health")
    h.add_argument("--window", type=int, default=25)
    h.set_defaults(func=cmd_health)
    a = sub.add_parser("audit")
    a.set_defaults(func=cmd_audit)
    c = sub.add_parser("circuit-check")
    c.add_argument("--window", type=int, default=25)
    c.add_argument("--max-fail-rate", type=float, default=0.25)
    c.add_argument("--max-consecutive-failures", type=int, default=5)
    c.set_defaults(func=cmd_circuit)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
