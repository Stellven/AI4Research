#!/usr/bin/env python3
"""
Solar Wiki Capture Server

Local-only web UI for pasting web page content into the Obsidian vault raw
staging area. A background scheduler periodically creates wiki-ingest dispatches
for new captures and sends them to Solar builder lab panes.

No external dependencies. Binds to 127.0.0.1 only.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
try:
    import cgi
except ModuleNotFoundError:
    cgi = None
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
SOLAR = HARNESS_DIR / "solar-harness.sh"
CONFIG = Path(os.environ.get("OBSIDIAN_WIKI_CONFIG", str(Path.home() / ".obsidian-wiki" / "config")))
BIND_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("SOLAR_WIKI_CAPTURE_PORT", "8765"))
INTERVAL = int(os.environ.get("SOLAR_WIKI_CAPTURE_INTERVAL", "60"))
AUDIT_SCRIPT = HARNESS_DIR / "lib" / "wiki-upload-audit.py"
BACKFILL_SCRIPT = HARNESS_DIR / "lib" / "wiki-upload-backfill.py"
CHATGPT_IMPORTER = HARNESS_DIR / "lib" / "chatgpt-conversation-ingest.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_vault() -> Path:
    env = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if env:
        return Path(env).expanduser()
    if CONFIG.exists():
        for raw in CONFIG.read_text(errors="ignore").splitlines():
            if raw.startswith("OBSIDIAN_VAULT_PATH="):
                value = raw.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return Path(value).expanduser()
    return Path.home() / "Knowledge"


VAULT = load_vault()
RAW_ROOT = VAULT / "_raw"
WEB_CAPTURE_DIR = RAW_ROOT / "web-captures"
CHATGPT_INBOX_DIR = RAW_ROOT / "chatgpt-extension-inbox"
UPLOAD_DIR = RAW_ROOT / "file-uploads"
DB_EXPORT_DIR = RAW_ROOT / "solar-db-export"
DISPATCH_DIR = RAW_ROOT / "solar-harness" / ".dispatch"
STATE_FILE = RAW_ROOT / "solar-harness" / ".capture-state.json"
PID_FILE = HARNESS_DIR / ".wiki-capture-server.pid"
PORT_FILE = HARNESS_DIR / ".wiki-capture-server.port"


def slugify(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", value, flags=re.UNICODE)
    value = value.strip("-._").lower()
    return value[:80] or "capture"


def safe_filename(value: str) -> str:
    name = Path(value or "upload").name
    stem = Path(name).stem or "upload"
    suffix = Path(name).suffix[:16]
    return f"{slugify(stem)}{suffix.lower()}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def root_raw_ingest_candidate(path: Path) -> bool:
    """Only auto-ingest real root-level raw notes; skip smoke/test sentinels."""
    name = path.name.lower()
    if name.startswith("."):
        return False
    if name.startswith("mirage-smoke") or "smoke" in name or "test" in name:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    if len(text.strip()) < 1000 and not text.startswith("---"):
        return False
    if text.startswith("---"):
        return any(marker in text[:1200] for marker in ("topic:", "artifact_type:", "source: codex", "source: web-capture"))
    return len(text.strip()) >= 1000


def clean_content(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + "\n"


def stable_digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def normalize_capture_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def yaml_scalar(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"version": 1, "captures": {}, "last_scan_at": "", "last_dispatch_at": ""}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"version": 1, "captures": {}, "last_scan_at": "", "last_dispatch_at": ""}


def save_state(state: dict) -> None:
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(STATE_FILE)


def run_cmd(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def timeout_result(args: list[str], timeout: int, exc: subprocess.TimeoutExpired) -> subprocess.CompletedProcess[str]:
    stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
    stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    cmd = " ".join(args)
    return subprocess.CompletedProcess(
        args=args,
        returncode=124,
        stdout=stdout,
        stderr=(stderr or f"timeout after {timeout}s: {cmd}"),
    )


def dispatch_file_from_output(output: str) -> str:
    for raw in reversed((output or "").splitlines()):
        line = raw.strip()
        if line.endswith(".md") and "wiki-" in Path(line).name:
            return line
    return ""


def dispatch_status(path: str | Path) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    match = re.search(r"^status:\s*(\S+)\s*$", text, flags=re.MULTILINE)
    return match.group(1) if match else ""


def existing_dispatch_for_source(source_path: Path) -> dict:
    """Return the newest dispatch that already references source_path."""
    source = str(source_path)
    if not DISPATCH_DIR.exists():
        return {}
    matches = []
    for path in DISPATCH_DIR.glob("wiki-ingest-*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if f"source={source}" not in text and f"source: {source}" not in text:
            continue
        status = dispatch_status(path)
        matches.append({"path": str(path), "status": status, "mtime": path.stat().st_mtime})
    if not matches:
        return {}
    terminal_rank = {"completed": 5, "skipped": 4, "running": 3, "dispatched": 2, "pending": 2, "failed": 1}
    matches.sort(key=lambda item: (terminal_rank.get(item["status"], 0), item["mtime"]), reverse=True)
    return matches[0]


def run_wiki_dispatch(dispatch_file: str, lab_builder: int = 1) -> dict:
    if not dispatch_file:
        return {"ok": False, "error": "missing dispatch file"}
    attempts = []
    order = list(range(lab_builder, 5)) + list(range(1, lab_builder))
    result = None
    selected = lab_builder
    for candidate in order:
        selected = candidate
        args = [str(SOLAR), "wiki", "run-dispatch", dispatch_file, "--lab-builder", str(candidate)]
        try:
            result = run_cmd(args, timeout=8)
        except subprocess.TimeoutExpired as e:
            result = timeout_result(args, 8, e)
        attempts.append(
            {
                "lab_builder": candidate,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )
        if result.returncode == 0:
            break
        # returncode 2 means the pane exists but is busy; try the next lab pane.
        # returncode 124 means one pane/dispatch path timed out; try another pane
        # before giving up so a stale dispatch cannot stall the whole scheduler.
        if result.returncode not in {2, 124}:
            break
    assert result is not None
    return {
        "ok": result.returncode == 0,
        "dispatch_file": dispatch_file,
        "target_lab_builder": selected,
        "attempts": attempts,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "error": "" if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip()),
    }


def dispatch_is_pending_chatgpt(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    if not text.startswith("---"):
        return False
    if re.search(r"^status:\s*pending\s*$", text, flags=re.MULTILINE) is None:
        return False
    return "project=chatgpt" in text and f"source={RAW_ROOT / 'chatgpt'}" in text


def dispatch_pending_chatgpt(state: dict, limit: int = 4) -> list[dict]:
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    lab_builder = int(state.get("next_lab_builder", 1) or 1)
    results = []
    for path in sorted(DISPATCH_DIR.glob("wiki-ingest-*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(results) >= limit:
            break
        if not dispatch_is_pending_chatgpt(path):
            continue
        result = run_wiki_dispatch(str(path), lab_builder=lab_builder)
        results.append(result)
        if result.get("ok"):
            lab_builder = int(result.get("target_lab_builder") or lab_builder)
            lab_builder = 1 if lab_builder >= 4 else lab_builder + 1
    state["next_lab_builder"] = lab_builder
    if results:
        state["last_chatgpt_dispatch_retry_at"] = utc_now()
    return results


def create_capture(
    title: str,
    source_url: str,
    content: str,
    *,
    metadata: dict | None = None,
    capture_method: str = "",
    content_hash: str = "",
    selected_text: str = "",
    canonical_url: str = "",
    capture_schema_version: int = 1,
) -> dict:
    WEB_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    capture_hashes = state.setdefault("capture_hashes", {})
    title = title.strip() or "Untitled Capture"
    source_url = source_url.strip()
    canonical_url = canonical_url.strip() or source_url
    body = clean_content(content)
    digest = content_hash.strip() or stable_digest({
        "kind": "web-capture",
        "url": canonical_url or source_url,
        "content": normalize_capture_text(body),
    })
    existing = capture_hashes.get(digest, {})
    existing_path_raw = str(existing.get("path", "")) if isinstance(existing, dict) else str(existing or "")
    existing_path = Path(existing_path_raw) if existing_path_raw else None
    if existing_path and existing_path.exists():
        existing["last_duplicate_at"] = utc_now()
        existing["duplicate_count"] = int(existing.get("duplicate_count", 0) or 0) + 1
        capture_hashes[digest] = existing
        save_state(state)
        return {"ok": True, "path": existing_path, "duplicate": True, "content_hash": digest}
    ts = utc_now()
    name = f"{safe_ts()}-{slugify(title)}.md"
    path = WEB_CAPTURE_DIR / name
    md = [
        "---",
        "source: web-capture",
        f"capture_schema_version: {int(capture_schema_version or 1)}",
        f"title: {yaml_scalar(title)}",
        f"captured_at: {ts}",
        "visibility: internal",
        "tags: [web-capture, raw-ingest]",
        f"content_hash: {yaml_scalar(digest)}",
    ]
    if source_url:
        md.append(f"source_url: {yaml_scalar(source_url)}")
    if canonical_url and canonical_url != source_url:
        md.append(f"canonical_url: {yaml_scalar(canonical_url)}")
    if capture_method:
        md.append(f"capture_method: {yaml_scalar(capture_method)}")
    md.extend(
        [
            "---",
            "",
            f"# {title}",
            "",
        ]
    )
    if source_url:
        md.extend([f"Source: {source_url}", ""])
    if selected_text.strip():
        md.extend(["## Selected Text", "", clean_content(selected_text)])
    if metadata:
        md.extend(["## Capture Metadata", "", "```json", json.dumps(metadata, ensure_ascii=False, indent=2), "```", ""])
    md.extend(["## Captured Content", "", body])
    path.write_text("\n".join(md), encoding="utf-8")
    capture_hashes[digest] = {
        "path": str(path),
        "source_url": source_url,
        "canonical_url": canonical_url,
        "title": title,
        "created_at": ts,
        "duplicate_count": 0,
    }
    save_state(state)
    return {"ok": True, "path": path, "duplicate": False, "content_hash": digest}


def chatgpt_payload_digest(payload: dict) -> str:
    messages = []
    for item in payload.get("messages") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        text = normalize_capture_text(str(item.get("text") or item.get("content") or ""))
        if role and text:
            messages.append({"role": role, "text": text})
    return str(payload.get("content_hash") or "").strip() or stable_digest({
        "kind": "chatgpt-capture",
        "conversation_id": str(payload.get("conversation_id") or ""),
        "url": str(payload.get("canonical_url") or payload.get("url") or ""),
        "messages": messages,
    })


def import_chatgpt_capture(payload: dict) -> dict:
    if not CHATGPT_IMPORTER.exists():
        return {"ok": False, "error": f"chatgpt importer not found: {CHATGPT_IMPORTER}"}
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return {"ok": False, "error": "messages is required"}
    state = load_state()
    chatgpt_hashes = state.setdefault("chatgpt_hashes", {})
    digest = chatgpt_payload_digest(payload)
    existing = chatgpt_hashes.get(digest, {})
    existing_out_raw = str(existing.get("out_dir", "")) if isinstance(existing, dict) else ""
    existing_out = Path(existing_out_raw) if existing_out_raw else None
    if existing_out and existing_out.exists():
        existing["last_duplicate_at"] = utc_now()
        existing["duplicate_count"] = int(existing.get("duplicate_count", 0) or 0) + 1
        chatgpt_hashes[digest] = existing
        save_state(state)
        return {
            "ok": True,
            "duplicate": True,
            "content_hash": digest,
            "out_dir": str(existing_out),
            "manifest": existing.get("manifest", ""),
            "dispatch_output": existing.get("dispatch_output", ""),
            "source_inbox": existing.get("source_inbox", ""),
        }
    payload = {**payload, "content_hash": digest}
    CHATGPT_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    title = str(payload.get("title") or "ChatGPT Browser Capture")
    source_path = CHATGPT_INBOX_DIR / f"{safe_ts()}-{slugify(title)}.json"
    source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = run_cmd(
        [
            "python3",
            str(CHATGPT_IMPORTER),
            "--source",
            str(source_path),
            "--out-root",
            str(RAW_ROOT / "chatgpt"),
            "--project",
            "chatgpt",
            "--json",
        ],
        timeout=90,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "source": str(source_path),
            "error": result.stderr.strip() or result.stdout.strip() or f"importer failed: exit={result.returncode}",
        }
    try:
        data = json.loads(result.stdout)
    except Exception as exc:
        return {"ok": False, "source": str(source_path), "error": f"invalid importer json: {exc}", "stdout": result.stdout}
    dispatch_file = dispatch_file_from_output(str(data.get("dispatch_output") or ""))
    if dispatch_file:
        data["run_dispatch"] = run_wiki_dispatch(dispatch_file, lab_builder=1)
    data["source_inbox"] = str(source_path)
    data["content_hash"] = digest
    data["duplicate"] = False
    chatgpt_hashes[digest] = {
        "source_inbox": str(source_path),
        "out_dir": str(data.get("out_dir", "")),
        "manifest": str(data.get("manifest", "")),
        "dispatch_output": str(data.get("dispatch_output", "")),
        "title": title,
        "url": str(payload.get("url") or ""),
        "conversation_id": str(payload.get("conversation_id") or ""),
        "created_at": utc_now(),
        "duplicate_count": 0,
    }
    save_state(state)
    return data


def save_uploaded_files(form: cgi.FieldStorage) -> list[Path]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    field = form["files"] if "files" in form else []
    items = field if isinstance(field, list) else [field]
    saved: list[Path] = []
    ts = safe_ts()
    for idx, item in enumerate(items, start=1):
        filename = getattr(item, "filename", "") or ""
        fileobj = getattr(item, "file", None)
        if not filename or fileobj is None:
            continue
        target = UPLOAD_DIR / f"{ts}-{idx:02d}-{safe_filename(filename)}"
        with target.open("wb") as out:
            shutil.copyfileobj(fileobj, out)
        saved.append(target)
    return saved


def dispatch_capture(path: Path, lab_builder: int) -> tuple[bool, str, str]:
    ingest = run_cmd([str(SOLAR), "wiki", "ingest", "--source", str(path), "--mode", "append"])
    if ingest.returncode != 0:
        return False, "", ingest.stderr.strip() or ingest.stdout.strip()
    dispatch_file = (ingest.stdout.strip().splitlines() or [""])[-1]
    if not dispatch_file:
        return False, "", "wiki ingest did not print dispatch file"
    send = run_wiki_dispatch(dispatch_file, lab_builder=lab_builder)
    if not send.get("ok"):
        return False, dispatch_file, str(send.get("error") or send)
    return True, dispatch_file, str(send.get("stdout") or send)


def upload_batches(limit: int = 4) -> list[tuple[str, list[Path]]]:
    """Return recent upload batches by timestamp prefix."""
    if not UPLOAD_DIR.exists():
        return []
    groups: dict[str, list[Path]] = {}
    for path in UPLOAD_DIR.iterdir():
        if not path.is_file():
            continue
        match = re.match(r"^(\d{8}T\d{6}Z)-\d{2}-", path.name)
        if not match:
            continue
        groups.setdefault(match.group(1), []).append(path)
    return sorted(groups.items(), key=lambda item: item[0], reverse=True)[:limit]


def audit_upload_batch(batch_id: str) -> dict:
    result = run_cmd(
        ["python3", str(AUDIT_SCRIPT), "--batch", batch_id, "--json", "--vault", str(VAULT)],
        timeout=90,
    )
    if result.returncode not in (0, 1):
        return {"ok": False, "batch": batch_id, "error": result.stderr.strip() or result.stdout.strip()}
    try:
        data = json.loads(result.stdout)
    except Exception as exc:
        return {"ok": False, "batch": batch_id, "error": f"invalid audit json: {exc}"}
    data["ok"] = True
    return data


def backfill_upload_batch(batch_id: str) -> dict:
    result = run_cmd(
        ["python3", str(BACKFILL_SCRIPT), "--batch", batch_id, "--repair", "--json", "--vault", str(VAULT)],
        timeout=180,
    )
    if result.returncode not in (0, 1):
        return {"ok": False, "batch": batch_id, "error": result.stderr.strip() or result.stdout.strip()}
    try:
        data = json.loads(result.stdout)
    except Exception as exc:
        return {"ok": False, "batch": batch_id, "error": f"invalid backfill json: {exc}"}
    data["ok"] = True
    return data


def auto_backfill_uploads(state: dict) -> list[dict]:
    """Repair completed upload batches so vault, qmd, and Solar DB converge automatically."""
    if not AUDIT_SCRIPT.exists() or not BACKFILL_SCRIPT.exists():
        return []
    records = state.setdefault("upload_backfills", {})
    results = []
    for batch_id, files in upload_batches(limit=4):
        cached = records.get(batch_id, {})
        if cached.get("status") == "ok" and cached.get("total") == len(files):
            continue
        audit = audit_upload_batch(batch_id)
        if not audit.get("ok"):
            records[batch_id] = {"status": "audit_error", "total": len(files), "error": audit.get("error"), "updated_at": utc_now()}
            results.append({"batch": batch_id, "status": "audit_error", "error": audit.get("error")})
            continue
        total = int(audit.get("total", 0) or 0)
        dispatch_done = int(audit.get("dispatch", {}).get("completed", 0) or 0)
        gaps = {
            "qmd": int(audit.get("qmd", {}).get("missing", 0) or 0),
            "vault": int(audit.get("vault", {}).get("missing", 0) or 0),
            "solar_db": int(audit.get("solar_db", {}).get("missing", 0) or 0),
        }
        if total <= 0 or dispatch_done < total:
            records[batch_id] = {
                "status": "waiting_dispatch",
                "total": total,
                "dispatch_completed": dispatch_done,
                "gaps": gaps,
                "updated_at": utc_now(),
            }
            results.append({"batch": batch_id, "status": "waiting_dispatch", "dispatch_completed": dispatch_done, "total": total})
            continue
        if not any(gaps.values()):
            records[batch_id] = {"status": "ok", "total": total, "gaps": gaps, "updated_at": utc_now()}
            results.append({"batch": batch_id, "status": "ok", "total": total})
            continue
        backfill = backfill_upload_batch(batch_id)
        if not backfill.get("ok"):
            records[batch_id] = {"status": "backfill_error", "total": total, "gaps": gaps, "error": backfill.get("error"), "updated_at": utc_now()}
            results.append({"batch": batch_id, "status": "backfill_error", "error": backfill.get("error")})
            continue
        records[batch_id] = {
            "status": "repaired",
            "total": total,
            "before": gaps,
            "after": {
                "qmd": int(backfill.get("qmd", {}).get("missing", 0) or 0),
                "vault": int(backfill.get("vault", {}).get("missing", 0) or 0),
                "solar_db": int(backfill.get("solar_db", {}).get("missing", 0) or 0),
            },
            "stubs_created": backfill.get("stubs_created", 0),
            "updated_at": utc_now(),
        }
        state["last_upload_backfill_at"] = utc_now()
        results.append({"batch": batch_id, "status": "repaired", "stubs_created": backfill.get("stubs_created", 0)})
    return results


def scan_once(limit: int = 4) -> dict:
    WEB_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DB_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    captures = state.setdefault("captures", {})
    state["last_scan_at"] = utc_now()
    dispatched = []
    errors = []
    lab_builder = int(state.get("next_lab_builder", 1) or 1)

    source_paths = [
        *(p for p in RAW_ROOT.glob("*.md") if p.is_file() and root_raw_ingest_candidate(p)),
        *WEB_CAPTURE_DIR.glob("*.md"),
        *(p for p in UPLOAD_DIR.iterdir() if p.is_file() and not p.name.startswith(".")),
        *(p for p in DB_EXPORT_DIR.rglob("*.md") if p.is_file() and not p.name.startswith(".")),
    ]
    for path in sorted(source_paths, key=lambda p: p.stat().st_mtime, reverse=True):
        if len(dispatched) >= limit:
            break
        digest = sha256(path)
        rec = captures.get(str(path), {})
        existing = existing_dispatch_for_source(path)
        if not rec and existing and existing.get("status") in {"completed", "skipped", "running", "pending", "dispatched"}:
            captures[str(path)] = {
                "status": existing.get("status"),
                "content_hash": digest,
                "source_path": str(path),
                "dispatch_file": existing.get("path", ""),
                "deduped_at": utc_now(),
            }
            continue
        if rec.get("content_hash") == digest:
            rec_status = rec.get("status")
            dispatch_file = rec.get("dispatch_file") or ""
            live_status = dispatch_status(dispatch_file) if dispatch_file else ""
            if rec_status in {"dispatched", "completed", "running"} or live_status in {"running", "completed"}:
                continue
            if dispatch_file and live_status in {"", "pending", "dispatched"}:
                retry = run_wiki_dispatch(dispatch_file, lab_builder=lab_builder)
                if retry.get("ok"):
                    captures[str(path)] = {
                        **rec,
                        "status": "running",
                        "content_hash": digest,
                        "source_path": str(path),
                        "dispatch_file": dispatch_file,
                        "dispatched_at": utc_now(),
                        "target_lab_builder": retry.get("target_lab_builder", lab_builder),
                    }
                    dispatched.append({"source": str(path), "dispatch": dispatch_file, "lab_builder": retry.get("target_lab_builder", lab_builder), "retry": True})
                    lab_builder = int(retry.get("target_lab_builder") or lab_builder)
                    lab_builder = 1 if lab_builder >= 4 else lab_builder + 1
                else:
                    captures[str(path)] = {
                        **rec,
                        "status": "error",
                        "content_hash": digest,
                        "source_path": str(path),
                        "dispatch_file": dispatch_file,
                        "error": retry.get("error") or str(retry),
                        "updated_at": utc_now(),
                    }
                    errors.append({"source": str(path), "dispatch": dispatch_file, "error": retry.get("error") or str(retry), "retry": True})
                continue
        ok, dispatch_file, detail = dispatch_capture(path, lab_builder)
        if ok:
            captures[str(path)] = {
                "status": "running",
                "content_hash": digest,
                "source_path": str(path),
                "dispatch_file": dispatch_file,
                "dispatched_at": utc_now(),
                "target_lab_builder": lab_builder,
            }
            state["last_dispatch_at"] = utc_now()
            dispatched.append({"source": str(path), "dispatch": dispatch_file, "lab_builder": lab_builder})
            lab_builder = 1 if lab_builder >= 4 else lab_builder + 1
        else:
            captures[str(path)] = {
                **rec,
                "status": "error",
                "content_hash": digest,
                "source_path": str(path),
                "dispatch_file": dispatch_file,
                "error": detail,
                "updated_at": utc_now(),
            }
            errors.append({"source": str(path), "dispatch": dispatch_file, "error": detail})

    state["next_lab_builder"] = lab_builder
    backfills = auto_backfill_uploads(state)
    chatgpt_dispatches = dispatch_pending_chatgpt(state, limit=limit)
    state.pop("last_error", None)
    if errors:
        state["last_dispatch_errors_at"] = utc_now()
        state["last_dispatch_error_count"] = len(errors)
        state["last_dispatch_error_sample"] = errors[0].get("error", "")
    save_state(state)
    return {"dispatched": dispatched, "errors": errors, "backfills": backfills, "chatgpt_dispatches": chatgpt_dispatches, "state": state}


def scheduler_loop(stop: threading.Event) -> None:
    while not stop.wait(INTERVAL):
        try:
            scan_once()
        except Exception as exc:
            state = load_state()
            state["last_error"] = str(exc)
            state["last_scan_at"] = utc_now()
            save_state(state)


HTML_PAGE = """<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Solar Wiki Capture</title>
  <style>
    :root { --bg:#f7f3ea; --ink:#191711; --muted:#6f675c; --line:#ded4c3; --brand:#2f6f73; --card:#fffdf8; --hot:#bc5f36; }
    * { box-sizing:border-box; }
    body { margin:0; font-family: ui-serif, Georgia, "Times New Roman", serif; background: radial-gradient(circle at top left,#e2efe5,transparent 36%), linear-gradient(135deg,#f7f3ea,#efe3d0); color:var(--ink); }
    main { max-width:980px; margin:0 auto; padding:40px 22px; }
    header { display:flex; justify-content:space-between; gap:20px; align-items:flex-end; margin-bottom:24px; }
    h1 { margin:0; font-size:42px; letter-spacing:-1px; }
    p { color:var(--muted); line-height:1.5; }
    .card { background:rgba(255,253,248,.9); border:1px solid var(--line); border-radius:22px; padding:22px; box-shadow:0 18px 45px rgba(70,52,26,.12); }
    label { display:block; font-weight:700; margin:14px 0 8px; }
    input, textarea { width:100%; border:1px solid var(--line); border-radius:14px; padding:13px 14px; background:#fffaf1; color:var(--ink); font:15px ui-monospace, SFMono-Regular, Menlo, monospace; }
    textarea { min-height:360px; resize:vertical; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    button { appearance:none; border:0; border-radius:999px; padding:13px 18px; background:var(--brand); color:white; font-weight:800; cursor:pointer; }
    button.secondary { background:#513f30; }
    .actions { display:flex; gap:10px; margin-top:18px; flex-wrap:wrap; }
    .status { margin-top:16px; padding:14px; border-radius:14px; background:#eef4ef; border:1px solid #c9dacc; white-space:pre-wrap; font:13px ui-monospace, SFMono-Regular, Menlo, monospace; }
    .pill { display:inline-block; padding:7px 11px; border:1px solid var(--line); border-radius:999px; background:#fffaf1; color:var(--muted); font:13px ui-monospace, SFMono-Regular, Menlo, monospace; }
    @media (max-width:720px){ .row, header { display:block; } h1 { font-size:34px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <div class="pill">127.0.0.1 · Solar Wiki Capture</div>
        <h1>Capture into Knowledge</h1>
        <p>粘贴网页正文，或选择多个文件，保存到 <code>Knowledge/_raw/</code>。后台会定时派发 wiki-ingest。</p>
      </div>
      <button class="secondary" onclick="runNow()">Run ingest now</button>
    </header>
    <section class="card">
      <div class="row">
        <div>
          <label>标题</label>
          <input id="title" placeholder="例如：OpenAI Symphony 架构笔记">
        </div>
        <div>
          <label>来源 URL（可选）</label>
          <input id="url" placeholder="https://...">
        </div>
      </div>
      <label>网页内容</label>
      <textarea id="content" placeholder="把网页正文粘贴到这里"></textarea>
      <div class="actions">
        <button onclick="saveCapture()">Save to _raw</button>
        <button class="secondary" onclick="status()">Refresh status</button>
      </div>
      <div id="status" class="status">Loading...</div>
    </section>
    <section class="card upload-card">
      <h2>文件上传</h2>
      <p>选择 PDF、Markdown、JSONL、日志、图片等文件；服务会复制到 <code>Knowledge/_raw/file-uploads/</code> 并自动入库提取。</p>
      <label>选择多个文件</label>
      <input id="files" type="file" multiple>
      <div class="actions">
        <button onclick="uploadFiles()">Upload files to _raw</button>
        <button class="secondary" onclick="runNow()">Run ingest now</button>
      </div>
      <div id="uploadStatus" class="status">No files selected.</div>
    </section>
  </main>
<script>
async function post(path, body) {
  const res = await fetch(path, {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  const text = await res.text();
  if (!res.ok) throw new Error(text);
  return JSON.parse(text);
}
async function saveCapture() {
  const body = new URLSearchParams({title: title.value, source_url: url.value, content: content.value});
  const data = await post('/capture', body);
  document.getElementById('status').textContent = JSON.stringify(data, null, 2);
}
async function uploadFiles() {
  const picker = document.getElementById('files');
  if (!picker.files.length) {
    document.getElementById('uploadStatus').textContent = '请选择至少一个文件。';
    return;
  }
  const body = new FormData();
  for (const file of picker.files) body.append('files', file, file.name);
  const res = await fetch('/upload', {method:'POST', body});
  const text = await res.text();
  if (!res.ok) throw new Error(text);
  const data = JSON.parse(text);
  document.getElementById('uploadStatus').textContent = JSON.stringify(data, null, 2);
  await status();
}
async function runNow() {
  const data = await post('/run-now', '');
  document.getElementById('status').textContent = JSON.stringify(data, null, 2);
}
async function status() {
  const res = await fetch('/status');
  document.getElementById('status').textContent = JSON.stringify(await res.json(), null, 2);
}
status();
</script>
</body>
</html>
"""


DB_PATH = Path(os.environ.get("SOLAR_DB", str(Path.home() / ".solar" / "solar.db")))
INDEXER = HARNESS_DIR / "lib" / "obsidian-vault-indexer.py"
MANIFEST_PATH = Path(os.environ.get(
    "SOLAR_KB_MANIFEST",
    str(HARNESS_DIR / "state" / "knowledge-manifest.json")
))


def _solar_kb_status() -> dict:
    """Query solar.db for retrieval stats — fail-open."""
    result: dict = {
        "db_exists": DB_PATH.exists(),
        "fts_docs": 0,
        "cortex_sources": 0,
        "hook_enabled": os.environ.get("SOLAR_KB_CONTEXT", "1") != "0",
        "hook_path": str(HARNESS_DIR.parent.parent / ".claude" / "hooks" / "solar-knowledge-context.sh"),
        "last_query_ms": None,
    }
    if not DB_PATH.exists():
        return result
    try:
        import sqlite3 as _sq
        conn = _sq.connect(str(DB_PATH), timeout=0.3)
        conn.execute("PRAGMA query_only=1")
        try:
            result["fts_docs"] = (conn.execute(
                "SELECT COUNT(*) FROM fts_unified_search"
            ).fetchone() or [0])[0]
        except Exception:
            pass
        try:
            result["cortex_sources"] = (conn.execute(
                "SELECT COUNT(*) FROM cortex_sources"
            ).fetchone() or [0])[0]
        except Exception:
            pass
        conn.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def _obsidian_sync_status() -> dict:
    """Query obsidian_vault_index stats and manifest — fail-open."""
    result: dict = {
        "vault": str(VAULT),
        "vault_exists": VAULT.exists(),
        "indexed_notes": 0,
        "indexer_available": INDEXER.exists(),
        "last_sync_at": "",
        "last_exported_at": "",
        "scheduler_interval_seconds": INTERVAL,
    }
    # Manifest cursor
    if MANIFEST_PATH.exists():
        try:
            m = json.loads(MANIFEST_PATH.read_text())
            result["last_exported_at"] = m.get("last_exported_at", "")
        except Exception:
            pass
    if not DB_PATH.exists():
        return result
    try:
        import sqlite3 as _sq
        conn = _sq.connect(str(DB_PATH), timeout=0.3)
        conn.execute("PRAGMA query_only=1")
        try:
            row = conn.execute(
                "SELECT COUNT(*), MAX(indexed_at) FROM obsidian_vault_index WHERE deleted_at IS NULL"
            ).fetchone()
            if row:
                result["indexed_notes"] = row[0] or 0
                result["last_sync_at"] = row[1] or ""
        except Exception:
            pass
        conn.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def _accepted_artifact_status() -> dict:
    """Return accepted artifact export stats from manifest — fail-open."""
    result: dict = {
        "exported_count": 0,
        "pending_ingest_count": 0,
        "failed_count": 0,
        "last_sid": "",
        "last_path": "",
        "last_exported_at": "",
        "last_error": "",
        "manifest_exists": False,
    }
    manifest_path = VAULT / "_raw" / "solar-harness" / ".manifest" / "accepted-artifacts.json"
    if not manifest_path.exists():
        # Also check if vault doesn't exist yet — not an error
        result["manifest_exists"] = False
        return result
    try:
        manifest = json.loads(manifest_path.read_text())
        result["manifest_exists"] = True
        entries = manifest.get("entries", {})
        result["exported_count"] = len(entries)
        pending = 0
        failed = 0
        last_sid = ""
        last_path = ""
        last_at = ""
        last_err = ""
        for sid, entry in entries.items():
            ks = entry.get("knowledge_export_status", "")
            if ks == "pending" or ks == "exported":
                pending += 1
            elif ks == "failed":
                failed += 1
                last_err = entry.get("knowledge_export_error", "")
            at = entry.get("knowledge_exported_at", "")
            if at > last_at:
                last_at = at
                last_sid = sid
                last_path = entry.get("knowledge_export_path", "")
        result["pending_ingest_count"] = pending
        result["failed_count"] = failed
        result["last_sid"] = last_sid
        result["last_path"] = last_path
        result["last_exported_at"] = last_at
        result["last_error"] = last_err
    except Exception as e:
        result["error"] = str(e)
    return result


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=2), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, HTML_PAGE, "text/html; charset=utf-8")
        elif parsed.path == "/status":
            state = load_state()
            web_files = [str(p) for p in sorted(WEB_CAPTURE_DIR.glob("*.md"))] if WEB_CAPTURE_DIR.exists() else []
            upload_files = [str(p) for p in sorted(UPLOAD_DIR.iterdir()) if p.is_file()] if UPLOAD_DIR.exists() else []
            db_export_files = [str(p) for p in sorted(DB_EXPORT_DIR.rglob("*.md"))] if DB_EXPORT_DIR.exists() else []
            self._json(200, {
                "ok": True,
                "vault": str(VAULT),
                "raw_root": str(RAW_ROOT),
                "web_capture_dir": str(WEB_CAPTURE_DIR),
                "upload_dir": str(UPLOAD_DIR),
                "db_export_dir": str(DB_EXPORT_DIR),
                "interval_seconds": INTERVAL,
                "captures_seen": len(state.get("captures", {})),
                "web_capture_files": len(web_files),
                "uploaded_files": len(upload_files),
                "db_export_files": len(db_export_files),
                "raw_files": len(web_files) + len(upload_files) + len(db_export_files),
                "last_scan_at": state.get("last_scan_at", ""),
                "last_dispatch_at": state.get("last_dispatch_at", ""),
                "last_upload_backfill_at": state.get("last_upload_backfill_at", ""),
                "last_error": state.get("last_error", ""),
                "dedup": {
                    "web_hashes": len(state.get("capture_hashes", {})),
                    "chatgpt_hashes": len(state.get("chatgpt_hashes", {})),
                },
                "upload_backfills": state.get("upload_backfills", {}),
                "solar_kb": _solar_kb_status(),
                "obsidian_sync": _obsidian_sync_status(),
            })
        elif parsed.path == "/api/accepted-artifacts":
            # sprint-20260508-accepted-artifact-knowledge: accepted artifact export status
            self._json(200, {
                "ok": True,
                "accepted_artifacts": _accepted_artifact_status(),
            })
        elif parsed.path == "/healthz":
            self._send(200, "ok")
        else:
            self._send(404, "not found")

    def do_OPTIONS(self) -> None:
        self._send(204, "")

    def do_POST(self) -> None:
        if self.path == "/capture":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            fields = urllib.parse.parse_qs(raw)
            title = fields.get("title", [""])[0]
            source_url = fields.get("source_url", [""])[0]
            content = fields.get("content", [""])[0]
            if not content.strip():
                self._json(400, {"ok": False, "error": "content is required"})
                return
            result = create_capture(title, source_url, content)
            self._json(200, {
                "ok": True,
                "path": str(result.get("path", "")),
                "duplicate": bool(result.get("duplicate")),
                "content_hash": result.get("content_hash", ""),
                "message": "saved; auto-ingest scheduler will pick it up" if not result.get("duplicate") else "duplicate capture; existing file reused",
            })
        elif self.path == "/capture-json":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except Exception as exc:
                self._json(400, {"ok": False, "error": f"invalid json: {exc}"})
                return
            content = str(payload.get("content") or "")
            if not content.strip():
                self._json(400, {"ok": False, "error": "content is required"})
                return
            result = create_capture(
                str(payload.get("title") or ""),
                str(payload.get("url") or payload.get("source_url") or ""),
                content,
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                capture_method=str(payload.get("capture_method") or ""),
                content_hash=str(payload.get("content_hash") or ""),
                selected_text=str(payload.get("selected_text") or ""),
                canonical_url=str(payload.get("canonical_url") or ""),
                capture_schema_version=int(payload.get("capture_schema_version") or 2),
            )
            self._json(200, {
                "ok": True,
                "path": str(result.get("path", "")),
                "duplicate": bool(result.get("duplicate")),
                "content_hash": result.get("content_hash", ""),
                "message": "saved; auto-ingest scheduler will pick it up" if not result.get("duplicate") else "duplicate capture; existing file reused",
            })
        elif self.path == "/chatgpt-import":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except Exception as exc:
                self._json(400, {"ok": False, "error": f"invalid json: {exc}"})
                return
            result = import_chatgpt_capture(payload)
            self._json(200 if result.get("ok") else 400, result)
        elif self.path == "/upload":
            if cgi is None:
                self._json(501, {"ok": False, "error": "multipart upload requires Python cgi module; use /capture or /chatgpt-import"})
                return
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            saved = save_uploaded_files(form)
            if not saved:
                self._json(400, {"ok": False, "error": "no files uploaded"})
                return
            self._json(200, {
                "ok": True,
                "saved": [str(p) for p in saved],
                "message": "uploaded; auto-ingest scheduler will pick them up",
            })
        elif self.path == "/run-now":
            result = scan_once()
            self._json(200, {
                "ok": True,
                "dispatched": result["dispatched"],
                "errors": result["errors"],
                "backfills": result.get("backfills", []),
                "chatgpt_dispatches": result.get("chatgpt_dispatches", []),
            })
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[wiki-capture] " + fmt % args + "\n")


def main() -> int:
    WEB_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    CHATGPT_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DB_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    thread = threading.Thread(target=scheduler_loop, args=(stop,), daemon=True)
    thread.start()

    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer((BIND_HOST, port), Handler)
    PID_FILE.write_text(str(os.getpid()) + "\n")
    PORT_FILE.write_text(str(port) + "\n")
    print(f"Solar Wiki Capture listening on http://{BIND_HOST}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
