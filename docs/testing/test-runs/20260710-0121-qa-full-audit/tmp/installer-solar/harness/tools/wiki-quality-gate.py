#!/usr/bin/env python3
"""
wiki-quality-gate.py — detect and quarantine low-quality derived wiki pages.

This is intentionally conservative: it does not delete source uploads or
user-authored notes. It only moves machine-generated PDF stubs out of the
Obsidian vault when --apply is passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any


HOME = Path.home()
DEFAULT_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(HOME / "Knowledge")))
DEFAULT_DB = Path(os.environ.get("SOLAR_DB", str(HOME / ".solar" / "solar.db")))
DEFAULT_QUARANTINE = HOME / ".solar" / "harness" / "quarantine" / "wiki-low-quality"
KNOWLEDGE_ROOTS = (
    "synthesis",
    "references",
    "concepts",
    "entities",
    "projects",
    "skills",
    "rules",
    "analysis",
)
GRAPH_EXCLUDED_PARTS = {"_raw", ".dispatch", "file-uploads", "uploads"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def frontmatter_field(text: str, name: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    for raw in parts[1].splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def iter_markdown(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def is_pdf_page_dump(path: Path, text: str) -> bool:
    name = path.name.lower()
    if re.fullmatch(r"page-\d+\.md", name):
        return True
    if frontmatter_field(text, "source_page") and frontmatter_field(text, "source_pdf"):
        return True
    return False


def is_pdf_index_dump(path: Path, text: str) -> bool:
    if path.name.lower() != "index.md":
        return False
    if not frontmatter_field(text, "source_pdf"):
        return False
    raw_markers = (
        "Extracted by MinerU",
        "Full content split into",
        "extraction_method: pymupdf",
        "Abstract\n",
        "arXiv:",
    )
    return sum(1 for marker in raw_markers if marker in text) >= 2


def looks_like_ocr_or_code_dump(text: str) -> bool:
    body = text.split("---", 2)[-1] if text.startswith("---") else text
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return False

    code_like = 0
    figure_like = 0
    headings = 0
    for line in lines:
        if re.search(r"\b(pid|tl\.program_id|BLOCK_SIZE|num_xcds|program_id|def |class |import )\b", line):
            code_like += 1
        if re.match(r"^(Figure|Table)\s+\d+[:.]", line, re.IGNORECASE):
            figure_like += 1
        if line.startswith("#"):
            headings += 1

    density = (code_like + figure_like) / max(len(lines), 1)
    return density >= 0.18 and headings <= 2


def has_knowledge_structure(text: str) -> bool:
    required = (
        "论点",
        "问题",
        "方法",
        "机制",
        "实验",
        "证据",
        "局限",
        "来源",
        "implication",
        "limitation",
        "evidence",
    )
    body = text.lower()
    hits = sum(1 for item in required if item.lower() in body)
    headings = len(re.findall(r"^#{2,}\s+", text, re.MULTILINE))
    return hits >= 3 or headings >= 4


def quality_findings(vault: Path, min_words: int) -> list[dict[str, Any]]:
    roots = [vault / name for name in KNOWLEDGE_ROOTS]
    findings: list[dict[str, Any]] = []
    for root in roots:
        for path in iter_markdown(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            words = len(re.findall(r"\w+", text))
            reasons = []
            pdf_page_dump = is_pdf_page_dump(path, text)
            pdf_index_dump = is_pdf_index_dump(path, text)
            if "Auto-extracted from PDF" in text:
                reasons.append("auto_extracted_pdf_stub")
            if "Auto-generated stub from batch backfill" in text:
                reasons.append("batch_backfill_stub")
            if frontmatter_field(text, "backfill").lower() == "true" and words < min_words:
                reasons.append("batch_backfill_stub")
            if "batch-backfill" in text[:1200] and words < min_words:
                reasons.append("batch_backfill_stub")
            if pdf_page_dump:
                reasons.append("raw_pdf_page_dump")
            if pdf_index_dump:
                reasons.append("raw_pdf_index_dump")
            if pdf_page_dump and looks_like_ocr_or_code_dump(text):
                reasons.append("ocr_or_code_page_dump")
            if "Abstract" in text[:3000] and words < min_words and frontmatter_field(text, "source_type") == "pdf":
                reasons.append("abstract_only_pdf_note")
            if words < min_words and pdf_page_dump and not has_knowledge_structure(text):
                reasons.append("missing_deep_knowledge_structure")
            reasons = list(dict.fromkeys(reasons))
            if reasons and (
                any(r in reasons for r in ("auto_extracted_pdf_stub", "batch_backfill_stub", "raw_pdf_page_dump", "ocr_or_code_page_dump"))
                or "raw_pdf_index_dump" in reasons
                or (words < min_words and "missing_deep_knowledge_structure" in reasons)
            ):
                findings.append({
                    "path": str(path),
                    "relative_path": str(path.relative_to(vault)),
                    "words": words,
                    "bytes": path.stat().st_size,
                    "title": frontmatter_field(text, "title") or path.stem,
                    "source": frontmatter_field(text, "source") or frontmatter_field(text, "source_file"),
                    "dispatch_id": frontmatter_field(text, "dispatch_id") or frontmatter_field(text, "dispatch"),
                    "reasons": reasons,
                    "sha256": sha256_file(path),
                })
    return findings


def normalize_target(raw: str) -> str:
    target = raw.strip().split("|", 1)[0].split("#", 1)[0].strip()
    target = target.replace("\\", "/")
    if target.endswith(".md"):
        target = target[:-3]
    return target.strip("/").lower()


def graph_candidates(vault: Path) -> list[Path]:
    candidates: list[Path] = []
    for root_name in KNOWLEDGE_ROOTS:
        root = vault / root_name
        for path in iter_markdown(root):
            rel = path.relative_to(vault)
            parts = set(rel.parts)
            if parts & GRAPH_EXCLUDED_PARTS:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if is_pdf_page_dump(path, text) or is_pdf_index_dump(path, text):
                continue
            candidates.append(path)
    return sorted(candidates)


def graph_audit(vault: Path, sample_limit: int = 50) -> dict[str, Any]:
    docs = graph_candidates(vault)
    by_key: dict[str, str] = {}
    for path in docs:
        rel_no_ext = str(path.relative_to(vault).with_suffix("")).replace("\\", "/").lower()
        by_key[rel_no_ext] = str(path.relative_to(vault))
        by_key[path.stem.lower()] = str(path.relative_to(vault))

    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {str(path.relative_to(vault)): set() for path in docs}
    broken: list[dict[str, str]] = []

    for path in docs:
        rel = str(path.relative_to(vault))
        text = path.read_text(encoding="utf-8", errors="replace")
        links = set()
        links.update(normalize_target(m.group(1)) for m in re.finditer(r"\[\[([^\]]+)\]\]", text))
        links.update(normalize_target(m.group(1)) for m in re.finditer(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)", text))
        links.discard("")
        outgoing[rel] = set()
        for target in sorted(links):
            matched = by_key.get(target) or by_key.get(Path(target).stem.lower())
            if matched and matched != rel:
                outgoing[rel].add(matched)
                incoming.setdefault(matched, set()).add(rel)
            elif matched == rel:
                continue
            elif target:
                broken.append({"source": rel, "target": target})

    orphans = []
    for rel in sorted(incoming):
        if not incoming.get(rel) and not outgoing.get(rel):
            orphans.append(rel)

    return {
        "doc_count": len(docs),
        "orphan_count": len(orphans),
        "orphans_sample": orphans[:sample_limit],
        "broken_link_count": len(broken),
        "broken_links_sample": broken[:sample_limit],
    }


def mark_deleted_in_db(db_path: Path, rel_path: str) -> bool:
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.execute(
            "UPDATE obsidian_vault_index SET deleted_at = ? WHERE file_path = ?",
            (now, rel_path),
        )
        try:
            conn.execute(
                "DELETE FROM fts_unified_search WHERE doc_id = ?",
                (f"obsidian:{rel_path}",),
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def quarantine(findings: list[dict[str, Any]], vault: Path, dest_root: Path, db_path: Path) -> dict[str, Any]:
    batch = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = dest_root / batch
    manifest_path = dest / "manifest.jsonl"
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for item in findings:
        src = Path(item["path"])
        rel = Path(item["relative_path"])
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
        db_marked = mark_deleted_in_db(db_path, item["relative_path"])
        record = {**item, "quarantined_to": str(target), "db_marked_deleted": db_marked}
        moved.append(record)
        with manifest_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"batch": batch, "dest": str(dest), "manifest": str(manifest_path), "moved": moved}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit/quarantine low-quality wiki pages")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE))
    parser.add_argument("--min-words", type=int, default=1200)
    parser.add_argument("--apply", action="store_true", help="Move low-quality pages out of the vault")
    parser.add_argument("--no-graph", action="store_true", help="Skip wikilink graph audit")
    parser.add_argument("--fail-on-orphans", action="store_true", help="Return non-zero when graph orphans exist")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault)
    findings = quality_findings(vault, args.min_words)
    graph = None if args.no_graph else graph_audit(vault)
    result: dict[str, Any] = {
        "ok": not findings and not (args.fail_on_orphans and graph and graph.get("orphan_count", 0) > 0),
        "vault": str(vault),
        "apply": args.apply,
        "min_words": args.min_words,
        "low_quality_count": len(findings),
        "findings": findings,
    }
    if graph is not None:
        result["graph"] = graph
    if args.apply and findings:
        result["quarantine"] = quarantine(findings, vault, Path(args.quarantine_dir), Path(args.db))
        result["ok"] = not (args.fail_on_orphans and graph and graph.get("orphan_count", 0) > 0)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"low_quality_count={len(findings)} apply={args.apply}")
        if graph is not None:
            print(f"graph_doc_count={graph['doc_count']} graph_orphan_count={graph['orphan_count']} broken_link_count={graph['broken_link_count']}")
        for item in findings:
            print(f"- {item['relative_path']} words={item['words']} reasons={','.join(item['reasons'])}")
        if "quarantine" in result:
            print(f"quarantine={result['quarantine']['dest']}")
    if findings and not args.apply:
        return 1
    if args.fail_on_orphans and graph and graph.get("orphan_count", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
