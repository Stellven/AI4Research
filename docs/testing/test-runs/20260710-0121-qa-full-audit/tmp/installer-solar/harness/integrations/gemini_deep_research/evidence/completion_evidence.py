"""U3 — runtime structured completion evidence.

Replaces "natural-language claims of done" with a machine-checkable evidence
packet derived from the append-only event log: the async_state trajectory,
attempt count, structured success-criteria breakdown, evidence refs, and a
terminal verdict. An evaluator re-checks the verdict from the same events
(``verify_evidence``) rather than trusting prose.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HARNESS_DIR = Path(__file__).resolve().parents[3]
for _p in (str(_HARNESS_DIR / "lib"), str(_HARNESS_DIR / "lib" / "capabilities")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gemini_deep_research.core.controller import GeminiDRController  # noqa: E402
from gemini_deep_research.core.retry import MIN_REFS, evaluate_success  # noqa: E402
from gemini_deep_research.schemas.models import AsyncState, ResultStatus  # noqa: E402
from gemini_deep_research.schemas.persistence import EventLog  # noqa: E402

_DEFAULT_OUT = _HARNESS_DIR / "var" / "gemini_deep_research" / "evidence"


@dataclass
class CompletionEvidence:
    run_ref: str
    verdict: str                       # "complete" | "incomplete" | "no_run"
    controller_state: str
    final_async_state: str | None
    async_state_trajectory: list[str] = field(default_factory=list)
    attempts: int = 0
    result_status: str | None = None
    references_count: int = 0
    category_count: int = 0
    evidence_refs: list[str] = field(default_factory=list)
    success_reason: str | None = None  # why complete/incomplete (structured)
    event_count: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _trajectory(events: list[Any]) -> list[str]:
    traj: list[str] = []
    for ev in events:
        st = ev.payload.get("async_state")
        if st and (not traj or traj[-1] != st):
            traj.append(st)
    return traj


def build_evidence(run_ref: str, event_log: EventLog) -> CompletionEvidence:
    events = event_log.read_all(run_ref)
    now = datetime.now(timezone.utc).isoformat()
    if not events:
        return CompletionEvidence(
            run_ref=run_ref, verdict="no_run", controller_state="input",
            final_async_state=None, generated_at=now,
        )

    snap = GeminiDRController.rebuild(run_ref, event_log)
    handle = snap.handle
    result = snap.result
    traj = _trajectory(events)
    final_state = handle.async_state.value if handle else (traj[-1] if traj else None)
    evidence_refs = list(result.evidence_refs) if result else []

    verdict = "incomplete"
    reason = "no terminal succeeded result"
    refs_count = 0
    cat_count = 0
    if result is not None:
        refs_count = len(result.references)
        cat_count = len({r.category for r in result.references if r.category})
        if handle is not None and result.status == ResultStatus.SUCCEEDED:
            check = evaluate_success(handle.async_state, result, MIN_REFS)
            verdict = "complete" if check.ok else "incomplete"
            reason = check.reason or "all success criteria met"
        else:
            reason = result.failure_reason or "result not succeeded"

    return CompletionEvidence(
        run_ref=run_ref,
        verdict=verdict,
        controller_state=snap.state.value,
        final_async_state=final_state,
        async_state_trajectory=traj,
        attempts=snap.attempt,
        result_status=result.status.value if result else None,
        references_count=refs_count,
        category_count=cat_count,
        evidence_refs=evidence_refs,
        success_reason=reason,
        event_count=len(events),
        generated_at=now,
    )


def write_evidence(evidence: CompletionEvidence, out_dir: str | Path | None = None) -> Path:
    base = Path(out_dir) if out_dir is not None else _DEFAULT_OUT
    base.mkdir(parents=True, exist_ok=True)
    safe = evidence.run_ref.replace("/", "_")
    path = base / f"{safe}.evidence.json"
    path.write_text(json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def verify_evidence(run_ref: str, event_log: EventLog, claimed_verdict: str) -> dict[str, Any]:
    """Evaluator re-derives the verdict from events and compares to the claim."""
    ev = build_evidence(run_ref, event_log)
    return {
        "run_ref": run_ref,
        "claimed": claimed_verdict,
        "rederived": ev.verdict,
        "agrees": ev.verdict == claimed_verdict,
        "reason": ev.success_reason,
    }
