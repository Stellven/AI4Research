#!/usr/bin/env python3
"""Run a bounded sample through spans -> extracted JSON -> validation -> watermark."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


HARNESS = Path(__file__).resolve().parents[1]
LIB = HARNESS / "lib"
DEFAULT_VAULT = Path.home() / "Knowledge"


def run(cmd: list[str], *, allow_fail: bool = False) -> tuple[int, str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0 and not allow_fail:
        raise RuntimeError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\n{proc.stdout}")
    return proc.returncode, proc.stdout


DEFAULT_SOURCE_KINDS = [
    "raw_chatgpt",
    "raw_youtube",
    "raw_github",
    "raw_web",
    "raw_social",
    "raw_solar",
    "accepted_sprint",
    "obsidian_vault",
]


def load_sidecar_kind(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("source_kind") or "unknown")
    except Exception:
        return "invalid"


def collect_sidecars(vault: Path, limit: int) -> list[Path]:
    roots = [vault / "_vault_index" / "spans", vault / "_raw" / ".spans"]
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.spans.json")):
            out.append(path)
            if len(out) >= limit:
                return out
    return out


def collect_sidecars_by_source_kind(vault: Path, *, source_kinds: list[str], quota_per_class: int) -> dict[str, list[Path]]:
    roots = [vault / "_vault_index" / "spans", vault / "_raw" / ".spans"]
    buckets: dict[str, list[Path]] = {kind: [] for kind in source_kinds}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.spans.json")):
            kind = load_sidecar_kind(path)
            if kind not in buckets:
                continue
            if len(buckets[kind]) >= quota_per_class:
                continue
            buckets[kind].append(path)
        if all(len(paths) >= quota_per_class for paths in buckets.values()):
            break
    return buckets


def process_one(sidecar: Path, output_dir: Path, *, mock: bool) -> dict[str, Any]:
    source_kind = load_sidecar_kind(sidecar)
    extract_cmd = [
        "python3",
        str(LIB / "knowledge_extract_json.py"),
        "extract-sidecar",
        "--sidecar",
        str(sidecar),
        "--output-dir",
        str(output_dir),
        "--doc-type",
        "sample",
    ]
    if mock:
        extract_cmd.append("--mock")
    rc, out = run(extract_cmd, allow_fail=True)
    try:
        extract = json.loads(out)
    except Exception:
        return {"ok": False, "sidecar": str(sidecar), "stage": "extract", "rc": rc, "output": out[:1000]}
    if not extract.get("ok"):
        return {"ok": False, "source_kind": source_kind, "sidecar": str(sidecar), "stage": "extract", "extract": extract}
    validate_cmd = [
        "python3",
        str(LIB / "knowledge_extracted_validator.py"),
        "process",
        "--candidate",
        extract["candidate"],
        "--sidecar",
        str(sidecar),
        "--quarantine-dir",
        str(output_dir / "_quarantine"),
    ]
    v_rc, v_out = run(validate_cmd, allow_fail=True)
    validation = json.loads(v_out)
    return {
        "ok": bool(validation.get("ok")),
        "source_kind": source_kind,
        "sidecar": str(sidecar),
        "candidate": extract.get("candidate"),
        "markdown": extract.get("markdown"),
        "validation": validation,
        "validation_rc": v_rc,
    }


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Knowledge Ingest Dispatcher Sample Backfill Report",
        "",
        f"- total: {payload['total']}",
        f"- passed: {payload['passed']}",
        f"- failed: {payload['failed']}",
        f"- pass_rate: {payload['pass_rate']:.2%}",
        f"- repair_terminal_fail_rate: {payload['repair_terminal_fail_rate']:.2%}",
        f"- mode: {payload['mode']}",
        "",
        "## By Source Kind",
        "",
        "| Source Kind | Target | Total | Passed | Failed | Pass Rate | Enough Sample |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for kind, stats in sorted((payload.get("by_source_kind") or {}).items()):
        lines.append(
            f"| {kind} | {stats.get('target', 0)} | {stats.get('total', 0)} | "
            f"{stats.get('passed', 0)} | {stats.get('failed', 0)} | "
            f"{stats.get('pass_rate', 0.0):.2%} | {'yes' if stats.get('enough_sample') else 'no'} |"
        )
    lines.extend(
        [
            "",
        "## Results",
        "",
        "| Status | Sidecar | Candidate |",
        "|---|---|---|",
        ]
    )
    for item in payload["results"]:
        lines.append(f"| {'ok' if item.get('ok') else 'fail'} | `{item.get('sidecar')}` | `{item.get('candidate', 'N/A')}` |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--quota-per-class", type=int, default=0)
    parser.add_argument(
        "--source-kinds",
        default=",".join(DEFAULT_SOURCE_KINDS),
        help="Comma-separated source_kind list for quota sampling.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_VAULT / "_extracted" / "thunderomlx" / "sample-backfill"))
    parser.add_argument("--report", required=True)
    parser.add_argument("--live", action="store_true", help="Use real ThunderOMLX instead of mock contract.")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    source_kinds = [item.strip() for item in str(args.source_kinds).split(",") if item.strip()]
    if args.quota_per_class > 0:
        buckets = collect_sidecars_by_source_kind(vault, source_kinds=source_kinds, quota_per_class=args.quota_per_class)
        sidecars = [path for kind in source_kinds for path in buckets.get(kind, [])]
    else:
        buckets = {}
        sidecars = collect_sidecars(vault, args.limit)
    results = [process_one(sidecar, output_dir, mock=not args.live) for sidecar in sidecars]
    total = len(results)
    passed = sum(1 for item in results if item.get("ok"))
    failed = total - passed
    pass_rate = (passed / total) if total else 0.0
    by_source_kind: dict[str, dict[str, Any]] = {}
    result_kinds = source_kinds if args.quota_per_class > 0 else sorted({str(item.get("source_kind") or "unknown") for item in results})
    for kind in result_kinds:
        kind_results = [item for item in results if item.get("source_kind") == kind]
        kind_total = len(kind_results)
        kind_passed = sum(1 for item in kind_results if item.get("ok"))
        kind_failed = kind_total - kind_passed
        target = args.quota_per_class if args.quota_per_class > 0 else kind_total
        by_source_kind[kind] = {
            "target": target,
            "total": kind_total,
            "passed": kind_passed,
            "failed": kind_failed,
            "pass_rate": (kind_passed / kind_total) if kind_total else 0.0,
            "enough_sample": kind_total >= target,
        }
    enough_all = all(stats["enough_sample"] for stats in by_source_kind.values()) if by_source_kind else bool(total)
    pass_all = all(stats["pass_rate"] >= 0.90 for stats in by_source_kind.values() if stats["total"]) if by_source_kind else pass_rate >= 0.90
    payload = {
        "ok": enough_all and pass_all,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "repair_terminal_fail_rate": (failed / total) if total else 0.0,
        "mode": "live" if args.live else "mock-contract",
        "quota_per_class": args.quota_per_class,
        "source_kinds": source_kinds,
        "by_source_kind": by_source_kind,
        "results": results,
    }
    report_path = Path(args.report).expanduser()
    write_report(report_path, payload)
    print(json.dumps({**payload, "report": str(report_path)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
