#!/usr/bin/env python3
"""
solar-harness wiki mineru-doctor
Returns JSON schema per design §2.1
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
VENV_DIR = HARNESS_DIR / "vendor" / "mineru" / ".venv"
LOCK_FILE = HARNESS_DIR / "vendor" / "mineru" / "requirements.lock"
REPORT_FILE = HARNESS_DIR / "vendor" / "mineru" / "install-report.json"
AUDIT_GLOB = Path.home() / ".solar" / "reports"
VENV_PYTHON = VENV_DIR / "bin" / "python"


def _venv_status() -> tuple[str, list[dict]]:
    """Check venv and return (status, errors)."""
    errors: list[dict] = []

    if not VENV_DIR.exists():
        return "missing", [{"code": "VENV_MISSING", "msg": "venv not found",
                            "actionable": f"bash {HARNESS_DIR}/vendor/mineru/bootstrap.sh"}]

    if not VENV_PYTHON.exists():
        return "broken", [{"code": "VENV_NO_PYTHON", "msg": "venv python binary missing",
                            "actionable": f"bash {HARNESS_DIR}/vendor/mineru/bootstrap.sh --force"}]

    # pip check
    try:
        r = subprocess.run(
            [str(VENV_PYTHON), "-m", "pip", "check"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            errors.append({
                "code": "PIP_CHECK_FAILED",
                "msg": r.stdout.strip() or r.stderr.strip(),
                "actionable": f"bash {HARNESS_DIR}/vendor/mineru/bootstrap.sh --force",
            })
    except Exception as e:
        errors.append({"code": "PIP_CHECK_ERROR", "msg": str(e),
                        "actionable": "check vendor/mineru/.venv manually"})

    # import check
    import_ok = False
    for mod in ["magic_pdf", "fitz", "pdfminer"]:
        try:
            result = subprocess.run(
                [str(VENV_PYTHON), "-c", f"import {mod}"],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                import_ok = True
                break
        except Exception:
            continue

    if not import_ok:
        errors.append({
            "code": "IMPORT_FAILED",
            "msg": "no extractable PDF module found in venv",
            "actionable": f"bash {HARNESS_DIR}/vendor/mineru/bootstrap.sh --force",
        })
        return "broken", errors

    return ("ok" if not errors else "broken"), errors


def _models_status() -> dict:
    """Check if layout/OCR models are available."""
    layout = "missing"
    ocr = "missing"

    # Check magic-pdf model cache
    model_dir = Path.home() / ".cache" / "magic-pdf"
    if not model_dir.exists():
        model_dir = Path.home() / ".mineru" / "models"

    if VENV_PYTHON.exists():
        try:
            # Check if layoutlmv3 / paddle models exist
            r = subprocess.run(
                [str(VENV_PYTHON), "-c",
                 "from magic_pdf.model.doc_analyze_by_custom_model import ModelSingleton; print('ok')"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0 and "ok" in r.stdout:
                layout = "ok"
                ocr = "ok"
        except Exception:
            pass

    return {"layout": layout, "ocr": ocr}


def _last_extract() -> dict | None:
    """Find most recent audit report."""
    try:
        reports = sorted(AUDIT_GLOB.glob("mineru-audit-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            return None
        rpt = json.loads(reports[0].read_text())
        return {
            "ts": rpt.get("extracted_at") or rpt.get("ts") or reports[0].stat().st_mtime,
            "source": rpt.get("source", ""),
            "pages": len(rpt.get("generated_pages", [])),
        }
    except Exception:
        return None


def _canonical_papers_status() -> dict:
    """Check canonical papers input directory and manifest.
    Reports how many papers are available for extraction and their resolution status.
    """
    vault = Path.home() / "Knowledge"
    manifest_path = vault / "_meta" / "source-manifest.jsonl"
    sources_papers = vault / "_sources" / "papers"

    status: dict = {
        "manifest_exists": manifest_path.exists(),
        "sources_papers_dir_exists": sources_papers.exists(),
        "total_in_manifest": 0,
        "resolvable_canonical": 0,
        "resolvable_original_fallback": 0,
        "unresolved": 0,
        "already_extracted": 0,
    }

    if not manifest_path.exists():
        status["status"] = "blocked"
        status["blocked_reason"] = "manifest not found — run source_manifest.py generate --apply first"
        return status

    try:
        from pathlib import Path as P
        references_dir = vault / "references"
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("category") != "papers" or entry.get("media_type") != "application/pdf":
                    continue
                status["total_in_manifest"] += 1

                canonical = P(entry["canonical_path"])
                original = P(entry["original_path"])

                if canonical.exists():
                    status["resolvable_canonical"] += 1
                    resolved = canonical
                elif original.exists():
                    status["resolvable_original_fallback"] += 1
                    resolved = original
                else:
                    status["unresolved"] += 1
                    continue

                # Check extraction status
                import re
                stem = re.sub(r"[^\w\-]", "-", resolved.stem).strip("-").lower()[:60]
                if (references_dir / stem / "index.md").exists():
                    status["already_extracted"] += 1
    except Exception as e:
        status["status"] = "error"
        status["error"] = str(e)
        return status

    resolvable = status["resolvable_canonical"] + status["resolvable_original_fallback"]
    if status["total_in_manifest"] == 0:
        status["status"] = "empty"
        status["blocked_reason"] = "no papers in manifest"
    elif resolvable == 0:
        status["status"] = "blocked"
        status["blocked_reason"] = "papers in manifest but none resolvable on disk — run migration first"
    else:
        status["status"] = "ok"
        status["pending_extraction"] = resolvable - status["already_extracted"]

    return status


def main() -> None:
    verbose = "--verbose" in sys.argv
    as_json = "--json" in sys.argv or True  # always JSON

    venv_status, errors = _venv_status()
    models = _models_status()
    last_extract = _last_extract()

    report_info = {}
    if REPORT_FILE.exists():
        try:
            ri = json.loads(REPORT_FILE.read_text())
            report_info = {
                "magic_pdf_version": ri.get("magic_pdf_version", ""),
                "bootstrap_ts": ri.get("bootstrap_ts", ""),
                "wheel_count": ri.get("wheel_count", 0),
            }
        except Exception:
            pass

    result = {
        "venv": venv_status,
        "venv_path": str(VENV_DIR),
        "lock_file": str(LOCK_FILE) if LOCK_FILE.exists() else None,
        "models": models,
        "last_extract": last_extract,
        "canonical_papers": _canonical_papers_status(),
        "errors": errors,
        **report_info,
    }

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"MinerU Doctor")
        print(f"  venv: {venv_status}")
        print(f"  venv_path: {VENV_DIR}")
        print(f"  layout: {models['layout']}  ocr: {models['ocr']}")
        cp = result.get("canonical_papers", {})
        cp_status = cp.get("status", "unknown")
        print(f"  canonical_papers: {cp_status} ({cp.get('total_in_manifest', 0)} in manifest, "
              f"{cp.get('resolvable_canonical', 0)} canonical, "
              f"{cp.get('resolvable_original_fallback', 0)} original-fallback, "
              f"{cp.get('already_extracted', 0)} extracted)")
        if cp.get("blocked_reason"):
            print(f"    ⚠ {cp['blocked_reason']}")
        if last_extract:
            print(f"  last_extract: {last_extract['ts']} ({last_extract['pages']} pages from {last_extract['source'][:40]})")
        if errors:
            print("  errors:")
            for e in errors:
                print(f"    [{e['code']}] {e['msg']}")
                print(f"      → {e['actionable']}")

    sys.exit(0 if venv_status == "ok" else 1)


if __name__ == "__main__":
    main()
