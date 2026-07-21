"""Import human/Gemini/GPT search Markdown into survey ledger JSONL files."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SOURCE_TYPE_ALIASES = {
    "official": "official_doc",
    "official docs": "official_doc",
    "official_doc": "official_doc",
    "documentation": "official_doc",
    "repo": "code",
    "repository": "code",
    "github": "code",
    "paper": "paper",
    "arxiv": "paper",
    "benchmark": "benchmark",
    "dataset": "dataset",
    "standard": "standard",
    "web": "web",
    "other": "other",
}

RESEARCH_ANGLE_ALIASES = {
    "history": "literature_lineage",
    "lineage": "literature_lineage",
    "literature": "literature_lineage",
    "literature_lineage": "literature_lineage",
    "literature_lineage_literature_lineage": "literature_lineage",
    "evolution": "literature_lineage",
    "谱系": "literature_lineage",
    "文献谱系": "literature_lineage",
    "taxonomy": "method_taxonomy",
    "method": "method_taxonomy",
    "method_taxonomy": "method_taxonomy",
    "method_taxonomy_method_taxonomy": "method_taxonomy",
    "方法": "method_taxonomy",
    "分类": "method_taxonomy",
    "方法分类": "method_taxonomy",
    "evaluation": "evaluation_protocol",
    "eval": "evaluation_protocol",
    "protocol": "evaluation_protocol",
    "benchmark": "evaluation_protocol",
    "evaluation_protocol": "evaluation_protocol",
    "evaluation_protocol_evaluation_protocol": "evaluation_protocol",
    "评估": "evaluation_protocol",
    "评价": "evaluation_protocol",
    "评估协议": "evaluation_protocol",
    "controversy": "controversy",
    "contradiction": "controversy",
    "negative_evidence": "controversy",
    "negative": "controversy",
    "risk": "controversy",
    "争议": "controversy",
    "反证": "controversy",
    "争议反证": "controversy",
    "engineering": "engineering",
    "deployment": "engineering",
    "engineering_deployment": "engineering",
    "engineering_deployment_engineering_and_deployment": "engineering",
    "工程": "engineering",
    "部署": "engineering",
    "工程部署": "engineering",
}
REQUIRED_RESEARCH_ANGLES = ["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"]

RETURN_FORMAT_EXAMPLE = """# External Search Results: <brief>

## Source 1: <title>
URL: <https://...>
Publisher: <publisher or N/A>
Published: <date or N/A>
Source Type: <paper|official_doc|code|benchmark|dataset|standard|web|other>
Research Angles: <literature_lineage|method_taxonomy|evaluation_protocol|controversy|engineering>

Summary:
- <2-5 factual bullets>

Key Claims:
- <claim supported by this source>
- <claim supported by this source>

Relevant Quotes:
> <short quote or N/A>
"""


def _stable_id(prefix: str, *parts: str) -> str:
    text = "\n".join(parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _normalize_source_type(value: str) -> str:
    cleaned = re.sub(r"[<>|].*$", "", str(value or "")).strip().lower()
    return SOURCE_TYPE_ALIASES.get(cleaned, cleaned if cleaned in set(SOURCE_TYPE_ALIASES.values()) else "web")


def _normalize_research_angles(value: str, block: str = "") -> list[str]:
    raw = str(value or "")
    parts = re.split(r"[,，;/|]+", raw)
    angles: list[str] = []
    for part in parts:
        cleaned = re.sub(r"[<>]", "", part).strip().lower().replace("-", "_").replace(" ", "_")
        cleaned = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", "_", cleaned).strip("_")
        if not cleaned:
            continue
        normalized = RESEARCH_ANGLE_ALIASES.get(cleaned)
        if normalized and normalized not in angles:
            angles.append(normalized)
    if angles:
        return angles
    lowered = (block or "").lower()
    inferred = []
    inference_patterns = {
        "literature_lineage": r"literature lineage|文献谱系|history|evolution|演进",
        "method_taxonomy": r"method taxonomy|taxonomy|方法分类|representation|control policy",
        "evaluation_protocol": r"evaluation protocol|benchmark|baseline|ablation|metric|评估协议",
        "controversy": r"controversy|negative evidence|contradiction|争议|反证",
        "engineering": r"engineering|deployment|production|observability|工程|部署",
    }
    for angle, pattern in inference_patterns.items():
        if re.search(pattern, lowered):
            inferred.append(angle)
    return inferred


def _research_angle_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        angle: sum(1 for rec in records if angle in (rec.get("research_angles") or []))
        for angle in REQUIRED_RESEARCH_ANGLES
    }


def _missing_research_angles(records: list[dict[str, Any]]) -> list[str]:
    counts = _research_angle_counts(records)
    return [angle for angle in REQUIRED_RESEARCH_ANGLES if counts.get(angle, 0) < 1]


def _field(block: str, name: str) -> str:
    match = re.search(rf"(?im)^{re.escape(name)}:\s*(.+)$", block)
    return match.group(1).strip() if match else ""


def _section_lines(block: str, heading: str) -> list[str]:
    pattern = rf"(?ims)^{re.escape(heading)}:\s*\n(.*?)(?=^\w[\w ]+:\s*$|^##\s+Source\s+\d+\s*:|\Z)"
    match = re.search(pattern, block)
    if not match:
        return []
    lines: list[str] = []
    for line in match.group(1).splitlines():
        item = line.strip()
        if not item:
            continue
        item = re.sub(r"^[-*>]\s*", "", item).strip()
        if item and item.upper() != "N/A":
            lines.append(item)
    return lines


def _infer_source_type_from_fields(title: str, url: str, publisher: str) -> str:
    lowered = " ".join([title, url, publisher]).lower()
    if "github.com" in lowered:
        return "code"
    if any(token in lowered for token in ("paperswithcode", "benchmark", "leaderboard")):
        return "benchmark"
    if any(token in lowered for token in ("arxiv.org", "openreview", "doi.org", "/program/20", "/papers/")):
        return "paper"
    if any(token in lowered for token in ("caisconf.org", "eurekalert", "official", "conference homepage", "workshops index", "accepted papers index")):
        return "official_doc"
    return "web"


def _infer_research_angles_from_context(category: str, title: str, summary: str, source_type: str) -> list[str]:
    text = " ".join([category, title, summary]).lower()
    inferred: list[str] = []
    if re.search(r"official|会议信号|主页|workshop|accepted|history|lineage|evolution|演进|谱系", text):
        inferred.append("literature_lineage")
    if re.search(r"planning|protocol|specification|taxonomy|tool|orchestration|multi-agent|方法|分类|机制|runtime", text):
        inferred.append("method_taxonomy")
    if re.search(r"evaluation|benchmark|reliability|评测|评估|diagnostic|metric", text):
        inferred.append("evaluation_protocol")
    if re.search(r"risk|safety|limitation|controversy|contradiction|failure|争议|反证|失败", text):
        inferred.append("controversy")
    if re.search(r"engineering|deployment|system|inference|code|repo|observability|伸缩|工程|部署|架构", text):
        inferred.append("engineering")
    if source_type == "code" and "engineering" not in inferred:
        inferred.append("engineering")
    if source_type == "paper" and "method_taxonomy" not in inferred:
        inferred.append("method_taxonomy")
    if source_type == "benchmark" and "evaluation_protocol" not in inferred:
        inferred.append("evaluation_protocol")
    if source_type == "official_doc" and "literature_lineage" not in inferred:
        inferred.append("literature_lineage")
    return inferred or ["engineering"]


def parse_gemini_deep_search_markdown(markdown: str) -> list[dict[str, Any]]:
    text = str(markdown or "")
    lines = text.splitlines()
    records: list[dict[str, Any]] = []
    category = ""
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line.startswith("类别 "):
            category = line
            idx += 1
            continue
        if not line or line.startswith("#") or line.startswith("## "):
            idx += 1
            continue
        if idx + 3 >= len(lines):
            idx += 1
            continue
        source_line = lines[idx + 1].strip()
        summary_line = lines[idx + 2].strip()
        url_line = lines[idx + 3].strip()
        if not source_line.startswith("来源/作者:") or not summary_line.startswith("核心价值:") or not url_line.startswith("URL:"):
            idx += 1
            continue
        title = line
        publisher = source_line.split(":", 1)[1].strip()
        summary = summary_line.split(":", 1)[1].strip()
        url = url_line.split(":", 1)[1].strip().strip("<>")
        source_type = _infer_source_type_from_fields(title, url, publisher)
        research_angles = _infer_research_angles_from_context(category, title, summary, source_type)
        records.append({
            "title": title,
            "url": url,
            "publisher": publisher,
            "published": "",
            "source_type": source_type,
            "research_angles": research_angles,
            "summary": [summary],
            "key_claims": [summary],
            "quotes": [],
            "content": "\n".join([
                f"Title: {title}",
                f"URL: {url}",
                f"Publisher: {publisher or 'N/A'}",
                "Published: N/A",
                f"Research Angles: {', '.join(research_angles)}",
                "",
                "Summary:",
                f"- {summary}",
                "",
                "Key Claims:",
                f"- {summary}",
                "",
                "Relevant Quotes:",
                "> N/A",
            ]),
        })
        idx += 4
    return records


def diagnose_survey_search_markdown(markdown: str) -> dict[str, Any]:
    text = markdown or ""
    blocks = re.split(r"(?im)^##\s+Source\s+\d+\s*:\s*", text)
    source_blocks = blocks[1:]
    missing: list[dict[str, Any]] = []
    for idx, block in enumerate(source_blocks, start=1):
        fields = []
        if not _field(block, "URL") and not re.findall(r"https?://[^\s>)]+", block):
            fields.append("URL")
        if not _field(block, "Source Type"):
            fields.append("Source Type")
        if not _field(block, "Research Angles"):
            fields.append("Research Angles")
        if not _section_lines(block, "Summary"):
            fields.append("Summary")
        if not _section_lines(block, "Key Claims"):
            fields.append("Key Claims")
        if fields:
            title = block.strip().splitlines()[0].strip(" #\t") if block.strip().splitlines() else ""
            missing.append({"source_index": idx, "title": title or "N/A", "missing_fields": fields})
    angle_records = [
        {"research_angles": _normalize_research_angles(_field(block, "Research Angles"), block)}
        for block in source_blocks
    ]
    angle_counts = _research_angle_counts(angle_records)
    return {
        "source_heading_count": len(source_blocks),
        "url_count": len(re.findall(r"https?://[^\s>)]+", text)),
        "has_external_search_results_heading": bool(re.search(r"(?im)^#\s+External Search Results:", text)),
        "missing_fields_by_source": missing[:20],
        "expected_source_heading": "## Source 1: <title>",
        "expected_fields": ["URL", "Publisher", "Published", "Source Type", "Research Angles", "Summary", "Key Claims", "Relevant Quotes"],
        "repair_hint": "Paste results into returned_sources.md using the exact Source block schema from survey_source_gap_handoff.md.",
        "required_research_angles": REQUIRED_RESEARCH_ANGLES,
        "research_angle_counts": angle_counts,
        "missing_research_angles": [angle for angle in REQUIRED_RESEARCH_ANGLES if angle_counts.get(angle, 0) < 1],
        "example": RETURN_FORMAT_EXAMPLE,
    }


def parse_survey_search_markdown(markdown: str) -> list[dict[str, Any]]:
    text = markdown or ""
    blocks = re.split(r"(?im)^##\s+Source\s+\d+\s*:\s*", text)
    records: list[dict[str, Any]] = []
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip(" #\t") or "External search source"
        url = _field(block, "URL")
        if not url:
            urls = re.findall(r"https?://[^\s>)]+", block)
            url = urls[0] if urls else ""
        url = url.strip("<>")
        if not url:
            continue
        source_type = _normalize_source_type(_field(block, "Source Type") or "web")
        research_angles = _normalize_research_angles(_field(block, "Research Angles"), block)
        summary = _section_lines(block, "Summary")
        key_claims = _section_lines(block, "Key Claims")
        quotes = _section_lines(block, "Relevant Quotes")
        if not key_claims:
            key_claims = summary[:2] or [title]
        content = "\n".join([
            f"Title: {title}",
            f"URL: {url}",
            f"Publisher: {_field(block, 'Publisher') or 'N/A'}",
            f"Published: {_field(block, 'Published') or 'N/A'}",
            f"Research Angles: {', '.join(research_angles) if research_angles else 'N/A'}",
            "",
            "Summary:",
            *[f"- {item}" for item in summary],
            "",
            "Key Claims:",
            *[f"- {item}" for item in key_claims],
            "",
            "Relevant Quotes:",
            *[f"> {item}" for item in quotes],
        ]).strip()
        records.append({
            "title": title,
            "url": url,
            "publisher": _field(block, "Publisher") or "",
            "published": _field(block, "Published") or "",
            "source_type": source_type,
            "research_angles": research_angles,
            "summary": summary,
            "key_claims": key_claims,
            "quotes": quotes,
            "content": content,
        })
    if records:
        return records
    return parse_gemini_deep_search_markdown(text)


def import_survey_search_results(
    output_dir: str | Path,
    input_md: str | Path,
    *,
    continue_finalize: bool = False,
    brief: str = "",
    target_chars: int = 50000,
    audience: str = "technical",
    domain: str = "ai",
    run_id: str = "",
    section_limit: int = 3,
    repair_limit: int = 0,
    min_finalized: int | None = None,
    min_chars: int = 1200,
    require_complete: bool = False,
    narrative_backend: str = "",
    narrative_model: str = "",
    narrative_fallback_models: list[str] | None = None,
    narrative_command: str = "",
    narrative_timeout: int = 0,
    narrative_max_budget_usd: float = 0.0,
    narrative_min_chars: int = 0,
    narrative_require_hitl: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    markdown = Path(input_md).expanduser().read_text(encoding="utf-8")
    records = parse_survey_search_markdown(markdown)
    if not records:
        payload = {
            "ok": False,
            "reason": "no_importable_sources",
            "imported_sources": 0,
            "input_md": str(Path(input_md).expanduser()),
            "diagnostics": diagnose_survey_search_markdown(markdown),
        }
        (root / "survey_import_search_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload

    sources = _read_jsonl(root / "sources.jsonl")
    evidence = _read_jsonl(root / "evidence.jsonl")
    claims = _read_jsonl(root / "claims.jsonl")
    links = _read_jsonl(root / "claim_evidence.jsonl")
    existing_urls = {str(row.get("url") or "") for row in sources}
    imported_sources = 0
    imported_evidence = 0
    imported_claims = 0
    imported_links = 0
    for rec in records:
        source_id = _stable_id("src", rec["url"])
        if rec["url"] not in existing_urls:
            sources.append({
                "id": source_id,
                "source_id": source_id,
                "url": rec["url"],
                "title": rec["title"],
                "source_type": rec["source_type"],
                "research_angle": (rec.get("research_angles") or ["other"])[0],
                "research_angles": rec.get("research_angles") or [],
                "publisher": rec.get("publisher") or "",
                "published_at": rec.get("published") or "",
                "content_hash": _stable_id("hash", rec["content"]),
            })
            existing_urls.add(rec["url"])
            imported_sources += 1
        for claim_text in rec["key_claims"]:
            evidence_text = "\n".join([
                f"Source: {rec['title']}",
                f"URL: {rec['url']}",
                f"Research Angles: {', '.join(rec.get('research_angles') or []) or 'N/A'}",
                f"Claim: {claim_text}",
                "",
                rec["content"],
            ]).strip()
            evidence_id = _stable_id("ev", rec["url"], claim_text)
            if not any(str(row.get("id") or row.get("evidence_id")) == evidence_id for row in evidence):
                evidence.append({
                    "id": evidence_id,
                    "evidence_id": evidence_id,
                    "source_id": source_id,
                    "content": evidence_text,
                    "span_text": evidence_text,
                    "evidence_type": "human_search_claim_span",
                    "confidence": 0.75,
                    "span_start": 0,
                    "span_end": len(evidence_text),
                    "content_hash": _stable_id("hash", evidence_text),
                })
                imported_evidence += 1
            claim_id = _stable_id("cl", rec["url"], claim_text)
            if not any(str(row.get("id") or row.get("claim_id")) == claim_id for row in claims):
                claims.append({
                    "id": claim_id,
                    "claim_id": claim_id,
                    "claim_text": claim_text,
                    "text": claim_text,
                    "claim_type": "factual",
                    "stance": "support",
                    "confidence": 0.75,
                    "section_ref": "",
                    "content_hash": _stable_id("hash", claim_text),
                })
                imported_claims += 1
            link_id = _stable_id("link", claim_id, evidence_id)
            if not any(str(row.get("id")) == link_id for row in links):
                links.append({
                    "id": link_id,
                    "claim_id": claim_id,
                    "evidence_id": evidence_id,
                    "relation": "supports",
                    "strength": 0.75,
                })
                imported_links += 1

    _write_jsonl(root / "sources.jsonl", sources)
    _write_jsonl(root / "evidence.jsonl", evidence)
    _write_jsonl(root / "claims.jsonl", claims)
    _write_jsonl(root / "claim_evidence.jsonl", links)
    payload: dict[str, Any] = {
        "ok": True,
        "records_parsed": len(records),
        "imported_sources": imported_sources,
        "imported_evidence": imported_evidence,
        "imported_claims": imported_claims,
        "imported_links": imported_links,
        "research_angle_counts": _research_angle_counts(records),
        "missing_research_angles": _missing_research_angles(records),
        "sources_path": str(root / "sources.jsonl"),
        "evidence_path": str(root / "evidence.jsonl"),
        "claims_path": str(root / "claims.jsonl"),
        "claim_evidence_path": str(root / "claim_evidence.jsonl"),
        "run_path": str(root / "survey_import_search_results.json"),
    }
    if continue_finalize:
        from .finalize_run import finalize_survey_run

        payload["finalize"] = finalize_survey_run(
            root,
            brief=brief,
            target_chars=target_chars,
            audience=audience,
            domain=domain,
            run_id=run_id,
            skip_plan=(root / "survey_report_ast.json").exists(),
            skip_pack=False,
            section_limit=section_limit,
            repair_limit=repair_limit,
            min_finalized=min_finalized,
            min_chars=min_chars,
            require_complete=require_complete,
            narrative_backend=narrative_backend,
            narrative_model=narrative_model,
            narrative_fallback_models=narrative_fallback_models,
            narrative_command=narrative_command,
            narrative_timeout=narrative_timeout,
            narrative_max_budget_usd=narrative_max_budget_usd,
            narrative_min_chars=narrative_min_chars,
            narrative_require_hitl=narrative_require_hitl,
        )
    (root / "survey_import_search_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
