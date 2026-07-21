"""Per-chapter evidence, state events, and writer runtime for planned reports."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


FORBIDDEN_PUBLIC_FIELDS = (
    "video_id",
    "chapter_id",
    "evidence_pack_id",
    "transcript_status",
)
_FORBIDDEN_RE = re.compile(r"\b(video_id|chapter_id|evidence_pack_id|transcript_status)\b\s*[:=]?\s*[\w./:-]*", re.I)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def sanitize_public_markdown(markdown: str) -> str:
    sanitized = _FORBIDDEN_RE.sub("[内部字段已过滤]", markdown)
    return sanitized.replace("  ", " ")


def public_text_has_forbidden_fields(markdown: str) -> bool:
    return bool(_FORBIDDEN_RE.search(markdown))


def append_chapter_event(events_path: Path, *, chapter_id: str, from_status: str, to_status: str, reason: str, by: str = "core-runtime") -> dict[str, Any]:
    event = {
        "chapter_id": chapter_id,
        "from": from_status,
        "to": to_status,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": by,
        "reason": reason,
    }
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def rebuild_chapter_state(events_path: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    if not events_path.exists():
        return state
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        state[str(event["chapter_id"])] = str(event["to"])
    return state


def _video_ref(video: dict[str, Any], index: int) -> str:
    return str(video.get("video_ref") or video.get("ref") or f"V{index:03d}").strip()


def _quality_tier(video: dict[str, Any]) -> str:
    return str(video.get("quality_tier") or video.get("transcript_quality_tier") or video.get("transcript_grade") or (video.get("transcript_quality") or {}).get("tier") or "T1").upper()


def _transcript_status(video: dict[str, Any]) -> str:
    return str(video.get("transcript_status") or video.get("status") or "fetched").lower()


def _segments(video: dict[str, Any]) -> list[dict[str, Any]]:
    raw = video.get("transcript_segments") or video.get("segments") or []
    if isinstance(raw, list) and raw:
        return [s for s in raw if isinstance(s, dict)]
    transcript = str(video.get("transcript_clean") or video.get("transcript") or "").strip()
    return [{"text": transcript}] if transcript else []


def _public_video(video: dict[str, Any], index: int) -> dict[str, Any]:
    public = {k: v for k, v in video.items() if k not in {"video_id", "transcript_status"}}
    public.setdefault("video_ref", _video_ref(video, index))
    public["quality_tier"] = _quality_tier(video)
    return public


def build_chapter_evidence_pack(global_evidence_pack: dict[str, Any], chapter_spec: dict[str, Any], quality_targets: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build chapter-scoped evidence using T0/T1 core, T2 support-only, and T3/failed exclusion."""
    targets = quality_targets or {}
    refs = {
        str(ref).strip()
        for ref in (chapter_spec.get("selected_video_refs") or chapter_spec.get("material_video_refs") or [])
        if str(ref).strip()
    }
    videos_in = [v for v in (global_evidence_pack.get("videos") or []) if isinstance(v, dict)]
    core: list[dict[str, Any]] = []
    support: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    selected_videos: list[dict[str, Any]] = []
    selected_video_refs: list[str] = []
    segment_count = 0
    for idx, video in enumerate(videos_in, start=1):
        ref = _video_ref(video, idx)
        if refs and ref not in refs:
            continue
        tier = _quality_tier(video)
        status = _transcript_status(video)
        public = _public_video(video, idx)
        segments = _segments(video)
        if status in {"failed", "missing", "quarantined"} or tier in {"T3", "FAILED"}:
            excluded.append({
                "video_ref": ref,
                "quality_tier": tier,
                "status": status,
                "reason": f"excluded:{status}",
                "metadata_only": True,
            })
            continue
        selected_video_refs.append(ref)
        selected_videos.append(public)
        segment_count += len([s for s in segments if str(s.get("text") or "").strip()])
        public["transcript_segments"] = segments
        if tier in {"T0", "T1"}:
            core.append(public)
        elif tier == "T2":
            public["support_only"] = True
            support.append(public)
        else:
            excluded.append({"video_ref": ref, "quality_tier": tier, "reason": "unsupported_quality_tier"})

    pack_video_refs = set(selected_video_refs)
    semantic_packets = [
        p for p in (global_evidence_pack.get("semantic_packets") or [])
        if isinstance(p, dict) and ((str(p.get("video_ref") or p.get("ref") or "") in pack_video_refs) or (not pack_video_refs))
    ]
    cross_source_links = [
        c for c in (global_evidence_pack.get("cross_source_links") or [])
        if isinstance(c, dict) and (
            str(c.get("video_ref") or c.get("ref") or "") in pack_video_refs or
            not pack_video_refs
        )
    ]
    counter_evidence = [
        c for c in (global_evidence_pack.get("counter_evidence") or [])
        if isinstance(c, dict)
    ]

    transcript_segments = [
        {**s, "video_ref": s.get("video_ref") or segment_video_ref}
        for segment_video_ref, selected_video in zip(selected_video_refs, selected_videos)
        for s in (selected_video.get("transcript_segments") or [])
        if isinstance(s, dict)
    ]
    weak_reasons: list[str] = []
    if str(chapter_spec.get("chapter_type") or "") == "core_trend":
        if len(selected_video_refs) < int(targets.get("min_videos") or 2):
            weak_reasons.append("selected_videos_below_min")
        if segment_count < int(targets.get("min_transcript_segments") or 4):
            weak_reasons.append("transcript_segments_below_min")

    core_missing_evidence_ids = [v.get("video_ref") for v in core if not v.get("evidence_id")]
    must_use_evidence_ids = [v.get("evidence_id") for v in core if v.get("evidence_id")]
    optional_evidence_ids = [v.get("evidence_id") for v in support if v.get("evidence_id")]
    if core_missing_evidence_ids and not must_use_evidence_ids and refs and str(chapter_spec.get("chapter_type") or "") == "core_trend":
        must_use_evidence_ids = list(selected_video_refs)
        if len(core_missing_evidence_ids) < len(core):
            weak_reasons.append("partial_core_evidence_id_annotations")
    return {
        "schema_version": "chapter_evidence_pack.v1",
        "chapter": {k: v for k, v in chapter_spec.items() if k not in {"video_id", "transcript_status"}},
        "chapter_id": str(chapter_spec.get("chapter_id") or ""),
        "selected_videos": selected_videos,
        "core_evidence": core,
        "support_evidence": support,
        "excluded_evidence": excluded,
        "video_count": len(selected_video_refs),
        "transcript_segments": transcript_segments,
        "semantic_packets": semantic_packets,
        "cross_source_links": cross_source_links,
        "counter_evidence": counter_evidence,
        "must_use_evidence_ids": must_use_evidence_ids,
        "optional_evidence_ids": optional_evidence_ids,
        "transcript_segment_count": segment_count,
        "weak": bool(weak_reasons),
        "weak_reasons": weak_reasons,
        "allowed_use": "current_chapter_only",
        "transcript_policy": "T0/T1 core; T2 support_only; T3/failed metadata_only",
    }


def _default_mock_writer(chapter_spec: dict[str, Any], evidence_pack: dict[str, Any], model_name: str) -> dict[str, Any]:
    title = str(chapter_spec.get("title") or "章节").strip()
    core_count = len(evidence_pack.get("core_evidence") or [])
    support_count = len(evidence_pack.get("support_evidence") or [])
    markdown = (
        f"## {title}\n\n"
        f"本章基于 {core_count} 条核心证据和 {support_count} 条辅助证据形成判断。"
        "核心结论围绕材料中的趋势、工程信号和不确定性展开，证据不足处明确降级为观察项。\n\n"
        "### 判断\n逐章链路已按证据包隔离写作，避免跨章节混用素材。\n\n"
        "### 不确定性\n仍需在后续验证切片中引入更严格的事实核验。"
    )
    return {"markdown": markdown, "model": model_name, "backend": "local_mock", "latency_ms": 0}


def run_chapter_writer(
    report_dir: Path,
    chapter_job: dict[str, Any],
    chapter_spec: dict[str, Any],
    evidence_pack: dict[str, Any],
    *,
    model_name: str = "chatgpt-5.5",
    writer_callable: Callable[[dict[str, Any], dict[str, Any], str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Invoke ChapterWriterOperator-compatible callable and persist draft/final/proof atomically."""
    chapter_id = str(chapter_job.get("chapter_id") or chapter_spec.get("chapter_id") or "chapter")
    writer = writer_callable or _default_mock_writer
    result = writer(chapter_spec, evidence_pack, model_name)
    markdown = sanitize_public_markdown(str(result.get("markdown") or "").strip())
    if not markdown:
        raise ValueError(f"chapter_writer_empty_output:{chapter_id}")
    chapters_dir = report_dir / "chapters"
    evidence_dir = report_dir / "evidence-packs"
    proof_dir = report_dir / "proof"
    draft_path = chapters_dir / f"{chapter_id}.draft.md"
    final_path = chapters_dir / f"{chapter_id}.final.md"
    evidence_path = evidence_dir / f"{chapter_id}.evidence.json"
    proof_path = proof_dir / f"{chapter_id}.writer.proof.json"
    atomic_write_json(evidence_path, evidence_pack)
    atomic_write_text(draft_path, markdown + "\n")
    shutil.copyfile(draft_path, final_path)
    proof = {
        "schema_version": "chapter_writer_proof.v1",
        "chapter_id": chapter_id,
        "draft_path": str(draft_path),
        "final_path": str(final_path),
        "evidence_path": str(evidence_path),
        "model": result.get("model") or model_name,
        "backend": result.get("backend") or "ChapterWriterOperator",
        "latency_ms": int(result.get("latency_ms") or 0),
        "input_token_count": int(result.get("input_token_count") or 0),
        "output_token_count": int(result.get("output_token_count") or 0),
        "request_dir": str(result.get("request_dir") or ""),
    }
    atomic_write_json(proof_path, proof)
    return {**proof, "markdown": markdown, "proof_path": str(proof_path)}
