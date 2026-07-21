"""Report IR compiler and chapter job builder for AI Influence YouTube reports."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


DEFAULT_QUALITY_TARGETS = {
    "min_videos": 2,
    "min_transcript_segments": 4,
    "core_tiers": ["T0", "T1"],
    "support_tiers": ["T2"],
}


def _slug(value: str, *, fallback: str = "report") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return text or fallback


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return value
    return default


def _coalesce_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _coalesce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _stable_id(seed: Any) -> str:
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _refs_from_spec(spec: dict[str, Any], fallback_refs: list[str]) -> list[str]:
    refs: list[str] = []
    for key in (
        "selected_video_refs",
        "material_video_refs",
        "supporting_video_refs",
        "video_refs",
        "video_refs_list",
        "reference_video_refs",
    ):
        refs.extend(str(ref).strip() for ref in (spec.get(key) or []) if str(ref).strip())
    for key in ("chapters", "subsections", "sections"):
        for child in spec.get(key) or []:
            if isinstance(child, dict):
                refs.extend(_refs_from_spec(child, []))
    seen: set[str] = set()
    deduped = [ref for ref in refs if ref and not (ref in seen or seen.add(ref))]
    return deduped or list(fallback_refs)


def _catalog_refs(catalog: Any) -> list[str]:
    if isinstance(catalog, dict):
        rows = catalog.get("videos") or catalog.get("items") or catalog.get("catalog") or []
    else:
        rows = catalog or []
    refs: list[str] = []
    for idx, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        ref = str(item.get("video_ref") or item.get("ref") or f"V{idx:03d}").strip()
        if ref:
            refs.append(ref)
    return refs


def _chapter_defaults(chapter: dict[str, Any], *, index: int, fallback_refs: list[str]) -> dict[str, Any]:
    title = str(
        _first(
            chapter.get("title"),
            chapter.get("chapter_title"),
            chapter.get("section_title"),
            chapter.get("trend_title"),
            chapter.get("name"),
            f"Chapter {index}",
        )
    ).strip()
    chapter_id = str(
        _first(
            chapter.get("chapter_id"),
            chapter.get("id"),
            _slug(title, fallback=f"ch-{index:02d}"),
        )
    ).strip()
    chapter_type = str(_first(chapter.get("chapter_type"), chapter.get("type"), default="core_trend")).strip()
    out = dict(chapter)
    out["chapter_id"] = chapter_id
    out["title"] = title
    out["chapter_type"] = chapter_type or "core_trend"
    out.setdefault("priority", str(_first(chapter.get("priority"), chapter.get("priority_level"), default="P1")).strip())
    out["deep_writer_required"] = _coalesce_bool(
        _first(chapter.get("deep_writer_required"), chapter.get("deep_writer")),
        default=False,
    )
    out["expected_words"] = _coalesce_int(
        _first(
            chapter.get("expected_words"),
            chapter.get("word_limit"),
            chapter.get("target_words"),
            chapter.get("word_target"),
        ),
        default=900 if chapter_type == "core_trend" else 500,
    )
    out["selected_video_refs"] = _refs_from_spec(out, fallback_refs)
    if "material_video_refs" not in out:
        out["material_video_refs"] = list(out["selected_video_refs"])
    if not all(key in chapter for key in ("priority", "deep_writer_required", "expected_words")):
        out["legacy_imported"] = True
    elif chapter.get("legacy_imported"):
        out["legacy_imported"] = True
    return out


def _chapters_from_report_spec(report_spec: dict[str, Any], all_refs: list[str]) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    raw_chapters = [c for c in (report_spec.get("chapters") or []) if isinstance(c, dict)]
    trends = [t for t in (report_spec.get("trends") or []) if isinstance(t, dict)]
    sections = [s for s in (report_spec.get("sections") or []) if isinstance(s, dict)]

    if raw_chapters:
        for idx, chapter in enumerate(raw_chapters, start=1):
            chapters.append(_chapter_defaults(chapter, index=idx, fallback_refs=all_refs))
        return chapters

    idx = 1
    for trend in trends:
        nested = [c for c in (trend.get("chapters") or []) if isinstance(c, dict)]
        trend_refs = _refs_from_spec(trend, all_refs)
        if nested:
            for chapter in nested:
                merged = {**chapter}
                merged.setdefault("chapter_type", "core_trend")
                merged.setdefault("trend_context", {k: v for k, v in trend.items() if k != "chapters"})
                chapters.append(_chapter_defaults(merged, index=idx, fallback_refs=trend_refs))
                idx += 1
        else:
            chapters.append(_chapter_defaults(trend, index=idx, fallback_refs=trend_refs))
            idx += 1

    if not chapters:
        if sections:
            for section in sections:
                chapters.append(_chapter_defaults(section, index=idx, fallback_refs=all_refs))
                idx += 1
        else:
            chapters.append(_chapter_defaults({"title": "核心趋势", "chapter_type": "core_trend"}, index=1, fallback_refs=all_refs))

    return chapters


def compile_report_ir(
    report_plan: dict[str, Any],
    catalog: dict[str, Any] | list[dict[str, Any]],
    video_groups: dict[str, Any] | None,
    config: dict[str, Any] | None,
    *,
    report_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile planner output into the authoritative per-report execution IR."""
    cfg = config or {}
    reports = [r for r in (report_plan.get("reports") or []) if isinstance(r, dict)]
    spec = report_spec or (reports[0] if reports else report_plan)
    spec = spec if isinstance(spec, dict) else {}
    all_refs = _catalog_refs(catalog)
    selected_refs = _refs_from_spec(spec, all_refs)

    report_id = str(_first(spec.get("report_id"), spec.get("id"), spec.get("slug"), default="")).strip()
    if not report_id:
        report_id = _slug(
            str(
                _first(
                    spec.get("title"),
                    spec.get("report_title"),
                    spec.get("plan_title"),
                    spec.get("name"),
                    f"report-{_stable_id(spec)}",
                    default=f"report-{_stable_id(spec)}",
                )
            ),
            fallback=f"report-{_stable_id(spec)}",
        )

    quality_targets = dict(DEFAULT_QUALITY_TARGETS)
    quality_targets.update(
        (cfg.get("quality_targets") or {})
        if isinstance(cfg.get("quality_targets"), dict)
        else {}
    )
    chapters = _chapters_from_report_spec(spec, selected_refs)

    source_group_ids = [
        str(group_id).strip()
        for group_id in _first(spec.get("source_group_ids"), spec.get("group_ids"), default=[]) or []
        if str(group_id).strip()
    ]

    return {
        "schema_version": "report_ir.v1",
        "report_id": report_id[:96],
        "title": str(_first(spec.get("title"), spec.get("report_title"), spec.get("plan_title"), spec.get("name"), "AI Influence YouTube Report")).strip(),
        "quality_targets": quality_targets,
        "source_group_ids": list(dict.fromkeys(source_group_ids)),
        "video_groups": video_groups or {},
        "selected_video_refs": selected_refs,
        "chapters": chapters,
        "metadata": {
            "legacy_imported": any(ch.get("legacy_imported") for ch in chapters),
            "planner_schema_version": spec.get("schema_version") or report_plan.get("schema_version") or report_plan.get("version") or "unknown",
        },
    }


def create_chapter_jobs(report_ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Create queued independent chapter jobs from Report IR."""
    jobs: list[dict[str, Any]] = []
    report_id = str(report_ir.get("report_id") or "").strip()
    for idx, chapter in enumerate(report_ir.get("chapters") or [], start=1):
        if not isinstance(chapter, dict):
            continue
        chapter_id = str(chapter.get("chapter_id") or f"ch_{idx:02d}").strip() or f"ch_{idx:02d}"
        priority = str(_first(chapter.get("priority"), default="P1")).strip()
        jobs.append(
            {
                "job_id": f"{report_id}:{chapter_id}",
                "report_id": report_id,
                "chapter_id": chapter_id,
                "status": "queued",
                "priority": priority,
                "chapter_type": chapter.get("chapter_type") or "core_trend",
                "deep_writer_required": bool(_coalesce_bool(chapter.get("deep_writer_required"), default=False)),
                "expected_words": _coalesce_int(chapter.get("expected_words"), default=0),
            }
        )
    return jobs
