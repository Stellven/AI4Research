"""Refresh orchestrator — concurrent multi-source status aggregator.

Run as module:
    cd ~/.solar
    python3 -m harness.lib.refresh.orchestrator --scope all --json

Schema: refresh.run.v1
Exit codes: 0=all ok, 1=any error, 2=any degraded (no error), 3=all skipped
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait

SCHEMA = "refresh.run.v1"
ALL_SOURCES = ["status", "sprints", "dashboards", "autopilot", "kb"]
DEFAULT_BUDGET = 5.0
DEEP_BUDGET = 30.0


def _get_source(name: str):
    from harness.lib.refresh.sources import (
        autopilot,
        dashboards,
        kb,
        sprints,
        status,
    )
    return {"status": status, "sprints": sprints, "dashboards": dashboards,
            "autopilot": autopilot, "kb": kb}[name]


def _exit_code(sources: list[dict]) -> int:
    statuses = [s["status"] for s in sources]
    if "error" in statuses:
        return 1
    if "degraded" in statuses:
        return 2
    if statuses and all(s == "skipped" for s in statuses):
        return 3
    return 0


def orchestrate(scopes: list[str], deep: bool, budget: float) -> dict:
    """Run all scopes concurrently; return refresh.run.v1 payload dict."""
    started_ts = datetime.datetime.utcnow().isoformat() + "Z"
    t0 = time.monotonic()
    deadline = t0 + budget

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(len(scopes), 1)) as pool:
        futures = {
            pool.submit(_get_source(name).fetch, deep, deadline): name
            for name in scopes
        }
        done, not_done = wait(futures, timeout=budget)

        for fut in done:
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as exc:
                results[name] = {
                    "name": name,
                    "status": "error",
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                    "note": str(exc)[:200],
                }

        for fut in not_done:
            name = futures[fut]
            results[name] = {
                "name": name,
                "status": "degraded",
                "duration_ms": int(budget * 1000),
                "note": "timeout: global budget exceeded",
            }
            fut.cancel()

    ordered = [results[name] for name in scopes if name in results]
    finished_ts = datetime.datetime.utcnow().isoformat() + "Z"
    duration_ms = int((time.monotonic() - t0) * 1000)

    return {
        "schema": SCHEMA,
        "started_at": started_ts,
        "finished_at": finished_ts,
        "duration_ms": duration_ms,
        "scope": scopes,
        "deep": deep,
        "exit_code": _exit_code(ordered),
        "sources": ordered,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="solar-harness refresh",
        description="Lightweight read-only view over Solar Harness status sources.",
        epilog=(
            "See also (heavier ops):\n"
            "  solar-harness reload          — coordinator hot-reload\n"
            "  solar-harness wiki rebuild    — full KB rebuild\n"
            "  solar-harness wiki qmd-embed  — embedding backlog processing\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scope", default="all",
                        help="Comma-separated: status,sprints,dashboards,autopilot,kb,all  (default: all)")
    parser.add_argument("--json", action="store_true", dest="json_mode",
                        help="Emit refresh.run.v1 JSON to stdout")
    parser.add_argument("--deep", action="store_true",
                        help="Heavier probes; budget extends to 30s")
    parser.add_argument("--timeout", type=float, default=None,
                        help="Override budget seconds (0..30; only meaningful with --deep)")

    args = parser.parse_args(argv)

    parts = [s.strip() for s in args.scope.split(",")]
    scopes = ALL_SOURCES[:] if "all" in parts else [s for s in parts if s in ALL_SOURCES]
    if not scopes:
        scopes = ALL_SOURCES[:]

    if args.deep:
        budget = min(args.timeout if args.timeout is not None else DEEP_BUDGET, DEEP_BUDGET)
        print("warning: --deep mode enabled; this may take up to 30s", file=sys.stderr)
    else:
        budget = DEFAULT_BUDGET

    result = orchestrate(scopes, args.deep, budget)

    if args.json_mode:
        try:
            from harness.lib.refresh.schema_validate import validate as _validate
            _validate(result)
        except Exception as _ve:
            print(f"warning: schema validation failed: {_ve}", file=sys.stderr)
        print(json.dumps(result))
    else:
        print(f"solar-harness refresh  {result['finished_at']}  {result['duration_ms']}ms")
        print(f"\n{'Source':<14} {'Status':<10} {'Duration':>10}  Note")
        print("-" * 70)
        for src in result["sources"]:
            print(f"{src['name']:<14} {src['status']:<10} {src['duration_ms']:>8}ms  {src.get('note', '')}")
        print(f"\nexit={result['exit_code']}  use --deep / reload / wiki rebuild / qmd-embed for heavier ops")

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
