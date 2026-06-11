#!/usr/bin/env python3
"""Solar-Harness intent adapter.

This ports the useful, runtime-safe parts of Solar's old
``Solar/hooks/intent-engine-hook.sh`` into Solar-Harness so dispatch text can be
classified before it is sent to panes.  It is deliberately fail-open: a broken
SQLite table or missing legacy hook never blocks dispatch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOLAR_DB = Path(os.environ.get("SOLAR_INTENT_DB", str(Path.home() / ".solar" / "solar.db")))
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
SPRINTS_DIR = HARNESS_DIR / "sprints"
STATE_DIR = HARNESS_DIR / "state"
EVENTS_JSONL = STATE_DIR / "events.jsonl"
DISPATCH_LEDGER = HARNESS_DIR / "run" / "dispatch-ledger.jsonl"
_TABLE_EXISTS_CACHE: dict[tuple[tuple[int, int] | None, str], bool] = {}
_LEARNED_ROWS_CACHE: tuple[tuple[int, int] | None, list[dict[str, Any]]] | None = None
_CONFIGURED_RULES_CACHE: tuple[tuple[int, int] | None, list[dict[str, Any]]] | None = None
_TABLE_COLUMNS_CACHE: dict[tuple[tuple[int, int] | None, str], set[str]] = {}


@dataclass(frozen=True)
class IntentRule:
    kind: str
    intent_type: str
    confidence: float
    patterns: tuple[str, ...]
    instruction: str
    source: str = "solar-harness"
    skill: str | None = None
    target: str | None = None


DIRECT_RULES: tuple[IntentRule, ...] = (
    IntentRule("intent", "confirm", 0.95, (r"^(好|可|可以|OK|确认|通过|不错|行|对|是的?|批准|approved|go|yes|y)$",), "用户输入为确认/批准信号；如果有待批准或主动请求，应立即执行。"),
    IntentRule("intent", "reject", 0.95, (r"^(不对|错了|重来|不行|不是|错误|问题|不好|差|糟糕|N|No|否|取消|拒绝|停|算了)$",), "用户输入为否定/纠正信号；停止当前错误路径，基于证据修正。"),
    IntentRule("intent", "save", 0.90, (r"^(保存|休息|我先走|暂停|save|pause)",), "用户希望保存状态或暂停；输出中途宣告并持久化状态。"),
    IntentRule("intent", "execute", 0.90, (r"修复|继续|开始执行|执行|fix|continue|开始|下一步|接着|next",), "用户希望执行上一个提议；立即开始执行，无需再次确认。"),
    IntentRule("intent", "solar_start", 1.00, (r"^(solar|打开solar|加载solar|启动solar)$",), "用户触发 Solar 启动；加载 Solar 状态和启动宣告。"),
    IntentRule("intent", "solar_max", 1.00, (r"^solar-max$",), "用户触发 Solar-MAX 项目模式；切换并装载项目状态。"),
    IntentRule("intent", "dev_mode", 0.95, (r"^我要开发",), "用户希望进入开发模式；识别项目路径、装载状态、恢复上下文。"),
    IntentRule("intent", "office_mode", 0.95, (r"^我要办公",), "用户希望进入办公模式。"),
    IntentRule("intent", "status_query", 0.95, (r"^(status|状态|显示状态|看状态)$",), "用户请求查看当前状态；优先返回结构化状态摘要。"),
    IntentRule("intent", "task_status_query", 0.95, (r"有哪些任务|哪些任务|任务.*(执行|运行|状态|进展)|后台.*任务|task.*(status|running)",), "用户请求查看任务或后台 worker 状态；优先返回任务池/DAG 摘要。"),
    IntentRule("intent", "display", 0.90, (r"^(我要看|我想看|给我看|展示|显示|呈现)",), "用户希望查看/展示内容；用可读仪表盘或结构化视图输出。"),
    IntentRule("intent", "insight_quick", 0.95, (r"^洞察分析[：:]",), "用户请求快速洞察分析。"),
    IntentRule("intent", "insight_deep", 0.95, (r"^(深入洞察|深度洞察)\s+",), "用户请求深度洞察分析。"),
    IntentRule("intent", "plan", 0.95, (r"^/plan( +preview| +metrics)? +",), "用户请求 Plan/Act 流程。"),
    IntentRule("intent", "agent", 0.95, (r"^@[A-Za-z][A-Za-z0-9_]*",), "用户显式触发 @Agent；映射到对应 specialist/subagent。"),
    IntentRule("intent", "show_dashboard", 0.95, (r"dashboard|仪表盘|solar.*状况|solar.*状态|查.*solar.*状态|看指标|solar.*dashboard",), "用户请求查看 Solar 运行状况。"),
    IntentRule("intent", "task_completed", 0.85, (r"完成了|搞定了|做好了|弄完了|搞好了|写完了|改完了|改好了|任务完成|已完成|执行完毕|\b(done|finished|complete)\b",), "用户标记任务完成；读取最近状态并推荐后续动作。"),
    IntentRule("intent", "mode_switch", 0.95, (r"^(省钱|经济|economy)$",), "用户请求切换到经济模式。", target="economy"),
    IntentRule("intent", "mode_switch", 0.95, (r"^(用glm|智谱|glm\.only)$",), "用户请求切换到 GLM 全量模式。", target="glm_only"),
    IntentRule("intent", "mode_switch", 0.95, (r"^(平衡|正常|balanced)$",), "用户请求切换到平衡模式。", target="balanced"),
)

SUPERPOWER_RULES: tuple[IntentRule, ...] = (
    IntentRule("hint", "skill_hint", 0.85, (r"头脑风暴|brainstorm|来个创意|构思一下",), "建议使用 Superpowers brainstorming。", "superpowers", "brainstorming"),
    IntentRule("hint", "skill_hint", 0.85, (r"写计划|制定计划|roadmap",), "建议使用 Superpowers writing-plans。", "superpowers", "writing-plans"),
    IntentRule("hint", "skill_hint", 0.85, (r"执行计划|按计划执行|executing.plan",), "建议使用 Superpowers executing-plans。", "superpowers", "executing-plans"),
    IntentRule("hint", "skill_hint", 0.85, (r"TDD|测试驱动|test.driven",), "建议使用 Superpowers test-driven-development。", "superpowers", "test-driven-development"),
    IntentRule("hint", "skill_hint", 0.85, (r"系统化调试|逐步排查|systematic.debug",), "建议使用 Superpowers systematic-debugging。", "superpowers", "systematic-debugging"),
    IntentRule("hint", "skill_hint", 0.85, (r"验证完成|完成前检查|verify.before",), "建议使用 Superpowers verification-before-completion。", "superpowers", "verification-before-completion"),
    IntentRule("hint", "skill_hint", 0.85, (r"并行代理|parallel.agent|多代理并行",), "建议使用 Superpowers dispatching-parallel-agents。", "superpowers", "dispatching-parallel-agents"),
    IntentRule("hint", "skill_hint", 0.85, (r"子代理|subagent.dev|自动开发",), "建议使用 Superpowers subagent-driven-development。", "superpowers", "subagent-driven-development"),
    IntentRule("hint", "skill_hint", 0.85, (r"worktree|工作树|git.隔离",), "建议使用 Superpowers using-git-worktrees。", "superpowers", "using-git-worktrees"),
    IntentRule("hint", "skill_hint", 0.85, (r"完成分支|结束开发|finish.branch",), "建议使用 Superpowers finishing-a-development-branch。", "superpowers", "finishing-a-development-branch"),
    IntentRule("hint", "skill_hint", 0.85, (r"收到review|审查反馈|receiving.review",), "建议使用 Superpowers receiving-code-review。", "superpowers", "receiving-code-review"),
    IntentRule("hint", "skill_hint", 0.85, (r"请求审查|要review|request.review",), "建议使用 Superpowers requesting-code-review。", "superpowers", "requesting-code-review"),
    IntentRule("hint", "skill_hint", 0.85, (r"编写技能|创建.*skill|写个skill|新建skill|write.skill|创建技能",), "建议使用 Superpowers writing-skills。", "superpowers", "writing-skills"),
)

GSTACK_RULES: tuple[IntentRule, ...] = (
    IntentRule("hint", "skill_hint", 0.85, (r"浏览|打开网页|screenshot|访问网站|^browse ",), "建议使用 gstack browse。", "gstack", "browse"),
    IntentRule("hint", "skill_hint", 0.85, (r"审查.*代码|code.review|review.*代码|review.*PR|做.*review|^review$",), "建议使用 gstack review。", "gstack", "review"),
    IntentRule("hint", "skill_hint", 0.85, (r"排查|investigate|根因分析|排查bug",), "建议使用 gstack investigate。", "gstack", "investigate"),
    IntentRule("hint", "skill_hint", 0.85, (r"^qa$|QA|质量保证|全面测试|找bug",), "建议使用 gstack qa。", "gstack", "qa"),
    IntentRule("hint", "skill_hint", 0.85, (r"发布|上线|^ship$|^deploy$",), "建议使用 gstack ship。", "gstack", "ship"),
    IntentRule("hint", "skill_hint", 0.85, (r"性能基准|benchmark|跑分|性能回归",), "建议使用 gstack benchmark。", "gstack", "benchmark"),
    IntentRule("hint", "skill_hint", 0.85, (r"办公时间|YC办公|office.hours",), "建议使用 gstack office-hours。", "gstack", "office-hours"),
    IntentRule("hint", "skill_hint", 0.85, (r"自动评审|全审|^autoplan",), "建议使用 gstack autoplan。", "gstack", "autoplan"),
    IntentRule("hint", "skill_hint", 0.85, (r"谨慎|小心|生产环境|^careful$",), "建议使用 gstack careful。", "gstack", "careful"),
    IntentRule("hint", "skill_hint", 0.85, (r"守护|安全模式|^guard$",), "建议使用 gstack guard。", "gstack", "guard"),
    IntentRule("hint", "skill_hint", 0.85, (r"冻结|限制编辑|^freeze$",), "建议使用 gstack freeze。", "gstack", "freeze"),
    IntentRule("hint", "skill_hint", 0.85, (r"^unfreeze$|^解冻$",), "建议使用 gstack unfreeze。", "gstack", "unfreeze"),
    IntentRule("hint", "skill_hint", 0.85, (r"设计审查|视觉QA|design.review",), "建议使用 gstack design-review。", "gstack", "design-review"),
    IntentRule("hint", "skill_hint", 0.85, (r"设计咨询|设计系统|design.consult",), "建议使用 gstack design-consultation。", "gstack", "design-consultation"),
    IntentRule("hint", "skill_hint", 0.85, (r"CEO评审|战略评审|plan.ceo.review",), "建议使用 gstack plan-ceo-review。", "gstack", "plan-ceo-review"),
    IntentRule("hint", "skill_hint", 0.85, (r"工程评审|架构评审|plan.eng.review",), "建议使用 gstack plan-eng-review。", "gstack", "plan-eng-review"),
    IntentRule("hint", "skill_hint", 0.85, (r"设计方案评审|plan.design.review",), "建议使用 gstack plan-design-review。", "gstack", "plan-design-review"),
    IntentRule("hint", "skill_hint", 0.85, (r"回顾|复盘|^retro$",), "建议使用 gstack retro。", "gstack", "retro"),
    IntentRule("hint", "skill_hint", 0.85, (r"文档更新|发布文档|document.release",), "建议使用 gstack document-release。", "gstack", "document-release"),
    IntentRule("hint", "skill_hint", 0.85, (r"金丝雀|部署监控|^canary$",), "建议使用 gstack canary。", "gstack", "canary"),
    IntentRule("hint", "skill_hint", 0.85, (r"安全审计|OWASP|^CSO$|^cso$",), "建议使用 gstack cso。", "gstack", "cso"),
    IntentRule("hint", "skill_hint", 0.85, (r"codex审查|第二意见|codex.review",), "建议使用 gstack codex。", "gstack", "codex"),
    IntentRule("hint", "skill_hint", 0.85, (r"合并部署|^land$|land.and.deploy",), "建议使用 gstack land-and-deploy。", "gstack", "land-and-deploy"),
)

AGENT_RULES_BOOKS_RULES: tuple[IntentRule, ...] = (
    IntentRule("hint", "skill_hint", 0.86, (r"clean code|整洁代码|命名|小函数|可读性|code smell",), "建议使用 agent-rules-books: clean-code.mini。", "agent-rules-books", "clean-code"),
    IntentRule("hint", "skill_hint", 0.88, (r"refactor|refactoring|重构|代码异味|安全重构",), "建议使用 agent-rules-books: refactoring.mini。", "agent-rules-books", "refactoring"),
    IntentRule("hint", "skill_hint", 0.88, (r"legacy code|遗留代码|characterization test|seam|难测代码",), "建议使用 agent-rules-books: working-effectively-with-legacy-code.mini。", "agent-rules-books", "working-effectively-with-legacy-code"),
    IntentRule("hint", "skill_hint", 0.86, (r"clean architecture|整洁架构|dependency rule|边界|use case",), "建议使用 agent-rules-books: clean-architecture.mini。", "agent-rules-books", "clean-architecture"),
    IntentRule("hint", "skill_hint", 0.86, (r"\bddd\b|domain[- ]driven design|领域驱动|bounded context|聚合|领域事件",), "建议使用 agent-rules-books: domain-driven-design.mini。", "agent-rules-books", "domain-driven-design"),
    IntentRule("hint", "skill_hint", 0.86, (r"\bddia\b|data[- ]intensive|数据密集|一致性|复制|分区|事务|schema evolution|event stream",), "建议使用 agent-rules-books: designing-data-intensive-applications.mini。", "agent-rules-books", "designing-data-intensive-applications"),
    IntentRule("hint", "skill_hint", 0.86, (r"release it|生产可靠性|熔断|限流|超时|重试|bulkhead|backpressure",), "建议使用 agent-rules-books: release-it.mini。", "agent-rules-books", "release-it"),
    IntentRule("hint", "skill_hint", 0.82, (r"pragmatic programmer|程序员修炼|正交性|\bdry\b|自动化|快速反馈",), "建议使用 agent-rules-books: the-pragmatic-programmer.mini。", "agent-rules-books", "the-pragmatic-programmer"),
)


AUTORESEARCH_RULES: tuple[IntentRule, ...] = (
    IntentRule(
        "hint",
        "skill_hint",
        0.87,
        (
            r"\b(autoresearch|auto research|pane optimizer|execution optimizer|dispatch advisor|issue[- ]loop|local issue|implementation loop|score[- ]gate|passing score)\b",
            r"自动实现.*issue|issue.*自动实现|本地.*issue|多代理.*迭代|评分门禁|分数门禁|执行优化器|质量优化|实现循环|修复循环",
        ),
        "建议使用 autoresearch.pane_optimizer / issue_loop 提升 pane 输出质量；默认只 advisor/dry-run，执行必须有 --execute 和明确授权。",
        "autoresearch",
        "pane-optimizer",
    ),
)


META_HARNESS_RULES: tuple[IntentRule, ...] = (
    IntentRule(
        "hint",
        "skill_hint",
        0.89,
        (
            r"\b(meta[- ]?harness|outer[- ]loop|self[- ]optimization|self[- ]improvement|harness code|pareto frontier|trace[- ]based eval)\b",
            r"自我优化|优化自己|自演化|外循环优化|元优化|能力演化|优化.*规则|优化.*技能|优化.*hook|优化.*config|帕累托|Pareto",
        ),
        "建议使用 meta_harness.outer_loop 做 harness-level 自优化评估；默认只 status/dry-run，真实 run/apply 必须显式 --execute 并审查风险。",
        "meta-harness",
        "outer-loop",
    ),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize(text: str) -> str:
    return " ".join(text.strip().split())


def as_match(rule: IntentRule, text: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kind": rule.kind,
        "type": rule.intent_type,
        "source": rule.source,
        "confidence": rule.confidence,
        "instruction": rule.instruction,
    }
    if rule.skill:
        out["skill"] = rule.skill
    if rule.target:
        out["target"] = rule.target
    if rule.intent_type == "agent":
        tag = re.match(r"^@[A-Za-z][A-Za-z0-9_]*", text.strip())
        if tag:
            out["agent"] = tag.group(0)
    return out


def _loads_json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _loads_json_dict(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _has_regex_meta(trigger: str) -> bool:
    return any(ch in trigger for ch in "^$.*+?[](){}|\\")


def _trigger_matches(trigger: str, text: str, lowered: str) -> bool:
    trigger = trigger.strip()
    if not trigger:
        return False
    trigger_lower = trigger.lower()
    if _has_regex_meta(trigger):
        try:
            return re.search(trigger, text, re.IGNORECASE) is not None
        except re.error:
            return trigger_lower in lowered
    if len(trigger) <= 3 and trigger.isascii() and trigger.isalnum():
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(trigger)}(?![A-Za-z0-9_])", text, re.IGNORECASE) is not None
    return trigger_lower in lowered


def configured_rows() -> list[dict[str, Any]]:
    global _CONFIGURED_RULES_CACHE
    sig = db_signature()
    if _CONFIGURED_RULES_CACHE is not None and _CONFIGURED_RULES_CACHE[0] == sig:
        return _CONFIGURED_RULES_CACHE[1]

    conn = open_db()
    if conn is None:
        _CONFIGURED_RULES_CACHE = (sig, [])
        return []
    try:
        if not has_table(conn, "intent_patterns"):
            rows: list[dict[str, Any]] = []
        else:
            rows = [dict(row) for row in conn.execute(
                """SELECT pattern_id, name, category, triggers, typical_actions,
                          capability_mapping, success_rate, avg_confidence, frequency
                   FROM intent_patterns
                   ORDER BY frequency DESC, success_rate DESC, pattern_id"""
            ).fetchall()]
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    _CONFIGURED_RULES_CACHE = (sig, rows)
    return rows


def match_static(text: str) -> list[dict[str, Any]]:
    normalized = normalize(text)
    lowered = normalized.lower()
    matches: list[dict[str, Any]] = []

    for rule in DIRECT_RULES:
        haystack = lowered if rule.intent_type == "mode_switch" else normalized
        if any(re.search(p, haystack, re.IGNORECASE) for p in rule.patterns):
            if rule.intent_type == "task_completed" and re.search(r"完成[前之]", normalized):
                continue
            matches.append(as_match(rule, normalized))
            break

    # Preserve legacy precedence: Superpowers before gstack.
    for rule in SUPERPOWER_RULES:
        if any(re.search(p, lowered, re.IGNORECASE) for p in rule.patterns):
            matches.append(as_match(rule, normalized))
            return matches

    for rule in AUTORESEARCH_RULES:
        if any(re.search(p, normalized, re.IGNORECASE) for p in rule.patterns):
            matches.append(as_match(rule, normalized))
            return matches

    for rule in META_HARNESS_RULES:
        if any(re.search(p, normalized, re.IGNORECASE) for p in rule.patterns):
            matches.append(as_match(rule, normalized))
            return matches

    for rule in AGENT_RULES_BOOKS_RULES:
        if any(re.search(p, lowered, re.IGNORECASE) for p in rule.patterns):
            matches.append(as_match(rule, normalized))
            return matches

    for rule in GSTACK_RULES:
        if any(re.search(p, lowered, re.IGNORECASE) for p in rule.patterns):
            matches.append(as_match(rule, normalized))
            return matches

    return matches


def match_configured(text: str) -> list[dict[str, Any]]:
    normalized = normalize(text)
    lowered = normalized.lower()
    for row in configured_rows():
        triggers = [str(item).strip() for item in _loads_json_list(row.get("triggers")) if str(item).strip()]
        if not triggers:
            continue
        matched_trigger = next((trigger for trigger in triggers if _trigger_matches(trigger, normalized, lowered)), "")
        if not matched_trigger:
            continue
        actions = [str(item) for item in _loads_json_list(row.get("typical_actions"))]
        capability_mapping = _loads_json_dict(row.get("capability_mapping"))
        confidence = max(0.75, float(row.get("avg_confidence") or 0.5), float(row.get("success_rate") or 0.5))
        out: dict[str, Any] = {
            "kind": "intent",
            "type": str(row.get("pattern_id") or row.get("category") or "configured_pattern"),
            "source": "solar-intent-patterns",
            "confidence": min(0.99, confidence),
            "instruction": f"命中 Solar intent_patterns: {row.get('name') or row.get('pattern_id')} / {matched_trigger}",
            "pattern_id": str(row.get("pattern_id") or ""),
            "name": str(row.get("name") or ""),
            "category": str(row.get("category") or ""),
            "trigger": matched_trigger,
        }
        if actions:
            out["actions"] = actions
        if capability_mapping:
            out["capability_mapping"] = capability_mapping
            params = capability_mapping.get("params")
            if isinstance(params, dict) and params.get("mode"):
                out["target"] = str(params["mode"])
        return [out]
    return []


def open_db() -> sqlite3.Connection | None:
    if not SOLAR_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(SOLAR_DB), timeout=1.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def db_signature() -> tuple[int, int] | None:
    try:
        st = SOLAR_DB.stat()
        return (int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return None


def has_table(conn: sqlite3.Connection, table: str) -> bool:
    sig = db_signature()
    key = (sig, table)
    if key in _TABLE_EXISTS_CACHE:
        return _TABLE_EXISTS_CACHE[key]
    try:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        exists = row is not None
    except sqlite3.Error:
        exists = False
    _TABLE_EXISTS_CACHE[key] = exists
    return exists


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    sig = db_signature()
    key = (sig, table)
    if key in _TABLE_COLUMNS_CACHE:
        return _TABLE_COLUMNS_CACHE[key]
    try:
        columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        columns = set()
    _TABLE_COLUMNS_CACHE[key] = columns
    return columns


def learned_rows() -> list[dict[str, Any]]:
    global _LEARNED_ROWS_CACHE
    sig = db_signature()
    if _LEARNED_ROWS_CACHE is not None and _LEARNED_ROWS_CACHE[0] == sig:
        return _LEARNED_ROWS_CACHE[1]

    conn = open_db()
    if conn is None:
        _LEARNED_ROWS_CACHE = (sig, [])
        return []
    try:
        if not has_table(conn, "sys_intent_patterns"):
            rows: list[dict[str, Any]] = []
        else:
            rows = [dict(row) for row in conn.execute(
                """SELECT pattern, intent_type, confidence
                   FROM sys_intent_patterns
                   ORDER BY confidence DESC, success_count DESC
                   LIMIT 200"""
            ).fetchall()]
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    _LEARNED_ROWS_CACHE = (sig, rows)
    return rows


def match_learned(text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    lowered = text.lower()
    for row in learned_rows():
        pattern = str(row["pattern"] or "").strip()
        intent_type = str(row["intent_type"] or "").strip()
        if not pattern or not intent_type:
            continue
        try:
            hit = re.search(pattern, text, re.IGNORECASE) is not None
        except re.error:
            hit = pattern.lower() in lowered
        if hit:
            matches.append({
                "kind": "intent",
                "type": intent_type,
                "source": "solar-learned-db",
                "confidence": float(row["confidence"] or 0.8),
                "instruction": f"命中 Solar 学习规则: {pattern} -> {intent_type}",
                "pattern": pattern,
            })
            break
    return matches


def record_feedback(text: str, matches: list[dict[str, Any]]) -> None:
    conn = open_db()
    if conn is None:
        return
    try:
        if has_table(conn, "evo_feedback_v2"):
            signal_type = "implicit_positive"
            if any(m.get("type") == "confirm" for m in matches):
                signal_type = "explicit_positive"
            elif any(m.get("type") == "reject" for m in matches):
                signal_type = "explicit_negative"
            conn.execute(
                "INSERT OR IGNORE INTO evo_feedback_v2 (input, signal_type, source, created_at) VALUES (?, ?, ?, datetime('now'))",
                (text[:1000], signal_type, "harness_intent_adapter"),
            )
        if not matches and has_table(conn, "sys_intent_unknown"):
            conn.execute(
                """INSERT INTO sys_intent_unknown (input, created_at)
                   SELECT ?, datetime('now')
                   WHERE NOT EXISTS (
                       SELECT 1 FROM sys_intent_unknown
                       WHERE input = ?
                       LIMIT 1
                   )""",
                (text[:1000], text[:1000]),
            )
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def record_configured_usage(matches: list[dict[str, Any]]) -> None:
    pattern_ids = sorted({
        str(match.get("pattern_id") or "")
        for match in matches
        if match.get("source") == "solar-intent-patterns" and match.get("pattern_id")
    })
    if not pattern_ids:
        return
    conn = open_db()
    if conn is None:
        return
    try:
        if not has_table(conn, "intent_patterns"):
            return
        columns = table_columns(conn, "intent_patterns")
        assignments: list[str] = []
        if "frequency" in columns:
            assignments.append("frequency = COALESCE(frequency, 0) + 1")
        if "success_count" in columns:
            # record=True means the parse was accepted for telemetry, not that downstream execution passed.
            assignments.append("success_count = COALESCE(success_count, 0) + 1")
        if "last_used" in columns:
            assignments.append("last_used = datetime('now')")
        if "updated_at" in columns:
            assignments.append("updated_at = datetime('now')")
        if not assignments:
            return
        for pattern_id in pattern_ids:
            conn.execute(
                f"UPDATE intent_patterns SET {', '.join(assignments)} WHERE pattern_id = ?",
                (pattern_id,),
            )
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def learn(pattern: str, intent_type: str) -> dict[str, Any]:
    try:
        SOLAR_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(SOLAR_DB), timeout=1.0)
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc), "db": str(SOLAR_DB)}
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sys_intent_patterns (
                   pattern TEXT NOT NULL,
                   intent_type TEXT NOT NULL,
                   success_count INTEGER DEFAULT 0,
                   confidence REAL DEFAULT 0.8,
                   created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                   updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                   PRIMARY KEY (pattern, intent_type)
               )"""
        )
        conn.execute(
            """INSERT INTO sys_intent_patterns
                   (pattern, intent_type, success_count, confidence, created_at, updated_at)
               VALUES (?, ?, 1, 0.8, datetime('now'), datetime('now'))
               ON CONFLICT(pattern, intent_type) DO UPDATE SET
                   success_count = success_count + 1,
                   confidence = MIN(0.99, confidence + 0.02),
                   updated_at = datetime('now')""",
            (pattern, intent_type),
        )
        conn.commit()
        return {"ok": True, "pattern": pattern, "intent_type": intent_type, "db": str(SOLAR_DB)}
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc), "db": str(SOLAR_DB)}
    finally:
        conn.close()


def emit_event(event: str, payload: dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": now_iso(), "actor": "intent-adapter", "event": event, **payload}
        with EVENTS_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def match(text: str, *, record: bool = False) -> dict[str, Any]:
    matches = match_learned(text) + match_static(text)
    if not matches:
        matches = match_configured(text)
    result = {
        "ok": True,
        "input": text,
        "matches": matches,
        "matched": bool(matches),
        "generated_at": now_iso(),
        "sources": {
            "ported_from": str(Path.home() / "Solar" / "hooks" / "intent-engine-hook.sh"),
            "db": str(SOLAR_DB),
        },
    }
    if record:
        record_configured_usage(matches)
        record_feedback(text, matches)
        emit_event("intent_matched", {"matched": bool(matches), "match_count": len(matches)})
    return result


def cmd_match(args: argparse.Namespace) -> int:
    text = args.text or sys.stdin.read()
    result = match(text, record=args.record)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["matches"]:
            print("intent: N/A")
        for item in result["matches"]:
            label = item.get("skill") or item.get("type")
            print(f"{item['kind']} {item['source']} {label} confidence={item['confidence']}")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    result = learn(args.pattern, args.intent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _iter_intent_sidecars(sid: str | None = None) -> list[Path]:
    roots = [SPRINTS_DIR, HARNESS_DIR / "reports" / "capability-activation-evidence"]
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.intent.json"):
            if sid and sid not in str(path):
                data = _load_json(path)
                if sid not in str(data.get("dispatch_file", "")):
                    continue
            out.append(path)
    return sorted(set(out), key=lambda p: str(p))


def _infer_sid(sidecar: Path, data: dict[str, Any]) -> str:
    text = f"{sidecar} {data.get('dispatch_file', '')}"
    m = re.search(r"sprint-\d{8}[-A-Za-z0-9_.]+", text)
    if not m:
        return ""
    raw = m.group(0)
    for suffix in (
        ".dispatch", ".handoff", ".eval", ".status", ".task_graph",
        ".contract", ".plan", ".prd", ".design",
    ):
        if suffix in raw:
            raw = raw.split(suffix, 1)[0]
    return raw.rstrip(".")


def _status_for_sid(sid: str) -> dict[str, Any]:
    if not sid:
        return {}
    return _load_json(SPRINTS_DIR / f"{sid}.status.json")


def _artifact_paths_for_sid(sid: str) -> list[Path]:
    if not sid:
        return []
    pats = [
        f"{sid}.handoff.md",
        f"{sid}.eval.md",
        f"{sid}.eval.json",
        f"{sid}.status.json",
        f"{sid}.*handoff.md",
        f"{sid}.*eval.md",
        f"{sid}.*report.md",
        f"{sid}.*report.json",
    ]
    paths: list[Path] = []
    for pat in pats:
        paths.extend(SPRINTS_DIR.glob(pat))
    return sorted(set(p for p in paths if p.exists()))


def _terms_from_telemetry(data: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    intent = data.get("intent") or {}
    for m in intent.get("matches") or []:
        for key in ("type", "source", "skill", "target"):
            val = m.get(key)
            if val:
                terms.append(str(val))
    for cap in data.get("capabilities") or []:
        if cap.get("provider"):
            terms.append(str(cap["provider"]))
        for c in cap.get("capabilities") or []:
            terms.append(str(c))
    return sorted({t.lower() for t in terms if len(t) >= 3})


def _audit_one_sidecar(sidecar: Path, write: bool = False) -> dict[str, Any]:
    data = _load_json(sidecar)
    sid = _infer_sid(sidecar, data)
    status = _status_for_sid(sid)
    artifact_paths = _artifact_paths_for_sid(sid)
    terms = _terms_from_telemetry(data)
    evidence: list[dict[str, Any]] = []
    for path in artifact_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except Exception:
            continue
        hits = [term for term in terms if term in text]
        if hits:
            evidence.append({
                "file": str(path),
                "hits": hits[:12],
            })

    has_signal = bool((data.get("intent") or {}).get("matches") or data.get("capabilities"))
    worker_used = bool(evidence)
    status_value = str(status.get("status", "unknown"))
    phase_value = str(status.get("phase", "unknown"))
    terminal_pass = status_value in {"passed", "completed"} or phase_value in {"eval_passed", "completed"}
    terminal_fail = status_value in {"failed", "failed_review"} or phase_value in {"eval_failed", "failed"}
    if not has_signal:
        effect_status = "no_intent_or_capability"
    elif worker_used and terminal_pass:
        effect_status = "used_and_passed"
    elif worker_used and terminal_fail:
        effect_status = "used_but_failed"
    elif worker_used:
        effect_status = "used_unverified"
    elif artifact_paths:
        effect_status = "visible_not_used"
    else:
        effect_status = "pending_worker_evidence"

    effect = {
        "status": effect_status,
        "worker_used": worker_used,
        "evidence": evidence,
        "audited_at": now_iso(),
        "artifact_count": len(artifact_paths),
        "terminal_status": status_value,
        "terminal_phase": phase_value,
        "note": "Audit checks observable handoff/eval/status artifacts; private model reasoning is not observable.",
    }
    if write:
        data["effect"] = effect
        sidecar.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "sidecar": str(sidecar),
        "sid": sid,
        "dispatch_file": data.get("dispatch_file", ""),
        "intent_matched": bool((data.get("intent") or {}).get("matched")),
        "intent_matches": (data.get("intent") or {}).get("matches", []),
        "capability_providers": [c.get("provider") for c in data.get("capabilities") or []],
        "worker_visible": data.get("worker_visible") or {},
        "effect": effect,
    }


def _sidecar_from_arg(path_arg: str) -> Path:
    path = Path(path_arg)
    if path.name.endswith(".intent.json"):
        return path
    return path.with_name(path.name + ".intent.json")


def _short_label(value: Any, limit: int = 24) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def summarize_sidecar(path_arg: str) -> dict[str, Any]:
    sidecar = _sidecar_from_arg(path_arg)
    data = _load_json(sidecar)
    intent = data.get("intent") or {}
    matches = intent.get("matches") or []
    caps = data.get("capabilities") or []
    intent_labels: list[str] = []
    for m in matches:
        label = m.get("skill") or m.get("target") or m.get("type") or m.get("source")
        if label:
            intent_labels.append(str(label))
    cap_labels = [str(c.get("provider")) for c in caps if c.get("provider")]
    effect = data.get("effect") or {}
    intent_text = ",".join(_short_label(x, 22) for x in intent_labels[:3]) if intent_labels else "N/A"
    cap_text = ",".join(_short_label(x, 22) for x in cap_labels[:4]) if cap_labels else "N/A"
    effect_status = str(effect.get("status") or "pending_worker_evidence")
    title_parts = []
    if intent_labels:
        title_parts.append("I:" + ",".join(_short_label(x, 10) for x in intent_labels[:2]))
    if cap_labels:
        title_parts.append("C:" + ",".join(_short_label(x, 10) for x in cap_labels[:3]))
    title = " | ".join(title_parts) if title_parts else "能力:N/A"
    text = f"Solar能力: intent={intent_text} | caps={cap_text} | effect={_short_label(effect_status, 20)}"
    return {
        "ok": bool(data),
        "sidecar": str(sidecar),
        "intent_labels": intent_labels,
        "capability_providers": cap_labels,
        "effect_status": effect_status,
        "text": text,
        "title": title,
    }


def cmd_audit(args: argparse.Namespace) -> int:
    sidecars = _iter_intent_sidecars(args.sid)
    rows = [_audit_one_sidecar(p, write=args.write) for p in sidecars]
    payload = {
        "ok": True,
        "generated_at": now_iso(),
        "sid": args.sid or "",
        "total": len(rows),
        "matched": sum(1 for r in rows if r.get("intent_matched") or r.get("capability_providers")),
        "worker_used": sum(1 for r in rows if (r.get("effect") or {}).get("worker_used")),
        "effect_status_counts": {},
        "rows": rows,
    }
    counts: dict[str, int] = {}
    for row in rows:
        st = (row.get("effect") or {}).get("status", "unknown")
        counts[st] = counts.get(st, 0) + 1
    payload["effect_status_counts"] = counts
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Intent audit: total={payload['total']} matched={payload['matched']} worker_used={payload['worker_used']}")
        print("┌──────────────────────────────────────────────┬──────────────┬──────────────┬──────────────────────┐")
        print("│ sidecar                                      │ matched      │ worker_used  │ effect               │")
        print("├──────────────────────────────────────────────┼──────────────┼──────────────┼──────────────────────┤")
        for row in rows[-20:]:
            name = Path(str(row.get("sidecar", ""))).name[:44]
            effect = row.get("effect") or {}
            print(f"│ {name:<44} │ {str(row.get('intent_matched')):<12} │ {str(effect.get('worker_used')):<12} │ {str(effect.get('status'))[:20]:<20} │")
        print("└──────────────────────────────────────────────┴──────────────┴──────────────┴──────────────────────┘")
        if args.write:
            print("updated sidecars with latest effect audit")
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    payload = summarize_sidecar(args.path)
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.title:
        print(payload.get("title", "能力:N/A"))
    else:
        print(payload.get("text", "Solar能力: N/A"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="intent_engine_adapter.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("match")
    m.add_argument("text", nargs="?")
    m.add_argument("--json", action="store_true", dest="as_json")
    m.add_argument("--record", action="store_true")
    m.set_defaults(func=cmd_match)
    l = sub.add_parser("learn")
    l.add_argument("pattern")
    l.add_argument("intent")
    l.set_defaults(func=cmd_learn)
    a = sub.add_parser("audit")
    a.add_argument("--sid")
    a.add_argument("--json", action="store_true", dest="as_json")
    a.add_argument("--write", action="store_true")
    a.set_defaults(func=cmd_audit)
    s = sub.add_parser("summarize")
    s.add_argument("path")
    s.add_argument("--json", action="store_true", dest="as_json")
    s.add_argument("--title", action="store_true")
    s.set_defaults(func=cmd_summarize)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
