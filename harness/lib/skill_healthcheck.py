#!/usr/bin/env python3
"""Daily Solar skill healthcheck.

This script is intentionally deterministic enough for automation: it checks the
night/power gate, scans Solar + solar-harness evidence, proposes skill
candidates, writes a Markdown report, and appends a JSONL summary.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS = HOME / ".solar" / "harness"
SOLAR = HOME / "Solar"
CODEX_SKILLS = HOME / ".codex" / "skills"
AGENTS_SKILLS = HOME / ".agents" / "skills"
CODEX_MEMORY = HOME / ".codex" / "memories"
REMOTE = "solar@example-host"
REMOTE_HARNESS = "~/.solar/harness"
MEMRL_DB = HOME / ".solar" / "solar.db"
MEMRL_FEEDBACK_JSONL = HARNESS / "logs" / "skill-healthcheck-memrl-feedback.jsonl"
EVOLUTION_ENGINE = HARNESS / "lib" / "evolution_engine.py"

PATTERNS: dict[str, dict[str, Any]] = {
    "prompt_residue": {
        "terms": ["prompt residue", "prompt_residue", "残留", "quarantine", "C-u"],
        "skill": "solar-prompt-residue-quarantine",
        "priority": "P0",
        "trigger": "pane 输入框有旧 prompt、C-u 清不掉、不能按 Enter",
        "output": "PLANNER-INBOX 记录 + pane/lease 安全状态 + 是否需要 respawn",
    },
    "remote_sync": {
        "terms": ["mac-mini", "Mac mini", "remote_sync", "sync-required", "状态分叉", "remote divergence"],
        "skill": "solar-mac-mini-sync-auditor",
        "priority": "P0",
        "trigger": "本机和 Mac mini harness 代码/工件/状态不一致",
        "output": "差异表 + sync manifest + md5/test 清单",
    },
    "contract_patrol": {
        "terms": ["contract-patrol", "合约", "status corrupt", "corrupt status", "异常终态"],
        "skill": "solar-contract-patrol",
        "priority": "P1",
        "trigger": "合约库非终态、异常 tuple、queue/lease/status 互相矛盾",
        "output": "合约表 + blocker_type + 低风险修复记录",
    },
    "artifact_export": {
        "terms": ["export-harness-artifacts", "extracted_knowledge", "knowledge", "导出", "commit"],
        "skill": "solar-artifact-export",
        "priority": "P1",
        "trigger": "passed sprint 需要导出到 Solar/harness 并抽取知识",
        "output": "导出数量 + commit SHA + 知识文件 + 跳过状态统计",
    },
    "state_machine": {
        "terms": ["state machine", "state-mapper", "handoff_to", "phase", "状态机"],
        "skill": "solar-state-machine-repair",
        "priority": "P1",
        "trigger": "status/phase/handoff_to 不一致或 coordinator 不能扩展",
        "output": "状态 tuple 诊断 + transition 建议 + 回归测试",
    },
    "exec_pool": {
        "terms": ["maximum number of unified exec", "exec 会话", "僵尸进程", "process"],
        "skill": "codex-exec-session-hygiene",
        "priority": "P2",
        "trigger": "Codex automation/patrol 产生过多 shell 会话或长跑进程",
        "output": "进程/会话清单 + 收敛策略",
    },
}


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def local_now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def run(cmd: list[str], timeout: int = 20, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout)


def in_night_window(now: dt.datetime) -> bool:
    return 0 <= now.hour < 7


def power_ok() -> tuple[bool, str]:
    try:
        cp = run(["pmset", "-g", "batt"], timeout=5)
    except Exception as exc:
        return False, f"pmset_error:{exc}"
    text = (cp.stdout + cp.stderr).strip()
    ok = ("AC Power" in text) or ("charging" in text.lower())
    return ok, text.splitlines()[0] if text else "no pmset output"


def read_tail(path: Path, max_bytes: int = 512_000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        return f.read().decode("utf-8", errors="replace")


def safe_jsonl_tail(path: Path, limit: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = read_tail(path, 1_000_000)
    for line in text.splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def count_pattern_hits(texts: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    haystack = "\n".join(texts)
    for key, cfg in PATTERNS.items():
        total = 0
        for term in cfg["terms"]:
            total += len(re.findall(re.escape(term), haystack, flags=re.I))
        if total:
            counts[key] = total
    return counts


def scan_statuses() -> dict[str, Any]:
    nonterminal = {
        "drafting", "drafting_held", "queued", "active", "planning", "approved",
        "reviewing", "ready_for_review", "failed_review", "needs_human_review",
        "blocked", "superseded", "interrupted", "eval_pass", "failed",
    }
    rows: list[dict[str, Any]] = []
    corrupt: list[str] = []
    for path in sorted((HARNESS / "sprints").glob("*.status.json")):
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            corrupt.append(f"{path.name}:{exc}")
            continue
        status = data.get("status")
        phase = data.get("phase")
        handoff_to = data.get("handoff_to")
        abnormal = (status == "approved" and phase in {"completed", "done", "eval_passed"}) or (
            status == "passed" and handoff_to in {"builder", "builder_main", "evaluator", "planner"}
        )
        if status in nonterminal or abnormal:
            rows.append({
                "sprint": path.name.removesuffix(".status.json"),
                "status": status,
                "phase": phase,
                "handoff_to": handoff_to,
                "updated_at": data.get("updated_at") or data.get("created_at"),
                "abnormal": abnormal,
            })
    rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    return {"nonterminal": rows[:50], "corrupt": corrupt}


def scan_skills() -> dict[str, Any]:
    roots = [CODEX_SKILLS, AGENTS_SKILLS, SOLAR / "skills", HARNESS / "skills"]
    names: dict[str, list[str]] = {}
    for root in roots:
        vals: list[str] = []
        if root.exists():
            for skill_md in root.rglob("SKILL.md"):
                try:
                    vals.append(str(skill_md.parent.relative_to(root)))
                except Exception:
                    vals.append(str(skill_md.parent))
        names[str(root)] = sorted(vals)[:300]
    all_names = {Path(x).name for vals in names.values() for x in vals}
    return {"roots": names, "all_names": sorted(all_names)}


def build_candidates(patterns: Counter[str], existing_names: set[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key, count in patterns.most_common():
        cfg = PATTERNS[key]
        name = cfg["skill"]
        exists = name in existing_names
        candidates.append({
            "priority": cfg["priority"],
            "name": name,
            "hit_count": count,
            "exists": exists,
            "trigger": cfg["trigger"],
            "inputs": "Solar/Solar-Harness logs, sprint artifacts, queue/lease/status, optional Mac mini probe",
            "outputs": cfg["output"],
            "validation": "run skill-healthcheck plus targeted smoke/pytest for touched module",
            "risk_boundary": "do not execute pane residue, do not create sprint, do not overwrite remote without sync manifest",
            "target_dir": f"{CODEX_SKILLS}/{name}",
        })
    return candidates


def remote_probe(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"checked": False, "ok": False, "reason": "disabled"}
    script = (
        f"cd {REMOTE_HARNESS} || exit 10; "
        "./solar-harness.sh coord-status 2>/dev/null; "
        "printf '\\nREMOTE_STATUS_COUNT '; ls sprints/*.status.json 2>/dev/null | wc -l; "
        "printf 'REMOTE_LEASE_COUNT '; find run/pane-leases -type f 2>/dev/null | wc -l"
    )
    try:
        cp = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", REMOTE, script], timeout=20)
    except Exception as exc:
        return {"checked": True, "ok": False, "reason": str(exc)}
    return {
        "checked": True,
        "ok": cp.returncode == 0,
        "returncode": cp.returncode,
        "stdout_tail": cp.stdout[-2000:],
        "stderr_tail": cp.stderr[-1000:],
    }


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    widths = [len(h) for h in headers]
    srows = [[str(c) if c is not None else "N/A" for c in row] for row in rows]
    for row in srows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"
    out = [top, "│ " + " │ ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " │", mid]
    for row in srows:
        out.append("│ " + " │ ".join(row[i].ljust(widths[i]) for i in range(len(headers))) + " │")
    out.append(bot)
    return "\n".join(out)


def _sqlite_tables(db: Path) -> set[str]:
    if not db.exists():
        return set()
    try:
        import sqlite3
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        return {str(r[0]) for r in rows if r and r[0]}
    except Exception:
        return set()


def _sqlite_count(db: Path, table: str) -> int | None:
    try:
        import sqlite3
        conn = sqlite3.connect(str(db))
        cur = conn.execute(f"SELECT count(1) FROM {table}")
        val = cur.fetchone()
        conn.close()
        return int(val[0]) if val and val[0] is not None else 0
    except Exception:
        return None


def _memrl_probe(update_memrl: bool, ts: str, gate_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    required_tables = ["memrl_feedback_logs", "memrl_retrieval_logs", "memrl_utility_store", "sys_skill_bank"]
    tables = _sqlite_tables(MEMRL_DB)
    missing = [t for t in required_tables if t not in tables]
    counts = {t: _sqlite_count(MEMRL_DB, t) for t in required_tables}
    fused_q: dict[str, Any] = {"available": False}
    if "memrl_utility_store" in tables:
        try:
            import sqlite3
            conn = sqlite3.connect(str(MEMRL_DB))
            row = conn.execute(
                "SELECT avg(q_value), max(q_value), count(1) FROM memrl_utility_store"
            ).fetchone()
            conn.close()
            if row:
                fused_q = {
                    "available": True,
                    "avg_q": float(row[0]) if row[0] is not None else None,
                    "max_q": float(row[1]) if row[1] is not None else None,
                    "samples": int(row[2]) if row[2] is not None else None,
                }
        except Exception:
            fused_q = {"available": False}

    impl_path = HOME / ".claude" / "core" / "memrl"
    memrl_status = {
        "ready": bool(MEMRL_DB.exists()) and not missing,
        "db": str(MEMRL_DB),
        "implementation_path": str(impl_path),
        "implementation_exists": impl_path.exists(),
        "required_tables_present": [t for t in required_tables if t in tables],
        "missing_tables": missing,
        "counts": counts,
        "fused_q": fused_q,
    }

    metrics = gate_payload.get("metrics") if isinstance(gate_payload.get("metrics"), dict) else {}
    if isinstance(metrics, dict):
        metrics = {**metrics, "memrl_ready": bool(memrl_status.get("ready"))}

    feedback_obj = {
        "ts": ts,
        "source": "solar-skill-healthcheck",
        "task_key": "solar.skill_healthcheck",
        "reward": float(gate_payload.get("reward") or 0),
        "verdict": str(gate_payload.get("verdict") or "unknown"),
        "metrics": metrics,
        "promotion_allowed": bool(gate_payload.get("promotion_allowed")),
    }
    memrl_feedback = {"jsonl": str(MEMRL_FEEDBACK_JSONL), "sqlite_updated": False, "sqlite_reason": "disabled"}

    if update_memrl:
        MEMRL_FEEDBACK_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with MEMRL_FEEDBACK_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(feedback_obj, ensure_ascii=False) + "\n")
        memrl_feedback = {"jsonl": str(MEMRL_FEEDBACK_JSONL), "sqlite_updated": False, "sqlite_reason": "unknown"}
        try:
            import sqlite3
            conn = sqlite3.connect(str(MEMRL_DB))
            conn.execute(
                "INSERT INTO memrl_feedback_logs (intent_hash, experience_id, success, user_feedback, new_q_value, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "solar.skill_healthcheck",
                    f"healthcheck:{ts}",
                    1,
                    json.dumps(feedback_obj, ensure_ascii=False),
                    float(gate_payload.get("reward") or 0),
                    ts,
                ),
            )
            conn.commit()
            conn.close()
            memrl_feedback = {"jsonl": str(MEMRL_FEEDBACK_JSONL), "sqlite_updated": True, "sqlite_reason": "inserted_intent_experience_feedback_q"}
        except Exception as exc:
            memrl_feedback = {"jsonl": str(MEMRL_FEEDBACK_JSONL), "sqlite_updated": False, "sqlite_reason": f"sqlite_error:{exc}"}
    return memrl_status, memrl_feedback


def _skillrl_probe() -> dict[str, Any]:
    knowledge_doc = HOME / "Knowledge" / "entities" / "skillrl.md"
    return {
        "ready": knowledge_doc.exists(),
        "knowledge_doc": str(knowledge_doc),
        "knowledge_doc_exists": knowledge_doc.exists(),
        "harness_native_runtime": False,
        "gap": "SkillRL 当前主要是知识/方法论资产，未发现独立 harness runtime；应通过 eval pack + promotion gate 接入。",
    }


def _evolution_engine_probe() -> dict[str, Any]:
    if not EVOLUTION_ENGINE.exists():
        return {"ok": False, "reason": "missing", "path": str(EVOLUTION_ENGINE)}
    try:
        cp = run(["python3", str(EVOLUTION_ENGINE), "status", "--json"], timeout=25)
        out = {}
        if cp.stdout.strip():
            out = json.loads(cp.stdout)
        scorecards = out.get("scorecards") if isinstance(out.get("scorecards"), list) else []
        experiments = out.get("experiments") if isinstance(out.get("experiments"), list) else []
        status = {
            "ok": bool(out.get("ok")),
            "total_scorecards": len(scorecards),
            "active": sum(1 for x in scorecards if isinstance(x, dict) and x.get("status") == "active"),
            "pending": sum(1 for x in scorecards if isinstance(x, dict) and x.get("status") == "pending"),
            "degraded": sum(1 for x in scorecards if isinstance(x, dict) and x.get("status") == "degraded"),
            "experiments": len(experiments),
            "recent_experiments": [
                {"id": x.get("id"), "capability": x.get("capability"), "verdict": x.get("verdict"), "updated_at": x.get("updated_at")}
                for x in experiments[:5]
                if isinstance(x, dict)
            ],
        }
        return {
            "ok": cp.returncode == 0 and bool(out.get("ok")),
            "path": str(EVOLUTION_ENGINE),
            "returncode": cp.returncode,
            "status": status,
            "stderr_tail": (cp.stderr or "")[-800:],
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "path": str(EVOLUTION_ENGINE)}


def write_outputs(result: dict[str, Any]) -> None:
    reports = HARNESS / "reports"
    logs = HARNESS / "logs"
    reports.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    ts_slug = result["ts"].replace(":", "").replace("-", "")
    report_path = reports / f"skill-healthcheck-{ts_slug}.md"

    memrl_ready = bool((result.get("memrl_status") or {}).get("ready"))
    skillrl_ready = bool((result.get("skillrl_status") or {}).get("ready"))
    evolution_engine_ok = bool((result.get("evolution_engine") or {}).get("ok"))
    evolution_gate = result.get("evolution_gate") if isinstance(result.get("evolution_gate"), dict) else {}
    evolution_verdict = str(evolution_gate.get("verdict") or "N/A")

    candidate_rows = [
        [c["priority"], c["name"], c["hit_count"], "yes" if c["exists"] else "no", c["trigger"][:42]]
        for c in result["skill_candidates"][:12]
    ] or [["N/A", "N/A", 0, "N/A", "无明显候选"]]
    status_rows = [
        [x["sprint"][:46], x.get("status"), x.get("phase"), x.get("handoff_to"), "abnormal" if x.get("abnormal") else "legacy"]
        for x in result["statuses"]["nonterminal"][:10]
    ] or [["N/A", "ok", "N/A", "N/A", "无非终态"]]
    gap_rows = [
        ["prompt/lease", "warn" if result["patterns"].get("prompt_residue") else "ok", "pane 残留需要 skill 化"],
        ["remote-sync", "warn" if result["patterns"].get("remote_sync") else "ok", "Mac mini 同步差异入口"],
        ["artifact-export", "warn" if result["patterns"].get("artifact_export") else "ok", "passed 工件导出/知识化"],
        ["exec-pool", "warn" if result["patterns"].get("exec_pool") else "ok", "Codex exec 会话收敛"],
    ]

    memrl_status = result.get("memrl_status") if isinstance(result.get("memrl_status"), dict) else {}
    memrl_tables = len(memrl_status.get("required_tables_present") or [])
    memrl_missing = len(memrl_status.get("missing_tables") or [])
    skillrl_status = result.get("skillrl_status") if isinstance(result.get("skillrl_status"), dict) else {}
    evolution_status = (result.get("evolution_engine") or {}).get("status") if isinstance((result.get("evolution_engine") or {}).get("status"), dict) else {}
    evolution_scorecards = evolution_status.get("total_scorecards")

    memrl_row = ["MemRL", "ok" if memrl_ready else "error", f"tables={memrl_tables} missing={memrl_missing if memrl_missing else 'none'}"]
    skillrl_row = ["SkillRL", "ok" if skillrl_ready else "warn", f"doc={'yes' if skillrl_status.get('knowledge_doc_exists') else 'no'} runtime={'yes' if skillrl_status.get('harness_native_runtime') else 'no'}"]
    evolution_row = ["Evolution", "ok" if evolution_engine_ok else "error", f"scorecards={evolution_scorecards if evolution_scorecards is not None else 'N/A'}"]
    gate_row = ["Gate", evolution_verdict, f"reward={evolution_gate.get('reward','N/A')} blockers={','.join(evolution_gate.get('promotion_blockers') or []) or 'none'}"]

    report = "\n".join([
        "# Solar Skill Healthcheck",
        "",
        f"- ts: `{result['ts']}`",
        f"- window_ok: `{result['window_ok']}`",
        f"- power_ok: `{result['power_ok']}` ({result['power_detail']})",
        f"- mac_mini_checked: `{result['remote']['checked']}` ok=`{result['remote'].get('ok')}`",
        f"- memrl_ready: `{memrl_ready}` skillrl_ready=`{skillrl_ready}` evolution_engine_ok=`{evolution_engine_ok}`",
        "",
        "## 总览",
        "```text",
        markdown_table(["项", "值"], [
            ["files_scanned", result["files_scanned"]],
            ["pattern_keys", ", ".join(result["patterns"].keys()) or "none"],
            ["candidate_count", len(result["skill_candidates"])],
            ["nonterminal_statuses", len(result["statuses"]["nonterminal"])],
            ["evolution_verdict", evolution_verdict],
        ]),
        "```",
        "",
        "## MemRL / SkillRL / Evolution",
        "```text",
        markdown_table(["模块", "状态", "证据"], [memrl_row, skillrl_row, evolution_row, gate_row]),
        "```",
        "",
        "## Skill 候选",
        "```text",
        markdown_table(["优先级", "skill", "命中", "已存在", "触发场景"], candidate_rows),
        "```",
        "",
        "## 合约状态样本",
        "```text",
        markdown_table(["sprint", "status", "phase", "handoff_to", "类型"], status_rows),
        "```",
        "",
        "## 自动化缺口",
        "```text",
        markdown_table(["缺口", "状态", "建议"], gap_rows),
        "```",
        "",
        "## 建议下一步",
        "- P0: 对未存在的 P0 候选生成/更新 skill，并把自动化改为调用稳定脚本。",
        "- P1: 把 recurring blocker 做成 `solar-harness skills healthcheck --json` 可验证输出。",
        "- P2: 定期清理旧失败/中断合约或归档到 accepted/failed 知识层。",
        "",
        f"当前问题：{result['current_problem']}",
        f"下一步：{result['next_step']}",
        "",
    ])
    report_path.write_text(report, encoding="utf-8")
    result["report_path"] = str(report_path)
    log_record = {
        "ts": result["ts"],
        "window_ok": result["window_ok"],
        "power_ok": result["power_ok"],
        "files_scanned": result["files_scanned"],
        "top_patterns": result["patterns"],
        "skill_candidates": result["skill_candidates"],
        "existing_skill_improvements": result["existing_skill_improvements"],
        "automation_gaps": result["automation_gaps"],
        "bugs_or_risks": result["bugs_or_risks"],
        "memrl_status": result.get("memrl_status"),
        "skillrl_status": result.get("skillrl_status"),
        "evolution_engine": result.get("evolution_engine"),
        "evolution_gate": result.get("evolution_gate"),
        "memrl_feedback": result.get("memrl_feedback"),
        "report_path": str(report_path),
        "mac_mini_checked": result["remote"]["checked"],
        "residual_risk": result["residual_risk"],
    }
    with (logs / "skill-healthcheck.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_record, ensure_ascii=False) + "\n")


def run_healthcheck(args: argparse.Namespace) -> dict[str, Any]:
    ts = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    local = local_now()
    window_ok = in_night_window(local) or args.force or args.allow_daytime
    p_ok, power_detail = power_ok()
    p_ok = p_ok or args.force or args.allow_battery
    result: dict[str, Any] = {
        "ok": True,
        "ts": ts,
        "window_ok": bool(window_ok),
        "power_ok": bool(p_ok),
        "power_detail": power_detail,
        "quiet_exit": False,
    }
    if not window_ok or not p_ok:
        result.update({
            "quiet_exit": True,
            "decision": "DONT_NOTIFY",
            "reason": "outside allowed time window" if not window_ok else "not on AC power",
            "files_scanned": 0,
            "patterns": {},
            "skill_candidates": [],
            "statuses": {"nonterminal": [], "corrupt": []},
            "existing_skill_improvements": [],
            "automation_gaps": [],
            "bugs_or_risks": [],
            "remote": {"checked": False, "ok": False, "reason": "preflight skipped"},
            "current_problem": "前置条件未满足，未执行深度扫描",
            "next_step": "等待 00:00-07:00 且接入电源后自动运行",
            "residual_risk": "未扫描",
        })
        return result

    sources = [
        read_tail(HARNESS / "logs" / "contract-patrol-bugfixes.jsonl", 2_000_000),
        read_tail(HARNESS / "state" / "mac-mini-sync-required.jsonl", 1_000_000),
        read_tail(HARNESS / "PLANNER-INBOX.md", 1_000_000),
        read_tail(HARNESS / ".coordinator.log", 1_000_000),
        read_tail(CODEX_MEMORY / "MEMORY.md", 1_000_000),
    ]
    patterns = count_pattern_hits(sources)
    statuses = scan_statuses()
    skills = scan_skills()
    candidates = build_candidates(patterns, set(skills["all_names"]))
    remote = remote_probe(not args.no_remote)
    files_scanned = sum(1 for text in sources if text) + len(skills["all_names"]) + len(statuses["nonterminal"])

    existing_improvements = []
    for c in candidates:
        if c["exists"]:
            existing_improvements.append({
                "skill": c["name"],
                "suggestion": "补充 scripts/ 验证入口、统一 JSON schema、加入 Mac mini/queue/lease 边界条件",
            })
    automation_gaps = [
        {"gap": "pane prompt residue should be quarantined by watchdog, not manual Enter", "severity": "P0" if patterns.get("prompt_residue") else "P2"},
        {"gap": "Mac mini sync should consume sync-required manifest and close status", "severity": "P0" if patterns.get("remote_sync") else "P1"},
        {"gap": "skill healthcheck should be command-backed, not prompt-only automation", "severity": "P0"},
    ]
    bugs_or_risks = []
    if statuses["corrupt"]:
        bugs_or_risks.append({"severity": "P0", "risk": "corrupt status files", "evidence": statuses["corrupt"][:5]})
    if not remote.get("ok"):
        bugs_or_risks.append({"severity": "P1", "risk": "Mac mini probe failed", "evidence": remote.get("reason") or remote.get("stderr_tail")})
    if patterns.get("prompt_residue"):
        bugs_or_risks.append({"severity": "P1", "risk": "prompt residue recurrence", "evidence": patterns["prompt_residue"]})

    result.update({
        "decision": "NOTIFY" if any(c["priority"] in {"P0", "P1"} and not c["exists"] for c in candidates) or bugs_or_risks else "DONT_NOTIFY",
        "files_scanned": files_scanned,
        "patterns": dict(patterns),
        "skill_candidates": candidates,
        "statuses": statuses,
        "existing_skill_improvements": existing_improvements,
        "automation_gaps": automation_gaps,
        "bugs_or_risks": bugs_or_risks,
        "remote": remote,
        "current_problem": "存在可固化 skill 候选或运行可靠性风险" if candidates or bugs_or_risks else "未发现明显新增风险",
        "next_step": "优先固化 P0 skill 候选并把自动化切到稳定命令入口" if candidates else "继续每日巡检",
        "residual_risk": "统计来自日志/工件启发式，不能替代专项代码审计",
    })

    evolution_engine = _evolution_engine_probe()
    skillrl_status = _skillrl_probe()

    p0_missing_count = sum(1 for c in candidates if c.get("priority") == "P0" and not c.get("exists"))
    pattern_hit_total = sum(int(v) for v in patterns.values()) if patterns else 0
    remote_ok = remote.get("ok") if isinstance(remote, dict) and remote.get("checked") else None

    gate_metrics: dict[str, Any] = {
        "candidate_count": len(candidates),
        "p0_missing_count": p0_missing_count,
        "bug_or_risk_count": len(bugs_or_risks),
        "pattern_hit_total": pattern_hit_total,
        "memrl_ready": False,
        "skillrl_ready": bool(skillrl_status.get("ready")),
        "evolution_engine_ok": bool(evolution_engine.get("ok")),
        "remote_ok": remote_ok,
    }
    evolution_gate: dict[str, Any] = {
        "verdict": "stable",
        "reward": 1,
        "promotion_allowed": False,
        "promotion_blockers": ["external_eval_pack_not_passed"],
        "metrics": gate_metrics,
        "previous_metrics": gate_metrics,
        "improvements": [],
        "regressions": [],
        "policy": "candidate skills can be proposed by healthcheck, but promotion requires MemRL-ready state plus an external eval/regression pack pass.",
    }

    update_memrl = bool(getattr(args, "update_memrl", False))
    memrl_status, memrl_feedback = _memrl_probe(update_memrl, ts, evolution_gate)
    gate_metrics["memrl_ready"] = bool(memrl_status.get("ready"))
    evolution_gate["metrics"] = gate_metrics
    evolution_gate["previous_metrics"] = gate_metrics

    result["memrl_status"] = memrl_status
    result["memrl_feedback"] = memrl_feedback
    result["skillrl_status"] = skillrl_status
    result["evolution_engine"] = evolution_engine
    result["evolution_gate"] = evolution_gate

    write_outputs(result)
    return result


def print_human(result: dict[str, Any]) -> None:
    if result.get("quiet_exit"):
        print(f"DONT_NOTIFY: {result['reason']}")
        return
    rows = [[c["priority"], c["name"], c["hit_count"], "yes" if c["exists"] else "no"] for c in result["skill_candidates"][:8]]
    if not rows:
        rows = [["N/A", "N/A", 0, "N/A"]]
    print("Solar Skill Healthcheck")
    print("```text")
    print(markdown_table(["优先级", "候选 skill", "命中", "已存在"], rows))
    print("```")
    print(f"报告: {result.get('report_path', 'N/A')}")
    print(f"当前问题：{result['current_problem']}")
    print(f"下一步：{result['next_step']}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="solar-harness skills healthcheck")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force", action="store_true", help="bypass time and power gates")
    parser.add_argument("--allow-daytime", action="store_true")
    parser.add_argument("--allow-battery", action="store_true")
    parser.add_argument("--no-remote", action="store_true")
    parser.add_argument("--update-memrl", action="store_true")
    args = parser.parse_args()
    result = run_healthcheck(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
