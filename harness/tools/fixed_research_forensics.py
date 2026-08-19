#!/usr/bin/env python3
"""Forensic telemetry for a native fixed-research run.

Ported from the pattern in internal/codex-docker-uat/entrypoint.sh, which takes
a full forensic snapshot every N seconds rather than answering one question at a
time. The difference matters: this session lost hours to failures that were
sitting in operator-results the whole time, because the collector only reported
what it had been told to look for.

Two outputs, deliberately separate:

* snapshots/  -- one directory per tick holding copies of the sprint sidecars,
  the runtime control-plane directories, the process table, and a typed file
  inventory. Written for after the fact, when the question is not yet known.
* events.jsonl + stdout -- one line per STATE CHANGE, and every failure the
  moment it appears. Written for during, so a failing run is noticed while it
  is still failing.

The rule throughout: a thing that is absent is reported as absent, never as
healthy. A stage with no node result is "missing", not "pending", because those
are different facts and the second is the one that hides a stage that died.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

# Copied verbatim each tick when present. Same list the Docker UAT captures,
# plus the eval sidecars this workflow writes.
SPRINT_SUFFIXES = (
    "status.json", "task_graph.json", "task_dag.state.json", "gate-ledger.jsonl",
    "events.jsonl", "runstate.jsonl", "coverage_report.json", "acceptance_verdict.json",
    "closure.json", "route-proof.json", "requirement_trace.json",
)
RUNTIME_COMPONENTS = (
    "operator-status", "operator-results", "pm-inbox", "operator-leases", "multi-task",
)
STAGES = (
    "seed_fetch", "source_discovery", "source_validation", "evidence_synthesis",
    "report_draft", "independent_review", "report_revision", "final_acceptance",
    "poc_handoff", "idea_evaluation", "experiment_design", "experiment_approval",
    "experiment_run", "claim_verification", "final_delivery",
)
# Where each stage writes its node result, relative to the artifact root.
RESULT_DIR = {
    "seed_fetch": "seed", "source_discovery": "discovery", "source_validation": "validation",
    "evidence_synthesis": "synthesis", "report_draft": "report", "independent_review": "review",
    "report_revision": "revision", "final_acceptance": "final", "poc_handoff": "poc",
}
ARTIFACTS = "artifacts/research_evidence_to_poc"


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sprint_id(evidence_root: Path) -> str:
    sprints = evidence_root / "sprints"
    if not sprints.is_dir():
        return ""
    ids = sorted({p.name.split(".")[0] for p in sprints.glob("*wf-research-evidence-to-poc-v1-*")})
    return ids[-1] if ids else ""


def snapshot(evidence_root: Path, out_dir: Path, sequence: int) -> Path:
    """One forensic tick. Copies state; never interprets it."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    root = out_dir / "snapshots" / f"{sequence:05d}-{stamp}"
    (root / "sprint").mkdir(parents=True, exist_ok=True)
    (root / "run").mkdir(parents=True, exist_ok=True)

    sid = _sprint_id(evidence_root)
    (root / "sample.env").write_text(
        f"sequence={sequence}\ncaptured_at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        f"sprint_id={sid}\n",
        encoding="utf-8",
    )

    try:
        procs = subprocess.run(
            ["ps", "-eo", "pid,ppid,pgid,lstart,etime,stat,args", "--sort=pid"],
            capture_output=True, text=True, timeout=20, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        procs = ""
    (root / "processes.txt").write_text(procs, encoding="utf-8")

    sprints = evidence_root / "sprints"
    if sid and sprints.is_dir():
        for suffix in SPRINT_SUFFIXES:
            candidate = sprints / f"{sid}.{suffix}"
            if candidate.exists():
                shutil.copy2(candidate, root / "sprint" / candidate.name)
        # Every eval sidecar, so a gate verdict is recoverable per tick.
        for sidecar in sprints.glob(f"{sid}.*-eval.json"):
            shutil.copy2(sidecar, root / "sprint" / sidecar.name)
        rows = []
        for path in sorted(sprints.rglob(f"{sid}*")):
            try:
                stat = path.stat()
            except OSError:
                continue
            kind = "d" if path.is_dir() else "f"
            rows.append(f"{kind}\t{stat.st_size}\t{int(stat.st_mtime)}\t{path}")
        (root / "sprint-file-inventory.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    runtime = evidence_root / "runtime-harness" / "run"
    for component in RUNTIME_COMPONENTS:
        source = runtime / component
        if source.exists():
            shutil.copytree(source, root / "run" / component, dirs_exist_ok=True)
    return root


def digest(evidence_root: Path) -> dict[str, Any]:
    """The interpreted view: what is done, what failed, and why.

    Reads the three places a failure can hide, because this session found one in
    each: the gate sidecar, the operator dispatch result, and the node result the
    operator itself wrote.
    """
    sid = _sprint_id(evidence_root)
    if not sid:
        return {"sprint_id": "", "state": "no_sprint_yet"}
    sprints = evidence_root / "sprints"
    status = _load(sprints / f"{sid}.status.json") or {}

    workdir = sprints / sid / "workdir"
    stages: dict[str, Any] = {}
    failures: list[str] = []
    for stage in STAGES:
        row: dict[str, Any] = {}
        sidecar = _load(sprints / f"{sid}.{stage}-eval.json")
        if isinstance(sidecar, dict):
            row["gate"] = sidecar.get("verdict")
            row["gate_kind"] = sidecar.get("gate_kind")
            row["gate_seconds"] = sidecar.get("duration_seconds")
        directory = RESULT_DIR.get(stage)
        if directory:
            result = _load(workdir / ARTIFACTS / directory / "research_node_result.json")
            if isinstance(result, dict):
                row["node_status"] = result.get("status")
                errors = result.get("errors") or []
                if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                    row["node_error"] = str(errors[0].get("message") or "")[:200]
                if result.get("status") != "completed":
                    failures.append(f"{stage}: node_status={result.get('status')} {row.get('node_error','')}")
            elif row.get("gate"):
                # Gated but no result on disk is the exact shape that let a
                # failed stage read as a pass.
                failures.append(f"{stage}: gate={row['gate']} but no node result on disk")
        if row:
            stages[stage] = row

    # Operator dispatches, where the earliest and clearest failure text lives.
    dispatches: list[dict[str, Any]] = []
    results_root = evidence_root / "runtime-harness" / "run" / "operator-results"
    for result_path in sorted(results_root.glob("*/*/result.json")) if results_root.is_dir() else []:
        payload = _load(result_path)
        if not isinstance(payload, dict):
            continue
        entry = {
            "node": payload.get("node_id"),
            "status": payload.get("status"),
            "exit_code": payload.get("exit_code"),
            "task": result_path.parent.name[-24:],
        }
        if payload.get("status") != "completed":
            entry["log_tail"] = str(payload.get("log_tail") or "")[:300]
            failures.append(f"dispatch {payload.get('node_id')}: {entry['log_tail'][:180]}")
        dispatches.append(entry)

    calls: list[dict[str, Any]] = []
    for exchange in sorted(evidence_root.rglob("service-evidence/*/*/exchange.json")):
        payload = _load(exchange)
        if not isinstance(payload, dict):
            continue
        row = {
            "node": payload.get("node_id"),
            "provider": exchange.parent.parent.name,
            "model": payload.get("model"),
            "status": payload.get("status"),
            "seconds": round(float(payload.get("elapsed_ms") or 0) / 1000, 1),
        }
        if payload.get("status") != "completed":
            row["error"] = str(payload.get("error") or "")[:200]
            failures.append(f"call {payload.get('node_id')}: {row['error'][:180]}")
        calls.append(row)

    done = [s for s, row in stages.items() if row.get("node_status") == "completed"]
    return {
        "sprint_id": sid,
        "phase": status.get("phase"),
        "active_node": status.get("active_node"),
        "failed_nodes": status.get("failed_nodes") or [],
        "stages_completed": len(done),
        "stages_total": len(STAGES),
        "stages": stages,
        "dispatches": dispatches,
        "model_calls": calls,
        "failures": failures,
    }


def _line(view: dict[str, Any]) -> str:
    """One compact line, failures first because they are what needs acting on."""
    if view.get("state") == "no_sprint_yet":
        return "waiting for sprint"
    parts = [
        f"active={view.get('active_node')}",
        f"done={view.get('stages_completed')}/{view.get('stages_total')}",
        f"calls={len(view.get('model_calls') or [])}",
    ]
    gates = [f"{s}:{row['gate']}" for s, row in (view.get("stages") or {}).items() if row.get("gate")]
    if gates:
        parts.append("gates=" + ",".join(gates))
    failures = view.get("failures") or []
    if failures:
        parts.append(f"FAILURES={len(failures)}")
    line = " ".join(parts)
    for failure in failures:
        line += f"\n    !! {failure}"
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--out", default="", help="forensic snapshot directory")
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--watch", action="store_true", help="loop until the run process exits")
    parser.add_argument("--pattern", default="fixed_research_uat.py start-to-final",
                        help="process pattern whose disappearance ends the watch")
    args = parser.parse_args(argv)

    evidence_root = Path(args.evidence_root).expanduser()
    out_dir = Path(args.out).expanduser() if args.out else evidence_root / "forensics"

    if not args.watch:
        print(json.dumps(digest(evidence_root), indent=2, sort_keys=True))
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    events = out_dir / "events.jsonl"
    sequence = 0
    previous = ""
    seen_failures: set[str] = set()
    while True:
        sequence += 1
        try:
            snapshot(evidence_root, out_dir, sequence)
        except Exception as exc:  # forensics must never kill the watch
            print(f"snapshot error: {exc}", flush=True)
        view = digest(evidence_root)
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"sequence": sequence, "at": time.time(), **view}) + "\n")

        # Print on change, and always print a failure the first time it appears.
        fresh = [f for f in (view.get("failures") or []) if f not in seen_failures]
        seen_failures.update(fresh)
        line = _line(view)
        if line != previous or fresh:
            print(line, flush=True)
            previous = line

        alive = subprocess.run(["pgrep", "-f", args.pattern], capture_output=True, check=False)
        if alive.returncode != 0:
            print(f"RUN ENDED after {sequence} snapshots", flush=True)
            print(_line(digest(evidence_root)), flush=True)
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
