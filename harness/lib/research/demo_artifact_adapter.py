"""RSI demo artifact adapter — native DeepResearch exports -> the 5 demo artifacts.

Lane 4 (target-design §1.8). The DeepResearch engine exports a run as native jsonl
(``sources.jsonl``, ``evidence.jsonl``, ``claims.jsonl``, ``claim_evidence.jsonl``,
``sections.jsonl``) plus a compiled ``final.md``. The bounded RSI demo, however,
ships five *human-facing* artifacts under ``rsi-deep-research-report/`` that the
copied-workspace validator (``scripts/validate_rsi_demo_report.py``) checks:

    report.html · report.md · sources.json · claims.json · evaluation-checklist.md

This module maps the former to the latter, deterministically and offline.

**F-055 boilerplate bypass (memory: deepresearch-synth-hardcoded-content).** The
engine's ``cli.py`` synthesizer emits a hardcoded boilerplate report body regardless
of topic. This adapter never calls that synthesizer: the report body is assembled
from the run's own ``sections.jsonl`` (the builder-authored, per-section content),
falling back to ``final.md`` only when no sections exist. It consumes native
exports; it does not generate report prose.

The mapping is a pure function of the input files (stable ordering, no timestamps,
no randomness), so identical exports yield byte-identical artifacts (R3).
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

DEMO_ARTIFACT_ROOT = "rsi-deep-research-report"

# Must match scripts/validate_rsi_demo_report.py REQUIRED.
REQUIRED_ARTIFACTS = [
    "report.html",
    "report.md",
    "sources.json",
    "claims.json",
    "evaluation-checklist.md",
]

# Native export files this adapter reads. sources/claims are mandatory; the rest
# refine the mapping (evidence+claim_evidence give claim->source linkage; sections/
# final.md give the report body; section_checks feed the checklist).
_MANDATORY_NATIVE = ("sources.jsonl", "claims.jsonl")

DEFAULT_REPORT_TITLE = "Recursive Self-Improving Models"


class NativeExportError(ValueError):
    """A required native export file is missing or unreadable."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise NativeExportError(f"{path.name}:{line_no}: invalid JSON: {exc}") from exc
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    # Compact-but-readable, trailing newline, stable key order for byte-stability.
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _map_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for row in rows:
        sid = row.get("id")
        if sid is None:
            continue
        sources.append({
            "id": str(sid),
            "title": str(row.get("title") or ""),
            "url": str(row.get("url") or ""),
            "source_type": str(row.get("source_type") or ""),
        })
    return sources


def _evidence_source_map(evidence_rows: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(row["id"]): str(row.get("source_id") or "")
        for row in evidence_rows
        if row.get("id") is not None
    }


def _claim_source_links(
    claim_evidence_rows: list[dict[str, Any]],
    evidence_source: dict[str, str],
) -> dict[str, list[tuple[float, int, str]]]:
    """claim_id -> [(strength, file_order, source_id)] for each resolvable link."""
    links: dict[str, list[tuple[float, int, str]]] = {}
    for order, row in enumerate(claim_evidence_rows):
        claim_id = str(row.get("claim_id") or "")
        evidence_id = str(row.get("evidence_id") or "")
        if not claim_id or not evidence_id:
            continue
        source_id = evidence_source.get(evidence_id, "")
        if not source_id:
            continue
        try:
            strength = float(row.get("strength") or 0.0)
        except (TypeError, ValueError):
            strength = 0.0
        links.setdefault(claim_id, []).append((strength, order, source_id))
    return links


def _resolve_source_for_claim(
    claim_id: str,
    links: dict[str, list[tuple[float, int, str]]],
    valid_source_ids: set[str],
) -> str | None:
    candidates = [
        (strength, -order, source_id)
        for strength, order, source_id in links.get(claim_id, [])
        if source_id in valid_source_ids
    ]
    if not candidates:
        return None
    # Strongest link wins; ties resolve to the earliest claim_evidence line.
    strength, neg_order, source_id = max(candidates)
    return source_id


def _map_claims(
    claim_rows: list[dict[str, Any]],
    links: dict[str, list[tuple[float, int, str]]],
    valid_source_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    claims: list[dict[str, Any]] = []
    dropped: list[str] = []
    for row in claim_rows:
        claim_id = str(row.get("id") or "")
        if not claim_id:
            continue
        source_id = _resolve_source_for_claim(claim_id, links, valid_source_ids)
        if source_id is None:
            dropped.append(claim_id)
            continue
        claims.append({
            "claim_id": claim_id,
            "source_id": source_id,
            "claim_text": str(row.get("claim_text") or ""),
            "claim_type": str(row.get("claim_type") or ""),
            "stance": str(row.get("stance") or ""),
            "confidence": row.get("confidence"),
        })
    return claims, dropped


def _report_markdown(
    section_rows: list[dict[str, Any]],
    final_md: str,
    title: str,
) -> str:
    body_parts: list[str] = []
    ordered = sorted(
        section_rows,
        key=lambda r: (int(r.get("section_order") or 0), str(r.get("id") or "")),
    )
    for row in ordered:
        content = str(row.get("content") or "").strip()
        if content:
            body_parts.append(content)
    if body_parts:
        body = "\n\n".join(body_parts)
    else:
        body = final_md.strip()
    header = f"# {title}"
    if body.lstrip().startswith("# "):
        return body + "\n"
    return f"{header}\n\n{body}\n"


def _report_html(
    section_rows: list[dict[str, Any]],
    report_md: str,
    title: str,
) -> str:
    esc_title = html.escape(title)
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{esc_title}</title>",
        "</head>",
        "<body>",
        f"<h1>{esc_title}</h1>",
    ]
    ordered = sorted(
        section_rows,
        key=lambda r: (int(r.get("section_order") or 0), str(r.get("id") or "")),
    )
    rendered_any = False
    for row in ordered:
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        rendered_any = True
        section_title = str(row.get("title") or "").strip()
        parts.append("<section>")
        if section_title:
            parts.append(f"<h2>{html.escape(section_title)}</h2>")
        for para in _paragraphs(content):
            parts.append(f"<p>{_escape_paragraph(para)}</p>")
        parts.append("</section>")
    if not rendered_any:
        # Fall back to the assembled markdown body as escaped paragraphs.
        parts.append("<section>")
        for para in _paragraphs(report_md):
            parts.append(f"<p>{_escape_paragraph(para)}</p>")
        parts.append("</section>")
    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def _paragraphs(text: str) -> list[str]:
    blocks = [block.strip() for block in text.split("\n\n")]
    return [block for block in blocks if block]


def _escape_paragraph(block: str) -> str:
    # Drop leading markdown heading hashes, escape, keep intra-block newlines as <br>.
    lines = [line.lstrip("#").strip() if line.lstrip().startswith("#") else line for line in block.splitlines()]
    return "<br>".join(html.escape(line) for line in lines)


def _evaluation_checklist(
    title: str,
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    dropped_claims: list[str],
    evidence_count: int,
    section_rows: list[dict[str, Any]],
    section_checks: list[dict[str, Any]],
) -> str:
    passed_checks = sum(1 for c in section_checks if _truthy(c.get("passed")))
    total_checks = len(section_checks)
    lines = [
        f"# Evaluation checklist — {title}",
        "",
        "Derived from the run's native DeepResearch exports.",
        "",
        f"- [x] Sources collected: {len(sources)}",
        f"- [x] Claims retained (each linked to a source): {len(claims)}",
        f"- [x] Evidence atoms: {evidence_count}",
        f"- [x] Report sections: {len(section_rows)}",
        f"- [{'x' if total_checks and passed_checks == total_checks else ' '}]"
        f" Section checks passed: {passed_checks}/{total_checks}",
        f"- [{'x' if not dropped_claims else ' '}]"
        f" Unlinked claims dropped: {len(dropped_claims)}"
        + (f" ({', '.join(dropped_claims)})" if dropped_claims else ""),
        "",
        "## Sources represented",
        "",
    ]
    for source in sources:
        label = source.get("title") or source.get("id")
        lines.append(f"- {source['id']}: {label}")
    lines.append("")
    return "\n".join(lines)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "passed"}
    return bool(value)


def adapt_native_exports(
    native_dir: str | Path,
    workspace_root: str | Path,
    *,
    report_title: str = DEFAULT_REPORT_TITLE,
) -> dict[str, Any]:
    """Map native jsonl exports in *native_dir* to the 5 demo artifacts under
    ``<workspace_root>/rsi-deep-research-report/``. Returns a manifest.

    Raises :class:`NativeExportError` if a mandatory native file is missing.
    """
    native = Path(native_dir)
    for name in _MANDATORY_NATIVE:
        if not (native / name).is_file():
            raise NativeExportError(f"missing mandatory native export: {name}")

    source_rows = _read_jsonl(native / "sources.jsonl")
    claim_rows = _read_jsonl(native / "claims.jsonl")
    evidence_rows = _read_jsonl(native / "evidence.jsonl")
    claim_evidence_rows = _read_jsonl(native / "claim_evidence.jsonl")
    section_rows = _read_jsonl(native / "sections.jsonl")
    section_checks = _read_jsonl(native / "section_checks.jsonl")
    final_md_path = native / "final.md"
    final_md = final_md_path.read_text(encoding="utf-8") if final_md_path.is_file() else ""

    sources = _map_sources(source_rows)
    valid_source_ids = {s["id"] for s in sources}
    links = _claim_source_links(claim_evidence_rows, _evidence_source_map(evidence_rows))
    claims, dropped = _map_claims(claim_rows, links, valid_source_ids)

    report_md = _report_markdown(section_rows, final_md, report_title)
    report_html = _report_html(section_rows, report_md, report_title)
    checklist = _evaluation_checklist(
        report_title, sources, claims, dropped, len(evidence_rows), section_rows, section_checks
    )

    root = Path(workspace_root) / DEMO_ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    _write_json(root / "sources.json", sources)
    _write_json(root / "claims.json", claims)
    (root / "report.md").write_text(report_md, encoding="utf-8")
    (root / "report.html").write_text(report_html, encoding="utf-8")
    (root / "evaluation-checklist.md").write_text(checklist, encoding="utf-8")

    return {
        "ok": True,
        "root": str(root),
        "artifacts": {name: str(root / name) for name in REQUIRED_ARTIFACTS},
        "counts": {
            "sources": len(sources),
            "claims": len(claims),
            "claims_dropped": len(dropped),
            "evidence": len(evidence_rows),
            "sections": len(section_rows),
        },
        "dropped_claim_ids": dropped,
        "source_ids": [s["id"] for s in sources],
    }
