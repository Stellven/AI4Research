#!/usr/bin/env python3
"""
solar-harness mineru extract <pdf-path> [--background] [--vault PATH] [--json]
solar-harness mineru scan-papers [--json]
solar-harness mineru queue-papers [--limit N] [--json]

Extracts PDF to Obsidian references/<slug>/ with provenance frontmatter.
Produces ~/.solar/reports/mineru-audit-<ts>.json with source -> generated_pages.
scan-papers discovers canonical papers from source-manifest.jsonl.
queue-papers enqueues discovered papers for idle background extraction.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
VENV_PYTHON = HARNESS_DIR / "vendor" / "mineru" / ".venv" / "bin" / "python"
QUEUE_FILE = Path.home() / ".solar" / "queues" / "mineru.jsonl"
REPORTS_DIR = Path.home() / ".solar" / "reports"
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH",
                                      str(Path.home() / "Knowledge")))
# S5: Canonical source paths
K_SOURCES_DIR = OBSIDIAN_VAULT / "_sources"
K_META_DIR = OBSIDIAN_VAULT / "_meta"
MANIFEST_JSONL = K_META_DIR / "source-manifest.jsonl"
REFERENCES_DIR = OBSIDIAN_VAULT / "references"


def _slug(pdf_path: Path) -> str:
    stem = re.sub(r"[^\w\-]", "-", pdf_path.stem).strip("-").lower()
    return stem[:60]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _mineru_version() -> str:
    if not VENV_PYTHON.exists():
        return "unavailable"
    try:
        r = subprocess.run(
            [str(VENV_PYTHON), "-c",
             "import magic_pdf; print(magic_pdf.__version__)"],
            capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _extract_with_magic_pdf(pdf_path: Path, out_dir: Path) -> list[Path]:
    """Try magic-pdf extraction. Returns list of generated .md files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        script = f"""
import sys, os, json
from pathlib import Path
try:
    from magic_pdf.data.data_reader_writer import FileBasedDataWriter
    from magic_pdf.data.dataset import PymuDocDataset
    from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
    from magic_pdf.config.enums import SupportedPdfParseMethod

    pdf_path = Path({repr(str(pdf_path))})
    out_dir = Path({repr(str(out_dir))})
    out_dir.mkdir(parents=True, exist_ok=True)

    name = pdf_path.stem
    reader = pdf_path.read_bytes()
    dataset = PymuDocDataset(reader)
    infer_result = doc_analyze(dataset, ocr=False)

    if infer_result.pdf_parse_method == SupportedPdfParseMethod.TXT:
        pipe = infer_result.pipe_txt_mode(FileBasedDataWriter(str(out_dir / 'images')), FileBasedDataWriter(str(out_dir)))
    else:
        pipe = infer_result.pipe_ocr_mode(FileBasedDataWriter(str(out_dir / 'images')), FileBasedDataWriter(str(out_dir)))

    pipe.pipe_classify()
    pipe.pipe_analyze()
    pipe.pipe_parse()
    pipe.dump_md(FileBasedDataWriter(str(out_dir)), name + '.md', str(out_dir / 'images'))
    print(json.dumps({{"ok": True, "files": [str(out_dir / (name + '.md'))], "method": "magic_pdf"}}))
except Exception as e:
    print(json.dumps({{"ok": False, "error": str(e), "method": "magic_pdf"}}))
"""
        r = subprocess.run(
            [str(VENV_PYTHON), "-c", script],
            capture_output=True, text=True, timeout=600
        )
        if r.returncode == 0:
            last_line = [l for l in r.stdout.strip().split("\n") if l.startswith("{")]
            if last_line:
                result = json.loads(last_line[-1])
                if result.get("ok"):
                    return [Path(f) for f in result.get("files", [])]
    except Exception:
        pass
    return []


def _extract_with_pymupdf(pdf_path: Path, out_dir: Path) -> list[Path]:
    """Fallback: PyMuPDF (fitz) text extraction to markdown."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        script = f"""
import json, sys
try:
    import fitz
    from pathlib import Path
    pdf_path = Path({repr(str(pdf_path))})
    out_dir = Path({repr(str(out_dir))})
    doc = fitz.open(str(pdf_path))
    files = []
    for i, page in enumerate(doc):
        text = page.get_text("markdown") or page.get_text()
        if not text.strip():
            continue
        pg_file = out_dir / f"page-{{i+1:03d}}.md"
        pg_file.write_text(text, encoding="utf-8")
        files.append(str(pg_file))
    doc.close()
    print(json.dumps({{"ok": True, "files": files, "method": "pymupdf"}}))
except Exception as e:
    print(json.dumps({{"ok": False, "error": str(e), "method": "pymupdf"}}))
"""
        r = subprocess.run(
            [str(VENV_PYTHON), "-c", script],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if line.startswith("{"):
                    result = json.loads(line)
                    if result.get("ok"):
                        return [Path(f) for f in result.get("files", [])]
    except Exception:
        pass
    return []


def extract_pdf(pdf_path: Path, vault: Path, as_json: bool = False) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    slug = _slug(pdf_path)
    ref_dir = vault / "references" / slug
    ref_dir.mkdir(parents=True, exist_ok=True)

    sha256 = _sha256(pdf_path)
    version = _mineru_version()

    # Try magic-pdf first, then pymupdf fallback
    raw_files = _extract_with_magic_pdf(pdf_path, ref_dir / "_raw")
    method = "magic_pdf"
    if not raw_files:
        raw_files = _extract_with_pymupdf(pdf_path, ref_dir / "_raw")
        method = "pymupdf"

    generated_pages: list[str] = []

    if raw_files:
        # Combine pages into index.md with provenance frontmatter + individual page files
        all_text_parts: list[str] = []
        for i, raw_f in enumerate(raw_files[:100]):  # cap at 100 pages
            try:
                text = raw_f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Per-page file with provenance
            page_file = ref_dir / f"page-{i+1:03d}.md"
            page_content = f"""---
source_pdf: {pdf_path}
source_pdf_sha256: {sha256}
source_page: {i+1}
mineru_version: {version}
extracted_at: {ts}
extraction_method: {method}
---

{text}
"""
            page_file.write_text(page_content, encoding="utf-8")
            generated_pages.append(str(page_file))
            all_text_parts.append(text)

        # Write index.md
        index_md = ref_dir / "index.md"
        index_content = f"""---
source_pdf: {pdf_path}
source_pdf_sha256: {sha256}
source_pages: {len(raw_files)}
mineru_version: {version}
extracted_at: {ts}
extraction_method: {method}
slug: {slug}
---

# {pdf_path.name}

> Extracted by MinerU ({method}) on {ts[:10]}
> Source: `{pdf_path}`
> SHA256: `{sha256[:16]}...`

{"".join(all_text_parts[:3])[:4096]}

---
*Full content split into {len(generated_pages)} page file(s) in this directory.*
"""
        index_md.write_text(index_content, encoding="utf-8")
        generated_pages.insert(0, str(index_md))
    else:
        # Nothing extracted — write stub
        stub = ref_dir / "index.md"
        stub.write_text(f"""---
source_pdf: {pdf_path}
source_pdf_sha256: {sha256}
extracted_at: {ts}
extraction_status: failed
---

# {pdf_path.name}

Extraction failed — PDF may be scanned image-only or require GPU-based OCR.
""", encoding="utf-8")
        generated_pages = [str(stub)]

    audit = {
        "source": str(pdf_path),
        "source_pdf_sha256": sha256,
        "extracted_at": ts,
        "ts": ts,
        "method": method,
        "slug": slug,
        "ref_dir": str(ref_dir),
        "generated_pages": generated_pages,
        "page_count": len(generated_pages),
    }

    # Write audit report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"mineru-audit-{report_ts}.json"
    report_path.write_text(json.dumps(audit, indent=2))

    return {
        "ok": bool(generated_pages),
        "pdf": str(pdf_path),
        "ref_dir": str(ref_dir),
        "generated_pages": generated_pages,
        "audit_report": str(report_path),
        "method": method,
        "extraction_status": "ok" if len(generated_pages) > 1 else "stub",
    }


def scan_canonical_papers(as_json: bool = False) -> dict:
    """Scan source-manifest.jsonl for papers with category=papers, media_type=application/pdf.
    Resolve actual file path: canonical_path first, then original_path fallback.
    Returns summary with discovered papers and their resolvable paths.
    """
    papers: list[dict] = []
    unresolved: list[dict] = []
    if not MANIFEST_JSONL.exists():
        result = {
            "ok": False,
            "error": f"manifest not found: {MANIFEST_JSONL}",
            "papers": [],
            "total": 0,
            "resolvable": 0,
            "unresolved": 0,
        }
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"ERROR: manifest not found at {MANIFEST_JSONL}")
        return result

    with open(MANIFEST_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("category") != "papers" or entry.get("media_type") != "application/pdf":
                continue

            canonical = Path(entry["canonical_path"])
            original = Path(entry["original_path"])
            resolved = None
            source_type = None

            if canonical.exists():
                resolved = canonical
                source_type = "canonical"
            elif original.exists():
                resolved = original
                source_type = "original_fallback"

            # Check if already extracted: look for references/<slug>/index.md
            slug = _slug(resolved) if resolved else _slug(canonical)
            ref_dir = REFERENCES_DIR / slug
            already_extracted = (ref_dir / "index.md").exists() if ref_dir else False

            paper_info = {
                "sha256": entry["sha256"],
                "original_path": str(original),
                "canonical_path": str(canonical),
                "resolved_path": str(resolved) if resolved else None,
                "source_type": source_type,
                "size": entry.get("size", 0),
                "name": canonical.name,
                "slug": slug,
                "already_extracted": already_extracted,
                "ref_dir": str(ref_dir),
            }

            if resolved:
                papers.append(paper_info)
            else:
                unresolved.append(paper_info)

    result = {
        "ok": True,
        "manifest": str(MANIFEST_JSONL),
        "total": len(papers) + len(unresolved),
        "resolvable": len(papers),
        "unresolved": len(unresolved),
        "already_extracted": sum(1 for p in papers if p["already_extracted"]),
        "pending_extraction": sum(1 for p in papers if not p["already_extracted"]),
        "papers": papers,
        "unresolved": unresolved,
    }
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Canonical papers scan: {result['total']} total, {result['resolvable']} resolvable, "
              f"{result['unresolved']} unresolved")
        print(f"  already extracted: {result['already_extracted']}, pending: {result['pending_extraction']}")
    return result


def queue_canonical_papers(limit: int = 0, as_json: bool = False) -> dict:
    """Enqueue canonical papers for idle background extraction.
    Only queues papers that are not already extracted.
    Never runs extraction in foreground — always queues to mineru.jsonl.
    """
    scan = scan_canonical_papers(as_json=False)
    if not scan.get("ok"):
        if as_json:
            print(json.dumps(scan, indent=2))
        return scan

    pending = [p for p in scan.get("papers", []) if not p["already_extracted"]]
    if limit > 0:
        pending = pending[:limit]

    if not pending:
        result = {
            "ok": True,
            "queued": 0,
            "message": "no pending papers to extract",
            "total_papers": scan["total"],
            "already_extracted": scan["already_extracted"],
        }
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print("No pending papers to extract.")
        return result

    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    jobs = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for paper in pending:
        job = {
            "ts": ts,
            "pdf": paper["resolved_path"],
            "vault": str(OBSIDIAN_VAULT),
            "status": "queued",
            "source_type": paper["source_type"],
            "canonical_path": paper["canonical_path"],
            "sha256": paper["sha256"],
            "slug": paper["slug"],
        }
        with open(QUEUE_FILE, "a", encoding="utf-8") as qf:
            qf.write(json.dumps(job) + "\n")
        jobs.append(job)

    result = {
        "ok": True,
        "queued": len(jobs),
        "queue_file": str(QUEUE_FILE),
        "total_papers": scan["total"],
        "already_extracted": scan["already_extracted"],
        "remaining_unresolved": scan["unresolved"],
        "jobs_sample": jobs[:3],
        "mode": "idle_background",
        "note": "extraction will run only when system is idle (HIDIdleTime >= 60s, no active claude processes)",
    }
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Queued {len(jobs)} papers for idle background extraction.")
        print(f"  queue: {QUEUE_FILE}")
        print(f"  mode: idle/background (worker runs only when system is idle)")
    return result


def doctor(as_json: bool = False) -> dict:
    """Quick health check: venv + canonical papers input + extraction output path."""
    venv_ok = VENV_PYTHON.exists()
    scan = scan_canonical_papers(as_json=False)
    references_dir = REFERENCES_DIR
    output_under_knowledge = str(references_dir).startswith(str(OBSIDIAN_VAULT))

    result = {
        "ok": venv_ok and scan.get("ok", False),
        "venv": str(VENV_PYTHON),
        "venv_ok": venv_ok,
        "canonical_papers_input": str(K_SOURCES_DIR / "papers"),
        "papers_in_manifest": scan.get("total", 0),
        "resolvable_pdfs": scan.get("resolvable", 0),
        "extraction_output": str(references_dir),
        "output_under_knowledge": output_under_knowledge,
        "worker_mode": "idle_background_queued",
        "foreground_blocking": False,
    }

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        tag = "✅" if result["ok"] else "⚠️"
        print(f"{tag} MinerU doctor")
        print(f"  venv:             {'ok' if venv_ok else 'missing'} — {VENV_PYTHON}")
        print(f"  canonical papers: {scan.get('total',0)} in manifest, "
              f"{scan.get('resolvable',0)} resolvable")
        print(f"  extraction output: {references_dir}")
        print(f"  worker:           idle/background (no foreground blocking)")
    return result


def main() -> None:
    args = sys.argv[1:]

    # doctor subcommand
    if args and args[0] == "doctor":
        as_json = "--json" in args
        doctor(as_json=as_json)
        return

    # S5 subcommands: scan-papers, queue-papers
    if args and args[0] == "scan-papers":
        as_json = "--json" in args
        scan_canonical_papers(as_json=as_json)
        return

    if args and args[0] == "queue-papers":
        as_json = "--json" in args
        limit = 0
        i = 1
        while i < len(args):
            if args[i] == "--limit" and i + 1 < len(args):
                limit = int(args[i + 1])
                i += 2
            else:
                i += 1
        queue_canonical_papers(limit=limit, as_json=as_json)
        return

    # Original extract subcommand
    if args and args[0] == "extract":
        args = args[1:]  # consume 'extract' subcommand

    background = "--background" in args
    as_json = "--json" in args
    vault_arg = None
    pdf_paths: list[Path] = []

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--background", "--json"):
            i += 1; continue
        elif a == "--vault":
            i += 1
            vault_arg = args[i] if i < len(args) else None
        elif not a.startswith("--"):
            pdf_paths.append(Path(a))
        i += 1

    if not pdf_paths:
        print("Usage: solar-harness mineru extract <pdf-path> [--background] [--vault PATH] [--json]", file=sys.stderr)
        print("       solar-harness mineru scan-papers [--json]", file=sys.stderr)
        print("       solar-harness mineru queue-papers [--limit N] [--json]", file=sys.stderr)
        sys.exit(1)

    vault = Path(vault_arg) if vault_arg else OBSIDIAN_VAULT

    if background:
        # Queue jobs and return immediately
        QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        jobs = []
        for pdf in pdf_paths:
            job = {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "pdf": str(pdf), "vault": str(vault), "status": "queued"
            }
            with open(QUEUE_FILE, "a") as qf:
                qf.write(json.dumps(job) + "\n")
            jobs.append(job)
        result = {"ok": True, "queued": len(jobs), "queue_file": str(QUEUE_FILE), "jobs": jobs}
        print(json.dumps(result, indent=2) if as_json else f"Queued {len(jobs)} PDF(s) for background extraction")
        return

    results = []
    for pdf in pdf_paths:
        if not pdf.exists():
            results.append({"ok": False, "pdf": str(pdf), "error": "file not found"})
            continue
        results.append(extract_pdf(pdf, vault, as_json))

    if len(results) == 1:
        out = results[0]
    else:
        out = {"ok": all(r.get("ok") for r in results), "results": results}

    if as_json:
        print(json.dumps(out, indent=2))
    else:
        for r in results:
            status = "✅" if r.get("ok") else "❌"
            print(f"{status} {r.get('pdf','')} → {r.get('ref_dir','')} ({r.get('page_count',0)} pages)")


if __name__ == "__main__":
    main()
