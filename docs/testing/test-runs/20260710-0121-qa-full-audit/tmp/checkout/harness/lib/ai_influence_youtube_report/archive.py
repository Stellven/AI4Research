"""Atomic archive writer for validated report bundles."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACTS = {
    "report.md": "report_md",
    "report.html": "report_html",
    "plan.json": "plan_json",
    "evidence_map.json": "evidence_map",
}


def archive_writer_commit(run_record: dict[str, Any], report_bundle: dict[str, Any], validator_report: dict[str, Any]) -> dict[str, Any]:
    if validator_report.get("overall") != "PASS":
        raise ValueError("refuse to archive report bundle when validator overall is not PASS")
    archive_dir = Path(str(run_record["archive_dir"]))
    tmp_dir = archive_dir.with_name(f".{archive_dir.name}.tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    artifacts = []
    try:
        for filename, key in REQUIRED_ARTIFACTS.items():
            value = report_bundle[key]
            path = tmp_dir / filename
            if filename.endswith(".json"):
                path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                path.write_text(str(value), encoding="utf-8")
            artifacts.append({"type": filename.rsplit(".", 1)[-1], "path": str(archive_dir / filename)})
        manifest = {
            "schema_version": "archive_manifest.v1",
            "archive_dir": str(archive_dir),
            "artifacts": artifacts,
            "chatgpt_session_url": str(run_record.get("chatgpt_session_url") or ""),
            "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        (tmp_dir / "archive_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if archive_dir.exists():
            shutil.rmtree(archive_dir)
        tmp_dir.replace(archive_dir)
        return manifest
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        raise
