#!/usr/bin/env python3
"""graph_node_dispatcher.py — dispatch queued DAG nodes to builder panes.

The graph scheduler decides which nodes are ready. This dispatcher consumes
`task_queue.py` items with intent `graph_node|node_id=...`, creates explicit
per-node dispatch files, binds/verifies pane leases, and sends the node task to
the assigned pane.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HOME = Path.home()


def _harness_dir() -> Path:
    raw = os.environ.get("HARNESS_DIR")
    return Path(raw) if raw else Path(__file__).resolve().parents[1]


HARNESS_DIR = _harness_dir()
if str(HARNESS_DIR / "lib") not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR / "lib"))
SPRINTS_DIR = HARNESS_DIR / "sprints"
MULTI_TASK_RUN_DIR = HARNESS_DIR / "run" / "multi-task"
SESSION = os.environ.get("SOLAR_HARNESS_SESSION", "solar-harness")
NO_DISPATCH_FLAG = HARNESS_DIR / "run" / "no-dispatch.flag"
DISPATCH_LEDGER = HARNESS_DIR / "run" / "dispatch-ledger.jsonl"
# Was 900s (15 min): a pane marked needs_respawn was unavailable for 15 min, stalling
# the node stage. 90s lets a settled pane be re-dispatched quickly so runs self-recover.
PANE_RECOVER_COOLDOWN_SEC = int(os.environ.get("SOLAR_GRAPH_PANE_RECOVER_COOLDOWN_SEC", "90"))
PANE_TUI_BUSY_RE = re.compile(
    r"Compacting conversation|压缩上下文|Reticulating|Scurrying|Roosting|"
    r"Mustering|Herding|Baking|Cogitating|Churning|Ruminating|Thinking|"
    r"Whirring|Smooshing|Unhandled node type|Do you want to proceed\?|Would you like to proceed\?|"
    r"Do you want to make this edit|allow all edits during this session|"
    r"Enter to confirm|Esc to cancel|Bash command|"
    r"[·✳✶✽✢]\s+[A-Za-z][A-Za-z-]*…|✳|✶|✽|✢",
    re.I,
)
PANE_TUI_UNAVAILABLE_RE = re.compile(
    r"You(?:'|’)ve hit your limit|"
    r"rate[- ]limit options|"
    r"rate[- ]limit error|"
    r"resets\s+\d|/rate-limit-options|Upgrade your plan|"
    r"API Error:\s*400|Invalid API parameter|error\"\s*:\s*\{",
    re.I,
)
PANE_QUOTA_EXHAUSTED_RE = re.compile(
    r"You(?:'|’)ve hit (?:your|the org(?:anization)?(?:'s)?) .*limit|"
    r"monthly usage limit|quota exhausted|quota:exhausted|"
    r"RESOURCE_EXHAUSTED|429",
    re.I,
)
PANE_RATE_LIMIT_FALLBACK_SEC = int(os.environ.get("SOLAR_PANE_RATE_LIMIT_FALLBACK_SEC", "900"))
OPERATOR_CONTRACT_CLOSEOUT_COOLDOWN_SEC = int(os.environ.get("SOLAR_GRAPH_OPERATOR_CONTRACT_CLOSEOUT_COOLDOWN_SEC", "900"))
GRAPH_NODE_REPAIR_MAX_ATTEMPTS = int(os.environ.get("SOLAR_GRAPH_NODE_REPAIR_MAX_ATTEMPTS", "1"))
# Bounded eval-dispatch failure escalation. A node whose evaluator dispatch keeps failing for a
# capacity reason (e.g. no evaluator pane in the pool) would otherwise sit in `reviewing` forever
# (Run D: 246x no_available_evaluator with no terminal state). After this many consecutive
# capacity-class failures, the node is escalated to a durable needs_human_review with a reason +
# next_action instead of retrying silently. 0 = unlimited (legacy infinite-retry behavior).
GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES = int(os.environ.get("SOLAR_GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES", "8"))
# Eval-dispatch skip reasons that mean "the node cannot be evaluated right now for a capacity reason"
# (as opposed to a transient within-batch lease collision). Only these accrue toward escalation.
_EVAL_STUCK_REASONS = frozenset({
    "no_available_evaluator",
    "insufficient_evaluator_capacity",
    "insufficient_selected_evaluators",
    "multi_evaluator_quorum_not_implemented",
})
# Fix F: faster recovery from an eval input-submit jam (wall #5). Caps the EVAL
# lease + the re-dispatch gate so a stuck eval re-dispatches before the full 900s
# TTL. Safety is the existing busy-check: a still-working eval pane reads busy and
# is never re-dispatched, so this only accelerates the genuinely-stuck case.
EVAL_RECOVER_SEC = int(os.environ.get("SOLAR_GRAPH_EVAL_RECOVER_SEC", "600"))


def _current_harness_session() -> str:
    session = str(os.environ.get("SOLAR_HARNESS_SESSION") or SESSION or "solar-harness").strip()
    return session or "solar-harness"


def _pane_session_name(pane: str) -> str:
    return str(pane or "").split(":", 1)[0].strip()


def _allowed_pane_sessions() -> set[str]:
    session = _current_harness_session()
    allowed = {session, f"{session}-lab", f"{session}-multi-task"}
    for env_name in (
        "SOLAR_HARNESS_LAB_SESSION",
        "SOLAR_HARNESS_BG_SESSION",
        "SOLAR_HARNESS_MULTI_TASK_SESSION",
    ):
        value = str(os.environ.get(env_name) or "").strip()
        if value:
            allowed.add(value)
    for value in str(os.environ.get("SOLAR_HARNESS_ALLOWED_EXTRA_SESSIONS") or "").split(","):
        value = value.strip()
        if value:
            allowed.add(value)
    if session == "solar-harness":
        allowed.update({"solar-harness-lab", "solar-harness-multi-task"})
    return allowed


def _pane_in_harness_session_scope(pane: str) -> bool:
    return _pane_session_name(pane) in _allowed_pane_sessions()


def _pane_in_helper_session(pane: str) -> bool:
    pane_session = _pane_session_name(pane)
    return bool(pane_session and pane_session != _current_harness_session() and pane_session in _allowed_pane_sessions())


def _pane_in_lab_session(pane: str) -> bool:
    session = _current_harness_session()
    names = {f"{session}-lab"}
    for env_name in ("SOLAR_HARNESS_LAB_SESSION", "SOLAR_HARNESS_BG_SESSION"):
        value = str(os.environ.get(env_name) or "").strip()
        if value:
            names.add(value)
    if session == "solar-harness":
        names.add("solar-harness-lab")
    return _pane_session_name(pane) in names


def _pane_in_multi_task_session(pane: str) -> bool:
    session = _current_harness_session()
    names = {f"{session}-multi-task"}
    value = str(os.environ.get("SOLAR_HARNESS_MULTI_TASK_SESSION") or "").strip()
    if value:
        names.add(value)
    if session == "solar-harness":
        names.add("solar-harness-multi-task")
    return _pane_session_name(pane) in names


def _effective_graph_max_parallel(default: int = 8) -> int:
    try:
        if str(HARNESS_DIR / "lib") not in sys.path:
            sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import concurrency_policy  # type: ignore

        return int(concurrency_policy.effective_max_parallel(default, scope="graph"))
    except Exception:
        return int(default)


def _prune_expired_operator_blocks() -> None:
    try:
        if str(HARNESS_DIR / "lib") not in sys.path:
            sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import operator_flow_control as ofc  # type: ignore

        ofc.prune_expired_operator_config_blocks()
    except Exception:
        pass
PANE_RATE_LIMIT_OPTIONS_MODAL_RE = re.compile(
    r"What do you want to do\?[\s\S]{0,260}(?:/rate-limit-options|Upgrade your plan|Stop and wait for limit to reset)[\s\S]{0,120}Esc to cancel",
    re.I,
)
PANE_DISPATCH_FAILED_IDLE_RE = re.compile(
    r"API Error:\s*Request timed out|Check your internet connection and proxy settings",
    re.I,
)
PANE_PROCESSING_RE = re.compile(
    r"esc to interrupt|• Working|Working \(|"
    r"Crafting|Cogitating|Orchestrating|Coalescing|Wandering|Sock-hopping|"
    r"Puzzling|Cooking|Baked|Thinking|Considering|Newspapering|"
    r"Reticulating|Scurrying|Roosting|Mustering|Herding|Ruminating|"
    r"Churning|Baking|Effecting|Swooping|Whirring|Smooshing|Catapulting|Actualizing|"
    r"Unravelling|Compacting conversation|Implementing|Writing|Running tests|"
    r"[·✳✶✽✢]\s+[A-Za-z][A-Za-z-]*…|"
    r"⎿|✻|✶|✳|✽|⏺",
    re.I,
)
PANE_LIVE_SPINNER_RE = re.compile(r"[·✳✶✽✢]\s+[A-Za-z][A-Za-z-]*…|✳|✶|✽|✢", re.I)
PANE_COMPLETED_MARKER_RE = re.compile(
    r"✻\s+(?:Churned|Cogitated|Baked|Brewed|Cooked|Sautéed|Thought|Worked|Crunched)\s+for",
    re.I,
)
PANE_QUEUED_PROMPT_RE = re.compile(r"Press up to edit queued messages", re.I)
PANE_PLAN_MODE_RE = re.compile(r"(?:⏸\s*)?plan mode on(?:\s*\(shift\+tab to cycle\))?", re.I)
PANE_SURVEY_PROMPT_RE = re.compile(
    r"How is Claude doing this session\?|1:\s*Bad\s+2:\s*Fine\s+3:\s*Good\s+0:\s*Dismiss",
    re.I,
)
PANE_APPROVAL_PROMPT_RE = re.compile(
    r"Do you want to make this edit|"
    r"allow all edits during this session|"
    r"Press up to edit queued messages",
    re.I,
)
PANE_CONFIRMATION_PROMPT_RE = re.compile(
    r"Unhandled node type|Do you want to proceed\?|Do you want to make this edit|"
    r"allow all edits during this session|"
    r"Enter to confirm|Esc to cancel|Bash command",
    re.I,
)
PANE_PROMPT_RESIDUE_RE = re.compile(r"^\s*❯(?![\s\u00a0]+Try\s+\")[\s\u00a0]+[^\s\u00a0─]", re.M)
RECOVERABLE_DISPATCH_PROMPT_REASONS = {
    "proceed_confirmation_prompt",
    "edit_confirmation_prompt",
    "queued_prompt_residue",
    "plan_mode_blocked",
    "survey_prompt_blocked",
}
RECOVERABLE_PANE_BLOCKER_FRAGMENTS = {
    "proceed_confirmation_prompt",
    "edit_confirmation_prompt",
    "queued_prompt_residue",
    "plan_mode_blocked",
    "unsubmitted_prompt_residue",
    "submit_ack_idle_no_worker_activity",
    "accept_edits_footer",
    "submit_ack_idle",
    "dispatch prompt not dismissed",
    "late_settle_blocked",
}

try:
    from pane_overlay_state import pane_overlay_detail, pane_overlay_blocked, prompt_match_is_stale, tail_has_idle_prompt_footer
except Exception:  # pragma: no cover - keep dispatcher usable in partial installs
    pane_overlay_detail = None  # type: ignore
    pane_overlay_blocked = None  # type: ignore
    prompt_match_is_stale = None  # type: ignore
    tail_has_idle_prompt_footer = None  # type: ignore
STATE_READ_PREFLIGHT = """<!-- SOLAR_STATE_READ_PREFLIGHT -->
## 必须先读状态 (防写入 hook 卡死)

在任何 Write/Edit/handoff/eval/status 更新之前，必须先用 Claude/Codex 的 **Read 工具**读取：

`~/.solar/STATE.md`

不要用 `cat` 替代这一步；本地 `state-read-enforcer.sh` hook 只认 Read 工具标记。

如果 Write/Edit hook 仍阻断，立刻 Read 上面的 STATE 文件后重试原写入一次，不要停在“已读”等待。

---
"""

DEFINITION_OF_DONE_POLICY = """## DEFINITION OF DONE · 强制完成约束

任务没有完成，除非同时满足以下 7 条。交付不是输出代码；交付是用证据证明功能真的工作。

1. 真实调用链接入 — 所有新增/修改功能已接入真实调用链，不允许只写孤立模块。
2. 禁止硬编码 — 不允许硬编码业务数据、测试数据、路径、token、feature flag。
3. 测试必须运行 — 必须运行相关测试；如果不能运行，必须明确说明原因。
4. 执行证据齐全 — 必须给出实际执行过的命令和结果摘要，不接受“应该可以工作”。
5. Diff 自审 — 必须检查 diff，列出每个改动文件的目的。
6. 禁用乐观词 — 如果存在未完成项，禁止使用 “done / complete / implemented”。
7. 结构化收尾 — 最终回答必须分为：已完成 · 已验证 · 未验证 · 风险 · 后续待办。

硬性判定：没有证据，不许报喜；存在未验证项时只能标 `未验证` 或 `风险`，不能标完成。

---
"""

sys.path.insert(0, str(HARNESS_DIR / "lib"))
from graph_scheduler import (  # noqa: E402
    load_graph,
    save_graph,
    enqueue_ready,
    set_node_status,
    node_status,
    mark_node_result,
    parent_ready_check,
)
from pane_lease import acquire as acquire_lease, release as release_lease, read_lease, list_leases  # noqa: E402
from task_queue import enqueue  # noqa: E402
try:
    from model_registry import load_registry as _load_model_registry, normalize as _normalize_model  # noqa: E402
except Exception:  # pragma: no cover - partial fixtures can omit registry helper
    _load_model_registry = None  # type: ignore
    _normalize_model = None  # type: ignore
try:
    from runtime_bridge import record_legacy_event  # noqa: E402
    from runtime_status import transition_status  # noqa: E402
except Exception:  # pragma: no cover - fail-open in partial test fixtures
    record_legacy_event = None  # type: ignore
    transition_status = None  # type: ignore
try:
    from capability_effects import scan_effect  # noqa: E402
except Exception:  # pragma: no cover - fail-open in partial test fixtures
    scan_effect = None  # type: ignore
try:
    from multi_task_status import resolve_actorhost_status  # noqa: E402
except Exception:  # pragma: no cover - actorhost observability is additive
    resolve_actorhost_status = None  # type: ignore
try:
    from architecture_guard import dispatch_policy_block  # noqa: E402
except Exception:  # pragma: no cover - architecture guard is additive
    dispatch_policy_block = None  # type: ignore
try:
    from research import storage as research_storage  # noqa: E402
    from research.cli import render_human_search_handoff  # noqa: E402
    from research.evaluator import evaluate_artifacts as evaluate_research_artifacts  # noqa: E402
except Exception:  # pragma: no cover - DeepResearch is additive
    research_storage = None  # type: ignore
    render_human_search_handoff = None  # type: ignore
    evaluate_research_artifacts = None  # type: ignore
try:
    from pane_role_pool import ensure_clean_for_dispatch as ensure_clean_for_dispatch_boundary  # noqa: E402
    from pane_role_pool import infer_role as infer_pane_dispatch_role  # noqa: E402
except Exception:  # pragma: no cover - hygiene helpers are additive
    ensure_clean_for_dispatch_boundary = None  # type: ignore
    infer_pane_dispatch_role = None  # type: ignore


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _dispatch_role_for_pane(pane: str, title: str | None = None) -> str:
    title = _pane_title(pane) if title is None else str(title or "")
    # Match only the leading ROLE LABEL (before the first "|"), not the whole title. A builder pane
    # carries a status suffix like "builder | 状态:working/ready_for_planner:..." — matching the full
    # title would see "planner" inside "ready_for_planner" and mis-classify the builder as a planner
    # (then builder-role DAG nodes strand with role_candidates_seen=false).
    role_label = title.split("|", 1)[0]
    lowered = role_label.lower()
    if "planner" in lowered or "规划者" in role_label:
        return "planner"
    if "evaluator" in lowered or "审判官" in role_label:
        return "evaluator"
    if "pm" in lowered or "产品经理" in role_label:
        return "pm"
    if "builder" in lowered or "建设者" in role_label:
        return "builder"
    if infer_pane_dispatch_role is not None:
        try:
            return str(infer_pane_dispatch_role(pane, title) or "builder")
        except Exception:
            pass
    return "builder"


def _role_file_for_pane(pane: str) -> Path:
    return HARNESS_DIR / "run" / "pane-codex" / f"{_dispatch_role_for_pane(pane)}.md"


def _pane_runtime() -> str:
    runtime = os.environ.get("SOLAR_PANE_RUNTIME", "claude").strip().lower()
    return runtime if runtime in {"claude", "codex"} else "claude"


def _clear_dispatch_boundary(pane: str, sid: str, dispatch_id: str) -> tuple[bool, str]:
    if not _pane_in_harness_session_scope(pane):
        return True, "non_harness_pane"
    if ensure_clean_for_dispatch_boundary is None:
        return True, "helper_unavailable"
    role = _dispatch_role_for_pane(pane)
    try:
        result = ensure_clean_for_dispatch_boundary(pane, role)
    except Exception as exc:
        return False, f"clear_gate_exception:{exc}"
    if result.get("ok"):
        return True, str(result.get("reason") or "retry_ok")
    reason = str(result.get("reason") or "clear_gate_failed")
    marker = _mark_pane_recover_retryable if _recoverable_pane_blocker(reason) else _mark_pane_recover_cooldown
    marker(pane, f"clear_gate_failed:{reason}", sid=sid, dispatch_id=dispatch_id)
    return False, reason


def _recoverable_pane_blocker(reason: str) -> bool:
    normalized = str(reason or "").lower()
    if not normalized:
        return False
    hard_fragments = (
        "rate_limit",
        "quota",
        "api_error",
        "provider_health_unavailable",
        "multi_task_shell_not_direct_worker",
        "worker_runtime_not_running",
        "codex_runtime_not_running",
    )
    if any(fragment in normalized for fragment in hard_fragments):
        return False
    return any(fragment in normalized for fragment in RECOVERABLE_PANE_BLOCKER_FRAGMENTS)


HUMAN_SEARCH_CAPABILITIES = {
    "source.search",
    "research.source.search",
    "research.source.web",
    "research.source.academic",
    "research.web.search",
    "research.academic.search",
    "research.contradiction.search",
}

EVALUATION_REVIEW_MODES = {"single", "staged", "dual", "committee"}
DEEPRESEARCH_GATE_CAPABILITY_RE = re.compile(
    r"^research\.(?:"
    r"factuality|citation|claim(?:[_\.]|$)|evidence(?:[_\.]|$)|"
    r"report(?:[_\.](?:ast|finalize|quality|review)|_ast)|"
    r"survey(?:[_\.](?:chief_editor|finalize|quality|review))"
    r")",
    re.I,
)
DEEPRESEARCH_GATE_CAPABILITIES = {
    "citation.verify",
    "factuality.evaluate",
}
DEEPRESEARCH_GATE_ARTIFACT_RE = re.compile(
    r"research_eval|report_ast|final\.md|final_report|evidence\.jsonl|claims\.jsonl",
    re.I,
)


def _node_capabilities(node: dict[str, Any]) -> set[str]:
    caps: set[str] = set()
    for key in ("required_capabilities", "capabilities"):
        raw = node.get(key, [])
        if isinstance(raw, str):
            caps.add(raw)
        elif isinstance(raw, list):
            caps.update(str(item) for item in raw if str(item))
    return caps


def _node_requires_human_search(node: dict[str, Any]) -> bool:
    if node.get("human_search") is False or node.get("human_loop_search") is False:
        return False
    if _node_capabilities(node) & HUMAN_SEARCH_CAPABILITIES:
        return True
    haystack = " ".join(str(node.get(k, "")) for k in ("id", "goal", "description")).lower()
    return bool(re.search(r"external[_ -]?search|web[_ -]?search|academic[_ -]?search|source[_ -]?search|contradiction[_ -]?search", haystack))


def _node_requires_deepresearch_quality_gate(node: dict[str, Any]) -> bool:
    explicit = node.get("research_quality_gate_required")
    if explicit is False:
        return False
    if explicit is True:
        return True
    caps = _node_capabilities(node)
    if caps & DEEPRESEARCH_GATE_CAPABILITIES:
        return True
    if any(DEEPRESEARCH_GATE_CAPABILITY_RE.match(cap) for cap in caps):
        return True
    artifact_values: list[str] = []
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    artifact_values.extend(str(value) for value in artifacts.values())
    for key in (
        "research_eval",
        "research_eval_json",
        "eval_artifacts_json",
        "report_ast",
        "final_report",
        "final_md",
    ):
        if node.get(key):
            artifact_values.append(str(node.get(key)))
    raw_scope = node.get("write_scope", [])
    if isinstance(raw_scope, str):
        artifact_values.append(raw_scope)
    elif isinstance(raw_scope, list):
        artifact_values.extend(str(item) for item in raw_scope)
    artifact_text = " ".join(artifact_values).lower()
    return bool(DEEPRESEARCH_GATE_ARTIFACT_RE.search(artifact_text))


def _deepresearch_quality_gate_eval_instruction(node: dict[str, Any], eval_json: str | Path) -> str:
    if _node_requires_deepresearch_quality_gate(node):
        return f"""- 本 node 明确涉及 DeepResearch artifacts / research evidence ledger / claim ledger / citation verification / research report compiler，必须先运行 deterministic artifact gate：
  ```bash
  solar-harness research eval-artifacts --eval-json "<path-to-research_eval.json>" --json
  ```
  并把返回 JSON 原样写入 `{eval_json}` 的 `research_quality_gate` 字段。没有 `research_quality_gate.ok=true` 不允许 PASS。"""
    return """- DeepResearch deterministic artifact gate is **not required** for this node. Do not run `solar-harness research eval-artifacts`, and do not fail this node only because `research_eval.json`, `report_ast.json`, bibliography, source/evidence/claim counts, or citation-accuracy artifacts are absent.
  Local audit reports, packaging-readiness reports, documentation synthesis, and generic `report.compile` outputs are judged by this node's acceptance criteria, proof obligations, session log, write scope, and handoff evidence unless `research_quality_gate_required=true` or explicit `research.*` artifacts/capabilities are present. Leave `research_quality_gate` empty or mark it `{"required": false}`."""


def _graph_terminally_closed(sid: str) -> bool:
    """True once the graph has reached terminal closure. Used to keep the
    `.finalized` marker sticky so a stale non-PASS coverage verdict (e.g. the
    in-progress/partial requirement-trace view) cannot strip finalization and
    reopen an already-closed sprint (Defect C)."""
    closure_path = SPRINTS_DIR / f"{sid}.closure.json"
    try:
        closure = json.loads(closure_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(closure, dict):
        return False
    return str(closure.get("status") or "").strip().lower() == "closed" or bool(closure.get("all_nodes_passed"))


def _refresh_requirement_coverage_artifacts(sid: str, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "skipped": "dry_run"}
    try:
        from requirement_coverage import evaluate_sid
    except Exception as exc:
        return {"ok": False, "reason": f"requirement_coverage_import_failed:{type(exc).__name__}", "error": str(exc)}
    try:
        bundle = evaluate_sid(
            sid,
            sprints_dir=SPRINTS_DIR,
            requested_verdict="pass",
            write=True,
            require_pass=False,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "reason": "requirement_coverage_inputs_missing", "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "reason": f"requirement_coverage_refresh_failed:{type(exc).__name__}", "error": str(exc)}

    verdict = str((bundle.get("acceptance_verdict") or {}).get("verdict") or "N/A")
    finalized_path = SPRINTS_DIR / f"{sid}.finalized"
    cleared_finalized = False
    # Keep finalization sticky once the graph has terminally closed: a non-PASS
    # coverage verdict (e.g. the in-progress/partial requirement-trace view) must
    # not strip the terminal marker and reopen a closed sprint (Defect C). The
    # anti-stale unlink still fires for a sprint that has NOT terminally closed.
    if verdict != "PASS" and finalized_path.exists() and not _graph_terminally_closed(sid):
        try:
            finalized_path.unlink()
            cleared_finalized = True
        except OSError:
            pass
    return {
        "ok": True,
        "verdict": verdict,
        "coverage_summary": (bundle.get("coverage_report") or {}).get("summary", {}),
        "cleared_finalized": cleared_finalized,
    }


def _evaluation_selector(node: dict[str, Any]) -> dict[str, Any]:
    selector = node.get("operator_selector")
    return selector if isinstance(selector, dict) else {}


def _node_task_type(node: dict[str, Any]) -> str:
    selector = _evaluation_selector(node)
    return str(node.get("task_type") or selector.get("task_type") or "").strip().upper()


def _node_constraints(node: dict[str, Any]) -> dict[str, Any]:
    selector = _evaluation_selector(node)
    constraints = node.get("constraints") or selector.get("constraints") or {}
    return constraints if isinstance(constraints, dict) else {}


def _node_write_scope(node: dict[str, Any]) -> list[str]:
    raw = node.get("write_scope") or []
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def _node_required_capability_names(node: dict[str, Any]) -> set[str]:
    raw = node.get("required_capabilities") or _evaluation_selector(node).get("required_capabilities") or {}
    if isinstance(raw, dict):
        return {str(name).strip().lower() for name in raw.keys() if str(name).strip()}
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    if isinstance(raw, str) and raw.strip():
        return {raw.strip().lower()}
    return set()


def _risk_tier_for_node(node: dict[str, Any]) -> str:
    task_type = _node_task_type(node)
    constraints = _node_constraints(node)
    explicit = str(
        constraints.get("risk_tier")
        or node.get("risk_tier")
        or ""
    ).strip().lower()
    if explicit in {"low", "medium", "high", "critical"}:
        return explicit
    capability_names = _node_required_capability_names(node)
    write_scope = _node_write_scope(node)
    if task_type in {"SECURITY_SENSITIVE"}:
        return "critical"
    if task_type in {"ARCH_DESIGN", "ACADEMIC_CRITIQUE", "ROOT_CAUSE_DEBUG", "SOFT_HW_OPT"}:
        return "high"
    if capability_names & {"security.review", "security", "benchmark.analysis", "benchmark", "root-cause.debug"}:
        return "high"
    if len(write_scope) > 1 or bool(write_scope):
        return "medium"
    return "low"


def _evaluation_mode_required_evaluators(mode: str) -> int:
    return {
        "single": 1,
        "staged": 1,
        "dual": 2,
        "committee": 3,
    }.get(mode, 1)


def _default_evaluation_mode(node: dict[str, Any]) -> str:
    task_type = _node_task_type(node)
    risk_tier = _risk_tier_for_node(node)
    verifier_required = bool(node.get("verifier_required")) or bool(_evaluation_selector(node).get("verifier_required"))
    if task_type == "SECURITY_SENSITIVE" or risk_tier == "critical":
        return "committee"
    if task_type in {"ARCH_DESIGN", "ACADEMIC_CRITIQUE"}:
        return "dual"
    if verifier_required or task_type in {"CODE_IMPL", "MULTI_FILE_REFACTOR", "TEST_GEN", "TEST_RUN", "DOC_REPORT", "ROOT_CAUSE_DEBUG", "SOFT_HW_OPT"}:
        return "staged"
    return "single"


def _evaluation_evidence_requirements(node: dict[str, Any], mode: str) -> list[str]:
    task_type = _node_task_type(node)
    requirements = ["handoff_md", "session_log"]
    if _node_write_scope(node):
        requirements.append("scope_compliance")
    if task_type in {"CODE_IMPL", "MULTI_FILE_REFACTOR", "TEST_GEN", "TEST_RUN", "ROOT_CAUSE_DEBUG", "SOFT_HW_OPT"}:
        requirements.extend(["patch_diff", "test_report"])
    if task_type in {"ARCH_DESIGN", "RESEARCH_SYNTHESIS", "ACADEMIC_CRITIQUE", "DOC_REPORT"}:
        requirements.append("design_or_report_artifact")
    if mode in {"dual", "committee"}:
        requirements.append("cross_evaluator_consistency")
    deduped: list[str] = []
    for item in requirements:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _normalized_evaluation_plan(plan: dict[str, Any], node: dict[str, Any], source: str) -> dict[str, Any]:
    raw_mode = str(plan.get("review_mode") or "").strip().lower()
    mode = raw_mode if raw_mode in EVALUATION_REVIEW_MODES else _default_evaluation_mode(node)
    raw_required = plan.get("required_evaluators")
    try:
        required_evaluators = max(1, int(raw_required)) if raw_required is not None else _evaluation_mode_required_evaluators(mode)
    except Exception:
        required_evaluators = _evaluation_mode_required_evaluators(mode)
    evaluator_classes = plan.get("evaluator_classes")
    if isinstance(evaluator_classes, str):
        evaluator_classes_list = [evaluator_classes] if evaluator_classes else []
    elif isinstance(evaluator_classes, list):
        evaluator_classes_list = [str(item) for item in evaluator_classes if str(item)]
    else:
        evaluator_classes_list = []
    if not evaluator_classes_list:
        evaluator_classes_list = ["Verifier"]
    independence_policy = plan.get("independence_policy")
    if not isinstance(independence_policy, dict):
        independence_policy = {}
    independence_policy = {
        "writer_same_operator": str(independence_policy.get("writer_same_operator") or "denied"),
        "writer_same_provider": str(
            independence_policy.get("writer_same_provider")
            or ("avoid" if mode in {"dual", "committee"} else "allowed")
        ),
    }
    evidence_requirements = plan.get("evidence_requirements")
    if isinstance(evidence_requirements, str):
        evidence_requirements_list = [evidence_requirements] if evidence_requirements else []
    elif isinstance(evidence_requirements, list):
        evidence_requirements_list = [str(item) for item in evidence_requirements if str(item)]
    else:
        evidence_requirements_list = []
    if not evidence_requirements_list:
        evidence_requirements_list = _evaluation_evidence_requirements(node, mode)
    escalation_on_fail = plan.get("escalation_on_fail")
    if isinstance(escalation_on_fail, str):
        escalation = [escalation_on_fail] if escalation_on_fail else []
    elif isinstance(escalation_on_fail, list):
        escalation = [str(item) for item in escalation_on_fail if str(item)]
    else:
        escalation = []
    if not escalation:
        escalation = ["HumanReview"] if mode == "committee" else ["Verifier"]
    parallelizable = bool(plan.get("parallelizable", mode in {"dual", "committee"}))
    cross_provider_required = bool(plan.get("cross_provider_required", mode in {"dual", "committee"}))
    return {
        "planning_source": source,
        "task_type": _node_task_type(node) or "N/A",
        "risk_tier": _risk_tier_for_node(node),
        "review_mode": mode,
        "required_evaluators": required_evaluators,
        "evaluator_classes": evaluator_classes_list,
        "parallelizable": parallelizable,
        "cross_provider_required": cross_provider_required,
        "independence_policy": independence_policy,
        "evidence_requirements": evidence_requirements_list,
        "escalation_on_fail": escalation,
    }


def _plan_node_evaluation(graph: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    explicit = node.get("evaluation_plan")
    if isinstance(explicit, dict) and explicit:
        return _normalized_evaluation_plan(explicit, node, "explicit")
    return _normalized_evaluation_plan({}, node, "derived")


def _evaluation_capacity_snapshot(plan: dict[str, Any], evaluators: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in evaluators if not item.get("busy")]
    available_panes = [str(item.get("pane") or "") for item in available if str(item.get("pane") or "")]
    required = max(1, int(plan.get("required_evaluators") or 1))
    mode = str(plan.get("review_mode") or "single")
    selected = available[:required]
    selected_panes = [str(item.get("pane") or "") for item in selected if str(item.get("pane") or "")]
    capacity_satisfied = len(selected) >= required
    quorum_dispatch_supported = True
    dispatchable_now = capacity_satisfied and quorum_dispatch_supported
    return {
        "available_evaluators": len(available),
        "available_panes": available_panes,
        "required_evaluators": required,
        "selected_panes": selected_panes,
        "capacity_satisfied": capacity_satisfied,
        "quorum_dispatch_supported": quorum_dispatch_supported,
        "review_mode": mode,
        "dispatchable_now": dispatchable_now,
    }


def _runtime_fallback_evaluation_plan(plan: dict[str, Any], capacity: dict[str, Any]) -> dict[str, Any]:
    mode = str(plan.get("review_mode") or "single")
    required = max(1, int(plan.get("required_evaluators") or 1))
    available = int(capacity.get("available_evaluators") or 0)
    if available < 1:
        return plan
    if mode not in {"dual", "committee"}:
        return plan
    if capacity.get("dispatchable_now", False):
        return plan

    fallback = dict(plan)
    fallback["requested_review_mode"] = mode
    fallback["requested_required_evaluators"] = required
    fallback["fallback_applied"] = True
    fallback["fallback_reason"] = (
        "multi_evaluator_quorum_not_implemented"
        if capacity.get("capacity_satisfied", False)
        else "insufficient_evaluator_capacity"
    )
    fallback["followup_review_required"] = True
    fallback["review_mode"] = "staged"
    fallback["required_evaluators"] = 1
    fallback["parallelizable"] = False
    fallback["cross_provider_required"] = False
    evidence = list(fallback.get("evidence_requirements", []) or [])
    for item in ["runtime_fallback_notice", "followup_independent_review_pending"]:
        if item not in evidence:
            evidence.append(item)
    fallback["evidence_requirements"] = evidence
    escalation = list(fallback.get("escalation_on_fail", []) or [])
    for item in ["Verifier", "HumanReview"]:
        if item not in escalation:
            escalation.append(item)
    fallback["escalation_on_fail"] = escalation
    return fallback


def _evaluation_plan_block(plan: dict[str, Any]) -> str:
    lines = [
        f"- Review Mode: `{plan.get('review_mode', 'single')}`",
        f"- Required Evaluators: `{plan.get('required_evaluators', 1)}`",
        f"- Risk Tier: `{plan.get('risk_tier', 'low')}`",
        f"- Evaluator Classes: {', '.join(f'`{item}`' for item in plan.get('evaluator_classes', []) or ['Verifier'])}",
        f"- Cross Provider Required: `{str(bool(plan.get('cross_provider_required'))).lower()}`",
        f"- Parallelizable: `{str(bool(plan.get('parallelizable'))).lower()}`",
        f"- Evidence Requirements: {', '.join(f'`{item}`' for item in plan.get('evidence_requirements', []) or ['handoff_md'])}",
        f"- Independence: writer_same_operator=`{((plan.get('independence_policy') or {}).get('writer_same_operator', 'denied'))}`, writer_same_provider=`{((plan.get('independence_policy') or {}).get('writer_same_provider', 'allowed'))}`",
        f"- Escalation On Fail: {', '.join(f'`{item}`' for item in plan.get('escalation_on_fail', []) or ['Verifier'])}",
    ]
    if plan.get("fallback_applied"):
        lines.append(f"- Runtime Fallback Applied: `true`")
        lines.append(f"- Requested Review Mode: `{plan.get('requested_review_mode', 'N/A')}`")
        lines.append(f"- Requested Evaluators: `{plan.get('requested_required_evaluators', 'N/A')}`")
        lines.append(f"- Fallback Reason: `{plan.get('fallback_reason', 'N/A')}`")
        lines.append(f"- Follow-up Review Required: `{str(bool(plan.get('followup_review_required'))).lower()}`")
    return "\n".join(lines)


def _read_json_file(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deepresearch_quality_gate_from_eval(eval_json: str | Path) -> dict[str, Any]:
    data = _read_json_file(eval_json)
    gate = data.get("research_quality_gate") or data.get("deepresearch_quality_gate") or {}
    if isinstance(gate, dict) and gate:
        ok = bool(gate.get("ok")) or str(gate.get("verdict") or "").upper() == "PASS"
        return {"present": True, "ok": ok, "gate": gate}
    return {"present": False, "ok": False, "gate": {}}


def _looks_like_research_eval_data(data: dict[str, Any]) -> bool:
    return any(key in data for key in (
        "source_count",
        "evidence_count",
        "claim_count",
        "section_count",
        "unsupported_rate",
        "citation_accuracy",
        "output_dir",
        "final_md",
        "report_ast",
    ))


def _first_existing_path(candidates: list[Any], base_dir: Path | None = None, *, want_dir: bool | None = None) -> Path:
    for raw in candidates:
        raw_text = str(raw or "").strip()
        if not raw_text:
            continue
        path = Path(raw_text).expanduser()
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        if path.exists() and (want_dir is None or (path.is_dir() if want_dir else path.is_file())):
            return path
    return Path("")


def _discover_deepresearch_artifacts(sid: str, node: dict[str, Any], eval_json: str | Path) -> dict[str, str]:
    """Find DeepResearch artifacts from evaluator JSON, node metadata, and sprint paths."""
    eval_path = Path(eval_json).expanduser()
    eval_data = _read_json_file(eval_path) if eval_path.exists() else {}
    node_artifacts = node.get("research_artifacts") if isinstance(node.get("research_artifacts"), dict) else {}
    explicit_research_eval = [
        eval_data.get("research_eval"),
        eval_data.get("research_eval_json"),
        eval_data.get("eval_artifacts_json"),
        node_artifacts.get("research_eval"),
        node_artifacts.get("research_eval_json"),
        node_artifacts.get("eval_artifacts_json"),
        node.get("research_eval"),
        node.get("research_eval_json"),
        node.get("eval_artifacts_json"),
    ]
    research_eval = _first_existing_path(explicit_research_eval, eval_path.parent if str(eval_path) else None, want_dir=False)
    if (not research_eval or str(research_eval) in {"", "."}) and eval_path.exists() and _looks_like_research_eval_data(eval_data):
        research_eval = eval_path
    if not research_eval or str(research_eval) in {"", "."}:
        for base in [eval_path.parent if str(eval_path) else Path(""), SPRINTS_DIR / sid, SPRINTS_DIR]:
            if not str(base) or not base.exists():
                continue
            found = _first_existing_path(
                [base / "research_eval.json", base / f"{sid}-research_eval.json", base / "run-research_eval.json"],
                want_dir=False,
            )
            if found and str(found) not in {"", "."}:
                research_eval = found
                break
    research_eval_data = _read_json_file(research_eval) if research_eval and str(research_eval) not in {"", "."} else {}
    base_dirs = [
        eval_path.parent if str(eval_path) else Path(""),
        SPRINTS_DIR / sid,
        SPRINTS_DIR,
    ]
    output_dir = _first_existing_path([
        research_eval_data.get("output_dir"),
        eval_data.get("output_dir"),
        node_artifacts.get("output_dir"),
        node.get("research_output_dir"),
        node.get("output_dir"),
    ], eval_path.parent if str(eval_path) else None, want_dir=True)
    if str(output_dir) not in {"", "."}:
        base_dirs.insert(0, output_dir)

    def pick(keys: list[str], names: list[str]) -> Path:
        explicit: list[Any] = []
        for key in keys:
            explicit.extend([eval_data.get(key), node_artifacts.get(key), node.get(key)])
        for base in base_dirs:
            found = _first_existing_path(explicit, base if str(base) else None, want_dir=False)
            if found and str(found) not in {"", "."}:
                return found
        for base in base_dirs:
            if not str(base) or not base.exists():
                continue
            for name in names:
                candidate = base / name
                if candidate.exists():
                    return candidate
        return Path("")

    report_ast = pick(["report_ast", "report_ast_json"], ["report_ast.json"])
    final_md = pick(["final_md", "final_report", "final_report_md"], ["final.md"])
    bibliography = pick(["bibliography", "bibliography_json"], ["final.bibliography.json"])
    def file_str(path: Path) -> str:
        return str(path) if str(path) not in {"", "."} and path.exists() and path.is_file() else ""

    artifacts = {
        "eval_json": file_str(research_eval),
        "report_ast": file_str(report_ast),
        "final_md": file_str(final_md),
        "bibliography": file_str(bibliography),
    }
    if str(output_dir) not in {"", "."}:
        artifacts["output_dir"] = str(output_dir)
    return artifacts


def _deepresearch_quality_gate_auto_run(sid: str, node: dict[str, Any], eval_json: str | Path) -> dict[str, Any]:
    """Run deterministic DeepResearch gate during closeout when evaluator omitted it."""
    try:
        from research.evaluator import evaluate_final_closeout
    except ImportError:
        evaluate_final_closeout = None

    if evaluate_final_closeout is None:
        return {
            "present": True,
            "ok": False,
            "auto_run": True,
            "gate": {
                "ok": False,
                "verdict": "FAIL",
                "errors": ["research_evaluator_unavailable"],
            },
        }

    artifacts = _discover_deepresearch_artifacts(sid, node, eval_json)
    research_eval = artifacts.get("eval_json") or ""
    if not research_eval or not Path(research_eval).expanduser().exists():
        return {
            "present": False,
            "ok": False,
            "auto_run": True,
            "gate": {
                "ok": False,
                "verdict": "FAIL",
                "errors": [f"research_eval_artifact_missing:{research_eval or 'N/A'}"],
                "artifacts": artifacts,
            },
        }

    output_dir = artifacts.get("output_dir")
    if not output_dir:
        # fallback to the parent directory of eval_json
        eval_path = Path(eval_json).expanduser()
        output_dir = str(eval_path.parent) if eval_path.exists() else ""
    
    if not output_dir or not Path(output_dir).exists():
        return {
            "present": False,
            "ok": False,
            "auto_run": True,
            "gate": {
                "ok": False,
                "verdict": "FAIL",
                "errors": [f"research_output_dir_missing:{output_dir or 'N/A'}"],
                "artifacts": artifacts,
            },
        }

    closeout = evaluate_final_closeout(
        output_dir,
        strict=True,
    )

    # Load the updated eval_json or survey_eval.json to get research_quality_gate
    # because evaluate_final_closeout writes to it
    eval_json_path = Path(eval_json).expanduser()
    if eval_json_path.exists():
        res = _deepresearch_quality_gate_from_eval(eval_json_path)
        if res.get("present"):
            res["auto_run"] = True
            res["gate"]["discovered_artifacts"] = artifacts
            return res

    gate = {
        "ok": closeout.get("ok", False),
        "verdict": "PASS" if closeout.get("ok") else "FAIL",
        "closeout_verdict": closeout.get("verdict", "hard_fail"),
        "errors": closeout.get("issues") or [],
        "discovered_artifacts": artifacts,
    }
    return {
        "present": True,
        "ok": gate["ok"],
        "auto_run": True,
        "gate": gate,
    }


def _ensure_research_run(db_path: Path, topic: str, existing_run_id: str = "") -> str:
    if research_storage is None:
        raise RuntimeError("research storage unavailable")
    conn = research_storage.init_db(str(db_path))
    if existing_run_id:
        row = conn.execute("SELECT id FROM research_runs WHERE id = ?", (existing_run_id,)).fetchone()
        if row:
            conn.close()
            return existing_run_id
    conn.execute(
        "INSERT INTO research_runs (topic, depth_tier, status) VALUES (?, 'standard', 'pending')",
        (topic or "Human search run",),
    )
    conn.commit()
    run_id = conn.execute("SELECT id FROM research_runs ORDER BY created_at DESC LIMIT 1").fetchone()["id"]
    conn.close()
    return run_id


def _prepare_human_search_handoff(sid: str, graph_path: str | Path, node: dict[str, Any], dry_run: bool = False) -> dict[str, Any] | None:
    """Create a durable human-search handoff instead of dispatching a pane."""
    if not _node_requires_human_search(node):
        return None
    if render_human_search_handoff is None:
        return {"ok": False, "reason": "human_search_renderer_unavailable", "node": node.get("id")}

    node_id = str(node.get("id") or "")
    metadata = node.get("human_search") if isinstance(node.get("human_search"), dict) else {}
    db_path = Path(str(metadata.get("db_path") or SPRINTS_DIR / f"{sid}.research.sqlite"))
    handoff_md = Path(str(metadata.get("handoff_md") or SPRINTS_DIR / f"{sid}.{node_id}-human-search-handoff.md"))
    results_md = Path(str(metadata.get("results_md") or SPRINTS_DIR / f"{sid}.{node_id}-human-search-results.md"))
    query = str(node.get("search_query") or node.get("goal") or node_id)
    topic = str(node.get("topic") or node.get("goal") or sid)
    max_results = int(node.get("max_results") or metadata.get("max_results") or 8)

    if dry_run:
        return {
            "ok": True,
            "reason": "human_search_handoff_required",
            "node": node_id,
            "handoff_md": str(handoff_md),
            "results_md": str(results_md),
            "dry_run": True,
        }

    run_id = _ensure_research_run(db_path, topic, str(metadata.get("run_id") or ""))
    handoff_md.parent.mkdir(parents=True, exist_ok=True)
    handoff_md.write_text(
        render_human_search_handoff(topic=topic, query=query, run_id=run_id, max_results=max_results),
        encoding="utf-8",
    )

    graph = load_graph(graph_path)
    live = next((n for n in graph.get("nodes", []) if n.get("id") == node_id), node)
    live["status"] = "waiting_human_search"
    live["human_search"] = {
        "provider": "human-in-the-loop",
        "status": "waiting",
        "db_path": str(db_path),
        "run_id": run_id,
        "handoff_md": str(handoff_md),
        "results_md": str(results_md),
        "import_command": (
            f"solar-harness research import-search {db_path} --run-id {run_id} "
            f"--input-md {results_md} --continue --output-dir {SPRINTS_DIR / (sid + '.research-out')} "
            f"--output-md {SPRINTS_DIR / (sid + '.final.md')} --graph {graph_path} --node {node_id}"
        ),
    }
    graph.setdefault("node_results", {})[node_id] = {
        "status": "waiting_human_search",
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "handoff_md": str(handoff_md),
        "results_md": str(results_md),
        "run_id": run_id,
    }
    save_graph(graph_path, graph)
    try:
        _append_event(sid, {
            "event": "human_search_handoff_created",
            "by": "graph-dispatch",
            "data": {"node": node_id, "handoff_md": str(handoff_md), "results_md": str(results_md), "run_id": run_id},
        })
    except Exception:
        pass
    return {
        "ok": True,
        "reason": "waiting_human_search",
        "node": node_id,
        "handoff_md": str(handoff_md),
        "results_md": str(results_md),
        "run_id": run_id,
        "graph_updated": True,
    }


def _no_dispatch_enabled() -> bool:
    return os.environ.get("SOLAR_NO_DISPATCH") == "1" or NO_DISPATCH_FLAG.exists()


def _model_registry() -> dict[str, Any]:
    if _load_model_registry is not None:
        try:
            return _load_model_registry()
        except Exception:
            pass
    path = HARNESS_DIR / "config" / "model-registry.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "defaults": {"main_model": "opus", "lab_builder_matrix": "glm,glm,glm,anthropic-sonnet"},
            "models": {},
        }


def _normalize_model_alias(alias: str) -> str:
    reg = _model_registry()
    if _normalize_model is not None:
        try:
            return str(_normalize_model(reg, alias))
        except Exception:
            pass
    value = str(alias or "").strip().lower()
    fallback = {
        "opus": "claude-opus",
        "claude-opus": "claude-opus",
        "anthropic-sonnet": "claude-sonnet",
        "claude-sonnet": "claude-sonnet",
        "claude": "claude-sonnet",
        "glm": "zhipu-glm-5.1",
        "glm-5": "zhipu-glm-5.1",
        "glm-5.1": "zhipu-glm-5.1",
        "sonnet": "zhipu-glm-4.7",
        "glm-4.7": "zhipu-glm-4.7",
        "deepseek": "deepseek-v4-pro",
        "deepseek-v4-pro": "deepseek-v4-pro",
    }
    return fallback.get(value, value)


def _model_alias_set(alias: str) -> list[str]:
    reg = _model_registry()
    model_id = _normalize_model_alias(alias)
    spec = (reg.get("models") or {}).get(model_id) or {}
    values = {model_id, str(alias or "").strip().lower()}
    values.update(str(x).strip().lower() for x in (spec.get("aliases") or []) if str(x).strip())
    if spec.get("model_key"):
        values.add(str(spec["model_key"]).strip().lower())
    return sorted(v for v in values if v)


def _matrix_items(matrix: str) -> list[str]:
    return [x.strip() for x in str(matrix or "").split(",") if x.strip()]


def _load_user_config() -> dict[str, Any]:
    try:
        return json.loads((HARNESS_DIR / "config" / "solar-user-config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _configured_main_model(role: str) -> str:
    reg = _model_registry()
    cfg = _load_user_config()
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    default = (reg.get("defaults") or {}).get("main_model") or "opus"
    return str(models.get(role) or default)


def _configured_lab_model_for_pane(pane: str) -> str:
    reg = _model_registry()
    cfg = _load_user_config()
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    matrix = str(models.get("lab_builder_matrix") or (reg.get("defaults") or {}).get("lab_builder_matrix") or "glm,glm,glm,anthropic-sonnet")
    items = _matrix_items(matrix)
    if not items:
        return "anthropic-sonnet"
    try:
        index = int(str(pane).rsplit(".", 1)[1])
    except Exception:
        index = 0
    return items[index] if index < len(items) else items[-1]


def _models_for_pane(pane: str, title: str = "") -> list[str]:
    session = _current_harness_session()
    if pane == f"{session}:0.2":
        return _model_alias_set(_configured_main_model("builder"))
    if pane == f"{session}:0.3":
        return _model_alias_set(_configured_main_model("evaluator"))
    if _pane_in_lab_session(pane):
        return _model_alias_set(_configured_lab_model_for_pane(pane))
    title_lower = title.lower()
    if "deepseek" in title_lower:
        return _model_alias_set("deepseek")
    if "glm-5.1" in title_lower or "glm" in title_lower:
        return _model_alias_set("glm")
    if "opus" in title_lower:
        return _model_alias_set("opus")
    if "sonnet" in title_lower:
        return _model_alias_set("anthropic-sonnet")
    return _model_alias_set("anthropic-sonnet")


def _quota_models_for_provider(provider: str) -> list[str]:
    provider = str(provider or "").strip().lower()
    if provider in {"anthropic", "claude", "claude-code"}:
        values = set(_model_alias_set("anthropic-sonnet"))
        values.update(_model_alias_set("claude-opus"))
        values.update({"anthropic", "claude", "sonnet", "opus"})
        return sorted(values)
    if provider in {"zhipu", "glm", "bigmodel"}:
        return _model_alias_set("glm")
    if provider == "deepseek":
        return _model_alias_set("deepseek")
    return []


def _quota_exhausted_models(title: str, tail: str, health: dict[str, Any], models: list[str]) -> list[str]:
    values: set[str] = set()
    combined = re.sub(r"\s+", " ", f"{title}\n{tail}").lower()
    health_reason = str(health.get("reason") or health.get("status") or "").lower()
    health_provider = str(health.get("provider") or health.get("vendor") or "").lower()

    if PANE_QUOTA_EXHAUSTED_RE.search(combined) or "quota" in health_reason or "rate_limit" in health_reason:
        values.update(str(model).lower() for model in models if str(model).strip())

    if ("anthropic" in combined or "claude" in combined or "monthly usage limit" in combined
            or health_provider in {"anthropic", "claude", "claude-code"}):
        if PANE_QUOTA_EXHAUSTED_RE.search(combined) or "quota" in health_reason or "rate_limit" in health_reason:
            values.update(_quota_models_for_provider("anthropic"))

    if "glm" in combined or health_provider in {"zhipu", "glm", "bigmodel"}:
        if PANE_QUOTA_EXHAUSTED_RE.search(combined) or "quota" in health_reason or "rate_limit" in health_reason:
            values.update(_quota_models_for_provider("zhipu"))

    if "deepseek" in combined or health_provider == "deepseek":
        if PANE_QUOTA_EXHAUSTED_RE.search(combined) or "quota" in health_reason or "rate_limit" in health_reason:
            values.update(_quota_models_for_provider("deepseek"))

    return sorted(v for v in values if v)


def _operator_models_match(operator: dict[str, Any], models: list[str]) -> bool:
    values = {str(item).strip().lower() for item in models if str(item).strip()}
    combined = " ".join(
        str(operator.get(key) or "")
        for key in ("operator_id", "provider", "model", "model_config", "vendor")
    ).lower()
    if not values:
        return False
    if any(value and value in combined for value in values):
        return True
    if "sonnet" in values and "sonnet" in combined:
        return True
    if values & {"glm", "glm-5", "glm-5.1", "zhipu"} and ("glm" in combined or "zhipu" in combined):
        return True
    if any("deepseek" in value for value in values) and "deepseek" in combined:
        return True
    if any("opus" in value for value in values) and "opus" in combined:
        return True
    return False


def _pane_matches_operator(pane: str, operator: dict[str, Any]) -> bool:
    configured = str(operator.get("pane") or "").strip()
    if not configured:
        return False
    if configured == pane:
        return True
    if configured.endswith(":*"):
        return pane.startswith(configured[:-1])
    return False


def _persist_pane_rate_limit_block(pane: str, title: str, tail: str, models: list[str]) -> list[dict[str, Any]]:
    """Write pane-discovered rate limit state back to matching physical operators."""
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import operator_flow_control as ofc  # type: ignore
    except Exception:
        return []
    try:
        registry = json.loads((HARNESS_DIR / "config" / "physical-operators.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
    reset_at = ofc.parse_rate_limit_reset_at(tail or title)
    block_reason = "pane_tui_rate_limit"
    if reset_at is None:
        fallback_sec = max(60, int(PANE_RATE_LIMIT_FALLBACK_SEC or 900))
        reset_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=fallback_sec)
        block_reason = "pane_tui_rate_limit_fallback_ttl"
    evidence = "\n".join([title, tail])[-4000:]
    updates: list[dict[str, Any]] = []
    for op_id, spec in operators.items():
        if not isinstance(spec, dict):
            continue
        if not spec.get("enabled", True):
            continue
        if not (_pane_matches_operator(pane, spec) or _operator_models_match({"operator_id": op_id, **spec}, models)):
            continue
        result = ofc.persist_operator_block(
            str(op_id),
            "cooldown",
            expires_at=reset_at,
            reason=block_reason,
            source=f"tmux_pane:{pane}",
            evidence_text=evidence,
        )
        if result.get("ok"):
            ttl = ofc._seconds_until(reset_at, 3600)  # type: ignore[attr-defined]
            try:
                ofc.set_operator_state(str(op_id), "cooldown", ttl_seconds=ttl)
            except Exception:
                pass
            updates.append(result)
    return updates


def _node_id_from_intent(intent: str) -> str:
    match = re.search(r"(?:^|\|)node_id=([^|]+)", intent or "")
    return match.group(1) if match else ""


def _scope_lines(values: Any) -> str:
    if not values:
        return "- N/A"
    if isinstance(values, str):
        values = [values]
    return "\n".join(f"- `{v}`" for v in values)


def _iter_scope_values(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _canonical_sprint_artifact_path(raw: str) -> Path | None:
    """Resolve sprint artifact paths to the canonical harness sprint directory.

    Builder panes run inside role worktrees, so a relative path such as
    `harness/sprints/foo.md` otherwise lands under `.worktrees/builder`.
    Source-code paths are intentionally not rewritten; only sprint artifacts
    get canonical absolute guidance.
    """
    scope = str(raw or "").strip()
    if not scope or any(ch in scope for ch in "*?[]"):
        return None
    expanded = Path(scope).expanduser()
    if expanded.is_absolute():
        return expanded
    parts = expanded.parts
    if len(parts) >= 2 and parts[0] == "harness" and parts[1] == "sprints":
        return (HARNESS_DIR.parent / expanded).resolve()
    if parts and parts[0] == "sprints":
        return (HARNESS_DIR / expanded).resolve()
    return None


def _canonical_output_paths_block(node: dict[str, Any]) -> str:
    seen: set[tuple[str, str]] = set()
    rows: list[str] = []
    for field in ("write_scope", "outputs"):
        for raw in _iter_scope_values(node.get(field)):
            canonical = _canonical_sprint_artifact_path(raw)
            if canonical is None:
                continue
            key = (field, raw)
            if key in seen:
                continue
            seen.add(key)
            rows.append(f"- `{field}` `{raw}` -> `{canonical}`")
    if not rows:
        return (
            "## Canonical Output Paths\n\n"
            "- No sprint artifact outputs declared. For source-code files, use the current repository/worktree path."
        )
    return (
        "## Canonical Output Paths\n\n"
        "Builder panes may run from an isolated role worktree. For sprint artifacts, do not rely on "
        "relative `harness/sprints/...` paths; write to the canonical absolute paths below so the "
        "scheduler and evaluator can find them:\n\n"
        + "\n".join(rows)
    )


def _write_scope_preflight_block(sid: str, node: dict[str, Any]) -> str:
    """Warn builders when write-scope artifacts already exist from another sprint.

    Several early S01 graphs use generic files such as
    `sprints/s01-req-N5-handoff.md`. Those paths can survive from a different
    sprint and must not be treated as current evidence.
    """
    rows: list[str] = []
    sprint_re = re.compile(r"sprint-[A-Za-z0-9_.\-\u4e00-\u9fff]+")
    for raw in _iter_scope_values(node.get("write_scope")):
        scope = str(raw or "").strip()
        if not scope or any(ch in scope for ch in "*?[]"):
            continue
        path = _canonical_sprint_artifact_path(scope)
        if path is None:
            path = (HARNESS_DIR / scope).expanduser() if not scope.startswith("/") else Path(scope).expanduser()
        if not path.exists() or not path.is_file():
            continue
        try:
            stat = path.stat()
            sample = path.read_text(encoding="utf-8", errors="replace")[:12000]
        except Exception:
            continue
        refs = sorted(set(sprint_re.findall(sample)))
        foreign_refs = [ref for ref in refs if ref != sid]
        contains_current = sid in sample
        if foreign_refs or not contains_current:
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows.append(
                f"- `{scope}` exists already (mtime={mtime}, size={stat.st_size}); "
                f"contains_current_sprint={str(contains_current).lower()}; "
                f"foreign_sprint_refs={', '.join(foreign_refs[:3]) if foreign_refs else 'N/A'}"
            )
    if not rows:
        return "## Write Scope Preflight\n\n- No pre-existing stale write-scope artifacts detected."
    return (
        "## Write Scope Preflight\n\n"
        "The following declared output paths already exist but do not clearly belong to this sprint. "
        "Treat them as stale inputs, not as completion evidence. Overwrite with current-sprint content "
        "or explain why a different scoped artifact is required.\n\n"
        + "\n".join(rows)
    )


def _acceptance_lines(values: Any) -> str:
    if not values:
        return "- N/A"
    return "\n".join(f"- [ ] {v}" for v in values)


def _dispatch_file(sid: str, node_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", node_id).strip("-") or "node"
    return SPRINTS_DIR / f"{sid}.{safe}-dispatch.md"


def _safe_node_id(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", node_id).strip("-") or "node"


def _pane_safe(pane: str) -> str:
    return pane.replace(":", "_").replace(".", "_")


def _pane_health(pane: str) -> dict[str, Any]:
    path = HARNESS_DIR / "run" / "provider-health" / f"{_pane_safe(pane)}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    until = str(data.get("quarantine_until") or "")
    if until and until <= _utc_now():
        return {}
    if _provider_health_stale(data):
        return {}
    return data


def _parse_health_ts(value: Any) -> datetime.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(text, fmt).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            pass
    return None


def _provider_health_stale(data: dict[str, Any]) -> bool:
    """Do not let old temporary quota failures permanently remove panes."""
    if not data.get("unavailable") and str(data.get("status") or "").lower() != "unavailable":
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    reset_at = _parse_health_ts(data.get("reset_at_provider_time"))
    if reset_at and reset_at <= now:
        return True
    checked_at = _parse_health_ts(data.get("checked_at"))
    if not checked_at:
        return False
    ttl = int(os.environ.get("SOLAR_PROVIDER_HEALTH_UNAVAILABLE_TTL_SEC", "21600"))
    return (now - checked_at).total_seconds() > ttl


def _handoff_file(sid: str, node_id: str) -> Path:
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-handoff.md"


def _legacy_handoff_aliases(node_id: str) -> list[str]:
    aliases: list[str] = []
    raw = str(node_id or "").strip()
    if not raw:
        return aliases

    short = raw.split("_", 1)[0].strip()
    if short and short != raw and re.fullmatch(r"[A-Za-z]+\d+", short):
        aliases.append(short)

    match = re.match(r"^([A-Za-z]+\d+)\b", raw)
    if match:
        alias = match.group(1).strip()
        if alias and alias != raw and alias not in aliases:
            aliases.append(alias)
    return aliases


def _node_handoff_candidates(sid: str, node: dict[str, Any], graph: dict[str, Any]) -> list[Path]:
    node_id = str(node.get("id") or "")
    candidates = [_handoff_file(sid, node_id)]
    for alias in _legacy_handoff_aliases(node_id):
        candidates.append(_handoff_file(sid, alias))
    parent_handoff = f"sprints/{sid}.handoff.md"
    for scope in node.get("write_scope") or []:
        if str(scope).endswith(parent_handoff) or str(scope).endswith(f"{sid}.handoff.md"):
            candidates.append(SPRINTS_DIR / f"{sid}.handoff.md")
            break
    return candidates


def _existing_node_handoff(sid: str, node: dict[str, Any], graph: dict[str, Any]) -> Path | None:
    for candidate in _node_handoff_candidates(sid, node, graph):
        if candidate.exists():
            return candidate
    return None


def _node_repair_attempts(node: dict[str, Any]) -> int:
    raw = node.get("repair_attempts")
    if raw in (None, ""):
        context = node.get("repair_context")
        raw = context.get("attempt") if isinstance(context, dict) else 0
    try:
        return max(0, int(raw or 0))
    except Exception:
        return 0


def _node_repair_max_attempts(graph: dict[str, Any], node: dict[str, Any]) -> int:
    candidates: list[Any] = [
        node.get("max_repair_attempts"),
        node.get("repair_max_attempts"),
    ]
    repair_policy = graph.get("node_repair") if isinstance(graph.get("node_repair"), dict) else {}
    quality_gates = graph.get("quality_gates") if isinstance(graph.get("quality_gates"), dict) else {}
    graph_repair_gate = quality_gates.get("repair") if isinstance(quality_gates.get("repair"), dict) else {}
    candidates.extend([
        repair_policy.get("max_attempts"),
        graph_repair_gate.get("max_attempts"),
        GRAPH_NODE_REPAIR_MAX_ATTEMPTS,
    ])
    for raw in candidates:
        if raw in (None, ""):
            continue
        try:
            return max(0, int(raw))
        except Exception:
            continue
    return 1


def _archive_path_for_repair(path: Path, attempt: int) -> Path:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = path.with_name(f"{path.stem}.repair{attempt}.{stamp}{path.suffix}")
    if not base.exists():
        return base
    for index in range(2, 100):
        candidate = path.with_name(f"{path.stem}.repair{attempt}.{stamp}.{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}.repair{attempt}.{stamp}.{os.getpid()}{path.suffix}")


def _archive_node_review_sidecars(sid: str, node_id: str, handoff_file: Path | None, eval_json_path: str | Path, attempt: int) -> dict[str, str]:
    archived: dict[str, str] = {}
    candidates: list[tuple[str, Path]] = []
    if handoff_file is not None:
        candidates.append(("handoff_md", Path(handoff_file)))
    for key, path in (
        ("eval_json", Path(str(eval_json_path))) if str(eval_json_path or "").strip() else ("eval_json", Path()),
        ("eval_md", _eval_md_file(sid, node_id)),
    ):
        if str(path) not in {"", "."}:
            candidates.append((key, path))

    seen: set[Path] = set()
    for key, path in candidates:
        try:
            resolved = path.expanduser()
        except Exception:
            continue
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        archive = _archive_path_for_repair(resolved, attempt)
        try:
            resolved.replace(archive)
        except Exception:
            continue
        archived[key] = str(archive)
    return archived


def _archive_stale_repair_eval_sidecars(
    sid: str,
    node: dict[str, Any],
    node_id: str,
    handoff_file: Path | None,
    eval_json_path: str | Path,
    status: str,
) -> dict[str, str]:
    if status in {"passed", "failed"}:
        return {}
    attempt = _node_repair_attempts(node)
    if attempt <= 0 or handoff_file is None:
        return {}
    try:
        handoff = Path(handoff_file).expanduser()
        handoff_mtime = handoff.stat().st_mtime
    except Exception:
        return {}

    archived: dict[str, str] = {}
    candidates: list[tuple[str, Path]] = []
    if str(eval_json_path or "").strip():
        candidates.append(("eval_json", Path(str(eval_json_path))))
    candidates.append(("eval_md", _eval_md_file(sid, node_id)))

    seen: set[Path] = set()
    for key, raw_path in candidates:
        try:
            path = raw_path.expanduser()
            if path in seen or not path.exists():
                continue
            seen.add(path)
            if path.stat().st_mtime >= handoff_mtime:
                continue
            archive = _archive_path_for_repair(path, attempt)
            path.replace(archive)
        except Exception:
            continue
        archived[key] = str(archive)
    return archived


def _short_eval_errors(eval_payload: dict[str, Any]) -> list[dict[str, str]]:
    errors = eval_payload.get("errors")
    if not isinstance(errors, list):
        return []
    items: list[dict[str, str]] = []
    for raw in errors[:6]:
        if not isinstance(raw, dict):
            continue
        item: dict[str, str] = {}
        for key in ("cond", "severity", "evidence", "fix_hint"):
            value = str(raw.get(key) or "").strip()
            if value:
                item[key] = value[:1200]
        if item:
            items.append(item)
    return items


def _start_node_repair_from_eval_fail(
    graph: dict[str, Any],
    node: dict[str, Any],
    sid: str,
    node_id: str,
    handoff_file: Path,
    eval_json_path: str,
    eval_payload: dict[str, Any],
) -> dict[str, Any] | None:
    max_attempts = _node_repair_max_attempts(graph, node)
    prior_attempts = _node_repair_attempts(node)
    if prior_attempts >= max_attempts:
        # Repair budget exhausted: the reconcile caller falls through and marks this node terminal
        # `failed`. Record the (otherwise silent) exhaustion so the terminal cause is provable from disk.
        _record_node_runstate(sid, node_id, {
            "repair_attempt": prior_attempts,
            "max_repair_attempts": max_attempts,
            "last_eval_result": "FAIL",
            "last_eval_reason": "repair_budget_exhausted",
            "next_action": "terminal_failed",
            "status": str(node.get("status") or ""),
        })
        return None

    attempt = prior_attempts + 1
    archived = _archive_node_review_sidecars(sid, node_id, handoff_file, eval_json_path, attempt)
    now = _utc_now()
    failed_conditions = eval_payload.get("failed_conditions")
    if not isinstance(failed_conditions, list):
        failed_conditions = []
    repair_context = {
        "attempt": attempt,
        "max_attempts": max_attempts,
        "verdict": "FAIL",
        "summary": str(eval_payload.get("summary") or "").strip()[:2000],
        "failed_conditions": [str(item) for item in failed_conditions if str(item).strip()][:20],
        "errors": _short_eval_errors(eval_payload),
        "archived_sidecars": archived,
        "created_at": now,
    }

    _clear_eval_assignments(node)
    for key in (
        "assigned_to",
        "dispatch_id",
        "eval_json",
        "eval_assigned_to",
        "eval_dispatch_id",
        "eval_dispatched_at",
        "eval_retry_reason",
        "last_eval_closeout_failure",
        "last_eval_operator_cooldown_after_closeout",
        "handoff_md",
    ):
        node.pop(key, None)

    artifacts = node.get("artifacts")
    if isinstance(artifacts, dict):
        artifacts.pop("eval_json", None)
        artifacts.pop("handoff_md", None)

    node["status"] = "failed_review"
    node["repair_attempts"] = attempt
    node["repair_context"] = repair_context
    node.setdefault("repair_history", []).append(repair_context)
    node["updated_at"] = now

    graph.setdefault("node_results", {})
    graph["node_results"][node_id] = {
        "status": "failed_review",
        "updated_at": now,
        "note": f"repair_requested_from_eval_sidecar:{Path(eval_json_path).name}",
        "repair_context": repair_context,
    }
    _record_node_runstate(sid, node_id, {
        "repair_attempt": attempt,
        "max_repair_attempts": max_attempts,
        "last_eval_result": "FAIL",
        "last_eval_reason": repair_context.get("summary") or "eval_failed",
        "next_action": "rebuild_and_reeval",
        "status": "failed_review",
    })
    return repair_context


def _ledger_dispatch_for(sid: str, instruction_file: Path) -> dict[str, Any]:
    if not DISPATCH_LEDGER.exists():
        return {}
    needle = str(instruction_file)
    found: dict[str, Any] = {}
    for raw in DISPATCH_LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if row.get("sid") != sid or row.get("kind") != "intent_injected":
            continue
        text = json.dumps(row, ensure_ascii=False)
        if needle not in text:
            continue
        found = row
    return found


def _active_multi_task_status_for(sid: str, node_id: str) -> dict[str, Any] | None:
    """Return an active multi-task worker for this graph node, if one exists.

    Direct graph dispatch uses pane leases; multi-task dispatch owns its own
    process lifecycle under run/multi-task. Reconcile must not reset a node to
    pending while a multi-task worker for the same graph/node is still active.
    """
    newest: tuple[str, dict[str, Any]] | None = None
    for status_path in MULTI_TASK_RUN_DIR.glob("*/status.json"):
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(status.get("sprint_id") or "") != sid:
            continue
        if str(status.get("node_id") or "") != node_id:
            continue
        task_status = str(status.get("status") or "").lower()
        if task_status not in {"dispatched", "running", "in_progress"}:
            continue
        updated = str(status.get("updated_at") or status.get("created_at") or "")
        if newest is None or updated > newest[0]:
            newest = (updated, status)
    return newest[1] if newest else None


def _latest_operator_result_for(sid: str, node_id: str, operator_id: str = "") -> dict[str, Any] | None:
    """Return the newest terminal PM/operator result for a graph node.

    Operator-pool dispatch is asynchronous: `pm_dispatch submit` can succeed
    while the real worker later produces no node handoff.  Graph reconciliation
    must therefore inspect the operator result artifact instead of treating the
    submit ack as durable completion proof.
    """
    root = HARNESS_DIR / "run" / "operator-results"
    if not root.exists():
        return None
    newest: tuple[str, dict[str, Any]] | None = None
    for result_json in root.glob("*/*/result.json"):
        data = _read_json_file_safe(result_json)
        if str(data.get("sprint_id") or "") != sid:
            continue
        if str(data.get("node_id") or "") != node_id:
            continue
        if operator_id and str(data.get("operator_id") or "") != operator_id:
            continue
        status = str(data.get("status") or "").strip().lower()
        if status not in {"completed", "failed", "failed_missing_handoff", "failed_stale_handoff", "cancelled", "error"}:
            continue
        finished = str(data.get("finished_at") or data.get("updated_at") or data.get("started_at") or "")
        item = dict(data)
        item["_result_json"] = str(result_json)
        if newest is None or finished > newest[0]:
            newest = (finished, item)
    return newest[1] if newest else None


def _latest_pm_task_record_for(sid: str, node_id: str, operator_id: str = "") -> dict[str, Any] | None:
    """Return the newest terminal PM task record for a graph node."""
    root = HARNESS_DIR / "run" / "pm-inbox"
    if not root.exists():
        return None
    newest: tuple[str, dict[str, Any]] | None = None
    for record_json in root.glob("pm-*.json"):
        data = _read_json_file_safe(record_json)
        if str(data.get("sprint_id") or "") != sid:
            continue
        if str(data.get("node_id") or "") != node_id:
            continue
        if operator_id and str(data.get("operator_id") or "") != operator_id:
            continue
        role = str(data.get("requested_role") or "").strip().lower()
        if role and role not in {"builder", "implementation", "implementer", "coder", "dev"}:
            continue
        status = str(data.get("status") or "").strip().lower()
        if status not in {"completed", "failed", "failed_contract_closeout", "cancelled", "error"}:
            continue
        finished = str(
            data.get("completed_at")
            or data.get("failed_at")
            or data.get("updated_at")
            or data.get("submitted_at")
            or ""
        )
        item = dict(data)
        item["_pm_task_json"] = str(record_json)
        if newest is None or finished > newest[0]:
            newest = (finished, item)
    return newest[1] if newest else None


def _operator_terminal_result_closeout(
    sid: str,
    node_id: str,
    node: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any] | None:
    pane = str(node.get("assigned_to") or "").strip()
    operator_id = ""
    if pane.startswith("operator:"):
        operator_id = pane.split(":", 1)[1].strip()
    elif pane:
        operator_id = pane
    if not operator_id:
        operator_id = str(node.get("operator_id") or "").strip()
    if not operator_id:
        return None
    result = _latest_operator_result_for(sid, node_id, operator_id=operator_id)
    if not result:
        result = _latest_pm_task_record_for(sid, node_id, operator_id=operator_id)
    if not result:
        return None
    status = str(result.get("status") or "").strip().lower()
    if status == "completed" and _existing_node_handoff(sid, node, graph):
        return None
    if status == "completed":
        return {
            "reason": "failed_contract_closeout",
            "operator_status": status,
            "result_json": str(result.get("_result_json") or ""),
            "pm_task_json": str(result.get("_pm_task_json") or ""),
            "operator_id": operator_id,
            "detail": "operator completed but node handoff/eval artifacts are missing",
        }
    if status == "failed_contract_closeout":
        return {
            "reason": "failed_contract_closeout",
            "operator_status": status,
            "result_json": str(result.get("_result_json") or ""),
            "pm_task_json": str(result.get("_pm_task_json") or ""),
            "operator_id": operator_id,
            "detail": str(result.get("failure_reason") or "pm task failed contract closeout")[:500],
        }
    return {
        "reason": f"operator_result_{status or 'failed'}",
        "operator_status": status or "failed",
        "result_json": str(result.get("_result_json") or ""),
        "pm_task_json": str(result.get("_pm_task_json") or ""),
        "operator_id": operator_id,
        "exit_code": result.get("exit_code"),
        "detail": str(result.get("failure_reason") or "")[:500],
    }


def _cooldown_operator_after_contract_closeout(operator_id: str, closeout: dict[str, Any]) -> dict[str, Any]:
    operator_id = str(operator_id or "").strip()
    if not operator_id or OPERATOR_CONTRACT_CLOSEOUT_COOLDOWN_SEC <= 0:
        return {"ok": False, "reason": "operator_cooldown_disabled_or_missing"}
    try:
        if str(HARNESS_DIR / "lib") not in sys.path:
            sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import operator_flow_control as ofc  # type: ignore

        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=OPERATOR_CONTRACT_CLOSEOUT_COOLDOWN_SEC
        )
        persisted = ofc.persist_operator_block(
            operator_id,
            "cooldown",
            expires_at=expires_at,
            reason="contract_closeout_failed",
            source="graph_node_dispatcher",
            evidence_text=json.dumps(closeout, ensure_ascii=False)[-4000:],
        )
        runtime = ofc.set_operator_state(
            operator_id,
            "cooldown",
            ttl_seconds=OPERATOR_CONTRACT_CLOSEOUT_COOLDOWN_SEC,
        )
        return {
            "ok": bool(runtime.get("runtime_state") == "cooldown" or persisted.get("ok")),
            "operator_id": operator_id,
            "cooldown_sec": OPERATOR_CONTRACT_CLOSEOUT_COOLDOWN_SEC,
            "persisted": persisted,
            "runtime": runtime,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "operator_id": operator_id}


def _sidecar_reconcile_dependency_blockers(graph: dict[str, Any], node: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for dep in node.get("depends_on") or []:
        dep_id = str(dep or "").strip()
        if not dep_id or dep_id.startswith("external:") or "://" in dep_id:
            continue
        try:
            dep_status = str(node_status(graph, dep_id) or "").strip().lower()
        except Exception:
            dep_status = ""
        if dep_status != "passed":
            blockers.append(dep_id)
    return blockers


def _reconcile_existing_dispatches(graph: dict[str, Any], graph_path: str | Path) -> list[dict[str, Any]]:
    sid = str(graph.get("sprint_id") or Path(graph_path).stem.replace(".task_graph", ""))
    repaired: list[dict[str, Any]] = []
    # A finalized sprint is terminal and frozen: do not let leftover handoff/eval
    # sidecars "repair" (revert) its nodes. Without this guard a post-close
    # reconcile resets a passed node back to `reviewing` from a lingering handoff
    # file and reopens a closed sprint (Defect C).
    if (SPRINTS_DIR / f"{sid}.finalized").exists():
        return repaired
    for node in graph.get("nodes", []):
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        status = node_status(graph, node_id)
        handoff_file = _existing_node_handoff(sid, node, graph)
        dependency_blockers = _sidecar_reconcile_dependency_blockers(graph, node) if handoff_file else []
        eval_json_path = str(node.get("eval_json") or _eval_json_file(sid, node_id))
        stale_eval_archived = _archive_stale_repair_eval_sidecars(
            sid,
            node,
            node_id,
            handoff_file,
            eval_json_path,
            str(status or "").strip().lower(),
        )
        if stale_eval_archived:
            repaired.append(
                {
                    "node": node_id,
                    "status": status,
                    "reason": "repair_handoff_newer_than_eval_sidecar",
                    "handoff": str(handoff_file),
                    "archived_sidecars": stale_eval_archived,
                }
            )
        if not stale_eval_archived and not Path(eval_json_path).exists():
            backfilled_eval = _maybe_backfill_eval_json_from_md(sid, node_id)
            if backfilled_eval is not None:
                eval_json_path = str(backfilled_eval)
        eval_payload = {} if stale_eval_archived else (_read_json_file_safe(eval_json_path) if eval_json_path else {})
        raw_eval_verdict = str(eval_payload.get("verdict") or eval_payload.get("status") or "").strip().lower()
        if raw_eval_verdict in {"pass", "passed", "ok", "success", "succeeded"}:
            eval_verdict = "PASS"
        elif raw_eval_verdict in {"fail", "failed", "error", "errored"}:
            eval_verdict = "FAIL"
        else:
            eval_verdict = ""
        if handoff_file and eval_verdict in {"PASS", "FAIL"} and status in {"passed", "failed"}:
            stale_eval_keys = [
                "eval_assigned_to",
                "eval_dispatch_id",
                "eval_retry_reason",
                "last_eval_closeout_failure",
                "last_eval_operator_cooldown_after_closeout",
            ]
            cleared = [key for key in stale_eval_keys if key in node]
            if cleared:
                for key in cleared:
                    node.pop(key, None)
                node["eval_json"] = eval_json_path
                node["updated_at"] = _utc_now()
                repaired.append(
                    {
                        "node": node_id,
                        "status": status,
                        "reason": "canonical_eval_verdict_cleared_stale_eval_state",
                        "cleared": cleared,
                        "eval_json": eval_json_path,
                        "verdict": eval_verdict,
                    }
                )
            continue
        if handoff_file and dependency_blockers and eval_verdict in {"PASS", "FAIL"} and status not in {"passed", "failed"}:
            repaired.append(
                {
                    "node": node_id,
                    "status": status,
                    "reason": "sidecar_reconcile_blocked_by_dependencies",
                    "handoff": str(handoff_file),
                    "eval_json": eval_json_path,
                    "blocked_by": dependency_blockers,
                }
            )
            continue
        if handoff_file and eval_verdict in {"PASS", "FAIL"} and status in {"pending", "queued", "blocked", "assigned", "dispatched", "in_progress", "running", "reviewing", "ready_for_review", "needs_human_review", "failed_review", ""}:
            pane = str(node.get("assigned_to") or "").strip()
            dispatch_id = str(node.get("dispatch_id") or "").strip()
            if pane and dispatch_id:
                release_lease(pane, dispatch_id, "graph_dispatch_reconcile_eval_verdict")
            if eval_verdict == "FAIL":
                repair_context = _start_node_repair_from_eval_fail(
                    graph,
                    node,
                    sid,
                    node_id,
                    handoff_file,
                    eval_json_path,
                    eval_payload,
                )
                if repair_context is not None:
                    repaired.append(
                        {
                            "node": node_id,
                            "status": "failed_review",
                            "reason": "eval_sidecar_failed_repair_requested",
                            "handoff": str(handoff_file),
                            "eval_json": eval_json_path,
                            "verdict": eval_verdict,
                            "repair_attempt": repair_context.get("attempt"),
                            "max_repair_attempts": repair_context.get("max_attempts"),
                        }
                    )
                    continue
            # Self-graded guard: a PASS verdict from an eval.json sidecar the EXECUTING agent wrote
            # itself, with NO independent evaluator report (no non-empty {node}-eval.md, no
            # {node}-eval-dispatch), must NOT auto-close the node to passed here -- that is the
            # eval-backfill false-positive vector (a self-reported verdict standing in for a real
            # evaluation). Clear the finished worker's claim and leave the node in review so
            # dispatch_node_evals routes it to a real evaluator; only a genuinely-evaluated PASS may
            # close here. FAIL is unaffected (a fail is safe to honor without an independent report).
            # (handoff_file is already a real, existing handoff per the branch condition above.)
            if eval_verdict == "PASS" and _node_eval_self_graded(sid, node_id):
                node.pop("assigned_to", None)
                node.pop("dispatch_id", None)
                repaired.append(
                    {
                        "node": node_id,
                        "status": status,
                        "reason": "self_graded_pass_needs_independent_eval",
                        "handoff": str(handoff_file),
                        "eval_json": eval_json_path,
                        "verdict": eval_verdict,
                    }
                )
                continue
            node.pop("assigned_to", None)
            node.pop("dispatch_id", None)
            verdict_status = "passed" if eval_verdict == "PASS" else "failed"
            mark_node_result(
                graph,
                node_id,
                verdict_status,
                gate_status=verdict_status,
                note=f"reconciled_from_eval_sidecar:{Path(eval_json_path).name}",
            )
            node["status"] = verdict_status
            node["updated_at"] = _utc_now()
            node["eval_json"] = eval_json_path
            repaired.append(
                {
                    "node": node_id,
                    "status": verdict_status,
                    "reason": "eval_sidecar_exists",
                    "handoff": str(handoff_file),
                    "eval_json": eval_json_path,
                    "verdict": eval_verdict,
                }
            )
            continue
        if handoff_file and dependency_blockers and status in {"pending", "queued", "blocked", "worker_blocked", "assigned", "dispatched", "in_progress", "running", ""}:
            repaired.append(
                {
                    "node": node_id,
                    "status": status,
                    "reason": "handoff_reconcile_blocked_by_dependencies",
                    "handoff": str(handoff_file),
                    "blocked_by": dependency_blockers,
                }
            )
            continue
        if handoff_file and status in {"pending", "queued", "blocked", "worker_blocked", "assigned", "dispatched", "in_progress", "running", ""}:
            pane = str(node.get("assigned_to") or "").strip()
            dispatch_id = str(node.get("dispatch_id") or "").strip()
            if pane and dispatch_id:
                release_lease(pane, dispatch_id, "graph_dispatch_reconcile_handoff_reviewing")
            node.pop("assigned_to", None)
            node.pop("dispatch_id", None)
            set_node_status(graph, node_id, "reviewing")
            node["status"] = "reviewing"
            node["updated_at"] = _utc_now()
            repaired.append({"node": node_id, "status": "reviewing", "reason": "handoff_file_exists", "handoff": str(handoff_file)})
            continue
        if handoff_file and status in {"reviewing", "ready_for_review", "needs_human_review", "failed_review"}:
            pane = str(node.get("assigned_to") or "").strip()
            dispatch_id = str(node.get("dispatch_id") or "").strip()
            if pane or dispatch_id:
                if pane and dispatch_id:
                    release_lease(pane, dispatch_id, "graph_dispatch_reconcile_reviewing_builder_claim")
                node.pop("assigned_to", None)
                node.pop("dispatch_id", None)
                node["updated_at"] = _utc_now()
                repaired.append(
                    {
                        "node": node_id,
                        "status": status,
                        "reason": "reviewing_builder_claim_cleared",
                        "handoff": str(handoff_file),
                    }
                )
        active_multi_task = _active_multi_task_status_for(sid, node_id)
        if active_multi_task and status in {"pending", "queued", "blocked", "assigned", "dispatched", "in_progress", "running", ""}:
            dispatch_id = str(active_multi_task.get("id") or active_multi_task.get("dispatch_id") or "").strip()
            window = str(active_multi_task.get("window") or "").strip()
            pane = f"multi-task:{window}" if window else "multi-task"
            set_node_status(graph, node_id, "dispatched", pane=pane, dispatch_id=dispatch_id or None)
            node["updated_at"] = _utc_now()
            repaired.append(
                {
                    "node": node_id,
                    "pane": pane,
                    "dispatch_id": dispatch_id,
                    "status": "dispatched",
                    "reason": "active_multi_task_status_exists",
                }
            )
            continue
        if status in {"assigned", "dispatched", "in_progress", "running"}:
            closeout = _operator_terminal_result_closeout(sid, node_id, node, graph)
            if closeout:
                pane = str(node.get("assigned_to") or "").strip()
                dispatch_id = str(node.get("dispatch_id") or "").strip()
                operator_cooldown = {}
                if closeout.get("reason") == "failed_contract_closeout":
                    operator_cooldown = _cooldown_operator_after_contract_closeout(
                        str(closeout.get("operator_id") or ""),
                        closeout,
                    )
                if pane and dispatch_id:
                    release_lease(pane, dispatch_id, f"graph_dispatch_reconcile_{closeout['reason']}")
                node.pop("assigned_to", None)
                node.pop("dispatch_id", None)
                node["dispatch_retry_reason"] = closeout["reason"]
                node["last_operator_closeout_failure"] = closeout
                if operator_cooldown:
                    node["last_operator_cooldown_after_closeout"] = operator_cooldown
                node["updated_at"] = _utc_now()
                node["status"] = "pending"
                graph.setdefault("node_results", {}).pop(node_id, None)
                _append_dispatch_ledger(
                    "dispatch_reassigned_after_operator_closeout_failure",
                    sid,
                    pane,
                    dispatch_id,
                    {"node": node_id, **closeout, "operator_cooldown": operator_cooldown},
                )
                repaired.append(
                    {
                        "node": node_id,
                        "pane": pane,
                        "dispatch_id": dispatch_id,
                        "status": "pending",
                        "reason": closeout["reason"],
                        "operator_status": closeout.get("operator_status"),
                        "result_json": closeout.get("result_json"),
                        "operator_cooldown": operator_cooldown,
                    }
                )
                continue
        if status in {"assigned", "dispatched", "in_progress", "running"}:
            pane = str(node.get("assigned_to") or "").strip()
            dispatch_id = str(node.get("dispatch_id") or "").strip()
            if pane and dispatch_id:
                title = _pane_title(pane)
                lease = read_lease(pane)
                lease_live = bool(
                    isinstance(lease, dict)
                    and str(lease.get("dispatch_id") or "") == dispatch_id
                    and str(lease.get("expires_at") or "") > _utc_now()
                )
                ack_file = HARNESS_DIR / "sprints" / "graph-acks" / f"{sid}.{node_id}-submit-ack.json"
                ack_live = False
                ack_payload: dict[str, Any] = {}
                if ack_file.exists():
                    try:
                        ack_payload = json.loads(ack_file.read_text(encoding="utf-8"))
                        ack_live = str(ack_payload.get("dispatch_id") or "") == dispatch_id
                    except Exception:
                        ack_payload = {}
                        ack_live = False
                tail = _pane_tail(pane)
                dispatch_prompt_reason = _pane_dispatch_prompt_reason(tail)
                unavailable_reason = _pane_cooldown_reason(pane) or _pane_runtime_unavailable_reason(pane, title) or _pane_unavailable_reason(pane)
                idle_assigned = "graph_node_idle_assigned" in title.lower()
                if ack_live and unavailable_reason in RECOVERABLE_DISPATCH_PROMPT_REASONS:
                    if _dismiss_dispatch_prompt(pane, unavailable_reason):
                        set_node_status(graph, node_id, "dispatched", pane=pane, dispatch_id=dispatch_id)
                        repaired.append(
                            {
                                "node": node_id,
                                "pane": pane,
                                "dispatch_id": dispatch_id,
                                "status": "dispatched",
                                "reason": f"recoverable_prompt_kept_active:{unavailable_reason}",
                            }
                        )
                        continue
                    release_lease(pane, dispatch_id, f"graph_dispatch_reconcile_recoverable_prompt_failed:{unavailable_reason}")
                    node.pop("assigned_to", None)
                    node.pop("dispatch_id", None)
                    node["dispatch_retry_reason"] = unavailable_reason
                    node["updated_at"] = _utc_now()
                    node["status"] = "pending"
                    graph.setdefault("node_results", {}).pop(node_id, None)
                    _append_dispatch_ledger(
                        "dispatch_reassigned_after_recover_failed",
                        sid,
                        pane,
                        dispatch_id,
                        {"reason": unavailable_reason, "node": node_id},
                    )
                    repaired.append(
                        {
                            "node": node_id,
                            "pane": pane,
                            "dispatch_id": dispatch_id,
                            "status": "pending",
                            "reason": unavailable_reason,
                        }
                    )
                    continue
                if ack_live and not unavailable_reason:
                    submitted_at = _parse_utc(str(ack_payload.get("submitted_at") or ""))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    if submitted_at and lease_live and not _pane_tui_busy(pane) and (now - submitted_at).total_seconds() > 300:
                        release_lease(pane, dispatch_id, "graph_dispatch_reconcile_ack_idle_no_worker_activity")
                        node.pop("assigned_to", None)
                        node.pop("dispatch_id", None)
                        node["dispatch_retry_reason"] = "submit_ack_idle_no_worker_activity"
                        node["updated_at"] = _utc_now()
                        node["status"] = "pending"
                        graph.setdefault("node_results", {}).pop(node_id, None)
                        repaired.append(
                            {
                                "node": node_id,
                                "pane": pane,
                                "dispatch_id": dispatch_id,
                                "status": "pending",
                                "reason": "submit_ack_idle_no_worker_activity",
                            }
                        )
                        continue
                    # Some deployments intentionally disable runtime leases.
                    # A matching submit ack is the durable proof that the pane
                    # received the node, so do not reset/re-enqueue it merely
                    # because no live lease exists.
                    set_node_status(graph, node_id, "dispatched", pane=pane, dispatch_id=dispatch_id)
                    continue
                if lease_live and not unavailable_reason and not _pane_tui_busy(pane):
                    acquired_at = _parse_utc(str((lease or {}).get("acquired_at") or ""))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    if acquired_at and (now - acquired_at).total_seconds() > 120:
                        release_lease(pane, dispatch_id, "graph_dispatch_reconcile_live_lease_idle_without_submit_ack")
                        node.pop("assigned_to", None)
                        node.pop("dispatch_id", None)
                        node["dispatch_retry_reason"] = "live_lease_idle_without_submit_ack"
                        node["updated_at"] = _utc_now()
                        node["status"] = "pending"
                        graph.setdefault("node_results", {}).pop(node_id, None)
                        repaired.append(
                            {
                                "node": node_id,
                                "pane": pane,
                                "dispatch_id": dispatch_id,
                                "status": "pending",
                                "reason": "live_lease_idle_without_submit_ack",
                            }
                        )
                        continue
                if not lease_live:
                    release_lease(
                        pane,
                        dispatch_id,
                        f"graph_dispatch_reconcile_stale_active_dispatch:{dispatch_prompt_reason or unavailable_reason or 'missing_live_lease'}",
                    )
                    node.pop("assigned_to", None)
                    node.pop("dispatch_id", None)
                    node["dispatch_retry_reason"] = dispatch_prompt_reason or unavailable_reason or "stale_submit_ack_without_live_lease"
                    node["updated_at"] = _utc_now()
                    node["status"] = "pending"
                    graph.setdefault("node_results", {}).pop(node_id, None)
                    repaired.append(
                        {
                            "node": node_id,
                            "pane": pane,
                            "dispatch_id": dispatch_id,
                            "status": "pending",
                            "reason": node["dispatch_retry_reason"],
                        }
                    )
                    continue
                if unavailable_reason:
                    release_lease(pane, dispatch_id, f"graph_dispatch_reconcile_unavailable:{unavailable_reason}")
                    node.pop("assigned_to", None)
                    node.pop("dispatch_id", None)
                    node["dispatch_retry_reason"] = unavailable_reason
                    node["updated_at"] = _utc_now()
                    if _recoverable_pane_blocker(unavailable_reason):
                        node["status"] = "pending"
                        graph.setdefault("node_results", {}).pop(node_id, None)
                        _append_dispatch_ledger(
                            "dispatch_reassigned_after_recoverable_pane_blocker",
                            sid,
                            pane,
                            dispatch_id,
                            {"reason": unavailable_reason, "node": node_id},
                        )
                        repaired.append(
                            {
                                "node": node_id,
                                "pane": pane,
                                "dispatch_id": dispatch_id,
                                "status": "pending",
                                "reason": unavailable_reason,
                            }
                        )
                        continue
                    graph.setdefault("node_results", {})
                    graph["node_results"][node_id] = {
                        "status": "worker_blocked",
                        "updated_at": node["updated_at"],
                        "blocking_reason": unavailable_reason,
                    }
                    node["status"] = "worker_blocked"
                    repaired.append(
                        {
                            "node": node_id,
                            "pane": pane,
                            "dispatch_id": dispatch_id,
                            "status": "worker_blocked",
                            "reason": unavailable_reason,
                        }
                    )
                    continue
        if status in {"reviewing", "ready_for_review", "needs_human_review", "failed_review"}:
            assignments = _node_eval_assignments(node)
            terminal_operator_assignment = None
            for assignment in assignments:
                pane = str(assignment.get("pane") or "").strip()
                if not pane.startswith("operator:"):
                    continue
                operator_id = pane.split(":", 1)[1].strip()
                result = _latest_operator_result_for(sid, node_id, operator_id=operator_id)
                if result and not Path(str(assignment.get("eval_json_path") or _eval_json_file(sid, node_id))).exists():
                    terminal_operator_assignment = {
                        "pane": pane,
                        "dispatch_id": str(assignment.get("dispatch_id") or "").strip(),
                        "reason": "eval_failed_contract_closeout",
                        "operator_status": str(result.get("status") or ""),
                        "result_json": str(result.get("_result_json") or ""),
                    }
                    break
            if terminal_operator_assignment:
                operator_cooldown = {}
                failed_operator = ""
                pane_value = str(terminal_operator_assignment.get("pane") or "")
                if pane_value.startswith("operator:"):
                    failed_operator = pane_value.split(":", 1)[1].strip()
                    operator_cooldown = _cooldown_operator_after_contract_closeout(
                        failed_operator,
                        terminal_operator_assignment,
                    )
                if terminal_operator_assignment["dispatch_id"]:
                    release_lease(
                        terminal_operator_assignment["pane"],
                        terminal_operator_assignment["dispatch_id"],
                        "graph_eval_reconcile_failed_contract_closeout",
                    )
                _clear_eval_assignments(node)
                node["eval_retry_reason"] = terminal_operator_assignment["reason"]
                node["last_eval_closeout_failure"] = terminal_operator_assignment
                if operator_cooldown:
                    node["last_eval_operator_cooldown_after_closeout"] = operator_cooldown
                node["updated_at"] = _utc_now()
                repaired.append(
                    {
                        "node": node_id,
                        "pane": terminal_operator_assignment["pane"],
                        "dispatch_id": terminal_operator_assignment["dispatch_id"],
                        "status": status,
                        "reason": terminal_operator_assignment["reason"],
                        "operator_status": terminal_operator_assignment.get("operator_status"),
                        "result_json": terminal_operator_assignment.get("result_json"),
                        "operator_cooldown": operator_cooldown,
                    }
                )
                continue
            blocked_assignment = None
            for assignment in assignments:
                pane = str(assignment.get("pane") or "").strip()
                if not pane:
                    continue
                unavailable_reason = _pane_cooldown_reason(pane) or _pane_runtime_unavailable_reason(pane, _pane_title(pane)) or _pane_unavailable_reason(pane)
                if unavailable_reason:
                    blocked_assignment = {
                        "pane": pane,
                        "dispatch_id": str(assignment.get("dispatch_id") or "").strip(),
                        "reason": unavailable_reason,
                    }
                    break
            if blocked_assignment:
                if blocked_assignment["dispatch_id"]:
                    release_lease(
                        blocked_assignment["pane"],
                        blocked_assignment["dispatch_id"],
                        f"graph_eval_reconcile_unavailable:{blocked_assignment['reason']}",
                    )
                _clear_eval_assignments(node)
                node["eval_retry_reason"] = blocked_assignment["reason"]
                node["updated_at"] = _utc_now()
                repaired.append(
                    {
                        "node": node_id,
                        "pane": blocked_assignment["pane"],
                        "dispatch_id": blocked_assignment["dispatch_id"],
                        "status": status,
                        "reason": blocked_assignment["reason"],
                    }
                )
                continue
        if status not in {"pending", "queued", "blocked", "worker_blocked", ""}:
            continue
        instruction_file = _dispatch_file(sid, node_id)
        if not instruction_file.exists():
            continue
        ledger = _ledger_dispatch_for(sid, instruction_file)
        if not ledger:
            continue
        pane = str(ledger.get("pane") or "")
        dispatch_id = str(ledger.get("dispatch_id") or "")
        ack_file = HARNESS_DIR / "sprints" / "graph-acks" / f"{sid}.{node_id}-submit-ack.json"
        if not ack_file.exists():
            continue
        try:
            ack = json.loads(ack_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(ack.get("dispatch_id") or "") != dispatch_id:
            continue
        lease = read_lease(pane) if pane else None
        lease_live = bool(
            isinstance(lease, dict)
            and str(lease.get("dispatch_id") or "") == dispatch_id
            and str(lease.get("expires_at") or "") > _utc_now()
        )
        unavailable_reason = _pane_runtime_unavailable_reason(pane, _pane_title(pane)) or _pane_unavailable_reason(pane)
        if not lease_live or unavailable_reason:
            node.pop("assigned_to", None)
            node.pop("dispatch_id", None)
            node["dispatch_retry_reason"] = unavailable_reason or "stale_submit_ack_without_live_lease"
            node["updated_at"] = _utc_now()
            node["status"] = "pending"
            graph.setdefault("node_results", {}).pop(node_id, None)
            repaired.append(
                {
                    "node": node_id,
                    "pane": pane,
                    "dispatch_id": dispatch_id,
                    "status": "pending",
                    "reason": node["dispatch_retry_reason"],
                }
            )
            continue
        set_node_status(graph, node_id, "dispatched", pane=pane or None, dispatch_id=dispatch_id or None)
        repaired.append({"node": node_id, "pane": pane, "dispatch_id": dispatch_id, "reason": "submit_ack_exists"})
    return repaired


def _eval_dispatch_file(sid: str, node_id: str) -> Path:
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-eval-dispatch.md"


def _eval_md_file(sid: str, node_id: str) -> Path:
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-eval.md"


def _eval_json_file(sid: str, node_id: str) -> Path:
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-eval.json"


def _eval_peer_md_file(sid: str, node_id: str, index: int) -> Path:
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-eval-q{index}.md"


def _eval_peer_json_file(sid: str, node_id: str, index: int) -> Path:
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-eval-q{index}.json"


def _eval_dispatch_member_file(sid: str, node_id: str, index: int) -> Path:
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-eval-dispatch-q{index}.md"


def _verdict_from_eval_md(eval_md: Path) -> str:
    try:
        text = eval_md.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    match = re.search(r"(?ims)^##\s+Verdict\s*\n+\s*(PASS|FAIL|FAILED|OK)\b", text)
    if not match:
        return ""
    raw = match.group(1).strip().upper()
    if raw in {"PASS", "OK"}:
        return "PASS"
    if raw in {"FAIL", "FAILED"}:
        return "FAIL"
    return ""


def _eval_md_is_substantive(eval_md: Path) -> bool:
    """True iff the evaluator Markdown reads as a genuine independent verification
    rather than a bare verdict stamp. A real node eval re-runs checks and records
    evidence across multiple sections (observed genuine evals are ~7-9KB / 11-12
    sections); a rubber-stamp is a few lines. Thresholds are set far below genuine
    sizes so this only rejects stamps, never real evals."""
    try:
        text = eval_md.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if len(text.strip()) < 600:
        return False
    section_count = len(re.findall(r"(?im)^##\s+\S", text))
    has_evidence = bool(re.search(r"(?i)\b(evidence|checked|acceptance|re-?ran|re-?run|verif|smoke)", text))
    return section_count >= 3 or has_evidence


def _maybe_backfill_eval_json_from_md(sid: str, node_id: str) -> Path | None:
    """Recover evaluator sidecar JSON when the Markdown verdict is explicit.

    This is intentionally narrow: it only runs for graph node eval sidecars,
    requires a `## Verdict` section with PASS/FAIL, and records that the JSON was
    derived from evaluator Markdown. It does not invent a verdict, and (trust gate)
    it never mints a PASS sidecar from a non-substantive eval .md.
    """
    eval_json = _eval_json_file(sid, node_id)
    if eval_json.exists():
        return eval_json
    eval_md = _eval_md_file(sid, node_id)
    if not eval_md.exists():
        return None
    verdict = _verdict_from_eval_md(eval_md)
    if verdict not in {"PASS", "FAIL"}:
        return None
    # Trust gate (no hollow passes): a PASS must be backed by a substantive
    # independent eval. A thin/rubber-stamp PASS .md is refused here so the node
    # stays unverified and is re-evaluated rather than silently marked passed.
    # FAIL is always honored (fail-safe).
    if verdict == "PASS" and not _eval_md_is_substantive(eval_md):
        try:
            _append_dispatch_ledger(
                "eval_backfill_refused_thin_pass", sid, "", "",
                {"node": node_id, "eval_md": str(eval_md)},
            )
        except Exception:
            pass
        return None
    payload = {
        "verdict": verdict,
        "status": "passed" if verdict == "PASS" else "failed",
        "node_id": node_id,
        "sprint_id": sid,
        "eval_md": str(eval_md),
        "source": "backfilled_from_eval_md",
        "created_at": _utc_now(),
    }
    try:
        eval_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        return None
    return eval_json


def _node_eval_assignments(node: dict[str, Any]) -> list[dict[str, Any]]:
    raw = node.get("eval_assignments")
    if isinstance(raw, list):
        normalized: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            pane = str(item.get("pane") or "").strip()
            dispatch_id = str(item.get("dispatch_id") or "").strip()
            if not pane or not dispatch_id:
                continue
            normalized.append(
                {
                    "pane": pane,
                    "dispatch_id": dispatch_id,
                    "role": str(item.get("role") or "secondary"),
                    "eval_md_path": str(item.get("eval_md_path") or ""),
                    "eval_json_path": str(item.get("eval_json_path") or ""),
                }
            )
        if normalized:
            return normalized
    pane = str(node.get("eval_assigned_to") or "").strip()
    dispatch_id = str(node.get("eval_dispatch_id") or "").strip()
    if pane and dispatch_id:
        return [
            {
                "pane": pane,
                "dispatch_id": dispatch_id,
                "role": "primary",
                "eval_md_path": str(node.get("eval_md_path") or ""),
                "eval_json_path": str(node.get("eval_json") or ""),
            }
        ]
    return []


def _read_json_file_safe(path: str | Path) -> dict[str, Any]:
    try:
        candidate = Path(path).expanduser()
        if not candidate.exists():
            return {}
        data = json.loads(candidate.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _node_proof_obligations(sid: str, node: dict[str, Any]) -> list[dict[str, Any]]:
    obligations = node.get("proof_obligations")
    if isinstance(obligations, list):
        return [item for item in obligations if isinstance(item, dict)]
    for key in ("capsule_plan_ir", "physical_plan_ir"):
        payload = node.get(key)
        if isinstance(payload, dict) and isinstance(payload.get("proof_obligations"), list):
            return [item for item in payload.get("proof_obligations", []) if isinstance(item, dict)]
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    for key in ("capsule_plan_ir", "physical_plan_ir"):
        path = artifacts.get(key)
        if not path:
            continue
        data = _read_json_file_safe(path)
        if isinstance(data.get("proof_obligations"), list):
            return [item for item in data.get("proof_obligations", []) if isinstance(item, dict)]
    return []


# --- Deterministic secret-leak guard + resource binding (general builder/operator path) ---
# gitleaks is the release/CI/git-hook scanner but is NOT on the runtime PATH; mirror the
# canonical built-in pattern set from runtime_interfaces.RuntimePolicy.secret_patterns.
# (Weaker coverage than gitleaks — keyword + a few high-signal provider tokens — but real
# and deterministic, unlike the previous LLM "guard_decision_written" narrative attestation.)
_SECRET_SCAN_PATTERNS = [
    r"(?i)api[_-]?key\s*[=:]\s*\S+",
    r"(?i)token\s*[=:]\s*\S{8,}",
    r"(?i)password\s*[=:]\s*\S+",
    r"(?i)secret\s*[=:]\s*\S+",
    r"(?i)credential\s*[=:]\s*\S+",
    r"(?i)auth[_-]?token\s*[=:]\s*\S+",
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[0-9a-zA-Z]{36}",
    r"sk-[0-9a-zA-Z]{20,}",
]
_GUARD_SCAN_MAX_FILES = 64
_GUARD_SCAN_MAX_BYTES = 512 * 1024


def _node_sidecar_file(sid: str, node_id: str, kind: str) -> Path | None:
    """Return the existing guard/resource sidecar for a node, or None.

    Accepts both underscore and dash filename spellings ({sid}.{node}-guard_decision.json
    / -guard-decision.json) for parity with the tools/ dispatcher copy.
    """
    nid = _safe_node_id(node_id)
    suffixes = [".md"] if kind == "bridged_artifact" else [".json"]
    for suffix in suffixes:
        for cand in (
            SPRINTS_DIR / f"{sid}.{nid}-{kind}{suffix}",
            SPRINTS_DIR / f"{sid}.{nid}-{kind.replace('_', '-')}{suffix}",
        ):
            if cand.exists():
                return cand
    return None


def _expected_node_sidecar_file(sid: str, node_id: str, kind: str) -> Path:
    suffix = ".md" if kind == "bridged_artifact" else ".json"
    return SPRINTS_DIR / f"{sid}.{_safe_node_id(node_id)}-{kind}{suffix}"


def _resolve_write_scope_paths(node: dict[str, Any]) -> list[Path]:
    """Resolve a node's write_scope entries to existing filesystem paths, scoped to known roots."""
    roots = [HARNESS_DIR, HARNESS_DIR.parent, SPRINTS_DIR, Path.cwd()]
    resolved: list[Path] = []
    for entry in (node.get("write_scope") or []):
        rel = str(entry or "").strip()
        if not rel:
            continue
        cand = Path(rel).expanduser()
        if cand.is_absolute():
            if cand.exists():
                resolved.append(cand)
            continue
        for root in roots:
            probe = root / rel
            if probe.exists():
                resolved.append(probe)
                break
    return resolved


def _collect_guard_scan_targets(sid: str, node: dict[str, Any]) -> list[Path]:
    """Scan targets = the node's OWN outputs only (handoff, patch.diff, write_scope files).

    Deliberately scoped — never the whole repo / unrelated files.
    """
    node_id = str(node.get("id") or "")
    targets: list[Path] = []
    handoff = _existing_node_handoff(sid, node, {"nodes": [node]}) or _handoff_file(sid, node_id)
    if handoff and Path(handoff).exists():
        targets.append(Path(handoff))
    patch = SPRINTS_DIR / f"{sid}.patch.diff"
    if patch.exists():
        targets.append(patch)
    for path in _resolve_write_scope_paths(node):
        if path.is_dir():
            for sub in sorted(path.rglob("*")):
                if sub.is_file():
                    targets.append(sub)
        elif path.is_file():
            targets.append(path)
    seen: set[str] = set()
    bounded: list[Path] = []
    for target in targets:
        key = str(target)
        if key in seen:
            continue
        seen.add(key)
        bounded.append(target)
        if len(bounded) >= _GUARD_SCAN_MAX_FILES:
            break
    return bounded


def _scan_paths_for_secrets(paths: list[Path]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for path in paths:
        try:
            raw = path.read_bytes()[:_GUARD_SCAN_MAX_BYTES]
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        for pattern in _SECRET_SCAN_PATTERNS:
            found = re.search(pattern, text)
            if found:
                snippet = found.group(0)
                redacted = (snippet[:6] + "...[REDACTED]") if len(snippet) > 6 else "[REDACTED]"
                matches.append({"path": str(path), "pattern": pattern, "match_redacted": redacted})
    return matches


def _emit_guard_resource_sidecars(sid: str, node: dict[str, Any]) -> dict[str, Any]:
    """Deterministic guard (secret scan) + resource binding for the general builder/operator path.

    Replaces the bespoke understand_anything S1 closeout (which hardcoded node S1 and wrote a
    constant "allow"). Scans the node's own outputs for secrets and writes:
      {sid}.{node}-guard_decision.json  -> {decision: allow|block, matches, scanned_paths, detector}
      {sid}.{node}-resource_binding.json -> {write_scope, scanned_paths, in_scope, bound}
    Returns the guard decision dict. Idempotent (re-scans + overwrites on each node-verdict).
    """
    node_id = str(node.get("id") or "")
    nid = _safe_node_id(node_id)
    targets = _collect_guard_scan_targets(sid, node)
    scanned = [str(t) for t in targets]
    matches = _scan_paths_for_secrets(targets)
    guard = {
        "node_id": node_id,
        "decision": "block" if matches else "allow",
        "detector": "builtin_secret_patterns",
        "matches": matches,
        "scanned_paths": scanned,
        "checked_at": _utc_now(),
    }
    resource = {
        "node_id": node_id,
        "resource": "resource.repo-workspace",
        "workspace_root": str(HARNESS_DIR),
        "write_scope": [str(x) for x in (node.get("write_scope") or [])],
        "scanned_paths": scanned,
        "in_scope": True,
        "bound": True,
        "checked_at": _utc_now(),
    }
    try:
        (SPRINTS_DIR / f"{sid}.{nid}-guard_decision.json").write_text(
            json.dumps(guard, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (SPRINTS_DIR / f"{sid}.{nid}-resource_binding.json").write_text(
            json.dumps(resource, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    return guard


def _proof_obligations_require_field(sid: str, node: dict[str, Any], field: str) -> bool:
    for obligation in _node_proof_obligations(sid, node):
        if str(obligation.get("field") or "") == field:
            return True
        requirement = str(obligation.get("requirement") or "")
        if field == "guard_decision" and requirement in {"check.guard_decision_written", "guard_decision exists"}:
            return True
        if field == "resource_binding" and requirement in {"check.resource_binding_written", "resource_binding exists"}:
            return True
        if field == "bridged_artifact" and requirement in {
            "check.adapter_output_written",
            "adapter output exists",
            "type_mismatch_bridge",
        }:
            return True
    return False


def _emit_bridged_artifact_sidecar(sid: str, node: dict[str, Any]) -> Path | None:
    if not _proof_obligations_require_field(sid, node, "bridged_artifact"):
        return None
    node_id = str(node.get("id") or "")
    path = _expected_node_sidecar_file(sid, node_id, "bridged_artifact")
    obligations = _node_proof_obligations(sid, node)
    source_artifacts: list[str] = []
    missing_required_inputs: list[str] = []
    target_stage_ids: list[str] = []
    for obligation in obligations:
        if str(obligation.get("requirement") or "") != "type_mismatch_bridge":
            continue
        source_artifacts.extend(str(item) for item in (obligation.get("source_artifacts") or []) if str(item))
        missing_required_inputs.extend(str(item) for item in (obligation.get("missing_required_inputs") or []) if str(item))
        if obligation.get("target_stage_id"):
            target_stage_ids.append(str(obligation.get("target_stage_id")))

    def _line_items(items: list[str]) -> str:
        unique = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return "\n".join(f"- `{item}`" for item in unique) if unique else "- `N/A`"

    handoff = _existing_node_handoff(sid, node, {"nodes": [node]}) or _handoff_file(sid, node_id)
    candidate_files: list[tuple[str, Path]] = [
        ("handoff_md", Path(handoff)),
        ("patch_diff", SPRINTS_DIR / f"{sid}.patch.diff"),
        ("guard_decision", _expected_node_sidecar_file(sid, node_id, "guard_decision")),
        ("resource_binding", _expected_node_sidecar_file(sid, node_id, "resource_binding")),
    ]
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    for key in ("capsule_plan_ir", "physical_plan_ir", "patch_diff", "test_report", "test_log"):
        value = artifacts.get(key)
        if isinstance(value, str) and value.strip():
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = SPRINTS_DIR / value
            candidate_files.append((key, candidate))

    existing_files = "\n".join(
        f"- `{label}`: `{candidate}`"
        for label, candidate in candidate_files
        if candidate.exists()
    ) or "- `N/A`"
    content = f"""# Bridged Artifact - {sid} / {node_id}

Generated by: `graph_node_dispatcher`
Generated at: `{_utc_now()}`

## Purpose

This deterministic sidecar bridges capsule JSON/proof metadata into a Markdown artifact for evaluator review.

## Node

- Goal: {node.get("goal", "N/A")}
- Gate: `{node.get("gate", "N/A")}`
- Type: `{node.get("type", "N/A")}`

## Adapter Contract

Target stages:
{_line_items(target_stage_ids)}

Missing required inputs bridged:
{_line_items(missing_required_inputs)}

Source artifacts:
{_line_items(source_artifacts)}

## Verifier-Visible Files

{existing_files}
"""
    try:
        path.write_text(content, encoding="utf-8")
        return path
    except Exception:
        return None


def _emit_node_proof_sidecars(sid: str, node: dict[str, Any]) -> dict[str, str]:
    emitted: dict[str, str] = {}
    guard = _emit_guard_resource_sidecars(sid, node)
    if guard:
        emitted["guard_decision"] = str(_expected_node_sidecar_file(sid, str(node.get("id") or ""), "guard_decision"))
        emitted["resource_binding"] = str(_expected_node_sidecar_file(sid, str(node.get("id") or ""), "resource_binding"))
    bridged = _emit_bridged_artifact_sidecar(sid, node)
    if bridged:
        emitted["bridged_artifact"] = str(bridged)
    return emitted


def _proof_support_artifacts_block(sid: str, node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    entries: list[tuple[str, Path]] = []
    for kind in ("guard_decision", "resource_binding", "bridged_artifact"):
        if _proof_obligations_require_field(sid, node, kind):
            existing = _node_sidecar_file(sid, node_id, kind)
            entries.append((kind, existing or _expected_node_sidecar_file(sid, node_id, kind)))
    if not entries:
        return "- `N/A`"
    lines = []
    for kind, path in entries:
        state = "present" if path.exists() else "missing"
        lines.append(f"- `{kind}`: `{path}` ({state})")
    lines.append("")
    lines.append("Read these sidecars before failing guard/resource/adapter proof obligations.")
    return "\n".join(lines)


def _proof_artifact_presence(sid: str, node: dict[str, Any], eval_json: str | Path = "") -> dict[str, bool]:
    node_id = str(node.get("id") or "")
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    handoff = _existing_node_handoff(sid, node, {"nodes": [node]})
    eval_json_path = Path(eval_json).expanduser() if str(eval_json) else _eval_json_file(sid, node_id)
    eval_md_path = _eval_md_file(sid, node_id)
    patch_path = Path(str(artifacts.get("patch_diff") or "")).expanduser() if artifacts.get("patch_diff") else Path("")
    test_path = Path(str(artifacts.get("test_log") or artifacts.get("test_report") or "")).expanduser() if (artifacts.get("test_log") or artifacts.get("test_report")) else Path("")
    presence = {
        "handoff_md": bool(handoff and Path(handoff).exists()),
        "eval_json": bool(eval_json_path.exists()),
        "eval_md": bool(eval_md_path.exists()),
        "patch_diff": bool(str(patch_path) not in {"", "."} and patch_path.exists()) or bool(handoff and node.get("write_scope")),
        "test_log": bool(str(test_path) not in {"", "."} and test_path.exists()),
    }
    # Deterministic guard/resource sidecars (lib/ previously had no lookup — tools/ did).
    # guard_decision counts as present ONLY when the real scan returned decision == "allow";
    # a "block" (secret found) leaves it absent so the proof gate fails the node.
    guard_sidecar = _node_sidecar_file(sid, node_id, "guard_decision")
    guard_payload = _read_json_file_safe(guard_sidecar) if guard_sidecar else {}
    presence["guard_decision"] = bool(guard_sidecar) and str(guard_payload.get("decision") or "").lower() == "allow"
    presence["resource_binding"] = _node_sidecar_file(sid, node_id, "resource_binding") is not None
    presence["bridged_artifact"] = _node_sidecar_file(sid, node_id, "bridged_artifact") is not None
    for artifact_key, artifact_value in artifacts.items():
        if artifact_key in presence:
            continue
        if isinstance(artifact_value, str) and artifact_value.strip():
            candidate = Path(artifact_value).expanduser()
            if not candidate.is_absolute():
                candidate = SPRINTS_DIR / artifact_value
            presence[artifact_key] = candidate.exists()
    operator_results_root = HARNESS_DIR / "run" / "operator-results"
    if operator_results_root.exists():
        for result_json in operator_results_root.glob("*/*/result.json"):
            data = _read_json_file_safe(result_json)
            if str(data.get("sprint_id") or "") != sid or str(data.get("node_id") or "") != node_id:
                continue
            result_dir = result_json.parent
            skill_dispatch_result = result_dir / "skill-dispatch-result.json"
            skill_dispatch_prompt = result_dir / "skill-dispatch-pane-prompt.md"
            skill_dispatch_selection = result_dir / "skill-dispatch-selection-proof.json"
            skill_dispatch_contract = result_dir / "skill-dispatch-bridge-contract.json"
            skill_contract_payload = _read_json_file_safe(skill_dispatch_contract)
            command_protocol = skill_contract_payload.get("command_protocol") if isinstance(skill_contract_payload.get("command_protocol"), dict) else {}
            workflow_contract = skill_contract_payload.get("workflow_contract") if isinstance(skill_contract_payload.get("workflow_contract"), dict) else {}
            semantic_proof = result_dir / "understand-anything-semantic-proof.json"
            semantic_request = result_dir / "understand-anything-semantic-phase-request.json"
            dispatch_result = result_dir / "understand-anything-result.json"
            semantic_proof_payload = _read_json_file_safe(semantic_proof)
            dispatch_payload = _read_json_file_safe(dispatch_result)
            local_dispatch = dispatch_payload.get("dispatch_result") if isinstance(dispatch_payload.get("dispatch_result"), dict) else {}
            presence.update(
                {
                    "skill_dispatch_result": skill_dispatch_result.exists(),
                    "check.skill_dispatch_result_written": skill_dispatch_result.exists(),
                    "check.skill_dispatch_prompt_written": skill_dispatch_prompt.exists(),
                    "check.skill_dispatch_selection_proof_written": skill_dispatch_selection.exists(),
                    "check.skill_dispatch_contract_written": skill_dispatch_contract.exists(),
                    "check.skill_dispatch_command_protocol_declared": bool(command_protocol.get("mode")),
                    "check.skill_dispatch_workflow_phases_declared": bool(workflow_contract.get("phases")),
                    "check.skill_dispatch_delivery_expectation_declared": bool(workflow_contract.get("delivery_expectation")),
                    "understand_anything_dispatch_result": dispatch_result.exists(),
                    "check.understand_anything_dispatch_result_written": dispatch_result.exists(),
                    "check.semantic_proof_artifact_written": semantic_proof.exists(),
                    "check.semantic_phase_request_written": semantic_request.exists(),
                    "check.chunk_manifest_written": Path(str(local_dispatch.get("manifest_path") or "")).exists(),
                    "check.resume_state_written": Path(str(local_dispatch.get("resume_state_path") or "")).exists(),
                    "check.meta_written": Path(str(local_dispatch.get("meta_path") or "")).exists(),
                    "check.semantic_backend_thunderomlx_declared": (
                        semantic_proof_payload.get("semantic_backend_declared") == "ThunderOMLX"
                    ),
                }
            )
            break
    return presence


def _evaluate_proof_obligations(sid: str, node: dict[str, Any], eval_json: str | Path = "") -> dict[str, Any]:
    obligations = _node_proof_obligations(sid, node)
    if not obligations:
        return {"required": False, "ok": True, "checked": [], "missing": []}

    eval_data = _read_json_file_safe(eval_json or _eval_json_file(sid, str(node.get("id") or "")))
    proof_checks = eval_data.get("proof_checks") if isinstance(eval_data.get("proof_checks"), dict) else {}
    presence = _proof_artifact_presence(sid, node, eval_json=eval_json)
    checked: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for obligation in obligations:
        kind = str(obligation.get("kind") or "")
        requirement = str(obligation.get("requirement") or "")
        satisfied = True
        reason = ""
        if kind == "external_verifier":
            satisfied = presence["eval_json"]
            reason = "eval_json_missing" if not satisfied else ""
        elif kind == "self_check":
            if proof_checks:
                value = proof_checks.get(requirement)
                satisfied = value is not False
                reason = "self_check_failed" if not satisfied else ""
            else:
                if requirement in presence:
                    satisfied = bool(presence.get(requirement))
                    reason = "self_check_missing_artifact" if not satisfied else ""
                else:
                    satisfied = True
        elif kind in {"pass_condition", "postcondition"}:
            field = str(obligation.get("field") or "")
            if "handoff" in requirement or field == "handoff_md":
                satisfied = presence["handoff_md"]
                reason = "handoff_missing" if not satisfied else ""
            elif "patch_diff" in requirement or field == "patch_diff":
                satisfied = presence["patch_diff"]
                reason = "patch_diff_missing" if not satisfied else ""
            elif "test" in requirement or field in {"test_log", "test_report"}:
                satisfied = presence["test_log"]
                reason = "test_log_missing" if not satisfied else ""
            elif "eval" in requirement or field == "eval_json":
                satisfied = presence["eval_json"]
                reason = "eval_json_missing" if not satisfied else ""
            elif requirement == "output_present" and field:
                satisfied = presence.get(field, False)
                reason = f"{field}_missing" if not satisfied else ""
                if not satisfied and field == "guard_decision":
                    _gf = _node_sidecar_file(sid, str(node.get("id") or ""), "guard_decision")
                    _gd = _read_json_file_safe(_gf) if _gf else {}
                    if str(_gd.get("decision") or "").lower() == "block":
                        reason = "secret_leak_blocked"
        elif kind == "adapter_contract":
            satisfied = True
        checked.append(
            {
                "kind": kind,
                "requirement": requirement,
                "field": obligation.get("field"),
                "satisfied": bool(satisfied),
                "reason": reason,
            }
        )
        if not satisfied:
            missing.append(
                {
                    "kind": kind,
                    "requirement": requirement,
                    "field": obligation.get("field"),
                    "reason": reason,
                }
            )

    return {
        "required": True,
        "ok": not missing,
        "checked": checked,
        "missing": missing,
        "artifact_presence": presence,
    }


def _proof_checks_template(obligations: list[dict[str, Any]]) -> dict[str, Any]:
    template: dict[str, Any] = {}
    for obligation in obligations:
        if str(obligation.get("kind") or "") != "self_check":
            continue
        requirement = str(obligation.get("requirement") or "").strip()
        if requirement:
            template[requirement] = None
    return template


def _proof_obligations_block(obligations: list[dict[str, Any]]) -> str:
    if not obligations:
        return "- `N/A`"
    lines = []
    for item in obligations:
        kind = str(item.get("kind") or "unknown")
        requirement = str(item.get("requirement") or "N/A")
        field = str(item.get("field") or "").strip()
        suffix = f" | field=`{field}`" if field else ""
        lines.append(f"- `{kind}`: `{requirement}`{suffix}")
    return "\n".join(lines)


def _store_eval_assignments(node: dict[str, Any], assignments: list[dict[str, Any]], dispatched_at: str) -> None:
    normalized = [
        {
            "pane": str(item.get("pane") or ""),
            "dispatch_id": str(item.get("dispatch_id") or ""),
            "role": str(item.get("role") or "secondary"),
            "eval_md_path": str(item.get("eval_md_path") or ""),
            "eval_json_path": str(item.get("eval_json_path") or ""),
        }
        for item in assignments
        if str(item.get("pane") or "") and str(item.get("dispatch_id") or "")
    ]
    node["eval_assignments"] = normalized
    primary = next((item for item in normalized if item.get("role") == "primary"), normalized[0] if normalized else {})
    node["eval_assigned_to"] = str(primary.get("pane") or "")
    node["eval_dispatch_id"] = str(primary.get("dispatch_id") or "")
    node["eval_dispatched_at"] = dispatched_at


def _clear_eval_assignments(node: dict[str, Any]) -> None:
    node.pop("eval_assignments", None)
    node.pop("eval_assigned_to", None)
    node.pop("eval_dispatch_id", None)
    node.pop("eval_dispatched_at", None)


def _queue_file(sprint_id: str) -> Path:
    qdir = HARNESS_DIR / "run" / "queue"
    qdir.mkdir(parents=True, exist_ok=True)
    return qdir / f"{sprint_id}.jsonl"


def _is_graph_queue_item(item: dict[str, Any]) -> bool:
    intent = item.get("intent", "")
    return "graph_node|" in intent or bool((item.get("payload") or {}).get("node"))


def _pop_graph_queue_item(sprint_id: str) -> dict[str, Any] | None:
    """Pop only graph-node items so legacy PM/planner queue entries do not block DAG dispatch."""
    qf = _queue_file(sprint_id)
    if not qf.exists():
        return None
    lock_path = str(qf) + ".lock"
    with open(lock_path, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            items: list[dict[str, Any]] = []
            for line in qf.read_text().splitlines():
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
            pending = sorted(
                [item for item in items if not item.get("consumed") and _is_graph_queue_item(item)],
                key=lambda x: (-x.get("priority", 0), x.get("enqueued_at", "")),
            )
            if not pending:
                return None
            target = pending[0]
            target["consumed"] = True
            target["consumed_at"] = _utc_now()
            for idx, item in enumerate(items):
                if item.get("id") == target.get("id"):
                    items[idx] = target
                    break
            tmp = str(qf) + ".tmp"
            with open(tmp, "w") as f:
                for item in items:
                    f.write(json.dumps(item) + "\n")
            os.replace(tmp, str(qf))
            return target
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
            # The lock is advisory and fd-scoped. Leaving an empty sidecar
            # behind makes patrols treat a healthy queue read as a stale lock.
            try:
                os.unlink(lock_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _node_by_id(graph: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for node in graph.get("nodes", []):
        if node.get("id") == node_id:
            return node
    return None


def _graph_node_runtime_state(graph_path: str, node_id: str) -> dict[str, Any]:
    try:
        graph = load_graph(graph_path)
        node = _node_by_id(graph, node_id) or {}
        result = (graph.get("node_results") or {}).get(node_id) or {}
        status = str(node_status(graph, node_id) or "pending").lower()
        active_statuses = {"assigned", "dispatched", "in_progress", "running"}
        return {
            "ok": True,
            "status": status,
            "dispatch_id": (node.get("dispatch_id") or result.get("dispatch_id") or "") if status in active_statuses else "",
            "assigned_to": (node.get("assigned_to") or result.get("assigned_to") or "") if status in active_statuses else "",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "status": ""}


def _mark_graph_node(graph_path: str, node_id: str, status: str,
                     pane: str | None = None, dispatch_id: str | None = None,
                     clear_assignment: bool = False) -> bool:
    try:
        graph = load_graph(graph_path)
        for node in graph.get("nodes", []):
            if node.get("id") != node_id:
                continue
            updated_at = _utc_now()
            node["status"] = status
            node["updated_at"] = updated_at
            results = graph.setdefault("node_results", {})
            if status in {"pending", "queued", "blocked", ""}:
                results.pop(node_id, None)
            else:
                results[node_id] = {"status": status, "updated_at": updated_at}
            clear_builder_claim = clear_assignment or status in {"reviewing", "failed_review", "passed", "failed", "skipped"}
            if clear_builder_claim:
                node.pop("assigned_to", None)
                node.pop("dispatch_id", None)
                if isinstance(results.get(node_id), dict):
                    results[node_id].pop("assigned_to", None)
                    results[node_id].pop("dispatch_id", None)
            else:
                if pane:
                    node["assigned_to"] = pane
                    if isinstance(results.get(node_id), dict):
                        results[node_id]["assigned_to"] = pane
                if dispatch_id:
                    node["dispatch_id"] = dispatch_id
                    if isinstance(results.get(node_id), dict):
                        results[node_id]["dispatch_id"] = dispatch_id
            save_graph(graph_path, graph)
            return True
    except Exception:
        return False
    return False


def _mark_graph_node_compat(
    graph_path: str,
    node_id: str,
    status: str,
    *,
    pane: str | None = None,
    dispatch_id: str | None = None,
    clear_assignment: bool = False,
) -> bool:
    try:
        return _mark_graph_node(
            graph_path,
            node_id,
            status,
            pane=pane,
            dispatch_id=dispatch_id,
            clear_assignment=clear_assignment,
        )
    except TypeError:
        return _mark_graph_node(  # type: ignore[misc]
            graph_path,
            node_id,
            status,
            clear_assignment=clear_assignment,
        )

def _save_graph_preserving_runtime_progress(graph_path: str, graph: dict[str, Any]) -> None:
    """Avoid stale dispatcher saves downgrading nodes updated by another loop."""
    try:
        current = load_graph(graph_path)
        current_nodes = {
            str(node.get("id") or ""): node
            for node in current.get("nodes", [])
            if str(node.get("id") or "")
        }
        stale_nodes = {
            str(node.get("id") or ""): node
            for node in graph.get("nodes", [])
            if str(node.get("id") or "")
        }
        protected_statuses = {
            "dispatched",
            "in_progress",
            "running",
            "reviewing",
            "failed_review",
            "passed",
            "failed",
            "skipped",
            "cancelled",
            "skipped_parent_passed",
        }
        overwriteable_statuses = {"", "pending", "queued", "blocked", "worker_blocked", "assigned"}
        current_results = current.get("node_results") if isinstance(current.get("node_results"), dict) else {}
        for node_id, current_node in current_nodes.items():
            stale_node = stale_nodes.get(node_id)
            if not stale_node:
                continue
            current_status = str(node_status(current, node_id) or "").strip().lower()
            stale_status = str(node_status(graph, node_id) or "").strip().lower()
            closeout_retry = str(stale_node.get("dispatch_retry_reason") or "").strip().lower()
            closeout_failure = stale_node.get("last_operator_closeout_failure")
            closeout_is_authoritative = (
                stale_status == "pending"
                and current_status in protected_statuses
                and closeout_retry in {"failed_contract_closeout", "operator_result_failed", "operator_result_error"}
                and isinstance(closeout_failure, dict)
            )
            if closeout_is_authoritative:
                continue
            if current_status not in protected_statuses or stale_status not in overwriteable_statuses:
                continue
            current_result = current_results.get(node_id) if isinstance(current_results.get(node_id), dict) else {}
            set_node_status(
                graph,
                node_id,
                current_status,
                pane=str(current_node.get("assigned_to") or current_result.get("assigned_to") or "") or None,
                dispatch_id=str(current_node.get("dispatch_id") or current_result.get("dispatch_id") or "") or None,
            )
    except Exception:
        pass
    save_graph(graph_path, graph)


def _ensure_execution_plan_payload(
    payload: dict[str, Any],
    *,
    graph_path: str,
    sid: str,
    node: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("capsule_plan_ir") and payload.get("physical_plan_ir"):
        return payload
    try:
        from apo_plan_compiler import compile_execution_plan_for_node, materialize_execution_plan_artifacts  # noqa: WPS433

        compiled = compile_execution_plan_for_node(
            node,
            request_type=str(node.get("type") or ""),
            lane_hint="",
            registry_path=HARNESS_DIR / "config" / "capability-capsules.registry.yaml",
            operators_path=HARNESS_DIR / "config" / "physical-operators.json",
        )
        capsule_plan_ir = dict(compiled.get("capsule_plan") or {})
        physical_plan_ir = dict(compiled.get("physical_plan") or {})
        payload["logical_plan_node"] = dict(compiled.get("logical_plan_node") or {})
        payload["capsule_plan_ir"] = capsule_plan_ir
        payload["physical_plan_ir"] = physical_plan_ir
        payload["plan_artifacts"] = materialize_execution_plan_artifacts(
            sid,
            str(node.get("id") or ""),
            capsule_plan=capsule_plan_ir,
            physical_plan=physical_plan_ir,
            base_dir=SPRINTS_DIR,
        )
    except Exception:
        return payload
    return payload


def _node_repair_context_block(node: dict[str, Any]) -> str:
    context = node.get("repair_context")
    if not isinstance(context, dict) or not context:
        return ""

    attempt = context.get("attempt", "N/A")
    max_attempts = context.get("max_attempts", "N/A")
    summary = str(context.get("summary") or "").strip() or "N/A"
    failed_conditions = context.get("failed_conditions")
    condition_lines = _scope_lines(failed_conditions if isinstance(failed_conditions, list) else [])
    archived = context.get("archived_sidecars")
    archived_lines = _scope_lines(
        [f"{key}: {value}" for key, value in archived.items()]
        if isinstance(archived, dict)
        else []
    )

    error_lines: list[str] = []
    errors = context.get("errors")
    if isinstance(errors, list):
        for index, item in enumerate(errors[:6], start=1):
            if not isinstance(item, dict):
                continue
            cond = str(item.get("cond") or f"error-{index}")
            severity = str(item.get("severity") or "unknown")
            evidence = str(item.get("evidence") or "").strip()
            fix_hint = str(item.get("fix_hint") or "").strip()
            error_lines.append(f"- `{cond}` ({severity})")
            if evidence:
                error_lines.append(f"  Evidence: {evidence}")
            if fix_hint:
                error_lines.append(f"  Fix hint: {fix_hint}")
    if not error_lines:
        error_lines = ["- `N/A`"]
    error_text = "\n".join(error_lines)

    return f"""## Repair Context

This node previously failed evaluator review. Repair the existing node artifact using the evaluator feedback below, then write a fresh handoff for re-review.

- Repair Attempt: `{attempt}` / `{max_attempts}`
- Previous Verdict: `FAIL`
- Previous Summary: {summary}

### Failed Conditions

{condition_lines}

### Evaluator Errors

{error_text}

### Archived Previous Review Sidecars

{archived_lines}
"""


def build_dispatch_text(payload: dict[str, Any], pane: str) -> str:
    node = payload.get("node") or {}
    sid = payload.get("sprint_id") or payload.get("sid") or ""
    node_id = node.get("id") or payload.get("node_id") or _node_id_from_intent(payload.get("intent", ""))
    graph_path = payload.get("graph") or str(SPRINTS_DIR / f"{sid}.task_graph.json")
    dispatch_id = payload.get("dispatch_id", "")
    graph_for_policy: dict[str, Any] = {}
    try:
        graph_for_policy = load_graph(graph_path)
    except Exception:
        graph_for_policy = {"nodes": [node]}
    architecture_block = dispatch_policy_block(node, graph_for_policy) if dispatch_policy_block else "## Architecture Guard\n\n- unavailable"
    logical_plan_node = payload.get("logical_plan_node") if isinstance(payload.get("logical_plan_node"), dict) else {}
    capsule_plan_ir = payload.get("capsule_plan_ir") if isinstance(payload.get("capsule_plan_ir"), dict) else {}
    physical_plan_ir = payload.get("physical_plan_ir") if isinstance(payload.get("physical_plan_ir"), dict) else {}
    plan_artifacts = payload.get("plan_artifacts") if isinstance(payload.get("plan_artifacts"), dict) else {}
    if str(pane or "").startswith("operator-pool:"):
        physical_selected = str(
            payload.get("actual_operator_id")
            or "operator-pool selector (final operator recorded in dispatch event + node runstate)"
        )
    else:
        physical_selected = str(physical_plan_ir.get("selected_operator_id") or "N/A")
    logical_operator = str(
        logical_plan_node.get("logical_operator")
        or capsule_plan_ir.get("logical_operator")
        or node.get("logical_operator")
        or "N/A"
    )
    capsule_id = str(
        capsule_plan_ir.get("capability_capsule_id")
        or payload.get("capability_capsule_id")
        or node.get("capability_capsule_id")
        or "N/A"
    )
    stage_lines = _scope_lines(
        [
            f"{stage.get('stage_kind')}:{stage.get('capability_capsule_id')}"
            for stage in (capsule_plan_ir.get("stages") or [])
            if isinstance(stage, dict)
        ]
    )
    plan_artifact_lines = _scope_lines(
        [
            plan_artifacts.get("capsule_plan_ir_path", ""),
            plan_artifacts.get("physical_plan_ir_path", ""),
        ]
    )
    write_scope_preflight = _write_scope_preflight_block(str(sid), node)
    canonical_output_paths = _canonical_output_paths_block(node)
    repair_context_block = _node_repair_context_block(node)

    return f"""{STATE_READ_PREFLIGHT}
{DEFINITION_OF_DONE_POLICY}

# DAG Node Dispatch — {sid} / {node_id}

Sprint: `{sid}`
Node: `{node_id}`
Pane: `{pane}`
Dispatch ID: `{dispatch_id or "N/A"}`
Graph: `{graph_path}`

## Execution Plan

- Logical Operator: `{logical_operator}`
- Capability Capsule: `{capsule_id}`
- Selected Physical Operator: `{physical_selected}`

## Capsule Stages

{stage_lines}

## Plan Artifacts

{plan_artifact_lines}

## Goal

{node.get("goal", "N/A")}

## Required Skills

{_scope_lines(node.get("required_skills"))}

## Required Capabilities

{_scope_lines(node.get("required_capabilities"))}

## Read Scope

{_scope_lines(node.get("read_scope"))}

## Write Scope

{_scope_lines(node.get("write_scope"))}

{canonical_output_paths}

{write_scope_preflight}

{architecture_block}

{repair_context_block}

## Acceptance

{_acceptance_lines(node.get("acceptance"))}

## Rules

- 只做本节点，不接手其他 DAG node。
- 只允许修改 `Write Scope` 里的文件/目录；需要扩大范围时写入 handoff 的 `Scope Change Request`，不要直接扩大。
- 如果 `Write Scope` / `outputs` 包含 `harness/sprints/...` 或 `sprints/...`，必须写入上方 `Canonical Output Paths` 中的绝对路径；不要把 sprint artifact 只写到当前 builder worktree 的相对路径。
- 不要把 parent sprint 标成 passed。
- 不要等待用户确认；遇到阻塞先写清楚证据和最小修复建议。
- 不要停在“继续/要不要继续/等待 review”提示；只要本节点 acceptance 未完成，就自主继续执行。
- 完成后必须写 handoff 并把本节点标记为 `reviewing`；这是释放下游和 evaluator 的唯一闭环。

## Work Steps

1. 读取 graph 和合约：
   ```bash
   cat "{graph_path}"
   cat "{SPRINTS_DIR / f'{sid}.contract.md'}"
   ```

2. 按本节点 goal/acceptance 实现。

3. 运行本节点相关验证；把命令和结果写入 handoff。

4. 写节点 handoff：
   ```bash
   cat > "{SPRINTS_DIR / f'{sid}.{node_id}-handoff.md'}" <<'EOF'
   # Handoff — {sid} / {node_id}

   ## Summary

   ## Changed Files

   ## Verification Evidence

   ## Capability / KB Usage Evidence

   - 写明实际使用了 dispatch 中哪些 Solar capability / skill / KB context。
   - 如果未使用，写明原因；不要把“被注入”当成“已使用”。

   ## Scope Compliance

   ## Known Risks

   ## Not Done
   EOF
   ```

5. 将节点状态置为 reviewing，等待 evaluator：
   ```bash
   {HARNESS_DIR}/solar-harness.sh graph-scheduler mark --graph "{graph_path}" --node "{node_id}" --status reviewing --in-place
   ```
"""


def build_eval_dispatch_text(graph: dict[str, Any], graph_path: str, node: dict[str, Any], pane: str,
                             dispatch_id: str, *, evaluator_role: str = "primary",
                             evaluator_index: int = 1, evaluator_total: int = 1,
                             eval_md_override: Path | None = None,
                             eval_json_override: Path | None = None,
                             peer_eval_json_paths: list[str] | None = None,
                             canonical_eval_json_path: str = "",
                             canonical_eval_md_path: str = "") -> str:
    sid = str(graph.get("sprint_id") or Path(graph_path).stem.replace(".task_graph", ""))
    node_id = str(node.get("id") or "")
    proof_obligations = _node_proof_obligations(sid, node)
    proof_checks_template = _proof_checks_template(proof_obligations)
    proof_support_artifacts = _proof_support_artifacts_block(sid, node)
    evaluation_plan = node.get("evaluation_plan_runtime") or node.get("evaluation_plan")
    if not isinstance(evaluation_plan, dict) or not evaluation_plan:
        evaluation_plan = _plan_node_evaluation(graph, node)
    handoff = _existing_node_handoff(sid, node, graph) or _handoff_file(sid, node_id)
    handoff_candidates = "\n".join(f"- `{candidate}`" for candidate in _node_handoff_candidates(sid, node, graph))
    eval_md = eval_md_override or _eval_md_file(sid, node_id)
    eval_json = eval_json_override or _eval_json_file(sid, node_id)
    node_dispatch = _dispatch_file(sid, node_id)
    contract = SPRINTS_DIR / f"{sid}.contract.md"
    architecture_block = dispatch_policy_block(node, graph) if dispatch_policy_block else "## Architecture Guard\n\n- unavailable"
    research_quality_gate_instruction = _deepresearch_quality_gate_eval_instruction(node, eval_json)
    peer_eval_json_paths = peer_eval_json_paths or []
    canonical_eval_json_path = canonical_eval_json_path or str(_eval_json_file(sid, node_id))
    canonical_eval_md_path = canonical_eval_md_path or str(_eval_md_file(sid, node_id))
    peer_block = "\n".join(f"- `{path}`" for path in peer_eval_json_paths) if peer_eval_json_paths else "- `N/A`"
    verdict_step = f"""3. 提交节点 verdict。通过时会自动释放下游 ready node；失败时只阻塞依赖它的下游：
   ```bash
   {HARNESS_DIR}/solar-harness.sh graph-dispatch node-verdict --graph "{graph_path}" --node "{node_id}" --verdict pass --eval-json "{eval_json}"
   ```

   如果失败，改用：
   ```bash
   {HARNESS_DIR}/solar-harness.sh graph-dispatch node-verdict --graph "{graph_path}" --node "{node_id}" --verdict fail --eval-json "{eval_json}" --reason "写清楚失败原因"
   ```
""" if evaluator_role == "primary" else f"""3. 不要直接提交 node verdict。你是并行副评审，只负责产出 sidecar 评审结果：
   - Markdown sidecar: `{eval_md}`
   - JSON sidecar: `{eval_json}`
   - Canonical evaluator 负责最终合并并提交：`{canonical_eval_json_path}`
"""
    role_rules = """- 你是主评审（primary），负责读取所有副评审 sidecar 并合并成 canonical verdict。
- 对于 dual/committee 模式，若副评审 sidecar 尚未出现，先轮询等待这些文件；不要抢先在没有 peer evidence 的情况下提交 PASS。""" if evaluator_role == "primary" and evaluator_total > 1 else (
"""- 你是并行副评审（secondary），不要写 canonical eval.json，也不要直接调用 node-verdict。
- 专注给出独立证据与 verdict sidecar，供主评审合并。""" if evaluator_role != "primary" else "- 当前只有一个 evaluator；直接完成 canonical verdict。"
)

    return f"""{STATE_READ_PREFLIGHT}
{DEFINITION_OF_DONE_POLICY}

# DAG Node Evaluation Dispatch — {sid} / {node_id}

Sprint: `{sid}`
Node: `{node_id}`
Pane: `{pane}`
Dispatch ID: `{dispatch_id}`
Evaluator Role: `{evaluator_role}`
Evaluator Index: `{evaluator_index}/{evaluator_total}`
Graph: `{graph_path}`
Handoff: `{handoff}`

## Handoff Candidates

{handoff_candidates}

## Evaluation Scope

- 只评审本 DAG node：`{node_id}`。
- 不要评审 parent sprint。
- 不要把 parent sprint 标成 passed。
- 只根据 node goal / acceptance / write_scope / handoff evidence 给 verdict。
- {role_rules}

## Node Goal

{node.get("goal", "N/A")}

## Acceptance

{_acceptance_lines(node.get("acceptance"))}

## Required Capabilities

{_scope_lines(node.get("required_capabilities"))}

## Evaluation Plan

{_evaluation_plan_block(evaluation_plan)}

## Proof Obligations

{_proof_obligations_block(proof_obligations)}

## Proof Support Artifacts

{proof_support_artifacts}

## Write Scope

{_scope_lines(node.get("write_scope"))}

{architecture_block}

## Required Reads

```bash
cat "{graph_path}"
cat "{contract}"
cat "{node_dispatch}"
test -f "{handoff}" && cat "{handoff}"
solar-harness session evaluate "{sid}" --json
```

## Log-Native Evaluation Requirement

- 评审必须消费 append-only session log，不得只看最终 handoff 文件。
- 在 eval.md 的 `Evidence Checked` 中写入 `Session Log: solar-harness session evaluate used`。
- 如果 `session evaluate` 返回 errors/warnings，必须逐项解释是否阻塞本 node verdict。
- 必须检查 `Architecture Guard`：新能力是否为 package/plugin/skill/connector；如触碰 protected core，必须有 `core_patch_allowed=true`、rollback 和 P0 bugfix 证据，否则 FAIL。
- 涉及 online exploration 的 node 必须验证 >=2 个候选方向和 kill_criteria；否则 FAIL。
- 必须把 proof obligations 逐项回填到 eval artifact：
  - `proof_obligations`: 原样记录本 node 的 obligation 列表
  - `proof_checks`: 对 `self_check` 逐项填 `true/false`
  - `verification_results`: 记录 `checked_artifacts / missing_artifacts / proof_gate`
{research_quality_gate_instruction}

## Required Outputs

1. 写 Markdown 评审：
   ```bash
   cat > "{eval_md}" <<'EOF'
   # Node Evaluation — {sid} / {node_id}

   ## Verdict

   PASS 或 FAIL

   ## Evidence Checked

   ## Capability / KB Usage Evidence Checked

   - 检查 handoff 是否说明实际使用了哪些 capability / KB context。
   - 如果 eval PASS，必须说明这些能力证据是否支撑验收。

   ## Acceptance Result

   ## Proof Obligations

   - 逐项说明哪些 obligation 已满足，哪些未满足。

   ## Scope Compliance

   ## Architecture Guard Compliance

   ## Risks

   ## Required Fixes
   EOF
   ```

2. 写机器可读 JSON：
   ```bash
   cat > "{eval_json}" <<'EOF'
   {{
     "node_id": "{node_id}",
     "verdict": "PASS",
     "summary": "",
     "evaluation_plan": {json.dumps(evaluation_plan, ensure_ascii=False, indent=2)},
     "proof_obligations": {json.dumps(proof_obligations, ensure_ascii=False, indent=2)},
     "proof_checks": {json.dumps(proof_checks_template, ensure_ascii=False, indent=2)},
     "verification_results": {{
       "proof_gate": "PENDING",
       "checked_artifacts": [],
       "missing_artifacts": []
     }},
     "research_quality_gate": {{}},
     "checked_at": "{_utc_now()}",
     "eval_md_path": "{eval_md}"
    }}
    EOF
   ```

## Peer Evaluator Sidecars

{peer_block}

## Canonical Eval Outputs

- Markdown: `{canonical_eval_md_path}`
- JSON: `{canonical_eval_json_path}`

{verdict_step}
"""


def _pane_exists(pane: str) -> bool:
    try:
        return subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).returncode == 0
    except Exception:
        return False


def _pane_title(pane: str) -> str:
    try:
        return subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_title}"],
            text=True,
            capture_output=True,
            timeout=2,
        ).stdout.strip()
    except Exception:
        return ""


def _pane_title_matches_role(pane: str, title: str, role: str) -> bool:
    if os.environ.get("SOLAR_GRAPH_ALLOW_ANY_ROLE_PANE") == "1":
        return True
    title = title or _pane_title(pane)
    # Ignore trailing `| 状态:working/...:sprint-...pm-pane-...` metadata so a
    # sprint id containing `pm-pane` does not look like a PM role conflict.
    title = re.split(r"\s+\|\s+状态:", title or "", maxsplit=1)[0].strip()
    negative = re.compile(r"PM|产品经理|Planner|规划者|Builder|建设者|Evaluator|审判官", re.I)
    if role == "builder":
        if _pane_in_lab_session(pane) or _pane_in_multi_task_session(pane):
            return bool(re.search(r"Builder|建设者|lab-builder", title, re.I)) and not bool(
                re.search(r"PM|产品经理|Planner|规划者|Evaluator|审判官", title, re.I)
            )
        return False
    if role == "evaluator":
        # The designated cockpit evaluator pane is authoritative BY POSITION. Its idle
        # title ("...sprint 评估") lacks "审判官"/"Evaluator" — that title is only set
        # transiently during an active dispatch — so gating discovery on the title makes a
        # cold/idle evaluator undiscoverable, leaving only the (often unbacked) operator-pool
        # evaluator slot to be selected -> send_failed retry loop. The title regex below is
        # meant to reject OTHER panes, not to gate the one hardcoded evaluator pane.
        session = _current_harness_session()
        if pane == f"{session}:0.3":
            return True
        if not (
            pane == f"{session}:0.3"
            or _pane_in_lab_session(pane)
            or _pane_in_multi_task_session(pane)
            or pane.startswith(f"{session}:")
        ):
            return False
        non_role_title = re.sub(r"Evaluator|审判官", "", title, flags=re.I)
        return bool(re.search(r"Evaluator|审判官", title, re.I)) and not bool(
            negative.search(non_role_title)
        )
    return False


def _pane_execution_priority(pane: str) -> tuple[int, str]:
    session = _current_harness_session()
    if _pane_in_multi_task_session(pane):
        return (0, pane)
    if _pane_in_lab_session(pane):
        return (1, pane)
    if pane.startswith(f"{session}:"):
        return (2, pane)
    return (9, pane)


def _pane_evaluator_priority(pane: str, title: str = "") -> tuple[int, str]:
    """Prefer the canonical evaluator as primary, then evaluator-capable pool panes.

    Graph eval dispatch can run quorum/secondary reviews, but the canonical
    eval sidecar should stay anchored to the main Evaluator when it is
    available. Lab panes are capacity spillover, not the first choice.
    """
    session = _current_harness_session()
    if pane == f"{session}:0.3":
        return (0, pane)
    if re.search(r"Evaluator|审判官", title or _pane_title(pane), re.I):
        return (1, pane)
    if _pane_in_multi_task_session(pane):
        return (2, pane)
    if _pane_in_lab_session(pane):
        return (3, pane)
    if pane.startswith(f"{session}:"):
        return (4, pane)
    return (9, pane)


def _lab_builder_can_host_evaluator(pane: str, title: str) -> bool:
    """Allow idle lab builders to serve as evaluator spillover by default.

    The eval dispatch prompt fully specifies evaluator behavior and writes
    evaluator sidecars, so a clean lab Builder pane can safely act as a
    secondary/overflow evaluator. This closes the previous gap where the code
    supported multi-evaluator dispatch but only discovered one Evaluator pane.
    """
    if os.environ.get("SOLAR_GRAPH_ALLOW_LAB_BUILDER_EVALUATOR", "1") == "0":
        return False
    if not (_pane_in_lab_session(pane) or _pane_in_multi_task_session(pane)):
        return False
    normalized_title = re.split(r"\s+\|\s+状态:", title or "", maxsplit=1)[0].strip()
    if re.search(r"PM|产品经理|Planner|规划者", normalized_title, re.I):
        return False
    return bool(re.search(r"Builder|建设者|lab-builder", normalized_title, re.I))


def _pane_tail(pane: str, lines: int = 80) -> str:
    try:
        return subprocess.run(
            ["tmux", "capture-pane", "-pt", pane, "-S", f"-{lines}"],
            text=True,
            capture_output=True,
            timeout=2,
        ).stdout
    except Exception:
        return ""


def _pane_current_command(pane: str) -> str:
    try:
        return subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_current_command}"],
            text=True,
            capture_output=True,
            timeout=2,
        ).stdout.strip()
    except Exception:
        return ""


def _pane_root_pid(pane: str) -> int | None:
    try:
        raw = subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_pid}"],
            text=True,
            capture_output=True,
            timeout=2,
        ).stdout.strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _pane_has_codex_process(pane: str) -> bool:
    """Return true when a pane's process tree contains the Codex CLI.

    tmux reports `pane_current_command=bash` for panes launched through
    `pane-launcher.sh`, even while Codex is alive as a child process. Use the
    process tree instead of the foreground command alone for Codex liveness.
    """
    root_pid = _pane_root_pid(pane)
    if not root_pid:
        return False
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,comm=,args="],
            text=True,
            capture_output=True,
            timeout=3,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    children: dict[int, list[tuple[int, str, str]]] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        comm = parts[2]
        args = parts[3] if len(parts) > 3 else ""
        children.setdefault(ppid, []).append((pid, comm, args))
    stack = [root_pid]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for pid, comm, args in children.get(current, []):
            command = f"{comm} {args}"
            if comm == "codex" or re.search(r"(^|[/\s])codex($|\s)", command):
                return True
            stack.append(pid)
    return False


def _pane_has_codex_idle_composer(text: str) -> bool:
    """Return true for Codex's empty composer glyph.

    Codex shows a placeholder after `›`, so text following that glyph is not
    necessarily unsubmitted user input. During active turns the footer includes
    `esc to interrupt`, which keeps this from being treated as idle.
    """
    if "esc to interrupt" in text.lower():
        return False
    return "›" in text


def _pane_current_prompt_has_residue(text: str) -> bool:
    """Return true only when the visible current prompt has unsubmitted text.

    `capture-pane` includes prompt history. Searching the whole tail for
    `❯ text` makes an idle pane unavailable after any recent submitted command.
    Only inspect the final prompt line and stop at status/footer lines.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("⏵", "?", "────────────────", "Esc ", "esc ", "Tab ", "Press up ")):
            continue
        if stripped.startswith("❯"):
            remainder = stripped[1:].strip()
            return bool(remainder) and not remainder.startswith("Try ")
        return False
    return False


def _prompt_match_followed_by_idle_default_prompt(text: str, match: re.Match[str] | None) -> bool:
    """Return true when a prompt-looking match is stale scrollback.

    Claude Code often leaves old first-run confirmation prompts in tmux
    scrollback. If a later idle default prompt is visible, that old
    `Enter to confirm`/confirmation text must not make the pane unavailable.
    """
    if match is None:
        return False
    if prompt_match_is_stale:
        return bool(prompt_match_is_stale(text, match))
    after = text[match.end():]
    return bool(re.search(r"❯[\s\u00a0]+Try\s+\"", after)) or _tail_has_idle_prompt_footer(after)


def _tail_has_idle_prompt_footer(text: str) -> bool:
    """Return true when the visible tail already settled on an idle prompt.

    Older queued-message and confirmation overlays can remain in tmux scrollback
    even after Claude returns to a clean prompt/footer. Treating that history as
    live state strands otherwise idle panes.
    """
    if tail_has_idle_prompt_footer:
        return bool(tail_has_idle_prompt_footer(text))
    lines = [line.rstrip() for line in text.splitlines()]
    footer_prefixes = (
        "⏵",
        "●",
        "esc ",
        "Esc ",
        "Tab ",
        "Interrupt",
        "bypass permissions on",
        "accept edits on",
        "plan mode on",
    )
    saw_footer = False
    for line in reversed(lines[-12:]):
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if stripped.startswith("────────────────") or stripped.isdigit():
            continue
        if stripped.startswith("❯"):
            remainder = stripped[1:].strip()
            return remainder.startswith("Try ") or (not remainder and saw_footer)
        if lowered.startswith(footer_prefixes) or "tokens" in lowered or "/effort" in lowered:
            saw_footer = True
            continue
        return False
    return False


def _pane_prompt_residue_is_stale_scrollback(pane: str, text: str) -> bool:
    """Return true for old completed Claude output, not live editable input.

    In some panes `capture-pane` keeps the last completed Claude prompt visible
    after the process has returned to a shell. That prompt line is scrollback,
    but treating it as live input makes evaluator discovery report
    `no_available_evaluator` forever.
    """
    if not _pane_current_prompt_has_residue(text):
        return False
    command = _pane_current_command(pane).lower()
    if command not in {"bash", "zsh", "sh", "fish"}:
        return False
    return any(
        marker in text
        for marker in (
            "✻ Churned for",
            "✻ Cogitated for",
            "✻ Baked for",
            "✻ Brewed for",
            "✻ Cooked for",
            "✻ Sautéed for",
            "✻ Thought for",
            "✻ Worked for",
            "✻ Crunched for",
        )
    )


def _clear_pane_scrollback(pane: str) -> bool:
    """Fix #7b: drop a pane's tmux scrollback buffer to evict a stale, already-
    resolved rate-limit banner ("resets X") that would otherwise keep matching
    PANE_TUI_UNAVAILABLE_RE and wedge the pane out of dispatch forever (a /clear
    clears the conversation, NOT the terminal scrollback). Does not touch the
    Claude turn/conversation — only the terminal backbuffer."""
    try:
        subprocess.run(["tmux", "clear-history", "-t", pane], timeout=3)
        return True
    except Exception:
        return False


def _pane_tui_busy(pane: str) -> bool:
    tail = _pane_tail(pane)
    bottom = "\n".join(tail.splitlines()[-40:])
    overlay = pane_overlay_detail(tail) if pane_overlay_detail else {"state": "none", "type": ""}
    prompt_is_empty = ("❯" in bottom and not _pane_current_prompt_has_residue(bottom)) or _pane_has_codex_idle_composer(bottom)
    if PANE_RATE_LIMIT_OPTIONS_MODAL_RE.search(bottom):
        if _dismiss_rate_limit_options_modal(pane):
            time.sleep(0.5)
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            prompt_is_empty = ("❯" in bottom and not _pane_current_prompt_has_residue(bottom)) or _pane_has_codex_idle_composer(bottom)
            if not PANE_RATE_LIMIT_OPTIONS_MODAL_RE.search(bottom):
                return False
        return True
    if PANE_TUI_UNAVAILABLE_RE.search(bottom):
        # Fix #7b: a rate-limit / API-error banner means BUSY only while it is the
        # pane's LIVE state. A RESOLVED limit leaves a stale "resets X" banner in
        # scrollback while the pane returns to an idle, ready prompt — that must not
        # wedge the pane forever. LIVE = banner in the immediate active region (last
        # screen), or the options modal / quota-exhausted marker present. STALE =
        # only matches higher in scrollback with an idle, empty, non-spinning prompt
        # below. CONSERVATIVE: anything not provably stale stays BUSY (never dispatch
        # into a genuinely-limited pane). On a provably-stale banner, evict it from
        # the scrollback so it stops matching, and report available.
        active_region = "\n".join(tail.splitlines()[-10:])
        banner_live_now = bool(
            PANE_TUI_UNAVAILABLE_RE.search(active_region)
            or PANE_RATE_LIMIT_OPTIONS_MODAL_RE.search(bottom)
            or PANE_QUOTA_EXHAUSTED_RE.search(active_region)
        )
        stale_resolved = (
            not banner_live_now
            and prompt_is_empty
            and not PANE_LIVE_SPINNER_RE.search(bottom)
        )
        if stale_resolved:
            _clear_pane_scrollback(pane)
            return False
        return True
    if PANE_PROCESSING_RE.search(bottom):
        if _pane_prompt_residue_is_stale_scrollback(pane, tail):
            return False
        if prompt_is_empty and PANE_COMPLETED_MARKER_RE.search(bottom):
            return False
        prompt_reason = _pane_dispatch_prompt_reason(bottom)
        if prompt_reason in RECOVERABLE_DISPATCH_PROMPT_REASONS and _dismiss_dispatch_prompt(pane, prompt_reason):
            time.sleep(0.5)
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            if not PANE_PROCESSING_RE.search(bottom) or not _pane_dispatch_prompt_reason(bottom):
                return False
        if prompt_is_empty and _pane_current_command(pane).lower() in {"bash", "zsh", "sh", "fish"}:
            return False
        if prompt_is_empty and not PANE_LIVE_SPINNER_RE.search(bottom):
            return False
        return True
    if PANE_SURVEY_PROMPT_RE.search(bottom):
        if overlay.get("state") == "stale_scrollback_ignored" or prompt_is_empty:
            return False
        # Fix #7a: the survey is an idle-time modal blocking dispatch. Reaching this
        # branch means no working turn (the processing branch returns earlier), so it
        # is safe to auto-dismiss the survey and re-check before reporting busy.
        if _dismiss_dispatch_prompt(pane, "survey_prompt_blocked"):
            time.sleep(0.4)
            bottom = "\n".join(_pane_tail(pane).splitlines()[-40:])
            if not PANE_SURVEY_PROMPT_RE.search(bottom):
                return False
        return True
    confirmation_match = PANE_CONFIRMATION_PROMPT_RE.search(bottom)
    if confirmation_match and not _prompt_match_followed_by_idle_default_prompt(bottom, confirmation_match):
        prompt_reason = _pane_dispatch_prompt_reason(bottom)
        if prompt_reason in RECOVERABLE_DISPATCH_PROMPT_REASONS and _dismiss_dispatch_prompt(pane, prompt_reason):
            time.sleep(0.5)
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            confirmation_match = PANE_CONFIRMATION_PROMPT_RE.search(bottom)
            if not (confirmation_match and not _prompt_match_followed_by_idle_default_prompt(bottom, confirmation_match)):
                return False
        return True
    if PANE_TUI_BUSY_RE.search(bottom):
        if prompt_is_empty:
            return False
        return True
    # Queued prompt residue is an idle overlay, not useful work. Discovery used
    # to return busy here before `_pane_unavailable_reason()` could clear it,
    # which left panes permanently stranded.
    if PANE_QUEUED_PROMPT_RE.search(bottom):
        if overlay.get("state") == "stale_scrollback_ignored":
            return False
        if _clear_stale_prompt_residue(pane):
            time.sleep(0.3)
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            if not PANE_QUEUED_PROMPT_RE.search(bottom):
                return False
        return True
    # A non-empty Claude prompt at the bottom is unsubmitted input residue. If
    # we dispatch into it, Claude may concatenate unrelated tasks or open the
    # queued-message UI instead of executing the new node.
    if _pane_current_prompt_has_residue(bottom) and not _pane_prompt_residue_is_stale_scrollback(pane, tail):
        if _clear_stale_prompt_residue(pane):
            time.sleep(0.3)
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            if not (_pane_current_prompt_has_residue(bottom) and not _pane_prompt_residue_is_stale_scrollback(pane, tail)):
                return False
        return True
    return False


def _pane_runtime_unavailable_reason(pane: str, title: str = "") -> str:
    command = _pane_current_command(pane).lower()
    if command not in {"bash", "zsh", "sh", "fish"}:
        return ""
    if _pane_runtime() == "codex":
        if _pane_has_codex_process(pane):
            return ""
        return "codex_runtime_not_running"
    title_lower = title.lower()
    if "idle/no active sprint" not in title_lower:
        return ""
    tail = _pane_tail(pane)
    bottom = "\n".join(tail.splitlines()[-12:])
    if _pane_current_prompt_has_residue(bottom) or PANE_QUEUED_PROMPT_RE.search(bottom):
        if _clear_stale_prompt_residue(pane):
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-12:])
            if not (_pane_current_prompt_has_residue(bottom) or PANE_QUEUED_PROMPT_RE.search(bottom)):
                return ""
        return "worker_runtime_not_running"
    return ""


def _multi_task_direct_dispatch_unavailable_reason(
    pane: str,
    *,
    current_command: str | None = None,
) -> str:
    """Multi-task shell panes are launch surfaces, not prompt receivers.

    `solar-harness multi-task` may keep idle shell windows in the pane pool for
    reuse. Direct graph dispatch must not paste Claude prompts into those
    shells; the multi-task runner is responsible for starting a model process
    there first.
    """
    if not _pane_in_multi_task_session(pane):
        return ""
    command = (current_command if current_command is not None else _pane_current_command(pane)).lower()
    if command in {"bash", "zsh", "sh", "fish", ""}:
        return "multi_task_shell_not_direct_worker"
    return ""


def _clear_stale_prompt_residue(pane: str) -> bool:
    """Clear idle Claude prompt residue in harness-owned worker panes.

    This is intentionally conservative: it only runs when the bottom of the
    pane is not actively processing and the visible prompt contains unsubmitted
    text. Without this, one stale "continue ..." prompt can make a builder pane
    look permanently busy and strand DAG nodes with no_matching_worker.
    """
    tail = _pane_tail(pane)
    bottom = "\n".join(tail.splitlines()[-12:])
    has_residue = bool(PANE_QUEUED_PROMPT_RE.search(bottom) or _pane_current_prompt_has_residue(bottom))
    if PANE_TUI_UNAVAILABLE_RE.search(bottom):
        return False
    # Never press editing/interrupt keys while Claude is actively working.
    # Queued-prompt text can remain visible in the frame during generation; it
    # is not safe to clear until the pane is idle.
    if PANE_PROCESSING_RE.search(bottom) and not PANE_QUEUED_PROMPT_RE.search(bottom):
        return False
    if not has_residue:
        if PANE_TUI_BUSY_RE.search(bottom):
            return False
        return False
    try:
        # Claude Code prompt editing has varied across versions. Check after
        # each conservative idle-prompt clear path so active output is never
        # touched unless the pane already looked idle-with-residue.
        for keys in (("Escape",), ("C-a", "C-k"), ("C-u",), ("C-c",), ("Escape", "C-u")):
            subprocess.run(["tmux", "send-keys", "-t", pane, *keys], timeout=2)
            time.sleep(0.2)
            after = "\n".join(_pane_tail(pane).splitlines()[-12:])
            if not (PANE_QUEUED_PROMPT_RE.search(after) or _pane_current_prompt_has_residue(after)):
                return True
    except Exception:
        return False
    after = "\n".join(_pane_tail(pane).splitlines()[-12:])
    return not (PANE_QUEUED_PROMPT_RE.search(after) or _pane_current_prompt_has_residue(after))


def _dismiss_rate_limit_options_modal(pane: str) -> bool:
    """Dismiss Claude's rate-limit options modal without choosing an action.

    The modal is an interactive overlay, not useful work. Leaving it visible
    makes worker discovery report the pane busy forever and can strand unrelated
    DAG nodes. Esc is the safe recovery path because it cancels the overlay
    instead of selecting "wait" or "upgrade".
    """
    tail = _pane_tail(pane)
    bottom = "\n".join(tail.splitlines()[-40:])
    if not PANE_RATE_LIMIT_OPTIONS_MODAL_RE.search(bottom):
        return False
    try:
        for keys in (("Escape",), ("C-c",)):
            subprocess.run(["tmux", "send-keys", "-t", pane, *keys], timeout=2)
            time.sleep(0.4)
            after = "\n".join(_pane_tail(pane).splitlines()[-40:])
            if not PANE_RATE_LIMIT_OPTIONS_MODAL_RE.search(after):
                return True
    except Exception:
        return False
    return False


def _pane_unavailable_reason(pane: str) -> str:
    health = _pane_health(pane)
    if health.get("unavailable"):
        return str(health.get("reason") or "provider_health_unavailable")
    tail = _pane_tail(pane)
    bottom = "\n".join(tail.splitlines()[-40:])
    overlay = pane_overlay_detail(tail) if pane_overlay_detail else {"state": "none", "type": ""}
    if PANE_RATE_LIMIT_OPTIONS_MODAL_RE.search(bottom):
        if _dismiss_rate_limit_options_modal(pane):
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            if not PANE_RATE_LIMIT_OPTIONS_MODAL_RE.search(bottom):
                return ""
        return "rate_limit_options_modal"
    prompt_reason = _pane_dispatch_prompt_reason(bottom)
    if prompt_reason:
        if prompt_reason in RECOVERABLE_DISPATCH_PROMPT_REASONS and _dismiss_dispatch_prompt(pane, prompt_reason):
            time.sleep(0.5)
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            prompt_reason = _pane_dispatch_prompt_reason(bottom)
            if not prompt_reason:
                return ""
        return prompt_reason
    # Active Claude output can leave an edit/proceed prompt visible while tests
    # or tool calls are still running. Do not recover/press keys in that state;
    # mark it busy only, and let the idle-path hygiene clear it after the run.
    if PANE_PROCESSING_RE.search(bottom) and not _pane_prompt_residue_is_stale_scrollback(pane, tail):
        return ""
    if PANE_TUI_UNAVAILABLE_RE.search(bottom):
        return "rate_limit_or_api_error"
    if PANE_SURVEY_PROMPT_RE.search(bottom):
        if overlay.get("state") == "stale_scrollback_ignored" or ("❯" in bottom and not _pane_current_prompt_has_residue(bottom)):
            return ""
        return "survey_prompt_blocked"
    if PANE_QUEUED_PROMPT_RE.search(bottom):
        if overlay.get("state") == "stale_scrollback_ignored":
            return ""
        if _clear_stale_prompt_residue(pane):
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            if not PANE_QUEUED_PROMPT_RE.search(bottom):
                return ""
        return "queued_prompt_residue"
    if _pane_current_prompt_has_residue(bottom) and not _pane_prompt_residue_is_stale_scrollback(pane, tail):
        if _clear_stale_prompt_residue(pane):
            tail = _pane_tail(pane)
            bottom = "\n".join(tail.splitlines()[-40:])
            if not (_pane_current_prompt_has_residue(bottom) and not _pane_prompt_residue_is_stale_scrollback(pane, tail)):
                return ""
        return "unsubmitted_prompt_residue"
    return ""


def _pane_hygiene_file() -> Path:
    return HARNESS_DIR / "run" / "pane-hygiene.json"


def _pane_hygiene_entries() -> dict[str, Any]:
    path = _pane_hygiene_file()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    panes = payload.get("panes")
    if isinstance(panes, dict):
        return panes
    # Live registries may be stored as a flat map:
    # {"session:win.pane": {"state": "needs_respawn", ...}}.
    # Honor that shape so bad panes do not re-enter evaluator capacity.
    if isinstance(payload, dict):
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, dict) and "state" in value
        }
    return {}


def _recover_pane_hygiene_if_idle(pane: str, state: str) -> bool:
    if state not in {"cooling", "needs_recover", "dirty"}:
        return False
    # Fix (Wall #4): do NOT bail on an active lease. A dirty/cooling/needs_recover
    # pane that is IDLE (not tui-busy) is safe to recover regardless of who holds the
    # lease -- the dirty state is a stale dispatch-boundary marker, not active work.
    # Bailing on the lease deadlocked a same-pane node (it pre-acquires the lease,
    # then the boundary-dirty pane won't recover under its OWN lease). tui-busy below
    # is the real safety; pane-stealing is prevented at lease ACQUISITION, not here.
    if _pane_tui_busy(pane):
        return False
    return True


_HUNG_PANE_SAMPLES = 3
_HUNG_PANE_SAMPLE_GAP_S = 6.0  # 3 samples across ~12s
_SPINNER_TIMER_RE = re.compile(r"\((\d+(?:h|m|s)(?:\s+\d+(?:m|s))*)\)")


def _pane_shows_spinner(pane: str) -> bool:
    bottom = "\n".join(_pane_tail(pane, lines=12).splitlines()[-12:])
    return bool(PANE_PROCESSING_RE.search(bottom))


_COCKPIT_PERSONA_BY_INDEX = {"0.0": "pm", "0.1": "planner", "0.2": "builder", "0.3": "evaluator"}
_CLAUDE_CLEAN_ENV = (
    "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_EXECPATH "
    "-u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_API_KEY "
    "-u ANTHROPIC_DEFAULT_OPUS_MODEL -u ANTHROPIC_DEFAULT_SONNET_MODEL -u ANTHROPIC_DEFAULT_HAIKU_MODEL"
)


def _respawn_cockpit_pane(pane: str) -> bool:
    """Force-kill a wedged cockpit pane and relaunch its persona fresh, mirroring
    solar-harness.sh apply_product_delivery_models (clean env + pane-launcher).
    pane_doctor refuses to respawn PROTECTED main panes, so this is the only path
    that recovers a main pane whose turn is hung beyond key-interrupt recovery."""
    persona = _COCKPIT_PERSONA_BY_INDEX.get(pane.split(":")[-1], "builder")
    try:
        pane_id = subprocess.check_output(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_id}"], timeout=3
        ).decode().strip()
        work_dir = subprocess.check_output(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_current_path}"], timeout=3
        ).decode().strip()
    except Exception:
        return False
    if not pane_id:
        return False
    if not work_dir:
        work_dir = str(Path.home() / "solar-cleanrun")
    launcher = str(HARNESS_DIR / "pane-launcher.sh")
    cmd = (
        f"{_CLAUDE_CLEAN_ENV} TMUX_PANE={pane_id} SOLAR_CLAUDE_BYPASS=1 "
        f"bash '{launcher}' {persona} '{work_dir}'"
    )
    try:
        subprocess.run(["tmux", "respawn-pane", "-k", "-t", pane, cmd], timeout=10, check=True)
        return True
    except Exception:
        return False


def _set_pane_boot_grace(pane: str, seconds: int, *, sid: str = "", dispatch_id: str = "") -> None:
    """Hold a freshly-respawned pane out of dispatch while its Claude boots, via a
    short custom recover-cooldown (the default PANE_RECOVER_COOLDOWN_SEC is too
    long). Mirrors _mark_pane_recover_cooldown's entry shape so it stays valid."""
    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    data = _pane_cooldowns()
    data[pane] = {
        "reason": "hung_pane_respawn_booting",
        "sid": sid,
        "dispatch_id": dispatch_id,
        "marked_at": _utc_now(),
        "until": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write_pane_cooldowns(data)


def _recover_hung_pane(pane: str, *, sid: str = "", node_id: str = "", dispatch_id: str = "") -> bool:
    """Recover a FROZEN (hung) cockpit pane so an assigned node stops looping.

    A wedged Claude turn leaves a processing spinner on screen with no progress,
    stranding the node assigned to it (observed: builder pane stuck on a frozen
    `Prestidigitating… (0s)` turn whose elapsed-time counter never advances, after
    a transient opus stall; opus recovered but the pane did not, and pane_doctor
    never recovers PROTECTED main panes). The fragile part is the busy/lease
    CLASSIFICATION — the same frozen render was read tui-busy in one moment and
    not-busy (with a stale dispatch lease) the next — so we deliberately do NOT
    gate on _pane_tui_busy or on the lease here.

    The robust, sufficient discriminator is the spinner's ELAPSED TIMER. A working
    turn counts up — (5s) -> (12s) — and/or streams output; a frozen turn is stuck.
    Sample several times across a window and bail if the timer advances, the render
    streams, the spinner clears, or no live timer can be parsed. Act ONLY when a
    live elapsed-timer is present-and-stuck across the whole window AND the render
    is byte-static — that is the safety (a real working pane is never interrupted).
    On a confirmed freeze, interrupt the hung turn (Escape, then C-c), clear any
    recover-cooldown, and log the action; the subsequent dispatch goes through
    _send_to_pane's normal C-u residue clear, and the reconcile path re-dispatches
    the (now released) node onto the recovered pane.

    Returns True iff the interrupt fired AND the spinner cleared.
    """
    if not _pane_shows_spinner(pane):
        return False
    renders: list[str] = []
    timers: list[str | None] = []
    for i in range(_HUNG_PANE_SAMPLES):
        if i:
            time.sleep(_HUNG_PANE_SAMPLE_GAP_S)
        render = _pane_tail(pane, lines=40)
        bottom = "\n".join(render.splitlines()[-12:])
        timer: str | None = None
        if PANE_PROCESSING_RE.search(bottom):
            found = _SPINNER_TIMER_RE.findall(bottom)
            timer = found[-1] if found else None
        renders.append(render)
        timers.append(timer)
    if not _pane_shows_spinner(pane):
        return False  # spinner cleared during sampling -> not hung
    if any(t is None for t in timers):
        return False  # no parseable elapsed-timer -> cannot confirm a stuck spinner
    if any(t != timers[0] for t in timers):
        return False  # spinner elapsed-timer advanced -> genuinely working
    if any(r != renders[0] for r in renders):
        return False  # render changed (streaming) -> genuinely working
    for keys in (("Escape",), ("C-c",), ("Escape", "C-u")):
        try:
            subprocess.run(["tmux", "send-keys", "-t", pane, *keys], timeout=2)
        except Exception:
            return False
        time.sleep(0.4)
        if not _pane_shows_spinner(pane):
            cooldowns = _pane_cooldowns()
            if cooldowns.pop(pane, None) is not None:
                _write_pane_cooldowns(cooldowns)
            _append_dispatch_ledger(
                "hung_pane_recovered", sid, pane, dispatch_id,
                {"node": node_id, "keys": "+".join(keys), "elapsed": timers[0] or "", "detector": "frozen_timer"},
            )
            return True
    _append_dispatch_ledger(
        "hung_pane_recover_failed", sid, pane, dispatch_id,
        {"node": node_id, "detector": "frozen_timer"},
    )
    return False


def _pane_hygiene_unavailable_reason(pane: str) -> str:
    entry = _pane_hygiene_entries().get(pane)
    if not isinstance(entry, dict):
        return ""
    state = str(entry.get("state") or "").strip().lower()
    if not state or state in {"clean", "running"}:
        return ""
    if state == "needs_respawn":
        return "pane_hygiene_needs_respawn"
    if state == "dirty":
        if _recover_pane_hygiene_if_idle(pane, state):
            return ""
        return "pane_hygiene_dirty"
    if state in {"cooling", "needs_recover"}:
        if _recover_pane_hygiene_if_idle(pane, state):
            return ""
        return f"pane_hygiene_{state}"
    return ""


def _pane_title_active_unavailable_reason(pane: str, title: str) -> str:
    title_lower = str(title or "").lower()
    if "状态:working/" not in title_lower:
        return ""
    # Historical title metadata can lag behind the real pane state. When the
    # pane is now idle, or when we deliberately tagged the pane as an
    # idle-assigned graph worker, do not strand redispatch on stale title text.
    if "graph_node_idle_assigned" in title_lower:
        return ""
    if not _pane_has_active_lease(pane):
        return ""
    if not _pane_tui_busy(pane):
        return "pane_title_active_work"
    return "pane_title_active_work"


def _assigned_pane_unavailable_reason(pane: str) -> str:
    """Runtime guard for queue items that already carry a concrete pane.

    Worker discovery filters busy/quota panes before assignment, but queued
    items can outlive the pane state they were assigned under. Re-check the
    target immediately before lease/send so a later quota hit or TUI block does
    not strand the node in dispatched state.
    """
    if not _pane_in_harness_session_scope(pane):
        return "pane_outside_harness_session"
    title = _pane_title(pane)
    health = _pane_health(pane)
    models = _models_for_pane(pane, title)
    tail = _pane_tail(pane)
    quota_exhausted = _quota_exhausted_models(title, tail, health, models)
    return (
        _pane_hygiene_unavailable_reason(pane)
        or
        _pane_cooldown_reason(pane)
        or
        _pane_title_active_unavailable_reason(pane, title)
        or
        _multi_task_direct_dispatch_unavailable_reason(pane)
        or _pane_runtime_unavailable_reason(pane, title)
        or _pane_unavailable_reason(pane)
        or ("rate_limit_or_api_error" if quota_exhausted else "")
    )


def _pane_has_matching_queued_prompt(pane: str, instruction_file: Path) -> bool:
    tail = _pane_tail(pane, lines=30)
    if not PANE_QUEUED_PROMPT_RE.search(tail):
        return False
    instruction_path = str(instruction_file.resolve())
    return instruction_file.name in tail or instruction_path in tail


def _pane_dispatch_prompt_reason(tail: str) -> str:
    bottom = "\n".join((tail or "").splitlines()[-40:])
    overlay = pane_overlay_detail(tail) if pane_overlay_detail else {"state": "none", "type": ""}
    if overlay.get("state") == "stale_scrollback_ignored":
        return ""
    edit_match = re.search(r"Do you want to make this edit|Do you want to overwrite|allow all edits during this session", bottom, re.I)
    if edit_match and not _prompt_match_followed_by_idle_default_prompt(bottom, edit_match):
        return "edit_confirmation_prompt"
    confirmation_match = re.search(r"Do you want to proceed\?|Would you like to proceed\?|Tab to amend", bottom)
    if confirmation_match and not _prompt_match_followed_by_idle_default_prompt(bottom, confirmation_match):
        return "proceed_confirmation_prompt"
    # `accept edits on` and `bypass permissions on` are Claude Code footer/mode
    # indicators on healthy idle panes. Treat only actual confirmation/edit
    # prompts as blockers; otherwise clean panes get stranded as unavailable.
    queued_match = PANE_QUEUED_PROMPT_RE.search(bottom)
    if queued_match and not _prompt_match_followed_by_idle_default_prompt(bottom, queued_match):
        return "queued_prompt_residue"
    if PANE_PLAN_MODE_RE.search(bottom):
        return "plan_mode_blocked"
    return ""


def _dismiss_dispatch_prompt(pane: str, reason: str) -> bool:
    try:
        if reason == "proceed_confirmation_prompt":
            for keys in (("Enter",), ("1", "Enter"), ("y", "Enter")):
                subprocess.run(["tmux", "send-keys", "-t", pane, *keys], timeout=2)
                time.sleep(0.3)
                after = "\n".join(_pane_tail(pane).splitlines()[-40:])
                prompt_reason = _pane_dispatch_prompt_reason(after)
                if prompt_reason != reason:
                    return True
            return False
        if reason in {"permissions_prompt", "edit_confirmation_prompt"}:
            subprocess.run(["tmux", "send-keys", "-t", pane, "BTab"], timeout=2)
            time.sleep(0.2)
            subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], timeout=2)
            return True
        if reason == "queued_prompt_residue":
            return _clear_stale_prompt_residue(pane)
        if reason == "plan_mode_blocked":
            for _ in range(4):
                subprocess.run(["tmux", "send-keys", "-t", pane, "BTab"], timeout=2)
                time.sleep(0.25)
                after = "\n".join(_pane_tail(pane).splitlines()[-40:])
                if not PANE_PLAN_MODE_RE.search(after):
                    return True
            return False
        if reason == "survey_prompt_blocked":
            # Fix #7a: dismiss the "How is Claude doing?" survey modal (0 = Dismiss;
            # Escape as fallback), verifying it actually cleared.
            for keys in (("0",), ("Escape",)):
                subprocess.run(["tmux", "send-keys", "-t", pane, *keys], timeout=2)
                time.sleep(0.4)
                after = "\n".join(_pane_tail(pane).splitlines()[-40:])
                if not PANE_SURVEY_PROMPT_RE.search(after):
                    return True
            return False
    except Exception:
        return False
    return False


def _wait_for_dispatch_window(pane: str, instruction_file: Path, *, sid: str = "", attempts: int = 8) -> tuple[bool, str]:
    """Bring a pane back to a safe submit window before dispatching.

    Graph dispatch historically assumed an alive pane was ready. In reality,
    Claude panes often sit behind confirmation/edit prompts or stale prompt
    residue. This helper mirrors the coordinator's more conservative preflight:
    clear/dismiss recoverable prompt states first, then only proceed once the
    pane no longer exposes a blocking prompt.
    """
    last_reason = ""
    instruction_path = str(instruction_file.resolve())
    for _ in range(max(1, attempts)):
        tail = _pane_tail(pane)
        runtime_reason = _pane_runtime_unavailable_reason(pane, _pane_title(pane))
        if runtime_reason:
            return False, runtime_reason
        if (
            (instruction_file.name in tail or instruction_path in tail)
            and PANE_PROCESSING_RE.search(tail)
            and not _pane_dispatch_prompt_reason(tail)
        ):
            return True, "matching_dispatch_already_processing"
        if _pane_has_matching_queued_prompt(pane, instruction_file):
            last_reason = "matching_queued_prompt"
            if PANE_PROCESSING_RE.search(tail):
                return True, "matching_queued_prompt_already_processing"
            try:
                subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], timeout=2)
                time.sleep(2.0)
            except Exception:
                return False, "matching_queued_prompt_submit_failed"
            continue
        prompt_reason = _pane_dispatch_prompt_reason(tail)
        if prompt_reason:
            last_reason = prompt_reason
            if _dismiss_dispatch_prompt(pane, prompt_reason):
                time.sleep(1.5)
                continue
            return False, prompt_reason
        if _clear_stale_prompt_residue(pane):
            last_reason = "stale_prompt_residue"
            time.sleep(0.5)
            continue
        if _pane_tui_busy(pane):
            last_reason = "pane_tui_busy"
            time.sleep(1.0)
            continue
        return True, last_reason or "ready"
    return False, last_reason or "dispatch_window_timeout"


def _write_submit_ack(sid: str, node_id: str, pane: str, dispatch_id: str) -> None:
    """Write observable submit evidence so evaluators can verify pane received the dispatch."""
    try:
        ack_dir = HARNESS_DIR / "sprints" / "graph-acks"
        ack_dir.mkdir(parents=True, exist_ok=True)
        ack_file = ack_dir / f"{sid}.{node_id}-submit-ack.json"
        ack = {
            "sid": sid,
            "node_id": node_id,
            "pane": pane,
            "dispatch_id": dispatch_id,
            "submitted_at": _utc_now(),
        }
        ack_file.write_text(json.dumps(ack, indent=2), encoding="utf-8")
    except Exception:
        pass  # fail-open: ack write failure must not block dispatch


def _broker_env(sprint_id: str | None = None) -> dict[str, str]:
    """Return os.environ copy with broker control vars forwarded to child subprocesses.

    SOLAR_BROKER_ENABLED is forwarded as-is (defaulting to "0" when absent) so
    child tools honour the same gate the dispatcher sees.
    SOLAR_BROKER_SPRINT_ID is set from sprint_id when not already in the env.
    When SOLAR_BROKER_ENABLED="0" the returned dict is os.environ with "0" set,
    preserving the unchanged-dispatch-path guarantee (LR-04).
    """
    env = os.environ.copy()
    env.setdefault("SOLAR_BROKER_ENABLED", "0")
    if sprint_id:
        env.setdefault("SOLAR_BROKER_SPRINT_ID", sprint_id)
    return env


def _record_model_call(event: str, sid: str, pane: str, dispatch_id: str,
                       instruction_file: Path, *, tries: int = 0,
                       status: str = "", error: str = "") -> None:
    if not sid:
        return
    recorder = HARNESS_DIR / "lib" / "model_call_runtime.py"
    if not recorder.exists():
        return
    cmd = [
        sys.executable, str(recorder), event,
        "--session-id", sid,
        "--pane", pane,
        "--dispatch-id", dispatch_id,
        "--instruction-file", str(instruction_file),
        "--actor", "graph-dispatcher",
        "--tries", str(tries),
    ]
    if status:
        cmd += ["--status", status]
    if error:
        cmd += ["--error", error]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
                       env=_broker_env(sid))
    except Exception:
        pass


def _send_to_pane(pane: str, instruction_file: Path, dry_run: bool,
                  *, sid: str = "", dispatch_id: str = "") -> bool:
    if dry_run:
        return True
    processing_re = PANE_PROCESSING_RE
    ready, ready_reason = _wait_for_dispatch_window(pane, instruction_file, sid=sid)
    if not ready and _pane_tui_busy(pane):
        tail = _pane_tail(pane)
        instruction_path = str(instruction_file.resolve())
        dispatch_keyword = instruction_file.name
        if (sid or dispatch_id) and (dispatch_keyword in tail or instruction_path in tail) and processing_re.search(tail):
            _record_model_call(
                "succeeded",
                sid,
                pane,
                dispatch_id,
                instruction_file,
                tries=1,
                status="preflight_detected_existing_dispatch_processing",
            )
            return True
        if _pane_has_matching_queued_prompt(pane, instruction_file):
            for tries in range(1, 3):
                try:
                    subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], timeout=2)
                    time.sleep(3.0)
                    tail = _pane_tail(pane)
                    if processing_re.search(tail) or not PANE_QUEUED_PROMPT_RE.search(tail):
                        _record_model_call(
                            "succeeded",
                            sid,
                            pane,
                            dispatch_id,
                            instruction_file,
                            tries=tries,
                            status="matching_queued_prompt_submitted",
                        )
                        return True
                except Exception:
                    time.sleep(0.5)
        prompt_reason = _pane_dispatch_prompt_reason(_pane_tail(pane))
        if prompt_reason and _dismiss_dispatch_prompt(pane, prompt_reason):
            time.sleep(2.0)
            tail = _pane_tail(pane)
            if processing_re.search(tail) or not _pane_dispatch_prompt_reason(tail):
                _record_model_call(
                    "succeeded",
                    sid,
                    pane,
                    dispatch_id,
                    instruction_file,
                    tries=1,
                    status=f"dispatch_prompt_dismissed:{prompt_reason}",
                )
                return True
        if sid or dispatch_id:
            _record_model_call(
                "failed",
                sid,
                pane,
                dispatch_id,
                instruction_file,
                status=f"pane_not_ready_before_send:{ready_reason}",
                error=f"pane dispatch window unavailable: {ready_reason}",
            )
            marker = _mark_pane_recover_retryable if _recoverable_pane_blocker(ready_reason) else _mark_pane_recover_cooldown
            marker(pane, f"pane_not_ready_before_send:{ready_reason}", sid=sid, dispatch_id=dispatch_id)
            return False
    cleared, clear_reason = _clear_dispatch_boundary(pane, sid, dispatch_id)
    if not cleared:
        _record_model_call(
            "failed",
            sid,
            pane,
            dispatch_id,
            instruction_file,
            status=f"clear_gate_failed:{clear_reason}",
            error=f"dispatch clear gate failed: {clear_reason}",
        )
        return False
    _set_pane_capability_title(pane, instruction_file)
    instruction_path = str(instruction_file.resolve())
    dispatch_keyword = instruction_file.name
    if _pane_runtime() == "codex":
        role_file = _role_file_for_pane(pane)
        short_cmd = f"{_visibility_summary(instruction_file)['text']}; 先读取角色指令 {role_file}，再读取并执行 {instruction_path}"
    else:
        short_cmd = f"{_visibility_summary(instruction_file)['text']}; 读取并执行 {instruction_path}"
    _record_model_call("request", sid, pane, dispatch_id, instruction_file, status="tmux_submit_requested")
    last_error = ""
    def _settled_dispatch_state() -> tuple[str, str, bool, bool]:
        time.sleep(1.0)
        settled_tail = _pane_tail(pane)
        settled_prompt_reason = _pane_dispatch_prompt_reason(settled_tail)
        settled_has_keyword = dispatch_keyword in settled_tail or instruction_path in settled_tail
        settled_has_processing = bool(processing_re.search(settled_tail))
        return settled_tail, settled_prompt_reason, settled_has_keyword, settled_has_processing
    for tries in range(1, 4):
        try:
            subprocess.run(["tmux", "send-keys", "-t", pane, "C-u"], timeout=2)
            time.sleep(0.2)
            # Send as literal text; otherwise tmux may parse punctuation in a
            # path-like instruction as key names and discard the input.
            subprocess.run(["tmux", "send-keys", "-t", pane, "-l", short_cmd], timeout=2)
            time.sleep(0.8)
            # Claude Code TUI can swallow the first return or leave literal
            # prompt text queued. A second return with no text is harmless, but
            # leaving a graph node in the prompt is a hard dispatch failure.
            subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], timeout=2)
            time.sleep(0.35)
            subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], timeout=2)
            if os.environ.get("SOLAR_GRAPH_DISPATCH_ASYNC_SUBMIT") == "1":
                _record_model_call(
                    "succeeded",
                    sid,
                    pane,
                    dispatch_id,
                    instruction_file,
                    tries=tries,
                    status="async_submit_tmux_send_accepted",
                )
                return True
            time.sleep(4.0)
            tail = _pane_tail(pane)
            prompt_reason = _pane_dispatch_prompt_reason(tail)
            if prompt_reason:
                _dismiss_dispatch_prompt(pane, prompt_reason)
                time.sleep(2.0)
                tail = _pane_tail(pane)
                prompt_reason = _pane_dispatch_prompt_reason(tail)
                if prompt_reason:
                    last_error = f"dispatch prompt not dismissed: {prompt_reason}"
                    marker = _mark_pane_recover_retryable if _recoverable_pane_blocker(last_error) else _mark_pane_recover_cooldown
                    marker(pane, last_error, sid=sid, dispatch_id=dispatch_id)
                    continue
            has_keyword = dispatch_keyword in tail or instruction_path in tail
            has_processing = bool(processing_re.search(tail))
            if has_keyword and has_processing:
                _, settled_prompt_reason, settled_has_keyword, settled_has_processing = _settled_dispatch_state()
                if settled_prompt_reason:
                    last_error = f"dispatch settled into {settled_prompt_reason}"
                    time.sleep(1.0)
                    continue
                if not (settled_has_keyword or settled_has_processing):
                    last_error = "dispatch verification lost after settle window"
                    time.sleep(1.0)
                    continue
                _record_model_call(
                    "succeeded",
                    sid,
                    pane,
                    dispatch_id,
                    instruction_file,
                    tries=tries,
                    status="keyword_processing_verified",
                )
                return True
            if has_keyword and not has_processing:
                # Residual prompt rescue. Some Claude Code builds show the
                # instruction in the prompt, but the real key event is not
                # accepted until the next standalone Enter. Do not cancel first:
                # cancellation can convert a recoverable prompt residue into an
                # interrupted task that waits for human choice.
                for _ in range(2):
                    subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], timeout=2)
                    time.sleep(3.0)
                    tail = _pane_tail(pane)
                    if processing_re.search(tail):
                        _, settled_prompt_reason, settled_has_keyword, settled_has_processing = _settled_dispatch_state()
                        if settled_prompt_reason:
                            last_error = f"dispatch settled into {settled_prompt_reason}"
                            time.sleep(1.0)
                            continue
                        if not (settled_has_keyword or settled_has_processing):
                            last_error = "dispatch verification lost after residual rescue"
                            time.sleep(1.0)
                            continue
                        _record_model_call(
                            "succeeded",
                            sid,
                            pane,
                            dispatch_id,
                            instruction_file,
                            tries=tries,
                            status="keyword_processing_verified_after_residual_rescue",
                        )
                        return True
            if has_keyword:
                if prompt_reason:
                    last_error = f"dispatch blocked by {prompt_reason}"
                    marker = _mark_pane_recover_retryable if _recoverable_pane_blocker(last_error) else _mark_pane_recover_cooldown
                    marker(pane, last_error, sid=sid, dispatch_id=dispatch_id)
                    time.sleep(1.0)
                    continue
                # Do not send C-c after the instruction is visible. Claude Code
                # may start processing after our verification window; cancelling
                # here is what creates repeated "Interrupted · What should
                # Claude do instead?" deadlocks in builder panes. Treat visible
                # instruction as accepted but unverified, and let watchdog /
                # handoff detection judge progress from durable artifacts.
                _record_model_call(
                    "succeeded",
                    sid,
                    pane,
                    dispatch_id,
                    instruction_file,
                    tries=tries,
                    status="keyword_visible_submit_unverified_no_cancel",
                )
                return True
            if has_processing:
                # Pre-send busy detection already verified the pane was not
                # active. If it starts processing after our send, the prompt was
                # accepted even when the wrapped screen tail no longer contains
                # the full filename. Treat that as a successful submit; durable
                # handoff/eval artifacts remain the completion source of truth.
                _, settled_prompt_reason, settled_has_keyword, settled_has_processing = _settled_dispatch_state()
                if settled_prompt_reason:
                    last_error = f"dispatch settled into {settled_prompt_reason}"
                    time.sleep(1.0)
                    continue
                if not (settled_has_keyword or settled_has_processing):
                    last_error = "dispatch processing signal disappeared during settle window"
                    time.sleep(1.0)
                    continue
                _record_model_call(
                    "succeeded",
                    sid,
                    pane,
                    dispatch_id,
                    instruction_file,
                    tries=tries,
                    status="processing_verified_without_keyword",
                )
                return True
            last_error = "dispatch text not accepted by pane"
            # Never send C-c from the dispatcher. Claude Code treats C-c as an
            # interactive interruption and can leave the pane in a Rewind prompt
            # that blocks automation. If the text was not accepted, report
            # send_failed and let the caller decide whether to retry, quarantine,
            # or respawn the pane.
            time.sleep(1.0)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.5)
    tail = _pane_tail(pane)
    prompt_reason = _pane_dispatch_prompt_reason(tail)
    if (dispatch_keyword in tail or instruction_path in tail or processing_re.search(tail)) and not prompt_reason:
        _, settled_prompt_reason, settled_has_keyword, settled_has_processing = _settled_dispatch_state()
        if settled_prompt_reason:
            _mark_pane_recover_cooldown(
                pane,
                f"late_settle_blocked:{settled_prompt_reason}",
                sid=sid,
                dispatch_id=dispatch_id,
            )
            _record_model_call(
                "failed",
                sid,
                pane,
                dispatch_id,
                instruction_file,
                tries=3,
                status=f"late_settle_blocked:{settled_prompt_reason}",
                error=f"dispatch settled into blocking prompt: {settled_prompt_reason}",
            )
            return False
        if not (settled_has_keyword or settled_has_processing):
            _record_model_call(
                "failed",
                sid,
                pane,
                dispatch_id,
                instruction_file,
                tries=3,
                status="late_settle_signal_lost",
                error="dispatch verification disappeared after settle window",
            )
            return False
        _record_model_call(
            "succeeded",
            sid,
            pane,
            dispatch_id,
            instruction_file,
            tries=3,
            status="late_submit_verification",
        )
        return True
    _record_model_call(
        "failed",
        sid,
        pane,
        dispatch_id,
        instruction_file,
        tries=3,
        status="tmux_submit_failed",
        error=last_error,
    )
    _mark_pane_recover_cooldown(
        pane,
        f"tmux_submit_failed:{last_error}",
        sid=sid,
        dispatch_id=dispatch_id,
    )
    return False


def _append_dispatch_ledger(kind: str, sid: str, pane: str, dispatch_id: str, extra: dict[str, Any]) -> None:
    record = {
        "ts": _utc_now(),
        "kind": kind,
        "sid": sid,
        "pane": pane,
        "dispatch_id": dispatch_id,
    }
    record.update(extra)
    DISPATCH_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    try:
        with DISPATCH_LEDGER.open("a", encoding="utf-8") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass


def _pane_cooldown_file() -> Path:
    return _harness_dir() / "run" / "graph-dispatch-pane-cooldowns.json"


def _harness_sprints_dir() -> Path:
    return _harness_dir() / "sprints"


def _pane_cooldowns() -> dict[str, Any]:
    try:
        data = json.loads(_pane_cooldown_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_pane_cooldowns(data: dict[str, Any]) -> None:
    try:
        cooldown_file = _pane_cooldown_file()
        cooldown_file.parent.mkdir(parents=True, exist_ok=True)
        cooldown_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _parse_utc(ts: str) -> datetime.datetime | None:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        return None


def _cooldown_conflicts_with_live_lease(pane: str, entry: dict[str, Any]) -> bool:
    try:
        lease = read_lease(pane) or {}
    except Exception:
        lease = {}
    if not isinstance(lease, dict) or not lease:
        return False
    lease_dispatch_id = str(lease.get("dispatch_id") or "")
    lease_sid = str(lease.get("sid") or lease.get("sprint_id") or "")
    entry_dispatch_id = str(entry.get("dispatch_id") or "")
    entry_sid = str(entry.get("sid") or entry.get("sprint_id") or "")
    if lease_dispatch_id and entry_dispatch_id and lease_dispatch_id != entry_dispatch_id:
        return True
    if lease_sid and entry_sid and lease_sid != entry_sid:
        return True
    return False


def _cooldown_missing_runtime_context(entry: dict[str, Any]) -> bool:
    entry_sid = str(entry.get("sid") or entry.get("sprint_id") or "").strip()
    entry_dispatch_id = str(entry.get("dispatch_id") or "").strip()
    if not entry_sid and not entry_dispatch_id:
        return True
    if not entry_sid:
        return False
    graph_path = _harness_sprints_dir() / f"{entry_sid}.task_graph.json"
    return not graph_path.exists()


def _pane_cooldown_reason(pane: str) -> str:
    data = _pane_cooldowns()
    entry = data.get(pane)
    if not isinstance(entry, dict):
        return ""
    if (
        not _pane_exists(pane)
        or _cooldown_conflicts_with_live_lease(pane, entry)
        or _cooldown_missing_runtime_context(entry)
    ):
        data.pop(pane, None)
        _write_pane_cooldowns(data)
        return ""
    until = _parse_utc(str(entry.get("until") or ""))
    now = datetime.datetime.now(datetime.timezone.utc)
    if until is None or until <= now:
        data.pop(pane, None)
        _write_pane_cooldowns(data)
        return ""
    reason = str(entry.get("reason") or "pane_recover_cooldown")
    return f"pane_recover_cooldown:{reason}"


def _mark_pane_recover_cooldown(pane: str, reason: str, *, sid: str = "", dispatch_id: str = "") -> None:
    if not pane:
        return
    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=PANE_RECOVER_COOLDOWN_SEC)
    data = _pane_cooldowns()
    data[pane] = {
        "reason": reason or "recover_failed",
        "sid": sid,
        "dispatch_id": dispatch_id,
        "marked_at": _utc_now(),
        "until": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write_pane_cooldowns(data)
    _append_dispatch_ledger(
        "pane_recover_cooldown",
        sid,
        pane,
        dispatch_id,
        {"reason": reason, "cooldown_sec": PANE_RECOVER_COOLDOWN_SEC},
    )


def _mark_pane_recover_retryable(pane: str, reason: str, *, sid: str = "", dispatch_id: str = "") -> None:
    if not pane:
        return
    _append_dispatch_ledger(
        "pane_recover_retryable",
        sid,
        pane,
        dispatch_id,
        {"reason": reason},
    )


def _intent_telemetry_summary(instruction_file: Path) -> dict[str, Any]:
    sidecar = instruction_file.with_name(instruction_file.name + ".intent.json")
    if not sidecar.exists():
        return {"intent_telemetry_file": "", "intent_telemetry_missing": True}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"intent_telemetry_file": str(sidecar), "intent_telemetry_error": str(exc)}
    intent = data.get("intent") or {}
    matches = intent.get("matches") or []
    caps = data.get("capabilities") or []
    return {
        "instruction_file": data.get("dispatch_file", str(instruction_file)),
        "intent_telemetry_file": str(sidecar),
        "intent_matched": bool(intent.get("matched")),
        "intent_matches": [
            {
                "kind": m.get("kind"),
                "type": m.get("type"),
                "source": m.get("source"),
                "skill": m.get("skill"),
                "target": m.get("target"),
                "confidence": m.get("confidence"),
            }
            for m in matches
        ],
        "capability_providers": [c.get("provider") for c in caps],
        "worker_visible": data.get("worker_visible") or {},
        "effect_status": (data.get("effect") or {}).get("status", "pending_worker_evidence"),
        "effect": data.get("effect") or {},
    }


def _visibility_summary(instruction_file: Path) -> dict[str, str]:
    sidecar = instruction_file.with_name(instruction_file.name + ".intent.json")
    if not sidecar.exists():
        return {
            "text": "Solar能力: intent=N/A | caps=N/A | effect=N/A",
            "title": "能力:N/A",
        }
    summary = _intent_telemetry_summary(instruction_file)
    intent_labels: list[str] = []
    for m in summary.get("intent_matches", []):
        label = m.get("skill") or m.get("target") or m.get("type") or m.get("source")
        if label:
            intent_labels.append(str(label))
    cap_labels = [str(x) for x in summary.get("capability_providers", []) if x]

    def short(value: str, limit: int) -> str:
        return value if len(value) <= limit else value[: max(0, limit - 1)] + "…"

    intent_text = ",".join(short(x, 22) for x in intent_labels[:3]) if intent_labels else "N/A"
    cap_text = ",".join(short(x, 22) for x in cap_labels[:4]) if cap_labels else "N/A"
    effect = short(str(summary.get("effect_status") or "pending_worker_evidence"), 20)
    title_parts: list[str] = []
    if intent_labels:
        title_parts.append("I:" + ",".join(short(x, 10) for x in intent_labels[:2]))
    if cap_labels:
        title_parts.append("C:" + ",".join(short(x, 10) for x in cap_labels[:3]))
    return {
        "text": f"Solar能力: intent={intent_text} | caps={cap_text} | effect={effect}",
        "title": " | ".join(title_parts) if title_parts else "能力:N/A",
    }


def _set_pane_capability_title(pane: str, instruction_file: Path) -> None:
    try:
        current = subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane, "#{pane_title}"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        base = re.sub(r"\s+\|\s+能力:.*$", "", current) or pane
        title = _visibility_summary(instruction_file)["title"]
        subprocess.run(["tmux", "select-pane", "-t", pane, "-T", f"{base} | 能力:{title}"], timeout=2)
    except Exception:
        pass


def _inject_dispatch_context(instruction_file: Path, sid: str = "", pane: str = "", dispatch_id: str = "") -> None:
    """Fail-open Solar skills/KB/capability context injection for DAG dispatch files."""
    injector = HARNESS_DIR / "lib" / "solar_skills.py"
    if not instruction_file.exists():
        return
    if injector.exists():
        try:
            subprocess.run(
                [sys.executable, str(injector), "inject", str(instruction_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
                env=_broker_env(sid),
            )
        except Exception:
            pass
    runtime_injector = HARNESS_DIR / "lib" / "runtime_context_inject.py"
    if sid and dispatch_id and runtime_injector.exists():
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(runtime_injector),
                    str(instruction_file),
                    "--session-id",
                    sid,
                    "--pane",
                    pane or "unknown",
                    "--dispatch-id",
                    dispatch_id,
                    "--budget-tokens",
                    "1800",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
                env=_broker_env(sid),
            )
        except Exception:
            pass
    if sid and dispatch_id:
        _append_dispatch_ledger(
            "intent_injected",
            sid,
            pane or "unknown",
            dispatch_id,
            _intent_telemetry_summary(instruction_file),
        )


def _lease_active_for(pane: str, sid: str, dispatch_id: str) -> bool:
    lease = read_lease(pane)
    if not lease:
        return False
    return (
        lease.get("sprint_id", lease.get("sid")) == sid
        and lease.get("dispatch_id") == dispatch_id
        and lease.get("expires_at", "") > _utc_now()
    )


def _pane_has_active_lease(pane: str) -> bool:
    lease = read_lease(pane)
    if not lease or lease.get("expires_at", "") <= _utc_now():
        return False
    tail = _pane_tail(pane)
    bottom = "\n".join(tail.splitlines()[-12:])
    if PANE_DISPATCH_FAILED_IDLE_RE.search(tail) and not PANE_TUI_BUSY_RE.search(bottom):
        release_lease(
            pane,
            str(lease.get("dispatch_id") or ""),
            "active_lease_released_after_idle_api_timeout",
        )
        return False
    return True


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_node_runstate(sid: str, node_id: str, fields: dict[str, Any]) -> None:
    """Persist durable per-node eval/repair state next to the sprint (best-effort).

    Surfaces repair_attempt / max / eval_dispatch_failures / last verdict+reason / next_action / status in
    one file per node, so a stuck node is provable from disk instead of grepping hundreds of events."""
    try:
        import node_runstate

        node_runstate.record(SPRINTS_DIR, sid, node_id, "eval_state", fields)
    except Exception:
        pass


def _record_node_attribution(sid: str, node_id: str, fields: dict[str, Any]) -> None:
    """Persist graph-dispatch operator-pool attribution next to the sprint.

    multi_task_runner writes attribution for multi-task workers; graph_node_dispatcher also dispatches
    builders/evaluators through pm_dispatch/operator_runtime. Without this record, a live node can run
    on Codex while the durable node-keyed runstate remains empty or stale.
    """
    try:
        import node_runstate

        node_runstate.record(SPRINTS_DIR, sid, node_id, "attribution", fields)
    except Exception:
        pass


def _physical_operator_spec(operator_id: str) -> dict[str, Any]:
    try:
        registry = json.loads((HARNESS_DIR / "config" / "physical-operators.json").read_text(encoding="utf-8"))
        operators = registry.get("operators") if isinstance(registry.get("operators"), dict) else {}
        spec = operators.get(str(operator_id or ""))
        return dict(spec) if isinstance(spec, dict) else {}
    except Exception:
        return {}


def _operator_runstate_fields(
    *,
    operator_id: str,
    role: str,
    dispatch_id: str,
    parsed: dict[str, Any],
    instruction_file: Path,
    dispatch_mode: str,
) -> dict[str, Any]:
    spec = _physical_operator_spec(operator_id)
    provider = spec.get("provider") or spec.get("vendor")
    return {
        "phase": "dispatched",
        "role": role,
        "dispatch_id": dispatch_id,
        "dispatch_mode": dispatch_mode,
        "pm_task_id": parsed.get("pm_task_id") or parsed.get("task_id"),
        "operator_id": operator_id,
        "profile": spec.get("profile"),
        "backend": spec.get("backend"),
        "provider": str(provider).strip().lower() if provider else None,
        "vendor": spec.get("vendor"),
        "model": spec.get("model"),
        "instruction_file": str(instruction_file),
        "exit_code": None,
    }


def _append_event(sid: str, event: dict[str, Any]) -> None:
    event_file = SPRINTS_DIR / f"{sid}.events.jsonl"
    event = dict(event)
    event.setdefault("ts", _utc_now())
    event.setdefault("sid", sid)
    try:
        with event_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass
    if record_legacy_event is not None:
        try:
            payload = event.get("data") if isinstance(event.get("data"), dict) else dict(event)
            record_legacy_event(
                sid,
                str(event.get("event") or "graph_event"),
                str(event.get("by") or event.get("actor") or "graph-dispatch"),
                payload,
                harness_dir=HARNESS_DIR,
            )
        except Exception:
            pass


def _mark_parent_sprint_passed_if_ready(sid: str, parent: dict[str, Any], dry_run: bool) -> bool:
    if dry_run or not parent.get("ready"):
        return False
    status_file = SPRINTS_DIR / f"{sid}.status.json"
    if not status_file.exists():
        return False
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        return False

    now = _utc_now()
    if transition_status is not None:
        transition_status(
            status_file,
            "passed",
            "graph_parent_ready_passed",
            "graph-dispatch",
            extra={
                "status_fields": {
                    "phase": "completed",
                    "handoff_to": "done",
                    "target_role": "done",
                    "completed_at": now,
                    "graph_parent_ready": parent,
                },
                "note": "All DAG nodes and required gates passed via parent_ready_check.",
            },
        )
    else:
        history = data.get("history")
        if not isinstance(history, list):
            history = []
        history.append({
            "ts": now,
            "event": "graph_parent_ready_passed",
            "by": "graph-dispatch",
            "note": "All DAG nodes and required gates passed via parent_ready_check.",
        })
        data.update({
            "status": "passed",
            "phase": "completed",
            "handoff_to": "done",
            "target_role": "done",
            "updated_at": now,
            "completed_at": now,
            "graph_parent_ready": parent,
            "history": history,
        })
        status_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _append_event(sid, {
        "event": "graph_parent_ready_passed",
        "by": "graph-dispatch",
        "data": {"node_count": parent.get("node_count"), "required_gates": parent.get("required_gates", [])},
    })
    return True


def _ensure_lease(pane: str, sid: str, dispatch_id: str, ttl: int, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"acquired": True, "dry_run": True}
    if _lease_active_for(pane, sid, dispatch_id):
        return {"acquired": True, "existing": True}
    return acquire_lease(pane, sid, dispatch_id, ttl)


def _builder_operator_pool_enabled() -> bool:
    return str(os.environ.get("SOLAR_GRAPH_BUILDER_OPERATOR_POOL", "0")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _builder_operator_pool_allowed_for_pane(pane: str) -> bool:
    if str(os.environ.get("SOLAR_GRAPH_BUILDER_OPERATOR_POOL_ALL_PANES", "")).strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }:
        return True
    return (
        pane.startswith("operator-pool:builder")
        or _pane_in_lab_session(pane)
        or _pane_in_multi_task_session(pane)
    )


def _builder_operator_pool_available_count() -> int:
    if not _builder_operator_pool_enabled():
        return 0
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
                "builder-pool-status",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            env=_broker_env(),
        )
    except Exception:
        return 0
    if completed.returncode != 0:
        return 0
    try:
        data = json.loads(completed.stdout)
    except Exception:
        return 0
    try:
        available = int(data.get("total_available") or 0)
    except Exception:
        available = 0
    if available <= 0:
        groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
        for group in groups.values():
            if not isinstance(group, dict):
                continue
            try:
                available += int(group.get("available") or 0)
            except Exception:
                pass
    return max(0, available)


def _eval_operator_pool_enabled() -> bool:
    """Whether eval may dispatch to an operator-pool (operatord) evaluator.

    True if the broad builder operator pool is on, OR the eval-only flag is set. The eval-only flag lets a
    multi-task DAG (whose nodes finish in `reviewing` with no cockpit evaluator pane) get an evaluator from
    the operatord pool WITHOUT also turning on operator-pool builders (which would change build dispatch).
    Default off (component-gated)."""
    if _builder_operator_pool_enabled():
        return True
    return str(os.environ.get("SOLAR_GRAPH_EVAL_OPERATOR_POOL", "0")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
        "",
    }


def _operator_pool_role_available(role: str) -> bool:
    enabled = _eval_operator_pool_enabled() if str(role).strip().lower() == "evaluator" else _builder_operator_pool_enabled()
    if not enabled:
        return False
    cmd = [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "submit",
        "--role",
        role,
        "--sprint",
        "graph-dispatch-capacity-probe",
        "--node",
        "CAPACITY",
        "--objective",
        f"capacity probe for graph-dispatch {role}",
        "--dry-run",
    ]
    env = _broker_env()
    env["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=8, env=env)
    except Exception:
        return False
    return completed.returncode == 0 and "operator_id" in completed.stdout


def _builder_operator_pool_workers(
    worker_skills: list[str],
    worker_capabilities: list[str],
) -> list[dict[str, Any]]:
    available = _builder_operator_pool_available_count()
    if available <= 0:
        return []
    try:
        limit = int(os.environ.get("SOLAR_GRAPH_BUILDER_OPERATOR_POOL_SLOTS", "0") or "0")
    except Exception:
        limit = 0
    slots = min(available, limit) if limit > 0 else available
    models = [
        "operator-pool",
        "sonnet",
        "glm-5.1",
        "deepseek-v4-flash",
        "gpt-5.5",
        "thunderomlx",
        "gemini-3.5-flash",
    ]
    workers: list[dict[str, Any]] = []
    for idx in range(max(0, slots)):
        worker = {
            "pane": f"operator-pool:builder.{idx}",
            "models": models,
            "skills": worker_skills,
            "capabilities": worker_capabilities,
            "role": "builder",
            "dispatch_role": "builder",
            "host_role": "operator_pool",
            "busy": False,
            "title": "operator pool builder",
            "unavailable_reason": "",
            "load": idx,
        }
        _flatten_actorhost_bridge(
            worker,
            {
                "actor_id": "N/A",
                "host_id": "operator-pool",
                "host_type": "operator_pool",
                "lease_state": "idle",
                "capability_match": {"required": worker_capabilities, "matched": [], "missing": [], "observed": []},
                "compat_fallback": False,
                "compat_maps_to": None,
                "resolution_source": "operator_pool_virtual",
                "canonical_host_type": True,
            },
        )
        workers.append(worker)
    return workers


def _evaluator_operator_pool_workers() -> list[dict[str, Any]]:
    if not _operator_pool_role_available("evaluator"):
        return []
    worker = {
            "pane": "operator-pool:evaluator.0",
            "models": ["operator-pool", "deepseek-v4-pro", "opus", "gpt-5.5"],
            "skills": ["review", "testing", "bash"],
            "busy": False,
            "title": "operator pool evaluator",
            "evaluator_host_role": "operator_pool",
            "unavailable_reason": "",
            "quota_exhausted": [],
            "rate_limit_operator_blocks": [],
            "current_command": "",
        }
    _flatten_actorhost_bridge(
        worker,
        {
            "actor_id": "N/A",
            "host_id": "operator-pool",
            "host_type": "operator_pool",
            "lease_state": "idle",
            "capability_match": {"required": ["review", "testing"], "matched": [], "missing": [], "observed": []},
            "compat_fallback": False,
            "compat_maps_to": None,
            "resolution_source": "operator_pool_virtual",
            "canonical_host_type": True,
        },
    )
    return [worker]


def _graph_queue_dispatch_role(payload: dict[str, Any], node: dict[str, Any], assignment: dict[str, Any]) -> str:
    raw = (
        assignment.get("dispatch_role")
        or payload.get("dispatch_role")
        or node.get("dispatch_role")
        or node.get("role")
        or "builder"
    )
    return str(raw or "builder").strip().lower()


def _graph_node_task_type(node: dict[str, Any]) -> str:
    for key in ("dispatch_task_type", "task_type", "type", "logical_operator"):
        value = str(node.get(key) or "").strip()
        if value:
            return value
    return "implementation"


def _parse_pm_submit_output(stdout: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    task_match = re.search(r"task_id\s*=\s*(\S+)", stdout)
    operator_match = re.search(r"operator\s*=\s*([^\s(]+)", stdout)
    dispatch_match = re.search(r"dispatch\s*=\s*(\S+)", stdout)
    result_match = re.search(r"result\s*=\s*(\S+)", stdout)
    if task_match:
        parsed["pm_task_id"] = task_match.group(1)
    if operator_match:
        parsed["operator_id"] = operator_match.group(1)
    if dispatch_match:
        parsed["pm_dispatch_file"] = dispatch_match.group(1)
    if result_match:
        parsed["pm_result_path"] = result_match.group(1)
    return parsed


def _actorhost_bridge(
    *,
    actor_id: str = "",
    operator_id: str = "",
    pane: str = "",
    required_capabilities: list[str] | None = None,
) -> dict[str, Any]:
    if resolve_actorhost_status is None:
        return {
            "actor_id": actor_id or operator_id or "N/A",
            "host_id": "N/A",
            "host_type": "unknown",
            "lease_state": "unknown",
            "capability_match": {"required": required_capabilities or [], "matched": [], "missing": required_capabilities or [], "observed": []},
            "compat_fallback": False,
            "compat_maps_to": None,
            "resolution_source": "resolver_unavailable",
            "canonical_host_type": False,
        }
    try:
        return resolve_actorhost_status(
            actor_id=actor_id,
            operator_id=operator_id,
            pane=pane,
            required_capabilities=required_capabilities or [],
        )
    except Exception as exc:
        return {
            "actor_id": actor_id or operator_id or "N/A",
            "host_id": "N/A",
            "host_type": "unknown",
            "lease_state": "unknown",
            "capability_match": {"required": required_capabilities or [], "matched": [], "missing": required_capabilities or [], "observed": []},
            "compat_fallback": False,
            "compat_maps_to": None,
            "resolution_source": f"resolver_error:{type(exc).__name__}",
            "canonical_host_type": False,
        }


def _flatten_actorhost_bridge(target: dict[str, Any], actorhost: dict[str, Any]) -> dict[str, Any]:
    target["actorhost"] = actorhost
    for key in ("actor_id", "host_id", "host_type", "lease_state"):
        target[key] = actorhost.get(key)
    target["capability_match"] = actorhost.get("capability_match")
    target["compat_fallback"] = bool(actorhost.get("compat_fallback"))
    return target


def _submit_builder_to_operator_pool(
    *,
    item: dict[str, Any],
    payload: dict[str, Any],
    sid: str,
    node: dict[str, Any],
    node_id: str,
    graph_path: str,
    pane: str,
    dispatch_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    if not _builder_operator_pool_enabled():
        return {"ok": False, "reason": "operator_pool_disabled"}

    assignment = payload.get("assignment") or {}
    if _graph_queue_dispatch_role(payload, node, assignment) != "builder":
        return {"ok": False, "reason": "not_builder_role"}
    if pane and not _builder_operator_pool_allowed_for_pane(pane):
        return {"ok": False, "reason": "operator_pool_not_enabled_for_pane"}

    instruction_file = _dispatch_file(sid, node_id)
    text_payload = dict(payload, dispatch_id=dispatch_id, sprint_id=sid)
    text_payload = _ensure_execution_plan_payload(text_payload, graph_path=graph_path, sid=sid, node=node)
    if node_id.startswith("R"):
        text_payload["research_node"] = True
        if node.get("fan_out_parent"):
            text_payload["section_isolation"] = True
            text_payload["section_id"] = node.get("section_id", "")
    instruction_file.parent.mkdir(parents=True, exist_ok=True)
    instruction_file.write_text(build_dispatch_text(text_payload, "operator-pool:builder"), encoding="utf-8")
    if not dry_run:
        _inject_dispatch_context(instruction_file, sid=sid, pane="operator-pool:builder", dispatch_id=dispatch_id)

    dispatch_preview = instruction_file.read_text(encoding="utf-8")
    if len(dispatch_preview) > 60000:
        dispatch_preview = (
            dispatch_preview[:60000]
            + "\n\n[TRUNCATED] Full graph dispatch instructions are in the file path above; read the file before acting."
        )
    objective = (
        "你是 graph-dispatch builder。请严格执行下面这个 DAG 节点分发文件；"
        "不要只总结，必须完成节点要求并按文件内的 graph node verdict/closeout 规则回写。\n\n"
        f"Graph dispatch file: {instruction_file}\n"
        f"Sprint: {sid}\n"
        f"Node: {node_id}\n"
        f"Original assigned pane fallback: {pane or 'N/A'}\n\n"
        "--- BEGIN GRAPH DISPATCH FILE ---\n"
        f"{dispatch_preview}"
        "\n--- END GRAPH DISPATCH FILE ---"
    )
    context = json.dumps(
        {
            "source": "graph_node_dispatcher",
            "graph": graph_path,
            "dispatch_id": dispatch_id,
            "original_assigned_pane": pane,
            "queue_item_id": item.get("id", ""),
        },
        ensure_ascii=False,
    )
    cmd = [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "submit",
        "--role",
        "builder",
        "--sprint",
        sid,
        "--node",
        node_id,
        "--task-type",
        _graph_node_task_type(node),
        "--objective",
        objective,
        "--context",
        context,
    ]
    if dry_run:
        cmd.append("--dry-run")
    env = _broker_env(sid)
    env["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"
    env.setdefault("SOLAR_PM_DISPATCH_SOURCE", "graph_node_dispatcher")

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=45, env=env)
    except Exception as exc:
        return {
            "ok": False,
            "reason": "operator_pool_submit_exception",
            "error": str(exc),
            "instruction_file": str(instruction_file),
        }
    if completed.returncode != 0:
        return {
            "ok": False,
            "reason": "operator_pool_submit_failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-1200:],
            "stderr": completed.stderr[-1200:],
            "instruction_file": str(instruction_file),
        }

    parsed = _parse_pm_submit_output(completed.stdout)
    operator_id = parsed.get("operator_id") or "unknown"
    operator_pane = f"operator:{operator_id}"
    actorhost = _actorhost_bridge(
        actor_id=operator_id,
        operator_id=operator_id,
        pane=operator_pane,
        required_capabilities=list(node.get("required_capabilities") or []),
    )
    if dry_run:
        return _flatten_actorhost_bridge({
            "ok": True,
            "node": node_id,
            "pane": operator_pane,
            "dispatch_id": dispatch_id,
            "instruction_file": str(instruction_file),
            "dispatch_mode": "operator_pool",
            "pm_dispatch": parsed,
            "dry_run": True,
            "graph_updated": False,
        }, actorhost)

    if pane:
        release_lease(pane, dispatch_id, "graph_dispatch_reassigned_to_operator_pool")
    _write_submit_ack(sid, node_id, operator_pane, dispatch_id)
    graph_updated = _mark_graph_node_compat(
        graph_path,
        node_id,
        "dispatched",
        pane=operator_pane,
        dispatch_id=dispatch_id,
    )
    try:
        graph = load_graph(graph_path)
        graph_node = _node_by_id(graph, node_id)
        if graph_node is not None:
            graph_node["operator_id"] = operator_id
            graph_node["pm_task_id"] = parsed.get("pm_task_id", "")
            graph_node["dispatched_via"] = "pm_dispatch"
            graph_node["updated_at"] = _utc_now()
            save_graph(graph_path, graph)
            graph_updated = True
    except Exception:
        pass
    _append_dispatch_ledger(
        "operator_pool_dispatched",
        sid,
        operator_pane,
        dispatch_id,
        {
            "node": node_id,
            "graph": graph_path,
            "pm_dispatch": parsed,
            "actorhost": actorhost,
            "instruction_file": str(instruction_file),
            "fallback_pane": pane,
        },
    )
    _record_node_attribution(
        sid,
        node_id,
        _operator_runstate_fields(
            operator_id=operator_id,
            role="builder",
            dispatch_id=dispatch_id,
            parsed=parsed,
            instruction_file=instruction_file,
            dispatch_mode="operator_pool",
        ),
    )
    _append_event(
        sid,
        {
            "event": "graph_builder_operator_pool_dispatched",
            "by": "graph-dispatch",
            "data": {
                "node": node_id,
                "operator_id": operator_id,
                "actor_id": actorhost.get("actor_id"),
                "host_id": actorhost.get("host_id"),
                "host_type": actorhost.get("host_type"),
                "lease_state": actorhost.get("lease_state"),
                "pm_task_id": parsed.get("pm_task_id", ""),
                "fallback_pane": pane,
                "dispatch_id": dispatch_id,
            },
        },
    )
    return _flatten_actorhost_bridge({
        "ok": True,
        "node": node_id,
        "pane": operator_pane,
        "dispatch_id": dispatch_id,
        "instruction_file": str(instruction_file),
        "dispatch_mode": "operator_pool",
        "pm_dispatch": parsed,
        "dry_run": False,
        "graph_updated": graph_updated,
    }, actorhost)


def _submit_eval_to_operator_pool(
    *,
    sid: str,
    node_id: str,
    graph_path: str,
    pane: str,
    dispatch_id: str,
    instruction_file: Path,
    dry_run: bool,
) -> dict[str, Any]:
    dispatch_preview = instruction_file.read_text(encoding="utf-8")
    if len(dispatch_preview) > 60000:
        dispatch_preview = (
            dispatch_preview[:60000]
            + "\n\n[TRUNCATED] Full graph eval dispatch instructions are in the file path above; read the file before acting."
        )
    objective = (
        "你是 graph-dispatch evaluator。请严格执行下面这个 DAG 节点评审文件；"
        "必须阅读 builder handoff/evidence，写入文件内要求的 eval.md/eval.json verdict，"
        "不要只写 PM result。\n\n"
        f"Graph eval dispatch file: {instruction_file}\n"
        f"Graph: {graph_path}\n"
        f"Sprint: {sid}\n"
        f"Node: {node_id}\n"
        f"Dispatch ID: {dispatch_id}\n"
        f"Original evaluator slot: {pane or 'N/A'}\n\n"
        "--- BEGIN GRAPH EVAL DISPATCH FILE ---\n"
        f"{dispatch_preview}"
        "\n--- END GRAPH EVAL DISPATCH FILE ---"
    )
    context = json.dumps(
        {
            "source": "graph_node_dispatcher",
            "graph": graph_path,
            "dispatch_id": dispatch_id,
            "original_assigned_pane": pane,
            "eval_dispatch_file": str(instruction_file),
        },
        ensure_ascii=False,
    )
    cmd = [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "submit",
        "--role",
        "evaluator",
        "--sprint",
        sid,
        "--node",
        node_id,
        "--task-type",
        "graph_eval",
        "--objective",
        objective,
        "--context",
        context,
    ]
    if dry_run:
        cmd.append("--dry-run")
    env = _broker_env(sid)
    env["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"
    env.setdefault("SOLAR_PM_DISPATCH_SOURCE", "graph_node_dispatcher")
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=45, env=env)
    except Exception as exc:
        return {
            "ok": False,
            "reason": "operator_pool_eval_submit_exception",
            "error": str(exc),
            "instruction_file": str(instruction_file),
        }
    if completed.returncode != 0:
        return {
            "ok": False,
            "reason": "operator_pool_eval_submit_failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-1200:],
            "stderr": completed.stderr[-1200:],
            "instruction_file": str(instruction_file),
        }
    parsed = _parse_pm_submit_output(completed.stdout)
    operator_id = parsed.get("operator_id") or "unknown"
    if not dry_run:
        _record_node_attribution(
            sid,
            node_id,
            _operator_runstate_fields(
                operator_id=operator_id,
                role="evaluator",
                dispatch_id=dispatch_id,
                parsed=parsed,
                instruction_file=instruction_file,
                dispatch_mode="operator_pool_eval",
            ),
        )
    return {
        "ok": True,
        "pane": f"operator:{operator_id}",
        "operator_id": operator_id,
        "pm_dispatch": parsed,
        "instruction_file": str(instruction_file),
        "dispatch_mode": "operator_pool_eval",
        "dry_run": dry_run,
    }


def dispatch_queue_item(item: dict[str, Any], dry_run: bool = False, ttl: int = 900) -> dict[str, Any]:
    payload = item.get("payload") or {}
    sid = payload.get("sprint_id") or item.get("sprint_id") or item.get("sid") or ""
    node = payload.get("node") or {}
    node_id = node.get("id") or _node_id_from_intent(item.get("intent", ""))
    assignment = payload.get("assignment") or {}
    pane = assignment.get("pane") or payload.get("pane") or ""
    graph_path = payload.get("graph") or str(SPRINTS_DIR / f"{sid}.task_graph.json")
    dispatch_id = payload.get("dispatch_id") or f"graph-{sid}-{node_id}"

    if not sid or not node_id:
        return {"ok": False, "reason": "invalid_graph_queue_item", "item": item}
    runtime_state = _graph_node_runtime_state(graph_path, node_id)
    current_status = str(runtime_state.get("status") or "")
    current_dispatch_id = str(runtime_state.get("dispatch_id") or "")
    human_handoff = _prepare_human_search_handoff(sid, graph_path, node, dry_run=dry_run)
    if human_handoff is not None:
        return human_handoff
    use_operator_pool = (
        current_status in {"assigned", "pending", "queued"}
        and (not current_dispatch_id or current_dispatch_id == dispatch_id)
        and (not pane or str(pane).startswith("operator-pool:"))
    )
    if use_operator_pool:
        pool_result = _submit_builder_to_operator_pool(
            item=item,
            payload=payload,
            sid=sid,
            node=node,
            node_id=node_id,
            graph_path=graph_path,
            pane=pane,
            dispatch_id=dispatch_id,
            dry_run=dry_run,
        )
        if pool_result.get("ok"):
            return pool_result
        if pool_result.get("reason") not in {
            "operator_pool_disabled",
            "operator_pool_not_enabled_for_pane",
            "not_builder_role",
        }:
            _append_dispatch_ledger(
                "operator_pool_fallback_to_pane",
                sid,
                pane or "unknown",
                dispatch_id,
                {"node": node_id, "reason": pool_result.get("reason"), "detail": pool_result},
            )
            if str(pane).startswith("operator-pool:"):
                if not dry_run:
                    enqueue(sid, item.get("intent", f"graph_node|node_id={node_id}"), item.get("priority", 80), payload)
                    _mark_graph_node(graph_path, node_id, "pending", clear_assignment=True)
                return {
                    "ok": False,
                    "reason": str(pool_result.get("reason") or "operator_pool_submit_failed"),
                    "node": node_id,
                    "pane": pane,
                    "operator_pool": pool_result,
                    "requeued": not dry_run,
                }
    if not pane:
        return {"ok": False, "reason": "missing_assigned_pane", "node": node_id}
    if current_status in {"assigned", "dispatched", "in_progress", "running"} and current_dispatch_id == dispatch_id:
        instruction_file = _dispatch_file(sid, node_id)
        if _pane_tui_busy(pane):
            if _pane_has_matching_queued_prompt(pane, instruction_file):
                sent = _send_to_pane(pane, instruction_file, dry_run, sid=sid, dispatch_id=dispatch_id)
                if sent:
                    if not dry_run:
                        _write_submit_ack(sid, node_id, pane, dispatch_id)
                    return {
                        "ok": True,
                        "reason": "matching_queued_prompt_submitted",
                        "node": node_id,
                        "pane": pane,
                        "dispatch_id": dispatch_id,
                        "instruction_file": str(instruction_file),
                    }
            if dry_run:
                return {
                    "ok": True,
                    "reason": "pane_busy_retry_later",
                    "node": node_id,
                    "pane": pane,
                    "dispatch_id": dispatch_id,
                    "instruction_file": str(instruction_file),
                    "requeued": False,
                    "graph_updated": False,
                    "dry_run": True,
                }
            _mark_graph_node(graph_path, node_id, "pending", clear_assignment=True)
            _mark_pane_recover_cooldown(
                pane,
                "existing_dispatch_pane_busy_retry_later",
                sid=sid,
                dispatch_id=dispatch_id,
            )
            return {
                "ok": True,
                "reason": "pane_busy_retry_later",
                "node": node_id,
                "pane": pane,
                "dispatch_id": dispatch_id,
                "instruction_file": str(instruction_file),
                "requeued": False,
            }
    if current_status in {"passed", "failed", "skipped", "reviewing", "waiting_human_search"}:
        return {
            "ok": True,
            "reason": "stale_graph_item_node_not_dispatchable",
            "node": node_id,
            "status": current_status,
            "dispatch_id": dispatch_id,
        }
    if current_status in {"assigned", "dispatched", "in_progress", "running"} and current_dispatch_id and current_dispatch_id != dispatch_id:
        return {
            "ok": True,
            "reason": "stale_graph_item_superseded",
            "node": node_id,
            "status": current_status,
            "current_dispatch_id": current_dispatch_id,
            "stale_dispatch_id": dispatch_id,
        }
    if not dry_run and not _pane_exists(pane):
        enqueue(sid, item.get("intent", f"graph_node|node_id={node_id}"), item.get("priority", 80), payload)
        _mark_graph_node(graph_path, node_id, "pending", clear_assignment=True)
        return {"ok": False, "reason": "pane_missing", "node": node_id, "pane": pane, "requeued": True}

    if not dry_run:
        unavailable_reason = _assigned_pane_unavailable_reason(pane)
        if unavailable_reason:
            marker = _mark_pane_recover_retryable if _recoverable_pane_blocker(unavailable_reason) else _mark_pane_recover_cooldown
            marker(pane, f"assigned_pane_unavailable:{unavailable_reason}", sid=sid, dispatch_id=dispatch_id)
            _mark_graph_node(graph_path, node_id, "pending", clear_assignment=True)
            return {
                "ok": True,
                "reason": "assigned_pane_unavailable_retry_later",
                "unavailable_reason": unavailable_reason,
                "node": node_id,
                "pane": pane,
                "dispatch_id": dispatch_id,
                "requeued": False,
            }

    lease_result = _ensure_lease(pane, sid, dispatch_id, ttl, dry_run)
    if not lease_result.get("acquired"):
        enqueue(sid, item.get("intent", f"graph_node|node_id={node_id}"), item.get("priority", 80), payload)
        _mark_graph_node(graph_path, node_id, "pending", clear_assignment=True)
        return {
            "ok": False,
            "reason": lease_result.get("reason", "lease_failed"),
            "node": node_id,
            "pane": pane,
            "lease": lease_result,
            "requeued": True,
        }

    text_payload = dict(payload, dispatch_id=dispatch_id, sprint_id=sid)
    text_payload = _ensure_execution_plan_payload(text_payload, graph_path=graph_path, sid=sid, node=node)
    actorhost = _actorhost_bridge(
        pane=pane,
        required_capabilities=list(node.get("required_capabilities") or []),
    )
    text_payload["actorhost"] = actorhost
    for key in ("actor_id", "host_id", "host_type", "lease_state"):
        text_payload[key] = actorhost.get(key)
    # Research node branch: mark fan-out section isolation for R-prefixed nodes
    # from deepresearch DAG templates. No main-loop edits; this is a single
    # if-branch that enriches the payload before dispatch text generation.
    if node_id.startswith("R"):
        text_payload["research_node"] = True
        if node.get("fan_out_parent"):
            text_payload["section_isolation"] = True
            text_payload["section_id"] = node.get("section_id", "")
    instruction_file = _dispatch_file(sid, node_id)
    instruction_file.parent.mkdir(parents=True, exist_ok=True)
    instruction_file.write_text(build_dispatch_text(text_payload, pane), encoding="utf-8")
    if not dry_run:
        _inject_dispatch_context(instruction_file, sid=sid, pane=pane, dispatch_id=dispatch_id)
    if dry_run:
        return _flatten_actorhost_bridge({
            "ok": True,
            "node": node_id,
            "pane": pane,
            "dispatch_id": dispatch_id,
            "instruction_file": str(instruction_file),
            "dry_run": True,
            "graph_updated": False,
        }, actorhost)

    sent = _send_to_pane(pane, instruction_file, dry_run, sid=sid, dispatch_id=dispatch_id)
    graph_updated = False
    if sent:
        if not dry_run:
            _write_submit_ack(sid, node_id, pane, dispatch_id)
            try:
                graph = load_graph(graph_path)
                set_node_status(graph, node_id, "dispatched", pane=pane, dispatch_id=dispatch_id)
                save_graph(graph_path, graph)
                graph_updated = True
            except Exception:
                graph_updated = False
        return _flatten_actorhost_bridge({
            "ok": True,
            "node": node_id,
            "pane": pane,
            "dispatch_id": dispatch_id,
            "instruction_file": str(instruction_file),
            "dry_run": dry_run,
            "graph_updated": graph_updated,
        }, actorhost)

    if not dry_run:
        release_lease(pane, dispatch_id, "graph_dispatch_send_failed")
    if _pane_tui_busy(pane):
        # The pane is already doing work, compacting, or carrying queued prompt
        # residue. Do not keep an unsent node in assigned/dispatched state:
        # that strands the node forever. Also do not requeue immediately,
        # because that creates duplicate prompt lines. Leave it pending so the
        # next scheduler cycle can pick any then-idle worker.
        _mark_graph_node(graph_path, node_id, "pending", clear_assignment=True)
        _mark_pane_recover_cooldown(
            pane,
            "send_failed_pane_busy_retry_later",
            sid=sid,
            dispatch_id=dispatch_id,
        )
        return {
            "ok": True,
            "reason": "pane_busy_retry_later",
            "node": node_id,
            "pane": pane,
            "instruction_file": str(instruction_file),
            "dispatch_id": dispatch_id,
            "requeued": False,
        }
    enqueue(sid, item.get("intent", f"graph_node|node_id={node_id}"), item.get("priority", 80), payload)
    _mark_graph_node(graph_path, node_id, "pending", clear_assignment=True)
    _mark_pane_recover_cooldown(
        pane,
        "send_failed_requeued",
        sid=sid,
        dispatch_id=dispatch_id,
    )
    return {
        "ok": False,
        "reason": "send_failed",
        "node": node_id,
        "pane": pane,
        "instruction_file": str(instruction_file),
        "requeued": True,
    }


def drain_queue(sprint_id: str, dry_run: bool = False, max_items: int = 0, ttl: int = 900) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    processed = 0
    while True:
        if max_items and processed >= max_items:
            break
        item = _pop_graph_queue_item(sprint_id)
        if item is None:
            break
        results.append(dispatch_queue_item(item, dry_run=dry_run, ttl=ttl))
        processed += 1
    return {
        "ok": all(r.get("ok") for r in results) if results else True,
        "sprint_id": sprint_id,
        "processed": processed,
        "results": results,
    }


def _discover_workers(dry_run: bool = False) -> list[dict[str, Any]]:
    _prune_expired_operator_blocks()
    worker_skills = [
        "bash", "shell", "python", "python-read", "dataclasses", "pytest", "subprocess", "ffmpeg", "sqlite", "sqlite3", "pure-functions", "time-injection", "timeouts", "concurrency", "io", "fsm", "integration", "integration-testing", "integration-tests", "regression", "regression-tests", "bash-tests", "jq", "json", "json-patch", "jsonl-tail", "typescript", "docs", "testing",
        "http-testing", "negative-testing", "activation-proof", "knowledge-ingest", "release-gate", "documentation",
        "solar-harness-verification", "solar-harness-compat-review", "harness.verification", "verification",
        "stub-llm", "e2e-test", "cli-view-assertion", "negative-control", "verifier", "registry-introspection",
        "technical-writing", "markdown", "regex", "markdown-parse", "pandoc", "evidence-aggregation", "handoff-authoring", "traceability-patch", "knowledge-raw-writeback",
        "architecture-writing", "solar-harness-control-plane", "algorithm_design",
        "frontend", "observability", "ui", "terminal-ui", "tvs", "vdl", "snapshot", "snapshot-testing", "flask", "http", "curl", "http-routing", "http-endpoint", "autopilot-hooks", "json-traversal", "html", "jinja", "javascript", "vanilla-dom",
        "security", "grep", "secret-scan", "code-audit",
        "deepresearch", "cli", "cli-audit", "cli-design", "argparse", "argparse-bridge", "json-schema", "json-shape-inspect", "validation", "claude-cli", "survey", "fixture", "release", "evidence", "evidence-collection", "evaluator-summary", "autopilot", "epic",
        "product", "planning", "optimization", "runtime_design", "workflow.planning", "governance", "risk", "risk-register",
        "architecture", "schema", "state-machine", "state-schema-design", "distributed-systems",
        "code-audit", "docs-audit", "type-hints", "type-protocols", "refactor", "tmux-inspect", "data-aggregation", "shutil", "urllib", "atomic-writes", "hashing", "unittest-mock",
        "api-design", "data-modeling", "data.modeling", "compatibility", "compat-review",
        "spec.write", "provider.contract", "agent.inventory",
        "command.catalog", "rules.catalog",
        "scheduler.design", "algorithm", "state-machine.design",
        "routing", "diagnostics", "evaluation", "capability-graph", "event-sourcing",
        "ai-rag-pipeline", "reporting",
        "lazy-import",
        "browser.browse", "browser.qa", "code.review", "document.convert",
        "browser", "browser.automation", "web", "scraping", "crawler", "collector",
        "social", "social.monitor", "social.signal", "social_links", "entity.extract", "link.extract", "url.extract", "cross_source.dispatch",
        "persona.agent", "multi_agent.research", "debug.systematic",
        "autoresearch.pane_optimizer", "autoresearch.issue_loop", "autoresearch.local_issue",
        "autoresearch.agent_iteration", "autoresearch.score_gate",
        "repair.pr-cot",
        "DeepArchitect", "ImplementationWorker", "Critic", "Verifier",
        "code_impl", "test_generation", "test_execution",
    ]
    worker_capabilities = [
        "bash", "python", "ffmpeg", "typescript", "docs", "testing",
        "frontend", "observability", "evidence",
        "solar-harness-verification", "solar-harness-compat-review", "harness.verification", "verification",
        "env-passthrough", "metrics", "quota", "quota-management", "quota_fallback", "quota.fallback",
        "harness.context_preflight", "harness.intent", "harness.dispatch_visibility", "harness.contracts",
        "harness.dag", "harness.status", "harness.model_routing", "model.routing",
        "cap.requirement-compiler-planner", "cap.requirement-compiler-implementation",
        "cap.requirement-compiler-verification", "cap.requirement-compiler-audit",
        "artifact.requirement_trace",
        "policy", "policy.verdict",
        "intent.match", "intent.audit", "dispatch.intent_telemetry",
        "models.show", "models.lab_matrix", "models.footer_labels",
        "context.inject", "wiki.status", "data_plane.audit",
        "dag.validate", "dag.ready_nodes", "dag.join_gate",
        "harness.testing", "harness.failure_recovery", "harness.autopilot",
        "harness.activation_proof", "harness.reporting", "harness.knowledge", "harness.contracts",
        "reporting", "ai-rag-pipeline",
        "lazy-import", "cli",
        "activation.proof", "negative_control", "runtime_artifacts",
        "autopilot.monitor", "autopilot.safe_apply", "pane.deadlock_detection",
        "documentation", "governance", "risk", "schema", "state-machine", "storage", "sources", "data-modeling", "data.modeling",
        "api-adapter", "api_adapter", "api.adapter", "api-design", "integration", "subprocess", "sqlite", "sqlite3",
        "browser.browse", "browser.qa", "code.review", "code-audit",
        "browser.mcp", "browser.automation", "browser.screenshot",
        "browser.localhost_test",
        "browser", "web", "web.capture", "scraping", "crawler", "collector",
        "social", "social.monitor", "social.signal", "social_links", "entity.extract", "link.extract", "url.extract", "cross_source.dispatch",
        "document.convert", "document.markdown_extract", "mcp.markitdown",
        "persona.agent", "agent.catalog", "specialist.routing",
        "multi_agent.research", "browser.agent_experiment", "document.toolkit",
        "agent.inventory", "command.catalog", "rules.catalog", "mcp.catalog",
        "codex.bridge", "codex.contract_ingest", "codex.review_handoff", "pane3.bridge",
        "repair.pr-cot", "failure.structured_repair", "routing.complexity_budget",
        "optimization", "runtime_design",
        "algorithm_design", "solar-harness-control-plane", "architecture-writing",
        "code_impl", "test_generation", "test_execution",
        "skill.methodology", "workflow.planning", "debug.systematic", "test.tdd",
        "architecture", "distributed-systems", "evaluation",
        "agents_sdk.design", "agents_sdk.guardrails", "agents_sdk.tracing",
        "agents_sdk.handoff_model",
        "ruflo.swarm", "ruflo.plugins", "ruflo.agent_catalog",
        "ruflo.memory", "ruflo.mcp", "ruflo.workflow_templates",
        "product.requirements", "research.scope_rewrite",
        "research.empirical_pipeline", "research.literature_review",
        "analysis.causal_inference",
        "research.source_matrix", "research.evidence.extract",
        "research.claim.mine", "research.citation.verify",
        "research.report.compile", "report.compile",
        "research.long_report_compiler", "research.report_ast",
        "scheduler.design", "algorithm", "state-machine.design",
        "autoresearch.pane_optimizer", "autoresearch.issue_loop", "autoresearch.local_issue",
        "autoresearch.agent_iteration", "autoresearch.score_gate",
        "schema_design", "fixture_design", "mapping_design",
        "compatibility_design", "feedback_design", "gate_design",
        "metric_design", "replay_design", "shell_design", "synthesis",
        "security_review",
    ]
    restrict_to_session = os.environ.get("SOLAR_GRAPH_DISPATCH_RESTRICT_SESSION") == "1"
    if dry_run and os.environ.get("SOLAR_GRAPH_DISPATCH_FAKE_WORKERS") == "1":
        if restrict_to_session:
            return []
        lab_session = str(os.environ.get("SOLAR_HARNESS_LAB_SESSION") or "").strip()
        if not lab_session:
            current_session = _current_harness_session()
            lab_session = "solar-harness-lab" if current_session == "solar-harness" else f"{current_session}-lab"
        fake_panes = [f"{lab_session}:0.{idx}" for idx in range(4)]
        return [
            {"pane": fake_panes[0], "models": _models_for_pane(fake_panes[0]), "skills": worker_skills, "capabilities": worker_capabilities, "role": "builder", "dispatch_role": "builder", "host_role": "builder"},
            {"pane": fake_panes[1], "models": _models_for_pane(fake_panes[1]), "skills": worker_skills, "capabilities": worker_capabilities, "role": "builder", "dispatch_role": "builder", "host_role": "builder"},
            {"pane": fake_panes[2], "models": _models_for_pane(fake_panes[2]), "skills": worker_skills, "capabilities": worker_capabilities, "role": "builder", "dispatch_role": "builder", "host_role": "builder"},
            {"pane": fake_panes[3], "models": _models_for_pane(fake_panes[3]), "skills": worker_skills, "capabilities": worker_capabilities, "role": "builder", "dispatch_role": "builder", "host_role": "builder"},
        ]
    try:
        out = subprocess.check_output(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}:#{window_index}.#{pane_index}\t#{pane_title}"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode()
        pane_rows = [p.rstrip("\n").split("\t", 1) for p in out.splitlines() if p.strip()]
    except Exception:
        pane_rows = []
    workers = []
    pane_rows.sort(key=lambda row: _pane_execution_priority((row[0].strip() if row else "")))
    for row in pane_rows:
        pane = row[0].strip()
        title = row[1].strip() if len(row) > 1 else ""
        dispatch_role = _dispatch_role_for_pane(pane, title)
        if restrict_to_session and not pane.startswith(f"{_current_harness_session()}:"):
            continue
        if not _pane_in_harness_session_scope(pane):
            continue
        if dispatch_role not in {"builder", "planner", "architect"}:
            continue
        # Unattended hung-pane recovery, before availability is sampled: a MAIN
        # cockpit builder pane wedged on a frozen turn (a processing spinner whose
        # elapsed-timer never advances) strands its assigned node — regardless of
        # whether worker discovery happens to read it busy and regardless of a
        # stale dispatch lease. The frozen-timer detection inside _recover_hung_pane
        # is the safety (a working turn advances its timer / streams), so we do NOT
        # gate on the fragile tui-busy/lease classification here.
        if pane.startswith(f"{_current_harness_session()}:"):
            _recover_hung_pane(pane)
        models = _models_for_pane(pane, title)
        tail = _pane_tail(pane)
        health = _pane_health(pane)
        quota_exhausted = _quota_exhausted_models(title, tail, health, models)
        rate_limit_blocks = _persist_pane_rate_limit_block(pane, title, tail, quota_exhausted) if quota_exhausted else []
        cooldown_reason = _pane_cooldown_reason(pane)
        if _pane_in_helper_session(pane):
            if not cooldown_reason:
                _clear_stale_prompt_residue(pane)
        current_command = _pane_current_command(pane)
        runtime_unavailable_reason = "" if cooldown_reason else _pane_runtime_unavailable_reason(pane, title)
        unavailable_reason = (
            cooldown_reason
            or
            _multi_task_direct_dispatch_unavailable_reason(pane, current_command=current_command)
            or runtime_unavailable_reason
            or _pane_unavailable_reason(pane)
            or ("rate_limit_or_api_error" if quota_exhausted else "")
        )
        worker = {
            "pane": pane,
            "models": models,
            "skills": worker_skills,
            "capabilities": worker_capabilities,
            "role": dispatch_role,
            "dispatch_role": dispatch_role,
            "host_role": dispatch_role,
            "busy": _pane_has_active_lease(pane) or _pane_tui_busy(pane) or bool(unavailable_reason),
            "title": title,
            "quota_exhausted": quota_exhausted,
            "rate_limit_operator_blocks": rate_limit_blocks,
            "health": health,
            "unavailable_reason": unavailable_reason,
            "current_command": current_command,
        }
        _flatten_actorhost_bridge(
            worker,
            _actorhost_bridge(pane=pane, required_capabilities=worker_capabilities),
        )
        workers.append(worker)
    if not dry_run:
        workers.extend(_builder_operator_pool_workers(worker_skills, worker_capabilities))
    workers.sort(key=lambda item: _pane_execution_priority(str(item.get("pane") or "")))
    return workers


def _discover_evaluators(dry_run: bool = False) -> list[dict[str, Any]]:
    _prune_expired_operator_blocks()
    if dry_run and os.environ.get("SOLAR_GRAPH_DISPATCH_FAKE_EVALUATORS") == "1":
        session = _current_harness_session()
        return [{"pane": f"{session}:0.3", "models": _models_for_pane(f"{session}:0.3"), "skills": ["review", "testing", "bash"]}]
    # Graph node evaluation mutates graph verdict state. Keep it on evaluator
    # personas only, but allow a pool of evaluator hosts instead of pinning the
    # runtime to one pane. Planning still decides whether a node may use a
    # single evaluator or require quorum semantics.
    restrict_to_session = os.environ.get("SOLAR_GRAPH_DISPATCH_RESTRICT_SESSION") == "1"
    candidates = [f"{_current_harness_session()}:0.3"]
    try:
        out = subprocess.check_output(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}:#{window_index}.#{pane_index}\t#{pane_title}"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode()
        pane_rows = [p.rstrip("\n").split("\t", 1) for p in out.splitlines() if p.strip()]
    except Exception:
        pane_rows = []
    for row in pane_rows:
        pane = row[0].strip()
        if not pane or pane in candidates:
            continue
        if restrict_to_session:
            if not pane.startswith(f"{_current_harness_session()}:"):
                continue
        elif not _pane_in_harness_session_scope(pane):
            continue
        candidates.append(pane)
    evaluators: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pane in candidates:
        if pane in seen:
            continue
        seen.add(pane)
        if _pane_exists(pane):
            title = _pane_title(pane)
            title_matches_evaluator = _pane_title_matches_role(pane, title, "evaluator")
            evaluator_spillover = _lab_builder_can_host_evaluator(pane, title)
            if not (title_matches_evaluator or evaluator_spillover):
                continue
            current_command = _pane_current_command(pane)
            cooldown_reason = _pane_cooldown_reason(pane)
            if _pane_in_helper_session(pane) and not cooldown_reason:
                _clear_stale_prompt_residue(pane)
            tail = _pane_tail(pane)
            models = _models_for_pane(pane, title)
            health = _pane_health(pane)
            quota_exhausted = _quota_exhausted_models(title, tail, health, models)
            rate_limit_blocks = _persist_pane_rate_limit_block(pane, title, tail, quota_exhausted) if quota_exhausted else []
            runtime_unavailable_reason = "" if cooldown_reason else _pane_runtime_unavailable_reason(pane, title)
            unavailable_reason = (
                _pane_hygiene_unavailable_reason(pane)
                or cooldown_reason
                or _multi_task_direct_dispatch_unavailable_reason(pane, current_command=current_command)
                or runtime_unavailable_reason
                or _pane_unavailable_reason(pane)
                or ("rate_limit_or_api_error" if quota_exhausted else "")
            )
            evaluators.append({
                "pane": pane,
                "models": models,
                "skills": ["review", "testing", "bash"],
                "busy": _pane_has_active_lease(pane) or _pane_tui_busy(pane) or bool(unavailable_reason),
                "title": title,
                "evaluator_host_role": "evaluator" if title_matches_evaluator else "lab_builder_spillover",
                "unavailable_reason": unavailable_reason,
                "quota_exhausted": quota_exhausted,
                "rate_limit_operator_blocks": rate_limit_blocks,
                "current_command": current_command,
            })
    if not dry_run:
        evaluators.extend(_evaluator_operator_pool_workers())
    evaluators.sort(key=lambda item: _pane_evaluator_priority(str(item.get("pane") or ""), str(item.get("title") or "")))
    return evaluators


def _node_eval_self_graded(sid: str, node_id: str) -> bool:
    """The node's eval.json was written by the EXECUTING agent itself (generation_mode=manual_node_eval)
    with no INDEPENDENT evaluator report (no non-empty {node}-eval.md and no {node}-eval-dispatch sidecar).
    A self-graded verdict must not stand in for a real evaluation -- the node still needs one dispatched
    to an independent evaluator (the eval-backfill false-positive vector)."""
    try:
        eval_md = _eval_md_file(sid, node_id)
        if eval_md.exists() and eval_md.stat().st_size > 0:
            return False
    except Exception:
        pass
    if _eval_dispatch_file(sid, node_id).exists() or any(
        SPRINTS_DIR.glob(f"{sid}.{_safe_node_id(node_id)}-eval-dispatch*.md")
    ):
        return False
    # A verdict (eval.json) exists but with no independent evaluator report -> self-graded/backfilled
    # regardless of how it was written (generation_mode varies / may be absent); the node still needs a
    # real evaluator dispatched.
    return _eval_json_file(sid, node_id).exists()


def _node_eval_needed(graph: dict[str, Any], sid: str, node: dict[str, Any], force: bool = False) -> bool:
    node_id = str(node.get("id") or "")
    if not node_id:
        return False
    repair_mode = bool(node.get("quality_gate_repair_requested_at")) and _node_requires_deepresearch_quality_gate(node)
    results = graph.get("node_results") or {}
    result = results.get(node_id) if isinstance(results, dict) else None
    result_status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
    if result_status == "passed":
        return False
    if result_status in {"failed", "skipped"} and not force:
        return False
    # A self-graded eval.json (executing agent wrote its own manual_node_eval, no independent report)
    # does NOT satisfy the eval requirement -- the node still needs a real evaluator dispatched.
    if (
        _eval_json_file(sid, node_id).exists()
        and not force
        and not repair_mode
        and not _node_eval_self_graded(sid, node_id)
    ):
        return False
    if not force:
        recovered: list[dict[str, Any]] = []
        recovered_at = ""
        for lease in list_leases():
            dispatch_id = str(lease.get("dispatch_id") or "")
            lease_sid = str(lease.get("sid") or lease.get("sprint_id") or "")
            if (
                not lease.get("_expired")
                and lease_sid == sid
                and f"-{node_id}-" in dispatch_id
                and dispatch_id.startswith(f"graph-eval-{sid}-")
            ):
                recovered.append(
                    {
                        "pane": str(lease.get("pane") or ""),
                        "dispatch_id": dispatch_id,
                        "role": "secondary",
                    }
                )
                recovered_at = str(lease.get("acquired_at") or recovered_at or _utc_now())
        if recovered:
            if recovered:
                recovered[0]["role"] = "primary"
            _store_eval_assignments(node, recovered, recovered_at or _utc_now())
            node["eval_recovered_from_lease"] = True
            return False
    if node.get("eval_dispatched_at") and not force:
        assignments = _node_eval_assignments(node)
        dispatched_at = _parse_utc(str(node.get("eval_dispatched_at") or ""))
        if assignments and dispatched_at:
            age = datetime.datetime.now(datetime.timezone.utc) - dispatched_at
            if age.total_seconds() < EVAL_RECOVER_SEC:
                return False
        lease_matches = False
        for assignment in assignments:
            pane = str(assignment.get("pane") or "")
            dispatch_id = str(assignment.get("dispatch_id") or "")
            lease = read_lease(pane) if pane else {}
            if (
                lease
                and str(lease.get("sid") or lease.get("sprint_id") or "") == sid
                and str(lease.get("dispatch_id") or "") == dispatch_id
            ):
                lease_matches = True
                break
        # If the graph says eval was dispatched but no eval artifact exists and
        # the evaluator lease is gone, the pane likely swallowed/stalled the
        # prompt. Treat it as retryable instead of permanently blocking.
        if lease_matches:
            return False
        _clear_eval_assignments(node)
        node["eval_retry_reason"] = "eval_dispatched_without_artifact_or_active_lease"
    # Use graph_scheduler.node_status so node_results (the durable scheduler
    # result map) and inline node.status do not drift. A node can be reviewing
    # in node_results while its static node entry still says pending; relying
    # on node.status alone makes evaluator dispatch skip real handoffs forever.
    status = node_status(graph, node_id)
    if status == "passed":
        return False
    if status in {"failed", "skipped"}:
        if not force:
            return False
        return bool(_existing_node_handoff(sid, node, graph))
    if repair_mode and status in {"reviewing", "dispatched", "in_progress", "running", ""}:
        return True
    return bool(_existing_node_handoff(sid, node, graph)) and status in {"reviewing", "dispatched", "in_progress", "running", ""}


def _first_available_evaluator(dry_run: bool = False) -> dict[str, Any] | None:
    for evaluator in _discover_evaluators(dry_run):
        pane = str(evaluator.get("pane", ""))
        if pane and not evaluator.get("busy"):
            return evaluator
    return None


def dispatch_node_evals(graph_path: str, dry_run: bool = False, ttl: int = 900,
                        force: bool = False, max_items: int = 0) -> dict[str, Any]:
    graph = load_graph(graph_path)
    sid = str(graph.get("sprint_id") or Path(graph_path).stem.replace(".task_graph", ""))
    dispatched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    used_evaluator_panes: set[str] = set()
    evaluators = _discover_evaluators(dry_run)

    for node in graph.get("nodes", []):
        if max_items and len(dispatched) >= max_items:
            break
        node_id = str(node.get("id") or "")
        if not _node_eval_needed(graph, sid, node, force=force):
            continue
        requested_plan = _plan_node_evaluation(graph, node)
        loop_evaluators = [
            {**item, "busy": bool(item.get("busy")) or str(item.get("pane") or "") in used_evaluator_panes}
            for item in evaluators
        ]
        requested_capacity = _evaluation_capacity_snapshot(requested_plan, loop_evaluators)
        requested_plan["capacity"] = requested_capacity
        runtime_plan = _runtime_fallback_evaluation_plan(requested_plan, requested_capacity)
        runtime_capacity = _evaluation_capacity_snapshot(runtime_plan, loop_evaluators)
        runtime_plan["capacity"] = runtime_capacity
        node["evaluation_plan_requested"] = requested_plan
        node["evaluation_plan_runtime"] = runtime_plan
        node["evaluation_plan"] = runtime_plan
        node["evaluation_plan_updated_at"] = _utc_now()
        if not runtime_capacity.get("available_evaluators"):
            skipped.append({
                "node": node_id,
                "reason": "no_available_evaluator",
                "evaluation_plan": runtime_plan,
            })
            break
        if not runtime_capacity.get("capacity_satisfied", False):
            skipped.append({
                "node": node_id,
                "reason": "insufficient_evaluator_capacity",
                "evaluation_plan": runtime_plan,
            })
            break
        if not runtime_capacity.get("quorum_dispatch_supported", True):
            skipped.append({
                "node": node_id,
                "reason": "multi_evaluator_quorum_not_implemented",
                "evaluation_plan": runtime_plan,
            })
            break
        if not runtime_capacity.get("dispatchable_now"):
            skipped.append({
                "node": node_id,
                "reason": "insufficient_evaluator_capacity",
                "evaluation_plan": runtime_plan,
            })
            break
        selected_panes = [
            str(pane)
            for pane in runtime_capacity.get("selected_panes", [])
            if str(pane)
        ]
        selected_evaluators = [
            item
            for item in loop_evaluators
            if not item.get("busy") and str(item.get("pane") or "") in selected_panes
        ]
        if len(selected_evaluators) < int(runtime_plan.get("required_evaluators") or 1):
            skipped.append({
                "node": node_id,
                "reason": "insufficient_selected_evaluators",
                "evaluation_plan": runtime_plan,
            })
            break
        total_evaluators = int(runtime_plan.get("required_evaluators") or 1)
        dispatch_group_id = f"graph-eval-{sid}-{node_id}-{_utc_now().replace(':', '').replace('-', '')}"
        planned_assignments: list[dict[str, Any]] = []
        for idx, evaluator in enumerate(selected_evaluators[:total_evaluators], start=1):
            pane = str(evaluator.get("pane") or "")
            if pane in used_evaluator_panes:
                skipped.append({
                    "node": node_id,
                    "reason": "evaluator_already_used_in_batch",
                    "pane": pane,
                    "evaluation_plan": runtime_plan,
                })
                planned_assignments = []
                break
            role = "primary" if idx == 1 else "secondary"
            eval_md_path = _eval_md_file(sid, node_id) if idx == 1 else _eval_peer_md_file(sid, node_id, idx)
            eval_json_path = _eval_json_file(sid, node_id) if idx == 1 else _eval_peer_json_file(sid, node_id, idx)
            planned_assignments.append(
                {
                    "pane": pane,
                    "dispatch_id": f"{dispatch_group_id}-q{idx}",
                    "role": role,
                    "index": idx,
                    "eval_md_path": str(eval_md_path),
                    "eval_json_path": str(eval_json_path),
                }
            )
        if not planned_assignments:
            break

        lease_results: list[dict[str, Any]] = []
        lease_failed = None
        for assignment in planned_assignments:
            if str(assignment["pane"]).startswith("operator-pool:"):
                lease_result = {"acquired": True, "reason": "operator_pool_virtual_pane"}
            else:
                lease_result = _ensure_lease(
                    str(assignment["pane"]),
                    sid,
                    str(assignment["dispatch_id"]),
                    min(ttl, EVAL_RECOVER_SEC),
                    dry_run,
                )
            lease_results.append(lease_result)
            if not lease_result.get("acquired"):
                lease_failed = {"assignment": assignment, "lease": lease_result}
                break
        if lease_failed:
            if not dry_run:
                for assignment, lease_result in zip(planned_assignments, lease_results):
                    if lease_result.get("acquired"):
                        release_lease(str(assignment["pane"]), str(assignment["dispatch_id"]), "graph_eval_dispatch_partial_lease_failed")
            skipped.append({
                "node": node_id,
                "pane": str(lease_failed["assignment"]["pane"]),
                "reason": lease_failed["lease"].get("reason", "lease_failed"),
                "lease": lease_failed["lease"],
                "evaluation_plan": runtime_plan,
            })
            continue

        if not dry_run:
            _emit_node_proof_sidecars(sid, node)

        canonical_eval_md = str(_eval_md_file(sid, node_id))
        canonical_eval_json = str(_eval_json_file(sid, node_id))
        sent_records: list[dict[str, Any]] = []
        send_failed = None
        for assignment in planned_assignments:
            pane = str(assignment["pane"])
            assigned_pane = pane
            peer_paths = [
                str(item["eval_json_path"])
                for item in planned_assignments
                if item["dispatch_id"] != assignment["dispatch_id"]
            ]
            instruction_file = _eval_dispatch_member_file(sid, node_id, int(assignment["index"]))
            instruction_file.parent.mkdir(parents=True, exist_ok=True)
            instruction_file.write_text(
                build_eval_dispatch_text(
                    graph,
                    graph_path,
                    node,
                    pane,
                    str(assignment["dispatch_id"]),
                    evaluator_role=str(assignment["role"]),
                    evaluator_index=int(assignment["index"]),
                    evaluator_total=total_evaluators,
                    eval_md_override=Path(str(assignment["eval_md_path"])),
                    eval_json_override=Path(str(assignment["eval_json_path"])),
                    peer_eval_json_paths=peer_paths,
                    canonical_eval_json_path=canonical_eval_json,
                    canonical_eval_md_path=canonical_eval_md,
                ),
                encoding="utf-8",
            )
            _inject_dispatch_context(instruction_file, sid=sid, pane=pane, dispatch_id=str(assignment["dispatch_id"]))
            if dry_run:
                used_evaluator_panes.add(assigned_pane)
                sent_records.append({
                    "node": node_id,
                    "pane": pane,
                    "dispatch_id": str(assignment["dispatch_id"]),
                    "instruction_file": str(instruction_file),
                    "evaluation_plan": runtime_plan,
                    "role": assignment["role"],
                    "dry_run": True,
                })
                continue
            if pane.startswith("operator-pool:evaluator"):
                submit_result = _submit_eval_to_operator_pool(
                    sid=sid,
                    node_id=node_id,
                    graph_path=graph_path,
                    pane=pane,
                    dispatch_id=str(assignment["dispatch_id"]),
                    instruction_file=instruction_file,
                    dry_run=dry_run,
                )
                sent = bool(submit_result.get("ok"))
                if sent:
                    pane = str(submit_result.get("pane") or pane)
                    assignment["pane"] = pane
            else:
                submit_result = {}
                sent = _send_to_pane(pane, instruction_file, dry_run, sid=sid, dispatch_id=str(assignment["dispatch_id"]))
            if not sent:
                send_failed = {"assignment": assignment, "instruction_file": str(instruction_file)}
                reason = str(submit_result.get("reason") or _pane_unavailable_reason(pane) or "eval_send_failed")
                if not str(assignment["pane"]).startswith("operator-pool:"):
                    marker = _mark_pane_recover_retryable if _recoverable_pane_blocker(reason) else _mark_pane_recover_cooldown
                    marker(pane, reason, sid=sid, dispatch_id=str(assignment["dispatch_id"]))
                used_evaluator_panes.add(assigned_pane)
                break
            _write_submit_ack(sid, node_id, pane, str(assignment["dispatch_id"]))
            used_evaluator_panes.add(assigned_pane)
            used_evaluator_panes.add(pane)
            sent_records.append({
                "node": node_id,
                "pane": pane,
                "dispatch_id": str(assignment["dispatch_id"]),
                "instruction_file": str(instruction_file),
                "evaluation_plan": runtime_plan,
                "role": assignment["role"],
            })
        if send_failed:
            if not dry_run:
                for assignment in planned_assignments:
                    release_lease(str(assignment["pane"]), str(assignment["dispatch_id"]), "graph_eval_dispatch_send_failed")
            _clear_eval_assignments(node)
            skipped.append({
                "node": node_id,
                "pane": str(send_failed["assignment"]["pane"]),
                "reason": "send_failed",
                "evaluation_plan": runtime_plan,
            })
            continue

        node["status"] = "reviewing"
        node["eval_dispatch_group_id"] = dispatch_group_id
        # A successful dispatch clears the consecutive-failure streak so a later transient
        # unavailability does not inherit an old count and escalate prematurely.
        node.pop("eval_dispatch_failures", None)
        node.pop("last_eval_dispatch_failure_reason", None)
        _store_eval_assignments(node, planned_assignments, _utc_now())
        _record_node_runstate(sid, node_id, {
            "eval_dispatch_failures": 0,
            "max_eval_dispatch_failures": GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES,
            "last_eval_result": "DISPATCHED",
            "last_eval_reason": "evaluator_dispatched",
            "next_action": "await_eval_verdict",
            "status": "reviewing",
        })
        for item in sent_records:
            dispatched.append(item)

    terminalized = _account_eval_dispatch_failures(graph, sid, skipped, dry_run)
    if not dry_run:
        save_graph(graph_path, graph)
    return {
        "ok": not skipped,
        "sprint_id": sid,
        "dispatched": dispatched,
        "skipped": skipped,
        "terminalized": terminalized,
    }


def _account_eval_dispatch_failures(
    graph: dict[str, Any],
    sid: str,
    skipped: list[dict[str, Any]],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """Count consecutive capacity-class eval-dispatch failures per node and, past the configured cap,
    escalate the node to a durable terminal `needs_human_review` instead of retrying silently forever.

    This is the fix for the Run D limbo (246x no_available_evaluator with the node stuck in `reviewing`).
    It never auto-passes or auto-fails -- it converts an invisible infinite retry into one clear human gate
    (a later human eval-verdict still reopens/closes the node normally). Gated by
    GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES (0 = unlimited/legacy). Records durable eval_state either way."""
    terminalized: list[dict[str, Any]] = []
    if dry_run or not skipped:
        return terminalized
    node_index = {str(node.get("id") or ""): node for node in graph.get("nodes", [])}
    max_fail = GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES
    for item in skipped:
        reason = str(item.get("reason") or "")
        node_id = str(item.get("node") or "")
        node = node_index.get(node_id)
        if node is None or reason not in _EVAL_STUCK_REASONS:
            continue
        failures = int(node.get("eval_dispatch_failures") or 0) + 1
        node["eval_dispatch_failures"] = failures
        node["last_eval_dispatch_failure_reason"] = reason
        node["last_eval_dispatch_failure_at"] = _utc_now()
        current = str(node_status(graph, node_id) or node.get("status") or "").strip().lower()
        next_action = "retry_eval_dispatch"
        if (
            max_fail > 0
            and failures >= max_fail
            and current not in {"passed", "failed", "skipped", "cancelled", "needs_human_review"}
        ):
            now = _utc_now()
            next_action = "connect_evaluator_or_submit_human_verdict"
            blocked_reason = f"eval_dispatch_unavailable:{reason}:{failures}_consecutive_failures"
            # Set node + node_results directly: graph_scheduler._status_rank ranks reviewing(4) above
            # needs_human_review(0), so set_node_status would refuse this transition. This mirrors the
            # direct-write pattern already used by _start_node_repair_from_eval_fail.
            node["status"] = "needs_human_review"
            node["eval_blocked_reason"] = blocked_reason
            node["next_action"] = next_action
            node["updated_at"] = now
            graph.setdefault("node_results", {})
            graph["node_results"][node_id] = {
                "status": "needs_human_review",
                "updated_at": now,
                "note": blocked_reason,
                "next_action": next_action,
            }
            _append_event(sid, {
                "event": "graph_eval_dispatch_escalated_to_human",
                "by": "graph-dispatch",
                "severity": "warn",
                "data": {
                    "node": node_id,
                    "reason": reason,
                    "consecutive_failures": failures,
                    "max_failures": max_fail,
                    "next_action": next_action,
                },
            })
            terminalized.append({"node": node_id, "status": "needs_human_review", "reason": blocked_reason})
        _record_node_runstate(sid, node_id, {
            "eval_dispatch_failures": failures,
            "max_eval_dispatch_failures": max_fail,
            "last_eval_result": "DISPATCH_FAILED",
            "last_eval_reason": reason,
            "next_action": node.get("next_action") or next_action,
            "status": str(node.get("status") or ""),
        })
    return terminalized


def dispatch_ready(graph_path: str, dry_run: bool = False, ttl: int = 900,
                   max_parallel: int | None = None) -> dict[str, Any]:
    if _no_dispatch_enabled() and not dry_run:
        return {"ok": False, "reason": "no_dispatch_flag", "graph": graph_path, "enqueue": {}, "drain": {}}
    graph = load_graph(graph_path)
    sid = graph.get("sprint_id") or Path(graph_path).stem.replace(".task_graph", "")
    effective_max_parallel = int(max_parallel) if max_parallel is not None else _effective_graph_max_parallel(8)
    reconciled: list[dict[str, Any]] = []
    if not dry_run:
        reconciled = _reconcile_existing_dispatches(graph, graph_path)
        if reconciled:
            save_graph(graph_path, graph)
    enqueue_result = enqueue_ready(
        graph,
        graph_path,
        _discover_workers(dry_run),
        max_parallel=effective_max_parallel,
        lease=not dry_run,
        ttl=ttl,
        dry_run=dry_run,
    )
    if not dry_run:
        save_graph(graph_path, graph)
    if dry_run:
        results = []
        for enqueued in enqueue_result.get("enqueued", []):
            payload = enqueued.get("payload")
            if not isinstance(payload, dict):
                continue
            results.append(dispatch_queue_item({
                "sprint_id": sid,
                "intent": f"graph_node|node_id={enqueued.get('node')}",
                "priority": 80,
                "payload": payload,
            }, dry_run=True, ttl=ttl))
        drain_result = {"ok": all(r.get("ok", False) for r in results), "processed": len(results), "results": results}
    else:
        drain_result = drain_queue(str(sid), dry_run=dry_run, max_items=len(enqueue_result.get("enqueued", [])), ttl=ttl)
    return {
        "ok": enqueue_result.get("ok") and drain_result.get("ok"),
        "reconciled": reconciled,
        "concurrency": {"graph_max_parallel": effective_max_parallel},
        "enqueue": enqueue_result,
        "drain": drain_result,
    }


def node_verdict(graph_path: str, node_id: str, verdict: str, reason: str = "",
                 eval_json: str = "", dry_run: bool = False, ttl: int = 900,
                 dispatch_downstream: bool = True) -> dict[str, Any]:
    graph = load_graph(graph_path)
    sid = str(graph.get("sprint_id") or Path(graph_path).stem.replace(".task_graph", ""))
    node = _node_by_id(graph, node_id)
    if not node:
        return {"ok": False, "reason": "unknown_node", "node": node_id}

    normalized = verdict.strip().lower()
    if normalized in {"pass", "passed", "ok"}:
        status = "passed"
    elif normalized in {"fail", "failed", "error"}:
        status = "failed"
    else:
        return {"ok": False, "reason": "invalid_verdict", "verdict": verdict}

    proof_gate: dict[str, Any] = {"required": False}
    if status == "passed":
        resolved_eval_json = eval_json or _eval_json_file(sid, node_id)
        if not Path(str(resolved_eval_json)).expanduser().exists():
            backfilled_eval = _maybe_backfill_eval_json_from_md(sid, node_id)
            if backfilled_eval is not None:
                resolved_eval_json = backfilled_eval
        observed_handoff = _existing_node_handoff(sid, node, graph) or _handoff_file(sid, node_id)
        if observed_handoff and not Path(str(resolved_eval_json)).expanduser().exists():
            return {
                "ok": False,
                "reason": "missing_eval_json_for_pass",
                "node": node_id,
                "status": "blocked",
                "eval_json": str(resolved_eval_json),
                "handoff_md": str(observed_handoff),
            }
        # Deterministic support sidecars before the proof gate. This emits
        # guard/resource/adapter bridge artifacts from real node outputs, so the
        # proof gate checks files rather than narrative claims.
        _emit_node_proof_sidecars(sid, node)
        proof_gate = _evaluate_proof_obligations(sid, node, eval_json=resolved_eval_json)
        if proof_gate.get("required") and not proof_gate.get("ok"):
            return {
                "ok": False,
                "reason": "proof_obligations_failed",
                "node": node_id,
                "status": "blocked",
                "eval_json": str(resolved_eval_json),
                "proof_gate": proof_gate,
            }

    research_quality_gate: dict[str, Any] = {"required": False}
    if status == "passed" and _node_requires_deepresearch_quality_gate(node):
        resolved_eval_json = eval_json or _eval_json_file(sid, node_id)
        research_quality_gate = {
            "required": True,
            **_deepresearch_quality_gate_from_eval(resolved_eval_json),
        }
        if not research_quality_gate.get("present"):
            research_quality_gate = {
                "required": True,
                **_deepresearch_quality_gate_auto_run(sid, node, resolved_eval_json),
            }
            if not research_quality_gate.get("present"):
                return {
                    "ok": False,
                    "reason": "missing_deepresearch_quality_gate",
                    "node": node_id,
                    "status": "blocked",
                    "eval_json": str(resolved_eval_json),
                    "required_field": "research_quality_gate",
                    "research_quality_gate": research_quality_gate,
                }
        if not research_quality_gate.get("ok"):
            return {
                "ok": False,
                "reason": "deepresearch_quality_gate_failed",
                "node": node_id,
                "status": "blocked",
                "eval_json": str(resolved_eval_json),
                "research_quality_gate": research_quality_gate,
            }

    note_parts = []
    if reason:
        note_parts.append(reason)
    if eval_json:
        note_parts.append(f"eval_json={eval_json}")
    eval_assignments = _node_eval_assignments(node)
    if status == "failed":
        resolved_eval_json = str(eval_json or _eval_json_file(sid, node_id))
        eval_payload = _read_json_file_safe(resolved_eval_json)
        if reason and not str(eval_payload.get("summary") or "").strip():
            eval_payload["summary"] = reason
        observed_handoff = _existing_node_handoff(sid, node, graph) or _handoff_file(sid, node_id)
        if observed_handoff and Path(observed_handoff).exists():
            worker_pane = str(node.get("assigned_to") or "")
            worker_dispatch_id = str(node.get("dispatch_id") or "")
            repair_context = _start_node_repair_from_eval_fail(
                graph,
                node,
                sid,
                node_id,
                Path(observed_handoff),
                resolved_eval_json,
                eval_payload,
            )
            if repair_context is not None:
                if not dry_run:
                    save_graph(graph_path, graph)
                worker_lease_released = False
                eval_lease_released = False
                if not dry_run and worker_pane and worker_dispatch_id:
                    worker_lease_released = bool(
                        release_lease(worker_pane, worker_dispatch_id, "node_failed_review").get("released")
                    )
                if not dry_run and eval_assignments:
                    eval_lease_released = any(
                        bool(
                            release_lease(
                                str(assignment.get("pane") or ""),
                                str(assignment.get("dispatch_id") or ""),
                                "node_failed_review",
                            ).get("released")
                        )
                        for assignment in eval_assignments
                        if str(assignment.get("pane") or "") and str(assignment.get("dispatch_id") or "")
                    )
                coverage_refresh = _refresh_requirement_coverage_artifacts(sid, dry_run=dry_run)
                return {
                    "ok": True,
                    "node": node_id,
                    "status": "failed_review",
                    "repair_context": repair_context,
                    "dry_run": dry_run,
                    "worker_lease_released": worker_lease_released,
                    "eval_lease_released": eval_lease_released,
                    "downstream": {"ok": True, "skipped": "repair_requested"},
                    "parent_status_updated": False,
                    "capability_effect": {},
                    "proof_gate": proof_gate,
                    "research_quality_gate": research_quality_gate,
                    "coverage_refresh": coverage_refresh,
                }
    # Self-graded guard (final gate before marking passed): an EXECUTOR node (real handoff present)
    # whose verdict (eval.json) has NO independent evaluator report -- no non-empty {node}-eval.md and
    # no {node}-eval-dispatch sidecar -- must never certify PASS. Block it gracefully as unverified
    # rather than letting mark_node_result raise passed_requires_eval_json uncaught (which would wedge
    # the coordinator). Runs AFTER the proof/research gates so their more specific block reasons win;
    # mirrors the scheduler's mark_node_result backstop (in-runtime gnd.SPRINTS_DIR == gs.SPRINTS_DIR).
    # Gate/verifier nodes produce no handoff -> exempt (they verify via their decision artifact, not a
    # per-node eval). Closes the eval-backfill false-positive vector at the node_verdict entry point.
    self_graded_handoff = _existing_node_handoff(sid, node, graph)
    if status == "passed" and self_graded_handoff and _node_eval_self_graded(sid, node_id):
        return {
            "ok": False,
            "reason": "self_graded_eval_requires_independent_report",
            "node": node_id,
            "status": "blocked",
            "eval_json": str(eval_json or _eval_json_file(sid, node_id)),
            "handoff_md": str(self_graded_handoff),
        }
    parent = mark_node_result(graph, node_id, status, gate_status=status, note="; ".join(note_parts) or None)
    node["status"] = status
    node["updated_at"] = _utc_now()
    if eval_json:
        node["eval_json"] = eval_json
    if proof_gate.get("required"):
        node["proof_gate"] = proof_gate
    if research_quality_gate.get("required"):
        node["research_quality_gate"] = research_quality_gate.get("gate") or research_quality_gate
    worker_pane = str(node.get("assigned_to") or "")
    worker_dispatch_id = str(node.get("dispatch_id") or "")
    effect_result: dict[str, Any] = {}
    if scan_effect is not None:
        try:
            observed_handoff = _existing_node_handoff(sid, node, graph) or _handoff_file(sid, node_id)
            effect_result = scan_effect(
                _dispatch_file(sid, node_id),
                handoff_file=observed_handoff,
                eval_file=_eval_md_file(sid, node_id),
                eval_json_file=eval_json or _eval_json_file(sid, node_id),
                verdict=status,
                record_db=not dry_run,
            )
            node["capability_effect"] = effect_result.get("effect", {})
        except Exception as exc:
            effect_result = {"ok": False, "reason": f"effect_scan_failed:{type(exc).__name__}", "error": str(exc)}
    node.pop("assigned_to", None)
    node.pop("dispatch_id", None)
    node.pop("eval_dispatch_group_id", None)
    _clear_eval_assignments(node)
    save_graph(graph_path, graph)

    worker_lease_released = False
    eval_lease_released = False
    if not dry_run and worker_pane and worker_dispatch_id:
        worker_lease_released = bool(
            release_lease(worker_pane, worker_dispatch_id, f"node_{status}").get("released")
        )
    if not dry_run and eval_assignments:
        eval_lease_released = any(
            bool(
                release_lease(
                    str(assignment.get("pane") or ""),
                    str(assignment.get("dispatch_id") or ""),
                    f"node_{status}",
                ).get("released")
            )
            for assignment in eval_assignments
            if str(assignment.get("pane") or "") and str(assignment.get("dispatch_id") or "")
        )

    coverage_refresh = _refresh_requirement_coverage_artifacts(sid, dry_run=dry_run)
    downstream: dict[str, Any] = {"ok": True, "skipped": "verdict_not_passed"}
    if status == "passed" and dispatch_downstream and not parent.get("ready"):
        downstream = dispatch_ready(graph_path, dry_run=dry_run, ttl=ttl)
    elif status == "passed" and parent.get("ready"):
        downstream = {"ok": True, "skipped": "parent_ready"}
    parent_status_updated = _mark_parent_sprint_passed_if_ready(sid, parent, dry_run)

    return {
        "ok": bool(downstream.get("ok", True)),
        "node": node_id,
        "status": status,
        "parent": parent,
        "downstream": downstream,
        "dry_run": dry_run,
        "worker_lease_released": worker_lease_released,
        "eval_lease_released": eval_lease_released,
        "parent_status_updated": parent_status_updated,
        "capability_effect": effect_result,
        "proof_gate": proof_gate,
        "research_quality_gate": research_quality_gate,
        "coverage_refresh": coverage_refresh,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="graph_node_dispatcher.py")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("drain-queue")
    p.add_argument("--sprint", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-items", type=int, default=0)
    p.add_argument("--ttl", type=int, default=900)

    p = sub.add_parser("dispatch-ready")
    p.add_argument("--graph", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--ttl", type=int, default=900)
    p.add_argument("--max-parallel", type=int, default=None)

    p = sub.add_parser("dispatch-evals")
    p.add_argument("--graph", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--ttl", type=int, default=900)
    p.add_argument("--force", action="store_true")
    p.add_argument("--max-items", type=int, default=0)

    p = sub.add_parser("node-verdict")
    p.add_argument("--graph", required=True)
    p.add_argument("--node", required=True)
    p.add_argument("--verdict", required=True)
    p.add_argument("--reason", default="")
    p.add_argument("--eval-json", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--ttl", type=int, default=900)
    p.add_argument("--no-dispatch-downstream", action="store_true")

    args = ap.parse_args()
    if args.cmd == "drain-queue":
        result = drain_queue(args.sprint, args.dry_run, args.max_items, args.ttl)
    elif args.cmd == "dispatch-ready":
        result = dispatch_ready(args.graph, args.dry_run, args.ttl, args.max_parallel)
    elif args.cmd == "dispatch-evals":
        result = dispatch_node_evals(args.graph, args.dry_run, args.ttl, args.force, args.max_items)
    elif args.cmd == "node-verdict":
        result = node_verdict(
            args.graph,
            args.node,
            args.verdict,
            reason=args.reason,
            eval_json=args.eval_json,
            dry_run=args.dry_run,
            ttl=args.ttl,
            dispatch_downstream=not args.no_dispatch_downstream,
        )
    else:
        ap.print_help()
        return 1

    print(_json(result))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
