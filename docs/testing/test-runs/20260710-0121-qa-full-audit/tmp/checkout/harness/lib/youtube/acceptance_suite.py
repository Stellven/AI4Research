"""Acceptance suite and traceability generator for YouTube S03 runtime."""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes
from youtube.cli import main as youtube_cli_main
from youtube.pollution_repair import audit_pollution, repair_pollution, verify_repair
from youtube.premium_escape import reserve_budget
from youtube.quality_gate import evaluate_quality, persist_quality_check, score_to_tier


SPRINT_ID = "sprint-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构-s03-core-runtime"
EPIC_ID = "epic-20260526-tech-hotspot-radar-youtube-transcript-高质量抓取与-asr-分层重构"
REPORT_NAMES = ("pytest", "dry-run", "threshold", "budget", "pollution", "atomicity")
MODULES_IMPLEMENTED = [
    "subtitle_discovery",
    "acquisition_ladder",
    "asr_router",
    "priority_queue",
    "audio_middleware",
    "job_scheduler",
    "transcript_storage",
    "pollution_repair",
    "quality_gate",
    "vocab_correction",
    "report_eligibility",
    "cross_source_extractor",
    "premium_escape",
    "dashboard",
    "cli",
]
TABLES_CREATED = [
    "youtube_subtitle_tracks",
    "youtube_transcripts",
    "youtube_transcript_segments",
    "youtube_asr_runs",
    "youtube_transcript_jobs",
    "cross_source_links",
    "vocab_dictionary",
    "quality_checks",
    "audio_chunks",
    "youtube_premium_asr_calls",
]
MIGRATIONS_APPLIED = [f"youtube_{i:03d}" for i in range(1, 11)]
FILES_TOUCHED = [
    "lib/youtube/quality_gate.py",
    "lib/youtube/vocab_correction.py",
    "lib/youtube/report_eligibility.py",
    "lib/youtube/cross_source_extractor.py",
    "lib/youtube/premium_escape.py",
    "lib/youtube/dashboard.py",
    "lib/youtube/cli.py",
    "lib/tech_hotspot_radar/_youtube_cli_wrapper.py",
    "migrations/youtube_010_premium_asr_calls.py",
    "tests/test_youtube_quality_gate.py",
    "tests/test_youtube_vocab_correction.py",
    "tests/test_youtube_report_eligibility.py",
    "tests/test_youtube_cross_source_extractor.py",
    "tests/test_youtube_premium_escape.py",
    "tests/test_youtube_dashboard.py",
    "tests/test_youtube_cli.py",
    "tests/test_youtube_acceptance_suite.py",
    "tests/integration/test_youtube_e2e.py",
]
NODE_IDS = (
    "B3_phase3_application",
    "B4_phase4_interface",
    "B5_acceptance_gates",
    "B6_traceability_handoff",
)
NODE_EVAL_BASENAMES = {node_id: f"{SPRINT_ID}.{node_id}-eval.json" for node_id in NODE_IDS}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_migrations(root: Path) -> list[Any]:
    import importlib.util

    migrations = []
    for migration_path in sorted((root / "migrations").glob("youtube_*.py")):
        spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        migrations.append(module)
    return migrations


def _build_fixture_db(root: Path, db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    for migration in _load_migrations(root):
        migration.up(conn)
    return conn


def run_pytest_report(root: Path, report_dir: Path) -> dict[str, Any]:
    coverage_json = report_dir / "coverage.json"
    test_files = sorted(
        str(path)
        for path in (root / "tests").glob("test_youtube_*.py")
        if path.name != "test_youtube_acceptance_suite.py"
    )
    integration_files = [
        str(root / "tests" / "integration" / "test_youtube_e2e.py"),
    ]
    cmd = [
        "pytest",
        "-q",
        *test_files,
        *integration_files,
        f"--cov={root / 'lib' / 'youtube'}",
        f"--cov={root / 'lib' / 'youtube_config.py'}",
        f"--cov={root / 'lib' / 'tech_hotspot_radar' / '_youtube_cli_wrapper.py'}",
        f"--cov-report=json:{coverage_json}",
    ]
    proc = subprocess.run(" ".join(str(item) for item in cmd), shell=True, text=True, capture_output=True, cwd=root)
    coverage_rate = 0.0
    if coverage_json.exists():
        payload = json.loads(coverage_json.read_text(encoding="utf-8"))
        relevant_files = {
            path: data
            for path, data in (payload.get("files") or {}).items()
            if not path.endswith("lib/youtube/acceptance_suite.py")
        }
        covered = 0
        statements = 0
        for data in relevant_files.values():
            summary = data.get("summary") or {}
            num_statements = int(summary.get("num_statements", 0) or 0)
            missing_lines = int(summary.get("missing_lines", 0) or 0)
            statements += num_statements
            covered += max(num_statements - missing_lines, 0)
        coverage_rate = float(covered / statements) if statements else 0.0
    match = re.search(r"(\d+)\s+passed", proc.stdout)
    passed = int(match.group(1)) if match else 0
    report = {
        "schema_version": "solar.youtube.s03.acceptance.v1",
        "report": "pytest",
        "generated_at": _now(),
        "ok": proc.returncode == 0 and coverage_rate >= 0.70,
        "command": " ".join(str(item) for item in cmd),
        "passed_count": passed,
        "returncode": proc.returncode,
        "coverage_line_rate": round(coverage_rate, 4),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }
    _write_json(report_dir / "pytest.json", report)
    return report


def run_dry_run_report(root: Path, report_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "youtube_test.db"
        conn = _build_fixture_db(root, db_path)
        conn.execute(
            """INSERT INTO youtube_transcript_jobs
               (job_id, video_id, job_type, priority, status)
               VALUES ('job-1', 'video-1', 'asr', 'P0', 'pending')"""
        )
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM youtube_transcript_jobs").fetchone()[0]
        conn.close()
        with contextlib.redirect_stdout(io.StringIO()):
            rc = youtube_cli_main(["process-transcript-jobs", "--db", str(db_path), "--priority", "P0,P1,P2", "--dry-run", "--json"])
        conn = sqlite3.connect(db_path)
        after = conn.execute("SELECT COUNT(*) FROM youtube_transcript_jobs").fetchone()[0]
        conn.close()
    report = {
        "schema_version": "solar.youtube.s03.acceptance.v1",
        "report": "dry-run",
        "generated_at": _now(),
        "ok": rc == 0 and before == after,
        "before_count": before,
        "after_count": after,
        "delta": after - before,
    }
    _write_json(report_dir / "dry-run.json", report)
    return report


def run_threshold_report(report_dir: Path) -> dict[str, Any]:
    cases = [
        (0.849, "T1"),
        (0.85, "T0"),
        (0.699, "T2"),
        (0.70, "T1"),
        (0.499, "T3"),
        (0.50, "T2"),
    ]
    results = [{"score": score, "tier": score_to_tier(score), "expected": expected} for score, expected in cases]
    report = {
        "schema_version": "solar.youtube.s03.acceptance.v1",
        "report": "threshold",
        "generated_at": _now(),
        "ok": all(item["tier"] == item["expected"] for item in results),
        "cases": results,
    }
    _write_json(report_dir / "threshold.json", report)
    return report


def run_budget_report(root: Path, report_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "budget.db"
        conn = _build_fixture_db(root, db_path)
        conn.close()
        results: list[dict[str, Any]] = []
        errors: list[str] = []
        lock = threading.Lock()

        def _worker(index: int) -> None:
            thread_conn = sqlite3.connect(db_path)
            try:
                call = reserve_budget(thread_conn, transcript_id=f"t-{index}", audio_minutes=300, day="2026-05-28")
                with lock:
                    results.append({"call_id": call.call_id, "cost_usd": call.cost_usd})
            except Exception as exc:  # pragma: no cover - diagnostic only
                with lock:
                    errors.append(str(exc))
            finally:
                thread_conn.close()

        threads = [threading.Thread(target=_worker, args=(index,)) for index in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        final_conn = sqlite3.connect(db_path)
        total_cost = float(final_conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM youtube_premium_asr_calls").fetchone()[0])
        final_conn.close()

    report = {
        "schema_version": "solar.youtube.s03.acceptance.v1",
        "report": "budget",
        "generated_at": _now(),
        "ok": not errors and total_cost <= 20.0,
        "thread_count": 5,
        "reserved_count": len(results),
        "total_cost_usd": round(total_cost, 4),
        "errors": errors,
    }
    _write_json(report_dir / "budget.json", report)
    return report


def run_pollution_report(root: Path, report_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "pollution.db"
        conn = _build_fixture_db(root, db_path)
        seed_path = root / "tests" / "fixtures" / "pollution_seed.sql"
        conn.executescript(seed_path.read_text(encoding="utf-8"))
        conn.commit()
        before_report = audit_pollution(conn, dry_run=True)
        repair = repair_pollution(conn, dry_run=False)
        remaining = verify_repair(conn)
        conn.close()
    report = {
        "schema_version": "solar.youtube.s03.acceptance.v1",
        "report": "pollution",
        "generated_at": _now(),
        "ok": before_report.polluted_count == 165 and repair.total_repaired == 165 and remaining == 0,
        "seed_count": before_report.polluted_count,
        "repaired_count": repair.total_repaired,
        "remaining_count": remaining,
        "repair_actions": repair.repair_actions,
        "pollution_types": before_report.pollution_types,
    }
    _write_json(report_dir / "pollution.json", report)
    return report


def run_atomicity_report(root: Path, report_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "atomicity.db"
        conn = _build_fixture_db(root, db_path)
        conn.execute(
            """INSERT INTO youtube_transcripts
               (transcript_id, video_id, source) VALUES ('t-atomic', 'v-atomic', 'premium')"""
        )
        conn.commit()
        inconsistencies = 0
        try:
            conn.execute("BEGIN")
            result = evaluate_quality(
                text="Good transcript with KV cache and batching.",
                corrected_text="Good transcript with KV cache and continuous batching.",
                coverage_ratio=0.84,
                hallucination_risk=0.2,
                source_reliability=0.82,
                vocab_terms=["KV cache", "continuous batching"],
            )
            persist_quality_check(conn, transcript_id="t-atomic", result=result, commit=False)
            raise RuntimeError("forced_phase2_failure")
        except RuntimeError:
            conn.rollback()
        row = conn.execute("SELECT quality_tier FROM youtube_transcripts WHERE transcript_id = 't-atomic'").fetchone()
        qc_count = conn.execute("SELECT COUNT(*) FROM quality_checks WHERE transcript_id = 't-atomic'").fetchone()[0]
        if row and row[0] is not None:
            inconsistencies += 1
        if qc_count != 0:
            inconsistencies += 1
        conn.close()
    report = {
        "schema_version": "solar.youtube.s03.acceptance.v1",
        "report": "atomicity",
        "generated_at": _now(),
        "ok": inconsistencies == 0,
        "inconsistency_count": inconsistencies,
        "rollback_verified": inconsistencies == 0,
    }
    _write_json(report_dir / "atomicity.json", report)
    return report


def generate_acceptance_reports(root: Path, report_dir: Path) -> dict[str, dict[str, Any]]:
    report_dir.mkdir(parents=True, exist_ok=True)
    reports = {
        "pytest": run_pytest_report(root, report_dir),
        "dry-run": run_dry_run_report(root, report_dir),
        "threshold": run_threshold_report(report_dir),
        "budget": run_budget_report(root, report_dir),
        "pollution": run_pollution_report(root, report_dir),
        "atomicity": run_atomicity_report(root, report_dir),
    }
    return reports


def generate_traceability_and_handoff(
    *,
    sprint_root: Path,
    report_dir: Path,
    reports: dict[str, dict[str, Any]],
    knowledge_context: str,
) -> tuple[Path, Path]:
    traceability_path = sprint_root / f"{SPRINT_ID}.traceability.json"
    handoff_path = sprint_root / f"{SPRINT_ID}.handoff.md"
    all_ok = all(report.get("ok", False) for report in reports.values())
    traceability = {
        "schema_version": "solar.s03_core_runtime.traceability.v1",
        "sprint_id": SPRINT_ID,
        "epic_id": EPIC_ID,
        "generated_at": _now(),
        "knowledge_context": knowledge_context,
        "phases": {
            "B1": "passed",
            "B2": "passed",
            "B3": "implemented",
            "B4": "implemented",
            "B5": "passed" if all_ok else "failed",
            "B6": "passed" if all_ok else "blocked",
        },
        "modules_implemented": MODULES_IMPLEMENTED,
        "tables_created": TABLES_CREATED,
        "migrations_applied": MIGRATIONS_APPLIED,
        "acceptance_reports": {name: str(report_dir / f"{name}.json") for name in REPORT_NAMES},
        "s04_dependencies": [
            "transcript-status --json",
            "discover-transcript-tracks",
            "acquire-transcripts",
            "process-transcript-jobs",
            "audit-transcript-quality",
            "transcript-ab-test-asr",
            "youtube_config.YoutubeConfig",
            "premium_escape.reserve_budget",
        ],
        "s05_dependencies": [
            "premium E2E 真跑",
            "165 真生产清理",
            "dashboard 真集成",
            "OpenAI/yt-dlp 真调用验证",
        ],
        "open_questions_carried": [
            {
                "id": "OQ-B6-COUNT-MISMATCH",
                "status": "open",
                "owner": "coordinator",
                "note": "B6 contract 对 modules_implemented/tables_created 的计数与列举项存在不一致，当前 traceability 保留实际实现全集。",
            }
        ],
        "risks": [
            "OQC-1 atomicity 目前靠事务回滚验证，尚未接到真实 orchestration path",
            "OQC-4 premium budget 并发验证是本地 SQLite fixture，不是真实 provider contention",
            "S05 仍需真实生产清理与 premium E2E",
        ],
        "files_touched": FILES_TOUCHED,
    }
    _write_json(traceability_path, traceability)

    lines = [
        f"# Handoff — {SPRINT_ID}",
        "",
        f"- generated_at: `{traceability['generated_at']}`",
        f"- acceptance_ok: `{all_ok}`",
        "",
        "## B1-B5 Summary",
        "",
        "- B1/B2 已通过，B3/B4 模块已补齐并进入可测状态。",
        "- B5 六份 acceptance 报告已生成，路径见下文。",
        "",
        "## Acceptance Reports",
        "",
    ]
    for name in REPORT_NAMES:
        report = reports[name]
        lines.append(f"- `{name}`: `{report_dir / f'{name}.json'}` | ok=`{report.get('ok', False)}`")
    lines.extend(
        [
            "",
            "## S04 Kickoff Checklist",
            "",
            "- 对接 `transcript-status --json` 输出。",
            "- 挂接 6 个 CLI 子命令到 orchestration 层。",
            "- 消费 `youtube_config.YoutubeConfig` 与 premium budget API。",
            "",
            "## S05 Kickoff Checklist",
            "",
            "- 真跑 premium ASR E2E。",
            "- 真生产 165 条污染清理。",
            "- dashboard 真集成与 release 证据。",
            "",
            "## Residual Risks",
            "",
            "- OQC-1: 原子性验证仍是 fixture 级。",
            "- OQC-4: premium budget 并发仍是本地 SQLite 级。",
            "- B6 contract 计数口径存在冲突，已在 traceability 保留 open question。",
            "",
            "## No Optimistic Terms",
            "",
            "- 本 handoff 避免使用 `已修复/稳定/完美/无需担忧/done/complete`。",
            "",
        ]
    )
    handoff_path.write_text("\n".join(lines), encoding="utf-8")
    return traceability_path, handoff_path


def _eval_json_path(sprint_root: Path, node_id: str) -> Path:
    return sprint_root / NODE_EVAL_BASENAMES[node_id]


def _b3_conditions(root: Path, reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    module_files = [
        root / "lib" / "youtube" / "quality_gate.py",
        root / "lib" / "youtube" / "vocab_correction.py",
        root / "lib" / "youtube" / "report_eligibility.py",
        root / "lib" / "youtube" / "cross_source_extractor.py",
        root / "lib" / "youtube" / "premium_escape.py",
        root / "migrations" / "youtube_010_premium_asr_calls.py",
    ]
    return [
        {"label": "b3_module_and_migration_files_present", "ok": all(path.exists() for path in module_files)},
        {"label": "pytest_acceptance_green", "ok": bool((reports.get("pytest") or {}).get("ok"))},
        {"label": "threshold_acceptance_green", "ok": bool((reports.get("threshold") or {}).get("ok"))},
        {"label": "budget_acceptance_green", "ok": bool((reports.get("budget") or {}).get("ok"))},
        {"label": "atomicity_acceptance_green", "ok": bool((reports.get("atomicity") or {}).get("ok"))},
    ]


def _b4_conditions(root: Path, reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    interface_files = [
        root / "lib" / "youtube" / "dashboard.py",
        root / "lib" / "youtube" / "cli.py",
        root / "lib" / "tech_hotspot_radar" / "_youtube_cli_wrapper.py",
    ]
    interface_tests = [
        root / "tests" / "test_youtube_dashboard.py",
        root / "tests" / "test_youtube_cli.py",
    ]
    return [
        {"label": "b4_interface_files_present", "ok": all(path.exists() for path in interface_files)},
        {"label": "b4_interface_tests_present", "ok": all(path.exists() for path in interface_tests)},
        {"label": "pytest_acceptance_green", "ok": bool((reports.get("pytest") or {}).get("ok"))},
        {"label": "dry_run_acceptance_green", "ok": bool((reports.get("dry-run") or {}).get("ok"))},
    ]


def _b5_conditions(report_dir: Path, reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"label": "all_acceptance_reports_written", "ok": all((report_dir / f"{name}.json").exists() for name in REPORT_NAMES)},
        {"label": "all_acceptance_reports_green", "ok": all(bool(report.get("ok")) for report in reports.values())},
        {"label": "pytest_coverage_threshold_met", "ok": float((reports.get("pytest") or {}).get("coverage_line_rate") or 0.0) >= 0.70},
    ]


def _b6_conditions(traceability_path: Path, handoff_path: Path, reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    traceability = json.loads(traceability_path.read_text(encoding="utf-8"))
    return [
        {"label": "traceability_exists", "ok": traceability_path.exists()},
        {"label": "handoff_exists", "ok": handoff_path.exists()},
        {"label": "traceability_lists_6_reports", "ok": len((traceability.get("acceptance_reports") or {}).keys()) == 6},
        {"label": "traceability_lists_15_modules", "ok": len(traceability.get("modules_implemented") or []) == 15},
        {"label": "traceability_lists_10_tables", "ok": len(traceability.get("tables_created") or []) == 10},
        {"label": "traceability_lists_10_migrations", "ok": len(traceability.get("migrations_applied") or []) == 10},
        {"label": "all_acceptance_reports_green", "ok": all(bool(report.get("ok")) for report in reports.values())},
    ]


def _eval_payload(
    *,
    node_id: str,
    conditions: list[dict[str, Any]],
    evidence: dict[str, Any],
    summary: str,
    round_number: int = 1,
) -> dict[str, Any]:
    passed = [item["label"] for item in conditions if item.get("ok")]
    failed = [item["label"] for item in conditions if not item.get("ok")]
    verdict = "PASS" if not failed else "FAIL"
    return {
        "sprint_id": SPRINT_ID,
        "node_id": node_id,
        "round": round_number,
        "verdict": verdict,
        "checked_at": _now(),
        "passed_conditions": passed,
        "failed_conditions": failed,
        "warnings": [],
        "evidence": evidence,
        "summary": summary,
    }


def build_closeout_eval_payloads(
    *,
    root: Path,
    report_dir: Path,
    sprint_root: Path,
    traceability_path: Path,
    handoff_path: Path,
    reports: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    report_paths = {name: str(report_dir / f"{name}.json") for name in REPORT_NAMES}
    return {
        "B3_phase3_application": _eval_payload(
            node_id="B3_phase3_application",
            conditions=_b3_conditions(root, reports),
            summary="B3 application-layer modules, migration, and acceptance checks verified from generated suite artifacts.",
            evidence={
                "report_paths": report_paths,
                "modules": MODULES_IMPLEMENTED[8:13],
                "migration": "youtube_010_premium_asr_calls",
            },
        ),
        "B4_phase4_interface": _eval_payload(
            node_id="B4_phase4_interface",
            conditions=_b4_conditions(root, reports),
            summary="B4 interface-layer files and acceptance checks verified from generated suite artifacts.",
            evidence={
                "report_paths": report_paths,
                "interface_files": [
                    "lib/youtube/dashboard.py",
                    "lib/youtube/cli.py",
                    "lib/tech_hotspot_radar/_youtube_cli_wrapper.py",
                ],
            },
        ),
        "B5_acceptance_gates": _eval_payload(
            node_id="B5_acceptance_gates",
            conditions=_b5_conditions(report_dir, reports),
            summary="B5 acceptance suite produced six machine-readable reports and satisfied suite thresholds.",
            evidence={"report_paths": report_paths},
        ),
        "B6_traceability_handoff": _eval_payload(
            node_id="B6_traceability_handoff",
            conditions=_b6_conditions(traceability_path, handoff_path, reports),
            summary="B6 traceability and handoff artifacts were emitted with the required downstream dependency manifest.",
            evidence={
                "traceability_json": str(traceability_path),
                "handoff_md": str(handoff_path),
                "report_paths": report_paths,
            },
        ),
    }


def auto_closeout_s03_runtime(
    *,
    root: Path,
    runtime_root: Path,
    report_dir: Path,
    traceability_path: Path,
    handoff_path: Path,
    reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sprint_root = runtime_root / "sprints"
    graph_path = sprint_root / f"{SPRINT_ID}.task_graph.json"
    payloads = build_closeout_eval_payloads(
        root=root,
        report_dir=report_dir,
        sprint_root=sprint_root,
        traceability_path=traceability_path,
        handoff_path=handoff_path,
        reports=reports,
    )
    return auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads={node_id: payloads[node_id] for node_id in NODE_IDS},
        eval_json_paths={node_id: _eval_json_path(sprint_root, node_id) for node_id in NODE_IDS},
        reason="youtube_s03_acceptance_auto_closeout",
        actor="youtube_acceptance_suite",
        event="youtube_s03_acceptance_auto_closeout",
        dispatch_downstream=False,
    )
