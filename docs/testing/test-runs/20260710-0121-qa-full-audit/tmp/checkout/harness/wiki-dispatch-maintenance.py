#!/usr/bin/env python3
"""Maintain Solar Obsidian wiki dispatch files.

The dispatch directory also contains result files. This tool only treats
frontmatter `type: wiki-dispatch` as actionable backlog.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


TERMINAL = {"completed", "success", "failed", "skipped", "chained", "skipped-duplicate"}
ACTIVE = {"pending", "dispatched", "running", ""}
STALE_FULL_VAULT_INGEST_CUTOFF = "20260509T000000Z"
STALE_RUNNING_AFTER = timedelta(hours=6)


@dataclass
class Dispatch:
    path: Path
    meta: dict[str, str]
    text: str

    @property
    def status(self) -> str:
        return self.meta.get("status", "").strip()

    @property
    def generated(self) -> str:
        return self.meta.get("generated_at", "").strip()

    @property
    def source(self) -> str:
        match = re.search(r"^\s*-\s*source=(.+)$", self.text, re.M)
        if match:
            return match.group(1).strip()
        return self.meta.get("reingest_source", "").strip()

    @property
    def destination(self) -> str:
        return self.meta.get("destination", "").strip()


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    meta: dict[str, str] = {}
    for raw in text[4:end].splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def read_dispatches(dispatch_dir: Path) -> tuple[list[Dispatch], dict[str, int]]:
    ignored: dict[str, int] = {}
    dispatches: list[Dispatch] = []
    for path in sorted(dispatch_dir.glob("*.md")):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            ignored["read_error"] = ignored.get("read_error", 0) + 1
            continue
        meta = parse_frontmatter(text)
        if meta.get("type") != "wiki-dispatch":
            ignored[meta.get("type") or "no_type"] = ignored.get(meta.get("type") or "no_type", 0) + 1
            continue
        dispatches.append(Dispatch(path=path, meta=meta, text=text))
    return dispatches, ignored


def result_dispatches(dispatch_dir: Path) -> set[str]:
    out: set[str] = set()
    for path in dispatch_dir.glob("wiki-result-*.md"):
        try:
            text = path.read_text(errors="ignore")[:1200]
        except OSError:
            continue
        meta = parse_frontmatter(text)
        dispatch = meta.get("dispatch", "").strip()
        status = meta.get("status", "").strip()
        if dispatch and status in {"success", "completed"}:
            out.add(dispatch)
    return out


def source_is_covered(vault: Path, source: str) -> tuple[bool, str]:
    if not source:
        return False, ""
    source_path = Path(source)
    candidates = [source_path.name]
    if source_path.suffix:
        candidates.append(source_path.stem)
        candidates.append(re.sub(r"^\d{1,8}[-_]", "", source_path.stem))
        candidates.append(re.sub(r"^\d{8}T\d{6}Z-\d{1,4}-", "", source_path.stem))
    candidates = [x for x in dict.fromkeys(candidates) if len(x) >= 8]
    if not candidates:
        return False, ""
    for path in vault.glob("**/*.md"):
        parts = set(path.relative_to(vault).parts)
        if "_raw" in parts:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if any(candidate in text for candidate in candidates):
            return True, str(path)
    return False, ""


def resolve_source_path(vault: Path, source: str) -> Optional[Path]:
    if not source:
        return None
    source_path = Path(source).expanduser()
    if source_path.is_absolute():
        return source_path if source_path.exists() else None
    candidates = [
        source_path,
        vault / source_path,
        vault / "_raw" / source_path,
        vault / "_raw" / "file-uploads" / source_path.name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def generated_is_stale(generated: str, now: Optional[datetime] = None) -> bool:
    match = re.match(r"^(\d{8}T\d{6}Z)", generated or "")
    if not match:
        return False
    try:
        ts = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (now or datetime.now(timezone.utc)) - ts > STALE_RUNNING_AFTER


def status_counts(dispatches: list[Dispatch]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in dispatches:
        status = item.status or "no_status"
        counts[status] = counts.get(status, 0) + 1
    return counts


def set_status(item: Dispatch, status: str, reason: str) -> None:
    text = item.text
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if re.search(r"^status:\s*.*$", text, re.M):
        text = re.sub(r"^status:\s*.*$", f"status: {status}", text, count=1, flags=re.M)
    else:
        text = text.replace("---\n", f"---\nstatus: {status}\n", 1)
    end = text.find("\n---", 4)
    if end >= 0:
        insert = f"\nmaintenance_at: {stamp}\nmaintenance_reason: {reason}"
        text = text[:end] + insert + text[end:]
    item.path.write_text(text)


def summarize(dispatch_dir: Path) -> dict:
    dispatches, ignored = read_dispatches(dispatch_dir)
    counts = status_counts(dispatches)
    unresolved = sum(counts.get(k, 0) for k in ("pending", "dispatched", "running", "no_status"))
    return {
        "dispatch_dir": str(dispatch_dir),
        "dispatch_total": len(dispatches),
        "counts": counts,
        "unresolved": unresolved,
        "ignored_non_dispatch": ignored,
    }


def repair(dispatch_dir: Path, vault: Path, apply: bool) -> dict:
    dispatches, ignored = read_dispatches(dispatch_dir)
    done_results = result_dispatches(dispatch_dir)
    now = datetime.now(timezone.utc)
    actions = []
    for item in dispatches:
        status = item.status
        if status in TERMINAL:
            continue
        if item.destination:
            dest = vault / item.destination
            if dest.exists() and dest.stat().st_size > 800:
                actions.append({
                    "file": item.path.name,
                    "from": status or "no_status",
                    "to": "completed",
                    "reason": "destination_note_exists",
                    "destination": item.destination,
                    "bytes": dest.stat().st_size,
                })
                if apply:
                    set_status(item, "completed", "destination_note_exists")
                continue
        if item.path.name in done_results:
            actions.append({"file": item.path.name, "from": status or "no_status", "to": "completed", "reason": "matching_success_result"})
            if apply:
                set_status(item, "completed", "matching_success_result")
            continue
        source_path = resolve_source_path(vault, item.source)
        if status == "running" and generated_is_stale(item.generated, now) and source_path:
            actions.append({
                "file": item.path.name,
                "from": "running",
                "to": "pending",
                "reason": "stale_running_requeued",
                "source": item.source,
                "resolved_source": str(source_path),
            })
            if apply:
                set_status(item, "pending", "stale_running_requeued")
            continue
        if (
            item.meta.get("action") == "ingest"
            and not item.source
            and item.generated
            and item.generated < STALE_FULL_VAULT_INGEST_CUTOFF
        ):
            actions.append({
                "file": item.path.name,
                "from": status or "no_status",
                "to": "skipped",
                "reason": "stale_duplicate_full_vault_ingest",
            })
            if apply:
                set_status(item, "skipped", "stale_duplicate_full_vault_ingest")
            continue
        if (
            item.meta.get("action") == "ingest"
            and item.source
            and item.generated
            and item.generated < STALE_FULL_VAULT_INGEST_CUTOFF
            and ("/_raw/solar-db-export/" in item.source or "/_raw/chatgpt/" in item.source)
        ):
            actions.append({
                "file": item.path.name,
                "from": status or "no_status",
                "to": "skipped",
                "reason": "historical_raw_backlog_archived_source_retained",
                "source": item.source,
            })
            if apply:
                set_status(item, "skipped", "historical_raw_backlog_archived_source_retained")
            continue
        if item.meta.get("action") in {"query", "update"} and not item.source and item.generated < "20260508T000000Z":
            actions.append({
                "file": item.path.name,
                "from": status or "no_status",
                "to": "skipped",
                "reason": "stale_legacy_control_dispatch",
            })
            if apply:
                set_status(item, "skipped", "stale_legacy_control_dispatch")
            continue
        covered, evidence = source_is_covered(vault, item.source)
        if covered:
            actions.append({
                "file": item.path.name,
                "from": status or "no_status",
                "to": "completed",
                "reason": "source_covered_in_vault",
                "source": item.source,
                "evidence": evidence,
            })
            if apply:
                set_status(item, "completed", "source_covered_in_vault")
            continue
    after = summarize(dispatch_dir) if apply else {
        "dispatch_total": len(dispatches),
        "counts": status_counts(dispatches),
        "unresolved": sum(status_counts(dispatches).get(k, 0) for k in ("pending", "dispatched", "running", "no_status")),
    }
    return {
        "dispatch_dir": str(dispatch_dir),
        "apply": apply,
        "actions": actions,
        "changed": len(actions),
        "ignored_non_dispatch": ignored,
        "after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "repair"], nargs="?", default="status")
    parser.add_argument("--dispatch-dir", default=str(Path.home() / "Knowledge" / "_raw" / "solar-harness" / ".dispatch"))
    parser.add_argument("--vault", default=str(Path.home() / "Knowledge"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    dispatch_dir = Path(args.dispatch_dir).expanduser()
    vault = Path(args.vault).expanduser()
    data = repair(dispatch_dir, vault, args.apply) if args.command == "repair" else summarize(dispatch_dir)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
