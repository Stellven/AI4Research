#!/usr/bin/env python3
from __future__ import annotations
"""
Solar Harness HTTP Status Server — port 8765
Sprint: sprint-20260507-symphony3 S4-S5

Endpoints:
  GET /status         → JSON {current_sprint, panes, recent_events, kpi}
  GET /               → HTML dashboard (5s auto-refresh, no external deps)
  GET /events         → JSON array, query params: sprint_id, limit
  GET /mermaid        → HTML Mermaid .mmd browser and renderer
  GET /mermaid/view   → HTML render for one .mmd file, query param: file
  GET /mermaid/raw    → raw .mmd source, query param: file
  GET /integrations        → JSON external open-source integration health
  GET /integrations-view   → HTML human-readable integrations health page
  GET /healthz        → "ok"

Startup: solar-harness status-server start  (writes pidfile, nohup)
         solar-harness status-server stop|restart|status

Binds to 127.0.0.1:8765 only. No auth, no TLS (internal use).
Port fallback: 8765-8775 if primary is occupied.
"""

import json
import os
import sqlite3
import subprocess
import sys
import re
import html
import hashlib
import fcntl
import importlib.util
import time
import datetime
import urllib.parse
from collections import deque
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

# ── Paths ──
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
SPRINTS_DIR = HARNESS_DIR / "sprints"
REPORTS_DIR = HARNESS_DIR / "reports"
SESSIONS_DIR = HARNESS_DIR / "sessions"
EVENTS_DIR = HARNESS_DIR / "events"
ALL_EVENTS = EVENTS_DIR / "all.jsonl"
COORD_STATE = HARNESS_DIR / ".coordinator-state"
PANE_ASSIGNMENTS = HARNESS_DIR / ".pane-assignments"
PANE_ASSIGNMENTS_JSON = HARNESS_DIR / ".pane-assignments.json"
MERMAID_DIST = HARNESS_DIR / "vendor" / "mermaid-viewer" / "node_modules" / "mermaid" / "dist"
INTEGRATIONS_HEALTH = HARNESS_DIR / "lib" / "external-integrations-health.py"
KNOWLEDGE_PROBE_HEALTH = HARNESS_DIR / "state" / "knowledge-probe-health.json"
KNOWLEDGE_DIR = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Knowledge")))
AI_INFLUENCE_RAW_DIR = Path(os.environ.get("AI_INFLUENCE_RAW_DIR", str(KNOWLEDGE_DIR / "_raw" / "ai-influence-daily-digest")))
YOUTUBE_DIGEST_CONFIG = HARNESS_DIR / "config" / "youtube-influence-digest.yaml"
AI_INFLUENCE_ACCOUNTS = HARNESS_DIR / "ai-influence-digest" / "references" / "accounts_extended.txt"
GITHUB_TRENDS_CONFIG = HARNESS_DIR / "config" / "github-trends.yaml"
GITHUB_TRENDS_DB = Path(os.environ.get("GITHUB_TRENDS_DB", str(HARNESS_DIR / "state" / "github-trends" / "github-trends.sqlite")))
TECH_HOTSPOT_CONFIG = HARNESS_DIR / "config" / "tech-hotspot-radar.yaml"
AI_INFLUENCE_MAIL_CONFIG = HARNESS_DIR / "state" / "ai-influence-mail-config.json"
ACCEPTED_ASSETS_DIR = KNOWLEDGE_DIR / "_raw" / "solar-harness" / "accepted"
ACCEPTED_ASSETS_MANIFEST = KNOWLEDGE_DIR / "_raw" / "solar-harness" / ".manifest" / "accepted-artifacts.json"
MODEL_DOCTOR_HEALTH = HARNESS_DIR / "state" / "model-registry-doctor-health.json"
SKILLS_CERTIFICATION = HARNESS_DIR / "state" / "skills-certification.json"
SKILLS_INVENTORY = HARNESS_DIR / "state" / "skills-inventory.json"
CAPABILITY_ACTIVATION_PROOF = HARNESS_DIR / "reports" / "capability-activation-proof-latest.json"
FINAL_CONTRACT_SUMMARY_DOC = HARNESS_DIR / "docs" / "pane-as-physical-operator-final-contract-summary.md"
FINAL_CONTRACT_SUMMARY_SPRINT_ARTIFACT = HARNESS_DIR / "sprints" / "sprint-20260523-pane-as-physical-operator-final-contract-summary.md"
META_HARNESS_DIR = Path(os.environ.get("SOLAR_META_HARNESS_DIR", str(Path.home() / ".solar" / "meta-harness")))
META_HARNESS_TOOL = Path(os.environ.get("SOLAR_META_HARNESS_TOOL", str(Path.home() / ".claude" / "core" / "solar-farm" / "meta-harness.ts")))
META_HARNESS_SKILL = Path(os.environ.get("SOLAR_META_HARNESS_SKILL", str(Path.home() / ".claude" / "skills" / "meta-harness" / "SKILL.md")))
MMD_ALLOWED_ROOTS = [
    HARNESS_DIR,
    Path.home() / "Knowledge",
]
OPEN_ALLOWED_ROOTS = [
    HARNESS_DIR,
    Path.home() / "Knowledge",
]

BIND_HOST = "127.0.0.1"
PORT_RANGE = range(8765, 8776)


_SYNTHETIC_SID_PREFIXES = ("test-hooks-", "test-sid-", "sprint-race-test-", "sprint-test-smoke-", "sprint-test-workspace-", "test-verify-")
_MODEL_EVENT_TYPES = {
    "model_call_requested",
    "model_call_succeeded",
    "model_call_failed",
    "model_session_started",
    "model_session_ended",
}
_MODEL_CALL_CACHE = {}
_MODEL_CALL_CACHE_TTL_SECONDS = 8.0
_MODEL_CALL_SESSION_FILE_LIMIT = 8
_MODEL_CALL_FILE_TAIL_LINES = 80
_MODEL_CALL_SCAN_BUDGET_SECONDS = 0.025
_RUNTIME_INTERFACES_CACHE = {}
_RUNTIME_INTERFACES_CACHE_TTL_SECONDS = 20.0
_RUNTIME_INTERFACES_TIMEOUT_SECONDS = 1.0
_ACTIVE_SPRINT_STATUSES = {
    "drafting",
    "queued",
    "active",
    "planning",
    "approved",
    "reviewing",
    "ready_for_review",
    "needs_human_review",
    "failed_review",
}


def _is_synthetic_event(obj: dict) -> bool:
    sid = obj.get("sprint_id", "")
    return any(sid.startswith(p) for p in _SYNTHETIC_SID_PREFIXES)


def _read_jsonl(path: Path, limit: int = 50, sprint_id: str = "", filter_synthetic: bool = False) -> list:
    """Read last `limit` lines from a JSONL file, optionally filtered by sprint_id."""
    if not path.exists():
        return []
    lines = []
    try:
        with open(path) as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if sprint_id and obj.get("sprint_id") != sprint_id:
                    continue
                if filter_synthetic and _is_synthetic_event(obj):
                    continue
                lines.append(obj)
    except OSError:
        return []
    return lines[-limit:]


def _runtime_events_path(sprint_id: str) -> Path:
    """Prefer session-log v2 events, fall back to legacy sprint events."""
    session_path = SESSIONS_DIR / sprint_id / "events.jsonl"
    if session_path.exists():
        return session_path
    return SPRINTS_DIR / f"{sprint_id}.events.jsonl"


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        return str(path)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _allowed_mmd_path(path: Path) -> bool:
    if path.suffix.lower() != ".mmd":
        return False
    return any(_is_within(path, root) for root in MMD_ALLOWED_ROOTS)


def _allowed_open_path(path: Path) -> bool:
    return any(_is_within(path, root) for root in OPEN_ALLOWED_ROOTS)


def _resolve_open_file(raw: str):
    raw = urllib.parse.unquote(raw or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = HARNESS_DIR / candidate
    try:
        candidate = candidate.resolve()
    except OSError:
        return None
    if candidate.exists() and candidate.is_file() and _allowed_open_path(candidate):
        return candidate
    return None


def _resolve_mmd_file(raw: str):
    """Resolve a .mmd file name/path inside allowed local roots."""
    raw = urllib.parse.unquote(raw or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        # Prefer direct harness-relative paths, then fall back to basename search.
        direct = HARNESS_DIR / candidate
        if direct.exists():
            candidate = direct
        else:
            matches = [item["path"] for item in _list_mmd_files(limit=500) if item["name"] == raw or item["rel"] == raw]
            if matches:
                candidate = Path(matches[0])
    try:
        candidate = candidate.resolve()
    except OSError:
        return None
    if candidate.exists() and candidate.is_file() and _allowed_mmd_path(candidate):
        return candidate
    return None


def _list_mmd_files(limit: int = 200) -> list[dict]:
    files = []
    skip_parts = {"node_modules", ".git", "venvs", "vendor"}
    for root in MMD_ALLOWED_ROOTS:
        if not root.exists():
            continue
        try:
            iterator = root.rglob("*.mmd")
            for path in iterator:
                if any(part in skip_parts for part in path.parts):
                    continue
                try:
                    st = path.stat()
                    resolved = path.resolve()
                except OSError:
                    continue
                files.append(
                    {
                        "name": path.name,
                        "path": str(resolved),
                        "rel": _safe_rel(resolved, root),
                        "root": str(root),
                        "mtime": st.st_mtime,
                        "size": st.st_size,
                    }
                )
        except OSError:
            continue
    files.sort(key=lambda item: item["mtime"], reverse=True)
    return files[:limit]


def _asset_path(raw: str):
    rel = urllib.parse.unquote(raw or "").lstrip("/")
    if not rel:
        return None
    path = (MERMAID_DIST / rel).resolve()
    if not _is_within(path, MERMAID_DIST):
        return None
    if path.exists() and path.is_file():
        return path
    return None


def _read_text_prefix(path: Path, limit_bytes: int = 8192) -> str:
    try:
        with path.open("rb") as fh:
            return fh.read(limit_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _frontmatter_value(text: str, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(text or "")
    if not match:
        return ""
    return match.group(1).strip().strip('"')


def _first_heading(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _status_for_asset_sid(sid: str) -> dict:
    direct = SPRINTS_DIR / f"{sid}.status.json"
    candidates = [direct] if direct.exists() else sorted(SPRINTS_DIR.glob(f"**/{sid}.status.json"))
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_status_path"] = str(path)
                return data
        except Exception:
            continue
    return {}


def _artifact_asset_link(label: str, path: Path | None) -> dict:
    exists = bool(path and path.exists() and path.is_file() and _allowed_open_path(path))
    return {
        "label": label,
        "path": str(path) if path else "",
        "exists": exists,
        "open_url": ("/file/open?path=" + urllib.parse.quote(str(path))) if exists else "",
        "view_url": ("/file/view?path=" + urllib.parse.quote(str(path))) if exists else "",
        "size": path.stat().st_size if exists else 0,
        "mtime": path.stat().st_mtime if exists else 0,
    }


def _asset_package_from_accepted(path: Path, manifest_entry: dict | None = None) -> dict:
    sid = path.name.removesuffix(".accepted.md")
    prefix = _read_text_prefix(path)
    status_data = _status_for_asset_sid(sid)
    artifacts = status_data.get("artifacts") if isinstance(status_data.get("artifacts"), dict) else {}
    title = (
        _frontmatter_value(prefix, "title")
        or status_data.get("title")
        or _first_heading(prefix).removeprefix("Accepted Sprint Knowledge:").strip()
        or sid
    )
    accepted_at = _frontmatter_value(prefix, "accepted_at") or status_data.get("updated_at") or ""
    exported_at = _frontmatter_value(prefix, "exported_at") or (manifest_entry or {}).get("exported_at") or status_data.get("knowledge_exported_at") or ""
    dispatch_rel = (manifest_entry or {}).get("ingest_dispatch") or ""
    dispatch_path = KNOWLEDGE_DIR / dispatch_rel if dispatch_rel else Path(str(status_data.get("knowledge_ingest_dispatch") or ""))
    if not dispatch_path.is_absolute():
        dispatch_path = KNOWLEDGE_DIR / dispatch_path

    sprint_artifacts = []
    for label, rel_or_suffix in [
        ("contract", ".contract.md"),
        ("prd", ".prd.md"),
        ("prd_html", artifacts.get("prd_html") or ".prd.html"),
        ("design", ".design.md"),
        ("design_html", artifacts.get("design_html") or ".design.html"),
        ("plan", ".plan.md"),
        ("planning_html", artifacts.get("planning_html") or ".planning.html"),
        ("task_graph", ".task_graph.json"),
        ("handoff", ".handoff.md"),
        ("eval", ".eval.md"),
    ]:
        if isinstance(rel_or_suffix, str) and rel_or_suffix.startswith("sprints/"):
            art_path = HARNESS_DIR / rel_or_suffix
        else:
            art_path = SPRINTS_DIR / f"{sid}{rel_or_suffix}"
        sprint_artifacts.append(_artifact_asset_link(label, art_path))

    st = path.stat()
    present_artifacts = [item["label"] for item in sprint_artifacts if item["exists"]]
    return {
        "sid": sid,
        "title": title,
        "status": status_data.get("status") or _frontmatter_value(prefix, "status") or "accepted",
        "phase": status_data.get("phase") or "",
        "accepted_at": accepted_at,
        "exported_at": exported_at,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "accepted_md": _artifact_asset_link("accepted_md", path),
        "dispatch": _artifact_asset_link("ingest_dispatch", dispatch_path),
        "sprint_artifacts": sprint_artifacts,
        "artifact_count": len(present_artifacts),
        "artifact_labels": present_artifacts,
        "has_html": any(label in present_artifacts for label in ("prd_html", "design_html", "planning_html")),
        "knowledge_path": str(path),
        "source_hash": (manifest_entry or {}).get("source_hash", ""),
    }


def _asset_packages_payload(limit: int = 80) -> dict:
    manifest = {}
    if ACCEPTED_ASSETS_MANIFEST.exists():
        try:
            manifest = json.loads(ACCEPTED_ASSETS_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    items = []
    try:
        paths = sorted(ACCEPTED_ASSETS_DIR.glob("*.accepted.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        paths = []
    for path in paths[:limit]:
        sid = path.name.removesuffix(".accepted.md")
        items.append(_asset_package_from_accepted(path, manifest.get(sid) if isinstance(manifest.get(sid), dict) else {}))
    html_count = sum(1 for item in items if item.get("has_html"))
    return {
        "ok": ACCEPTED_ASSETS_DIR.exists(),
        "status": "ok" if ACCEPTED_ASSETS_DIR.exists() else "warn",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "vault": str(KNOWLEDGE_DIR),
        "accepted_dir": str(ACCEPTED_ASSETS_DIR),
        "manifest": str(ACCEPTED_ASSETS_MANIFEST),
        "count": len(items),
        "html_asset_packages": html_count,
        "items": items,
    }


def _assets_view_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solar Asset Packages</title>
</head>
<body>
<script>location.replace('/#assets');</script>
<p>Open <a href="/#assets">Solar asset packages</a>.</p>
</body>
</html>"""


def _ai_influence_artifact_link(label: str, path: Path | None) -> dict:
    exists = bool(path and path.exists() and path.is_file() and _allowed_open_path(path))
    return {
        "label": label,
        "path": str(path) if path else "",
        "exists": exists,
        "view_url": ("/ai-influence/report?path=" + urllib.parse.quote(str(path))) if exists else "",
        "file_view_url": ("/file/view?path=" + urllib.parse.quote(str(path))) if exists else "",
        "size": path.stat().st_size if exists else 0,
        "mtime": path.stat().st_mtime if exists else 0,
    }


def _ai_influence_report_id(kind: str, report_dir: Path) -> str:
    digest = hashlib.sha256(f"{kind}::{report_dir.resolve()}".encode("utf-8")).hexdigest()[:16]
    return f"air-{digest}"


def _ai_influence_artifact_view_url(report_id: str, artifact_label: str) -> str:
    return "/ai-influence/report?" + urllib.parse.urlencode({"id": report_id, "artifact": artifact_label})


def _ai_influence_transcript_url(report_id: str, video: dict) -> str:
    query = {
        "id": report_id,
        "video_ref": str(video.get("video_ref") or ""),
        "video_id": str(video.get("video_id") or ""),
    }
    return "/ai-influence/transcript?" + urllib.parse.urlencode(query)


def _ai_influence_public_artifact(label: str, path: Path | None, report_id: str) -> dict:
    artifact = _ai_influence_artifact_link(label, path)
    public = {
        "label": artifact["label"],
        "exists": artifact["exists"],
        "size": artifact["size"],
        "mtime": artifact["mtime"],
        "view_url": _ai_influence_artifact_view_url(report_id, label) if artifact["exists"] else "",
    }
    if artifact["exists"]:
        public["artifact"] = label
    return public


def _ai_influence_date_from_path(path: Path) -> str:
    for part in reversed(path.parts):
        if re.match(r"^\d{4}-\d{2}-\d{2}$", part):
            return part
    return ""


def _parse_ai_influence_date(value: str) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _ai_influence_period_cutoff(period: str) -> tuple[str, datetime.date | None]:
    normalized = str(period or "30d").strip().lower()
    today = datetime.datetime.now(datetime.timezone.utc).date()
    mapping = {
        "7d": today - datetime.timedelta(days=7),
        "30d": today - datetime.timedelta(days=30),
        "90d": today - datetime.timedelta(days=90),
        "all": None,
    }
    if normalized not in mapping:
        normalized = "30d"
    return normalized, mapping[normalized]


def _tech_hotspot_raw_dir() -> Path:
    cfg = _read_yaml_file(TECH_HOTSPOT_CONFIG)
    raw_dir = ((cfg.get("output") or {}).get("raw_dir") or str(KNOWLEDGE_DIR / "_raw" / "tech-hotspot-radar"))
    return Path(str(raw_dir)).expanduser()


def _default_mail_to() -> str:
    return (
        os.environ.get("AI_INFLUENCE_MAIL_TO")
        or os.environ.get("MAIL_TO")
        or os.environ.get("GMAIL_TO")
        or os.environ.get("GMAIL_USER")
        or os.environ.get("AI_INFLUENCE_GMAIL_USER")
        or ""
    )


def _default_mail_from() -> str:
    return (
        os.environ.get("GMAIL_USER")
        or os.environ.get("AI_INFLUENCE_GMAIL_USER")
        or ""
    )


def _ai_influence_mail_config_payload() -> dict:
    saved = _read_json_file(AI_INFLUENCE_MAIL_CONFIG)
    to_value = str(saved.get("to") or _default_mail_to()).strip()
    return {
        "ok": True,
        "status": "ok",
        "path": str(AI_INFLUENCE_MAIL_CONFIG),
        "to": to_value,
        "from": str(saved.get("from") or _default_mail_from()).strip(),
        "updated_at": str(saved.get("updated_at") or ""),
    }


def _save_ai_influence_mail_config(data: dict) -> dict:
    to_value = str(data.get("to") or "").strip()
    if not to_value:
        return {"ok": False, "status": "error", "error": "missing_to"}
    payload = {
        "to": to_value,
        "from": _default_mail_from(),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    AI_INFLUENCE_MAIL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    AI_INFLUENCE_MAIL_CONFIG.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "status": "ok", "config": payload}


@contextmanager
def _temporary_environ(overrides: dict[str, str]):
    backup = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_tech_hotspot_module():
    script_path = HARNESS_DIR / "scripts" / "tech_hotspot_radar.py"
    if not script_path.exists():
        raise FileNotFoundError(f"tech_hotspot_radar.py missing: {script_path}")
    spec = importlib.util.spec_from_file_location("solar_status_server_tech_hotspot_radar", str(script_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load tech_hotspot_radar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ai_influence_collect_attachments(report_dir: Path) -> list[Path]:
    attachments: list[Path] = []
    for path in [
        report_dir / "transcripts.txt",
        report_dir / "transcripts-cleaned.txt",
        report_dir / "youtube-transcripts.txt",
        report_dir / "youtube-transcripts-cleaned.txt",
    ]:
        if path.exists() and path.is_file():
            attachments.append(path)
    for pattern in ("youtube-transcripts*.txt", "phase-transcripts*.txt"):
        for path in sorted(report_dir.glob(pattern)):
            if path.exists() and path.is_file():
                attachments.append(path)
    unique: list[Path] = []
    seen: set[str] = set()
    for item in attachments:
        raw = str(item)
        if raw in seen:
            continue
        seen.add(raw)
        unique.append(item)
    return unique


def _unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _ai_influence_resource_links(report_dir: Path, artifact_names: list[str], report_id: str) -> list[dict]:
    links: list[dict] = []
    for name in artifact_names:
        path = report_dir / name
        if not path.exists() or not path.is_file():
            continue
        links.append({
            "label": name,
            "artifact": name,
            "url": _ai_influence_artifact_view_url(report_id, name),
        })
    return links


def _mail_status_badge(mail_result: dict | None) -> str:
    if not isinstance(mail_result, dict):
        return "未发送"
    status = str(mail_result.get("status") or "N/A")
    return {"sent": "已发送", "skipped": "未发送", "warn": "告警", "failed": "失败"}.get(status, status)


def _build_report_subject(item: dict) -> str:
    title = str(item.get("title") or "AI Influence 报告").strip()
    date_str = str(item.get("date") or "").strip()
    module_label = str(item.get("module_label") or "AI Influence").strip()
    suffix = f" — {date_str}" if date_str and date_str not in title else ""
    return f"{module_label}：{title}{suffix}"


def _planned_report_item(report_dir: Path) -> dict:
    report_id = _ai_influence_report_id("planned_report", report_dir)
    result_path = report_dir / "report-result.json"
    evidence_path = report_dir / "evidence-pack.json"
    html_path = report_dir / "report.html"
    md_path = report_dir / "report.md"
    mail_path = report_dir / "mail-result.json"
    result = _read_json_file(result_path)
    evidence = _read_json_file(evidence_path)
    videos = evidence.get("videos") if isinstance(evidence.get("videos"), list) else []
    channels = _unique_preserve([str(video.get("channel") or "") for video in videos if isinstance(video, dict)])
    tags = _unique_preserve([str(tag) for video in videos if isinstance(video, dict) for tag in (video.get("topic_tags") or [])])
    return {
        "kind": "planned_report",
        "id": report_id,
        "module_key": "planned",
        "module_label": "专题洞察",
        "module_title": "AI Influence 专题报告",
        "date": _ai_influence_date_from_path(report_dir),
        "title": str(result.get("headline") or report_dir.name).strip(),
        "subtitle": str(result.get("subheadline") or "").strip(),
        "status": "ok" if html_path.exists() else "warn",
        "primary": _ai_influence_public_artifact("report_html", html_path, report_id),
        "artifacts": [
            _ai_influence_public_artifact("report_html", html_path, report_id),
            _ai_influence_public_artifact("report_md", md_path, report_id),
            _ai_influence_public_artifact("report_result_json", result_path, report_id),
            _ai_influence_public_artifact("evidence_pack_json", evidence_path, report_id),
        ],
        "mail": _read_json_file(mail_path) if mail_path.exists() else {"status": "skipped"},
        "metrics": {
            "素材": len(videos),
            "模型": str(result.get("_model") or result.get("model") or "N/A"),
            "推理": str(result.get("_reasoning_effort") or result.get("reasoning_effort") or "N/A"),
        },
        "filters": {
            "themes": tags,
            "technologies": tags,
            "channels": channels,
        },
        "resources": _ai_influence_resource_links(report_dir, [
            "transcripts.txt",
            "transcripts-cleaned.txt",
            "evidence-pack.json",
            "report.md",
            "writer-prompt.md",
        ], report_id),
        "_report_dir": str(report_dir),
        "mtime": max((p.stat().st_mtime for p in [html_path, md_path, result_path, evidence_path] if p.exists()), default=report_dir.stat().st_mtime),
    }


def _digest_report_item(run_dir: Path) -> dict:
    report_id = _ai_influence_report_id("daily_digest", run_dir)
    digest_json_path = run_dir / "digest.json"
    digest_html_path = run_dir / "digest.html"
    digest_md_path = run_dir / "digest.md"
    preview_path = run_dir / "digest.preview.html"
    data = _read_json_file(digest_json_path)
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else data
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    trends = analysis.get("trend_analysis") if isinstance(analysis, dict) else {}
    core_trends = trends.get("core_trends") if isinstance(trends, dict) else []
    items = analysis.get("items") if isinstance(analysis, dict) else []
    themes = _unique_preserve([str(item.get("theme") or "") for item in core_trends if isinstance(item, dict)])
    technologies = _unique_preserve([str(tag) for item in core_trends if isinstance(item, dict) for tag in (item.get("tags") or [])])
    handles = _unique_preserve([str(item.get("handle") or "") for item in items if isinstance(item, dict)])
    html_link = _ai_influence_public_artifact("digest_html", digest_html_path, report_id)
    preview_link = _ai_influence_public_artifact("digest_preview_html", preview_path, report_id)
    primary = html_link if html_link["exists"] else preview_link
    date_str = str(data.get("date") or _ai_influence_date_from_path(run_dir) or run_dir.name)
    return {
        "kind": "daily_digest",
        "id": report_id,
        "module_key": "daily_digest",
        "module_label": "日度洞察",
        "module_title": "AI Influence Daily Digest",
        "date": date_str,
        "title": f"AI Influence Digest — {date_str}",
        "subtitle": "旧版 daily digest",
        "status": "ok" if primary.get("exists") else "warn",
        "primary": primary,
        "artifacts": [
            html_link,
            preview_link,
            _ai_influence_public_artifact("digest_md", digest_md_path, report_id),
            _ai_influence_public_artifact("digest_json", digest_json_path, report_id),
        ],
        "mail": data.get("gmail", {}) if isinstance(data.get("gmail"), dict) else {"status": "skipped"},
        "metrics": {
            "条目": len(items) if isinstance(items, list) else 0,
            "趋势": len(core_trends) if isinstance(core_trends, list) else 0,
            "候选": int(stats.get("top_scored", 0) or 0),
        },
        "filters": {
            "themes": themes,
            "technologies": technologies,
            "channels": handles,
        },
        "resources": _ai_influence_resource_links(run_dir, [
            "digest.md",
            "digest.json",
            "digest.preview.html",
            "digest.email-preview.html",
            "unified-digest-result.json",
            "youtube-transcripts-2026-05-23.txt",
        ], report_id),
        "_report_dir": str(run_dir),
        "mtime": max((p.stat().st_mtime for p in [digest_json_path, digest_html_path, digest_md_path, preview_path] if p.exists()), default=run_dir.stat().st_mtime if run_dir.exists() else 0),
    }


def _unified_daily_report_item(run_dir: Path) -> dict:
    report_id = _ai_influence_report_id("unified_daily", run_dir)
    html_path = run_dir / "report.html"
    md_path = run_dir / "unified-overview.md"
    mail_path = run_dir / "mail-result.json"
    alerts_path = run_dir / "alerts.json"
    alerts = []
    if alerts_path.exists():
        try:
            payload = json.loads(alerts_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                alerts = payload
        except Exception:
            alerts = []
    technologies = _unique_preserve([str(row.get("source") or "") for row in alerts if isinstance(row, dict)])
    return {
        "kind": "unified_daily",
        "id": report_id,
        "module_key": "unified_daily",
        "module_label": "统一日报",
        "module_title": "Tech Hotspot Radar 日报",
        "date": _ai_influence_date_from_path(run_dir) or run_dir.name,
        "title": f"AI Influence 综合日报 — {_ai_influence_date_from_path(run_dir) or run_dir.name}",
        "subtitle": "YouTube / Social / GitHub 合并版",
        "status": "ok" if html_path.exists() else "warn",
        "primary": _ai_influence_public_artifact("report_html", html_path, report_id),
        "artifacts": [
            _ai_influence_public_artifact("report_html", html_path, report_id),
            _ai_influence_public_artifact("unified_overview_md", md_path, report_id),
        ],
        "mail": _read_json_file(mail_path) if mail_path.exists() else {"status": "skipped"},
        "metrics": {
            "附件": len(list(run_dir.glob("youtube-transcripts*.txt"))),
            "告警": 1 if (run_dir / "alerts.json").exists() else 0,
            "派单": 1 if (run_dir / "wiki-dispatch.md").exists() else 0,
        },
        "filters": {
            "themes": ["综合日报"],
            "technologies": technologies,
            "channels": [],
        },
        "resources": _ai_influence_resource_links(run_dir, [
            "unified-overview.md",
            "alerts.json",
            "alerts.md",
            "youtube-report.md",
            "social-report.md",
            "github-report.md",
            "youtube-transcripts-2026-05-26.txt",
            "transcripts.jsonl",
        ], report_id),
        "_report_dir": str(run_dir),
        "mtime": max((p.stat().st_mtime for p in [html_path, md_path, mail_path] if p.exists()), default=run_dir.stat().st_mtime),
    }


def _phase_report_item(run_dir: Path, phase_name: str) -> dict:
    report_id = _ai_influence_report_id("phase_report", run_dir)
    phase_json_path = run_dir / "phase-report.json"
    html_path = run_dir / "report.html"
    md_path = run_dir / "phase-report.md"
    mail_path = run_dir / "mail-result.json"
    payload = _read_json_file(phase_json_path)
    phase_label = phase_name.replace("-", " ").title()
    title = str(payload.get("headline") or f"{phase_label} — {run_dir.name}").strip()
    return {
        "kind": "phase_report",
        "id": report_id,
        "module_key": phase_name,
        "module_label": phase_label,
        "module_title": f"{phase_label} 历史洞察",
        "date": _ai_influence_date_from_path(run_dir) or run_dir.name,
        "title": title,
        "subtitle": str(payload.get("subheadline") or "").strip(),
        "status": "ok" if html_path.exists() else "warn",
        "primary": _ai_influence_public_artifact("report_html", html_path, report_id),
        "artifacts": [
            _ai_influence_public_artifact("report_html", html_path, report_id),
            _ai_influence_public_artifact("phase_report_md", md_path, report_id),
            _ai_influence_public_artifact("phase_report_json", phase_json_path, report_id),
        ],
        "mail": _read_json_file(mail_path) if mail_path.exists() else {"status": "skipped"},
        "metrics": {
            "素材": int(payload.get("_input_video_count", 0) or 0),
            "附件": len(list(run_dir.glob("youtube-transcripts*.txt"))),
            "模型": str(payload.get("_model") or "N/A"),
        },
        "filters": {
            "themes": [phase_label],
            "technologies": [phase_label],
            "channels": [],
        },
        "resources": _ai_influence_resource_links(run_dir, [
            "phase-report.md",
            "phase-report.json",
            "phase-evidence-pack.json",
            "youtube-transcripts-phase-2-2026-05-24.txt",
        ], report_id),
        "_report_dir": str(run_dir),
        "mtime": max((p.stat().st_mtime for p in [html_path, md_path, phase_json_path, mail_path] if p.exists()), default=run_dir.stat().st_mtime),
    }


def _github_trend_report_item(run_dir: Path) -> dict:
    report_id = _ai_influence_report_id("github_trend_report", run_dir)
    report_json_path = run_dir / "github-trend-report.json"
    html_path = run_dir / "github-trend-report.html"
    md_path = run_dir / "github-trend-report.md"
    pack_path = run_dir / "github-trend-pack.json"
    mail_path = run_dir / "mail-result.json"
    result = _read_json_file(report_json_path)
    pack = _read_json_file(pack_path)
    date_str = _ai_influence_date_from_path(run_dir) or run_dir.name
    card_count = len(pack.get("cards") or []) if isinstance(pack, dict) else 0
    model = str(result.get("model") or "N/A") if isinstance(result, dict) else "N/A"
    return {
        "kind": "github_trend_report",
        "id": report_id,
        "module_key": "github_trend_report",
        "module_label": "GitHub 洞察",
        "module_title": "AI Influence GitHub 开源趋势洞察",
        "date": date_str,
        "title": f"AI Influence GitHub 开源趋势洞察 — {date_str}",
        "subtitle": "基于项目情报卡、HF 论文侧信号和证据包生成的开源趋势判断",
        "status": "ok" if html_path.exists() and md_path.exists() else "warn",
        "primary": _ai_influence_public_artifact("report_html", html_path, report_id) if html_path.exists() else _ai_influence_public_artifact("report_md", md_path, report_id),
        "artifacts": [
            _ai_influence_public_artifact("report_html", html_path, report_id),
            _ai_influence_public_artifact("report_md", md_path, report_id),
            _ai_influence_public_artifact("report_result_json", report_json_path, report_id),
            _ai_influence_public_artifact("evidence_pack_json", pack_path, report_id),
        ],
        "mail": _read_json_file(mail_path) if mail_path.exists() else {"status": "skipped"},
        "metrics": {
            "项目卡": card_count,
            "模型": model,
            "watchlist": int(pack.get("repo_count") or 0) if isinstance(pack, dict) else 0,
        },
        "filters": {
            "themes": ["GitHub 洞察", "开源趋势"],
            "technologies": ["GitHub", "Repo", "Open Source"],
            "channels": [],
        },
        "resources": _ai_influence_resource_links(run_dir, [
            "github-trend-report.md",
            "github-trend-report.json",
            "github-trend-pack.json",
            "wiki-dispatch.md",
        ], report_id),
        "_report_dir": str(run_dir),
        "mtime": max((p.stat().st_mtime for p in [html_path, md_path, report_json_path, pack_path, mail_path] if p.exists()), default=run_dir.stat().st_mtime if run_dir.exists() else 0),
    }


def _ai_influence_group_summary(key: str, items: list[dict]) -> dict:
    if key == "planned":
        rows = []
        channels: set[str] = set()
        tags: set[str] = set()
        total_videos = 0
        for item in items:
            report_dir = Path(str(item.get("_report_dir") or ""))
            report_id = str(item.get("id") or "")
            evidence_path = report_dir / "evidence-pack.json"
            evidence = _read_json_file(evidence_path)
            videos = evidence.get("videos") if isinstance(evidence.get("videos"), list) else []
            total_videos += len(videos)
            for video in videos[:12]:
                channel = str(video.get("channel") or "N/A").strip()
                channels.add(channel)
                for tag in (video.get("topic_tags") or [])[:6]:
                    if str(tag).strip():
                        tags.add(str(tag).strip())
                title = str(video.get("title") or "N/A")
                transcript_url = _ai_influence_transcript_url(report_id, video)
                youtube_url = str(video.get("url") or "").strip()
                title_html = (
                    f'<a href="{html.escape(transcript_url)}" target="_blank" rel="noreferrer">{html.escape(title)}</a>'
                    + (
                        f' <a class="video-source-link" href="{html.escape(youtube_url)}" target="_blank" rel="noreferrer">YouTube</a>'
                        if youtube_url else ""
                    )
                )
                rows.append({
                    "date": item.get("date") or "N/A",
                    "channel": channel,
                    "title": title,
                    "title_html": title_html,
                    "published": str(video.get("published_at") or "N/A")[:10],
                    "tags": ", ".join(str(tag) for tag in (video.get("topic_tags") or [])[:4]) or "N/A",
                })
        return {
            "headline": f"{len(items)} 份专题报告，覆盖 {total_videos} 条视频素材、{len(channels)} 个频道。",
            "metrics": {"报告": len(items), "素材视频": total_videos, "频道": len(channels), "主题标签": len(tags)},
            "columns": ["日期", "频道", "视频标题", "发布时间", "标签"],
            "rows": rows[:24],
            "row_map": [("date", "日期"), ("channel", "频道"), ("title", "视频标题"), ("published", "发布时间"), ("tags", "标签")],
        }
    if key == "daily_digest":
        rows = []
        total_items = 0
        total_trends = 0
        handles: set[str] = set()
        for item in items:
            digest_path = Path(str(item.get("_report_dir") or "")) / "digest.json"
            digest = _read_json_file(digest_path)
            digest_items = digest.get("items") if isinstance(digest.get("items"), list) else []
            trend_items = ((digest.get("trend_analysis") or {}).get("core_trends") or []) if isinstance(digest, dict) else []
            total_items += len(digest_items)
            total_trends += len(trend_items)
            for row in digest_items[:12]:
                if not isinstance(row, dict):
                    rows.append({
                        "date": item.get("date") or "N/A",
                        "handle": "N/A",
                        "title": str(row),
                        "type": "item",
                        "summary": "N/A",
                    })
                    continue
                handle = str(row.get("handle") or "N/A")
                handles.add(handle)
                rows.append({
                    "date": item.get("date") or "N/A",
                    "handle": handle,
                    "title": str(row.get("title") or "N/A"),
                    "type": str(row.get("type") or "post"),
                    "summary": str(row.get("summary") or "N/A"),
                })
        return {
            "headline": f"{len(items)} 份日度洞察，汇总 {total_items} 条社交信号、{total_trends} 个核心趋势。",
            "metrics": {"报告": len(items), "社交信号": total_items, "核心趋势": total_trends, "账号": len(handles)},
            "columns": ["日期", "账号", "标题", "类型", "摘要"],
            "rows": rows[:24],
            "row_map": [("date", "日期"), ("handle", "账号"), ("title", "标题"), ("type", "类型"), ("summary", "摘要")],
        }
    if key == "unified_daily":
        rows = []
        total_alerts = 0
        total_transcripts = 0
        for item in items:
            run_dir = Path(str(item.get("_report_dir") or ""))
            alerts = []
            alerts_path = run_dir / "alerts.json"
            if alerts_path.exists():
                try:
                    payload = json.loads(alerts_path.read_text(encoding="utf-8"))
                    if isinstance(payload, list):
                        alerts = payload
                except Exception:
                    alerts = []
            total_alerts += len(alerts)
            total_transcripts += len(list(run_dir.glob("youtube-transcripts*.txt")))
            for row in alerts[:12]:
                rows.append({
                    "date": item.get("date") or "N/A",
                    "source": str(row.get("source") or "N/A"),
                    "rule": str(row.get("rule_name") or "N/A"),
                    "title": str(row.get("title") or "N/A"),
                    "time": str(row.get("fired_at") or "N/A").replace("T", " ")[:16],
                })
        return {
            "headline": f"{len(items)} 份统一日报，命中 {total_alerts} 条告警，带出 {total_transcripts} 份转写附件。",
            "metrics": {"日报": len(items), "告警": total_alerts, "转写附件": total_transcripts},
            "columns": ["日期", "来源", "规则", "标题", "触发时间"],
            "rows": rows[:24],
            "row_map": [("date", "日期"), ("source", "来源"), ("rule", "规则"), ("title", "标题"), ("time", "触发时间")],
        }
    rows = []
    total_inputs = 0
    for item in items:
        report_dir = Path(str(item.get("_report_dir") or ""))
        phase_path = report_dir / "phase-report.json"
        phase_json = _read_json_file(phase_path)
        total_inputs += int(phase_json.get("_input_video_count", 0) or 0)
        rows.append({
            "date": item.get("date") or "N/A",
            "module": item.get("module_label") or "N/A",
            "title": item.get("title") or "N/A",
            "videos": int(phase_json.get("_input_video_count", 0) or 0),
            "model": str(phase_json.get("_model") or "N/A"),
        })
    return {
        "headline": f"{len(items)} 份阶段洞察，累计处理 {total_inputs} 条视频输入。",
        "metrics": {"阶段报告": len(items), "视频输入": total_inputs},
        "columns": ["日期", "阶段", "标题", "素材数", "模型"],
        "rows": rows[:24],
        "row_map": [("date", "日期"), ("module", "阶段"), ("title", "标题"), ("videos", "素材数"), ("model", "模型")],
    }


def _render_ai_influence_summary_table(summary: dict) -> str:
    row_map = summary.get("row_map") or []
    rows = summary.get("rows") or []
    headers = "".join(f"<th>{html.escape(str(label))}</th>" for _, label in row_map)
    body_rows = []
    for row in rows:
        cols = []
        for key, _label in row_map:
            if isinstance(row, dict) and row.get(f"{key}_html"):
                cols.append(f"<td>{row.get(f'{key}_html')}</td>")
                continue
            value = row.get(key, "N/A") if isinstance(row, dict) else "N/A"
            cols.append(f"<td>{html.escape(str(value))}</td>")
        body_rows.append("<tr>" + "".join(cols) + "</tr>")
    if not body_rows:
        body_rows.append(f"<tr><td colspan='{max(1, len(row_map))}'>N/A</td></tr>")
    return f"<div class='summary-table-wrap'><table class='summary-table'><thead><tr>{headers}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>"


def _sanitize_ai_influence_item(item: dict) -> dict:
    public = dict(item)
    public.pop("_report_dir", None)
    public.pop("report_dir", None)
    return public


def _sanitize_ai_influence_payload(payload: dict) -> dict:
    groups = []
    for group in payload.get("groups") or []:
        group_public = dict(group)
        group_public["items"] = [_sanitize_ai_influence_item(item) for item in (group.get("items") or [])]
        groups.append(group_public)
    return {
        "ok": payload.get("ok", False),
        "status": payload.get("status", "warn"),
        "generated_at": payload.get("generated_at", ""),
        "period": payload.get("period", "30d"),
        "count": payload.get("count", 0),
        "items": [_sanitize_ai_influence_item(item) for item in (payload.get("items") or [])],
        "groups": groups,
        "module_counts": payload.get("module_counts", {}),
        "filter_options": payload.get("filter_options", {}),
        "mail_config": payload.get("mail_config", {}),
    }


def _ai_influence_payload_internal(limit: int = 80, period: str = "30d") -> dict:
    tech_hotspot_raw_dir = _tech_hotspot_raw_dir()
    items: list[dict] = []
    if AI_INFLUENCE_RAW_DIR.exists():
        for child in AI_INFLUENCE_RAW_DIR.iterdir():
            if child.is_dir() and (child / "digest.md").exists():
                items.append(_digest_report_item(child))
    planned_root = tech_hotspot_raw_dir / "ai-influence-planned"
    if planned_root.exists():
        for date_dir in sorted((p for p in planned_root.iterdir() if p.is_dir()), reverse=True):
            reports_dir = date_dir / "reports"
            if not reports_dir.exists():
                continue
            for report_dir in sorted((p for p in reports_dir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True):
                if (report_dir / "report.html").exists():
                    items.append(_planned_report_item(report_dir))
    if tech_hotspot_raw_dir.exists():
        for child in tech_hotspot_raw_dir.iterdir():
            if child.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", child.name) and (child / "report.html").exists():
                items.append(_unified_daily_report_item(child))
        for phase_dir in sorted((p for p in tech_hotspot_raw_dir.iterdir() if p.is_dir() and p.name.startswith("phase-"))):
            for child in sorted((p for p in phase_dir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True):
                if (child / "report.html").exists() and (child / "phase-report.json").exists():
                    items.append(_phase_report_item(child, phase_dir.name))
        github_report_root = tech_hotspot_raw_dir / "github-trend-report"
        if github_report_root.exists():
            for child in github_report_root.iterdir():
                if child.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", child.name) and ((child / "github-trend-report.html").exists() or (child / "github-trend-report.md").exists()):
                    items.append(_github_trend_report_item(child))
    items.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    normalized_period, cutoff = _ai_influence_period_cutoff(period)
    if cutoff is not None:
        items = [
            item for item in items
            if (_parse_ai_influence_date(str(item.get("date") or "")) or datetime.date.min) >= cutoff
        ]
    limited = items[:limit]
    groups: dict[str, dict] = {}
    for item in limited:
        key = str(item.get("module_key") or "other")
        group = groups.setdefault(key, {"key": key, "label": item.get("module_label") or key, "title": item.get("module_title") or item.get("module_label") or key, "items": []})
        group["items"].append(item)
    for key, group in groups.items():
        group["summary"] = _ai_influence_group_summary(key, group.get("items") or [])
    filter_themes = _unique_preserve([value for item in limited for value in ((item.get("filters") or {}).get("themes") or [])])
    filter_technologies = _unique_preserve([value for item in limited for value in ((item.get("filters") or {}).get("technologies") or [])])
    filter_channels = _unique_preserve([value for item in limited for value in ((item.get("filters") or {}).get("channels") or [])])
    return {
        "ok": bool(limited),
        "status": "ok" if limited else "warn",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "period": normalized_period,
        "count": len(limited),
        "items": limited,
        "groups": list(groups.values()),
        "module_counts": {group["label"]: len(group["items"]) for group in groups.values()},
        "filter_options": {
            "themes": filter_themes,
            "technologies": filter_technologies,
            "channels": filter_channels,
        },
        "mail_config": _ai_influence_mail_config_payload(),
    }


def _ai_influence_payload(limit: int = 80, period: str = "30d") -> dict:
    return _sanitize_ai_influence_payload(_ai_influence_payload_internal(limit=limit, period=period))


def _resolve_ai_influence_item(report_id: str) -> dict | None:
    token = str(report_id or "").strip()
    if not token:
        return None
    payload = _ai_influence_payload_internal(limit=500, period="all")
    for item in payload.get("items") or []:
        if str(item.get("id") or "") == token:
            return item
    return None


def _resolve_ai_influence_artifact(report_id: str, artifact_label: str) -> Path | None:
    item = _resolve_ai_influence_item(report_id)
    if not item:
        return None
    report_dir = Path(str(item.get("_report_dir") or ""))
    allowed = {
        "report_html": report_dir / "report.html",
        "report_md": report_dir / "report.md",
        "report_result_json": report_dir / "report-result.json",
        "evidence_pack_json": report_dir / "evidence-pack.json",
        "digest_html": report_dir / "digest.html",
        "digest_preview_html": report_dir / "digest.preview.html",
        "digest_md": report_dir / "digest.md",
        "digest_json": report_dir / "digest.json",
        "unified_overview_md": report_dir / "unified-overview.md",
        "phase_report_md": report_dir / "phase-report.md",
        "phase_report_json": report_dir / "phase-report.json",
    }
    if str(item.get("kind") or "") == "github_trend_report":
        allowed.update({
            "report_html": report_dir / "github-trend-report.html",
            "report_md": report_dir / "github-trend-report.md",
            "report_result_json": report_dir / "github-trend-report.json",
            "evidence_pack_json": report_dir / "github-trend-pack.json",
        })
    for resource in item.get("resources") or []:
        if not isinstance(resource, dict):
            continue
        label = str(resource.get("label") or "").strip()
        if label:
            allowed[label] = report_dir / label
    target = allowed.get(str(artifact_label or "").strip())
    if not target or not target.exists() or not target.is_file() or not _allowed_open_path(target):
        return None
    return target


def _resolve_ai_influence_mail_target(data: dict):
    report_id = str(data.get("id") or "").strip()
    if report_id:
        return _resolve_ai_influence_artifact(report_id, "report_html") or _resolve_ai_influence_artifact(report_id, "digest_html") or _resolve_ai_influence_artifact(report_id, "digest_preview_html")
    raw = urllib.parse.unquote(str(data.get("path") or "").strip())
    if not raw:
        return None
    target = _resolve_open_file(raw)
    if not target:
        return None
    if target.suffix.lower() != ".html":
        return None
    roots = [AI_INFLUENCE_RAW_DIR, _tech_hotspot_raw_dir()]
    if not any(_is_within(target, root) for root in roots if root.exists()):
        return None
    return target


def _ai_influence_send_report(data: dict) -> dict:
    target = _resolve_ai_influence_mail_target(data)
    if not target:
        return {"ok": False, "status": "error", "error": "report_not_found_or_not_allowed"}
    config = _ai_influence_mail_config_payload()
    to_value = str(data.get("to") or config.get("to") or "").strip()
    if not to_value:
        return {"ok": False, "status": "error", "error": "missing_mail_to"}
    module = _load_tech_hotspot_module()
    html_content = target.read_text(encoding="utf-8", errors="ignore")
    report_dir = target.parent
    item = {
        "title": data.get("title") or report_dir.name,
        "date": data.get("date") or _ai_influence_date_from_path(report_dir),
        "module_label": data.get("module_label") or "AI Influence",
    }
    subject = str(data.get("subject") or _build_report_subject(item))
    attachments = _ai_influence_collect_attachments(report_dir)
    from_value = str(config.get("from") or "").strip()
    if not from_value:
        # Status-server launchd does not inherit the user's shell GMAIL_USER.
        # Prefer an explicit Gmail recipient as the SMTP account so send buttons
        # work without duplicating secrets in the status UI config.
        recipients_for_account = [addr.strip() for addr in re.split(r"[,;]", to_value) if addr.strip()]
        from_value = next((addr for addr in recipients_for_account if addr.lower().endswith("@gmail.com")), "")
    env_overrides = {"AI_INFLUENCE_MAIL_TO": to_value}
    if from_value:
        env_overrides["AI_INFLUENCE_GMAIL_USER"] = from_value
        env_overrides["GMAIL_USER"] = from_value
        env_overrides["GMAIL_APP_PASSWORD_KEYCHAIN_ACCOUNT"] = from_value
    with _temporary_environ(env_overrides):
        result = module.send_html_email(html_content, subject, attachments)
    result = dict(result or {})
    result["subject"] = subject
    result["report_path"] = str(target)
    result["to"] = result.get("to") or [addr.strip() for addr in re.split(r"[,;]", to_value) if addr.strip()]
    if str(result.get("status") or "").lower() == "sent":
        (report_dir / "mail-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": str(result.get("status") or "").lower() == "sent", "status": result.get("status", "warn"), "result": result}


def _ai_influence_html(period: str = "30d") -> str:
    payload = _ai_influence_payload(limit=200, period=period)
    mail_cfg = payload.get("mail_config") if isinstance(payload.get("mail_config"), dict) else {}
    current_to = str(mail_cfg.get("to") or "")
    current_period = str(payload.get("period") or "30d")
    report_cards = []
    resource_sections = []
    for group in payload.get("groups") or []:
        summary = group.get("summary") if isinstance(group.get("summary"), dict) else {}
        summary_metrics = "".join(
            f"<span class='summary-metric'><b>{html.escape(str(value))}</b><small>{html.escape(str(key))}</small></span>"
            for key, value in (summary.get("metrics") or {}).items()
        )
        resource_rows = []
        report_rows = []
        rows = []
        for item in group.get("items") or []:
            primary = item.get("primary") if isinstance(item.get("primary"), dict) else {}
            open_url = primary.get("view_url") or ""
            module_label = str(item.get("module_label") or "N/A")
            mail_status = str(((item.get("mail") or {}).get("status")) or "unsent").strip().lower()
            mail_payload_attr = html.escape(json.dumps({
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "date": str(item.get("date") or ""),
                "module_label": module_label,
            }, ensure_ascii=False), quote=True)
            artifacts = item.get("artifacts") if isinstance(item.get("artifacts"), list) else []
            artifact_links = []
            for artifact in artifacts:
                if not isinstance(artifact, dict) or not artifact.get("exists"):
                    continue
                label = str(artifact.get("label") or "").replace("_", " ")
                view_url = str(artifact.get("file_view_url") or artifact.get("view_url") or "")
                if view_url:
                    artifact_links.append(f'<a class="btn tiny" href="{html.escape(view_url)}" target="_blank" rel="noreferrer">{html.escape(label)}</a>')
            metric_bits = []
            for key, value in (item.get("metrics") or {}).items():
                metric_bits.append(f"<span><b>{html.escape(str(value))}</b><small>{html.escape(str(key))}</small></span>")
            theme_values = (item.get("filters") or {}).get("themes") or []
            tech_values = (item.get("filters") or {}).get("technologies") or []
            channel_values = (item.get("filters") or {}).get("channels") or []
            theme_tokens = " | ".join(theme_values)
            tech_tokens = " | ".join(tech_values)
            channel_tokens = " | ".join(channel_values)
            primary_channel = str(channel_values[0] if channel_values else "未分配频道")
            report_cards.append(f"""
            <article class="report-card">
              <div class="main"
                   data-kind="{html.escape(str(item.get('kind') or 'report'))}"
                   data-date="{html.escape(str(item.get('date') or 'N/A'))}"
                   data-module="{html.escape(module_label)}"
                   data-themes="{html.escape(theme_tokens)}"
                   data-technologies="{html.escape(tech_tokens)}"
                   data-channels="{html.escape(channel_tokens)}"
                   data-primary-channel="{html.escape(primary_channel)}"
                   data-mail-status="{html.escape(mail_status)}"
                   data-title="{html.escape(str(item.get('title') or ''))}"
                   data-mail-payload="{mail_payload_attr}">
                <div class="date">{html.escape(str(item.get("date") or "N/A"))}</div>
                <h3>{html.escape(str(item.get("title") or "AI Influence 报告"))}</h3>
                <p class="meta">{html.escape(str(item.get("subtitle") or ""))}</p>
                <p class="meta">模块：{html.escape(module_label)} · 邮件：{html.escape(_mail_status_badge(item.get("mail")))}</p>
                <div class="artifact-row">{''.join(artifact_links)}</div>
              </div>
              <div class="metrics">{''.join(metric_bits) or '<span><b>N/A</b><small>指标</small></span>'}</div>
              <div class="actions">
                <a class="btn primary" href="{html.escape(open_url)}" target="_blank" rel="noreferrer">打开报告</a>
                <button class="btn accent" data-payload="{mail_payload_attr}" onclick="sendAiInfluenceReport(JSON.parse(this.dataset.payload), {{button: this}})">发送邮件</button>
                <button class="btn" onclick='showMailConfig()'>配置发送邮箱</button>
              </div>
            </article>
            """)
            resource_link_bits = []
            for resource in item.get("resources") or []:
                if not isinstance(resource, dict):
                    continue
                label = str(resource.get("label") or "resource")
                url = str(resource.get("url") or "")
                if url:
                    resource_link_bits.append(f'<a class="btn tiny" href="{html.escape(url)}" target="_blank" rel="noreferrer">{html.escape(label)}</a>')
            resource_rows.append(f"""
            <tr>
              <td>{html.escape(str(item.get("date") or "N/A"))}</td>
              <td>{html.escape(str(item.get("title") or "N/A"))}</td>
              <td>{html.escape(str(item.get("module_label") or "N/A"))}</td>
              <td>{''.join(resource_link_bits) or 'N/A'}</td>
            </tr>
            """)
        resource_sections.append(f"""
        <section class="group">
          <div class="group-head">
            <div>
              <div class="group-kicker">{html.escape(str(group.get("label") or "AI Influence"))}</div>
              <h2>{html.escape(str(group.get("title") or group.get("label") or "素材资源"))}</h2>
            </div>
            <span class="pill">{len(group.get("items") or [])} 份</span>
          </div>
          <div class="summary-card">
            <p class="summary-headline">{html.escape(str(summary.get("headline") or "N/A"))}</p>
            <div class="summary-metrics">{summary_metrics}</div>
            {_render_ai_influence_summary_table(summary)}
          </div>
          <div class="resource-table-wrap">
            <table class="resource-table">
              <thead>
                <tr><th>日期</th><th>报告</th><th>模块</th><th>素材 / 下载</th></tr>
              </thead>
              <tbody>
                {''.join(resource_rows) if resource_rows else "<tr><td colspan='4'>N/A</td></tr>"}
              </tbody>
            </table>
          </div>
        </section>
        """)
    module_pills = "".join(
        f"<span class='pill'>{html.escape(str(name))}（{int(count)} 份报告）</span>"
        for name, count in (payload.get("module_counts") or {}).items()
    )
    period_links = "".join(
        f"<a class='pill period {'active' if current_period == key else ''}' href='/ai-influence?period={key}'>{label}</a>"
        for key, label in (("7d", "近 7 天"), ("30d", "近 30 天"), ("90d", "近 90 天"), ("all", "全部"))
    )
    filter_options = payload.get("filter_options") if isinstance(payload.get("filter_options"), dict) else {}
    theme_options = "".join(f"<option value='{html.escape(value)}'>{html.escape(value)}</option>" for value in (filter_options.get("themes") or []))
    technology_options = "".join(f"<option value='{html.escape(value)}'>{html.escape(value)}</option>" for value in (filter_options.get("technologies") or []))
    channel_options = "".join(f"<option value='{html.escape(value)}'>{html.escape(value)}</option>" for value in (filter_options.get("channels") or []))
    module_options = "".join(f"<option value='{html.escape(str(group.get('label') or ''))}'>{html.escape(str(group.get('label') or ''))}</option>" for group in (payload.get("groups") or []))
    quick_module_buttons = "".join(
        f"<button class='quick-btn' data-module='{html.escape(str(group.get('label') or ''))}' onclick=\"setQuickModule('{html.escape(str(group.get('label') or ''))}', this)\">{html.escape(str(group.get('label') or ''))}</button>"
        for group in (payload.get("groups") or [])
    )
    preset_buttons = "".join([
        "<button class='quick-btn preset-btn' data-preset='planned_unsent' onclick=\"applyPreset('planned_unsent', this)\">专题洞察未发送</button>",
        "<a class='quick-btn preset-link' href='/ai-influence?period=7d'>最近 7 天</a>",
        "<a class='quick-btn preset-link' href='/ai-influence?period=30d'>近 30 天</a>",
    ])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Influence Reports · Solar Harness</title>
  <style>
    :root {{ --ink:#17231f; --muted:#61706a; --line:#e8dcc8; --paper:#fffdf8; --bg:#f4efe4; --green:#123b35; --gold:#c9863d; --accent:#9a5a1a; }}
    body {{ margin:0; background:radial-gradient(circle at 12% 8%, #fff7df 0, transparent 28%), linear-gradient(135deg,#f4efe4,#edf2ea); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif; }}
    .wrap {{ max-width:1380px; margin:0 auto; padding:30px 20px 56px; }}
    .hero {{ border-radius:28px; padding:30px; color:#fff; background:linear-gradient(135deg,#123b35,#315f4f 58%,#c9863d); box-shadow:0 22px 60px rgba(30,45,37,.18); }}
    .kicker {{ font-size:12px; letter-spacing:.16em; text-transform:uppercase; opacity:.82; }}
    h1 {{ margin:9px 0 8px; font-size:36px; line-height:1.12; }}
    .hero p {{ margin:0; max-width:820px; opacity:.92; }}
    .toolbar {{ display:flex; gap:12px; align-items:center; margin:18px 0; flex-wrap:wrap; }}
    .tabs {{ display:flex; gap:10px; margin:18px 0 10px; flex-wrap:wrap; }}
    .tab-btn {{ border:1px solid var(--line); background:#fff; color:var(--green); border-radius:999px; padding:10px 16px; font-size:14px; font-weight:700; cursor:pointer; }}
    .tab-btn.active {{ background:var(--green); color:#fff; border-color:var(--green); }}
    .tab-panel {{ display:none; }}
    .tab-panel.active {{ display:block; }}
    .pill {{ border:1px solid var(--line); background:rgba(255,253,248,.78); border-radius:999px; padding:7px 12px; color:var(--muted); font-size:13px; }}
    .period {{ text-decoration:none; }}
    .period.active {{ background:var(--green); color:#fff; border-color:var(--green); }}
    .btn {{ border:1px solid var(--line); background:#fff; color:var(--green); text-decoration:none; border-radius:999px; padding:9px 14px; font-size:13px; font-weight:700; cursor:pointer; }}
    .btn.primary {{ background:var(--green); color:#fff; border-color:var(--green); }}
    .btn.accent {{ background:#fff4e8; color:var(--accent); border-color:#efcfaa; }}
    .btn.sending {{ opacity:.72; transform:translateY(1px); box-shadow:inset 0 0 0 999px rgba(18,59,53,.08); cursor:wait; }}
    .btn.sent {{ background:#e6f5ee; color:#16633f; border-color:#a9d9c0; }}
    .btn.failed {{ background:#fff0ef; color:#9f2e24; border-color:#e5aaa3; }}
    .btn.tiny {{ padding:6px 10px; font-size:12px; }}
    .mail-config {{ display:none; margin:16px 0 22px; padding:18px; border-radius:22px; border:1px solid var(--line); background:rgba(255,253,248,.9); box-shadow:0 10px 26px rgba(49,42,31,.06); }}
    .mail-config.visible {{ display:block; }}
    .mail-config h2 {{ margin:0 0 12px; font-size:20px; color:var(--green); }}
    .mail-grid {{ display:grid; grid-template-columns:minmax(280px, 1fr) auto; gap:12px; align-items:end; }}
    .mail-field label {{ display:block; font-size:12px; color:var(--muted); margin-bottom:6px; }}
    .mail-field input {{ width:100%; box-sizing:border-box; border:1px solid var(--line); border-radius:14px; padding:12px 14px; font-size:14px; background:#fff; }}
    .hint,.status-line {{ color:var(--muted); font-size:12px; }}
    .status-line {{ min-height:20px; margin-top:8px; }}
    .report-filters {{ display:grid; grid-template-columns:repeat(6,minmax(150px,1fr)); gap:10px; padding:16px; border:1px solid var(--line); background:#fffdf8; border-radius:22px; margin:6px 0 14px; }}
    .filter-field label {{ display:block; font-size:12px; color:var(--muted); margin-bottom:6px; }}
    .filter-field select {{ width:100%; box-sizing:border-box; border:1px solid var(--line); border-radius:14px; padding:11px 12px; font-size:14px; background:#fff; }}
    .filter-check {{ display:flex; align-items:center; gap:8px; min-height:48px; border:1px solid var(--line); border-radius:14px; padding:0 12px; background:#fff; color:var(--ink); }}
    .filter-check input {{ margin:0; }}
    .quick-filters {{ display:flex; gap:8px; flex-wrap:wrap; margin:0 0 16px; }}
    .quick-btn {{ border:1px solid var(--line); background:#fff; color:var(--green); border-radius:999px; padding:8px 13px; font-size:12px; font-weight:700; cursor:pointer; }}
    .quick-btn.active {{ background:var(--green); color:#fff; border-color:var(--green); }}
    .preset-link {{ text-decoration:none; display:inline-flex; align-items:center; }}
    .active-chips {{ display:flex; gap:8px; flex-wrap:wrap; margin:0 0 16px; }}
    .chip {{ display:inline-flex; align-items:center; gap:8px; border:1px solid #e5d8c4; background:#fff8ef; color:var(--ink); border-radius:999px; padding:8px 12px; font-size:12px; }}
    .chip button {{ border:0; background:transparent; color:var(--muted); cursor:pointer; font-size:12px; padding:0; }}
    .clear-filters {{ border:0; background:transparent; color:var(--accent); cursor:pointer; font-size:12px; font-weight:700; padding:0; }}
    .results-meta {{ display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin:0 0 10px; color:var(--muted); font-size:13px; }}
    .report-results {{ display:grid; gap:14px; }}
    .report-source {{ display:none; }}
    .channel-group {{ border:1px solid var(--line); border-radius:22px; background:rgba(255,253,248,.84); padding:12px 14px 6px; }}
    .channel-group + .channel-group {{ margin-top:12px; }}
    .channel-group summary {{ cursor:pointer; list-style:none; display:flex; justify-content:space-between; align-items:center; gap:10px; color:var(--green); font-weight:800; }}
    .channel-group summary::-webkit-details-marker {{ display:none; }}
    .channel-group-left,.channel-group-right {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
    .channel-group-count {{ color:var(--muted); font-size:12px; font-weight:600; }}
    .group-send-btn {{ border:1px solid #efcfaa; background:#fff4e8; color:var(--accent); border-radius:999px; padding:7px 11px; font-size:12px; font-weight:700; cursor:pointer; }}
    .group {{ margin-top:24px; }}
    .group-head {{ display:flex; justify-content:space-between; align-items:end; gap:12px; margin-bottom:12px; }}
    .group-kicker {{ color:var(--gold); font-size:12px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }}
    .group h2 {{ margin:4px 0 0; color:var(--green); font-size:25px; }}
    .summary-card {{ margin:0 0 14px; padding:16px 18px; border:1px solid var(--line); background:#fffaf2; border-radius:22px; }}
    .summary-headline {{ margin:0 0 10px; color:var(--ink); font-size:14px; }}
    .summary-metrics {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }}
    .summary-metric {{ border:1px solid #eadfcd; border-radius:16px; background:#fff; padding:8px 12px; color:var(--muted); min-width:96px; text-align:center; }}
    .summary-metric b {{ display:block; color:var(--green); font-size:16px; }}
    .summary-metric small {{ display:block; font-size:11px; margin-top:2px; }}
    .summary-table-wrap {{ overflow:auto; border:1px solid #eadfcd; border-radius:16px; background:#fff; }}
    .summary-table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    .summary-table th, .summary-table td {{ text-align:left; padding:9px 10px; border-bottom:1px solid #f0e6d8; vertical-align:top; }}
    .summary-table th {{ color:var(--muted); background:#fbf7ef; position:sticky; top:0; }}
    .summary-table a {{ color:var(--green); text-decoration:none; font-weight:700; }}
    .summary-table a.video-source-link {{ margin-left:8px; font-size:11px; color:var(--gold); font-weight:600; }}
    .resource-table-wrap {{ overflow:auto; border:1px solid #eadfcd; border-radius:16px; background:#fff; }}
    .resource-table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    .resource-table th, .resource-table td {{ text-align:left; padding:9px 10px; border-bottom:1px solid #f0e6d8; vertical-align:top; }}
    .resource-table th {{ color:var(--muted); background:#fbf7ef; }}
    .report-card {{ display:grid; grid-template-columns:minmax(0,1.45fr) minmax(220px,.48fr) auto; gap:18px; align-items:center; padding:20px; margin:13px 0; border:1px solid var(--line); background:rgba(255,253,248,.9); border-radius:24px; box-shadow:0 10px 26px rgba(49,42,31,.07); }}
    .date {{ color:var(--gold); font-size:12px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }}
    h3 {{ margin:4px 0 6px; font-size:20px; color:var(--green); }}
    .meta {{ margin:4px 0; color:var(--muted); font-size:13px; }}
    .artifact-row {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }}
    .metrics span {{ border:1px solid #eadfcd; border-radius:16px; background:#fbf7ef; padding:10px; text-align:center; color:var(--muted); }}
    .metrics b {{ display:block; color:var(--green); font-size:18px; line-height:1.2; }}
    .metrics small {{ display:block; font-size:11px; margin-top:2px; }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    .empty {{ margin-top:18px; padding:22px; border:1px dashed var(--line); border-radius:20px; background:#fffdf8; color:var(--muted); }}
    @media(max-width:1180px) {{ .report-filters {{ grid-template-columns:repeat(3,minmax(0,1fr)); }} }}
    @media(max-width:980px) {{ .report-card {{ grid-template-columns:1fr; }} .actions {{ justify-content:flex-start; }} .report-filters {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media(max-width:720px) {{ .mail-grid, .report-filters {{ grid-template-columns:1fr; }} .wrap {{ padding-inline:14px; }} h1 {{ font-size:29px; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="kicker">Solar Harness · AI Influence</div>
      <h1>AI Influence 报告中心</h1>
      <p>这里统一挂 AI Influence 的日度洞察、专题报告、统一日报和历史 phase 洞察。每条都可以直接打开，也可以在旁边一键发到配置好的邮箱。</p>
    </section>
    <div class="toolbar">
      <span class="pill">状态：{html.escape(str(payload.get("status") or "N/A"))}</span>
      <span class="pill">总报告：{int(payload.get("count", 0) or 0)}</span>
      <span class="pill">周期：{html.escape(current_period)}</span>
      <span class="pill">收件人：{html.escape(current_to or 'N/A')}</span>
      {module_pills}
      {period_links}
      <a class="btn" href="/">回到 Solar Status</a>
      <button class="btn accent" onclick="showMailConfig()">配置发送邮箱</button>
    </div>
    <div class="tabs">
      <button class="tab-btn active" data-tab="reports" onclick="switchTab('reports', this)">报告汇总</button>
      <button class="tab-btn" data-tab="resources" onclick="switchTab('resources', this)">素材资源</button>
    </div>
    <section id="mail-config" class="mail-config">
      <h2>配置发送邮箱</h2>
      <div class="mail-grid">
        <div class="mail-field">
          <label for="mail-to">收件人</label>
          <input id="mail-to" value="{html.escape(current_to)}" placeholder="多个邮箱可用逗号分隔">
        </div>
        <button class="btn primary" onclick="saveMailConfig()">保存配置</button>
      </div>
      <div class="hint">当前发信会复用现有 Gmail SMTP/keychain 能力；这里主要配置默认收件人。</div>
      <div id="mail-status" class="status-line"></div>
    </section>
    <section id="tab-reports" class="tab-panel active">
      <div class="report-filters">
        <div class="filter-field">
          <label for="filter-theme">主题</label>
          <select id="filter-theme" onchange="applyReportFilters()">
            <option value="">全部主题</option>
            {theme_options}
          </select>
        </div>
        <div class="filter-field">
          <label for="filter-technology">技术</label>
          <select id="filter-technology" onchange="applyReportFilters()">
            <option value="">全部技术</option>
            {technology_options}
          </select>
        </div>
        <div class="filter-field">
          <label for="filter-channel">频道 / 账号</label>
          <select id="filter-channel" onchange="applyReportFilters()">
            <option value="">全部频道 / 账号</option>
            {channel_options}
          </select>
        </div>
        <div class="filter-field">
          <label for="filter-module">模块</label>
          <select id="filter-module" onchange="applyReportFilters()">
            <option value="">全部模块</option>
            {module_options}
          </select>
        </div>
        <div class="filter-field">
          <label for="sort-reports">排序方式</label>
          <select id="sort-reports" onchange="applyReportFilters()">
            <option value="date_desc">时间：最新优先</option>
            <option value="date_asc">时间：最早优先</option>
            <option value="title_asc">标题：A-Z</option>
            <option value="module_asc">模块：A-Z</option>
          </select>
        </div>
        <label class="filter-check"><input id="filter-unsent" type="checkbox" onchange="applyReportFilters()">只看未发送</label>
        <label class="filter-check"><input id="group-channel" type="checkbox" onchange="applyReportFilters()">按频道折叠</label>
      </div>
      <div class="quick-filters">
        <button class="quick-btn active" data-module="" onclick="setQuickModule('', this)">全部报告</button>
        {quick_module_buttons}
        {preset_buttons}
      </div>
      <div id="active-chips" class="active-chips">
        <span class="chip">当前周期：{html.escape(current_period)}</span>
      </div>
      <div class="results-meta">
        <div id="report-results-count">N/A</div>
        <div>支持时间、主题、技术、频道、模块、邮件状态和频道折叠。</div>
      </div>
      <div id="report-source" class="report-source">{''.join(report_cards)}</div>
      <div id="report-results" class="report-results">{'<div class="empty">还没有 AI Influence 报告。先跑一次相关流水线。</div>' if not report_cards else ''}</div>
    </section>
    <section id="tab-resources" class="tab-panel">
      {' '.join(resource_sections) if resource_sections else "<div class='empty'>当前还没有素材资源。</div>"}
    </section>
  </div>
  <script>
    function switchTab(tab, btn) {{
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.toggle('active', el === btn));
      document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
      const panel = document.getElementById('tab-' + tab);
      if (panel) panel.classList.add('active');
    }}
    function showMailConfig() {{
      document.getElementById('mail-config').classList.toggle('visible');
    }}
    function setQuickModule(value, btn) {{
      const select = document.getElementById('filter-module');
      select.value = value;
      document.querySelectorAll('.quick-btn[data-module]').forEach(el => el.classList.toggle('active', el === btn));
      applyReportFilters();
    }}
    function clearAllReportFilters() {{
      document.getElementById('filter-theme').value = '';
      document.getElementById('filter-technology').value = '';
      document.getElementById('filter-channel').value = '';
      document.getElementById('filter-module').value = '';
      document.getElementById('sort-reports').value = 'date_desc';
      document.getElementById('filter-unsent').checked = false;
      document.getElementById('group-channel').checked = false;
      document.querySelectorAll('.quick-btn').forEach(el => el.classList.remove('active'));
      const allBtn = document.querySelector('.quick-btn[data-module=""]');
      if (allBtn) allBtn.classList.add('active');
    }}
    function applyPreset(name, btn) {{
      clearAllReportFilters();
      if (name === 'planned_unsent') {{
        document.getElementById('filter-module').value = '专题洞察';
        document.getElementById('filter-unsent').checked = true;
      }}
      document.querySelectorAll('.preset-btn').forEach(el => el.classList.toggle('active', el === btn));
      applyReportFilters();
    }}
    function renderActiveChips() {{
      const root = document.getElementById('active-chips');
      const chips = [`<span class="chip">当前周期：{html.escape(current_period)}</span>`];
      const values = [
        ['主题', document.getElementById('filter-theme').value],
        ['技术', document.getElementById('filter-technology').value],
        ['频道', document.getElementById('filter-channel').value],
        ['模块', document.getElementById('filter-module').value],
      ];
      values.forEach(([label, value]) => {{
        if (!value) return;
        chips.push(`<span class="chip">${{label}}：${{value}} <button type="button" data-clear="${{label}}">清除</button></span>`);
      }});
      if (document.getElementById('filter-unsent').checked) chips.push('<span class="chip">邮件：未发送</span>');
      if (document.getElementById('group-channel').checked) chips.push('<span class="chip">视图：按频道折叠</span>');
      chips.push('<button class="clear-filters" type="button" onclick="clearAllReportFilters(); applyReportFilters();">清空筛选</button>');
      root.innerHTML = chips.join('');
      root.querySelectorAll('button[data-clear]').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const label = btn.dataset.clear;
          if (label === '主题') document.getElementById('filter-theme').value = '';
          if (label === '技术') document.getElementById('filter-technology').value = '';
          if (label === '频道') document.getElementById('filter-channel').value = '';
          if (label === '模块') document.getElementById('filter-module').value = '';
          applyReportFilters();
        }});
      }});
    }}
    function visibleReportCards() {{
      const theme = document.getElementById('filter-theme').value;
      const technology = document.getElementById('filter-technology').value;
      const channel = document.getElementById('filter-channel').value;
      const moduleName = document.getElementById('filter-module').value;
      const unsentOnly = document.getElementById('filter-unsent').checked;
      return Array.from(document.querySelectorAll('#report-source .report-card')).filter(card => {{
        const main = card.querySelector('.main');
        const okTheme = !theme || (main.dataset.themes || '').includes(theme);
        const okTechnology = !technology || (main.dataset.technologies || '').includes(technology);
        const okChannel = !channel || (main.dataset.channels || '').includes(channel);
        const okModule = !moduleName || (main.dataset.module || '') === moduleName;
        const okMail = !unsentOnly || !['sent', 'warn'].includes((main.dataset.mailStatus || '').toLowerCase());
        return okTheme && okTechnology && okChannel && okModule && okMail;
      }});
    }}
    function sortReportCards(cards) {{
      const mode = document.getElementById('sort-reports').value;
      cards.sort((a, b) => {{
        const am = a.querySelector('.main');
        const bm = b.querySelector('.main');
        const ad = am.dataset.date || '';
        const bd = bm.dataset.date || '';
        const at = (am.dataset.title || '').toLowerCase();
        const bt = (bm.dataset.title || '').toLowerCase();
        const amod = (am.dataset.module || '').toLowerCase();
        const bmod = (bm.dataset.module || '').toLowerCase();
        if (mode === 'date_asc') return ad.localeCompare(bd);
        if (mode === 'title_asc') return at.localeCompare(bt);
        if (mode === 'module_asc') return amod.localeCompare(bmod) || bd.localeCompare(ad);
        return bd.localeCompare(ad);
      }});
      return cards;
    }}
    function renderReportCards(cards) {{
      const container = document.getElementById('report-results');
      const counter = document.getElementById('report-results-count');
      container.innerHTML = '';
      counter.textContent = '当前可见：' + cards.length + ' 份报告';
      if (!cards.length) {{
        container.innerHTML = "<div class='empty'>当前筛选条件下没有报告。</div>";
        return;
      }}
      if (document.getElementById('group-channel').checked) {{
        const grouped = new Map();
        cards.forEach(card => {{
          const channel = card.querySelector('.main').dataset.primaryChannel || '未分配频道';
          if (!grouped.has(channel)) grouped.set(channel, []);
          grouped.get(channel).push(card);
        }});
        Array.from(grouped.entries()).sort((a, b) => a[0].localeCompare(b[0])).forEach(([channel, entries]) => {{
          const details = document.createElement('details');
          details.className = 'channel-group';
          details.open = true;
          const unsent = entries.filter(card => !['sent', 'warn'].includes((card.querySelector('.main').dataset.mailStatus || '').toLowerCase()));
          const summary = document.createElement('summary');
          summary.innerHTML = '<span class="channel-group-left"><span>' + channel + '</span><span class="channel-group-count">' + entries.length + ' 份报告</span></span>'
            + '<span class="channel-group-right">'
            + (unsent.length ? '<button type="button" class="group-send-btn">发送本组未发送（' + unsent.length + '）</button>' : '')
            + '</span>';
          details.appendChild(summary);
          entries.forEach(card => details.appendChild(card));
          const sendBtn = summary.querySelector('.group-send-btn');
          if (sendBtn) {{
            sendBtn.addEventListener('click', async (ev) => {{
              ev.preventDefault();
              ev.stopPropagation();
              await sendBatchReports(unsent, channel);
            }});
          }}
          container.appendChild(details);
        }});
        return;
      }}
      cards.forEach(card => container.appendChild(card));
    }}
    function applyReportFilters() {{
      document.querySelectorAll('.preset-btn').forEach(el => {{
        if (document.getElementById('filter-module').value !== '专题洞察' || !document.getElementById('filter-unsent').checked) {{
          el.classList.remove('active');
        }}
      }});
      const cards = sortReportCards(visibleReportCards());
      renderActiveChips();
      renderReportCards(cards);
    }}
    async function saveMailConfig() {{
      const to = document.getElementById('mail-to').value.trim();
      const status = document.getElementById('mail-status');
      status.textContent = '保存中...';
      const res = await fetch('/ai-influence/mail-config', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{to}})
      }});
      const data = await res.json();
      if (!data.ok) {{
        status.textContent = '保存失败：' + (data.error || JSON.stringify(data));
        return;
      }}
      status.textContent = '已保存，新的默认收件人：' + (data.config?.to || to);
      setTimeout(() => location.reload(), 500);
    }}
    async function sendAiInfluenceReport(payload, options = {{}}) {{
      const status = document.getElementById('mail-status');
      const button = options.button || null;
      const originalText = button ? button.textContent : '';
      if (button) {{
        button.disabled = true;
        button.classList.remove('sent', 'failed');
        button.classList.add('sending');
        button.textContent = '发送中...';
      }}
      status.textContent = '发信中...';
      try {{
        const body = Object.assign({{}}, payload, {{to: document.getElementById('mail-to').value.trim()}});
        const res = await fetch('/ai-influence/send', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(body)
        }});
        const data = await res.json();
        if (!data.ok) {{
          const message = data.error || data.result?.reason || JSON.stringify(data);
          status.textContent = '发送失败：' + message;
          if (button) {{
            button.classList.remove('sending');
            button.classList.add('failed');
            button.textContent = '发送失败';
            setTimeout(() => {{ button.disabled = false; button.textContent = originalText || '发送邮件'; button.classList.remove('failed'); }}, 2200);
          }}
          return;
        }}
        const result = data.result || {{}};
        status.textContent = '已发送：' + (result.subject || payload.title || '报告');
        if (button) {{
          button.classList.remove('sending');
          button.classList.add('sent');
          button.textContent = '已发送';
        }}
        if (!options.silent) {{
          setTimeout(() => location.reload(), 900);
        }}
      }} catch (err) {{
        status.textContent = '发送失败：' + (err && err.message ? err.message : err);
        if (button) {{
          button.classList.remove('sending');
          button.classList.add('failed');
          button.textContent = '发送失败';
          setTimeout(() => {{ button.disabled = false; button.textContent = originalText || '发送邮件'; button.classList.remove('failed'); }}, 2200);
        }}
      }}
    }}
    async function sendBatchReports(cards, label) {{
      const status = document.getElementById('mail-status');
      const pending = cards
        .map(card => card.querySelector('.main')?.dataset.mailPayload || '')
        .filter(Boolean)
        .map(raw => JSON.parse(raw));
      if (!pending.length) {{
        status.textContent = '这一组没有可发送的未发送报告。';
        return;
      }}
      showMailConfig();
      status.textContent = '批量发送中：' + label + '（0/' + pending.length + '）';
      for (let i = 0; i < pending.length; i += 1) {{
        status.textContent = '批量发送中：' + label + '（' + (i + 1) + '/' + pending.length + '）';
        await sendAiInfluenceReport(pending[i], {{silent: true}});
      }}
      status.textContent = '批量发送完成：' + label + '（' + pending.length + ' 份）';
      setTimeout(() => location.reload(), 900);
    }}
    applyReportFilters();
  </script>
</body>
</html>"""


def _resolve_ai_influence_report(report_id_raw: str, artifact_raw: str):
    report_id = urllib.parse.unquote(str(report_id_raw or "")).strip()
    artifact = urllib.parse.unquote(str(artifact_raw or "report_html")).strip() or "report_html"
    return _resolve_ai_influence_artifact(report_id, artifact)


def _resolve_ai_influence_transcript(report_id_raw: str, video_ref_raw: str, video_id_raw: str) -> dict | None:
    item = _resolve_ai_influence_item(report_id_raw)
    if not item:
        return None
    report_dir = Path(str(item.get("_report_dir") or ""))
    evidence = _read_json_file(report_dir / "evidence-pack.json")
    videos = evidence.get("videos") if isinstance(evidence.get("videos"), list) else []
    video_ref = str(video_ref_raw or "").strip()
    video_id = str(video_id_raw or "").strip()
    match = None
    for video in videos:
        if not isinstance(video, dict):
            continue
        if video_ref and str(video.get("video_ref") or "").strip() == video_ref:
            match = video
            break
        if video_id and str(video.get("video_id") or "").strip() == video_id:
            match = video
            break
    if not match:
        return None
    transcript = str(match.get("transcript_clean") or "")
    if not transcript.strip():
        return None
    return {
        "report_id": str(item.get("id") or ""),
        "report_dir": report_dir,
        "video": match,
        "transcript": transcript,
    }


def _ai_influence_transcript_html(report_id: str, video: dict, transcript: str) -> str:
    title = str(video.get("title") or "Untitled transcript")
    channel = str(video.get("channel") or "N/A")
    published = str(video.get("published_at") or "N/A")
    duration = video.get("duration_min")
    youtube_url = str(video.get("url") or "").strip()
    duration_text = f"{float(duration):.1f} 分钟" if isinstance(duration, (int, float)) else "N/A"
    report_url = _ai_influence_artifact_view_url(report_id, "evidence_pack_json")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · 原始 Transcript</title>
  <style>
    :root {{ --ink:#17231f; --muted:#61706a; --line:#e8dcc8; --paper:#fffdf8; --bg:#f4efe4; --green:#123b35; --gold:#c9863d; }}
    body {{ margin:0; background:linear-gradient(135deg,#f4efe4,#edf2ea); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif; }}
    .wrap {{ max-width:1120px; margin:0 auto; padding:28px 18px 48px; }}
    .hero {{ border-radius:26px; padding:26px; color:#fff; background:linear-gradient(135deg,#123b35,#315f4f 58%,#c9863d); box-shadow:0 18px 50px rgba(30,45,37,.16); }}
    .eyebrow {{ font-size:12px; letter-spacing:.14em; text-transform:uppercase; opacity:.84; }}
    h1 {{ margin:8px 0 10px; font-size:34px; line-height:1.16; }}
    .meta {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }}
    .pill {{ border:1px solid rgba(255,255,255,.28); background:rgba(255,255,255,.12); border-radius:999px; padding:7px 12px; font-size:13px; }}
    .toolbar {{ display:flex; gap:10px; flex-wrap:wrap; margin:16px 0 18px; }}
    .btn {{ border:1px solid var(--line); background:#fff; color:var(--green); text-decoration:none; border-radius:999px; padding:9px 14px; font-size:13px; font-weight:700; }}
    .btn.primary {{ background:var(--green); color:#fff; border-color:var(--green); }}
    .panel {{ border:1px solid var(--line); border-radius:24px; background:rgba(255,253,248,.92); box-shadow:0 10px 28px rgba(49,42,31,.07); }}
    .panel-head {{ padding:18px 20px 0; color:var(--muted); font-size:13px; }}
    pre {{ margin:0; padding:20px; white-space:pre-wrap; word-break:break-word; line-height:1.72; font-size:14px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">AI Influence · Raw Transcript</div>
      <h1>{html.escape(title)}</h1>
      <div class="meta">
        <span class="pill">频道：{html.escape(channel)}</span>
        <span class="pill">发布时间：{html.escape(published[:10] if published != "N/A" else published)}</span>
        <span class="pill">时长：{html.escape(duration_text)}</span>
      </div>
    </section>
    <div class="toolbar">
      <a class="btn primary" href="{html.escape(youtube_url)}" target="_blank" rel="noreferrer">打开 YouTube 原视频</a>
      <a class="btn" href="{html.escape(report_url)}" target="_blank" rel="noreferrer">打开 evidence-pack.json</a>
      <a class="btn" href="/ai-influence?period=30d">回到 AI Influence</a>
    </div>
    <section class="panel">
      <div class="panel-head">原始转写素材</div>
      <pre>{html.escape(transcript)}</pre>
    </section>
  </div>
</body>
</html>"""


def _read_social_accounts(limit: int = 300) -> list[dict]:
    if not AI_INFLUENCE_ACCOUNTS.exists():
        return []
    accounts = []
    for line in AI_INFLUENCE_ACCOUNTS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("tier\t"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        tier, category, handle, display_name, notes, enabled, rotation_group = parts[:7]
        accounts.append({
            "tier": int(tier) if str(tier).isdigit() else 2,
            "category": category,
            "handle": handle,
            "display_name": display_name,
            "notes": notes,
            "enabled": str(enabled).lower() == "true",
            "rotation_group": rotation_group,
        })
        if len(accounts) >= limit:
            break
    return accounts


def _github_trends_status() -> dict:
    cfg = _read_yaml_file(GITHUB_TRENDS_CONFIG)
    db_path = Path(((cfg.get("output") or {}).get("database") or GITHUB_TRENDS_DB)).expanduser()
    status = {"database": str(db_path), "snapshots": 0, "latest": "", "ok": db_path.exists()}
    if not db_path.exists():
        return status
    try:
        conn = sqlite3.connect(db_path)
        status["snapshots"] = conn.execute("SELECT COUNT(*) FROM repo_snapshots").fetchone()[0]
        status["latest"] = conn.execute("SELECT MAX(collected_at) FROM repo_snapshots").fetchone()[0] or ""
    except Exception as exc:
        status["ok"] = False
        status["error"] = f"{type(exc).__name__}: {exc}"
    return status


def _knowledge_subscriptions_payload() -> dict:
    youtube_cfg = _read_yaml_file(YOUTUBE_DIGEST_CONFIG)
    github_cfg = _read_yaml_file(GITHUB_TRENDS_CONFIG)
    channels = youtube_cfg.get("channels") if isinstance(youtube_cfg.get("channels"), list) else []
    topics = github_cfg.get("tracked_topics") if isinstance(github_cfg.get("tracked_topics"), list) else []
    repos = github_cfg.get("tracked_repos") if isinstance(github_cfg.get("tracked_repos"), list) else []
    accounts = _read_social_accounts()
    return {
        "ok": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "youtube": {"config": str(YOUTUBE_DIGEST_CONFIG), "count": len(channels), "channels": channels},
        "social": {"accounts": str(AI_INFLUENCE_ACCOUNTS), "count": len(accounts), "items": accounts},
        "github": {
            "config": str(GITHUB_TRENDS_CONFIG),
            "topic_count": len(topics),
            "tracked_topics": topics,
            "tracked_repos": repos,
            "db": _github_trends_status(),
        },
    }


def _file_mtime_iso(path: Path) -> str:
    try:
        return datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except Exception:
        return ""


def _count_files(path: Path, pattern: str = "*", limit: int = 100000) -> int:
    if not path.exists():
        return 0
    count = 0
    try:
        for _ in path.rglob(pattern):
            count += 1
            if count >= limit:
                return count
    except Exception:
        return count
    return count


def _dir_size_bytes(path: Path, limit: int = 100000) -> int:
    if not path.exists():
        return 0
    total = 0
    scanned = 0
    try:
        for root, _, files in os.walk(path):
            for name in files:
                scanned += 1
                try:
                    total += (Path(root) / name).stat().st_size
                except Exception:
                    pass
                if scanned >= limit:
                    return total
    except Exception:
        return total
    return total


def _latest_file(path: Path, pattern: str = "*") -> dict:
    latest: Path | None = None
    if not path.exists():
        return {"path": "", "mtime": ""}
    try:
        for item in path.rglob(pattern):
            if not item.is_file():
                continue
            if latest is None or item.stat().st_mtime > latest.stat().st_mtime:
                latest = item
    except Exception:
        pass
    return {"path": str(latest) if latest else "", "mtime": _file_mtime_iso(latest) if latest else ""}


def _dispatch_status_counts(dispatch_dir: Path) -> dict:
    counts: dict[str, int] = {}
    latest: Path | None = None
    if not dispatch_dir.exists():
        return {"dir": str(dispatch_dir), "total": 0, "counts": counts, "latest": {}}
    try:
        for path in dispatch_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")[:2000]
            match = re.search(r"(?m)^status:\s*['\"]?([^'\"\n]+)", text)
            status = (match.group(1).strip() if match else "unknown") or "unknown"
            counts[status] = counts.get(status, 0) + 1
            if latest is None or path.stat().st_mtime > latest.stat().st_mtime:
                latest = path
    except Exception as exc:
        counts["error"] = counts.get("error", 0) + 1
        return {"dir": str(dispatch_dir), "total": sum(counts.values()), "counts": counts, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "dir": str(dispatch_dir),
        "total": sum(counts.values()),
        "counts": counts,
        "latest": {"path": str(latest) if latest else "", "mtime": _file_mtime_iso(latest) if latest else ""},
    }


def _recent_vault_markdown(vault: Path, hours: int = 24, limit: int = 10000) -> dict:
    cutoff = time.time() - hours * 3600
    count = 0
    latest: Path | None = None
    scanned = 0
    skip_names = {"_raw", ".git", ".obsidian", ".trash"}
    try:
        for root, dirs, files in os.walk(vault):
            dirs[:] = [d for d in dirs if d not in skip_names]
            for name in files:
                if not name.endswith(".md"):
                    continue
                scanned += 1
                path = Path(root) / name
                try:
                    mtime = path.stat().st_mtime
                except Exception:
                    continue
                if mtime >= cutoff:
                    count += 1
                if latest is None or mtime > latest.stat().st_mtime:
                    latest = path
                if scanned >= limit:
                    return {"recent_24h": count, "scanned": scanned, "truncated": True, "latest": {"path": str(latest) if latest else "", "mtime": _file_mtime_iso(latest) if latest else ""}}
    except Exception as exc:
        return {"recent_24h": count, "scanned": scanned, "error": f"{type(exc).__name__}: {exc}"}
    return {"recent_24h": count, "scanned": scanned, "truncated": False, "latest": {"path": str(latest) if latest else "", "mtime": _file_mtime_iso(latest) if latest else ""}}


def _knowledge_ingest_progress_payload() -> dict:
    raw_dir = KNOWLEDGE_DIR / "_raw"
    dispatch_dir = raw_dir / "solar-harness" / ".dispatch"
    state_root = Path.home() / ".solar" / "harness" / "state"
    sources = {
        "chatgpt": raw_dir / "chatgpt-import",
        "web_captures": raw_dir / "web-captures",
        "youtube": raw_dir / "youtube-influence-digest",
        "ai_influence": raw_dir / "ai-influence-daily-digest",
        "solar_harness": raw_dir / "solar-harness",
    }
    source_rows = []
    for name, path in sources.items():
        source_rows.append({
            "name": name,
            "path": str(path),
            "files": _count_files(path),
            "latest": _latest_file(path),
        })
    asr_queue = state_root / "youtube-influence-digest" / "asr-queue"
    asr_done = state_root / "youtube-influence-digest" / "asr-done"
    asr_audio = state_root / "youtube-influence-digest" / "asr-audio"
    youtube_cfg = _read_yaml_file(YOUTUBE_DIGEST_CONFIG)
    asr_cfg = youtube_cfg.get("asr") if isinstance(youtube_cfg.get("asr"), dict) else {}
    asr_blocks_progress = bool(asr_cfg.get("blocking_for_knowledge_progress", False))
    asr_queue_policy = str(asr_cfg.get("queue_health_policy") or ("blocking" if asr_blocks_progress else "fallback_non_blocking"))
    dispatch = _dispatch_status_counts(dispatch_dir)
    counts = dispatch.get("counts", {})
    completed = sum(v for k, v in counts.items() if str(k) in {"completed", "success", "skipped", "skipped-duplicate"})
    pending = sum(v for k, v in counts.items() if str(k) in {"pending", "running", "queued"})
    failed = sum(v for k, v in counts.items() if str(k) in {"failed", "error"})
    blocked = sum(v for k, v in counts.items() if str(k).startswith("blocked"))
    unknown = int(counts.get("unknown", 0) or 0)
    total = int(dispatch.get("total", 0) or 0)
    asr_queue_count = _count_files(asr_queue, "*.json")
    asr_done_count = _count_files(asr_done, "*.json")
    asr_audio_bytes = _dir_size_bytes(asr_audio)
    asr_blocking_count = asr_queue_count if asr_blocks_progress else 0
    status = "ok"
    if pending or blocked or asr_blocking_count:
        status = "pending"
    if failed:
        status = "warn"
    mirage = _mirage_status()
    qmd = mirage.get("qmd") if isinstance(mirage.get("qmd"), dict) else {}
    vault_md = _recent_vault_markdown(KNOWLEDGE_DIR)
    source_rows.sort(key=lambda item: ((item.get("latest") or {}).get("mtime") or ""), reverse=True)
    latest_source = source_rows[0] if source_rows else {}
    blockers = []
    if failed:
        blockers.append({"level": "warn", "title": "有失败 dispatch", "detail": f"{failed} 个 dispatch 失败，需要人工看失败原因或重派。"})
    if blocked:
        blockers.append({"level": "pending", "title": "有阻塞项", "detail": f"{blocked} 个 dispatch 被标记为 blocked，通常是缺 transcript 或等待人工确认。"})
    if asr_blocking_count:
        blockers.append({"level": "pending", "title": "YouTube ASR 队列积压", "detail": f"{asr_queue_count} 个视频等音频转文字；完成后才能产出高质量知识。"})
    if pending:
        blockers.append({"level": "pending", "title": "有待处理 dispatch", "detail": f"{pending} 个 dispatch 还没完成。"})
    if unknown:
        blockers.append({"level": "warn", "title": "历史状态不规范", "detail": f"{unknown} 个旧 dispatch 没有标准 status，建议后续维护清理。"})
    if not blockers:
        blockers.append({"level": "ok", "title": "没有明显卡点", "detail": "当前没有 failed/blocked/pending/ASR 积压。"})
    next_actions = []
    if failed:
        next_actions.append("先查看 failed dispatch，决定重派还是标记 skipped。")
    if asr_blocking_count:
        next_actions.append("让 YouTube ASR queue 低速处理，先不要继续批量抓字幕以免 429。")
    if pending:
        next_actions.append("确认 wiki dispatch tail/调度器是否在消费 pending。")
    if qmd.get("status") not in {"ok", None}:
        next_actions.append("修复 QMD/embedding，否则新知识不能稳定检索。")
    if not next_actions:
        next_actions.append("观察最近产出即可；无需人工介入。")
    return {
        "ok": status in {"ok", "pending"},
        "status": status,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "vault": str(KNOWLEDGE_DIR),
        "raw_dir": str(raw_dir),
        "headline": (
            f"还有 {pending} 个待处理、{failed} 个失败、{blocked} 个阻塞；"
            f"近 24 小时新增/更新 {vault_md.get('recent_24h', 0)} 个知识页。"
        ),
        "funnel": {
            "total_dispatch": total,
            "completed": completed,
            "pending": pending,
            "failed": failed,
            "blocked": blocked,
            "unknown": unknown,
            "asr_waiting": asr_queue_count,
            "asr_blocking": asr_blocking_count,
            "asr_policy": asr_queue_policy,
            "asr_done": asr_done_count,
            "recent_knowledge_24h": vault_md.get("recent_24h", 0),
        },
        "activity": {
            "latest_raw_source": latest_source,
            "latest_dispatch": dispatch.get("latest", {}),
            "latest_knowledge_page": vault_md.get("latest", {}),
        },
        "blockers": blockers[:6],
        "next_actions": next_actions[:5],
        "dispatch": dispatch,
        "qmd": {
            "status": qmd.get("status", mirage.get("qmd_status", "unknown")) if isinstance(qmd, dict) else "unknown",
            "indexed": qmd.get("indexed", 0) if isinstance(qmd, dict) else 0,
            "pending": qmd.get("pending", "N/A") if isinstance(qmd, dict) else "N/A",
            "last_probe_at": mirage.get("last_probe_at", ""),
            "stale": mirage.get("stale", False),
        },
        "asr": {
            "queue": asr_queue_count,
            "blocking_for_progress": asr_blocks_progress,
            "blocking_count": asr_blocking_count,
            "policy": asr_queue_policy,
            "done": asr_done_count,
            "queue_dir": str(asr_queue),
            "audio_dir": str(asr_audio),
            "audio_cache_bytes": asr_audio_bytes,
            "audio_cache_mb": round(asr_audio_bytes / 1024 / 1024, 1),
            "latest_queue": _latest_file(asr_queue, "*.json"),
        },
        "sources": source_rows,
        "vault_markdown": vault_md,
    }


def _append_youtube_subscription(data: dict) -> dict:
    cfg = _read_yaml_file(YOUTUBE_DIGEST_CONFIG)
    channels = cfg.get("channels") if isinstance(cfg.get("channels"), list) else []
    source = str(data.get("channel_id") or data.get("url") or data.get("handle") or "").strip()
    if not source:
        raise ValueError("channel_id/url/handle required")
    entry = {
        "url": source,
        "name": str(data.get("name") or data.get("handle") or source).strip(),
        "category": str(data.get("category") or "AI / Tech").strip(),
        "priority": str(data.get("priority") or "rotation").strip(),
    }
    key = entry["url"].lower()
    if any(str((x or {}).get("url") or (x or {}).get("channel_id") or "").lower() == key for x in channels if isinstance(x, dict)):
        return {"ok": True, "status": "exists", "entry": entry}
    channels.append(entry)
    cfg["channels"] = channels
    _write_yaml_file(YOUTUBE_DIGEST_CONFIG, cfg)
    return {"ok": True, "status": "added", "entry": entry}


def _append_social_subscription(data: dict) -> dict:
    handle = str(data.get("handle") or "").strip().lstrip("@")
    if not handle:
        raise ValueError("handle required")
    existing = {item["handle"].lower() for item in _read_social_accounts(limit=1000)}
    if handle.lower() in existing:
        return {"ok": True, "status": "exists", "handle": handle}
    tier = str(data.get("tier") or "2")
    category = str(data.get("category") or "custom").strip()
    display_name = str(data.get("display_name") or handle).strip()
    notes = str(data.get("notes") or "added from Solar WebUI").strip()
    enabled = "true" if data.get("enabled", True) is not False else "false"
    rotation_group = str(data.get("rotation_group") or "G").strip() if tier != "1" else ""
    with AI_INFLUENCE_ACCOUNTS.open("a", encoding="utf-8") as f:
        f.write("\t".join([tier, category, handle, display_name, notes, enabled, rotation_group]) + "\n")
    return {"ok": True, "status": "added", "handle": handle}


def _append_github_topic(data: dict) -> dict:
    cfg = _read_yaml_file(GITHUB_TRENDS_CONFIG)
    topics = cfg.get("tracked_topics") if isinstance(cfg.get("tracked_topics"), list) else []
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    if any(str((x or {}).get("name") or "").lower() == name.lower() for x in topics if isinstance(x, dict)):
        return {"ok": True, "status": "exists", "name": name}
    entry = {
        "name": name,
        "category": str(data.get("category") or "ai").strip(),
        "query": str(data.get("query") or name).strip(),
        "enabled": data.get("enabled", True) is not False,
    }
    topics.append(entry)
    cfg["tracked_topics"] = topics
    _write_yaml_file(GITHUB_TRENDS_CONFIG, cfg)
    return {"ok": True, "status": "added", "entry": entry}


def _append_github_repo(data: dict) -> dict:
    cfg = _read_yaml_file(GITHUB_TRENDS_CONFIG)
    repos = cfg.get("tracked_repos") if isinstance(cfg.get("tracked_repos"), list) else []
    repo = str(data.get("repo") or "").strip().removeprefix("https://github.com/")
    if repo.count("/") != 1:
        raise ValueError("repo must be owner/name")
    if repo.lower() in {str(x).lower() for x in repos}:
        return {"ok": True, "status": "exists", "repo": repo}
    repos.append(repo)
    cfg["tracked_repos"] = repos
    _write_yaml_file(GITHUB_TRENDS_CONFIG, cfg)
    return {"ok": True, "status": "added", "repo": repo}


def _knowledge_subscriptions_html() -> str:
    payload = _knowledge_subscriptions_payload()
    yt_rows = "".join(f"<li><b>{h(x.get('name') or x.get('url'))}</b> <span>{h(x.get('category',''))}</span><code>{h(x.get('url') or x.get('channel_id') or x.get('handle'))}</code></li>" for x in payload["youtube"]["channels"][:80] if isinstance(x, dict))
    social_rows = "".join(f"<li><b>@{h(x.get('handle'))}</b> <span>{h(x.get('category'))}</span><em>tier {h(x.get('tier'))}</em></li>" for x in payload["social"]["items"][:300])
    topic_rows = "".join(f"<li><b>{h(x.get('name'))}</b> <span>{h(x.get('category'))}</span><code>{h(x.get('query'))}</code></li>" for x in payload["github"]["tracked_topics"][:80] if isinstance(x, dict))
    repo_rows = "".join(f"<li><code>{h(repo)}</code></li>" for repo in payload["github"]["tracked_repos"][:80])
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowledge Subscriptions</title>
<style>body{{margin:0;background:#f4efe4;color:#17231f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif}}.wrap{{max-width:1180px;margin:0 auto;padding:24px 18px 44px}}.hero{{background:linear-gradient(135deg,#123b35,#315f4f 60%,#c9863d);color:#fff;border-radius:26px;padding:26px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;margin-top:16px}}.card{{background:#fffdf8;border:1px solid #eadfcd;border-radius:20px;padding:18px;box-shadow:0 8px 24px rgba(49,42,31,.06)}}input,select{{width:100%;box-sizing:border-box;border:1px solid #dbcdb7;border-radius:12px;padding:9px;margin:5px 0 9px;background:#fff}}button,.btn{{border:0;background:#123b35;color:#fff;border-radius:999px;padding:9px 14px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}}li{{margin:8px 0}}code{{display:block;color:#66736d;font-size:12px;margin-top:3px}}span,em{{color:#66736d;margin-left:6px}}.status{{color:#0f766e;font-weight:700}}</style></head>
<body><div class="wrap"><section class="hero"><h1>知识订阅中心</h1><p>YouTube 跟踪列表、热点社交媒体账号、GitHub 开源趋势分类都在这里维护。</p></section>
<div class="grid">
<section class="card"><h2>YouTube 跟踪</h2><p class="status">{payload['youtube']['count']} 个频道</p><form onsubmit="addSub(event,'/knowledge/subscriptions/youtube')"><input name="url" placeholder="@handle / channel URL / UC..." required><input name="name" placeholder="名称"><input name="category" placeholder="分类"><select name="priority"><option>tier1</option><option selected>rotation</option></select><button>增加 YouTube</button></form><ul>{yt_rows or '<li>N/A</li>'}</ul></section>
<section class="card"><h2>热点社交媒体</h2><p class="status">{payload['social']['count']} 个账号</p><form onsubmit="addSub(event,'/knowledge/subscriptions/social')"><input name="handle" placeholder="X handle，不带 @" required><input name="display_name" placeholder="显示名"><input name="category" placeholder="分类"><select name="tier"><option value="1">tier1</option><option value="2" selected>tier2</option></select><button>增加账号</button></form><ul>{social_rows or '<li>N/A</li>'}</ul></section>
<section class="card"><h2>GitHub 分类趋势</h2><p class="status">topic {payload['github']['topic_count']} · snapshot {payload['github']['db'].get('snapshots',0)}</p><form onsubmit="addSub(event,'/knowledge/subscriptions/github-topic')"><input name="name" placeholder="topic 名称" required><input name="query" placeholder="关键词/查询"><input name="category" placeholder="ai / agent / compute_framework"><button>增加 Topic</button></form><form onsubmit="addSub(event,'/knowledge/subscriptions/github-repo')"><input name="repo" placeholder="owner/repo，用于星标快照"><button>增加 Repo</button></form><h3>Topics</h3><ul>{topic_rows or '<li>N/A</li>'}</ul><h3>Tracked Repos</h3><ul>{repo_rows or '<li>N/A</li>'}</ul></section>
</div><p><a class="btn" href="/">回 Solar Status</a></p></div>
<script>
async function addSub(ev,url){{ev.preventDefault();const obj={{}};new FormData(ev.target).forEach((v,k)=>obj[k]=v);const res=await fetch(url,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(obj)}});const data=await res.json();if(!data.ok){{alert('失败: '+(data.error||JSON.stringify(data)));return}} location.reload();}}
</script></body></html>"""


def _mermaid_index_html() -> str:
    files = _list_mmd_files()
    cards = []
    for item in files:
        path = item["path"]
        name = html.escape(item["name"])
        rel = html.escape(item["rel"])
        root = html.escape(item["root"])
        url = "/mermaid/view?file=" + urllib.parse.quote(path)
        raw_url = "/mermaid/raw?file=" + urllib.parse.quote(path)
        cards.append(
            f"""<article class="mmd-card">
  <div>
    <h2>{name}</h2>
    <p>{rel}</p>
    <p class="muted">{root}</p>
  </div>
  <div class="actions">
    <a class="btn primary" href="{url}">打开图</a>
    <a class="btn" href="{raw_url}">看源码</a>
  </div>
</article>"""
        )
    if not cards:
        cards.append('<div class="empty">没有找到 .mmd 文件。</div>')
    default_file = str(REPORTS_DIR / "solar-system-architecture-20260508.mmd")
    default_link = "/mermaid/view?file=" + urllib.parse.quote(default_file)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solar Mermaid Viewer</title>
<style>
:root {{ --bg:#f7f0df; --ink:#211b12; --muted:#746858; --panel:#fffaf0; --line:rgba(33,27,18,.14); --accent:#1f6f5b; }}
body {{ margin:0; background:radial-gradient(circle at top left,#fff8df,#efe4cf 42%,#d9e7df); color:var(--ink); font-family:"Avenir Next","Gill Sans",ui-sans-serif,sans-serif; }}
header,main {{ max-width:1180px; margin:0 auto; padding:24px; }}
.hero {{ border:1px solid var(--line); border-radius:30px; padding:28px; background:linear-gradient(135deg,rgba(255,250,240,.90),rgba(226,239,230,.70)); box-shadow:0 24px 70px rgba(33,27,18,.10); }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.14em; color:var(--accent); font-weight:900; font-size:.78rem; }}
h1 {{ font-size:clamp(2.3rem,6vw,5.5rem); line-height:.9; margin:.2rem 0 .8rem; }}
.muted {{ color:var(--muted); }}
.toolbar,.actions {{ display:flex; flex-wrap:wrap; gap:.7rem; align-items:center; }}
.btn {{ border:1px solid var(--line); border-radius:14px; padding:.7rem .95rem; background:rgba(255,255,255,.54); color:var(--ink); text-decoration:none; font-weight:900; }}
.btn.primary {{ background:var(--ink); color:#fff8e8; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:1rem; margin-top:1rem; }}
.mmd-card {{ min-height:150px; display:flex; flex-direction:column; justify-content:space-between; gap:1rem; border:1px solid var(--line); border-radius:24px; padding:1rem; background:rgba(255,250,240,.78); box-shadow:0 14px 36px rgba(33,27,18,.07); overflow:hidden; }}
.mmd-card h2 {{ margin:.2rem 0; overflow-wrap:anywhere; }}
.mmd-card p {{ margin:.2rem 0; overflow-wrap:anywhere; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.84rem; }}
.empty {{ padding:2rem; border:1px dashed var(--line); border-radius:22px; background:rgba(255,250,240,.58); }}
</style>
</head>
<body>
<header>
  <div class="hero">
    <div class="eyebrow">Solar Harness Diagram Desk</div>
    <h1>Mermaid Viewer</h1>
    <p class="muted">直接浏览和渲染 Solar 里的 .mmd 架构图。默认只暴露 harness 和 Knowledge 目录下的 .mmd 文件。</p>
    <div class="toolbar">
      <a class="btn primary" href="{default_link}">打开 Solar 完整架构图</a>
      <a class="btn" href="/">回到 Solar Status</a>
      <a class="btn" href="/mermaid/list">查看 JSON 列表</a>
    </div>
  </div>
</header>
<main>
  <div class="grid">
    {''.join(cards)}
  </div>
</main>
</body>
</html>"""


def _mermaid_view_html(path: Path) -> str:
    name = html.escape(path.name)
    raw_path = html.escape(str(path))
    raw_url = "/mermaid/raw?file=" + urllib.parse.quote(str(path))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} · Solar Mermaid</title>
<style>
:root {{ --bg:#f6efe0; --ink:#1f1a12; --muted:#746858; --panel:#fffaf0; --line:rgba(31,26,18,.14); --accent:#1f6f5b; --danger:#9f3a2f; }}
body {{ margin:0; background:linear-gradient(135deg,#f8f0df,#dfece3); color:var(--ink); font-family:"Avenir Next","Gill Sans",ui-sans-serif,sans-serif; }}
header {{ max-width:1280px; margin:0 auto; padding:22px 24px 0; }}
main {{ max-width:calc(100vw - 24px); margin:0 auto; padding:12px 12px 24px; }}
.bar {{ border:1px solid var(--line); border-radius:24px; background:rgba(255,250,240,.86); padding:1rem; display:flex; gap:1rem; justify-content:space-between; flex-wrap:wrap; align-items:center; box-shadow:0 18px 50px rgba(31,26,18,.09); }}
h1 {{ margin:.15rem 0; font-size:clamp(1.6rem,4vw,3.6rem); }}
.path {{ color:var(--muted); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; overflow-wrap:anywhere; }}
.actions {{ display:flex; flex-wrap:wrap; gap:.65rem; }}
.btn {{ border:1px solid var(--line); border-radius:14px; padding:.7rem .95rem; background:rgba(255,255,255,.58); color:var(--ink); text-decoration:none; font-weight:900; cursor:pointer; }}
.btn.primary {{ background:var(--ink); color:#fff8e8; }}
.stage {{ border:1px solid var(--line); border-radius:24px; background:rgba(255,250,240,.72); min-height:78vh; padding:1rem; overflow:auto; box-shadow:inset 0 0 0 1px rgba(255,255,255,.25); }}
#diagram {{ transform-origin: top left; width:max-content; min-width:100%; }}
#diagram svg {{ max-width:none; height:auto; min-width:1200px; }}
#zoom-label {{ min-width:4.5rem; text-align:center; font-weight:900; color:var(--accent); }}
.error {{ color:var(--danger); white-space:pre-wrap; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.source {{ display:none; margin-top:1rem; background:#211b12; color:#f8efe0; border-radius:18px; padding:1rem; white-space:pre; overflow:auto; }}
</style>
</head>
<body>
<header>
  <div class="bar">
    <div>
      <div class="path">Solar Mermaid</div>
      <h1>{name}</h1>
      <div class="path">{raw_path}</div>
    </div>
    <div class="actions">
      <a class="btn" href="/mermaid">图列表</a>
      <a class="btn" href="{raw_url}">源码</a>
      <button class="btn" id="toggle-source">显示源码</button>
      <button class="btn" id="zoom-out">缩小</button>
      <span id="zoom-label">140%</span>
      <button class="btn" id="zoom-in">放大</button>
      <button class="btn primary" id="fit">适配宽度</button>
    </div>
  </div>
</header>
<main>
  <div class="stage">
    <div id="diagram">Loading...</div>
    <pre id="source" class="source"></pre>
  </div>
</main>
<script type="module">
import mermaid from '/mermaid/assets/mermaid.esm.min.mjs';
const file = {json.dumps(str(path))};
const rawUrl = '/mermaid/raw?file=' + encodeURIComponent(file);
const diagram = document.getElementById('diagram');
const source = document.getElementById('source');
const zoomLabel = document.getElementById('zoom-label');
let zoom = 1.4;
function applyZoom() {{
  diagram.style.transform = 'scale(' + zoom + ')';
  diagram.style.marginRight = ((zoom - 1) * 100) + '%';
  diagram.style.marginBottom = ((zoom - 1) * 70) + 'vh';
  zoomLabel.textContent = Math.round(zoom * 100) + '%';
}}
mermaid.initialize({{
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'base',
  themeVariables: {{
    fontSize: '24px',
    fontFamily: 'Avenir Next, Gill Sans, sans-serif',
    primaryTextColor: '#211b12',
    lineColor: '#4d4334'
  }},
  flowchart: {{ htmlLabels: true, curve: 'basis' }},
  sequence: {{ mirrorActors: false }}
}});
try {{
  const text = await fetch(rawUrl).then(r => {{
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.text();
  }});
  source.textContent = text;
  const result = await mermaid.render('solar-mermaid-svg', text);
  diagram.innerHTML = result.svg;
  if (result.bindFunctions) result.bindFunctions(diagram);
  applyZoom();
}} catch (err) {{
  diagram.innerHTML = '<div class="error">Mermaid 渲染失败：\\n' + String(err && err.stack || err) + '</div>';
}}
document.getElementById('toggle-source').addEventListener('click', () => {{
  source.style.display = source.style.display === 'block' ? 'none' : 'block';
}});
document.getElementById('fit').addEventListener('click', () => {{
  const svg = diagram.querySelector('svg');
  if (svg) {{
    zoom = 1;
    svg.style.maxWidth = '100%';
    svg.style.width = '100%';
    applyZoom();
  }}
}});
document.getElementById('zoom-in').addEventListener('click', () => {{
  zoom = Math.min(2.5, zoom + 0.2);
  applyZoom();
}});
document.getElementById('zoom-out').addEventListener('click', () => {{
  zoom = Math.max(0.8, zoom - 0.2);
  applyZoom();
}});
</script>
</body>
</html>"""


def _integrations_view_html() -> str:
    """Standalone human-readable HTML page for external integrations health (server-side rendered)."""
    data = _external_integrations_payload(refresh=True)
    items = data.get("integrations", []) if isinstance(data, dict) else []
    summary = data.get("summary", {}) if isinstance(data, dict) else {}
    generated_at = data.get("generated_at", "N/A") if isinstance(data, dict) else "N/A"

    def _badge(st: str) -> str:
        cls = {"ok": "ok", "warn": "warn", "missing": "missing"}.get(st, "missing")
        return f'<span class="badge {html.escape(cls)}">{html.escape(st)}</span>'

    def _level_badge(level: str) -> str:
        cls = {
            "closed_loop": "ok",
            "default_usable": "default",
            "basic_usable": "warn",
            "dead_end": "missing",
        }.get(level, "missing")
        return f'<span class="level {html.escape(cls)}">{html.escape(level or "unknown")}</span>'

    def _pill(label: str, on: bool) -> str:
        cls = "on" if on else "off"
        return f'<div class="pill {cls}">{html.escape(label)}</div>'

    def _runtime_line(it: dict) -> str:
        ev = it.get("evidence", {}) if isinstance(it.get("evidence", {}), dict) else {}
        parts = []
        for key in ("runtime_level", "runtime_backend", "runtime_version", "dispatch_capability"):
            if ev.get(key):
                parts.append(f"{key}: {ev.get(key)}")
        return " · ".join(parts)

    cards_html = ""
    for it in items:
        name = it.get("name", "N/A")
        purpose = it.get("purpose", it.get("source", ""))
        status = it.get("status", "unknown")
        level = it.get("status_label", "unknown")
        reason = it.get("degraded_reason", "")
        ev = json.dumps(it.get("evidence", {}), ensure_ascii=False, indent=2)
        reason_html = ('<div class="reason">' + html.escape(reason) + '</div>') if reason else ''
        runtime_html = ('<div class="runtime-line">' + html.escape(_runtime_line(it)) + '</div>') if _runtime_line(it) else ''
        cards_html += (
            '<article class="card">'
            '<div class="card-head"><div><div class="card-name">' + html.escape(name) + '</div>'
            '<div class="purpose">' + html.escape(purpose) + '</div></div>'
            '<div class="badge-stack">' + _badge(status) + _level_badge(level) + '</div></div>'
            '<div class="state-row">'
            + _pill("安装", bool(it.get("installed")))
            + _pill("配置", bool(it.get("configured")))
            + _pill("运行", bool(it.get("running")))
            + _pill("索引", bool(it.get("indexed")))
            + _pill("默认", bool(it.get("used_by_default")))
            + '</div>'
            + reason_html
            + runtime_html
            + '<details><summary>证据详情</summary>'
            '<pre class="code">' + html.escape(ev) + '</pre></details>'
            '</article>'
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solar Integrations Health</title>
<style>
:root{{--bg:#f7f0df;--ink:#211b12;--muted:#746858;--panel:#fffaf0;--line:rgba(33,27,18,.14);--accent:#1f6f5b;--ok:#1a7a4a;--warn:#c27a10;--err:#9f3a2f;--miss:#888;}}
body{{margin:0;background:radial-gradient(circle at top left,#fff8df,#efe4cf 42%,#d9e7df);color:var(--ink);font-family:"Avenir Next","Gill Sans",ui-sans-serif,sans-serif;}}
header,main{{max-width:1180px;margin:0 auto;padding:24px;}}
.hero{{border:1px solid var(--line);border-radius:30px;padding:28px;background:linear-gradient(135deg,rgba(255,250,240,.90),rgba(226,239,230,.70));box-shadow:0 24px 70px rgba(33,27,18,.10);}}
.eyebrow{{text-transform:uppercase;letter-spacing:.14em;color:var(--accent);font-weight:900;font-size:.78rem;}}
h1{{font-size:clamp(2rem,5vw,4rem);line-height:.9;margin:.2rem 0 .8rem;}}
.muted{{color:var(--muted);}}
.actions{{display:flex;flex-wrap:wrap;gap:.7rem;align-items:center;margin-top:.8rem;}}
.btn{{border:1px solid var(--line);border-radius:14px;padding:.7rem .95rem;background:rgba(255,255,255,.54);color:var(--ink);text-decoration:none;font-weight:900;cursor:pointer;}}
.btn.primary{{background:var(--ink);color:#fff8e8;}}
.summary-strip{{display:grid;grid-template-columns:repeat(4,minmax(100px,1fr));gap:.65rem;margin:1.2rem 0;}}
.s-tile{{border:1px solid var(--line);border-radius:18px;padding:.85rem;background:rgba(255,255,255,.42);}}
.s-tile .num{{font-size:1.8rem;font-weight:900;color:var(--accent);display:block;margin-top:.2rem;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:1rem;margin-top:1rem;}}
.card{{border:1px solid var(--line);border-radius:24px;padding:1rem;background:rgba(255,252,244,.66);box-shadow:0 12px 32px rgba(33,27,18,.06);}}
.card-head{{display:flex;gap:.7rem;justify-content:space-between;align-items:flex-start;}}
.card-name{{font-size:1.05rem;font-weight:900;line-height:1.2;}}
.badge{{display:inline-block;padding:3px 9px;border-radius:999px;font:800 .74rem ui-monospace,SFMono-Regular,Menlo,monospace;color:#fffaf0;}}
.badge.ok{{background:var(--ok);}}
.badge.warn{{background:var(--warn);}}
.badge.missing{{background:var(--miss);}}
.badge-stack{{display:flex;flex-direction:column;gap:.35rem;align-items:flex-end;}}
.level{{display:inline-block;padding:3px 9px;border-radius:999px;font:800 .68rem ui-monospace,SFMono-Regular,Menlo,monospace;border:1px solid var(--line);background:rgba(255,255,255,.54);color:var(--ink);}}
.level.ok{{background:#d1f5e0;color:var(--ok);border-color:#a3e8c0;}}
.level.default{{background:#dbeafe;color:#1f4f8f;border-color:#b9d4ff;}}
.level.warn{{background:#f7e6c8;color:var(--warn);border-color:#eed09d;}}
.level.missing{{background:#eee;color:var(--miss);}}
.state-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:.4rem;margin:.7rem 0;}}
.pill{{border-radius:10px;padding:.35rem .4rem;text-align:center;font:800 .7rem ui-monospace,SFMono-Regular,Menlo,monospace;border:1px solid var(--line);}}
.pill.on{{background:#d1f5e0;color:#1a7a4a;border-color:#a3e8c0;}}
.pill.off{{background:#f5e8d0;color:#888;border-color:#e8d8b8;}}
.reason{{font-size:.86rem;margin:.5rem 0;padding:.5rem .7rem;border-radius:12px;background:rgba(255,255,255,.38);border:1px solid var(--line);}}
.runtime-line{{font:800 .78rem ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--accent);background:rgba(31,111,91,.08);border:1px solid rgba(31,111,91,.18);border-radius:12px;padding:.55rem .7rem;margin:.55rem 0;overflow-wrap:anywhere;}}
.purpose{{color:var(--muted);font-size:.84rem;margin:.3rem 0 .6rem;}}
details summary{{cursor:pointer;color:var(--muted);font-size:.82rem;margin-top:.7rem;}}
pre.code{{background:#211b12;color:#f8efe0;border-radius:14px;padding:.8rem;font-size:.78rem;overflow:auto;white-space:pre-wrap;word-break:break-all;max-height:200px;}}
.refresh-ts{{color:var(--muted);font-size:.78rem;margin-top:.5rem;}}
</style>
</head>
<body>
<header>
  <div class="hero">
    <div class="eyebrow">Solar Harness · External Integrations</div>
    <h1>集成健康</h1>
    <p class="muted">七个外部开源/外部项目的六态健康检查：installed · configured · running · indexed · used_by_default · degraded_reason</p>
    <div class="actions">
      <a class="btn primary" href="/integrations-view">刷新</a>
      <a class="btn" href="/integrations" target="_blank">JSON 原始数据</a>
      <a class="btn" href="/">Solar Status</a>
    </div>
    <p class="refresh-ts">探测时间: {html.escape(generated_at)}</p>
  </div>
</header>
<main>
  <div class="summary-strip">
    <div class="s-tile"><div class="muted">TOTAL</div><span class="num">{html.escape(str(summary.get("total", len(items))))}</span></div>
    <div class="s-tile"><div class="muted">OK</div><span class="num" style="color:var(--ok)">{html.escape(str(summary.get("ok", 0)))}</span></div>
    <div class="s-tile"><div class="muted">WARN</div><span class="num" style="color:var(--warn)">{html.escape(str(summary.get("warn", 0)))}</span></div>
    <div class="s-tile"><div class="muted">MISSING</div><span class="num" style="color:var(--miss)">{html.escape(str(summary.get("missing", 0)))}</span></div>
  </div>
  <div class="grid">
{cards_html}
  </div>
</main>
</body>
</html>"""


def _external_integrations_payload(refresh: bool = False) -> dict:
    if not INTEGRATIONS_HEALTH.exists():
        return {"error": "external integrations probe missing", "path": str(INTEGRATIONS_HEALTH)}
    # The probe can run deep historical upload audits, but the dashboard must
    # remain responsive. Use cached/fast health by default; explicit refresh is
    # still local-only and bounded.
    cmd = ["python3", str(INTEGRATIONS_HEALTH), "--json", "--max-age", "120"]
    if refresh:
        cmd.append("--refresh")
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=12,
        )
    except subprocess.TimeoutExpired:
        return {"error": "external integrations probe timeout", "path": str(INTEGRATIONS_HEALTH)}
    if proc.returncode != 0:
        return {"error": "external integrations probe failed", "stderr": proc.stderr[-1000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "external integrations probe returned invalid json", "stdout": proc.stdout[-1000:]}


def _current_sprint() -> dict:
    """Return the current non-terminal sprint.

    A passed/finalized sprint is recent history, not current work. Older code
    fell back to the most recently modified status file, which made the
    dashboard show completed work as "Current Sprint" and hid the real state:
    no active queue to dispatch.
    """
    if not SPRINTS_DIR.exists():
        return {"sprint_id": "", "status": "idle", "phase": "no_sprints", "is_active": False}
    candidates = []
    for sf in SPRINTS_DIR.glob("sprint-*.status.json"):
        try:
            d = json.loads(sf.read_text())
            st = str(d.get("status", "")).lower()
            if st in _ACTIVE_SPRINT_STATUSES:
                d["_mtime"] = sf.stat().st_mtime
                candidates.append(d)
        except (json.JSONDecodeError, OSError):
            continue
    if not candidates:
        recent = {}
        all_sf = sorted(SPRINTS_DIR.glob("sprint-*.status.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for sf in all_sf:
            try:
                d = json.loads(sf.read_text())
                sid = d.get("id", d.get("sprint_id", sf.name.removesuffix(".status.json")))
                recent = {
                    "sprint_id": sid,
                    "status": d.get("status", ""),
                    "phase": d.get("phase", ""),
                    "handoff_to": d.get("handoff_to", ""),
                    "title": d.get("title", ""),
                    "priority": d.get("priority", ""),
                    "lane": d.get("lane", ""),
                    "description": _sprint_description(sid),
                }
                break
            except (json.JSONDecodeError, OSError):
                continue
        return {
            "sprint_id": "",
            "status": "idle",
            "phase": "no_active_sprint",
            "round": 0,
            "handoff_to": "",
            "title": "No active sprint",
            "priority": "",
            "lane": "",
            "description": "当前没有 active/queued/reviewing sprint；coordinator 没有可派发工作。",
            "is_active": False,
            "recent_completed": recent,
        }
    # pick highest-priority non-terminal
    order = {"active": 0, "reviewing": 1, "ready_for_review": 2, "queued": 3, "planning": 4, "approved": 5, "drafting": 6}
    candidates.sort(key=lambda d: (order.get(str(d.get("status", "")).lower(), 9), -float(d.get("_mtime", 0))))
    d = candidates[0]
    current_sid = d.get("id", d.get("sprint_id", ""))
    plan_summary = _execution_plan_summary(current_sid)
    understand_anything_summary = _current_understand_anything_summary(plan_summary)
    return {
        "sprint_id": d.get("id", d.get("sprint_id", "")),
        "status": d.get("status", ""),
        "phase": d.get("phase", ""),
        "round": d.get("round", 0),
        "handoff_to": d.get("handoff_to", ""),
        "title": d.get("title", ""),
        "priority": d.get("priority", ""),
        "lane": d.get("lane", ""),
        "description": _sprint_description(d.get("id", d.get("sprint_id", ""))),
        "is_active": True,
        "execution_plan_summary": plan_summary.get("summary", ""),
        "execution_plan_artifacts": plan_summary,
        "understand_anything_summary": understand_anything_summary,
    }


def _execution_plan_summary(sid: str) -> dict:
    sid = str(sid or "").strip()
    if not sid:
        return {"count": 0, "summary": "N/A", "items": []}
    items: list[dict] = []
    for physical_path in sorted(SPRINTS_DIR.glob(f"{sid}.*-physical-plan.json")):
        prefix = physical_path.name.removesuffix("-physical-plan.json")
        node_id = prefix.split(".", 1)[1] if "." in prefix else prefix
        capsule_path = SPRINTS_DIR / f"{sid}.{node_id}-capsule-plan.json"
        selected_operator_id = ""
        capability_capsule_id = ""
        selected_skills: list[str] = []
        execution_surface = ""
        skill_bridge_mode = ""
        skill_template_profile = ""
        skill_delivery_expectation = ""
        skill_specialization_family = ""
        knowledge_graph_path = ""
        understand_meta_path = ""
        understand_chunk_manifest_path = ""
        understand_resume_state_path = ""
        understand_chunks_total = 0
        understand_chunks_completed = 0
        understand_resumed = False
        try:
            physical_data = json.loads(physical_path.read_text(encoding="utf-8"))
            if isinstance(physical_data, dict):
                selected_operator_id = str(physical_data.get("selected_operator_id") or "")
                capability_capsule_id = str(physical_data.get("capability_capsule_id") or "")
        except Exception:
            selected_operator_id = ""
        try:
            if capsule_path.exists():
                capsule_data = json.loads(capsule_path.read_text(encoding="utf-8"))
                if isinstance(capsule_data, dict):
                    selected_skills = list(capsule_data.get("selected_skills") or [])
                    runtime_preferences = capsule_data.get("runtime_preferences") if isinstance(capsule_data.get("runtime_preferences"), dict) else {}
                    execution_surface = str(runtime_preferences.get("execution_surface") or "")
                    skill_bridge = capsule_data.get("skill_bridge") if isinstance(capsule_data.get("skill_bridge"), dict) else {}
                    skill_bridge_mode = str(skill_bridge.get("mode") or "")
                    skill_template_profile = str(skill_bridge.get("template_profile") or "")
                    skill_delivery_expectation = str(skill_bridge.get("delivery_expectation") or "")
                    skill_specialization_family = str(skill_bridge.get("specialization_family") or "")
        except Exception:
            pass
        operator_results_root = HARNESS_DIR / "run" / "operator-results"
        if operator_results_root.exists():
            for result_json in operator_results_root.glob("*/*/result.json"):
                try:
                    result_data = json.loads(result_json.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(result_data.get("sprint_id") or "") != sid or str(result_data.get("node_id") or "") != node_id:
                    continue
                result_dir = result_json.parent
                ua_result_path = result_dir / "understand-anything-result.json"
                if ua_result_path.exists():
                    try:
                        ua_result = json.loads(ua_result_path.read_text(encoding="utf-8"))
                    except Exception:
                        ua_result = {}
                    knowledge_graph_path = str(ua_result.get("knowledge_graph_path") or "")
                    dispatch_result = ua_result.get("dispatch_result") if isinstance(ua_result.get("dispatch_result"), dict) else {}
                    understand_meta_path = str(dispatch_result.get("meta_path") or "")
                    understand_chunk_manifest_path = str(dispatch_result.get("manifest_path") or "")
                    understand_resume_state_path = str(dispatch_result.get("resume_state_path") or "")
                    understand_chunks_total = int(dispatch_result.get("chunks_total") or 0)
                    understand_chunks_completed = int(dispatch_result.get("chunks_completed") or 0)
                    understand_resumed = bool(dispatch_result.get("resumed"))
                break
        items.append(
            {
                "node_id": node_id,
                "capability_capsule_id": capability_capsule_id,
                "selected_operator_id": selected_operator_id,
                "selected_skills": selected_skills,
                "execution_surface": execution_surface,
                "skill_bridge_mode": skill_bridge_mode,
                "skill_template_profile": skill_template_profile,
                "skill_delivery_expectation": skill_delivery_expectation,
                "skill_specialization_family": skill_specialization_family,
                "knowledge_graph_path": knowledge_graph_path,
                "understand_meta_path": understand_meta_path,
                "understand_chunk_manifest_path": understand_chunk_manifest_path,
                "understand_resume_state_path": understand_resume_state_path,
                "understand_chunks_total": understand_chunks_total,
                "understand_chunks_completed": understand_chunks_completed,
                "understand_resumed": understand_resumed,
                "physical_plan_ir": str(physical_path),
                "capsule_plan_ir": str(capsule_path) if capsule_path.exists() else "",
            }
        )
    summary = "N/A"
    if items:
        parts = []
        for item in items[:4]:
            part = f"{item['node_id']}->{item['selected_operator_id'] or 'unbound'}"
            if item.get("selected_skills"):
                family = str(item.get("skill_specialization_family") or "")
                surface = str(item.get("skill_template_profile") or "")
                skill0 = str((item.get("selected_skills") or [""])[0] or "")
                suffix = ""
                if surface or family:
                    suffix = f"/{surface.replace('_tooling', '').replace('_methodology', '')}:{family}" if family else f"/{surface}"
                if len(item["selected_skills"]) > 1:
                    part += f" · {skill0}{suffix} +{len(item['selected_skills']) - 1}"
                else:
                    part += f" · {skill0}{suffix}"
            elif item.get("knowledge_graph_path"):
                chunk_total = int(item.get("understand_chunks_total") or 0)
                part += f" · ua:{chunk_total}chunks"
            parts.append(part)
        summary = " · ".join(parts)
        if len(items) > 4:
            summary += f" · +{len(items) - 4}"
    return {"count": len(items), "summary": summary, "items": items}


def _current_understand_anything_summary(plan_summary: dict) -> dict:
    items = list(plan_summary.get("items") or [])
    for item in items:
        if not item.get("knowledge_graph_path"):
            continue
        return {
            "present": True,
            "node_id": str(item.get("node_id") or ""),
            "knowledge_graph_path": str(item.get("knowledge_graph_path") or ""),
            "meta_path": str(item.get("understand_meta_path") or ""),
            "chunk_manifest_path": str(item.get("understand_chunk_manifest_path") or ""),
            "resume_state_path": str(item.get("understand_resume_state_path") or ""),
            "chunks_total": int(item.get("understand_chunks_total") or 0),
            "chunks_completed": int(item.get("understand_chunks_completed") or 0),
            "resumed": bool(item.get("understand_resumed")),
            "summary": (
                f"{item.get('node_id') or 'N/A'} · "
                f"{int(item.get('understand_chunks_completed') or 0)}/"
                f"{int(item.get('understand_chunks_total') or 0)} chunks"
            ),
        }
    return {
        "present": False,
        "node_id": "",
        "knowledge_graph_path": "",
        "meta_path": "",
        "chunk_manifest_path": "",
        "resume_state_path": "",
        "chunks_total": 0,
        "chunks_completed": 0,
        "resumed": False,
        "summary": "N/A",
    }


def _first_paragraph_after_heading(text: str, heading_pattern: str) -> str:
    lines = text.splitlines()
    start = -1
    for idx, line in enumerate(lines):
        if re.match(heading_pattern, line.strip(), flags=re.IGNORECASE):
            start = idx + 1
            break
    if start < 0:
        return ""
    buf = []
    for line in lines[start:]:
        s = line.strip()
        if s.startswith("#") and buf:
            break
        if not s:
            if buf:
                break
            continue
        if s.startswith("**") or s.startswith("- "):
            continue
        buf.append(s)
    return " ".join(buf).strip()


def _clip_text(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _sprint_description(sid: str) -> str:
    if not sid:
        return ""
    for suffix in (".prd.md", ".product-brief.md", ".contract.md", ".plan.md"):
        path = SPRINTS_DIR / f"{sid}{suffix}"
        try:
            if not path.exists():
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        desc = (
            _first_paragraph_after_heading(text, r"^##\s*(背景|context)\b.*")
            or _first_paragraph_after_heading(text, r"^##\s*(用户问题|problem)\b.*")
            or _first_paragraph_after_heading(text, r"^##\s*(目标|goals?|intent)\b.*")
        )
        if desc:
            return _clip_text(desc)
    return ""


def _sprint_meta(sid: str) -> dict:
    if not sid:
        return {"sprint_id": "", "title": "", "status": "", "phase": "", "description": ""}
    status_path = SPRINTS_DIR / f"{sid}.status.json"
    meta = {
        "sprint_id": sid,
        "title": sid,
        "status": "",
        "phase": "",
        "priority": "",
        "lane": "",
        "handoff_to": "",
        "description": _sprint_description(sid),
    }
    try:
        if status_path.exists():
            d = json.loads(status_path.read_text())
            meta.update(
                {
                    "title": d.get("title") or sid,
                    "status": d.get("status", ""),
                    "phase": d.get("phase", ""),
                    "priority": d.get("priority", ""),
                    "lane": d.get("lane", ""),
                    "handoff_to": d.get("handoff_to", ""),
                }
            )
            if not meta["description"]:
                meta["description"] = _clip_text(" ".join(d.get("evidence", [])[:2]))
    except (json.JSONDecodeError, OSError):
        pass
    return meta


def _read_assignments() -> dict:
    """Return pane assignment map from current or legacy assignment files."""
    if PANE_ASSIGNMENTS.exists():
        out = {}
        try:
            for raw in PANE_ASSIGNMENTS.read_text().splitlines():
                raw = raw.strip()
                if not raw or "=" not in raw:
                    continue
                pane, rest = raw.split("=", 1)
                sid = rest.rsplit(":", 1)[0]
                if pane and sid:
                    out[pane] = sid
            return out
        except OSError:
            return {}
    if not PANE_ASSIGNMENTS_JSON.exists():
        return {}
    try:
        d = json.loads(PANE_ASSIGNMENTS_JSON.read_text())
        return {str(k): str(v) for k, v in d.items()}
    except (json.JSONDecodeError, OSError):
        return {}


def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_yaml_file(path: Path) -> dict:
    if not yaml or not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_yaml_file(path: Path, data: dict) -> None:
    if not yaml:
        raise RuntimeError("PyYAML unavailable")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def h(value) -> str:
    return html.escape(str(value or ""))


def _health_file_summary(path: Path) -> dict:
    data = _read_json_file(path)
    if not data:
        return {"ok": False, "status": "missing", "path": str(path)}
    return {
        "ok": bool(data.get("ok")),
        "status": data.get("status") or ("ok" if data.get("ok") else "warn"),
        "checked_at": data.get("checked_at") or data.get("generated_at") or "",
        "probes_passed": data.get("probes_passed"),
        "probes_failed": data.get("probes_failed"),
        "path": str(path),
    }


def _activation_proof_summary() -> dict:
    data = _read_json_file(CAPABILITY_ACTIVATION_PROOF)
    if not data:
        return {"ok": False, "status": "missing", "path": str(CAPABILITY_ACTIVATION_PROOF)}
    return {
        "ok": bool(data.get("ok")),
        "status": "ok" if data.get("ok") else "warn",
        "generated_at": data.get("generated_at", ""),
        "passed": data.get("passed"),
        "total": data.get("total"),
        "path": str(CAPABILITY_ACTIVATION_PROOF),
    }


def _skills_certification_summary() -> dict:
    cert = _read_json_file(SKILLS_CERTIFICATION)
    inventory = _read_json_file(SKILLS_INVENTORY)
    if not cert:
        return {"ok": False, "status": "missing", "path": str(SKILLS_CERTIFICATION)}
    readiness = cert.get("readiness_summary") or {}
    totals = inventory.get("totals") or {}
    return {
        "ok": bool(cert.get("ok")) or cert.get("overall_status") == "ok",
        "status": cert.get("overall_status") or ("ok" if cert.get("ok") else "warn"),
        "checked_at": cert.get("generated_at", ""),
        "effective": readiness.get("effective", 0),
        "executable": readiness.get("executable", 0),
        "broken": readiness.get("broken", 0),
        "total_skills": totals.get("total", totals.get("skills", 0)),
        "path": str(SKILLS_CERTIFICATION),
    }


def _capability_health_summary(runtime_interfaces=None) -> dict:
    """Project runtime capability evidence for UI and activation proof.

    This is a projection, not a new source of truth: model/knowledge health come
    from append-only probe artifacts, Mirage/QMD from the data-plane probe, and
    intent/skill status from activation/certification artifacts.
    """
    model = _health_file_summary(MODEL_DOCTOR_HEALTH)
    knowledge = _health_file_summary(KNOWLEDGE_PROBE_HEALTH)
    mirage = _mirage_status()
    qmd = mirage.get("qmd") if isinstance(mirage.get("qmd"), dict) else {}
    activation = _activation_proof_summary()
    skills = _skills_certification_summary()
    runtime_interfaces = runtime_interfaces or {}
    runtime_dims = runtime_interfaces.get("dimensions") if isinstance(runtime_interfaces.get("dimensions"), dict) else {}
    sandbox = runtime_dims.get("sandbox_runtime") if isinstance(runtime_dims.get("sandbox_runtime"), dict) else {}
    intent_ok = bool(activation.get("ok")) and (HARNESS_DIR / "lib" / "intent_engine_adapter.py").exists()
    qmd_ok = qmd.get("status") == "ok" or mirage.get("qmd_status") == "ok"
    mirage_ok = bool(mirage.get("enabled")) and qmd_ok
    sandbox_write_guard_violations = int(sandbox.get("write_guard_violations") or 0)
    sandbox_ok = (
        bool(sandbox.get("ok"))
        and bool(sandbox.get("workspace_removed"))
        and sandbox.get("execution_mode") == "argv"
        and bool(sandbox.get("write_guard_enabled"))
        and sandbox_write_guard_violations == 0
    )
    checks = {
        "model": {
            "status": "ok" if model.get("ok") else "warn",
            "label": "Model routing",
            "detail": f"{model.get('status', 'unknown')} {model.get('checked_at', '')}".strip(),
            "evidence": model.get("path", ""),
        },
        "knowledge": {
            "status": "ok" if knowledge.get("ok") else "warn",
            "label": "Knowledge",
            "detail": f"{knowledge.get('probes_passed', 0)}/{(knowledge.get('probes_passed') or 0) + (knowledge.get('probes_failed') or 0)} probes",
            "evidence": knowledge.get("path", ""),
        },
        "mirage_qmd": {
            "status": "ok" if mirage_ok else "warn",
            "label": "Mirage/QMD",
            "detail": f"qmd={qmd.get('status', mirage.get('qmd_status', 'unknown'))}",
            "evidence": str(HARNESS_DIR / "state" / "mirage" / "last-probe.json"),
        },
        "intent": {
            "status": "ok" if intent_ok else "warn",
            "label": "Intent",
            "detail": f"activation {activation.get('passed', 0)}/{activation.get('total', 0)}",
            "evidence": activation.get("path", ""),
        },
        "skills": {
            "status": "ok" if skills.get("ok") and int(skills.get("broken") or 0) == 0 else "warn",
            "label": "Skills",
            "detail": f"effective={skills.get('effective', 0)} executable={skills.get('executable', 0)} broken={skills.get('broken', 0)}",
            "evidence": skills.get("path", ""),
        },
        "sandbox": {
            "status": "ok" if sandbox_ok else "warn",
            "label": "Sandbox",
            "detail": sandbox.get("message", "runtime doctor unavailable"),
            "evidence": sandbox.get("evidence_file", ""),
            "workspace_removed": bool(sandbox.get("workspace_removed")),
            "execution_mode": sandbox.get("execution_mode", ""),
            "write_guard_enabled": bool(sandbox.get("write_guard_enabled")),
            "write_guard_violations": sandbox_write_guard_violations,
            "boundary": sandbox.get("boundary", "local process sandbox, not VM/container isolation"),
        },
    }
    ok = all(item.get("status") == "ok" for item in checks.values())
    return {
        "ok": ok,
        "status": "ok" if ok else "warn",
        "checks": checks,
        "updated_at": max(
            [str(model.get("checked_at") or ""), str(knowledge.get("checked_at") or ""), str(skills.get("checked_at") or ""), str(activation.get("generated_at") or "")]
        ),
    }


def _pane_info() -> list:
    """Return list of known pane assignments."""
    d = _read_assignments()
    return [{"pane": k, "sprint_id": v, "sprint": _sprint_meta(v)} for k, v in d.items()]


def _run_tmux(args: list, timeout: float = 0.8) -> str:
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip("\n")
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _runtime_from_tail(tail: str) -> str:
    """Classify pane runtime from current Claude Code prompt/footer.

    Scrollback often contains old "Bash/Write/Edit" lines after a task has
    already returned to the prompt. Treat the current prompt/footer as stronger
    evidence than historical activity text.
    """
    lines = tail.splitlines()
    footer_re = re.compile(r"⏵.*(auto|accept edits|edit|bypass permissions).*mode on|shift\+tab|esc to interrupt", re.I)
    footer_indexes = [idx for idx, line in enumerate(lines) if footer_re.search(line)]
    footer_at = footer_indexes[-1] if footer_indexes else len(lines)
    prompt_indexes = [idx for idx, line in enumerate(lines) if "❯" in line]
    for idx in reversed(prompt_indexes):
        if idx <= footer_at and footer_at - idx <= 8:
            next_nonempty = ""
            for line in lines[idx + 1:footer_at + 1]:
                if line.strip():
                    next_nonempty = line.strip()
                    break
            # Historical submitted prompts are separated from the current input
            # region by Claude Code's divider line. They must not be reported
            # as editable prompt residue.
            if next_nonempty.startswith("─"):
                continue
            current = lines[idx].split("❯", 1)[1].replace("\u00a0", " ").strip()
            if not current or current in {'Try "fix lint errors"', 'Try "summarize this codebase"'}:
                return "idle"
            return "prompt_residue"
    if footer_indexes:
        return "idle"
    active_re = re.compile(
        r"Generating|thinking\)|Reading|Bash|Write|Edit|Inferring|Hatching|"
        r"Whirlpooling|Enchanting|Meandering|Philosophising",
        re.IGNORECASE,
    )
    if active_re.search(tail):
        return "active"
    if "❯" in tail or "mode on" in tail:
        return "idle"
    return "unknown"


def _artifact_for_assignment(role: str, sid: str) -> dict:
    if not sid:
        return {"state": "N/A", "path": "", "mtime": ""}
    candidates = []
    if role == "PM":
        candidates = [SPRINTS_DIR / f"{sid}.prd.md", SPRINTS_DIR / f"{sid}.product-brief.md"]
    elif role == "Planner":
        candidates = [SPRINTS_DIR / f"{sid}.plan.md"]
    elif role == "Builder":
        candidates = [SPRINTS_DIR / f"{sid}.handoff.md"]
    elif role == "Evaluator":
        candidates = [SPRINTS_DIR / f"{sid}.eval.md"]
    else:
        candidates = sorted((SPRINTS_DIR / "obsidian-wiki-lab").glob(f"{role.lower().replace(' ', '-') }*handoff.md"))

    for path in candidates:
        try:
            if path.exists():
                return {
                    "state": "present",
                    "path": str(path),
                    "mtime": path.stat().st_mtime,
                }
        except OSError:
            continue
    return {"state": "missing", "path": str(candidates[0]) if candidates else "", "mtime": ""}


def _model_call_status(event_type: str, payload: dict) -> str:
    if event_type == "model_call_succeeded":
        return "ok"
    if event_type == "model_call_failed":
        return "error"
    if event_type == "model_call_requested":
        return "running"
    if event_type == "model_session_started":
        return "ready"
    if event_type == "model_session_ended":
        return "ended" if payload.get("exit_code") == 0 else "warn"
    return "unknown"


def _model_label_from_payload(payload: dict) -> str:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    flag = str(model.get("model_flag") or "").replace("--model", "").strip()
    auth = str(model.get("auth_source") or "").strip()
    persona = str(model.get("persona") or "").strip()
    parts = [part for part in [flag, auth, persona] if part]
    return " / ".join(parts)


def _model_runtime_detail_from_payload(payload: dict) -> dict:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    token_usage = payload.get("token_usage") if isinstance(payload.get("token_usage"), dict) else {}
    tokens = {**usage, **token_usage}
    return {
        "provider": str(model.get("auth_source") or payload.get("provider") or ""),
        "model_flag": str(model.get("model_flag") or ""),
        "base_url_host": str(model.get("base_url_host") or ""),
        "persona": str(model.get("persona") or ""),
        "claude_bin": str(model.get("claude_bin") or ""),
        "tokens": tokens,
        "operator_kernel": str(payload.get("operator_kernel") or payload.get("kernel") or ""),
    }


def _tail_jsonl_lines(path: Path, max_lines: int) -> list:
    try:
        with open(path, encoding="utf-8") as fh:
            return list(deque(fh, maxlen=max_lines))
    except OSError:
        return []


def _latest_model_call_for_pane(target: str, pane_id: str = "") -> dict:
    """Project the newest observable model-call boundary event for one pane.

    This is intentionally based on the append-only session logs, not tmux tail
    text.  It proves the runtime boundary we can observe: pane/model dispatch
    submission and pane process lifecycle. It does not claim private model
    reasoning visibility.
    """
    cache_key = f"{target}|{pane_id}"
    now = time.monotonic()
    cached = _MODEL_CALL_CACHE.get(cache_key)
    if cached and now - cached.get("ts", 0.0) <= _MODEL_CALL_CACHE_TTL_SECONDS:
        return dict(cached.get("value") or {})

    aliases = {target}
    if pane_id:
        aliases.add(pane_id)
    safe_pane_id = pane_id.replace("%", "_") if pane_id else ""
    candidate_files = []
    try:
        candidate_files = sorted(
            SESSIONS_DIR.glob("*/events.jsonl"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )[:_MODEL_CALL_SESSION_FILE_LIMIT]
    except Exception:
        candidate_files = []

    newest = None
    newest_key = ("", -1)
    timed_out = False
    for path in candidate_files:
        if time.monotonic() - now > _MODEL_CALL_SCAN_BUDGET_SECONDS:
            timed_out = True
            break
        try:
            for raw in _tail_jsonl_lines(path, _MODEL_CALL_FILE_TAIL_LINES):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                ev_type = ev.get("type")
                if ev_type not in _MODEL_EVENT_TYPES:
                    continue
                payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
                ev_pane = str(payload.get("pane") or "")
                session_id = str(ev.get("session_id") or "")
                if ev_pane not in aliases and session_id != f"pane-{safe_pane_id}":
                    continue
                key = (str(ev.get("ts") or ""), int(ev.get("seq") or 0))
                if key >= newest_key:
                    newest_key = key
                    newest = ev
        except OSError:
            continue

    if not newest:
        value = {
            "status": "unknown",
            "event_type": "",
            "ts": "",
            "session_id": "",
            "dispatch_id": "",
            "model": "",
            "error": "",
            "instruction_preview": "",
            "private_reasoning_visible": False,
            "observability_boundary": "bounded_session_tail_scan_timeout" if timed_out else "bounded_session_tail_scan",
        }
        _MODEL_CALL_CACHE[cache_key] = {"ts": now, "value": value}
        return dict(value)

    payload = newest.get("payload") if isinstance(newest.get("payload"), dict) else {}
    value = {
        "status": _model_call_status(str(newest.get("type") or ""), payload),
        "event_type": newest.get("type") or "",
        "ts": newest.get("ts") or "",
        "session_id": newest.get("session_id") or "",
        "sprint_id": newest.get("sprint_id") or "",
        "dispatch_id": payload.get("dispatch_id") or newest.get("activity_id") or "",
        "model": _model_label_from_payload(payload),
        "error": payload.get("error") or "",
        "instruction_preview": payload.get("instruction_preview") or "",
        "private_reasoning_visible": bool(payload.get("private_reasoning_visible", False)),
        "observability_boundary": payload.get("observability_boundary") or ("bounded_session_tail_scan_timeout" if timed_out else "bounded_session_tail_scan"),
        **_model_runtime_detail_from_payload(payload),
    }
    _MODEL_CALL_CACHE[cache_key] = {"ts": now, "value": value}
    return dict(value)


def _skipped_model_call_status() -> dict:
    return {
        "status": "unknown",
        "event_type": "",
        "ts": "",
        "session_id": "",
        "dispatch_id": "",
        "model": "",
        "error": "",
        "instruction_preview": "",
        "private_reasoning_visible": False,
        "observability_boundary": "status_fast_path_model_call_skipped",
    }


def _pane_model_call_detail(target: str, pane_id: str = "") -> dict:
    """Lazy, heavier model-call projection for a pane. Not used by /status."""
    target = str(target or "").strip()
    pane_id = str(pane_id or "").strip()
    if not target:
        return {"ok": False, "status": "error", "error": "target is required"}
    if not pane_id:
        pane_id = _run_tmux(["display-message", "-p", "-t", target, "#{pane_id}"], timeout=0.8).strip()
    call = _latest_model_call_for_pane(target, pane_id)
    pane_meta = {}
    try:
        for pane in _multi_task_panes_info():
            if pane.get("pane") == target or (pane_id and str(pane.get("pane_id") or "") == pane_id):
                pane_meta = {
                    "model": pane.get("model") or "",
                    "backend": pane.get("backend") or "",
                    "operator_type": pane.get("operator_type") or "",
                    "profile": pane.get("profile") or "",
                    "role": pane.get("role") or "",
                    "status": pane.get("status") or "",
                    "task": pane.get("task") or {},
                    "lease": pane.get("lease") or {},
                }
                break
    except Exception:
        pane_meta = {}
    return {
        "ok": True,
        "target": target,
        "pane_id": pane_id,
        "model_call": call,
        "pane": pane_meta,
        "note": "lazy endpoint: bounded session-log scan; private model reasoning is not visible",
    }


def _pane_snapshot(target: str, role: str, assignment: str = "", capability_health=None, include_model_call: bool = True) -> dict:
    assignment_meta = _sprint_meta(assignment) if assignment else {}
    pane_id = _run_tmux(["display-message", "-p", "-t", target, "#{pane_id}"])
    health = capability_health or _capability_health_summary()
    if not pane_id:
        return {
            "target": target,
            "role": role,
            "runtime_state": "missing",
            "assignment": assignment or "",
            "assignment_meta": assignment_meta,
            "artifact": _artifact_for_assignment(role, assignment),
            "title": "",
            "model_call": _latest_model_call_for_pane(target, pane_id) if include_model_call else _skipped_model_call_status(),
            "capability_health": health,
        }
    title = _run_tmux(["display-message", "-p", "-t", target, "#{pane_title}"])
    tail = _run_tmux(["capture-pane", "-t", target, "-p", "-S", "-8"], timeout=1.0)
    return {
        "target": target,
        "role": role,
        "runtime_state": _runtime_from_tail(tail),
        "assignment": assignment or "",
        "assignment_meta": assignment_meta,
        "artifact": _artifact_for_assignment(role, assignment),
        "title": title,
        "model_call": _latest_model_call_for_pane(target, pane_id) if include_model_call else _skipped_model_call_status(),
        "capability_health": health,
    }


def _main_screen(capability_health=None, include_model_call: bool = True) -> dict:
    assignments = _read_assignments()
    roles = ["PM", "Planner", "Builder", "Evaluator"]
    panes = []
    for idx, role in enumerate(roles):
        target = f"solar-harness:0.{idx}"
        panes.append(_pane_snapshot(target, role, assignments.get(target, ""), capability_health=capability_health, include_model_call=include_model_call))
    return {
        "note": "runtime_state, assignment, and artifact are separate; pane output alone is not proof of progress.",
        "panes": panes,
    }


def _lab_screen(capability_health=None, include_model_call: bool = True) -> dict:
    roles = ["lab-builder-1", "lab-builder-2", "lab-builder-3", "lab-builder-4"]
    lab_dir = SPRINTS_DIR / "obsidian-wiki-lab"
    panes = []
    for idx, role in enumerate(roles):
        target = f"solar-harness-lab:0.{idx}"
        snap = _pane_snapshot(target, role, "", capability_health=capability_health, include_model_call=include_model_call)
        latest = None
        if lab_dir.exists():
            matches = sorted(lab_dir.glob(f"{role}*handoff.md"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
            latest = matches[-1] if matches else None
        if latest:
            snap["artifact"] = {
                "state": "present",
                "path": str(latest),
                "mtime": latest.stat().st_mtime,
            }
        panes.append(snap)
    return {
        "note": "artifact != runtime: handoff files prove delivery; pane state proves current activity.",
        "panes": panes,
    }


def _kpi() -> dict:
    """Compute KPI from sprint status files."""
    total = passed = failed = 0
    for sf in SPRINTS_DIR.glob("sprint-*.status.json"):
        try:
            d = json.loads(sf.read_text())
            total += 1
            st = d.get("status", "")
            if st in ("passed", "finalized"):
                passed += 1
            elif st in ("failed", "failed_review"):
                failed += 1
        except (json.JSONDecodeError, OSError):
            continue
    return {
        "sprints_total": total,
        "sprints_passed": passed,
        "sprints_failed": failed,
        "pass_rate": round(passed / total, 2) if total > 0 else 0.0,
    }


def _mirage_status() -> dict:
    """Return mirage VFS status block. Reads last-probe.json cache; never raises."""
    probe_path = HARNESS_DIR / "state" / "mirage" / "last-probe.json"
    empty = {"enabled": False, "mounts": [], "drive": {"status": "unknown"}, "qmd": {"status": "unknown"}, "last_probe_at": None}
    if not probe_path.exists():
        return empty
    try:
        import time as _time
        probe = json.loads(probe_path.read_text())
        # TTL: treat stale (>120s) probes as degraded but still return them
        probe_ts = probe.get("probed_at", "")
        stale = False
        if probe_ts:
            try:
                import datetime as _dt
                age = (_dt.datetime.utcnow() - _dt.datetime.fromisoformat(probe_ts.replace("Z", ""))).total_seconds()
                stale = age > 120
            except Exception:
                pass
        drive = probe.get("drive", {})
        qmd = probe.get("qmd", {})
        return {
            "enabled": probe.get("enabled", False),
            "workspace_id": probe.get("workspace_id", ""),
            "mounts": probe.get("mounts", []),
            "drive": drive,
            "drive_status": drive.get("status", "unknown") if isinstance(drive, dict) else "unknown",
            "qmd": qmd,
            "qmd_indexed": qmd.get("indexed", 0) if isinstance(qmd, dict) else 0,
            "last_probe_at": probe_ts,
            "stale": stale,
            "config": probe.get("config", ""),
        }
    except (json.JSONDecodeError, OSError, Exception):
        return empty


def _pane_capability_summary() -> dict:
    """Return capability summary for all known panes. Never raises — degrades gracefully."""
    persona_script = HARNESS_DIR / "lib" / "persona-config.sh"
    skills_py = HARNESS_DIR / "lib" / "solar_skills.py"

    panes_out = []
    if persona_script.exists():
        known_panes = ["lab-builder", "builder", "evaluator", "planner", "monitor"]
        for pane in known_panes:
            try:
                result = subprocess.run(
                    ["bash", str(persona_script), "--print-config", pane],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    cfg: dict = {}
                    for line in result.stdout.splitlines():
                        if "=" in line:
                            k, _, v = line.partition("=")
                            cfg[k.strip()] = v.strip("'\"")
                    extra_flags = cfg.get("EXTRA_FLAGS", "")
                    mcp_mode = "STRICT" if "--strict-mcp-config" in extra_flags else "DEFAULT"
                    kb_context = mcp_mode == "DEFAULT"
                    skills_accessible = kb_context
                    panes_out.append({
                        "pane": pane,
                        "model": cfg.get("MODEL_FLAG", "").replace("--model ", ""),
                        "auth_source": cfg.get("AUTH_SOURCE", "unknown"),
                        "mcp_mode": mcp_mode,
                        "kb_context": kb_context,
                        "skills_accessible": skills_accessible,
                    })
            except Exception:
                pass

    # Skills inventory counts from cache
    skills_inventory: dict = {}
    inventory_cache = HARNESS_DIR / "state" / "skills-inventory.json"
    if inventory_cache.exists():
        try:
            skills_inventory = json.loads(inventory_cache.read_text())
        except Exception:
            pass
    elif skills_py.exists():
        try:
            r = subprocess.run(
                ["python3", str(skills_py), "inventory", "--json"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                skills_inventory = json.loads(r.stdout)
        except Exception:
            pass

    return {
        "panes": panes_out,
        "skills": skills_inventory.get("totals", {}),
        "overall": {
            "total_panes": len(panes_out),
            "strict_mcp_panes": sum(1 for p in panes_out if p["mcp_mode"] == "STRICT"),
            "default_mcp_panes": sum(1 for p in panes_out if p["mcp_mode"] == "DEFAULT"),
            "status": "ok" if panes_out else "no_panes_configured",
        },
    }


def _evolution_status() -> dict:
    """Return evolution scorecards/experiments from state DB. Fail-open for UI."""
    engine = HARNESS_DIR / "lib" / "evolution_engine.py"
    if not engine.exists():
        return {"ok": False, "reason": "evolution_engine_missing", "scorecards": [], "experiments": []}
    try:
        proc = subprocess.run(
            ["python3", str(engine), "status", "--json"],
            capture_output=True,
            text=True,
            timeout=6,
        )
        if proc.returncode != 0:
            return {"ok": False, "reason": "evolution_status_failed", "stderr": proc.stderr[-500:]}
        return json.loads(proc.stdout)
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__, "scorecards": [], "experiments": []}


def _obsidian_wiki_readiness() -> dict:
    """Return obsidian_wiki readiness block. Never raises — degrades to ready=false."""
    integration = HARNESS_DIR / "integrations" / "obsidian-wiki.sh"
    harness_bin = HARNESS_DIR / "solar-harness.sh"

    # Integration not installed yet
    if not integration.exists() and not harness_bin.exists():
        return {
            "ready": False,
            "configured": False,
            "vault_path": "",
            "issues": ["integration not installed"],
        }

    try:
        result = subprocess.run(
            ["bash", str(integration), "status", "--json"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {
                "ready": False,
                "configured": False,
                "vault_path": "",
                "issues": ["status check failed (exit {})".format(result.returncode)],
            }
        data = json.loads(result.stdout)
        configured = data.get("configured", False)
        vault_path = data.get("vault_path", "")
        skills = data.get("skills_installed", {})
        issues = []
        if not configured:
            issues.append("wiki not configured")
        if vault_path and not Path(vault_path).exists():
            issues.append("vault path missing: {}".format(vault_path))
        missing_skills = [k for k, v in skills.items() if not v]
        if missing_skills:
            issues.append("skills not installed: {}".format(", ".join(missing_skills)))
        return {
            "ready": configured and len(issues) == 0,
            "configured": configured,
            "vault_path": vault_path,
            "issues": issues,
        }
    except subprocess.TimeoutExpired:
        return {"ready": False, "configured": False, "vault_path": "", "issues": ["status check timeout"]}
    except (json.JSONDecodeError, OSError, Exception) as exc:
        return {"ready": False, "configured": False, "vault_path": "", "issues": [str(exc)]}


def _solar_kb_status() -> dict:
    """Return solar KB (obsidian_vault_index) status. Never raises."""
    empty = {"indexed_count": 0, "last_indexed_at": None, "ok": False}
    db_path = Path(os.environ.get("SOLAR_DB", str(Path.home() / ".solar" / "solar.db")))
    if not db_path.exists():
        return {**empty, "error": "solar.db not found"}
    try:
        with sqlite3.connect(str(db_path), timeout=0.3) as conn:
            conn.execute("PRAGMA query_only=1")
            row = conn.execute(
                "SELECT COUNT(*), MAX(indexed_at) FROM obsidian_vault_index WHERE deleted_at IS NULL"
            ).fetchone()
            cnt, last_at = (row[0] or 0), (row[1] or None)
            return {"indexed_count": cnt, "last_indexed_at": last_at, "ok": cnt > 0}
    except sqlite3.OperationalError:
        return {**empty, "error": "obsidian_vault_index table not found"}
    except Exception as exc:
        return {**empty, "error": str(exc)}


def _tech_hotspot_db_path() -> Path:
    env_path = os.environ.get("TECH_HOTSPOT_RADAR_DB") or os.environ.get("SOLAR_TECH_HOTSPOT_RADAR_DB")
    if env_path:
        return Path(env_path).expanduser()
    if TECH_HOTSPOT_CONFIG.exists() and yaml is not None:
        try:
            data = yaml.safe_load(TECH_HOTSPOT_CONFIG.read_text(encoding="utf-8")) or {}
            db_path = ((data.get("output") or {}).get("database") or "").strip()
            if db_path:
                return Path(db_path).expanduser()
        except Exception:
            pass
    return HARNESS_DIR / "state" / "tech-hotspot-radar" / "tech-hotspot-radar.sqlite"


def _safe_json_obj(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _tech_hotspot_reasoning_policy_summary(limit: int = 8) -> dict:
    """Return recent reasoning packet policy routes for the dashboard. Never raises."""
    db_path = _tech_hotspot_db_path()
    empty = {
        "status": "missing",
        "ok": False,
        "db_path": str(db_path),
        "total_packets": 0,
        "items": [],
        "route_counts": {},
        "premium_allowed": 0,
        "embedding_unchanged": 0,
    }
    if not db_path.exists():
        return {**empty, "error": "tech-hotspot-radar database not found"}
    try:
        with sqlite3.connect(str(db_path), timeout=0.3) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=1")
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reasoning_packets'"
            ).fetchone()
            if not exists:
                return {**empty, "status": "warn", "error": "reasoning_packets table not found"}
            columns = {row[1] for row in conn.execute("PRAGMA table_info(reasoning_packets)").fetchall()}
            required = {"model_policy_json", "premium_escalation_json", "embedding_policy_json"}
            missing_columns = sorted(required - columns)
            total = conn.execute("SELECT COUNT(*) FROM reasoning_packets").fetchone()[0] or 0
            select_policy = "model_policy_json" if "model_policy_json" in columns else "'{}' AS model_policy_json"
            select_premium = "premium_escalation_json" if "premium_escalation_json" in columns else "'{}' AS premium_escalation_json"
            select_embedding = "embedding_policy_json" if "embedding_policy_json" in columns else "'{}' AS embedding_policy_json"
            rows = conn.execute(
                "SELECT packet_id, packet_type, evidence_atom_count, token_budget, created_at, "
                f"{select_policy}, {select_premium}, {select_embedding} "
                "FROM reasoning_packets ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            items = []
            route_counts: dict[str, int] = {}
            premium_allowed = 0
            embedding_unchanged = 0
            for row in rows:
                model_policy = _safe_json_obj(row["model_policy_json"])
                premium = _safe_json_obj(row["premium_escalation_json"])
                embedding = _safe_json_obj(row["embedding_policy_json"])
                route = str(model_policy.get("route") or "unknown")
                route_counts[route] = route_counts.get(route, 0) + 1
                if premium.get("allowed") is True:
                    premium_allowed += 1
                if embedding.get("route") == "embedding_unchanged":
                    embedding_unchanged += 1
                items.append({
                    "packet_id": row["packet_id"],
                    "packet_type": row["packet_type"],
                    "created_at": row["created_at"],
                    "evidence_atom_count": row["evidence_atom_count"],
                    "token_budget": row["token_budget"],
                    "route": route,
                    "default_model_family": model_policy.get("default_model_family") or "N/A",
                    "premium_allowed": bool(premium.get("allowed")),
                    "premium_reason": premium.get("reason") or "N/A",
                    "embedding_route": embedding.get("route") or "N/A",
                })
            status = "warn" if missing_columns else "ok"
            return {
                **empty,
                "status": status,
                "ok": not missing_columns,
                "total_packets": total,
                "items": items,
                "route_counts": route_counts,
                "premium_allowed": premium_allowed,
                "embedding_unchanged": embedding_unchanged,
                "missing_columns": missing_columns,
            }
    except sqlite3.OperationalError as exc:
        return {**empty, "status": "warn", "error": str(exc)}
    except Exception as exc:
        return {**empty, "status": "error", "error": str(exc)}


def _obsidian_sync_status() -> dict:
    """Return Obsidian→Solar sync status: pending raw queue + last sync manifest. Never raises."""
    vault_path = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Knowledge")))
    raw_dir = HARNESS_DIR / "vendor" / "obsidian-wiki" / "_raw" / "solar-db-export"
    manifest_path = HARNESS_DIR / "state" / "knowledge-manifest.json"
    try:
        pending_raw = len(list(raw_dir.glob("*.json"))) if raw_dir.exists() else 0
    except Exception:
        pending_raw = 0
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass
    return {
        "vault_path": str(vault_path),
        "vault_exists": vault_path.exists(),
        "pending_raw_export": pending_raw,
        "last_sync_at": manifest.get("last_sync_at") or manifest.get("generated_at"),
        "ok": vault_path.exists(),
    }


def _apple_notes_ingest_status() -> dict:
    """Return Apple Notes ingest status. Never raises."""
    manifest_path = HARNESS_DIR / "state" / "apple-notes-ingest" / "manifest.json"
    config_path = HARNESS_DIR / "config" / "apple-notes-ingest.json"
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.solar.apple-notes-ingest.plist"
    cfg: dict = {}
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
        except Exception:
            pass
    manifest: dict = {"notes": {}}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass
    notes = manifest.get("notes", {})
    exported = sum(1 for n in notes.values() if n.get("ingest_status") == "exported")
    dispatched = sum(1 for n in notes.values() if n.get("ingest_status") == "dispatched")
    last_run_at = manifest.get("last_scan_at")
    scheduler_loaded = False
    if plist_path.exists():
        try:
            import subprocess as _sp
            r = _sp.run(["launchctl", "list", "com.solar.apple-notes-ingest"],
                        capture_output=True, timeout=3)
            scheduler_loaded = r.returncode == 0
        except Exception:
            pass
    return {
        "enabled": manifest_path.exists(),
        "interval_seconds": cfg.get("interval_seconds", 7200),
        "last_run_at": last_run_at,
        "last_success_at": last_run_at,
        "last_error": None,
        "notes_seen": len(notes),
        "notes_exported": exported,
        "notes_skipped": len(notes) - exported - dispatched,
        "dispatch_created": dispatched,
        "scheduler_loaded": scheduler_loaded,
        "ok": manifest_path.exists(),
    }


def _human_search_waiting_status(limit: int = 20) -> dict:
    """Project DeepResearch human-search DAG waits into /status."""
    routes_path = HARNESS_DIR / "status-server" / "research_routes.py"
    if not routes_path.exists():
        return {
            "ok": False,
            "status": "error",
            "count": 0,
            "items": [],
            "errors": [{"error": "research_routes.py missing", "path": str(routes_path)}],
        }
    try:
        spec = importlib.util.spec_from_file_location("solar_research_routes_status", str(routes_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load research_routes.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        data = mod.discover_human_search_waiting(SPRINTS_DIR, "", limit=limit)
        return data if isinstance(data, dict) else {"ok": False, "status": "error", "count": 0, "items": []}
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "count": 0,
            "items": [],
            "errors": [{"error": f"{type(exc).__name__}: {exc}"}],
        }


def _research_status_summary(limit: int = 5) -> dict:
    """Project latest DeepResearch eval/report artifacts into /status."""
    routes_path = HARNESS_DIR / "status-server" / "research_routes.py"
    if not routes_path.exists():
        return {"ok": False, "status": "error", "runs": [], "errors": ["research_routes.py missing"]}
    try:
        def load_json(path: Path) -> dict:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

        def metric_int(metrics: dict, *keys: str):
            for key in keys:
                if key not in metrics:
                    continue
                try:
                    return int(metrics.get(key) or 0)
                except Exception:
                    continue
            return None

        def fallback_level(metrics: dict):
            usage = metrics.get("usage_source") or metrics.get("token_usage_source") or ""
            estimated = metrics.get("estimated")
            if estimated is None:
                estimated = metrics.get("token_usage_is_estimated", False)
            reason = metrics.get("fallback_reason") or ""
            if usage == "provider_usage_ledger" and not estimated:
                return "L1"
            if usage == "hybrid":
                return "L2"
            if usage == "estimated" or str(usage).startswith("estimated_"):
                return "L3" if reason in ("cli_no_usage", "cli_rate_limit") else "L4"
            return None

        def first_markdown_heading(path: Path) -> str:
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:80]:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        return stripped.lstrip("#").strip()
            except Exception:
                return ""
            return ""

        def title_from_dir(path: Path) -> str:
            name = path.name
            name = re.sub(r"^deepresearch[-_]*", "", name, flags=re.IGNORECASE)
            name = re.sub(r"[-_]20\d{6}T\d{6}[-+]\d{4}$", "", name)
            name = re.sub(r"[-_]20\d{6}$", "", name)
            name = re.sub(r"[-_]20\d{4}$", "", name)
            return " ".join(part for part in re.split(r"[-_]+", name) if part).strip()

        def local_user_path(path: str | Path | None, fallback: Path) -> Path:
            candidate = Path(str(path or fallback)).expanduser()
            if candidate.exists():
                return candidate
            parts = candidate.parts
            home = Path.home()
            if len(parts) >= 4 and parts[0] == "/" and parts[1] == "Users" and parts[2] != home.name:
                rewritten = home.joinpath(*parts[3:])
                if rewritten.exists():
                    return rewritten
            return candidate

        def run_from_eval(ef: Path) -> dict:
            data = load_json(ef)
            output_dir = local_user_path(data.get("output_dir"), ef.parent)
            final_md = local_user_path(data.get("final_md"), output_dir / "final.md")
            metrics = data.get("execution_metrics") if isinstance(data.get("execution_metrics"), dict) else {}
            if not metrics:
                metrics_path = output_dir / "research_execution_metrics.json"
                metrics = load_json(metrics_path) if metrics_path.exists() else {}
            usage_source = metrics.get("usage_source") or metrics.get("token_usage_source")
            estimated = metrics.get("estimated")
            if estimated is None and metrics:
                estimated = bool(metrics.get("token_usage_is_estimated", False))
            run_id = str(data.get("run_id") or ef.name.split("-research_eval", 1)[0])
            task_title = (
                str(data.get("title") or data.get("task_title") or data.get("topic") or "").strip()
                or first_markdown_heading(final_md)
                or title_from_dir(output_dir)
                or ef.name.split("-research_eval", 1)[0]
            )
            task_description = title_from_dir(output_dir) or str(output_dir.name)
            return {
                "run_id": run_id,
                "short_run_id": run_id[:10],
                "sid": ef.name.split("-research_eval", 1)[0],
                "task_title": task_title,
                "task_description": task_description,
                "status": str(data.get("status") or "unknown"),
                "source_count": data.get("source_count", 0),
                "evidence_count": data.get("evidence_count", 0),
                "claim_count": data.get("claim_count", 0),
                "citation_accuracy": data.get("citation_accuracy", 0.0),
                "report_ast_sections": data.get("section_count", 0),
                "word_count": metric_int(metrics, "word_count", "document_word_count"),
                "total_tokens": metric_int(metrics, "total_tokens", "total_token_consumption"),
                "usage_source": usage_source,
                "estimated": estimated,
                "state": metrics.get("state", "unknown") if metrics else "unknown",
                "fallback_level": fallback_level(metrics),
                "artifacts": {
                    "eval_json": str(ef),
                    "output_dir": str(output_dir),
                    "final_md": str(final_md),
                    "report_ast": str(output_dir / "report_ast.json"),
                    "bibliography": str(output_dir / "final.bibliography.json"),
                },
                "artifact_exists": {
                    "eval_json": ef.exists(),
                    "output_dir": output_dir.exists(),
                    "final_md": final_md.exists(),
                    "report_ast": (output_dir / "report_ast.json").exists(),
                    "bibliography": (output_dir / "final.bibliography.json").exists(),
                },
            }

        spec = importlib.util.spec_from_file_location("solar_research_routes_summary", str(routes_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load research_routes.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        eval_files = sorted(
            list(SPRINTS_DIR.glob("*research_eval*.json")) + list(REPORTS_DIR.glob("*/*research_eval*.json")),
            key=lambda p: p.stat().st_mtime,
        )
        filtered_eval_files = []
        for ef in eval_files:
            data = load_json(ef)
            gate_override = data.get("gate_override") if isinstance(data.get("gate_override"), dict) else {}
            if gate_override.get("reason") == "audit_node_no_research_output":
                continue
            if not data.get("status") and not data.get("run_id") and not data.get("source_count"):
                continue
            filtered_eval_files.append(ef)
        runs = [run_from_eval(ef) for ef in filtered_eval_files[-limit:]]
        gate_items = mod.discover_quality_gates(SPRINTS_DIR, "", limit=limit * 4).get("items") or []
        gates = [
            gate
            for gate in gate_items
            if "deepresearch" in str(gate.get("sprint_id") or gate.get("graph_path") or "").lower()
        ][-limit:]
        blocking_gates = [
            gate for gate in gates[-limit:]
            if gate.get("status") == "failed"
            or (gate.get("status") == "missing" and gate.get("node_status") not in {"passed", "skipped", "cancelled"})
        ]
        status = "idle"
        if runs or gates:
            status = "ok" if all(r.get("status") == "passed" for r in runs[-limit:]) and not blocking_gates else "warn"
        return {
            "ok": status == "ok" or not runs,
            "status": status,
            "count": len(runs),
            "runs": runs[-limit:],
            "quality_gates": gates[-limit:],
        }
    except Exception as exc:
        return {"ok": False, "status": "error", "runs": [], "errors": [f"{type(exc).__name__}: {exc}"]}


def _autoresearch_impact_summary(limit: int = 12) -> dict:
    """Summarize pane-optimizer telemetry recorded in sprint status artifacts."""
    if not SPRINTS_DIR.exists():
        return {"ok": True, "status": "idle", "count": 0, "items": []}
    items = []
    try:
        status_files = sorted(
            SPRINTS_DIR.glob("sprint-*.status.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for sf in status_files:
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            artifacts = data.get("artifacts")
            if not isinstance(artifacts, dict):
                continue
            opt = artifacts.get("autoresearch_optimizer")
            if not isinstance(opt, dict):
                continue
            telemetry = opt.get("telemetry") if isinstance(opt.get("telemetry"), dict) else {}
            metrics = opt.get("quality_metrics") if isinstance(opt.get("quality_metrics"), dict) else {}
            sid = str(data.get("id") or data.get("sprint_id") or opt.get("sid") or sf.name.removesuffix(".status.json"))
            task_description = (
                str(data.get("title") or "").strip()
                or _sprint_description(sid)
                or sid
            )
            item = {
                "sid": sid,
                "task_description": task_description,
                "status": data.get("status", ""),
                "phase": data.get("phase", ""),
                "role": opt.get("canonical_role") or opt.get("role") or "",
                "trigger_level": opt.get("trigger_level", "advisory"),
                "recommended": bool(opt.get("recommended")),
                "recorded_at": opt.get("recorded_at", ""),
                "eval_verdict": telemetry.get("eval_verdict", ""),
                "round": telemetry.get("round", 0),
                "failed_conditions": telemetry.get("failed_conditions") if isinstance(telemetry.get("failed_conditions"), list) else [],
                "error_count": telemetry.get("error_count", 0),
                "warning_count": telemetry.get("warning_count", 0),
                "expected_effect": metrics.get("expected_effect") if isinstance(metrics.get("expected_effect"), list) else [],
                "must_measure": metrics.get("must_measure") if isinstance(metrics.get("must_measure"), list) else [],
                "reasons": opt.get("reasons") if isinstance(opt.get("reasons"), list) else [],
            }
            items.append(item)
            if len(items) >= limit:
                break
        terminal_pass = {"passed", "done", "eval_pass", "finalized", "eval_passed"}
        failing_statuses = {"failed", "failed_review", "needs_human_review", "blocked"}
        strong_count = sum(1 for item in items if item.get("trigger_level") == "strong")
        recommended_count = sum(1 for item in items if item.get("recommended"))
        fail_verdict_count = sum(1 for item in items if str(item.get("eval_verdict", "")).upper() in {"FAIL", "FAILED", "ERROR", "NOT_READY", "NOT READY"})
        pass_after_trigger = sum(1 for item in items if str(item.get("status", "")).lower() in terminal_pass)
        still_failing = sum(1 for item in items if str(item.get("status", "")).lower() in failing_statuses or str(item.get("eval_verdict", "")).upper() in {"FAIL", "FAILED", "ERROR", "NOT_READY", "NOT READY"})
        fail_recurrence = sum(1 for item in items if item.get("trigger_level") == "strong" and str(item.get("eval_verdict", "")).upper() in {"FAIL", "FAILED", "ERROR", "NOT_READY", "NOT READY"} and str(item.get("status", "")).lower() not in terminal_pass)
        rounds = []
        for item in items:
            try:
                rounds.append(int(item.get("round") or 0))
            except Exception:
                continue
        avg_round = round(sum(rounds) / len(rounds), 2) if rounds else 0
        max_round = max(rounds) if rounds else 0
        if not items:
            effect_status = "insufficient"
        elif pass_after_trigger and not still_failing:
            effect_status = "promising"
        elif still_failing and not pass_after_trigger:
            effect_status = "warn"
        else:
            effect_status = "mixed"
        roles: dict[str, int] = {}
        for item in items:
            role = str(item.get("role") or "unknown")
            roles[role] = roles.get(role, 0) + 1
        status = "idle"
        if items:
            status = "warn" if strong_count or fail_verdict_count else "ok"
        return {
            "ok": status in {"ok", "idle"},
            "status": status,
            "count": len(items),
            "strong_count": strong_count,
            "recommended_count": recommended_count,
            "fail_verdict_count": fail_verdict_count,
            "trend": {
                "effect_status": effect_status,
                "pass_after_trigger": pass_after_trigger,
                "still_failing": still_failing,
                "fail_recurrence": fail_recurrence,
                "avg_round": avg_round,
                "max_round": max_round,
                "window_size": len(items),
            },
            "roles": roles,
            "latest": items[0] if items else {},
            "items": items,
        }
    except Exception as exc:
        return {"ok": False, "status": "error", "count": 0, "items": [], "errors": [f"{type(exc).__name__}: {exc}"]}


def _meta_harness_summary() -> dict:
    """Summarize Meta-Harness outer-loop optimizer state without running it."""
    def _load_json(path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    try:
        config = _load_json(META_HARNESS_DIR / "config.json", {})
        if not isinstance(config, dict):
            config = {}
        eval_set = _load_json(META_HARNESS_DIR / "evaluation_set.json", [])
        eval_count = len(eval_set) if isinstance(eval_set, list) else 0
        pareto_data = _load_json(META_HARNESS_DIR / "pareto.json", {})
        if not isinstance(pareto_data, dict):
            pareto_data = {}
        pareto = pareto_data.get("pareto") if isinstance(pareto_data.get("pareto"), list) else []
        all_runs = pareto_data.get("all_runs") if isinstance(pareto_data.get("all_runs"), list) else []
        runs_dir = META_HARNESS_DIR / "runs"
        run_dirs = sorted([p for p in runs_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True) if runs_dir.exists() else []
        latest_command = _read_json_file(REPORTS_DIR / "meta-harness" / "latest-command.json")
        ok = META_HARNESS_TOOL.exists() and META_HARNESS_DIR.exists() and META_HARNESS_SKILL.exists() and eval_count > 0
        if not META_HARNESS_TOOL.exists():
            status = "error"
        elif not META_HARNESS_DIR.exists() or eval_count <= 0:
            status = "pending"
        elif not pareto and not run_dirs:
            status = "ready"
        else:
            status = "ok"
        best = pareto[0] if pareto and isinstance(pareto[0], dict) else {}
        return {
            "ok": ok,
            "status": status,
            "integration_level": "solar_harness_cli_adapter" if ok else "external_tool_detected" if META_HARNESS_TOOL.exists() else "missing",
            "tool": {"path": str(META_HARNESS_TOOL), "exists": META_HARNESS_TOOL.exists()},
            "skill": {"path": str(META_HARNESS_SKILL), "exists": META_HARNESS_SKILL.exists()},
            "store": {
                "path": str(META_HARNESS_DIR),
                "exists": META_HARNESS_DIR.exists(),
                "evaluation_count": eval_count,
                "proposer_model": config.get("proposer_model", ""),
                "evaluator_model": config.get("evaluator_model", ""),
                "max_iterations": config.get("max_iterations", ""),
            },
            "pareto": {
                "path": str(META_HARNESS_DIR / "pareto.json"),
                "exists": (META_HARNESS_DIR / "pareto.json").exists(),
                "pareto_count": len(pareto),
                "all_runs_count": len(all_runs),
                "best_run_id": str(best.get("run_id") or best.get("id") or ""),
            },
            "runs": {
                "runs_dir": str(runs_dir),
                "exists": runs_dir.exists(),
                "count": len(run_dirs),
                "latest": run_dirs[0].name if run_dirs else "",
            },
            "latest_command": latest_command if isinstance(latest_command, dict) else {},
            "safety": {
                "default_execution": "dry_run",
                "real_run_requires_execute": True,
                "real_apply_requires_execute": True,
                "coordinator_autorun": False,
            },
            "commands": {
                "status": "solar-harness meta-harness status --json",
                "doctor": "solar-harness meta-harness doctor --json",
                "run_dry": "solar-harness meta-harness run 3 hooks --json",
                "apply_dry": "solar-harness meta-harness apply <run_id> --json",
            },
        }
    except Exception as exc:
        return {"ok": False, "status": "error", "errors": [f"{type(exc).__name__}: {exc}"]}


def _pm_dispatch_summary(limit: int = 8) -> dict:
    """Summarize recent PM dispatch records for the main status dashboard."""
    inbox_dir = HARNESS_DIR / "run" / "pm-inbox"
    if not inbox_dir.exists():
        return {"ok": True, "status": "idle", "count": 0, "items": [], "source": str(inbox_dir)}
    items = []
    try:
        records = sorted(
            inbox_dir.glob("pm-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[: max(1, limit)]
        for path in records:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            mode = str(record.get("mode") or "planner_order")
            target = (
                str(record.get("operator_id") or "operator")
                if mode == "adhoc_probe"
                else str(record.get("dispatch_target") or "solar-harness")
            )
            items.append({
                "task_id": str(record.get("task_id") or path.stem),
                "mode": mode,
                "target": target,
                "status": str(record.get("status") or "unknown"),
                "sprint_id": str(record.get("sprint_id") or ""),
                "submitted_at": str(record.get("submitted_at") or ""),
                "objective": str(record.get("objective") or ""),
            })
        statuses = {str(item.get("status") or "").lower() for item in items}
        summary_status = "idle"
        if items:
            if any(st in {"failed", "error", "rejected"} for st in statuses):
                summary_status = "warn"
            elif any(st in {"queued", "submitted", "planner_dispatch_ready", "requirements_ready"} for st in statuses):
                summary_status = "ok"
            else:
                summary_status = "ok"
        return {
            "ok": summary_status in {"ok", "idle"},
            "status": summary_status,
            "count": len(items),
            "items": items,
            "latest": items[0] if items else {},
            "source": str(inbox_dir),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "count": 0,
            "items": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
            "source": str(inbox_dir),
        }


def _recent_operator_results(results_dir: Path, multi_task_dir: Path, limit: int = 8) -> list[dict]:
    """Return recent physical operator executions from canonical results plus legacy task status."""
    rows: list[tuple[float, dict]] = []
    seen: set[tuple[str, str]] = set()
    max_items = max(1, limit)
    if results_dir.exists():
        result_paths = sorted(
            results_dir.glob("*/*/result.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[: max_items]
        for path in result_paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            operator_id = str(data.get("operator_id") or path.parents[1].name)
            task_id = str(data.get("task_id") or path.parent.name)
            seen.add((operator_id, task_id))
            rows.append((path.stat().st_mtime, {
                "operator_id": operator_id,
                "task_id": task_id,
                "status": str(data.get("status") or "unknown"),
                "started_at": str(data.get("started_at") or ""),
                "finished_at": str(data.get("finished_at") or ""),
                "exit_code": data.get("exit_code"),
                "sprint_id": str(data.get("sprint_id") or ""),
                "node_id": str(data.get("node_id") or ""),
                "model": str(data.get("model") or data.get("operator_model") or ""),
                "backend": str(data.get("backend") or ""),
                "result_kind": str(data.get("result_kind") or ""),
                "original_image_ok": bool(data.get("original_image_ok") or data.get("original_image_response")),
                "image_path": str(data.get("image_path") or ""),
                "url": str(data.get("url") or ""),
                "width": data.get("width"),
                "height": data.get("height"),
                "bytes": data.get("bytes"),
                "source": "operator-results",
            }))

    if multi_task_dir.exists():
        status_paths = sorted(
            multi_task_dir.glob("*/status.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in status_paths:
            if len(rows) >= max_items:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            operator_id = str(data.get("operator_id") or "")
            task_id = str(data.get("id") or data.get("task_id") or path.parent.name)
            if not operator_id or operator_id == "N/A" or (operator_id, task_id) in seen:
                continue
            status = str(data.get("status") or "unknown")
            rows.append((path.stat().st_mtime, {
                "operator_id": operator_id,
                "task_id": task_id,
                "status": status,
                "started_at": str(data.get("created_at") or ""),
                "finished_at": str(data.get("updated_at") or "") if status not in {"running", "submitted", "dispatched"} else "",
                "exit_code": data.get("exit_code"),
                "sprint_id": str(data.get("sprint_id") or ""),
                "node_id": str(data.get("node_id") or ""),
                "model": str(data.get("operator_model") or data.get("model") or ""),
                "backend": str(data.get("backend") or ""),
                "source": "multi-task-status",
            }))
            seen.add((operator_id, task_id))

    rows.sort(key=lambda row: row[0], reverse=True)
    return [row for _, row in rows[:max_items]]


def _operator_health_records(health_dir: Path) -> dict[str, dict]:
    """Load latest per-operator health projections."""
    records: dict[str, dict] = {}
    if not health_dir.exists():
        return records
    try:
        paths = sorted(health_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return records
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        operator_id = str(data.get("operator_id") or path.stem).strip()
        if operator_id:
            records[operator_id] = data
    return records


def _physical_operator_summary(limit: int = 8) -> dict:
    """Summarize physical operator fleet state for the main status dashboard."""
    registry_path = HARNESS_DIR / "config" / "physical-operators.json"
    lease_dir = HARNESS_DIR / "run" / "operator-leases"
    status_dir = HARNESS_DIR / "run" / "operator-status"
    results_dir = HARNESS_DIR / "run" / "operator-results"
    health_dir = HARNESS_DIR / "run" / "operator-health"
    multi_task_dir = HARNESS_DIR / "run" / "multi-task"
    empty = {
        "ok": False,
        "status": "missing",
        "count": 0,
        "enabled": 0,
        "available": 0,
        "dispatchable": 0,
        "busy": 0,
        "roles": {},
        "items": [],
        "alerts": [],
        "recent_results": [],
        "sources": {
            "registry": str(registry_path),
            "leases": str(lease_dir),
            "status": str(status_dir),
            "results": str(results_dir),
            "health": str(health_dir),
            "multi_task": str(multi_task_dir),
        },
    }
    if not registry_path.exists():
        return empty
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
        operators = raw.get("operators", {}) if isinstance(raw, dict) else {}
        if not isinstance(operators, dict):
            return {**empty, "status": "error", "errors": ["invalid operators registry shape"]}

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        leases = {}
        if lease_dir.exists():
            for path in lease_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(data.get("expires_at") or "") > now:
                    leases[path.stem] = data
        overrides = {}
        if status_dir.exists():
            for path in status_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                expires_at = str(data.get("expires_at") or "")
                if expires_at and expires_at <= now:
                    continue
                overrides[path.stem] = data
        health_records = _operator_health_records(health_dir)

        items = []
        alerts = []
        roles = {}
        enabled_count = 0
        available_count = 0
        dispatchable_count = 0
        busy_count = 0
        for operator_id, cfg in operators.items():
            cfg = cfg if isinstance(cfg, dict) else {}
            role = str(cfg.get("role") or "unknown")
            roles[role] = roles.get(role, 0) + 1
            enabled = bool(cfg.get("enabled", True))
            available = bool(cfg.get("available", True))
            if enabled:
                enabled_count += 1
            if available:
                available_count += 1
            reg_state = cfg.get("state") if isinstance(cfg.get("state"), dict) else {}
            runtime_state = "idle"
            if not enabled:
                runtime_state = "disabled"
            elif reg_state.get("availability") == "disabled" or reg_state.get("runtime_state") == "disabled":
                runtime_state = "disabled"
            elif operator_id in leases:
                runtime_state = str(leases[operator_id].get("state") or "leased")
            elif operator_id in overrides:
                runtime_state = str(overrides[operator_id].get("runtime_state") or "idle")
            elif str(reg_state.get("runtime_state") or ""):
                runtime_state = str(reg_state.get("runtime_state"))

            is_busy = runtime_state in {"leased", "running", "draining", "cooldown", "quota_exhausted", "auth_expired"}
            if is_busy:
                busy_count += 1
            if enabled and available and runtime_state == "idle":
                dispatchable_count += 1
            if runtime_state in {"quota_exhausted", "auth_expired", "error", "disabled"}:
                alerts.append({
                    "operator_id": operator_id,
                    "runtime_state": runtime_state,
                    "role": role,
                    "backend": str(cfg.get("backend") or "unknown"),
                })

            lease = leases.get(operator_id) or {}
            health = health_records.get(operator_id) or {}
            items.append({
                "operator_id": operator_id,
                "role": role,
                "backend": str(cfg.get("backend") or "unknown"),
                "enabled": enabled,
                "available": available,
                "runtime_state": runtime_state,
                "persona": str(cfg.get("persona") or ""),
                "model": str(cfg.get("model") or cfg.get("provider") or ""),
                "sprint_id": str(lease.get("sprint_id") or ""),
                "task_id": str(lease.get("task_id") or ""),
                "expires_at": str(lease.get("expires_at") or ""),
                "latest_health": health,
            })

        recent_results = _recent_operator_results(results_dir, multi_task_dir, limit=limit)

        def _display_rank(item: dict[str, Any]) -> tuple[int, int, str]:
            runtime_state = str(item.get("runtime_state") or "")
            enabled = bool(item.get("enabled"))
            available = bool(item.get("available"))
            if enabled and available and runtime_state == "idle":
                return (0, 0, str(item.get("operator_id") or ""))
            if runtime_state in {"leased", "running", "draining"}:
                return (1, 0, str(item.get("operator_id") or ""))
            if runtime_state in {"cooldown", "quota_exhausted", "auth_expired", "error"}:
                return (2, 0, str(item.get("operator_id") or ""))
            if runtime_state == "disabled" or not enabled:
                return (3, 0, str(item.get("operator_id") or ""))
            return (4, 0, str(item.get("operator_id") or ""))

        items.sort(key=_display_rank)
        summary_status = "ok"
        if any(str(item.get("runtime_state")) in {"quota_exhausted", "auth_expired", "error"} for item in items):
            summary_status = "warn"
        elif dispatchable_count == 0 and items:
            summary_status = "warn"
        elif not items:
            summary_status = "idle"
        return {
            "ok": summary_status in {"ok", "idle"},
            "status": summary_status,
            "count": len(items),
            "enabled": enabled_count,
            "available": available_count,
            "dispatchable": dispatchable_count,
            "busy": busy_count,
            "roles": roles,
            "items": items,
            "alerts": alerts[:limit],
            "recent_results": recent_results,
            "sources": {
                "registry": str(registry_path),
                "leases": str(lease_dir),
                "status": str(status_dir),
                "results": str(results_dir),
                "health": str(health_dir),
                "multi_task": str(multi_task_dir),
            },
        }
    except Exception as exc:
        return {
            **empty,
            "status": "error",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def _final_contract_summary_candidates() -> list[Path]:
    return [
        FINAL_CONTRACT_SUMMARY_DOC,
        FINAL_CONTRACT_SUMMARY_SPRINT_ARTIFACT,
    ]


def _load_final_contract_summary_text() -> tuple[str, Path | None]:
    for path in _final_contract_summary_candidates():
        try:
            if path.exists():
                return path.read_text(encoding="utf-8"), path
        except OSError:
            continue
    return "", None


def _final_contract_summary_status() -> dict:
    text, path = _load_final_contract_summary_text()
    if not text:
        return {
            "status": "missing",
            "title": "PM -> Planner -> Headless Pool DAG Flow",
            "path": "N/A",
            "route": "/contract-summary",
            "summary": "Final contract summary document not found.",
            "source": "N/A",
        }
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0].lstrip("#").strip() if lines else "PM -> Planner -> Headless Pool DAG Flow"
    summary = ""
    for line in lines[1:]:
        if not line.startswith("#"):
            summary = line
            break
    if not summary:
        summary = "Canonical PM -> Planner -> Headless Pool DAG Flow contract."
    return {
        "status": "ok",
        "title": title,
        "path": str(path),
        "route": "/contract-summary",
        "summary": summary,
        "source": "docs" if path == FINAL_CONTRACT_SUMMARY_DOC else "sprint-artifact",
    }


def _final_contract_summary_html() -> str:
    text, path = _load_final_contract_summary_text()
    if not text:
        body = "<div class='card'><h2>Final Contract Summary</h2><p class='warn'>Contract summary document not found.</p></div>"
    else:
        body = (
            "<div class='card'>"
            "<h2>Final Contract Summary</h2>"
            f"<p class='muted'>Source: {html.escape(str(path))}</p>"
            "<pre style='white-space:pre-wrap;overflow-wrap:anywhere;margin:0'>"
            + html.escape(text) +
            "</pre></div>"
        )
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Final Contract Summary</title>"
        "<style>"
        ":root{--bg:#f3efe4;--ink:#18211f;--line:rgba(30,43,39,.14);--panel:#fffaf0;--shadow:0 24px 80px rgba(33,27,18,.12);}"
        "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:\"Avenir Next\",\"Gill Sans\",\"Trebuchet MS\",sans-serif;padding:32px;}"
        ".shell{max-width:1100px;margin:0 auto}.card{border:1px solid var(--line);border-radius:24px;background:var(--panel);box-shadow:var(--shadow);padding:24px}"
        "h1{margin:0 0 16px}.muted{color:#68726d}.warn{color:#b7791f}.topnav{margin-bottom:16px}"
        ".topnav a{color:#0f6b68;text-decoration:none;font-weight:700}"
        "pre{font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;background:rgba(255,255,255,.48);padding:18px;border-radius:16px;border:1px solid var(--line)}"
        "</style></head><body><div class='shell'><div class='topnav'><a href='/'>← Back to 8765 Status</a></div>"
        f"{body}</div></body></html>"
    )


def _requirement_coverage_summary(sid: str = "") -> dict:
    """Return requirement coverage summary, preferring the active sprint and explicitly marking fallback."""
    candidates: list[tuple[str, str]] = []
    requested_sid = str(sid or "").strip()
    current_sid = str(_current_sprint().get("sprint_id") or "").strip()
    if requested_sid:
        candidates.append((requested_sid, "requested"))
    if current_sid and current_sid != requested_sid:
        candidates.append((current_sid, "active"))
    try:
        status_files = sorted(
            SPRINTS_DIR.glob("*.status.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        status_files = []
    for path in status_files:
        candidate = path.name.removesuffix(".status.json")
        if candidate not in {sid for sid, _ in candidates}:
            candidates.append((candidate, "recent"))

    for candidate, source in candidates:
        coverage_path = SPRINTS_DIR / f"{candidate}.coverage_report.json"
        verdict_path = SPRINTS_DIR / f"{candidate}.acceptance_verdict.json"
        if not coverage_path.exists():
            continue
        try:
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            verdict = json.loads(verdict_path.read_text(encoding="utf-8")) if verdict_path.exists() else {}
        except Exception:
            continue
        summary = coverage.get("summary", {}) if isinstance(coverage, dict) else {}
        verdict = verdict if isinstance(verdict, dict) else {}
        total = int(summary.get("total", 0) or 0)
        done = int(summary.get("done", 0) or 0)
        partial = int(summary.get("partial", 0) or 0)
        missing = int(summary.get("missing", 0) or 0)
        ratio = summary.get("coverage_ratio", 0)
        try:
            coverage_ratio = float(ratio or 0)
        except Exception:
            coverage_ratio = 0.0
        verdict_label = str(verdict.get("verdict") or "N/A")
        status = "ok"
        if partial or missing or verdict_label not in {"PASS", "N/A"}:
            status = "warn"
        return {
            "ok": status == "ok",
            "status": status,
            "sprint_id": candidate,
            "requested_sprint_id": requested_sid or current_sid,
            "source": source,
            "is_fallback": source not in {"requested", "active"},
            "total": total,
            "done": done,
            "partial": partial,
            "missing": missing,
            "coverage_ratio": coverage_ratio,
            "graph_complete": bool(summary.get("graph_complete", False)),
            "acceptance_verdict": verdict_label,
            "paths": {
                "coverage_report": str(coverage_path),
                "acceptance_verdict": str(verdict_path) if verdict_path.exists() else "",
            },
        }
    return {
        "ok": False,
        "status": "missing",
        "sprint_id": requested_sid or current_sid,
        "requested_sprint_id": requested_sid or current_sid,
        "source": "active_missing" if (requested_sid or current_sid) else "none",
        "is_fallback": False,
        "total": 0,
        "done": 0,
        "partial": 0,
        "missing": 0,
        "coverage_ratio": 0.0,
        "graph_complete": False,
        "acceptance_verdict": "N/A",
        "paths": {
            "coverage_report": "",
            "acceptance_verdict": "",
        },
    }


def _pane_title_model(title: str) -> str:
    match = re.search(r"模型:([^|]+)", title or "")
    if match:
        return match.group(1).strip()
    return ""


def _pane_operator_type(pool: str, command: str) -> str:
    if pool == "builder-lab":
        return "builder_lab_pane"
    if command in {"zsh", "bash", "sh", "fish"}:
        return "shell_worker"
    return "command_worker"


def _multi_task_shell_panes_info() -> list:
    """Return legacy multi-task shell panes with task/lease context."""
    session = "solar-harness-multi-task"
    cmd = ["list-panes", "-s", "-t", session, "-F", "#{window_index}\t#{window_name}\t#{window_active}\t#{pane_index}\t#{pane_current_command}\t#{pane_title}\t#{pane_active}\t#{pane_id}"]
    raw_panes = _run_tmux(cmd)
    if not raw_panes:
        return []
    
    leases = {}
    lease_dir = HARNESS_DIR / "run" / "operator-leases"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if lease_dir.exists():
        for path in lease_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(data.get("expires_at") or "") > now:
                pane_target = data.get("pane")
                if pane_target:
                    leases[pane_target] = data
                    
    run_dir = HARNESS_DIR / "run" / "multi-task"
    latest_by_window = {}
    if run_dir.exists():
        status_paths = sorted(run_dir.glob("*/status.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in status_paths:
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            window_name = str(row.get("window") or "").strip()
            if not window_name or window_name in latest_by_window:
                continue
            latest_by_window[window_name] = {
                "task_id": str(row.get("id") or ""),
                "status": str(row.get("status") or ""),
                "updated_at": str(row.get("updated_at") or row.get("created_at") or ""),
                "sprint_id": str(row.get("sprint_id") or ""),
                "node_id": str(row.get("node_id") or ""),
                "profile": str(row.get("profile") or ""),
                "role": str(row.get("role") or ""),
            }

    panes_list = []
    for line in raw_panes.splitlines():
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        w_idx, w_name, w_active, p_idx, p_cmd, p_title, p_active, p_id = parts[:8]
        pane_target = f"{session}:{w_idx}"
        lease = leases.get(pane_target) or leases.get(f"{session}:{w_idx}.{p_idx}") or {}
        task_meta = latest_by_window.get(w_name) or {}
        task_status = str(task_meta.get("status") or "").lower()
        
        status = "idle"
        if lease:
            status = "leased"
        elif p_cmd not in {"zsh", "bash", "sh", "fish"}:
            status = "running"
        elif task_status in {"completed", "completed_aligned", "failed", "failed_missing_handoff", "cancelled", "reaped", "reaped_stale_active"} or task_status.startswith("reaped"):
            status = "historical_active" if w_active == "1" else "reusable_idle"
            
        panes_list.append({
            "pane": pane_target,
            "session": session,
            "pool": "multi-task",
            "operator_type": _pane_operator_type("multi-task", p_cmd),
            "backend": str(lease.get("backend") or task_meta.get("backend") or "tmux-pane"),
            "model": str(lease.get("model") or task_meta.get("model") or _pane_title_model(p_title) or ""),
            "profile": str(lease.get("profile") or task_meta.get("profile") or ""),
            "role": str(lease.get("role") or task_meta.get("role") or ""),
            "window_index": int(w_idx),
            "window_name": w_name,
            "pane_index": int(p_idx),
            "current_command": p_cmd,
            "title": p_title,
            "status": status,
            "active": w_active == "1",
            "lease": lease,
            "task": task_meta,
        })
    return panes_list


def _builder_lab_panes_info() -> list:
    """Return builder-lab panes as part of the broader headless pool."""
    session = "solar-harness-lab"
    cmd = ["list-panes", "-s", "-t", session, "-F", "#{window_index}\t#{window_name}\t#{window_active}\t#{pane_index}\t#{pane_current_command}\t#{pane_title}\t#{pane_active}\t#{pane_id}"]
    raw_panes = _run_tmux(cmd)
    if not raw_panes:
        return []

    panes_list = []
    for line in raw_panes.splitlines():
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        w_idx, w_name, w_active, p_idx, p_cmd, p_title, p_active, p_id = parts[:8]
        status = "idle"
        title_l = (p_title or "").lower()
        if p_cmd not in {"zsh", "bash", "sh", "fish"}:
            status = "running"
        elif "leased" in title_l or "running" in title_l:
            status = "running"
        elif "idle" in title_l or "no active sprint" in title_l:
            status = "idle"
        panes_list.append({
            "pane": f"{session}:0.{p_idx}",
            "session": session,
            "pool": "builder-lab",
            "operator_type": _pane_operator_type("builder-lab", p_cmd),
            "backend": "tmux-pane",
            "model": _pane_title_model(p_title),
            "profile": "builder-lab",
            "role": "builder",
            "window_index": int(w_idx),
            "window_name": w_name,
            "pane_index": int(p_idx),
            "current_command": p_cmd,
            "title": p_title,
            "status": status,
            "active": w_active == "1",
            "lease": {},
            "task": {},
        })
    return panes_list


def _multi_task_panes_info() -> list:
    """Return the full headless pane pool shown under 8765 #lab."""
    return _builder_lab_panes_info() + _multi_task_shell_panes_info()


def _multi_task_pane_pool_summary(panes: list[dict]) -> dict:
    counts = {
        "total": len(panes),
        "idle": 0,
        "reusable_idle": 0,
        "historical_active": 0,
        "leased": 0,
        "running": 0,
    }
    for pane in panes:
        status = str(pane.get("status") or "idle")
        if status in counts:
            counts[status] += 1
        else:
            counts["idle"] += 1
    counts["target_keep"] = max(0, int(os.environ.get("SOLAR_MULTI_TASK_IDLE_WINDOW_POOL_TARGET", "1") or "1"))
    counts["reuse_enabled"] = str(os.environ.get("SOLAR_MULTI_TASK_REUSE_TERMINAL_WINDOWS", "1") or "1").lower() not in {"0", "false", "no", "off"}
    counts["auto_close_enabled"] = str(os.environ.get("SOLAR_MULTI_TASK_AUTO_CLOSE_TERMINAL_WINDOWS", "1") or "1").lower() not in {"0", "false", "no", "off"}
    counts["compact_recommended"] = counts["historical_active"] > 0 or counts["reusable_idle"] > counts["target_keep"]
    return counts


def _status_payload(limit: int = 50) -> dict:
    current = _current_sprint()
    runtime_interfaces = _runtime_interfaces_status(current.get("sprint_id", ""))
    capability_health = _capability_health_summary(runtime_interfaces)
    multi_task_panes = _multi_task_panes_info()
    return {
        "current_sprint": current,
        "panes": _pane_info(),
        "main_screen": _main_screen(capability_health, include_model_call=False),
        "lab_screen": _lab_screen(capability_health, include_model_call=False),
        "multi_task_panes": multi_task_panes,
        "multi_task_pane_pool": _multi_task_pane_pool_summary(multi_task_panes),
        "recent_events": _read_jsonl(ALL_EVENTS, limit=limit, filter_synthetic=True),
        "kpi": _kpi(),
        "obsidian_wiki": _obsidian_wiki_readiness(),
        "mirage": _mirage_status(),
        "knowledge_progress": _knowledge_ingest_progress_payload(),
        "knowledge_routing": _tech_hotspot_reasoning_policy_summary(),
        "capability_health": capability_health,
        "solar_kb": _solar_kb_status(),
        "obsidian_sync": _obsidian_sync_status(),
        "apple_notes_ingest": _apple_notes_ingest_status(),
        "evolution": _evolution_status(),
        "runtime_interfaces": runtime_interfaces,
        "human_search": _human_search_waiting_status(),
        "research": _research_status_summary(),
        "autoresearch_impact": _autoresearch_impact_summary(),
        "meta_harness": _meta_harness_summary(),
        "pm_dispatches": _pm_dispatch_summary(),
        "physical_operators": _physical_operator_summary(),
        "contract_summary": _final_contract_summary_status(),
        "requirement_coverage": _requirement_coverage_summary(current.get("sprint_id", "")),
    }


def _runtime_interfaces_status(sprint_id: str) -> dict:
    """Return lightweight runtime interface health for /status."""
    if not sprint_id:
        return {"ok": False, "status": "unknown", "message": "no current sprint"}
    now = time.monotonic()
    cached = _RUNTIME_INTERFACES_CACHE.get(sprint_id)
    if cached and now - cached.get("ts", 0.0) <= _RUNTIME_INTERFACES_CACHE_TTL_SECONDS:
        value = dict(cached.get("value") or {})
        value["cache"] = "hit"
        return value
    doctor = HARNESS_DIR / "lib" / "runtime_doctor.py"
    if not doctor.exists():
        return {"ok": False, "status": "error", "message": "runtime_doctor.py missing"}
    try:
        proc = subprocess.run(
            ["python3", str(doctor), sprint_id, "--json"],
            text=True,
            capture_output=True,
            timeout=_RUNTIME_INTERFACES_TIMEOUT_SECONDS,
        )
        if proc.returncode not in (0, 1):
            return {"ok": False, "status": "error", "message": (proc.stderr or proc.stdout)[-500:]}
        data = json.loads(proc.stdout)
        ih = data.get("checks", {}).get("interface_health", {})
        dims = ih.get("dimensions", {})
        total = len(dims)
        healthy = sum(1 for d in dims.values() if d.get("ok"))
        value = {
            "ok": bool(ih.get("ok")),
            "status": "ok" if ih.get("ok") else "warn",
            "message": ih.get("message", f"{healthy}/{total} interfaces healthy"),
            "healthy": healthy,
            "total": total,
            "dimensions": dims,
            "cache": "miss",
        }
        _RUNTIME_INTERFACES_CACHE[sprint_id] = {"ts": now, "value": value}
        return dict(value)
    except subprocess.TimeoutExpired:
        value = {"ok": False, "status": "warn", "message": "runtime doctor timeout", "cache": "miss"}
        _RUNTIME_INTERFACES_CACHE[sprint_id] = {"ts": now, "value": value}
        return dict(value)
    except Exception as exc:
        value = {"ok": False, "status": "error", "message": f"{type(exc).__name__}: {exc}", "cache": "miss"}
        _RUNTIME_INTERFACES_CACHE[sprint_id] = {"ts": now, "value": value}
        return dict(value)


# ── HTML Dashboard ──
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Solar Harness Status</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

:root {
  --bg: #070a13;
  --ink: #ffffff;
  --muted: #cbd5e1;
  --panel: rgba(15, 23, 42, 0.45);
  --panel-solid: #0f172a;
  --line: rgba(255, 255, 255, 0.08);
  --shadow: 0 16px 48px rgba(0, 0, 0, 0.6);
  --accent: #f43f5e;
  --accent-2: #06b6d4;
  --accent-3: #f59e0b;
  --warn: #fbbf24;
  --error: #ef4444;
  --ok: #10b981;
  --code: #030712;
  --page-max: 1400px;
  --page-pad: clamp(16px, 4vw, 48px);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background:
    radial-gradient(circle at 10% 10%, rgba(244, 63, 94, 0.06), transparent 45rem),
    radial-gradient(circle at 90% 10%, rgba(6, 182, 212, 0.10), transparent 45rem),
    radial-gradient(circle at 50% 85%, rgba(16, 185, 129, 0.04), transparent 50rem),
    #070a13;
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}
/* Custom modern scrollbars */
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
::-webkit-scrollbar-track {
  background: #070a13;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 99px;
  border: 2px solid #070a13;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.18);
}
header {
  padding: 2rem var(--page-pad) 1rem;
}
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 1.5rem 2rem;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow);
}
.eyebrow {
  color: var(--accent-2);
  font: 800 0.72rem ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  text-shadow: 0 0 12px rgba(6, 182, 212, 0.3);
}
h1 {
  margin: 0.35rem 0 0;
  color: #ffffff;
  font-weight: 900;
  font-size: clamp(1.8rem, 3.5vw, 2.6rem);
  letter-spacing: -0.04em;
  background: linear-gradient(135deg, #ffffff 40%, #94a3b8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
h2 {
  margin: 0 0 1rem;
  color: #ffffff;
  font-size: 1.25rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}
h3 {
  margin: 0 0 0.65rem;
  color: #e2e8f0;
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}
a { color: var(--accent-2); text-decoration: none; transition: color 0.2s; }
a:hover { color: #22d3ee; }
main {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 1.2rem var(--page-pad) 3rem;
}
.subhead {
  color: var(--muted);
  font: 600 0.8rem ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
}
.tabbar {
  display: flex;
  gap: 0.25rem;
  overflow-x: auto;
  width: calc(100% - clamp(32px, 8vw, 96px));
  max-width: var(--page-max);
  margin: 1.2rem auto 0;
  padding: 0.35rem;
  position: sticky;
  top: 0.75rem;
  z-index: 99;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 99px;
  background: rgba(15, 23, 42, 0.65);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow: 0 20px 50px rgba(0,0,0,0.4);
}
.tab, .tab-link {
  border: 0;
  background: transparent;
  color: #94a3b8;
  border-radius: 99px;
  padding: 0.6rem 1.1rem;
  font: 700 0.84rem 'Inter', sans-serif;
  cursor: pointer;
  white-space: nowrap;
  text-decoration: none;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.tab.active {
  background: linear-gradient(135deg, var(--accent-2) 0%, #0891b2 100%);
  color: #ffffff;
  box-shadow: 0 4px 15px rgba(6, 182, 212, 0.35);
  text-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.tab:hover, .tab-link:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.05);
}
.tab.active:hover {
  background: linear-gradient(135deg, var(--accent-2) 0%, #0891b2 100%);
  transform: scale(1.02);
}
.panel { display: none; }
.panel.active { display: block; animation: rise 220ms cubic-bezier(0.34, 1.56, 0.64, 1); }
@keyframes rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.2rem; }
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 1.5rem;
  margin-bottom: 1.2rem;
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.25s, border-color 0.25s;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.7), 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-color: rgba(255, 255, 255, 0.15);
}
.card:nth-child(4n + 1), .card:nth-child(4n + 2), .card:nth-child(4n + 3) {
  background: rgba(15, 23, 42, 0.45);
}
.metric {
  font-weight: 800;
  font-size: 2.8rem;
  line-height: 1;
  color: var(--accent-2);
  margin-top: 0.35rem;
  text-shadow: 0 0 20px rgba(6, 182, 212, 0.15);
}
.muted { color: var(--muted); }
.task-block {
  display: grid;
  gap: 0.8rem;
}
.task-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding-bottom: 0.8rem;
  border-bottom: 1px solid var(--line);
}
.task-title {
  font: 800 1.05rem 'Inter', sans-serif;
  letter-spacing: -0.02em;
  color: #ffffff;
}
.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 0.6rem;
}
.kv {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.65rem 0.75rem;
  background: rgba(255, 255, 255, 0.015);
  transition: background 0.2s;
}
.kv:hover {
  background: rgba(255, 255, 255, 0.03);
}
.kv-label {
  color: var(--muted);
  font: 800 0.65rem ui-monospace, monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.kv-value {
  margin-top: 0.2rem;
  font-weight: 700;
  color: #e2e8f0;
  font-size: 0.85rem;
}
.summary-list {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.summary-list li {
  position: relative;
  padding: 0.65rem 0.8rem 0.65rem 2rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.01);
  line-height: 1.5;
  font-size: 0.88rem;
  color: #f1f5f9;
  transition: all 0.2s;
}
.summary-list li:hover {
  background: rgba(255, 255, 255, 0.025);
  border-color: rgba(255, 255, 255, 0.12);
}
.summary-list li::before {
  content: "";
  position: absolute;
  left: 0.85rem;
  top: 1.15rem;
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 999px;
  background: var(--accent-2);
  box-shadow: 0 0 8px var(--accent-2);
}
.tech-id {
  color: var(--muted);
  font: 700 0.74rem ui-monospace, monospace;
  word-break: break-all;
}
.path-text {
  font-family: ui-monospace, monospace;
  font-size: 0.84rem;
  overflow-wrap: anywhere;
  word-break: break-all;
  color: #cbd5e1;
}
.badge, .level-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font: 700 0.7rem ui-monospace, monospace;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  border: 1px solid rgba(255,255,255,0.06);
}
.badge.active, .badge.passed, .badge.ok, .level-badge.ok {
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.25);
}
.badge.reviewing {
  background: rgba(59, 130, 246, 0.12);
  color: #60a5fa;
  border-color: rgba(59, 130, 246, 0.25);
}
.badge.failed, .badge.error-badge, .level-badge.error-badge {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.25);
}
.badge.warn-badge, .level-badge.warn {
  background: rgba(245, 158, 11, 0.12);
  color: #fbbf24;
  border-color: rgba(245, 158, 11, 0.25);
}
.badge.default, .level-badge.default {
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
}
.badge.missing, .level-badge.missing {
  background: rgba(255, 255, 255, 0.02);
  color: #94a3b8;
}
.warn { color: var(--warn); font-weight: 600; }
.error { color: var(--error); font-weight: 600; }
.info { color: var(--accent-2); }
.ok-text { color: #34d399; }
table {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgba(10, 15, 26, 0.4);
}
th {
  text-align: left;
  color: #cbd5e1;
  border-bottom: 1px solid var(--line);
  padding: 12px 14px;
  font: 800 0.74rem ui-monospace, monospace;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  background: rgba(255, 255, 255, 0.02);
}
td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  font-size: 0.88rem;
  color: #f1f5f9;
  background: transparent;
  vertical-align: middle;
}
tr:last-child td {
  border-bottom: none;
}
tr:hover td {
  background: rgba(255, 255, 255, 0.015);
}
.refresh {
  color: var(--muted);
  font: 600 0.76rem ui-monospace, monospace;
  margin-bottom: 0.6rem;
}
.actions { display: flex; flex-wrap: wrap; gap: 0.65rem; margin: 1rem 0; }
.knowledge-shell {
  display: grid;
  gap: 1rem;
}
.knowledge-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: 1rem;
  align-items: stretch;
}
.knowledge-title {
  font-weight: 900;
  font-size: clamp(1.8rem, 3vw, 2.5rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
  margin: 0 0 0.8rem;
  color: #ffffff;
}
.status-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.65rem;
}
.status-tile {
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 0.85rem;
  background: rgba(255,255,255,0.02);
  min-width: 0;
  transition: border-color 0.2s;
}
.status-tile:hover {
  border-color: rgba(255, 255, 255, 0.12);
}
.status-tile strong {
  display: block;
  margin-top: 0.4rem;
  font-size: 1.05rem;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.25;
}
.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.8rem;
}
.action-card {
  min-height: 128px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 1.2rem;
  background: rgba(255, 255, 255, 0.015);
  transition: all 0.2s;
}
.action-card:hover {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.03);
}
.action-card h3 { margin-bottom: 0.35rem; color: #ffffff; }
.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem;
}
.overview-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(290px, 0.55fr);
  gap: 1.2rem;
  align-items: stretch;
}
.overview-stack {
  display: grid;
  gap: 1.2rem;
}
.overview-bottom {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1.2rem;
}
.overview-side-card {
  min-height: 0;
}
.health-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 0.65rem;
  margin-bottom: 0.8rem;
}
.mini-metric {
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 0.8rem;
  background: rgba(255, 255, 255, 0.015);
  transition: border-color 0.2s;
}
.mini-metric:hover {
  border-color: rgba(255, 255, 255, 0.12);
}
.mini-metric .num {
  display: block;
  margin-top: 0.25rem;
  color: var(--accent-2);
  font: 900 1.25rem ui-monospace, monospace;
  overflow-wrap: anywhere;
}
.mount-list {
  display: grid;
  gap: 0.5rem;
}
.mount-row {
  display: grid;
  grid-template-columns: minmax(90px, 0.8fr) auto minmax(0, 1.4fr);
  gap: 0.65rem;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.65rem 0.85rem;
  background: rgba(255, 255, 255, 0.015);
}
.mount-path {
  font: 900 0.86rem ui-monospace, monospace;
  color: #e2e8f0;
}
.mount-reason {
  color: var(--muted);
  font-size: 0.82rem;
  overflow-wrap: anywhere;
}
.integration-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 1.2rem;
}
.integration-card {
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 1.25rem;
  background: rgba(255, 255, 255, 0.015);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  transition: all 0.2s;
}
.integration-card:hover {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.035);
}
.integration-head {
  display: flex;
  gap: 0.7rem;
  justify-content: space-between;
  align-items: flex-start;
}
.badge-stack {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  align-items: flex-end;
}
.integration-name {
  font-size: 1.15rem;
  font-weight: 800;
  line-height: 1.2;
  color: #ffffff;
}
.state-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.45rem;
  margin: 0.85rem 0;
}
.state-pill {
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: 0.5rem 0.35rem;
  text-align: center;
  background: rgba(255, 255, 255, 0.02);
  font-size: 0.74rem;
  font-weight: 800;
}
.state-pill.ok { background: rgba(16, 185, 129, 0.12); color: #34d399; }
.state-pill.warn { background: rgba(245, 158, 11, 0.12); color: #fbbf24; }
.integration-reason {
  min-height: 2.2rem;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.runtime-line {
  margin-top: 0.65rem;
  border: 1px solid rgba(6, 182, 212, 0.25);
  border-radius: 14px;
  padding: 0.6rem 0.8rem;
  background: rgba(6, 182, 212, 0.06);
  color: var(--accent-2);
  overflow-wrap: anywhere;
  font: 900 0.76rem ui-monospace, monospace;
}
.human-search-grid {
  display: grid;
  gap: 0.85rem;
}
.human-search-item {
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 18px;
  padding: 1rem;
  background: rgba(245, 158, 11, 0.05);
}
.human-search-item.ready {
  border-color: rgba(16, 185, 129, 0.30);
  background: rgba(16, 185, 129, 0.06);
}
.human-search-title {
  display: flex;
  gap: 0.75rem;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.65rem;
}
.research-shell {
  display: grid;
  gap: 0.9rem;
}
.research-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(125px, 1fr));
  gap: 0.6rem;
}
.research-stat {
  border: 1px solid rgba(62, 107, 179, 0.18);
  border-radius: 18px;
  padding: 0.85rem;
  background: linear-gradient(135deg, rgba(30,41,59,0.45), rgba(15,23,42,0.65));
}
.research-stat strong {
  display: block;
  margin-top: 0.2rem;
  color: var(--accent-2);
  font: 950 1.2rem ui-monospace, monospace;
  overflow-wrap: anywhere;
}
.research-run-list {
  display: grid;
  gap: 0.75rem;
}
.research-run-card {
  border: 1px solid rgba(62, 107, 179, 0.20);
  border-radius: 22px;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.01);
}
.research-run-card.ok {
  border-color: rgba(16, 185, 129, 0.30);
  background: rgba(16, 185, 129, 0.04);
}
.research-run-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.8rem;
  align-items: start;
}
.research-run-title {
  font: 900 1rem 'Inter', sans-serif;
  line-height: 1.3;
  overflow-wrap: anywhere;
  color: #ffffff;
}
.research-run-sub {
  margin-top: 0.2rem;
  color: var(--muted);
  font: 760 0.74rem ui-monospace, monospace;
  overflow-wrap: anywhere;
}
.research-metric-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(105px, 1fr));
  gap: 0.48rem;
  margin-top: 0.8rem;
}
.research-metric {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.6rem;
  background: rgba(255, 255, 255, 0.015);
}
.research-metric b {
  display: block;
  margin-top: 0.15rem;
  color: #ffffff;
  font: 900 0.94rem ui-monospace, monospace;
}
.research-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 0.55rem;
  margin-top: 0.8rem;
}
.research-paths {
  margin-top: 0.75rem;
  display: grid;
  gap: 0.38rem;
}
.research-path {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.65rem;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.5rem 0.65rem;
  background: rgba(255, 255, 255, 0.015);
  color: var(--muted);
  font: 800 0.72rem ui-monospace, monospace;
  overflow-wrap: anywhere;
}
.research-path-actions {
  display: inline-flex;
  gap: 0.35rem;
  white-space: nowrap;
}
.research-path-actions a {
  color: var(--accent-2);
  font: 950 0.74rem 'Inter', sans-serif;
  text-decoration: none;
}
.research-path-actions a:hover {
  text-decoration: underline;
}
.research-section-title {
  margin: 0.35rem 0 0.55rem;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .08em;
}
.impact-list {
  display: grid;
  gap: 0.7rem;
}
.impact-card {
  border: 1px solid rgba(16, 185, 129, 0.24);
  border-radius: 20px;
  padding: 1rem;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.06), rgba(6, 182, 212, 0.02));
}
.impact-card.strong {
  border-color: rgba(245, 158, 11, 0.35);
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.08), rgba(244, 63, 94, 0.04));
}
.impact-title {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.75rem;
  align-items: start;
}
.impact-title strong {
  display: block;
  overflow-wrap: anywhere;
  color: #ffffff;
}
.impact-note {
  margin-top: 0.55rem;
  color: var(--muted);
  font-size: 0.82rem;
  overflow-wrap: anywhere;
}
.copy-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin-top: 0.65rem;
}
.capability-evidence {
  display: grid;
  gap: 0.38rem;
  min-width: 190px;
}
.capability-chip {
  display: grid;
  grid-template-columns: minmax(70px, 0.8fr) auto minmax(0, 1.2fr);
  gap: 0.42rem;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.45rem 0.55rem;
  background: rgba(255, 255, 255, 0.015);
  font-size: 0.78rem;
}
.capability-chip b {
  overflow-wrap: anywhere;
}
.capability-chip .detail {
  color: var(--muted);
  overflow-wrap: anywhere;
}
.integration-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  align-items: center;
  margin-bottom: 1rem;
}
.btn {
  display: inline-block;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 0.6rem 1.1rem;
  background: rgba(255, 255, 255, 0.03);
  color: #f1f5f9;
  text-decoration: none;
  cursor: pointer;
  font: 700 0.82rem 'Inter', sans-serif;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
  transition: all 0.2s;
}
.btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  transform: translateY(-1px);
}
.btn.primary {
  background: linear-gradient(135deg, var(--accent-2) 0%, #0891b2 100%);
  color: #ffffff;
  border: none;
  box-shadow: 0 4px 12px rgba(6, 182, 212, 0.3);
}
.btn.primary:hover {
  box-shadow: 0 6px 18px rgba(6, 182, 212, 0.45);
}
.codebox {
  background: var(--code);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 14px;
  color: #cbd5e1;
  overflow: auto;
  padding: 1.1rem;
  white-space: pre-wrap;
  font-family: ui-monospace, monospace;
}
.embed {
  width: 100%;
  height: 640px;
  border: 1px solid var(--line);
  border-radius: 22px;
  background: var(--panel-solid);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
}
@media (max-width: 720px) {
  .hero { align-items: flex-start; flex-direction: column; border-radius: 22px; }
  .knowledge-hero { grid-template-columns: 1fr; }
  .overview-shell, .overview-bottom { grid-template-columns: 1fr; }
  .tabbar { width: calc(100% - 32px); border-radius: 20px; }
  .tab { padding: 0.62rem 0.78rem; }
  main { padding-top: 0.9rem; }
}
@keyframes opPulse {
  0% { box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5); border-color: rgba(6, 182, 212, 0.35); }
  100% { box-shadow: 0 12px 32px rgba(6, 182, 212, 0.22); border-color: rgba(6, 182, 212, 0.75); }
}
.op-list {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  margin-top: 1rem;
}
.op-row {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr 1.5fr 0.6fr 0.8fr 1.8fr 100px;
  align-items: center;
  padding: 1.1rem 1.4rem;
  background: rgba(15, 23, 42, 0.45);
  border: 1px solid var(--line);
  border-radius: 16px;
  gap: 1rem;
  transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}
.op-row:hover {
  background: rgba(15, 23, 42, 0.65);
  border-color: rgba(255, 255, 255, 0.12);
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.4);
}
.op-row-details {
  display: none;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1.2rem;
  margin-top: -0.4rem;
  margin-bottom: 0.4rem;
  animation: opSlideDown 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
@keyframes opSlideDown {
  from { opacity: 0; transform: translateY(-5px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (max-width: 1024px) {
  .op-row {
    grid-template-columns: 1fr;
    gap: 0.8rem;
    padding: 1.2rem;
  }
}
</style>
</head>
<body>
<header>
  <div class="hero">
    <div>
      <div class="eyebrow">Solar Harness Control Desk</div>
      <h1>Solar Status</h1>
    </div>
    <div class="subhead" id="refresh-ts">Loading...</div>
  </div>
</header>

<nav class="tabbar" role="tablist">
  <button class="tab active" data-tab="overview">总览</button>
  <button class="tab" data-tab="sprint">Sprint</button>
  <button class="tab" data-tab="main">物理算子</button>
  <button class="tab" data-tab="lab">Pane监控/无头池</button>
  <button class="tab" data-tab="events">事件</button>
  <button class="tab" data-tab="knowledge">知识库</button>
  <button class="tab" data-tab="assets">资产包</button>
  <a class="tab-link" href="/ai-influence" target="_blank" rel="noreferrer">AI Influence</a>
  <button class="tab" data-tab="upload">上传文档</button>
  <button class="tab" data-tab="config">配置</button>
  <button class="tab" data-tab="integrations">集成</button>
  <button class="tab" data-tab="diagrams">架构图</button>
  <button class="tab" data-tab="raw">Raw JSON</button>
</nav>

<main>
  <section class="panel active" id="tab-overview">
    <div class="overview-shell">
      <div class="card"><h2>当前主线</h2><div id="overview-sprint">Loading...</div></div>
      <div class="overview-stack">
        <div class="card overview-side-card"><h3>Pane Health</h3><div id="overview-panes">Loading...</div></div>
        <div class="card overview-side-card"><h3>KPI</h3><div id="overview-kpi">Loading...</div></div>
      </div>
    </div>
    <div class="overview-bottom">
      <div class="card"><h3>知识库状态</h3><div id="overview-knowledge">Loading...</div></div>
      <div class="card"><h3>Runtime Interfaces</h3><div id="overview-runtime">Loading...</div></div>
      <div class="card"><h3>Capability Evidence</h3><div id="overview-capabilities">Loading...</div></div>
      <div class="card"><h3>Autoresearch Impact</h3><div id="overview-autoresearch-impact">Loading...</div></div>
      <div class="card"><h3>Knowledge Routing</h3><div id="overview-knowledge-routing">Loading...</div></div>
      <div class="card"><h3>Meta-Harness</h3><div id="overview-meta-harness">Loading...</div></div>
      <div class="card"><h3>PM Dispatch</h3><div id="overview-pm-dispatch">Loading...</div></div>
      <div class="card"><h3>Physical Operators</h3><div id="overview-physical-operators">Loading...</div></div>
      <div class="card"><h3>DeepResearch Human Search</h3><div id="overview-human-search">Loading...</div></div>
      <div class="card"><h3>DeepResearch Quality</h3><div id="overview-research">Loading...</div></div>
      <div class="card"><h3>Contract Summary</h3><div id="overview-contract-summary">Loading...</div></div>
      <div class="card"><h3>Requirement Coverage</h3><div id="overview-requirement-coverage">Loading...</div></div>
      <div class="card"><h3>最近风险</h3><div id="overview-risk">Loading...</div></div>
    </div>
  </section>

  <section class="panel" id="tab-sprint">
    <h2>Current Sprint</h2>
    <div class="card" id="sprint-card">Loading...</div>
    <h2>Contract Summary</h2>
    <div class="card" id="contract-summary-card">Loading...</div>
    <h2>Autoresearch Impact</h2>
    <div class="card" id="autoresearch-impact-card">Loading...</div>
    <h2>Meta-Harness</h2>
    <div class="card" id="meta-harness-card">Loading...</div>
    <h2>PM Dispatch</h2>
    <div class="card" id="pm-dispatch-card">Loading...</div>
    <h2>Physical Operators</h2>
    <div class="card" id="physical-operators-card">Loading...</div>
    <h2>DeepResearch Human Search</h2>
    <div class="card" id="human-search-card">Loading...</div>
    <h2>DeepResearch Quality</h2>
    <div class="card" id="research-card">Loading...</div>
    <h2>Pane Assignments</h2>
    <div class="card" id="panes-card">Loading...</div>
  </section>

  <section class="panel" id="tab-main">
    <h2>物理算子状态监控 (Physical Operators)</h2>
    <div class="card" id="operator-metrics-container">Loading...</div>
    <div class="card" style="margin-top: 1rem; padding: 0.85rem; background: rgba(255, 252, 244, 0.48); display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; border-radius: 18px; border: 1px solid var(--line);">
      <div>
        <label style="font-weight:900; font-size:0.85rem; margin-right:0.4rem;">角色过滤:</label>
        <select id="op-filter-role" onchange="window.opFilterRole=this.value; renderOperatorsPage();" style="padding:0.4rem; border-radius:8px; border:1px solid var(--line); font-weight:800; background: rgba(255, 255, 255, 0.76); color: var(--ink);">
          <option value="all">全部角色</option>
          <option value="planner">Planner</option>
          <option value="builder">Builder</option>
          <option value="evaluator">Evaluator</option>
        </select>
      </div>
      <div>
        <label style="font-weight:900; font-size:0.85rem; margin-right:0.4rem;">状态过滤:</label>
        <select id="op-filter-state" onchange="window.opFilterState=this.value; renderOperatorsPage();" style="padding:0.4rem; border-radius:8px; border:1px solid var(--line); font-weight:800; background: rgba(255, 255, 255, 0.76); color: var(--ink);">
          <option value="all">全部状态</option>
          <option value="idle">Idle (空闲)</option>
          <option value="leased">Leased (已租用)</option>
          <option value="busy">Busy/Running (忙碌)</option>
          <option value="disabled">Disabled (已禁用)</option>
        </select>
      </div>
      <div style="flex-grow: 1;">
        <input type="text" id="op-search" placeholder="搜索算子 ID、模型、Sprint..." oninput="window.opSearch=this.value; renderOperatorsPage();" style="width: 100%; max-width: 320px; padding:0.45rem 0.8rem; border-radius:8px; border:1px solid var(--line); font-weight:800; background: rgba(255, 255, 255, 0.76); color: var(--ink);" />
      </div>
    </div>
    <div id="operator-cards-container" style="margin-top: 1rem;">Loading...</div>
    <h2 style="margin-top: 2rem;">最近执行结果 (Operator Results)</h2>
    <div class="card" id="operator-results-detailed">Loading...</div>
  </section>

  <section class="panel" id="tab-lab">
    <h2>Headless Pool 执行监控 (builder-lab + multi-task)</h2>
    <div class="card" id="pane-metrics-container">Loading...</div>
    <div class="card" id="pane-pool-contract-card" style="margin-top: 1rem;">Loading...</div>
    <div class="card" style="margin-top: 1rem; padding: 0.85rem; background: rgba(255, 252, 244, 0.48); display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; border-radius: 18px; border: 1px solid var(--line);">
      <div>
        <label style="font-weight:900; font-size:0.85rem; margin-right:0.4rem;">状态过滤:</label>
        <select id="pane-filter-state" onchange="window.paneFilterState=this.value; renderPanesPage();" style="padding:0.4rem; border-radius:8px; border:1px solid var(--line); font-weight:800; background: rgba(255, 255, 255, 0.76); color: var(--ink);">
          <option value="all">全部状态</option>
          <option value="idle">Idle (空闲)</option>
          <option value="reusable_idle">Reusable Idle (可复用历史壳)</option>
          <option value="historical_active">Historical Active (当前选中的历史壳)</option>
          <option value="leased">Leased (已租用)</option>
          <option value="running">Running command (执行中)</option>
        </select>
      </div>
      <div style="flex-grow: 1;">
        <input type="text" id="pane-search" placeholder="搜索 Pane ID、当前命令、标题、Lease 任务..." oninput="window.paneSearch=this.value; renderPanesPage();" style="width: 100%; max-width: 320px; padding:0.45rem 0.8rem; border-radius:8px; border:1px solid var(--line); font-weight:800; background: rgba(255, 255, 255, 0.76); color: var(--ink);" />
      </div>
    </div>
    <div id="pane-grid-container" style="margin-top: 1rem;">Loading...</div>
  </section>

  <section class="panel" id="tab-events">
    <h2>Recent Events</h2>
    <div class="card" id="events-card">Loading...</div>
  </section>

  <section class="panel" id="tab-knowledge">
    <div class="knowledge-shell">
      <div class="knowledge-hero">
        <div class="card">
          <div class="eyebrow">Knowledge Desk</div>
          <h2 class="knowledge-title">知识库工作台</h2>
          <p class="muted">这里看 Obsidian vault、上传入口、Mirage/QMD 检索底座是否可用。优先展示能不能用和下一步去哪操作，详细健康信息放下面。</p>
          <div class="status-strip" id="knowledge-summary">Loading...</div>
        </div>
        <div class="card">
          <h3>当前路径</h3>
          <div class="codebox">Vault  ~/Knowledge
Raw    ~/Knowledge/_raw
Upload http://127.0.0.1:8788
Config http://127.0.0.1:8789/setup</div>
        </div>
      </div>

      <div class="card">
        <h2>常用动作</h2>
        <div class="action-grid">
          <div class="action-card">
            <div><h3>上传资料</h3><div class="muted">粘贴网页、批量上传 PDF/图片/Markdown 到 _raw。</div></div>
            <a class="btn primary" href="http://127.0.0.1:8788" target="_blank" rel="noreferrer">打开上传页</a>
          </div>
          <div class="action-card">
            <div><h3>配置知识库</h3><div class="muted">修改 vault、QMD、Mirage、Drive、模型和 Key。</div></div>
            <a class="btn" href="http://127.0.0.1:8789/setup" target="_blank" rel="noreferrer">打开配置页</a>
          </div>
          <div class="action-card">
            <div><h3>手动提取</h3><div class="muted">立即让 wiki ingest 处理 raw 目录。</div></div>
            <button class="btn" onclick="copyText('solar-harness wiki ingest --vault ~/Knowledge')">复制命令</button>
          </div>
          <div class="action-card">
            <div><h3>语义索引</h3><div class="muted">更新 QMD semantic index，用于更好的检索。</div></div>
            <button class="btn" onclick="copyText('qmd embed -c solar-wiki')">复制命令</button>
          </div>
          <div class="action-card">
            <div><h3>订阅中心</h3><div class="muted">维护 YouTube、热点社交媒体和 GitHub 趋势分类。</div></div>
            <a class="btn primary" href="/knowledge/subscriptions-view" target="_blank" rel="noreferrer">打开订阅中心</a>
          </div>
        </div>
      </div>

      <div class="health-grid">
        <div class="card"><h2>采集 / 提取进展</h2><div id="knowledge-progress-card">Loading...</div></div>
        <div class="card"><h2>Reasoning Packet 路由</h2><div id="knowledge-routing-card">Loading...</div></div>
        <div class="card"><h2>Obsidian Wiki 健康</h2><div id="wiki-card">Loading...</div></div>
        <div class="card"><h2>Mirage / QMD 健康</h2><div id="mirage-card">Loading...</div></div>
      </div>
    </div>
  </section>

  <section class="panel" id="tab-assets">
    <h2>知识资产包</h2>
    <div class="card">
      <p class="muted">展示已经导出到知识库的 accepted sprint package，并把 accepted.md、dispatch、planning.html、prd.html、plan/handoff/eval 等源产物作为可点击资产暴露出来。</p>
      <div class="actions">
        <button class="btn primary" onclick="refreshAssets(true)">刷新资产包</button>
        <a class="btn" href="/assets" target="_blank" rel="noreferrer">打开 JSON</a>
        <button class="btn" onclick="copyText('~/Knowledge/_raw/solar-harness/accepted')">复制 accepted 目录</button>
      </div>
    </div>
    <div class="card"><div id="assets-summary">Loading...</div></div>
    <div id="assets-card">Loading...</div>
  </section>

  <section class="panel" id="tab-upload">
    <h2>上传文档 / 网页内容</h2>
    <div class="card">
      <p class="muted">这个标签对接现有 `wiki capture-server`。可粘贴网页内容保存为 Markdown，也可多选 PDF/图片/文本文件复制到 Knowledge/_raw，后续由知识库自动提取。</p>
      <div class="actions">
        <a class="btn primary" href="http://127.0.0.1:8788" target="_blank" rel="noreferrer">新窗口打开上传页</a>
        <button class="btn" onclick="copyText('solar-harness wiki capture-server start --open')">复制启动命令</button>
        <button class="btn" onclick="copyText('~/Knowledge/_raw')">复制 Raw 目录</button>
      </div>
      <iframe class="embed" src="http://127.0.0.1:8788" title="Solar Wiki Upload"></iframe>
    </div>
  </section>

  <section class="panel" id="tab-config">
    <h2>Solar 配置中心</h2>
    <div class="card">
      <p class="muted">统一修改模型、并发、Wiki、QMD、Mirage、Google Drive 和 API Key。敏感值只写入本机 secrets 文件，状态页不展示明文。</p>
      <div class="actions">
        <a class="btn primary" href="http://127.0.0.1:8789/setup" target="_blank" rel="noreferrer">打开配置中心</a>
        <button class="btn" onclick="copyText('solar-config-ui start --open')">复制启动命令</button>
      </div>
      <iframe class="embed" src="http://127.0.0.1:8789/setup" title="Solar Config UI"></iframe>
    </div>
  </section>

  <section class="panel" id="tab-integrations">
    <h2>外部集成健康</h2>
    <div class="card">
      <p class="muted">检查历史接入的开源/外部项目是否真的安装、配置、运行、索引并被 Solar 默认使用。这里不展示密钥，只展示可用性和断点原因。</p>
      <div class="actions">
        <button class="btn primary" onclick="refreshIntegrations(true)">刷新集成健康</button>
        <button class="btn" onclick="copyText('solar-harness integrations status --json --refresh')">复制诊断命令</button>
        <a class="btn" href="/integrations" target="_blank" rel="noreferrer">打开 JSON</a>
      </div>
    </div>
    <div class="card"><div id="integrations-summary">Loading...</div></div>
    <div class="card"><h3>自演化能力排序</h3><div id="evolution-card">Loading...</div></div>
    <div id="integrations-card">Loading...</div>
  </section>

  <section class="panel" id="tab-diagrams">
    <h2>Mermaid 架构图</h2>
    <div class="card">
      <p class="muted">直接浏览 Solar 里的 .mmd 文件，并用本地 vendored Mermaid 渲染。默认入口会打开刚才生成的 Solar 完整架构图。</p>
      <div class="actions">
        <a class="btn primary" href="/mermaid" target="_blank" rel="noreferrer">打开 Mermaid Viewer</a>
        <a class="btn" href="/mermaid/view?file={urllib.parse.quote(str(REPORTS_DIR / "solar-system-architecture-20260508.mmd"))}" target="_blank" rel="noreferrer">打开 Solar 完整架构图</a>
        <button class="btn" onclick="copyText('http://127.0.0.1:8765/mermaid')">复制访问地址</button>
      </div>
      <iframe class="embed" src="/mermaid" title="Solar Mermaid Viewer"></iframe>
    </div>
  </section>

  <section class="panel" id="tab-raw">
    <h2>Raw /status JSON</h2>
    <pre class="codebox" id="raw-card">Loading...</pre>
  </section>
</main>

<script>
function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}
function statusBadge(st) {
  const s = st || 'unknown';
  const cls = s === 'failed' || s === 'error' ? 'error-badge' : s === 'warn' ? 'warn-badge' : s;
  return '<span class="badge ' + esc(cls) + '">' + esc(s) + '</span>';
}
function fallbackBadge(level) {
  const s = level || 'N/A';
  const cls = s === 'L1' ? 'ok' : s === 'L2' ? 'warn' : s === 'L3' || s === 'L4' ? 'error-badge' : 'default';
  return '<span class="badge ' + esc(cls) + '">' + esc(s) + '</span>';
}
function levelBadge(level) {
  const s = level || 'unknown';
  const cls = s === 'closed_loop' ? 'ok' : s === 'default_usable' ? 'default' : s === 'basic_usable' ? 'warn' : 'missing';
  return '<span class="level-badge ' + esc(cls) + '">' + esc(s) + '</span>';
}
function formatBytes(n) {
  const v = Number(n || 0);
  if (v >= 1024 * 1024 * 1024) return (v / 1024 / 1024 / 1024).toFixed(1) + ' GB';
  if (v >= 1024 * 1024) return (v / 1024 / 1024).toFixed(1) + ' MB';
  if (v >= 1024) return (v / 1024).toFixed(1) + ' KB';
  return String(v) + ' B';
}
function sevClass(s) { return s === 'error' ? 'error' : s === 'warn' ? 'warn' : 'info'; }
function runtimeClass(s) { return s === 'active' ? 'info' : s === 'missing' ? 'error' : s === 'unknown' ? 'warn' : ''; }
function artifactLabel(a) {
  if (!a) return 'N/A';
  const st = a.state || 'N/A';
  if (a.mtime) {
    const d = new Date(a.mtime * 1000);
    return esc(st) + ' @ ' + esc(d.toLocaleTimeString());
  }
  return esc(st);
}
function modelCallCell(m) {
  m = m || {};
  const status = m.status || 'unknown';
  const model = m.model || 'N/A';
  const eventType = m.event_type || 'no_event';
  const ts = m.ts ? new Date(m.ts).toLocaleTimeString() : '';
  const dispatch = m.dispatch_id ? '<div class="tech-id">dispatch: ' + esc(clip(m.dispatch_id, 42)) + '</div>' : '';
  const err = m.error ? '<div class="warn">error: ' + esc(clip(m.error, 96)) + '</div>' : '';
  const preview = m.instruction_preview ? '<div class="muted">' + esc(clip(m.instruction_preview, 88)) + '</div>' : '';
  return '<div class="task-block">' +
    '<div class="task-head"><div>' + statusBadge(status) + '</div><div class="muted">' + esc(ts) + '</div></div>' +
    '<div class="kv-grid">' + kv('Event', eventType) + kv('Model', model) + '</div>' +
    dispatch + err + preview +
    '<div class="tech-id">private reasoning visible: ' + esc(String(!!m.private_reasoning_visible)) + '</div>' +
    '</div>';
}
function capabilityHealthCell(h) {
  h = h || {};
  const checks = h.checks || {};
  const order = ['model', 'knowledge', 'mirage_qmd', 'intent', 'skills', 'sandbox'];
  if (!order.some(k => checks[k])) {
    return '<div class="muted">No capability evidence.</div>';
  }
  return '<div class="capability-evidence">' + order.map(k => {
    const c = checks[k] || {};
    const label = c.label || k;
    const st = c.status || 'warn';
    const detail = c.detail || '';
    return '<div class="capability-chip">' +
      '<b>' + esc(label) + '</b>' +
      statusBadge(st) +
      '<span class="detail">' + esc(detail) + '</span>' +
      '</div>';
  }).join('') + '</div>';
}
function renderCapabilityHealthSummary(h) {
  h = h || {};
  const checks = h.checks || {};
  const order = ['model', 'knowledge', 'mirage_qmd', 'intent', 'skills', 'sandbox'];
  return '<div class="health-metrics">' +
    '<div class="mini-metric"><div class="kv-label">Overall</div><span class="num">' + esc(h.status || 'unknown') + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Updated</div><span class="num">' + esc((h.updated_at || 'N/A').slice(11, 19) || 'N/A') + '</span></div>' +
    '</div>' +
    '<div class="capability-evidence">' + order.map(k => {
      const c = checks[k] || {};
      return '<div class="capability-chip">' +
        '<b>' + esc(c.label || k) + '</b>' +
        statusBadge(c.status || 'warn') +
        '<span class="detail">' + esc(c.detail || '-') + '</span>' +
        '</div>';
    }).join('') + '</div>';
}
function renderPmDispatches(data, compact) {
  data = data || {};
  const items = data.items || [];
  const latest = data.latest || {};
  if (!items.length) {
    return '<div class="muted">暂无 PM 正式派单记录。</div>';
  }
  if (compact) {
    const submittedAt = latest.submitted_at ? new Date(latest.submitted_at).toLocaleTimeString() : 'N/A';
    return '<div class="health-metrics">' +
      '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">' + esc(data.status || 'unknown') + '</span></div>' +
      '<div class="mini-metric"><div class="kv-label">Count</div><span class="num">' + esc(data.count || items.length || 0) + '</span></div>' +
      '<div class="mini-metric"><div class="kv-label">Mode</div><span class="num">' + esc(latest.mode || 'N/A') + '</span></div>' +
      '<div class="mini-metric"><div class="kv-label">Target</div><span class="num">' + esc(latest.target || 'N/A') + '</span></div>' +
      '</div>' +
      '<div class="muted">最新：' + esc(latest.sprint_id || latest.task_id || 'N/A') +
      ' · ' + esc(latest.status || 'unknown') + ' · ' + esc(submittedAt) + '</div>';
  }
  return '<div class="health-metrics">' +
    '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">' + esc(data.status || 'unknown') + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Count</div><span class="num">' + esc(data.count || items.length || 0) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Source</div><span class="num">' + esc((data.source || '').split('/').slice(-2).join('/') || 'N/A') + '</span></div>' +
    '</div>' +
    '<table><tr><th>Sprint</th><th>Mode</th><th>Target</th><th>Status</th><th>Submitted</th></tr>' +
    items.map(item => {
      const submitted = item.submitted_at ? new Date(item.submitted_at).toLocaleString() : 'N/A';
      return '<tr>' +
        '<td>' + esc(item.sprint_id || item.task_id || '-') + '</td>' +
        '<td>' + esc(item.mode || '-') + '</td>' +
        '<td>' + esc(item.target || '-') + '</td>' +
        '<td>' + statusBadge(item.status || 'unknown') + '</td>' +
        '<td>' + esc(submitted) + '</td>' +
      '</tr>';
    }).join('') + '</table>';
}
function renderPhysicalOperators(data, compact) {
  data = data || {};
  const items = data.items || [];
  const alerts = data.alerts || [];
  const recentResults = data.recent_results || [];
  if (data.status === 'missing') {
    return '<div class="muted">physical-operators.json 缺失。</div>';
  }
  if (!items.length && !data.count) {
    return '<div class="muted">暂无物理算子记录。</div>';
  }
  const roles = Object.entries(data.roles || {}).map(([role, count]) => role + ':' + count).join(' · ') || 'N/A';
  if (compact) {
    return '<div class="health-metrics">' +
      '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">' + esc(data.status || 'unknown') + '</span></div>' +
      '<div class="mini-metric"><div class="kv-label">Dispatchable</div><span class="num">' + esc((data.dispatchable ?? 0) + '/' + (data.count ?? 0)) + '</span></div>' +
      '<div class="mini-metric"><div class="kv-label">Busy</div><span class="num">' + esc(data.busy ?? 0) + '</span></div>' +
      '<div class="mini-metric"><div class="kv-label">Available</div><span class="num">' + esc((data.available ?? 0) + '/' + (data.enabled ?? 0)) + '</span></div>' +
      '</div>' +
      '<div class="muted">roles: ' + esc(roles) + '</div>' +
      (alerts.length ? '<div class="warn">alerts: ' + esc(alerts.map(a => a.operator_id + ':' + a.runtime_state).join(' · ')) + '</div>' : '') +
      (recentResults.length ? '<div class="muted">latest result: ' + esc((recentResults[0].operator_id || '-') + ' · ' + (recentResults[0].status || '-')) + '</div>' : '');
  }
  return '<div class="health-metrics">' +
    '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">' + esc(data.status || 'unknown') + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Total</div><span class="num">' + esc(data.count ?? 0) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Dispatchable</div><span class="num">' + esc(data.dispatchable ?? 0) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Busy</div><span class="num">' + esc(data.busy ?? 0) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Enabled</div><span class="num">' + esc(data.enabled ?? 0) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Available</div><span class="num">' + esc(data.available ?? 0) + '</span></div>' +
    '</div>' +
    '<div class="muted">roles: ' + esc(roles) + '</div>' +
    (alerts.length ? '<div class="warn" style="margin:.6rem 0">Alerts: ' + esc(alerts.map(a => a.operator_id + ':' + a.runtime_state).join(' · ')) + '</div>' : '<div class="muted" style="margin:.6rem 0">Alerts: none</div>') +
    '<div class="op-list">' +
    '  <div class="op-row" style="grid-template-columns: 1.5fr 1fr 1.5fr 1fr 1fr; background: transparent; border: none; padding: 0.2rem 1.2rem; box-shadow: none; transform: none; pointer-events: none; margin-bottom: -0.4rem;">' +
    '    <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">Operator</div>' +
    '    <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">Role</div>' +
    '    <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">Backend</div>' +
    '    <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">State</div>' +
    '    <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">Sprint</div>' +
    '  </div>' +
    items.map(item => {
      let statusClass = "missing";
      let statusLabel = item.runtime_state || "unknown";
      if (!item.enabled) {
        statusClass = "missing";
        statusLabel = "disabled";
      } else if (item.runtime_state === 'idle') {
        statusClass = "ok";
      } else if (item.runtime_state === 'leased' || item.runtime_state === 'running') {
        statusClass = "default";
      } else if (item.runtime_state === 'disabled') {
        statusClass = "missing";
      } else {
        statusClass = "warn";
      }
      return '<div class="op-row" style="grid-template-columns: 1.5fr 1fr 1.5fr 1fr 1fr; padding: 0.8rem 1.2rem; margin-top: 0.5rem; gap: 0.5rem;">' +
        '<div><b style="font-size:0.95rem; color:#ffffff;">' + esc(item.operator_id || '-') + '</b></div>' +
        '<div><span class="badge default" style="background: rgba(255,255,255,0.04); font-size:0.78rem;">' + esc(item.role || '-') + '</span></div>' +
        '<div style="font-size:0.82rem;">' + esc(item.backend || '-') + '</div>' +
        '<div><span class="level-badge ' + statusClass + '" style="font-size:0.78rem;">' + statusLabel + '</span></div>' +
        '<div class="tech-id" style="font-size:0.78rem;">' + esc(item.sprint_id || '-') + '</div>' +
        '</div>';
    }).join('') + '</div>' +
    (recentResults.length ? '<h3 style="margin-top:.9rem">Recent Results</h3><table><tr><th>Operator</th><th>Task</th><th>Status</th><th>Finished</th></tr>' +
      recentResults.map(item => '<tr>' +
        '<td>' + esc(item.operator_id || '-') + '</td>' +
        '<td>' + esc(item.task_id || '-') + '</td>' +
        '<td>' + statusBadge(item.status || 'unknown') + '</td>' +
        '<td>' + esc(item.finished_at || item.started_at || '-') + '</td>' +
      '</tr>').join('') + '</table>' : '<div class="muted" style="margin-top:.8rem">Recent Results: none</div>');
}
function clip(v, limit) {
  const s = String(v || '').replace(/\\s+/g, ' ').trim();
  return s.length > limit ? s.slice(0, limit - 1).trim() + '…' : s;
}
function summaryList(text) {
  const s = String(text || '').replace(/\\s+/g, ' ').trim();
  if (!s) return '';
  let parts = s
    .split(new RegExp('[。；;\\\\n]+'))
    .map(x => x.trim())
    .filter(Boolean);
  if (parts.length <= 1 && s.includes('、')) {
    parts = s.split('、').map(x => x.trim()).filter(Boolean);
  }
  if (parts.length <= 1 && s.includes('，')) {
    parts = s.split('，').map(x => x.trim()).filter(Boolean);
  }
  parts = parts.slice(0, 6).map(x => clip(x, 96));
  return '<ul class="summary-list">' + parts.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>';
}
function kv(label, value) {
  return '<div class="kv"><div class="kv-label">' + esc(label) + '</div><div class="kv-value">' + esc(value || '-') + '</div></div>';
}
function sprintBlock(meta, sid, options = {}) {
  meta = meta || {};
  const title = meta.title || sid || 'N/A';
  const status = meta.status ? statusBadge(meta.status) : '';
  const ua = meta.understand_anything_summary || {};
  const detailItems = options.compact ? [
    kv('Phase', meta.phase || '-'),
    kv('Handoff', meta.handoff_to || '-')
  ] : [
    kv('Phase', meta.phase || '-'),
    kv('Handoff', meta.handoff_to || '-'),
    kv('Lane', meta.lane || '-'),
    kv('Priority', meta.priority || '-'),
    kv('Physical Plan', meta.execution_plan_summary || 'N/A'),
    kv('Understand Anything', ua.summary || 'N/A')
  ];
  const details = detailItems.join('');
  const id = sid ? '<div class="tech-id">id: ' + esc(sid) + '</div>' : '';
  const uaPaths = !options.compact && ua.present
    ? '<div class="task-block" style="margin-top:0.8rem;"><div class="task-title" style="font-size:0.88rem;">Understand Anything</div>' +
      '<div class="kv-grid">' +
      kv('Node', ua.node_id || '-') +
      kv('Chunks', String((ua.chunks_completed || 0)) + '/' + String((ua.chunks_total || 0))) +
      kv('Resumed', ua.resumed ? 'yes' : 'no') +
      '</div>' +
      '<div class="research-path" style="margin-top:0.45rem;"><span>kg=' + esc(ua.knowledge_graph_path || 'N/A') + '</span><span class="research-path-actions">' +
      (ua.knowledge_graph_path
        ? '<a href="' + fileOpenUrl(ua.knowledge_graph_path) + '" target="_blank" rel="noopener">打开</a><a href="' + fileViewUrl(ua.knowledge_graph_path) + '" target="_blank" rel="noopener">查看</a>'
        : '<span class="muted">missing</span>') +
      '</span></div>' +
      '</div>'
    : '';
  return '<div class="task-block">' +
    '<div class="task-head"><div class="task-title">' + esc(title) + '</div><div>' + status + '</div></div>' +
    '<div class="kv-grid">' + details + '</div>' +
    (options.hideDescription ? '' : summaryList(meta.description || '')) +
    uaPaths +
    (options.hideId ? '' : id) +
    '</div>';
}
function taskCell(meta, sid) {
  return sprintBlock(meta, sid, {compact: true, hideDescription: true});
}
function copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {});
}
function fileOpenUrl(path) {
  return '/file/open?path=' + encodeURIComponent(path || '');
}
function fileViewUrl(path) {
  return '/file/view?path=' + encodeURIComponent(path || '');
}
function researchPathLink(label, path, exists) {
  if (!path) {
    return '<div class="research-path"><span>' + esc(label) + '</span><span class="muted">missing</span></div>';
  }
  const state = exists ? '打开' : 'missing';
  const link = exists
    ? '<a href="' + fileOpenUrl(path) + '" target="_blank" rel="noopener">打开</a><a href="' + fileViewUrl(path) + '" target="_blank" rel="noopener">查看</a>'
    : '<span class="muted">missing</span>';
  return '<div class="research-path"><span>' + esc(label) + ': ' + esc(path) + '</span><span class="research-path-actions">' + link + '</span></div>';
}
function renderPaneMatrix(cardId, screen) {
  const panes = (screen && screen.panes) || [];
  if (!panes.length) {
    document.getElementById(cardId).textContent = 'No panes found.';
    return;
  }
  let t = '<div class="refresh">' + esc((screen && screen.note) || '') + '</div>';
  t += '<table><tr><th>Pane</th><th>Role</th><th>Runtime</th><th>能力证据</th><th>模型调用</th><th>当前任务</th><th>Artifact</th><th>Title</th></tr>';
  panes.forEach(p => {
    t += '<tr><td>' + esc(p.target || '-') + '</td>' +
         '<td>' + esc(p.role || '-') + '</td>' +
         '<td class="' + runtimeClass(p.runtime_state) + '">' + esc(p.runtime_state || '-') + '</td>' +
         '<td>' + capabilityHealthCell(p.capability_health || {}) + '</td>' +
         '<td>' + modelCallCell(p.model_call) + '<div style="margin-top:0.25rem;"><button class="btn" style="padding:3px 7px;font-size:0.7rem;" onclick="loadPaneModelCall(\\'' + esc(p.target || '') + '\\')">查调用</button></div><div class="muted" id="pane-call-' + esc((p.target || '').replace(/[^A-Za-z0-9_.-]/g, '_')) + '" style="font-size:0.72rem;margin-top:0.2rem;"></div></td>' +
         '<td>' + taskCell(p.assignment_meta, p.assignment) + '</td>' +
         '<td>' + artifactLabel(p.artifact) + '</td>' +
         '<td>' + esc(p.title || '-') + '</td></tr>';
  });
  t += '</table>';
  document.getElementById(cardId).innerHTML = t;
}

window.loadPaneModelCall = function(target) {
  const safeId = String(target || '').replace(/[^A-Za-z0-9_.-]/g, '_');
  const el = document.getElementById('pane-call-' + safeId);
  if (el) el.textContent = 'loading...';
  fetch('/api/pane-model-call?target=' + encodeURIComponent(target || '') + '&ts=' + Date.now(), {cache: 'no-store'})
    .then(r => r.json())
    .then(data => {
      const call = (data && data.model_call) || {};
      const pane = (data && data.pane) || {};
      const tokens = call.tokens && Object.keys(call.tokens).length ? JSON.stringify(call.tokens) : 'N/A';
      const text = [
        'status=' + (call.status || 'unknown'),
        'provider=' + (call.provider || pane.backend || 'N/A'),
        'model=' + (call.model || pane.model || call.model_flag || 'N/A'),
        'kernel=' + (call.operator_kernel || pane.operator_type || 'N/A'),
        'tokens=' + tokens
      ].join(' · ');
      if (el) el.textContent = text;
    })
    .catch(err => {
      if (el) el.textContent = 'error: ' + String(err);
    });
};
function renderList(obj) {
  if (!obj || typeof obj !== 'object') return '<div class="muted">N/A</div>';
  return '<table>' + Object.entries(obj).map(([k, v]) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(typeof v === 'object' ? JSON.stringify(v) : v) + '</td></tr>'
  ).join('') + '</table>';
}
function qmdDetail(qmd) {
  const d = (qmd && qmd.detail) || {};
  return {
    status: (qmd && qmd.status) || 'unknown',
    binary: (qmd && qmd.binary) || '',
    total: d.total || 'N/A',
    vectors: d.vectors || 'N/A',
    pending: d.pending || 'N/A',
    collection: d.collection || 'N/A'
  };
}
function renderMirageHealth(mirage) {
  mirage = mirage || {};
  const q = qmdDetail(mirage.qmd || {});
  const mounts = mirage.mounts || [];
  const ready = mounts.filter(m => m.ready).length;
  const drive = mirage.drive || {};
  const mountRows = mounts.map(m => {
    const state = m.ready ? 'ok' : (m.optional ? 'warn' : 'error');
    const reason = m.reason || m.status || m.adapter || m.physical_root || '';
    return '<div class="mount-row">' +
      '<div class="mount-path">' + esc(m.path || '-') + '</div>' +
      '<div>' + statusBadge(state) + '</div>' +
      '<div class="mount-reason">' + esc(reason || 'ready') + '</div>' +
      '</div>';
  }).join('');
  return '<div class="health-metrics">' +
    '<div class="mini-metric"><div class="kv-label">QMD</div><span class="num">' + esc(q.status) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Indexed</div><span class="num">' + esc(q.total) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Vectors</div><span class="num">' + esc(q.vectors) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Pending</div><span class="num">' + esc(q.pending) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Mounts</div><span class="num">' + ready + '/' + mounts.length + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Drive</div><span class="num">' + esc(drive.status || 'unknown') + '</span></div>' +
    '</div>' +
    '<h3>Mounts</h3><div class="mount-list">' + mountRows + '</div>' +
    '<details style="margin-top:0.85rem"><summary class="muted">查看原始 Mirage JSON</summary><pre class="codebox">' + esc(JSON.stringify(mirage, null, 2)) + '</pre></details>';
}
function renderRuntimeInterfaces(rt) {
  rt = rt || {};
  const dims = rt.dimensions || {};
  const rows = Object.keys(dims).map(k => {
    const d = dims[k] || {};
    return '<div class="mount-row">' +
      '<div class="mount-path">' + esc(k) + '</div>' +
      '<div>' + statusBadge(d.ok ? 'ok' : 'warn') + '</div>' +
      '<div class="mount-reason">' + esc(d.message || '-') + '</div>' +
      '</div>';
  }).join('');
  return '<div class="health-metrics">' +
    '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">' + esc(rt.status || 'unknown') + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Healthy</div><span class="num">' + esc((rt.healthy ?? 0) + '/' + (rt.total ?? 0)) + '</span></div>' +
    '</div><div class="mount-list">' + (rows || '<div class="muted">No runtime interface data.</div>') + '</div>';
}
function renderHumanSearch(hs, compact) {
  hs = hs || {};
  const items = hs.items || [];
  if (!items.length) {
    return '<div class="health-metrics">' +
      '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">idle</span></div>' +
      '<div class="mini-metric"><div class="kv-label">Waiting</div><span class="num">0</span></div>' +
      '</div><div class="muted">没有等待人工搜索的 DeepResearch DAG 节点。</div>';
  }
  const visible = compact ? items.slice(0, 2) : items;
  const cards = visible.map(item => {
    const ready = !!item.ready_to_import;
    const cmd = item.import_command || '';
    return '<div class="human-search-item ' + (ready ? 'ready' : '') + '">' +
      '<div class="human-search-title"><div><strong>' + esc(item.node_id || '-') + '</strong>' +
      '<div class="muted">' + esc(item.sprint_id || '-') + '</div></div>' +
      '<div>' + statusBadge(ready ? 'ok' : 'warn') + '</div></div>' +
      (compact ? '' : '<div class="muted">' + esc(clip(item.goal || '', 180)) + '</div>') +
      '<div class="kv-grid" style="margin-top:.65rem">' +
        kv('handoff', item.handoff_exists ? 'exists' : 'missing') +
        kv('results', item.results_exists ? 'ready' : 'waiting') +
        kv('provider', item.provider || 'human') +
      '</div>' +
      (compact ? '' : '<pre class="codebox" style="margin-top:.7rem">' +
        'Handoff: ' + esc(item.handoff_md || '-') + '\\n' +
        'Results: ' + esc(item.results_md || '-') + '\\n\\n' +
        esc(cmd || 'N/A') + '</pre>') +
      '<div class="copy-row">' +
        '<button class="btn" data-copy="' + esc(item.handoff_md || '') + '" onclick="copyText(this.dataset.copy)">复制 handoff</button>' +
        '<button class="btn" data-copy="' + esc(item.results_md || '') + '" onclick="copyText(this.dataset.copy)">复制 results 路径</button>' +
        '<button class="btn primary" data-copy="' + esc(cmd) + '" onclick="copyText(this.dataset.copy)">复制导入命令</button>' +
      '</div>' +
    '</div>';
  }).join('');
  return '<div class="health-metrics">' +
    '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">' + esc(hs.status || 'waiting') + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Waiting</div><span class="num">' + esc(hs.count || items.length) + '</span></div>' +
    '</div><div class="human-search-grid">' + cards +
    (compact && items.length > visible.length ? '<div class="muted">还有 ' + (items.length - visible.length) + ' 个等待项，打开 Sprint 标签查看。</div>' : '') +
    '</div>';
}
function renderResearchStatus(research, compact) {
  research = research || {};
  const runs = research.runs || [];
  const gates = research.quality_gates || [];
  if (!runs.length && !gates.length) {
    return '<div class="research-shell">' +
      '<div class="research-overview">' +
        '<div class="research-stat"><div class="kv-label">Status</div><strong>idle</strong></div>' +
        '<div class="research-stat"><div class="kv-label">Runs</div><strong>0</strong></div>' +
      '</div><div class="muted">还没有可展示的 DeepResearch research_eval 产物。</div></div>';
  }
  const latest = runs[runs.length - 1] || {};
  const latestCitation = latest.citation_accuracy == null ? 'N/A' : Math.round((latest.citation_accuracy || 0) * 100) + '%';
  const visible = compact ? runs.slice(-1) : runs;
  const cards = visible.map(run => {
    const artifacts = run.artifacts || {};
    const exists = run.artifact_exists || {};
    const status = run.status || 'unknown';
    const ok = status === 'passed';
    const citation = run.citation_accuracy == null ? 'N/A' : Math.round((run.citation_accuracy || 0) * 100) + '%';
    const runId = run.run_id || run.sid || '-';
    const shortRunId = run.short_run_id || String(runId).slice(0, 10);
    const taskTitle = run.task_title || run.task_description || run.sid || runId;
    const taskSub = (run.task_description && run.task_description !== taskTitle ? run.task_description + ' · ' : '') + 'run ' + shortRunId;
    return '<div class="research-run-card ' + (ok ? 'ok' : '') + '">' +
      '<div class="research-run-head">' +
        '<div><div class="research-run-title">' + esc(taskTitle) + '</div>' +
        '<div class="research-run-sub" title="' + esc(runId) + '">' + esc(taskSub) + '</div></div>' +
        '<div>' + statusBadge(ok ? 'ok' : 'warn') + '</div>' +
      '</div>' +
      '<div class="research-metric-row">' +
        '<div class="research-metric"><div class="kv-label">Words</div><b>' + esc(run.word_count ?? 'N/A') + '</b></div>' +
        '<div class="research-metric"><div class="kv-label">Tokens</div><b>' + esc(run.total_tokens ?? 'N/A') + '</b></div>' +
        '<div class="research-metric"><div class="kv-label">Citation</div><b>' + esc(citation) + '</b></div>' +
        '<div class="research-metric"><div class="kv-label">Sources</div><b>' + esc(run.source_count || 0) + '</b></div>' +
      '</div>' +
      (compact ? '' : '<div class="research-detail-grid">' +
        kv('Evidence', run.evidence_count || 0) +
        kv('Claims', run.claim_count || 0) +
        kv('AST Sections', run.report_ast_sections || 0) +
        kv('Usage Source', run.usage_source || 'N/A') +
        kv('Estimated', run.estimated === null || run.estimated === undefined ? 'N/A' : String(run.estimated)) +
        kv('State', run.state || 'unknown') +
        '<div><div class="kv-label">Fallback</div>' + fallbackBadge(run.fallback_level) + '</div>' +
        kv('Final MD', exists.final_md ? 'exists' : 'missing') +
      '</div><div class="research-paths">' +
        researchPathLink('final.md', artifacts.final_md, exists.final_md) +
        researchPathLink('report_ast', artifacts.report_ast, exists.report_ast) +
        researchPathLink('eval', artifacts.eval_json, exists.eval_json) +
      '</div><div class="copy-row">' +
        '<button class="btn" data-copy="' + esc(artifacts.final_md || '') + '" onclick="copyText(this.dataset.copy)">复制 final.md</button>' +
        '<button class="btn" data-copy="' + esc(artifacts.report_ast || '') + '" onclick="copyText(this.dataset.copy)">复制 ReportAST</button>' +
        '<button class="btn primary" data-copy="' + esc(artifacts.eval_json || '') + '" onclick="copyText(this.dataset.copy)">复制 Eval JSON</button>' +
      '</div>') +
    '</div>';
  }).join('');
  const visibleGates = compact ? gates.slice(-3) : gates;
  const gateCards = visibleGates.map(gate => {
    const ok = !!gate.ok;
    const status = gate.status || (ok ? 'ok' : 'missing');
    const errors = (gate.errors || []).slice(0, 2).join('; ');
    return '<div class="human-search-item ' + (ok ? 'ready' : '') + '">' +
      '<div class="human-search-title"><div><strong>' + esc(gate.node_id || '-') + '</strong>' +
      '<div class="muted">' + esc(gate.sid || gate.sprint_id || '-') + '</div></div><div>' + statusBadge(ok ? 'ok' : 'warn') + '</div></div>' +
      '<div class="health-metrics">' +
        '<div class="mini-metric"><div class="kv-label">Gate</div><span class="num">' + esc(status) + '</span></div>' +
        '<div class="mini-metric"><div class="kv-label">Verdict</div><span class="num">' + esc(gate.verdict || '-') + '</span></div>' +
        '<div class="mini-metric"><div class="kv-label">Auto</div><span class="num">' + (gate.auto_run ? 'yes' : 'no') + '</span></div>' +
      '</div>' +
      (compact ? '' : '<div class="muted">' + esc(gate.goal || '') + '</div>' +
        (errors ? '<pre class="codebox" style="margin-top:.7rem">' + esc(errors) + '</pre>' : '')) +
    '</div>';
  }).join('');
  return '<div class="research-shell">' +
    '<div class="research-overview">' +
      '<div class="research-stat"><div class="kv-label">Status</div><strong>' + esc(research.status || 'unknown') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Runs</div><strong>' + esc(research.count || runs.length) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Latest Words</div><strong>' + esc(latest.word_count ?? 'N/A') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Latest Tokens</div><strong>' + esc(latest.total_tokens ?? 'N/A') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Citation</div><strong>' + esc(latestCitation) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Fallback</div><strong>' + esc(latest.fallback_level || 'N/A') + '</strong></div>' +
    '</div>' +
    '<div class="research-section-title">' + (compact ? 'Latest Run' : 'Research Runs') + '</div>' +
    '<div class="research-run-list">' + cards + '</div>' +
    (gateCards ? '<div class="research-section-title">Quality Gates</div><div class="human-search-grid">' + gateCards + '</div>' : '') +
    '</div>';
}
function renderKnowledgeRouting(routing, compact) {
  routing = routing || {};
  const items = routing.items || [];
  if (routing.status === 'missing') {
    return '<div>' + statusBadge('warn') + ' <span class="muted">Tech Hotspot Radar DB 未初始化。</span></div>' +
      '<div class="tech-id">' + esc(routing.db_path || 'N/A') + '</div>';
  }
  const routeCounts = routing.route_counts || {};
  const routeText = Object.entries(routeCounts).map(([k, v]) => k + ':' + v).join(' · ') || 'N/A';
  const head = '<div class="health-metrics">' +
    '<div class="mini-metric"><div class="kv-label">Status</div><span class="num">' + esc(routing.status || 'unknown') + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Packets</div><span class="num">' + esc(routing.total_packets || 0) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Premium</div><span class="num">' + esc(routing.premium_allowed || 0) + '</span></div>' +
    '<div class="mini-metric"><div class="kv-label">Embedding OK</div><span class="num">' + esc(routing.embedding_unchanged || 0) + '</span></div>' +
    '</div>';
  if (compact) {
    const latest = items[0] || {};
    return head +
      '<div class="muted">routes: ' + esc(routeText) + '</div>' +
      '<div class="muted">latest: ' + esc(latest.packet_id || 'N/A') + ' · ' + esc(latest.route || 'N/A') + ' · ' + esc(latest.default_model_family || 'N/A') + '</div>';
  }
  const missing = (routing.missing_columns || []).length
    ? '<div class="warn">missing columns: ' + esc((routing.missing_columns || []).join(', ')) + '</div>'
    : '';
  if (!items.length) {
    return head + missing + '<div class="muted">暂无 reasoning packet。先运行 Tech Hotspot Radar reasoning pipeline。</div>' +
      '<div class="tech-id">' + esc(routing.db_path || 'N/A') + '</div>';
  }
  return head + missing +
    '<div class="muted">routes: ' + esc(routeText) + '</div>' +
    '<table><tr><th>Packet</th><th>Type</th><th>Route</th><th>Model</th><th>Premium</th><th>Embedding</th></tr>' +
    items.map(item => '<tr>' +
      '<td><span class="tech-id">' + esc(item.packet_id || '-') + '</span></td>' +
      '<td>' + esc(item.packet_type || '-') + '</td>' +
      '<td>' + statusBadge(item.route === 'premium_reasoner' ? 'warn' : 'ok') + ' ' + esc(item.route || '-') + '</td>' +
      '<td>' + esc(item.default_model_family || 'N/A') + '</td>' +
      '<td>' + esc(item.premium_allowed ? 'yes' : 'no') + '<div class="muted">' + esc(clip(item.premium_reason || '', 72)) + '</div></td>' +
      '<td>' + esc(item.embedding_route || 'N/A') + '</td>' +
    '</tr>').join('') + '</table>' +
    '<div class="tech-id">' + esc(routing.db_path || 'N/A') + '</div>';
}
function renderAutoresearchImpact(impact, compact) {
  impact = impact || {};
  const items = impact.items || [];
  const trend = impact.trend || {};
  if (!items.length) {
    return '<div class="research-shell">' +
      '<div class="research-overview">' +
        '<div class="research-stat"><div class="kv-label">Status</div><strong>idle</strong></div>' +
        '<div class="research-stat"><div class="kv-label">Triggers</div><strong>0</strong></div>' +
      '</div><div class="muted">还没有 autoresearch optimizer 触发记录；等待 dispatch 写入 status.json artifacts。</div></div>';
  }
  const latest = impact.latest || items[0] || {};
  const visible = compact ? items.slice(0, 1) : items;
  const cards = visible.map(item => {
    const level = item.trigger_level || 'advisory';
    const strong = level === 'strong';
    const failed = (item.failed_conditions || []).slice(0, compact ? 2 : 5);
    const effects = (item.expected_effect || []).slice(0, 3).join(', ') || 'N/A';
    const measures = (item.must_measure || []).slice(0, 3).join(', ') || 'N/A';
    const subtitle = (item.role || 'unknown') + ' · round ' + (item.round ?? 0) + ' · eval ' + (item.eval_verdict || 'N/A');
    return '<div class="impact-card ' + (strong ? 'strong' : '') + '">' +
      '<div class="impact-title">' +
        '<div><strong>' + esc(item.task_description || item.sid || 'N/A') + '</strong>' +
        '<div class="research-run-sub">' + esc(subtitle) + '</div></div>' +
        '<div>' + statusBadge(strong ? 'warn' : 'ok') + '</div>' +
      '</div>' +
      '<div class="research-metric-row">' +
        '<div class="research-metric"><div class="kv-label">Trigger</div><b>' + esc(level) + '</b></div>' +
        '<div class="research-metric"><div class="kv-label">Status</div><b>' + esc(item.status || 'N/A') + '</b></div>' +
        '<div class="research-metric"><div class="kv-label">Errors</div><b>' + esc(item.error_count ?? 0) + '</b></div>' +
      '</div>' +
      (failed.length ? '<div class="impact-note"><b>Failed conditions:</b> ' + esc(failed.join('; ')) + '</div>' : '') +
      (compact ? '' : '<div class="research-detail-grid">' +
        kv('Expected Effect', effects) +
        kv('Must Measure', measures) +
        kv('Recorded', item.recorded_at || 'N/A') +
        kv('Sprint', item.sid || 'N/A') +
      '</div>') +
    '</div>';
  }).join('');
  return '<div class="research-shell">' +
    '<div class="research-overview">' +
      '<div class="research-stat"><div class="kv-label">Status</div><strong>' + esc(impact.status || 'unknown') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Triggers</div><strong>' + esc(impact.count || items.length) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Strong</div><strong>' + esc(impact.strong_count || 0) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">FAIL Verdict</div><strong>' + esc(impact.fail_verdict_count || 0) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Latest Role</div><strong>' + esc(latest.role || 'N/A') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Latest Round</div><strong>' + esc(latest.round ?? 'N/A') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Effect</div><strong>' + esc(trend.effect_status || 'insufficient') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Pass After</div><strong>' + esc(trend.pass_after_trigger || 0) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Still Failing</div><strong>' + esc(trend.still_failing || 0) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Avg Round</div><strong>' + esc(trend.avg_round ?? 0) + '</strong></div>' +
    '</div>' +
    '<div class="impact-note">Trend is observational: it counts outcomes after optimizer triggers, not causal proof.</div>' +
    '<div class="research-section-title">' + (compact ? 'Latest Optimizer Trigger' : 'Optimizer Triggers') + '</div>' +
    '<div class="impact-list">' + cards + '</div>' +
	    '</div>';
}
function renderMetaHarness(meta, compact) {
  meta = meta || {};
  const store = meta.store || {};
  const pareto = meta.pareto || {};
  const runs = meta.runs || {};
  const safety = meta.safety || {};
  const latest = meta.latest_command || {};
  const commandRows = meta.commands || {};
  const status = meta.status || 'unknown';
  const note = safety.coordinator_autorun === false
    ? 'Controlled provider: coordinator does not autorun it; run/apply stay dry-run unless --execute is explicit.'
    : 'Check coordinator autorun policy before using.';
  const actions = compact ? '' :
    '<div class="copy-row">' +
      '<button class="btn" data-copy="' + esc(commandRows.status || 'solar-harness meta-harness status --json') + '" onclick="copyText(this.dataset.copy)">复制 status</button>' +
      '<button class="btn" data-copy="' + esc(commandRows.run_dry || 'solar-harness meta-harness run 3 hooks --json') + '" onclick="copyText(this.dataset.copy)">复制 dry-run</button>' +
      '<button class="btn" data-copy="' + esc(commandRows.apply_dry || 'solar-harness meta-harness apply <run_id> --json') + '" onclick="copyText(this.dataset.copy)">复制 apply dry-run</button>' +
    '</div>';
  const latestLine = latest && latest.subcommand
    ? '<div class="impact-note"><b>Latest command:</b> ' + esc(latest.subcommand) + ' · ' + esc(latest.mode || 'N/A') + ' · executed=' + esc(latest.executed === true ? 'true' : 'false') + '</div>'
    : '';
  return '<div class="research-shell">' +
    '<div class="research-overview">' +
      '<div class="research-stat"><div class="kv-label">Status</div><strong>' + esc(status) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Eval Set</div><strong>' + esc(store.evaluation_count ?? 0) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Pareto</div><strong>' + esc(pareto.pareto_count ?? 0) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Runs</div><strong>' + esc(runs.count ?? 0) + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Best</div><strong>' + esc(pareto.best_run_id || 'N/A') + '</strong></div>' +
      '<div class="research-stat"><div class="kv-label">Dry Run</div><strong>' + esc(safety.default_execution || 'N/A') + '</strong></div>' +
    '</div>' +
    '<div class="research-detail-grid">' +
      kv('Tool', (meta.tool || {}).path || 'N/A') +
      kv('Store', store.path || 'N/A') +
      kv('Proposer', store.proposer_model || 'N/A') +
      kv('Evaluator', store.evaluator_model || 'N/A') +
    '</div>' +
    '<div class="impact-note">' + esc(note) + '</div>' +
    latestLine +
    actions +
    '</div>';
}
function renderKnowledgeSummary(wiki, mirage) {
  const wikiReady = !!(wiki && wiki.ready);
  const mirageReady = !!(mirage && mirage.enabled);
  const qmdStatus = mirage && mirage.qmd && mirage.qmd.status ? mirage.qmd.status : 'unknown';
  const vault = (wiki && wiki.vault_path) || '~/Knowledge';
  return [
    '<div class="status-tile"><div class="kv-label">Wiki</div><strong>' + statusBadge(wikiReady ? 'ok' : 'warn') + '</strong></div>',
    '<div class="status-tile"><div class="kv-label">Mirage</div><strong>' + statusBadge(mirageReady ? 'ok' : 'warn') + '</strong></div>',
    '<div class="status-tile"><div class="kv-label">QMD</div><strong>' + esc(qmdStatus) + '</strong></div>',
    '<div class="status-tile"><div class="kv-label">Vault</div><strong class="path-text">' + esc(vault) + '</strong></div>'
  ].join('');
}
function renderKnowledgeProgress(progress) {
  progress = progress || {};
  const funnel = progress.funnel || {};
  const activity = progress.activity || {};
  const qmd = progress.qmd || {};
  const asr = progress.asr || {};
  const src = progress.sources || [];
  const blockers = progress.blockers || [];
  const actions = progress.next_actions || [];
  const latestRaw = activity.latest_raw_source || {};
  const latestRawStamp = ((latestRaw.latest || {}).mtime || 'N/A');
  const latestDispatch = activity.latest_dispatch || {};
  const latestKnowledge = activity.latest_knowledge_page || {};
  const blockerRows = blockers.map(b => {
    const level = b.level || 'pending';
    return '<li>' + statusBadge(level) + ' <b>' + esc(b.title || 'N/A') + '</b><br><span class="muted">' + esc(b.detail || '') + '</span></li>';
  }).join('');
  const actionRows = actions.map(a => '<li>' + esc(a) + '</li>').join('');
  const sourceRows = src.slice(0, 6).map(s => {
    const latest = (s.latest || {}).mtime || 'N/A';
    return '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.files || 0) + '</td><td class="path-text">' + esc(latest) + '</td></tr>';
  }).join('');
  return '' +
    '<div class="impact-note"><b>一句话：</b>' + esc(progress.headline || 'N/A') + '</div>' +
    '<div class="status-strip">' +
      '<div class="status-tile"><div class="kv-label">状态</div><strong>' + statusBadge(progress.status || 'unknown') + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">待处理</div><strong>' + esc(funnel.pending || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">失败</div><strong>' + esc(funnel.failed || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">阻塞</div><strong>' + esc(funnel.blocked || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">ASR fallback</div><strong>' + esc(funnel.asr_waiting || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">ASR缓存</div><strong>' + esc(formatBytes(asr.audio_cache_bytes || 0)) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">近24h知识页</div><strong>' + esc(funnel.recent_knowledge_24h || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">QMD</div><strong>' + esc(qmd.status || 'unknown') + '</strong></div>' +
    '</div>' +
    '<div class="kv-grid">' +
      kv('处理漏斗', '总任务 ' + (funnel.total_dispatch || 0) + ' · 已完成 ' + (funnel.completed || 0) + ' · 未知历史状态 ' + (funnel.unknown || 0)) +
      kv('最近原始输入', (latestRaw.name ? latestRaw.name + ' · ' + latestRawStamp : 'N/A')) +
      kv('最新派单', ((latestDispatch || {}).path || 'N/A')) +
      kv('最新知识页', ((latestKnowledge || {}).path || 'N/A')) +
      kv('QMD 语义索引', 'indexed ' + (qmd.indexed || 0) + ' · pending ' + (qmd.pending === undefined ? 'N/A' : qmd.pending)) +
      kv('ASR fallback', '等待 ' + (funnel.asr_waiting || 0) + ' · 阻塞 ' + (funnel.asr_blocking || 0) + ' · 策略 ' + (funnel.asr_policy || 'fallback_non_blocking')) +
      kv('ASR 缓存目录', formatBytes(asr.audio_cache_bytes || 0) + ' · ' + (asr.audio_dir || 'N/A')) +
    '</div>' +
    '<h3>当前卡点</h3>' +
    '<ul class="impact-list">' + (blockerRows || '<li>' + statusBadge('ok') + ' <b>没有明显卡点</b><br><span class="muted">采集、派单、抽取和索引没有发现硬阻塞。</span></li>') + '</ul>' +
    '<h3>建议动作</h3>' +
    '<ul>' + (actionRows || '<li>继续观察即可。</li>') + '</ul>' +
    '<h3>最近更新来源</h3>' +
    '<table><thead><tr><th>来源</th><th>文件数</th><th>最近更新时间</th></tr></thead><tbody>' + (sourceRows || '<tr><td colspan="3">N/A</td></tr>') + '</tbody></table>' +
    '<div class="muted">Generated: ' + esc(progress.generated_at || 'N/A') + '</div>';
}
function statePill(label, ok) {
  return '<div class="state-pill ' + (ok ? 'ok' : 'warn') + '">' + esc(label) + '<br>' + (ok ? '✓' : '×') + '</div>';
}
function evidenceSummary(item) {
  const ev = item.evidence || {};
  const upload = ev.latest_upload_audit || {};
  if (upload.batch && upload.data) {
    const d = upload.data || {};
    const q = d.qmd || {};
    const v = d.vault || {};
    const s = d.solar_db || {};
    return 'upload ' + upload.batch + ' · QMD ' + (q.title_hits || 0) + '/' + (d.total || 0) +
      ' · Vault ' + (v.hits || 0) + '/' + (d.total || 0) +
      ' · Solar DB ' + (s.hits || 0) + '/' + (d.total || 0);
  }
  if (upload.batch && upload.mode === 'fast_metadata') {
    return 'latest upload ' + upload.batch + ' · files ' + (upload.total_files || 0) + ' · deep audit skipped for dashboard speed';
  }
  if (ev.qmd_stats) {
    const qmd = ev.qmd_stats || {};
    return 'QMD indexed ' + (qmd.total || 0) + ' · pending ' + (qmd.pending || 0) + ' · vectors ' + (qmd.vectors || 0);
  }
  if (ev.total || ev.vectors || ev.pending !== undefined) {
    return 'QMD indexed ' + (ev.total || 0) + ' · vectors ' + (ev.vectors || 0) + ' · pending ' + (ev.pending || 0);
  }
  if (ev.runtime_level || ev.runtime_backend || ev.runtime_version) {
    return [
      ev.runtime_level ? 'runtime ' + ev.runtime_level : '',
      ev.runtime_backend || '',
      ev.runtime_version ? 'v' + ev.runtime_version : '',
      ev.dispatch_capability ? 'capability ' + ev.dispatch_capability : ''
    ].filter(Boolean).join(' · ');
  }
  if (ev.dispatch_backlog) {
    const b = ev.dispatch_backlog || {};
    return 'dispatch backlog unresolved ' + (b.unresolved || 0) + '/' + (b.total || 0);
  }
  if (ev.command) return 'command: ' + ev.command;
  if (ev.version) return 'version: ' + ev.version;
  if (ev.mounts) return 'mounts: ' + ev.mounts;
  return item.degraded_reason || item.status || 'N/A';
}
function renderIntegrations(data) {
  const summaryEl = document.getElementById('integrations-summary');
  const cardEl = document.getElementById('integrations-card');
  if (!summaryEl || !cardEl) return;
  if (!data || data.error) {
    summaryEl.innerHTML = statusBadge('error') + ' ' + esc((data && data.error) || 'integrations probe failed');
    cardEl.innerHTML = '<div class="card"><pre class="codebox">' + esc(JSON.stringify(data || {}, null, 2)) + '</pre></div>';
    return;
  }
  const summary = data.summary || {};
  const items = data.integrations || [];
  summaryEl.innerHTML =
    '<div class="integration-summary">' +
      '<div class="status-tile"><div class="kv-label">Total</div><strong>' + esc(summary.total || items.length || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">OK</div><strong>' + esc(summary.ok || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">Warn</div><strong>' + esc(summary.warn || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">Error</div><strong>' + esc(summary.error || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">Missing</div><strong>' + esc(summary.missing || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">断头</div><strong>' + esc(summary.dead_ends || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">Closed Loop</div><strong>' + esc((summary.integration_levels || {}).closed_loop || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">Default</div><strong>' + esc((summary.integration_levels || {}).default_usable || 0) + '</strong></div>' +
    '</div>' +
    '<div class="muted">缓存：' + (data._cache && data._cache.hit ? '命中' : '刷新') +
    ' · 探测时间：' + esc(data.generated_at || 'N/A') + '</div>';
  if (!items.length) {
    cardEl.innerHTML = '<div class="card muted">没有集成探测结果。</div>';
    return;
  }
  cardEl.innerHTML = '<div class="integration-grid">' + items.map(item => {
    const ev = item.evidence || {};
    const runtimeLine = [ev.runtime_level, ev.runtime_backend, ev.runtime_version ? 'v' + ev.runtime_version : '', ev.dispatch_capability]
      .filter(Boolean).join(' · ');
    return '<article class="integration-card">' +
      '<div class="integration-head"><div><div class="integration-name">' + esc(item.name || item.id || 'N/A') +
      '</div><div class="muted">' + esc(item.purpose || item.source || '') + '</div></div>' +
      '<div class="badge-stack">' + statusBadge(item.status || 'unknown') + levelBadge(item.status_label || 'unknown') + '</div></div>' +
      '<div class="state-row">' +
        statePill('安装', !!item.installed) +
        statePill('配置', !!item.configured) +
        statePill('运行', !!item.running) +
        statePill('索引', !!item.indexed) +
        statePill('默认', !!item.used_by_default) +
      '</div>' +
      '<div class="state-row">' +
        statePill('基础可用', item.health && item.health.basic_available !== 'error') +
        statePill('默认可用', item.health && item.health.default_available === 'ok') +
        statePill('完整闭环', item.health && item.health.complete_closed_loop === 'ok') +
        statePill('无断头', item.health && item.health.dead_ends === 'ok') +
      '</div>' +
      '<div class="integration-reason">' + esc(item.degraded_reason || '可用') + '</div>' +
      (item.dead_ends && item.dead_ends.length ? '<div class="integration-reason warn">断头：' + esc(item.dead_ends.join(', ')) + '</div>' : '') +
      (runtimeLine ? '<div class="runtime-line">' + esc(runtimeLine) + '</div>' : '') +
      '<div class="muted" style="margin-top:.7rem">' + esc(evidenceSummary(item)) + '</div>' +
      '<details style="margin-top:.8rem"><summary class="muted">证据</summary><pre class="codebox">' +
      esc(JSON.stringify(item.evidence || {}, null, 2)) + '</pre></details>' +
    '</article>';
  }).join('') + '</div>';
}
function renderContractSummary(data, compact) {
  data = data || {};
  if (data.status === 'missing') {
    return '<div class="muted">Contract summary not found.</div>';
  }
  const title = data.title || 'Contract Summary';
  const summary = data.summary || '';
  const link = data.route ? `<a href="${data.route}" target="_blank" rel="noopener" style="color: var(--accent-2); font-weight:800;">查看详情</a>` : '';
  
  if (compact) {
    return `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
          <div style="font-weight:800; font-size:0.9rem; color:#ffffff;">${esc(title)}</div>
          <div class="muted" style="font-size:0.75rem; margin-top:0.25rem;">${esc(summary)}</div>
        </div>
        <div>${link}</div>
      </div>
    `;
  }
  return `
    <div style="padding: 0.5rem 0;">
      <h3 style="margin-top:0; color:#ffffff;">${esc(title)}</h3>
      <p class="muted" style="font-size:0.85rem;">${esc(summary)}</p>
      <div style="margin-top:0.8rem;">
        ${link}
        <span class="muted" style="font-size:0.75rem; margin-left:1rem;">Source: ${esc(data.source || 'docs')} (${esc(data.path || '-')})</span>
      </div>
    </div>
  `;
}
function renderRequirementCoverage(data, compact) {
  data = data || {};
  if (data.status === 'missing') {
    const target = data.requested_sprint_id || data.sprint_id || 'N/A';
    return '<div><b class="tech-id">' + esc(target) + '</b> ' + statusBadge('missing') + '</div>'
      + '<div class="muted" style="margin-top:.35rem;">当前 active sprint 还没有 coverage 工件。</div>';
  }
  const total = Number(data.total || 0);
  const done = Number(data.done || 0);
  const partial = Number(data.partial || 0);
  const missing = Number(data.missing || 0);
  const verdict = data.acceptance_verdict || 'N/A';
  const ratio = Number(data.coverage_ratio || 0);
  const graphComplete = !!data.graph_complete;
  const badge = statusBadge(data.status || (partial || missing ? 'warn' : 'ok'));
  const source = data.source || 'recent';
  const requested = data.requested_sprint_id || '';
  const fallbackNote = data.is_fallback
    ? 'fallback from current ' + esc(requested || 'N/A')
    : (source === 'active' || source === 'requested' ? 'current active sprint' : source);
  if (compact) {
    return ''
      + '<div><b class="tech-id">' + esc(data.sprint_id || 'N/A') + '</b> ' + badge + '</div>'
      + '<div style="margin-top:.45rem;">verdict: <b>' + esc(verdict) + '</b></div>'
      + '<div style="margin-top:.2rem;">done/total: <b>' + esc(done) + '/' + esc(total) + '</b></div>'
      + '<div class="muted" style="margin-top:.3rem;">partial ' + esc(partial)
      + ' · missing ' + esc(missing)
      + ' · ratio ' + esc((ratio * 100).toFixed(0)) + '%'
      + ' · graph ' + esc(graphComplete ? 'complete' : 'incomplete') + '</div>'
      + '<div class="muted" style="margin-top:.28rem;">source: ' + fallbackNote + '</div>';
  }
  return ''
    + '<div class="research-shell">'
    + '<div class="research-overview">'
    +   '<div class="research-stat"><div class="kv-label">Sprint</div><strong>' + esc(data.sprint_id || 'N/A') + '</strong></div>'
    +   '<div class="research-stat"><div class="kv-label">Verdict</div><strong>' + esc(verdict) + '</strong></div>'
    +   '<div class="research-stat"><div class="kv-label">done/total</div><strong>' + esc(done) + '/' + esc(total) + '</strong></div>'
    +   '<div class="research-stat"><div class="kv-label">Partial</div><strong>' + esc(partial) + '</strong></div>'
    +   '<div class="research-stat"><div class="kv-label">Missing</div><strong>' + esc(missing) + '</strong></div>'
    +   '<div class="research-stat"><div class="kv-label">Coverage</div><strong>' + esc((ratio * 100).toFixed(0)) + '%</strong></div>'
    +   '<div class="research-stat"><div class="kv-label">Graph</div><strong>' + esc(graphComplete ? 'complete' : 'incomplete') + '</strong></div>'
    + '</div>'
    + '<div class="muted" style="margin-top:.6rem;">'
    + 'coverage report 会阻止半截交付：partial/missing 不为 0 时，PASS/finalized 不会放行。 source: ' + fallbackNote
    + '</div>'
    + '</div>';
}
function renderEvolution(evolution) {
  const el = document.getElementById('evolution-card');
  if (!el) return;
  if (!evolution || !evolution.ok) {
    el.innerHTML = '<div class="muted">Evolution scorecard unavailable.</div>';
    return;
  }
  const allRows = evolution.scorecards || [];
  const critical = allRows.filter(r => r.status === 'degraded' || r.status === 'demoted' || r.capability === 'deepresearch.quality_gate');
  const rows = allRows.slice(0, 10).concat(critical).filter((r, idx, arr) =>
    arr.findIndex(x => x.capability === r.capability && x.provider === r.provider) === idx
  ).slice(0, 16);
  if (!rows.length) {
    el.innerHTML = '<div class="muted">No scorecards yet. Run solar-harness evolution scorecard --json.</div>';
    return;
  }
  el.innerHTML = '<table><tr><th>Capability</th><th>Provider</th><th>Score</th><th>Level</th><th>Status</th></tr>' +
    rows.map(r => '<tr>' +
      '<td>' + esc(r.capability || '-') + '</td>' +
      '<td>' + esc(r.provider || '-') + '</td>' +
      '<td><strong>' + esc(r.score || '-') + '</strong></td>' +
      '<td>' + levelBadge(r.level || '-') + '</td>' +
      '<td>' + esc(r.status || 'N/A') + '</td>' +
    '</tr>').join('') + '</table>';
}
function refreshIntegrations(force) {
  const summaryEl = document.getElementById('integrations-summary');
  const cardEl = document.getElementById('integrations-card');
  if (summaryEl) summaryEl.textContent = force ? 'Refreshing...' : 'Loading...';
  if (cardEl) cardEl.textContent = 'Loading...';
  const url = '/integrations' + (force ? '?refresh=1' : '');
  fetch(url).then(r => r.json()).then(renderIntegrations).catch(err => {
    renderIntegrations({error: String(err)});
  });
}
function assetButtons(pkg) {
  const buttons = [];
  const primary = pkg.accepted_md || {};
  if (primary.exists) {
    buttons.push('<a class="btn primary" href="' + esc(primary.view_url || primary.open_url) + '" target="_blank" rel="noreferrer">accepted.md</a>');
  }
  const dispatch = pkg.dispatch || {};
  if (dispatch.exists) {
    buttons.push('<a class="btn" href="' + esc(dispatch.view_url || dispatch.open_url) + '" target="_blank" rel="noreferrer">dispatch</a>');
  }
  (pkg.sprint_artifacts || []).forEach(link => {
    if (!link || !link.exists) return;
    const cls = (link.label === 'planning_html' || link.label === 'prd_html' || link.label === 'design_html') ? ' primary' : '';
    buttons.push('<a class="btn' + cls + '" href="' + esc(link.view_url || link.open_url) + '" target="_blank" rel="noreferrer">' + esc(link.label) + '</a>');
  });
  return buttons.join('');
}
function renderAssetPackages(data) {
  const summaryEl = document.getElementById('assets-summary');
  const cardEl = document.getElementById('assets-card');
  if (!summaryEl || !cardEl) return;
  if (!data || data.error) {
    summaryEl.innerHTML = statusBadge('error') + ' ' + esc((data && data.error) || 'asset package probe failed');
    cardEl.innerHTML = '<div class="card"><pre class="codebox">' + esc(JSON.stringify(data || {}, null, 2)) + '</pre></div>';
    return;
  }
  const items = data.items || [];
  summaryEl.innerHTML =
    '<div class="integration-summary">' +
      '<div class="status-tile"><div class="kv-label">Status</div><strong>' + statusBadge(data.status || 'unknown') + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">Packages</div><strong>' + esc(data.count || items.length || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">HTML</div><strong>' + esc(data.html_asset_packages || 0) + '</strong></div>' +
      '<div class="status-tile"><div class="kv-label">Accepted Dir</div><strong class="path-text">' + esc(data.accepted_dir || 'N/A') + '</strong></div>' +
    '</div>' +
    '<div class="muted">资产包生成自 Knowledge accepted 目录；点击 planning_html / design_html / prd_html 可直接查看人类可读页面。</div>';
  if (!items.length) {
    cardEl.innerHTML = '<div class="card muted">没有 accepted knowledge package。先运行 accepted artifact export。</div>';
    return;
  }
  cardEl.innerHTML = '<div class="integration-grid">' + items.map(pkg => {
    const labels = (pkg.artifact_labels || []).slice(0, 9).join(', ') || 'N/A';
    const mtime = pkg.mtime ? new Date(pkg.mtime * 1000).toLocaleString() : 'N/A';
    return '<article class="integration-card">' +
      '<div class="integration-head"><div><div class="integration-name">' + esc(pkg.title || pkg.sid || 'N/A') + '</div>' +
      '<div class="tech-id">' + esc(pkg.sid || 'N/A') + '</div></div>' +
      '<div class="badge-stack">' + statusBadge(pkg.status || 'accepted') + (pkg.has_html ? '<span class="level-badge ok">HTML</span>' : '<span class="level-badge warn">no HTML</span>') + '</div></div>' +
      '<div class="research-metric-row">' +
        '<div class="research-metric"><div class="kv-label">Artifacts</div><b>' + esc(pkg.artifact_count || 0) + '</b></div>' +
        '<div class="research-metric"><div class="kv-label">Size</div><b>' + esc(pkg.size || 0) + '</b></div>' +
        '<div class="research-metric"><div class="kv-label">Updated</div><b>' + esc(mtime) + '</b></div>' +
      '</div>' +
      '<div class="impact-note"><b>Included:</b> ' + esc(labels) + '</div>' +
      '<div class="copy-row">' + assetButtons(pkg) + '</div>' +
      '<details style="margin-top:.8rem"><summary class="muted">路径</summary><pre class="codebox">' + esc(JSON.stringify({
        knowledge_path: pkg.knowledge_path,
        accepted_at: pkg.accepted_at,
        exported_at: pkg.exported_at,
        source_hash: pkg.source_hash
      }, null, 2)) + '</pre></details>' +
    '</article>';
  }).join('') + '</div>';
}
function refreshAssets(force) {
  const summaryEl = document.getElementById('assets-summary');
  const cardEl = document.getElementById('assets-card');
  if (summaryEl) summaryEl.textContent = force ? 'Refreshing...' : 'Loading...';
  if (cardEl) cardEl.textContent = 'Loading...';
  const url = '/assets?limit=120' + (force ? '&refresh=1' : '');
  fetch(url).then(r => r.json()).then(renderAssetPackages).catch(err => {
    renderAssetPackages({error: String(err)});
  });
}

function activateTab(tab) {
  const btn = document.querySelector('.tab[data-tab="' + tab + '"]') || document.querySelector('.tab[data-tab="overview"]');
  if (!btn) return;
  const activeTab = btn.dataset.tab || 'overview';
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x === btn));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + activeTab));
  if (activeTab === 'integrations') refreshIntegrations(false);
  if (activeTab === 'assets') refreshAssets(false);
}
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab || 'overview';
    if (location.hash !== '#' + tab) history.replaceState(null, '', '#' + tab);
    activateTab(tab);
  });
});
window.addEventListener('hashchange', () => activateTab((location.hash || '#overview').slice(1)));

window.opFilterRole = 'all';
window.opFilterState = 'all';
window.opSearch = '';
window.paneFilterState = 'all';
window.paneSearch = '';

function renderOperatorsPage() {
  const data = window.globalStatusData;
  if (!data || !data.physical_operators) return;
  const po = data.physical_operators;
  const items = po.items || [];
  
  // Calculate metrics dynamically
  const total = items.length;
  let enabled = 0, available = 0, busy = 0, idle = 0, disabled = 0;
  
  items.forEach(item => {
    if (item.enabled) enabled++;
    if (item.available) available++;
    if (item.runtime_state === 'disabled' || !item.enabled) {
      disabled++;
    } else if (item.runtime_state === 'leased' || item.runtime_state === 'running') {
      busy++;
    } else {
      idle++;
    }
  });
  
  // Render metrics container
  document.getElementById('operator-metrics-container').innerHTML = `
    <div class="health-metrics">
      <div class="mini-metric"><div class="kv-label">Total Fleet</div><span class="num">${total}</span></div>
      <div class="mini-metric"><div class="kv-label">Idle (空闲)</div><span class="num" style="color:#10b981;">${idle}</span></div>
      <div class="mini-metric"><div class="kv-label">Busy (忙碌/已租)</div><span class="num" style="color:#06b6d4;">${busy}</span></div>
      <div class="mini-metric"><div class="kv-label">Enabled</div><span class="num">${enabled}</span></div>
      <div class="mini-metric"><div class="kv-label">Available</div><span class="num">${available}</span></div>
      <div class="mini-metric"><div class="kv-label">Disabled</div><span class="num" style="color:#fbbf24;">${disabled}</span></div>
    </div>
  `;
  
  // Filter items
  const filtered = items.filter(item => {
    // Role filter
    if (window.opFilterRole !== 'all') {
      if ((item.role || '').toLowerCase() !== window.opFilterRole) return false;
    }
    // State filter
    if (window.opFilterState !== 'all') {
      if (window.opFilterState === 'disabled' && (item.runtime_state === 'disabled' || !item.enabled)) {
        // match
      } else if (window.opFilterState === 'leased' && item.runtime_state === 'leased') {
        // match
      } else if (window.opFilterState === 'busy' && (item.runtime_state === 'leased' || item.runtime_state === 'running')) {
        // match
      } else if (window.opFilterState === 'idle' && item.runtime_state === 'idle' && item.enabled) {
        // match
      } else {
        return false;
      }
    }
    // Search query
    if (window.opSearch) {
      const q = window.opSearch.toLowerCase();
      const match = (item.operator_id || '').toLowerCase().includes(q) ||
                    (item.model || '').toLowerCase().includes(q) ||
                    (item.backend || '').toLowerCase().includes(q) ||
                    (item.persona || '').toLowerCase().includes(q) ||
                    (item.runtime_state || '').toLowerCase().includes(q) ||
                    (item.sprint_id || '').toLowerCase().includes(q) ||
                    (item.task_id || '').toLowerCase().includes(q) ||
                    (item.role || '').toLowerCase().includes(q) ||
                    JSON.stringify(item.latest_health || {}).toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });
  
  // Render list/table
  if (!filtered.length) {
    document.getElementById('operator-cards-container').innerHTML = '<div class="muted" style="padding:2rem; text-align:center;">没有找到符合过滤条件的物理算子。</div>';
  } else {
    let listHtml = '<div class="op-list">';
    listHtml += `
      <div class="op-row" style="background: transparent; border: none; padding: 0.2rem 1.4rem; box-shadow: none; transform: none; pointer-events: none; margin-bottom: -0.4rem;">
        <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">算子 ID (名称)</div>
        <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">角色 / 类型</div>
        <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">模型 / 后端</div>
        <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">并发度</div>
        <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">当前状态</div>
        <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;">活跃租约 / 任务</div>
        <div style="font-size: 0.75rem; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; text-align: center;">操作</div>
      </div>
    `;
    
    filtered.forEach((item, idx) => {
      let statusClass = "missing";
      let statusLabel = item.runtime_state || "unknown";
      let rowStyle = "";
      
      if (!item.enabled) {
        statusClass = "missing";
        statusLabel = "disabled";
        rowStyle = "opacity: 0.65;";
      } else if (item.runtime_state === 'idle') {
        statusClass = "ok";
      } else if (item.runtime_state === 'leased' || item.runtime_state === 'running') {
        statusClass = "default";
        rowStyle = "background: rgba(6, 182, 212, 0.04);";
      } else if (item.runtime_state === 'disabled') {
        statusClass = "missing";
        rowStyle = "opacity: 0.65;";
      } else {
        statusClass = "warn";
      }
      
      let leaseText = '<span class="muted">-</span>';
      if (item.sprint_id || item.task_id) {
        const expires = item.expires_at ? new Date(item.expires_at).toLocaleTimeString() : 'N/A';
        leaseText = `
          <div>
            <span class="tech-id" style="color: var(--accent-2); font-weight:800;">${esc(item.sprint_id || '')}</span> / 
            <span class="tech-id">${esc(item.task_id || '')}</span>
            <span class="muted" style="font-size:0.75rem; margin-left:0.4rem;">(Expires: ${esc(expires)})</span>
          </div>
        `;
      }

      const health = item.latest_health || {};
      let painterHealth = '';
      if (item.operator_id === 'technology-diagram-painter' || health.result_kind === 'technology_diagram') {
        const healthOk = !!health.original_image_ok;
        const healthClass = healthOk ? 'ok' : (health.health_status === 'error' ? 'missing' : 'warn');
        const dims = health.width && health.height ? `${health.width}×${health.height}` : 'N/A';
        const bytes = health.bytes ? `${Math.round(Number(health.bytes) / 1024)} KB` : 'N/A';
        painterHealth = `
          <div style="margin-top:0.35rem;">
            <span class="level-badge ${healthClass}" style="font-size:0.7rem;">原图 ${healthOk ? 'ok' : 'warn'}</span>
            <span class="muted" style="font-size:0.72rem; margin-left:0.35rem;">${esc(health.source || 'N/A')} · ${esc(dims)} · ${esc(bytes)}</span>
          </div>
        `;
      }
      
      listHtml += `
        <div class="op-row" style="${rowStyle}">
          <div>
            <div style="font-weight: 800; font-size: 0.95rem; color:#ffffff;">${esc(item.operator_id)}</div>
            ${item.display_name && item.display_name !== item.operator_id ? `<div class="muted" style="font-size: 0.75rem; margin-top:0.15rem;">${esc(item.display_name)}</div>` : ''}
            ${painterHealth}
          </div>
          <div>
            <span class="badge default" style="background: rgba(255,255,255,0.04); padding: 0.3rem 0.6rem; border-radius: 8px;">${esc(item.role)}</span>
            <div class="muted" style="font-size: 0.72rem; margin-top:0.2rem;">${esc(item.persona || 'N/A')}</div>
          </div>
          <div>
            <div style="font-weight:700; font-size:0.85rem;">${esc(item.model || 'N/A')}</div>
            <div class="tech-id" style="font-size: 0.74rem; margin-top: 0.15rem;">${esc(item.backend)}</div>
          </div>
          <div>
            <div class="muted" style="font-size:0.7rem; margin-bottom:0.15rem;">Concurrency</div>
            <span class="tech-id">${esc(item.max_concurrency || '1')}</span>
          </div>
          <div><span class="level-badge ${statusClass}">${statusLabel}</span></div>
          <div>${leaseText}</div>
          <div>
            <button class="btn" onclick="toggleOpDetails(${idx})" style="padding: 4px 8px; font-size: 0.72rem; border-radius: 8px; width: 100%;">展开 JSON</button>
          </div>
        </div>
        <div id="op-details-row-${idx}" class="op-row-details">
          <div style="font-weight: 900; font-size: 0.8rem; color: var(--accent-2); margin-bottom: 0.4rem;">配置详情 (JSON)</div>
          <pre class="codebox" style="margin: 0; padding: 0.8rem; font-size: 0.74rem; line-height: 1.4; border-radius: 10px;">${esc(JSON.stringify(item, null, 2))}</pre>
        </div>
      `;
    });
    
    listHtml += '</div>';
    document.getElementById('operator-cards-container').innerHTML = listHtml;
  }

  // Render recent results table
  const recentResults = po.recent_results || [];
  if (!recentResults.length) {
    document.getElementById('operator-results-detailed').innerHTML = '<div class="muted">暂无最近执行结果记录。</div>';
  } else {
    let t = '<table><tr><th>Operator</th><th>模型 / 后端</th><th>Task</th><th>Sprint</th><th>Verdict / Status</th><th>Artifact</th><th>Started</th><th>Finished</th></tr>';
    recentResults.forEach(item => {
      const finished = item.finished_at ? new Date(item.finished_at).toLocaleString() : (item.started_at ? 'running' : 'N/A');
      const started = item.started_at ? new Date(item.started_at).toLocaleString() : 'N/A';
      let artifact = '<span class="muted">N/A</span>';
      if (item.result_kind === 'technology_diagram' || item.image_path || item.url) {
        const dims = item.width && item.height ? `${item.width}×${item.height}` : 'N/A';
        const bytes = item.bytes ? `${Math.round(Number(item.bytes) / 1024)} KB` : 'N/A';
        artifact = '<div>' + statusBadge(item.original_image_ok ? 'original-image-ok' : 'image-fallback') + '</div>' +
          '<div class="muted" style="font-size:0.72rem;margin-top:0.15rem;">' + esc(dims + ' · ' + bytes) + '</div>';
      }
      t += '<tr>' +
        '<td><b class="tech-id" style="display:inline;">' + esc(item.operator_id || '-') + '</b><div class="muted" style="font-size:0.72rem; margin-top:0.15rem;">' + esc(item.source || 'operator-results') + '</div></td>' +
        '<td><div style="font-weight:800; font-size:0.78rem;">' + esc(item.model || 'N/A') + '</div><div class="tech-id" style="font-size:0.72rem; margin-top:0.12rem;">' + esc(item.backend || 'N/A') + '</div></td>' +
        '<td><span class="tech-id">' + esc(item.task_id || '-') + '</span></td>' +
        '<td><span class="tech-id">' + esc(item.sprint_id || '-') + '</span></td>' +
        '<td>' + statusBadge(item.status || 'unknown') + '</td>' +
        '<td>' + artifact + '</td>' +
        '<td>' + esc(started) + '</td>' +
        '<td>' + esc(finished) + '</td>' +
      '</tr>';
    });
    t += '</table>';
    document.getElementById('operator-results-detailed').innerHTML = t;
  }
}

window.toggleOpDetails = function(idx) {
  const row = document.getElementById('op-details-row-' + idx);
  if (row) {
    if (row.style.display === 'none') {
      row.style.display = 'block';
    } else {
      row.style.display = 'none';
    }
  }
};

function renderPanesPage() {
  const data = window.globalStatusData;
  if (!data || !data.multi_task_panes) return;
  const panes = data.multi_task_panes;
  const pool = data.multi_task_pane_pool || {};
  const modelCounts = {};
  const operatorTypeCounts = {};
  panes.forEach(p => {
    const model = p.model || 'N/A';
    const operatorType = p.operator_type || p.pool || 'unknown';
    modelCounts[model] = (modelCounts[model] || 0) + 1;
    operatorTypeCounts[operatorType] = (operatorTypeCounts[operatorType] || 0) + 1;
  });
  const compactCounts = (counts) => Object.entries(counts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 6)
    .map(([name, count]) => `${esc(name)}:${count}`)
    .join(' · ') || 'N/A';
  const modelSummary = compactCounts(modelCounts);
  const operatorTypeSummary = compactCounts(operatorTypeCounts);
  
  // Calculate metrics
  const total = pool.total ?? panes.length;
  const idle = pool.idle ?? panes.filter(p => p.status === 'idle').length;
  const reusableIdle = pool.reusable_idle ?? panes.filter(p => p.status === 'reusable_idle').length;
  const historicalActive = pool.historical_active ?? panes.filter(p => p.status === 'historical_active').length;
  const leased = pool.leased ?? panes.filter(p => p.status === 'leased').length;
  const running = pool.running ?? panes.filter(p => p.status === 'running').length;
  
  // Render metrics container
  document.getElementById('pane-metrics-container').innerHTML = `
    <div class="health-metrics">
      <div class="mini-metric"><div class="kv-label">Total Panes</div><span class="num">${total}</span></div>
      <div class="mini-metric"><div class="kv-label">Idle (未使用)</div><span class="num" style="color:#1f6f5b;">${idle}</span></div>
      <div class="mini-metric"><div class="kv-label">Reusable Idle</div><span class="num" style="color:#254f91;">${reusableIdle}</span></div>
      <div class="mini-metric"><div class="kv-label">Historical Active</div><span class="num" style="color:#8b4a1d;">${historicalActive}</span></div>
      <div class="mini-metric"><div class="kv-label">Leased (已租用)</div><span class="num" style="color:#254f91;">${leased}</span></div>
      <div class="mini-metric"><div class="kv-label">Running Command (执行中)</div><span class="num" style="color:#8b4a1d;">${running}</span></div>
    </div>
    <div class="muted" style="margin-top:0.5rem;">模型分布：${modelSummary}</div>
    <div class="muted" style="margin-top:0.35rem;">算子类型：${operatorTypeSummary}</div>
    <div class="muted" style="margin-top:0.5rem;">说明：'reusable_idle' 是可安全复用的历史 shell 窗口；'historical_active' 是当前 tmux 选中的历史壳，出于安全默认不自动杀。</div>
  `;
  document.getElementById('pane-pool-contract-card').innerHTML = `
    <div class="health-metrics">
      <div class="mini-metric"><div class="kv-label">Target Keep</div><span class="num">${pool.target_keep ?? 1}</span></div>
      <div class="mini-metric"><div class="kv-label">Reuse</div><span class="num">${pool.reuse_enabled ? 'on' : 'off'}</span></div>
      <div class="mini-metric"><div class="kv-label">Auto Close</div><span class="num">${pool.auto_close_enabled ? 'on' : 'off'}</span></div>
      <div class="mini-metric"><div class="kv-label">Compact</div><span class="num" style="color:${pool.compact_recommended ? '#8b4a1d' : '#1f6f5b'};">${pool.compact_recommended ? 'recommended' : 'not-needed'}</span></div>
    </div>
    <div class="muted" style="margin-top:0.5rem;">contract: shrink 到目标池大小；保留可复用历史壳，不自动杀当前选中的历史壳。</div>
    <div class="muted" style="margin-top:0.35rem;">ops: 'compact-session' 会安全切走并收掉历史 current window；'detach-and-anchor' 只把 session current window 切到 anchor。</div>
  `;
  
  // Filter panes
  const filtered = panes.filter(p => {
    // State filter
    if (window.paneFilterState !== 'all') {
      if (p.status !== window.paneFilterState) return false;
    }
    // Search filter
    if (window.paneSearch) {
      const q = window.paneSearch.toLowerCase();
      const match = (p.pane || '').toLowerCase().includes(q) ||
                    (p.window_name || '').toLowerCase().includes(q) ||
                    (p.current_command || '').toLowerCase().includes(q) ||
                    (p.title || '').toLowerCase().includes(q) ||
                    (p.model || '').toLowerCase().includes(q) ||
                    (p.backend || '').toLowerCase().includes(q) ||
                    (p.operator_type || '').toLowerCase().includes(q) ||
                    (p.profile || '').toLowerCase().includes(q) ||
                    (p.role || '').toLowerCase().includes(q) ||
                    ((p.lease && p.lease.sprint_id) || '').toLowerCase().includes(q) ||
                    ((p.lease && p.lease.task_id) || '').toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });
  
  // Render panes list (as a beautiful detailed table)
  if (!filtered.length) {
    document.getElementById('pane-grid-container').innerHTML = '<div class="muted" style="padding:2rem; text-align:center;">没有找到符合过滤条件的 Headless Pane。</div>';
  } else {
    let t = '<table><tr><th>Pane</th><th>模型 / 后端 / 类型</th><th>Window Name</th><th>Cmd (进程)</th><th>Pane Title (TUI 标题)</th><th>Status</th><th>Lease Task (租约任务)</th></tr>';
    filtered.forEach(p => {
      let statusClass = "missing";
      if (p.status === 'idle') statusClass = "ok";
      else if (p.status === 'reusable_idle') statusClass = "default";
      else if (p.status === 'historical_active') statusClass = "warn";
      else if (p.status === 'leased') statusClass = "default";
      else statusClass = "warn";
      
      let leaseText = "-";
      if (p.lease && p.lease.task_id) {
        leaseText = `<div style="font-weight: 800; font-size: 0.8rem;"><span class="tech-id">${esc(p.lease.sprint_id || '')}</span> / <span class="tech-id">${esc(p.lease.task_id)}</span></div>`;
      } else if (p.task && p.task.task_id) {
        leaseText = `<div style="font-weight: 800; font-size: 0.8rem;"><span class="tech-id">${esc(p.task.sprint_id || '')}</span> / <span class="tech-id">${esc(p.task.task_id)}</span></div>`;
      }
      
      let cmdHighlight = p.current_command;
      if (p.status === 'running') {
        cmdHighlight = `<span class="badge warn" style="font-family:ui-monospace,monospace;">${esc(p.current_command)}</span>`;
      }
      
      const taskStatus = ((p.task && p.task.status) || '-');
      const modelLabel = p.model || 'N/A';
      const backendLabel = p.backend || p.pool || 'N/A';
      const operatorLabel = (p.operator_type || 'unknown') + ' · ' + (p.profile || p.role || '-');
      t += '<tr>' +
        '<td><b class="tech-id" style="display:inline; font-size:0.85rem;">' + esc(p.pane) + '</b></td>' +
        '<td><div style="font-weight:900; font-size:0.82rem;">' + esc(modelLabel) + '</div><div class="tech-id" style="font-size:0.72rem; margin-top:0.12rem;">' + esc(backendLabel) + '</div><div class="muted" style="font-size:0.72rem; margin-top:0.12rem;">' + esc(operatorLabel) + '</div></td>' +
        '<td><span style="font-size:0.8rem; font-weight:800;">' + esc(p.window_name) + '</span></td>' +
        '<td>' + cmdHighlight + '</td>' +
        '<td style="font-size:0.8rem; font-weight:900;">' + esc(p.title || '-') + '</td>' +
        '<td><span class="level-badge ' + statusClass + '">' + esc(p.status) + '</span><div class="muted" style="font-size:0.72rem; margin-top:0.18rem;">task=' + esc(taskStatus) + '</div></td>' +
        '<td>' + leaseText + '</td>' +
      '</tr>';
    });
    t += '</table>';
    document.getElementById('pane-grid-container').innerHTML = t;
  }
}

function render(data) {
  const now = new Date().toISOString();
  document.getElementById('refresh-ts').textContent = 'Last updated: ' + now;

  const sp = data.current_sprint || {};
  if (sp.sprint_id && sp.is_active !== false) {
    const sprintHtml = sprintBlock({
      title: sp.title || sp.sprint_id,
      status: sp.status,
      phase: sp.phase || '-',
      handoff_to: sp.handoff_to || '-',
      lane: sp.lane || '-',
      priority: sp.priority || '-',
      description: sp.description || '',
      understand_anything_summary: sp.understand_anything_summary || {}
    }, sp.sprint_id);
    document.getElementById('sprint-card').innerHTML = sprintHtml;
    document.getElementById('overview-sprint').innerHTML = sprintHtml;
  } else {
    const recent = sp.recent_completed || {};
    const idleHtml = '<div class="state-card idle"><h3>当前无活跃 Sprint</h3>' +
      '<p>队列为空；coordinator 没有可派发工作。</p>' +
      (recent.sprint_id ? '<p class="muted">最近完成：' + esc(recent.title || recent.sprint_id) +
        ' · ' + esc(recent.status || '-') + '/' + esc(recent.phase || '-') + '</p>' : '') +
      '</div>';
    document.getElementById('sprint-card').innerHTML = idleHtml;
    document.getElementById('overview-sprint').innerHTML = idleHtml;
  }

  const panes = data.panes || [];
  const assignedMainPanes = ((data.main_screen || {}).panes || []).filter(p => p.assignment);
  if (assignedMainPanes.length) {
    let t = '<table><tr><th>Pane</th><th>角色</th><th>运行</th><th>当前任务</th><th>产物</th></tr>';
    assignedMainPanes.forEach(p => {
      t += '<tr><td>' + esc(p.target || '-') + '</td><td>' + esc(p.role || '-') + '</td>' +
           '<td class="' + runtimeClass(p.runtime_state) + '">' + esc(p.runtime_state || '-') + '</td>' +
           '<td>' + taskCell(p.assignment_meta || {}, p.assignment || '-') + '</td>' +
           '<td>' + artifactLabel(p.artifact) + '</td></tr>';
    });
    t += '</table>';
    document.getElementById('panes-card').innerHTML = t;
    document.getElementById('overview-panes').innerHTML = '<div class="metric">' + assignedMainPanes.length + '</div><div class="muted">assigned panes</div>';
  } else if (panes.length) {
    let t = '<table><tr><th>Pane</th><th>当前任务</th><th>状态</th><th>阶段</th></tr>';
    panes.forEach(p => {
      const meta = p.sprint || {};
      t += '<tr><td>' + esc(p.pane) + '</td><td>' + taskCell(meta, p.sprint_id || '-') + '</td>' +
           '<td>' + statusBadge(meta.status || 'unknown') + '</td><td>' + esc(meta.phase || '-') + '</td></tr>';
    });
    t += '</table>';
    document.getElementById('panes-card').innerHTML = t;
    document.getElementById('overview-panes').innerHTML = '<div class="metric">' + panes.length + '</div><div class="muted">assigned panes</div>';
  } else {
    document.getElementById('panes-card').textContent = 'No pane assignments.';
    document.getElementById('overview-panes').innerHTML = '<div class="metric">0</div><div class="muted">assigned panes</div>';
  }

  window.globalStatusData = data;
  renderOperatorsPage();
  renderPanesPage();

  const evts = data.recent_events || [];
  if (evts.length) {
    let t = '<table><tr><th>Time</th><th>Sev</th><th>Actor</th><th>Event</th><th>Sprint</th></tr>';
    evts.slice().reverse().forEach(e => {
      const ts = (e.ts || '').substring(11, 19);
      t += '<tr><td>' + esc(ts) + '</td><td class="' + sevClass(e.severity) + '">' + esc(e.severity || '?') +
           '</td><td>' + esc(e.actor || '?') + '</td><td>' + esc(e.event || '?') +
           '</td><td>' + esc(e.sprint_id || '-') + '</td></tr>';
    });
    t += '</table>';
    document.getElementById('events-card').innerHTML = t;
  } else {
    document.getElementById('events-card').textContent = 'No events yet.';
  }
  const risky = evts.slice().reverse().filter(e => e.severity === 'warn' || e.severity === 'error').slice(0, 4);
  if (risky.length) {
    document.getElementById('overview-risk').innerHTML =
      '<ul class="summary-list">' + risky.map(e => '<li>' +
      esc((e.ts || '').substring(11, 19)) + ' · ' + esc(e.severity || '?') + ' · ' +
      esc(e.actor || '?') + ' · ' + esc(e.event || '?') + '</li>').join('') + '</ul>';
  } else {
    document.getElementById('overview-risk').innerHTML = '<div class="muted">最近 50 条事件没有 warn/error。</div>';
  }

  const kpi = data.kpi || {};
  const kpiHtml =
    'Total: <b>' + (kpi.sprints_total||0) + '</b> &nbsp; ' +
    'Passed: <b>' + (kpi.sprints_passed||0) + '</b> &nbsp; ' +
    'Failed: <b>' + (kpi.sprints_failed||0) + '</b> &nbsp; ' +
    'Pass rate: <b>' + ((kpi.pass_rate||0)*100).toFixed(0) + '%</b>';
  document.getElementById('overview-kpi').innerHTML = kpiHtml;

  const wiki = data.obsidian_wiki || {};
  const mirage = data.mirage || {};
  const knowledgeProgress = data.knowledge_progress || {};
  renderEvolution(data.evolution || {});
  document.getElementById('knowledge-summary').innerHTML = renderKnowledgeSummary(wiki, mirage);
  document.getElementById('knowledge-progress-card').innerHTML = renderKnowledgeProgress(knowledgeProgress);
  document.getElementById('wiki-card').innerHTML = renderList(wiki);
  document.getElementById('mirage-card').innerHTML = renderMirageHealth(mirage);
  document.getElementById('overview-knowledge').innerHTML =
    'Wiki: ' + statusBadge(wiki.ready ? 'ok' : 'warn') + '<br>' +
    'Mirage: ' + statusBadge(mirage.ready ? 'ok' : (mirage.status || 'warn'));
  document.getElementById('overview-runtime').innerHTML = renderRuntimeInterfaces(data.runtime_interfaces || {});
  document.getElementById('overview-capabilities').innerHTML = renderCapabilityHealthSummary(data.capability_health || {});
  document.getElementById('overview-knowledge-routing').innerHTML = renderKnowledgeRouting(data.knowledge_routing || {}, true);
  document.getElementById('knowledge-routing-card').innerHTML = renderKnowledgeRouting(data.knowledge_routing || {}, false);
  document.getElementById('overview-autoresearch-impact').innerHTML = renderAutoresearchImpact(data.autoresearch_impact || {}, true);
  document.getElementById('autoresearch-impact-card').innerHTML = renderAutoresearchImpact(data.autoresearch_impact || {}, false);
  document.getElementById('overview-meta-harness').innerHTML = renderMetaHarness(data.meta_harness || {}, true);
  document.getElementById('meta-harness-card').innerHTML = renderMetaHarness(data.meta_harness || {}, false);
  document.getElementById('overview-pm-dispatch').innerHTML = renderPmDispatches(data.pm_dispatches || {}, true);
  document.getElementById('pm-dispatch-card').innerHTML = renderPmDispatches(data.pm_dispatches || {}, false);
  document.getElementById('overview-physical-operators').innerHTML = renderPhysicalOperators(data.physical_operators || {}, true);
  document.getElementById('physical-operators-card').innerHTML = renderPhysicalOperators(data.physical_operators || {}, false);
  document.getElementById('overview-contract-summary').innerHTML = renderContractSummary(data.contract_summary || {}, true);
  document.getElementById('contract-summary-card').innerHTML = renderContractSummary(data.contract_summary || {}, false);
  document.getElementById('overview-requirement-coverage').innerHTML = renderRequirementCoverage(data.requirement_coverage || {}, true);
  document.getElementById('overview-human-search').innerHTML = renderHumanSearch(data.human_search || {}, true);
  document.getElementById('human-search-card').innerHTML = renderHumanSearch(data.human_search || {}, false);
  document.getElementById('overview-research').innerHTML = renderResearchStatus(data.research || {}, true);
  document.getElementById('research-card').innerHTML = renderResearchStatus(data.research || {}, false);

  document.getElementById('raw-card').textContent = JSON.stringify(data, null, 2);
}

function refresh() {
  if (window.__solarStatusRefreshInFlight) return;
  window.__solarStatusRefreshInFlight = true;
  fetch('/status?ts=' + Date.now(), {cache: 'no-store'})
    .then(r => r.json())
    .then(render)
    .catch(e => {
      console.warn('refresh error', e);
      const msg = 'Status refresh failed: ' + (e && e.message ? e.message : String(e));
      const ts = document.getElementById('refresh-ts');
      if (ts) ts.textContent = msg;
      ['overview-sprint', 'overview-knowledge', 'raw-card'].forEach(id => {
        const el = document.getElementById(id);
        if (el && /Loading/.test(el.textContent || el.innerHTML || '')) {
          el.innerHTML = '<div class="warn">' + esc(msg) + '</div>';
        }
      });
    })
    .finally(() => { window.__solarStatusRefreshInFlight = false; });
}
activateTab((location.hash || '#overview').slice(1));
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>
"""


class StatusHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access log noise

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, status=200, content_type="text/plain; charset=utf-8"):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json({"error": "not found"}, status=404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw or "{}")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            data = self._read_json_body()
            if path == "/knowledge/subscriptions/youtube":
                self._send_json(_append_youtube_subscription(data))
            elif path == "/knowledge/subscriptions/social":
                self._send_json(_append_social_subscription(data))
            elif path == "/knowledge/subscriptions/github-topic":
                self._send_json(_append_github_topic(data))
            elif path == "/knowledge/subscriptions/github-repo":
                self._send_json(_append_github_repo(data))
            elif path == "/ai-influence/mail-config":
                self._send_json(_save_ai_influence_mail_config(data))
            elif path == "/ai-influence/send":
                self._send_json(_ai_influence_send_report(data))
            else:
                self._send_json({"ok": False, "error": "not found"}, status=404)
        except Exception as exc:
            self._send_json({"ok": False, "status": "error", "error": f"{type(exc).__name__}: {exc}"}, status=400)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        if path == "/healthz":
            self._send_text("ok")

        elif path == "/status":
            self._send_json(_status_payload(limit=50))

        elif path == "/api/pane-model-call":
            target = params.get("target", [""])[0]
            pane_id = params.get("pane_id", [""])[0]
            self._send_json(_pane_model_call_detail(target, pane_id))

        elif path == "/contract-summary":
            self._send_text(_final_contract_summary_html(), content_type="text/html; charset=utf-8")

        elif path.startswith("/research/"):
            sid = path.split("/research/", 1)[1].strip("/")
            routes_path = HARNESS_DIR / "status-server" / "research_routes.py"
            try:
                spec = importlib.util.spec_from_file_location("solar_research_routes_http", str(routes_path))
                if spec is None or spec.loader is None:
                    raise RuntimeError("unable to load research_routes.py")
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if params.get("format", [""])[0].lower() == "html":
                    self._send_text(mod.render_html_report(SPRINTS_DIR, sid), content_type="text/html; charset=utf-8")
                else:
                    self._send_json(mod.build_research_payload(SPRINTS_DIR, sid))
            except Exception as exc:
                self._send_json({"error": f"{type(exc).__name__}: {exc}", "sid": sid}, status=500)

        elif path == "/events":
            sprint_id = params.get("sprint_id", [""])[0]
            try:
                limit = int(params.get("limit", ["50"])[0])
                limit = max(1, min(limit, 500))
            except ValueError:
                limit = 50
            if sprint_id:
                src = _runtime_events_path(sprint_id)
            else:
                src = ALL_EVENTS
            events = _read_jsonl(src, limit=limit, sprint_id="")
            self._send_json(events)

        elif path == "/integrations":
            refresh = params.get("refresh", ["0"])[0].lower() in ("1", "true", "yes")
            self._send_json(_external_integrations_payload(refresh=refresh))

        elif path == "/integrations-view":
            self._send_text(_integrations_view_html(), content_type="text/html; charset=utf-8")

        elif path == "/assets":
            try:
                limit = int(params.get("limit", ["80"])[0])
                limit = max(1, min(limit, 300))
            except ValueError:
                limit = 80
            self._send_json(_asset_packages_payload(limit=limit))

        elif path == "/assets-view":
            self._send_text(_assets_view_html(), content_type="text/html; charset=utf-8")

        elif path == "/knowledge/subscriptions":
            self._send_json(_knowledge_subscriptions_payload())

        elif path == "/knowledge/progress":
            self._send_json(_knowledge_ingest_progress_payload())

        elif path == "/knowledge/subscriptions-view":
            self._send_text(_knowledge_subscriptions_html(), content_type="text/html; charset=utf-8")

        elif path == "/ai-influence":
            period = params.get("period", ["30d"])[0]
            self._send_text(_ai_influence_html(period=period), content_type="text/html; charset=utf-8")

        elif path == "/ai-influence/list":
            try:
                limit = int(params.get("limit", ["80"])[0])
                limit = max(1, min(limit, 300))
            except ValueError:
                limit = 80
            period = params.get("period", ["30d"])[0]
            self._send_json(_ai_influence_payload(limit=limit, period=period))

        elif path == "/ai-influence/report":
            target = _resolve_ai_influence_report(
                params.get("id", [""])[0],
                params.get("artifact", ["report_html"])[0],
            )
            if not target:
                self._send_json({"ok": False, "status": "error", "error": "AI Influence report not found or not allowed"}, status=404)
            else:
                suffix = target.suffix.lower()
                content_type = "text/plain; charset=utf-8"
                if suffix == ".json":
                    content_type = "application/json; charset=utf-8"
                elif suffix in (".html", ".htm"):
                    content_type = "text/html; charset=utf-8"
                elif suffix in (".md", ".markdown"):
                    content_type = "text/markdown; charset=utf-8"
                self._send_text(target.read_text(encoding="utf-8", errors="ignore"), content_type=content_type)

        elif path == "/ai-influence/transcript":
            payload = _resolve_ai_influence_transcript(
                params.get("id", [""])[0],
                params.get("video_ref", [""])[0],
                params.get("video_id", [""])[0],
            )
            if not payload:
                self._send_json({"ok": False, "status": "error", "error": "AI Influence transcript not found or not allowed"}, status=404)
            else:
                self._send_text(
                    _ai_influence_transcript_html(payload["report_id"], payload["video"], payload["transcript"]),
                    content_type="text/html; charset=utf-8",
                )

        elif path == "/mermaid":
            self._send_text(_mermaid_index_html(), content_type="text/html; charset=utf-8")

        elif path == "/mermaid/list":
            self._send_json({"files": _list_mmd_files(), "roots": [str(root) for root in MMD_ALLOWED_ROOTS]})

        elif path == "/mermaid/view":
            mmd = _resolve_mmd_file(params.get("file", [""])[0])
            if not mmd:
                self._send_json({"error": "mmd not found or not allowed"}, status=404)
            else:
                self._send_text(_mermaid_view_html(mmd), content_type="text/html; charset=utf-8")

        elif path == "/mermaid/raw":
            mmd = _resolve_mmd_file(params.get("file", [""])[0])
            if not mmd:
                self._send_json({"error": "mmd not found or not allowed"}, status=404)
            else:
                self._send_text(mmd.read_text(errors="ignore"), content_type="text/plain; charset=utf-8")

        elif path == "/file/open":
            target = _resolve_open_file(params.get("path", [""])[0])
            if not target:
                self._send_json({"ok": False, "status": "error", "error": "file not found or not allowed"}, status=404)
            elif sys.platform != "darwin":
                self._send_json({"ok": False, "status": "warn", "error": "open is only supported on macOS", "path": str(target)}, status=501)
            else:
                try:
                    subprocess.run(["open", str(target)], check=False, timeout=2)
                    self._send_text(
                        f"Opened {html.escape(str(target))}. You may close this tab.",
                        content_type="text/html; charset=utf-8",
                    )
                except Exception as exc:
                    self._send_json({"ok": False, "status": "warn", "error": f"{type(exc).__name__}: {exc}", "path": str(target)}, status=500)

        elif path == "/file/view":
            target = _resolve_open_file(params.get("path", [""])[0])
            if not target:
                self._send_json({"ok": False, "status": "error", "error": "file not found or not allowed"}, status=404)
            else:
                suffix = target.suffix.lower()
                content_type = "text/plain; charset=utf-8"
                if suffix == ".json":
                    content_type = "application/json; charset=utf-8"
                elif suffix in (".md", ".markdown"):
                    content_type = "text/markdown; charset=utf-8"
                elif suffix in (".html", ".htm"):
                    content_type = "text/html; charset=utf-8"
                self._send_text(target.read_text(encoding="utf-8", errors="ignore"), content_type=content_type)

        elif path.startswith("/mermaid/assets/"):
            asset = _asset_path(path.removeprefix("/mermaid/assets/"))
            if not asset:
                self._send_json({"error": "asset not found"}, status=404)
            else:
                ctype = "application/javascript; charset=utf-8"
                if asset.suffix == ".map":
                    ctype = "application/json; charset=utf-8"
                elif asset.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                self._send_file(asset, ctype)

        elif path == "/api/capability":
            # Pane capability summary — skills, mcp_mode, kb_context per pane
            self._send_json(_pane_capability_summary())

        elif path == "/api/evolution":
            self._send_json(_evolution_status())

        elif path == "/benchmark/latest":
            # AP-4: benchmark latest run summary
            import json as _json
            from pathlib import Path as _Path
            _bench_reports = _Path.home() / ".solar" / "harness" / "reports" / "benchmark"
            _latest = _bench_reports / "latest-terminal-bench-2.json"
            if _latest.is_file():
                try:
                    with _latest.open(encoding="utf-8") as _f:
                        self._send_json(_json.load(_f))
                except (OSError, _json.JSONDecodeError):
                    self._send_json({"status": "no_runs", "benchmark": "terminal-bench@2.0"})
            else:
                self._send_json({"status": "no_runs", "benchmark": "terminal-bench@2.0"})

        elif path == "/":
            # _HTML_TEMPLATE is not formatted with str.format(), so collapse the
            # doubled braces used by earlier template-style escaping.
            self._send_text(_HTML_TEMPLATE.replace("{{", "{").replace("}}", "}"), content_type="text/html; charset=utf-8")

        else:
            self._send_json({"error": "not found"}, status=404)


def _find_port() -> int:
    import socket
    for port in PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((BIND_HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available port in range 8765-8775")


def main():
    pid_dir = HARNESS_DIR / "run"
    pid_dir.mkdir(parents=True, exist_ok=True)
    lock_path = pid_dir / "status-server.instance.lock"
    lock_fh = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Solar Harness status server already running; refusing duplicate instance.", flush=True)
        return

    port = _find_port()
    server = ThreadingHTTPServer((BIND_HOST, port), StatusHandler)
    server.daemon_threads = True
    # Write port to pidfile directory so clients can discover it
    (pid_dir / "status-server.port").write_text(str(port))
    print(f"Solar Harness status server listening on http://{BIND_HOST}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        (pid_dir / "status-server.port").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
