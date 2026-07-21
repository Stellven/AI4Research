"""Benchmark run artifact writer.

S03 N4: write_run_artifacts(run_dir, result) writes run.json + report.md +
latest pointers (copies, not symlinks) + artifacts.manifest.json fallback (CBD5).
All writes atomic via tempfile + os.replace.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .schemas import BenchmarkRunResult, asdict_run_result

_LATEST_JSON = "latest-terminal-bench-2.json"
_LATEST_MD = "latest-terminal-bench-2.md"


def _reports_base() -> Path:
    """Return the reports base directory.

    Honors SOLAR_BENCH_REPORTS_DIR env var; defaults to
    ~/.solar/harness/reports/benchmark/.
    """
    env = os.environ.get("SOLAR_BENCH_REPORTS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".solar" / "harness" / "reports" / "benchmark"


def _atomic_write(target: Path, content: str | bytes) -> None:
    """Write content to target atomically using tempfile + os.replace."""
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if isinstance(content, str) else "wb"
    suffix = ".json" if target.suffix == ".json" else ".tmp"
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=suffix)
    try:
        with os.fdopen(fd, mode, encoding="utf-8" if mode == "w" else None) as fh:
            fh.write(content)
        os.replace(tmp_path, str(target))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def sha256_file(p: Path) -> str:
    """Return the SHA-256 hex digest of the file at p."""
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _render_report_md(result: BenchmarkRunResult) -> str:
    """Render a human-readable report.md from a BenchmarkRunResult."""
    lines: list[str] = []
    lines.append(f"# Benchmark Run Report")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Run ID | `{result.run_id}` |")
    lines.append(f"| Dataset | `{result.dataset}` |")
    lines.append(f"| Agent | `{result.agent}` |")
    lines.append(f"| Model | `{result.model}` |")
    lines.append(f"| Env | `{result.env}` |")
    lines.append(f"| Verdict | `{result.verdict}` |")
    lines.append(f"| Score | {result.score if result.score is not None else 'N/A'} |")
    lines.append(f"| Pass/Fail/Pending | {result.pass_count}/{result.fail_count}/{result.pending_count} |")
    lines.append(f"| Exit Code | {result.exit_code if result.exit_code is not None else 'N/A'} |")
    lines.append(f"| Started | {result.started_at} |")
    lines.append(f"| Completed | {result.completed_at or 'N/A'} |")
    lines.append(f"| Duration | {result.duration_sec:.1f}s" if result.duration_sec is not None else "| Duration | N/A |")
    lines.append("")

    if result.command:
        lines.append("## Command")
        lines.append("```")
        lines.append(" ".join(result.command))
        lines.append("```")
        lines.append("")

    if result.tasks_requested:
        lines.append("## Tasks Requested")
        for t in result.tasks_requested:
            lines.append(f"- `{t}`")
        lines.append("")

    if result.tasks_completed:
        lines.append("## Tasks Completed")
        for t in result.tasks_completed:
            lines.append(f"- `{t}`")
        lines.append("")

    if result.failure_modes:
        lines.append("## Failure Modes")
        for fm in result.failure_modes:
            lines.append(f"- `{fm}`")
        lines.append("")

    if result.limitations:
        lines.append("## Limitations")
        for lim in result.limitations:
            lines.append(f"- {lim}")
        lines.append("")

    if result.artifacts:
        lines.append("## Artifacts")
        lines.append("| File | SHA-256 |")
        lines.append("|------|---------|")
        for art in result.artifacts:
            lines.append(f"| `{art}` | (external) |")
        lines.append("")

    return "\n".join(lines)


def _build_manifest(run_dir: Path) -> list[dict[str, Any]]:
    """Build artifacts.manifest.json entries with sha256 hashes.

    Checks for stdout.log and stderr.log in run_dir and hashes them
    if present.
    """
    entries: list[dict[str, Any]] = []
    for name in ("stdout.log", "stderr.log"):
        p = run_dir / name
        if p.is_file():
            entries.append({
                "name": name,
                "sha256": sha256_file(p),
                "size": p.stat().st_size,
            })
    return entries


def write_run_artifacts(run_dir: Path, result: BenchmarkRunResult) -> dict[str, str]:
    """Write all run artifacts atomically.

    Writes:
      1. run.json — serialized BenchmarkRunResult
      2. report.md — human-readable report
      3. latest-terminal-bench-2.json — copy of run.json in reports base
      4. latest-terminal-bench-2.md — copy of report.md in reports base
      5. artifacts.manifest.json — sha256 hashes for stdout.log/stderr.log

    Returns dict mapping artifact name to its path string.
    """
    run_dir.mkdir(parents=True, exist_ok=True)

    run_json_path = run_dir / "run.json"
    report_md_path = run_dir / "report.md"
    manifest_path = run_dir / "artifacts.manifest.json"

    run_json_content = json.dumps(asdict_run_result(result), indent=2, ensure_ascii=False)
    report_md_content = _render_report_md(result)

    _atomic_write(run_json_path, run_json_content)
    _atomic_write(report_md_path, report_md_content)

    # Latest pointers (copies, not symlinks)
    base = _reports_base()
    base.mkdir(parents=True, exist_ok=True)
    latest_json_path = base / _LATEST_JSON
    latest_md_path = base / _LATEST_MD

    _atomic_write(latest_json_path, run_json_content)
    _atomic_write(latest_md_path, report_md_content)

    # artifacts.manifest.json with sha256 hashes
    manifest_entries = _build_manifest(run_dir)
    if manifest_entries:
        _atomic_write(manifest_path, json.dumps(manifest_entries, indent=2, ensure_ascii=False))

    written: dict[str, str] = {
        "run_json": str(run_json_path),
        "report_md": str(report_md_path),
        "latest_json": str(latest_json_path),
        "latest_md": str(latest_md_path),
    }
    if manifest_entries:
        written["manifest"] = str(manifest_path)

    return written
