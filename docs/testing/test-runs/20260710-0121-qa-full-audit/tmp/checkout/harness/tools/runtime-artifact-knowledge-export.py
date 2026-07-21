#!/usr/bin/env python3
"""Export Solar Harness runtime artifacts into the raw knowledge vault.

This complements accepted-artifact-export.py. It covers multi-task DAG outputs
and monitor reports that may not have classic passed status.json records.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS = HOME / ".solar" / "harness"
SPRINTS = HARNESS / "sprints"
REPORTS = HARNESS / "monitor-reports"
VAULT = HOME / "Knowledge"
OUT_DIR = VAULT / "_raw" / "solar-harness" / "runtime-artifacts"
MANIFEST = VAULT / "_raw" / "solar-harness" / ".manifest" / "runtime-artifacts.json"

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9._-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.I),
    re.compile(r"(ANTHROPIC_AUTH_TOKEN|ZHIPU_AUTH_TOKEN|DEEPSEEK_API_KEY|OPENAI_API_KEY|GEMINI_API_KEY)\s*=\s*\\S+", re.I),
    re.compile(r"(?i)(api[_-]?key|auth[_-]?token|access[_-]?token|secret[_-]?key)([\"'\\s:=]+)([^\\s\"']+)"),
]


def utc(ts: float | None = None) -> str:
    if ts is None:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def redact(text: str) -> str:
    out = text
    for pat in SECRET_PATTERNS:
        if pat.pattern.startswith("(?i)(api"):
            out = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}REDACTED", out)
        else:
            out = pat.sub("REDACTED", out)
    return out


def sprint_id_for(path: Path) -> str:
    m = re.search(r"(sprint-[0-9]{8}[^./ ]+|epic-[0-9]{8}[^./ ]+)", path.name)
    if m:
        return m.group(1)
    return "N/A"


def kind_for(path: Path) -> str:
    n = path.name
    if n.endswith(".prd.md"):
        return "prd"
    if n.endswith(".contract.md"):
        return "contract"
    if n.endswith(".task_graph.json"):
        return "task_graph"
    if re.search(r"\\.N\\d+-handoff\\.md$", n) or n.endswith(".handoff.md"):
        return "handoff"
    if "monitor-reports" in str(path) and n.endswith(".json"):
        return "json_report"
    if "monitor-reports" in str(path):
        return "monitor_report"
    return "other"


def iter_sources(since: str | None = None) -> list[Path]:
    pats = ["*.prd.md", "*.contract.md", "*.task_graph.json", "*.N*-handoff.md", "*.handoff.md"]
    paths: list[Path] = []
    for pat in pats:
        paths.extend(SPRINTS.glob(pat))
    if REPORTS.exists():
        paths.extend(p for p in REPORTS.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".json"})
    if since:
        paths = [p for p in paths if p.name >= since or utc(p.stat().st_mtime)[:10] >= since]
    return sorted(set(paths), key=lambda p: str(p))


def slug(path: Path) -> str:
    base = path.name
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-")
    digest = sha256_file(path)[:12]
    return f"{base}.{digest}.md"


def render_export(path: Path) -> tuple[str, dict[str, Any]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    redacted = redact(raw)
    source_hash = sha256_file(path)
    sid = sprint_id_for(path)
    kind = kind_for(path)
    meta = {
        "source": "solar-harness",
        "artifact_type": "runtime_artifact_knowledge",
        "source_path": str(path),
        "source_sha256": source_hash,
        "source_mtime": utc(path.stat().st_mtime),
        "sprint_id": sid,
        "artifact_kind": kind,
        "redacted": True,
        "visibility": "internal",
        "exported_at": utc(),
    }
    front = "\n".join([
        "---",
        "source: solar-harness",
        "artifact_type: runtime_artifact_knowledge",
        f"source_path: {str(path)}",
        f"source_sha256: {source_hash}",
        f"source_mtime: {meta['source_mtime']}",
        f"sprint_id: {sid}",
        f"artifact_kind: {kind}",
        "redacted: true",
        "visibility: internal",
        "---",
        "",
    ])
    body = (
        front
        + f"# Runtime Artifact: {path.name}\n\n"
        + f"- source_path: `{path}`\n"
        + f"- artifact_kind: `{kind}`\n"
        + f"- sprint_id: `{sid}`\n\n"
        + "## Content\n\n"
        + "```text\n"
        + redacted
        + "\n```\n"
    )
    meta["output_sha256"] = sha256_text(body)
    return body, meta


def load_manifest() -> dict[str, Any]:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "updated_at": None, "entries": {}}


def save_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest["updated_at"] = utc()
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export(paths: list[Path], dry_run: bool = False) -> dict[str, Any]:
    manifest = load_manifest()
    entries = manifest.setdefault("entries", {})
    exported = []
    skipped = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in paths:
        source_hash = sha256_file(path)
        key = str(path)
        existing = entries.get(key)
        if existing and existing.get("source_sha256") == source_hash and Path(existing.get("output_path", "")).exists():
            skipped.append({"source_path": key, "reason": "unchanged"})
            continue
        body, meta = render_export(path)
        output = OUT_DIR / slug(path)
        meta["output_path"] = str(output)
        if not dry_run:
            output.write_text(body, encoding="utf-8")
            entries[key] = meta
        exported.append({"source_path": key, "output_path": str(output), "kind": meta["artifact_kind"]})
    if not dry_run:
        save_manifest(manifest)
    return {
        "ok": True,
        "source_count": len(paths),
        "exported_count": len(exported),
        "skipped_count": len(skipped),
        "manifest": str(MANIFEST),
        "output_dir": str(OUT_DIR),
        "exported_sample": exported[:20],
        "skipped_sample": skipped[:20],
    }


def audit(paths: list[Path]) -> dict[str, Any]:
    manifest = load_manifest()
    entries = manifest.get("entries", {})
    missing = []
    for p in paths:
        e = entries.get(str(p))
        if not e or e.get("source_sha256") != sha256_file(p) or not Path(e.get("output_path", "")).exists():
            missing.append(str(p))
    return {
        "ok": True,
        "source_count": len(paths),
        "manifest_entries": len(entries),
        "missing_count": len(missing),
        "missing_sample": missing[:80],
        "manifest": str(MANIFEST),
        "output_dir": str(OUT_DIR),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["audit", "export"])
    ap.add_argument("--since", default=None, help="YYYY-MM-DD filter")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    paths = iter_sources(args.since)
    if args.limit:
        paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[: args.limit]
    result = audit(paths) if args.command == "audit" else export(paths, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
