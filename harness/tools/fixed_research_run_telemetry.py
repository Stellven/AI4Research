#!/usr/bin/env python3
"""Structured telemetry for a fixed-research UAT run.

`fixed_research_uat.py` emits no telemetry. Every question about a run this
session -- did the gate fire, which stage stopped it, was a report produced,
how many sources survived -- was answered by tailing a log and grepping for
strings. That is how a timed-out stage was nearly reported as a success, and
how a stale server's output was read as the current run's.

The Docker UAT already has the right shape: a manifest with commit provenance,
a retained record per poll, a terminal-state classification, and a measured
teardown. This is that, for the research workflow: one JSON record per run,
read from artifacts on disk rather than from stdout.

It deliberately reports only what the artifacts say. When something is absent it
is recorded as absent, never inferred, because "no report was produced" and "a
report was produced and I could not find it" are different facts and the second
must not be silently rendered as the first.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ARTIFACTS = "artifacts/research_evidence_to_poc"
STAGE_ORDER = (
    "seed_fetch", "source_discovery", "source_validation", "evidence_synthesis",
    "report_draft", "independent_review", "report_revision", "final_acceptance",
    "poc_handoff", "idea_evaluation", "experiment_design", "experiment_approval",
    "experiment_run", "claim_verification", "final_delivery",
)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _commit(repo: Path) -> str:
    """The commit the run executed against, so a result is attributable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return (out.stdout or "").strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def collect(evidence_root: Path, *, repo: Path | None = None) -> dict[str, Any]:
    sprints = evidence_root / "sprints"
    sprint_ids = sorted(
        {
            path.name.split(".")[0]
            for path in sprints.glob("*wf-research-evidence-to-poc-v1-*")
            if path.name.count(".") >= 1
        }
    ) if sprints.is_dir() else []
    sid = sprint_ids[-1] if sprint_ids else ""

    stages: list[dict[str, Any]] = []
    for stage in STAGE_ORDER:
        sidecar = _load(sprints / f"{sid}.{stage}-eval.json") if sid else None
        if sidecar is None:
            stages.append({"stage": stage, "reached": False})
            continue
        stages.append({
            "stage": stage,
            "reached": True,
            "verdict": sidecar.get("verdict"),
            "gate_kind": sidecar.get("gate_kind"),
            # A gate that did not run is the single most important thing to see.
            "gate_ran": sidecar.get("gate_kind") == "deterministic_command",
            "exit_code": sidecar.get("exit_code"),
            "duration_seconds": sidecar.get("duration_seconds"),
        })

    workdir = sprints / sid / "workdir" if sid else evidence_root
    validation = _load(workdir / ARTIFACTS / "validation" / "source_validation.json") or {}
    synthesis = _load(workdir / ARTIFACTS / "synthesis" / "evidence_synthesis.json") or {}
    claims = (synthesis.get("outputs") or synthesis).get("claims") or []
    report = workdir / ARTIFACTS / "report" / "report.md"

    reached = [s for s in stages if s["reached"]]
    gated = [s for s in stages if s.get("gate_ran")]
    failed = [s for s in stages if s.get("verdict") == "FAIL"]

    return {
        "schema": "solar.fixed_research_run_telemetry.v1",
        "evidence_root": str(evidence_root),
        "commit": _commit(repo or Path.cwd()),
        "sprint_id": sid,
        "stages_reached": len(reached),
        "stages_total": len(STAGE_ORDER),
        "gates_executed": [s["stage"] for s in gated],
        "gate_verdicts": {s["stage"]: s.get("verdict") for s in gated},
        "first_failed_stage": failed[0]["stage"] if failed else None,
        "sources": {
            "accepted": validation.get("accepted_count"),
            "rejected": validation.get("rejected_count"),
        },
        "claims": len(claims) if isinstance(claims, list) else None,
        # Absent is recorded as absent. A refused run and a run whose output we
        # failed to locate are different outcomes.
        "report_produced": report.is_file(),
        "report_bytes": report.stat().st_size if report.is_file() else 0,
        "stages": stages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence-root", required=True, action="append",
                        help="repeatable; one record per run")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    records = [collect(Path(root).expanduser(), repo=Path(args.repo)) for root in args.evidence_root]
    payload = {"schema": "solar.fixed_research_run_telemetry_set.v1", "runs": records}
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).expanduser().write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
