#!/usr/bin/env python3
"""Render richer sprint HTML artifacts from canonical markdown/json artifacts.

Default path uses the html-anything adapter family. The legacy inline renderer
remains available behind ``SOLAR_USE_LEGACY_RENDERER=1`` and as a fail-open
fallback if the adapter raises.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", HARNESS_DIR / "sprints"))
TEMPLATE_PATH = HARNESS_DIR / "templates" / "html-artifact.visual-template.html"
VALID_KINDS = {"prd", "planning", "design"}

try:
    from html_anything_adapter import (
        HtmlAnythingAdapterError,
        render as render_html_anything,
    )
except Exception:  # pragma: no cover - fail-open to legacy renderer
    HtmlAnythingAdapterError = RuntimeError  # type: ignore[assignment]
    render_html_anything = None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _style_block() -> str:
    template = _read_text(TEMPLATE_PATH)
    match = re.search(r"<style>(.*?)</style>", template, flags=re.S)
    if match:
        return match.group(1).strip()
    return ""


def _html_page(title: str, body: str) -> str:
    style = _style_block()
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{html.escape(title)}</title>\n"
        f"  <style>\n{style}\n  </style>\n"
        "</head>\n<body>\n"
        '  <div class="wrap">\n'
        f"{body}\n"
        "  </div>\n"
        "</body>\n</html>\n"
    )


def _escape_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _render_markdown_block(text: str) -> str:
    if not text.strip():
        return '<p class="muted">N/A</p>'
    lines = text.strip().splitlines()
    out: list[str] = []
    buf: list[str] = []
    in_code = False
    code_lines: list[str] = []
    list_mode: str | None = None

    def flush_paragraph() -> None:
        nonlocal buf
        if buf:
            out.append(f"<p>{_escape_inline(' '.join(x.strip() for x in buf if x.strip()))}</p>")
            buf = []

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            out.append(f"</{list_mode}>")
            list_mode = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                out.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")
                in_code = False
                code_lines = []
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            if list_mode != "ul":
                close_list()
                out.append("<ul>")
                list_mode = "ul"
            out.append(f"<li>{_escape_inline(stripped[2:])}</li>")
            continue
        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            if list_mode != "ol":
                close_list()
                out.append("<ol>")
                list_mode = "ol"
            item = re.sub(r"^\d+\.\s+", "", stripped)
            out.append(f"<li>{_escape_inline(item)}</li>")
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = min(len(heading.group(1)) + 1, 4)
            out.append(f"<h{level}>{_escape_inline(heading.group(2))}</h{level}>")
            continue
        buf.append(stripped)
    flush_paragraph()
    close_list()
    if in_code:
        out.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")
    return "\n".join(out)


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "概览"
    buf: list[str] = []
    for raw in text.splitlines():
        match = re.match(r"^##+\s+(.*)$", raw.strip())
        if match:
            body = "\n".join(buf).strip()
            if body:
                sections.append((current_title, body))
            current_title = match.group(1).strip()
            buf = []
        else:
            buf.append(raw)
    body = "\n".join(buf).strip()
    if body:
        sections.append((current_title, body))
    return sections


def _diagram_from_graph(graph: dict[str, Any]) -> str:
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    if not nodes:
        return "N/A"
    lines = []
    for node in nodes:
        node_id = str(node.get("id") or "?")
        goal = str(node.get("title") or node.get("goal") or "").strip()
        deps = [str(x) for x in node.get("depends_on") or [] if str(x).strip()]
        dep_text = ", ".join(deps) if deps else "ROOT"
        lines.append(f"{dep_text} -> {node_id} [{goal[:64]}]")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    return (
        "<table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )


def _node_rows(graph: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for node in [n for n in graph.get("nodes", []) if isinstance(n, dict)]:
        skills = ", ".join(str(x) for x in node.get("required_skills") or []) or "N/A"
        deps = ", ".join(str(x) for x in node.get("depends_on") or []) or "ROOT"
        rows.append([
            html.escape(str(node.get("id") or "N/A")),
            html.escape(str(node.get("preferred_model") or "N/A")),
            html.escape(skills),
            html.escape(str(node.get("gate") or "N/A")),
            html.escape(deps),
        ])
    return rows


def _stack_rows(graph: dict[str, Any]) -> list[list[str]]:
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    model_counts = Counter(str(n.get("preferred_model") or "N/A") for n in nodes)
    skill_counts = Counter(skill for n in nodes for skill in (n.get("required_skills") or []))
    rows = [[html.escape(k), str(v), "preferred_model"] for k, v in sorted(model_counts.items())]
    rows.extend([[html.escape(k), str(v), "required_skill"] for k, v in sorted(skill_counts.items())])
    return rows or [["N/A", "0", "N/A"]]


def _write_scope_rows(graph: dict[str, Any]) -> list[list[str]]:
    rows = []
    for node in [n for n in graph.get("nodes", []) if isinstance(n, dict)]:
        scope = "<br>".join(html.escape(str(x)) for x in (node.get("write_scope") or [])[:4]) or "N/A"
        rows.append([
            html.escape(str(node.get("id") or "N/A")),
            scope,
            html.escape(str(node.get("risk") or "N/A")),
        ])
    return rows or [["N/A", "N/A", "N/A"]]


def _acceptance_rows(graph: dict[str, Any], text_blocks: list[str]) -> list[list[str]]:
    rows = []
    for node in [n for n in graph.get("nodes", []) if isinstance(n, dict)]:
        acc = "<br>".join(html.escape(str(x)) for x in (node.get("acceptance") or [])[:4]) or "N/A"
        rows.append([
            html.escape(str(node.get("id") or "N/A")),
            acc,
            html.escape(str(len(node.get("acceptance") or []))),
        ])
    if rows:
        return rows
    extracted = []
    for block in text_blocks:
        for line in block.splitlines():
            if any(key in line for key in ("验收", "验证", "stop", "风险")):
                extracted.append(line.strip())
    return [["artifact", "<br>".join(html.escape(x) for x in extracted[:6]) or "N/A", str(len(extracted[:6]))]]


def _hero(title: str, meta: str, badges: list[str]) -> str:
    badge_html = "".join(f'<span class="badge {cls}">{html.escape(label)}</span>' for cls, label in badges)
    return (
        '<header class="hero">'
        f"<h1>{html.escape(title)}</h1>"
        f'<div class="meta">{html.escape(meta)}</div>'
        f'<div class="badges">{badge_html}</div>'
        "</header>"
    )


def _toc() -> str:
    return (
        '<nav class="toc"><h2>目录</h2><ol>'
        '<li><a href="#summary">摘要</a></li>'
        '<li><a href="#architecture">架构设计</a></li>'
        '<li><a href="#flow">流程 / DAG</a></li>'
        '<li><a href="#requirements">Requirement Trace Matrix</a></li>'
        '<li><a href="#contracts">合约 / 约束</a></li>'
        '<li><a href="#stack">技术栈 / 算子绑定</a></li>'
        '<li><a href="#validation">验证 / 风险</a></li>'
        '</ol></nav>'
    )


def _section(section_id: str, title: str, inner: str) -> str:
    return f'<section id="{section_id}"><h2>{html.escape(title)}</h2>{inner}</section>'


def _coverage_block(requirement_trace: dict[str, Any], coverage_report: dict[str, Any], acceptance_verdict: dict[str, Any]) -> str:
    requirement_rows = []
    for item in requirement_trace.get("items", [])[:12]:
        requirement_rows.append([
            html.escape(str(item.get("requirement_id", "N/A"))),
            html.escape(str(item.get("final_status", "N/A"))),
            html.escape(", ".join(str(x) for x in item.get("mapped_nodes", [])[:4]) or "N/A"),
        ])
    if not requirement_rows:
        requirement_rows = [["N/A", "N/A", "N/A"]]
    coverage_summary = coverage_report.get("summary", {})
    return (
        _table(["Requirement", "状态", "映射节点"], requirement_rows)
        + _render_markdown_block(
            "\n".join(
                [
                    f"- total: {coverage_summary.get('total', 'N/A')}",
                    f"- done: {coverage_summary.get('done', 'N/A')}",
                    f"- partial: {coverage_summary.get('partial', 'N/A')}",
                    f"- missing: {coverage_summary.get('missing', 'N/A')}",
                    f"- acceptance_verdict: {acceptance_verdict.get('verdict', 'N/A')}",
                ]
            )
        )
    )


def _ha_toc() -> str:
    return (
        '<nav class="ha-toc"><h2>目录</h2><ol>'
        '<li><a href="#summary">摘要</a></li>'
        '<li><a href="#architecture">架构设计</a></li>'
        '<li><a href="#flow">流程 / DAG</a></li>'
        '<li><a href="#requirements">Requirement Trace Matrix</a></li>'
        '<li><a href="#contracts">合约 / 约束</a></li>'
        '<li><a href="#stack">技术栈 / 算子绑定</a></li>'
        '<li><a href="#validation">验证 / 风险</a></li>'
        '</ol></nav>'
    )


def _render_adapter_page(
    *,
    profile: str,
    title: str,
    hero_title: str,
    lede: str,
    meta: str,
    body_html: str,
    badges: list[str],
) -> str:
    if render_html_anything is None:
        raise HtmlAnythingAdapterError("adapter_unavailable")
    return render_html_anything(
        "",
        profile,
        title=title,
        hero_title=html.escape(hero_title),
        lede=lede,
        meta=meta,
        body_html=body_html,
        toc_html=_ha_toc(),
        badges=badges,
        surface_label=profile.upper(),
        topline_left="Solar Harness",
        topline_center=meta,
        topline_right="html-anything",
        footer_left="Solar Harness",
        footer_right="Default HTML Renderer",
        footer_tail=profile,
    )


def _summary_text(*blocks: str) -> str:
    for block in blocks:
        sections = _split_sections(block)
        if sections:
            return "\n\n".join(body for _, body in sections[:2])
    return ""


def _render_prd_legacy(sid: str) -> str:
    base = SPRINTS_DIR
    status = _read_json(base / f"{sid}.status.json")
    prd = _read_text(base / f"{sid}.prd.md")
    contract = _read_text(base / f"{sid}.contract.md")
    graph = _read_json(base / f"{sid}.task_graph.json")
    requirement_trace = _read_json(base / f"{sid}.requirement_trace.json")
    coverage_report = _read_json(base / f"{sid}.coverage_report.json")
    acceptance_verdict = _read_json(base / f"{sid}.acceptance_verdict.json")
    sections = _split_sections(prd)
    title = str(status.get("title") or sid)
    hero = _hero(
        f"PRD — {title}",
        f"Sprint: {sid} · status: {status.get('status','N/A')} · phase: {status.get('phase','N/A')}",
        [
            ("p0", str(status.get("priority") or "P0")),
            ("lane", str(status.get("lane_hint") or "strategy")),
            ("role", "PM"),
            ("warn", str(status.get("handoff_to") or "planner")),
        ],
    )
    summary_html = _render_markdown_block("\n\n".join(body for _, body in sections[:2]))
    arch_cards = []
    for name, body in sections[2:4] or sections[:2]:
        arch_cards.append(f'<div class="card"><h3>{html.escape(name)}</h3>{_render_markdown_block(body)}</div>')
    contracts_table = _table(
        ["来源", "说明"],
        [
            ["prd.md", "canonical PM 文档"],
            ["contract.md", "Planner/Builder 约束视图"],
            ["task_graph.json", "如存在则展示后续执行图"],
        ],
    )
    stack = _table(["项", "次数", "类别"], _stack_rows(graph))
    validation = _table(["节点/来源", "验收 / 验证", "计数"], _acceptance_rows(graph, [prd, contract]))
    requirements = _coverage_block(requirement_trace, coverage_report, acceptance_verdict)
    flow = (
        f'<div class="diagram">{html.escape(_diagram_from_graph(graph) if graph else "PM -> Planner -> Builder -> Evaluator")}</div>'
        + (_table(["节点", "模型", "技能", "Gate", "依赖"], _node_rows(graph)) if graph else "")
    )
    body = "\n".join([
        hero,
        _toc(),
        _section("summary", "摘要", summary_html),
        _section("architecture", "架构设计", '<div class="grid-2">' + "".join(arch_cards) + "</div>"),
        _section("flow", "流程 / DAG", flow),
        _section("requirements", "Requirement Trace Matrix", requirements),
        _section("contracts", "合约 / 约束", contracts_table + _render_markdown_block(contract)),
        _section("stack", "技术栈 / 算子绑定", stack),
        _section("validation", "验证 / 风险", validation),
    ])
    return _html_page(f"PRD — {title}", body)


def _render_planning_legacy(sid: str) -> str:
    base = SPRINTS_DIR
    status = _read_json(base / f"{sid}.status.json")
    design = _read_text(base / f"{sid}.design.md")
    plan = _read_text(base / f"{sid}.plan.md")
    contract = _read_text(base / f"{sid}.contract.md")
    graph = _read_json(base / f"{sid}.task_graph.json")
    requirement_trace = _read_json(base / f"{sid}.requirement_trace.json")
    coverage_report = _read_json(base / f"{sid}.coverage_report.json")
    acceptance_verdict = _read_json(base / f"{sid}.acceptance_verdict.json")
    title = str(status.get("title") or sid)
    hero = _hero(
        f"Planning — {title}",
        f"Sprint: {sid} · status: {status.get('status','N/A')} · phase: {status.get('phase','N/A')}",
        [
            ("p0", str(status.get("priority") or "P0")),
            ("lane", str(status.get("lane_hint") or "strategy")),
            ("role", "Planner"),
            ("warn", str(status.get("handoff_to") or "builder_main")),
        ],
    )
    design_sections = _split_sections(design)
    plan_sections = _split_sections(plan)
    summary = _render_markdown_block("\n\n".join([body for _, body in (design_sections[:1] + plan_sections[:1])]))
    arch_cards = []
    for name, body in (design_sections[:2] + plan_sections[:2])[:4]:
        arch_cards.append(f'<div class="card"><h3>{html.escape(name)}</h3>{_render_markdown_block(body)}</div>')
    flow = (
        f'<div class="diagram">{html.escape(_diagram_from_graph(graph))}</div>'
        + _table(["节点", "模型", "技能", "Gate", "依赖"], _node_rows(graph))
    )
    contracts = _table(["节点", "write_scope", "risk"], _write_scope_rows(graph))
    stack = _table(["项", "次数", "类别"], _stack_rows(graph))
    validation = _table(["节点/来源", "验收 / 验证", "计数"], _acceptance_rows(graph, [design, plan, contract]))
    coverage_block = _coverage_block(requirement_trace, coverage_report, acceptance_verdict)
    body = "\n".join([
        hero,
        _toc(),
        _section("summary", "摘要", summary),
        _section("architecture", "架构设计", '<div class="grid-2">' + "".join(arch_cards) + "</div>"),
        _section("flow", "流程 / DAG", flow),
        _section("requirements", "Requirement Trace Matrix", coverage_block),
        _section("contracts", "合约 / 约束", contracts + _render_markdown_block(contract)),
        _section("stack", "技术栈 / 算子绑定", stack),
        _section("validation", "验证 / 风险", validation + _render_markdown_block(plan)),
    ])
    return _html_page(f"Planning — {title}", body)


def _render_design_legacy(sid: str) -> str:
    base = SPRINTS_DIR
    status = _read_json(base / f"{sid}.status.json")
    design = _read_text(base / f"{sid}.design.md")
    contract = _read_text(base / f"{sid}.contract.md")
    plan = _read_text(base / f"{sid}.plan.md")
    graph = _read_json(base / f"{sid}.task_graph.json")
    title = str(status.get("title") or sid)
    design_sections = _split_sections(design)
    hero = _hero(
        f"Design — {title}",
        f"Sprint: {sid} · status: {status.get('status','N/A')} · phase: {status.get('phase','N/A')}",
        [
            ("p0", str(status.get("priority") or "P0")),
            ("lane", str(status.get("lane_hint") or "strategy")),
            ("role", "Architecture"),
            ("warn", str(status.get("handoff_to") or "builder_main")),
        ],
    )
    summary = _render_markdown_block(_summary_text(design, contract))
    arch_cards = []
    for name, body in design_sections[:4]:
        arch_cards.append(f'<div class="card"><h3>{html.escape(name)}</h3>{_render_markdown_block(body)}</div>')
    flow = (
        f'<div class="diagram">{html.escape(_diagram_from_graph(graph))}</div>'
        + _table(["节点", "模型", "技能", "Gate", "依赖"], _node_rows(graph))
    )
    body = "\n".join([
        hero,
        _toc(),
        _section("summary", "摘要", summary),
        _section("architecture", "架构设计", '<div class="grid-2">' + "".join(arch_cards) + "</div>"),
        _section("flow", "流程 / DAG", flow),
        _section("requirements", "Requirement Trace Matrix", _render_markdown_block("N/A")),
        _section("contracts", "合约 / 约束", _render_markdown_block(contract)),
        _section("stack", "技术栈 / 算子绑定", _table(["项", "次数", "类别"], _stack_rows(graph))),
        _section("validation", "验证 / 风险", _table(["节点/来源", "验收 / 验证", "计数"], _acceptance_rows(graph, [design, contract, plan]))),
    ])
    return _html_page(f"Design — {title}", body)


def _render_legacy(kind: str, sid: str) -> str:
    if kind == "prd":
        return _render_prd_legacy(sid)
    if kind == "planning":
        return _render_planning_legacy(sid)
    return _render_design_legacy(sid)


def _render_prd_adapter(sid: str) -> str:
    base = SPRINTS_DIR
    status = _read_json(base / f"{sid}.status.json")
    prd = _read_text(base / f"{sid}.prd.md")
    contract = _read_text(base / f"{sid}.contract.md")
    graph = _read_json(base / f"{sid}.task_graph.json")
    requirement_trace = _read_json(base / f"{sid}.requirement_trace.json")
    coverage_report = _read_json(base / f"{sid}.coverage_report.json")
    acceptance_verdict = _read_json(base / f"{sid}.acceptance_verdict.json")
    sections = _split_sections(prd)
    title = str(status.get("title") or sid)
    summary_html = _render_markdown_block("\n\n".join(body for _, body in sections[:2]))
    cards = [
        f'<div class="ha-card"><h3>{html.escape(name)}</h3>{_render_markdown_block(body)}</div>'
        for name, body in (sections[2:4] or sections[:2])
    ]
    body = "\n".join([
        f'<section id="summary"><h2>摘要</h2>{summary_html}</section>',
        f'<section id="architecture"><h2>架构设计</h2><div class="ha-grid-2">{"".join(cards) or "<div class=\"ha-card\"><p>N/A</p></div>"}</div></section>',
        f'<section id="flow"><h2>流程 / DAG</h2><div class="ha-diagram">{html.escape(_diagram_from_graph(graph) if graph else "PM -> Planner -> Builder -> Evaluator")}</div>{_table(["节点", "模型", "技能", "Gate", "依赖"], _node_rows(graph)) if graph else ""}</section>',
        f'<section id="requirements"><h2>Requirement Trace Matrix</h2>{_coverage_block(requirement_trace, coverage_report, acceptance_verdict)}</section>',
        f'<section id="contracts"><h2>合约 / 约束</h2>{_table(["来源", "说明"], [["prd.md", "canonical PM 文档"], ["contract.md", "Planner/Builder 约束视图"], ["task_graph.json", "如存在则展示后续执行图"]])}{_render_markdown_block(contract)}</section>',
        f'<section id="stack"><h2>技术栈 / 算子绑定</h2>{_table(["项", "次数", "类别"], _stack_rows(graph))}</section>',
        f'<section id="validation"><h2>验证 / 风险</h2>{_table(["节点/来源", "验收 / 验证", "计数"], _acceptance_rows(graph, [prd, contract]))}</section>',
    ])
    return _render_adapter_page(
        profile="prd",
        title=f"PRD — {title}",
        hero_title=f"PRD — {title}",
        lede=_summary_text(prd, contract)[:220] or "产品需求、约束与交付图谱。",
        meta=f"Sprint: {sid} · status: {status.get('status','N/A')} · phase: {status.get('phase','N/A')}",
        body_html=body,
        badges=[
            str(status.get("priority") or "P0"),
            str(status.get("lane_hint") or "strategy"),
            "PM",
            str(status.get("handoff_to") or "planner"),
        ],
    )


def _render_planning_adapter(sid: str) -> str:
    base = SPRINTS_DIR
    status = _read_json(base / f"{sid}.status.json")
    design = _read_text(base / f"{sid}.design.md")
    plan = _read_text(base / f"{sid}.plan.md")
    contract = _read_text(base / f"{sid}.contract.md")
    graph = _read_json(base / f"{sid}.task_graph.json")
    requirement_trace = _read_json(base / f"{sid}.requirement_trace.json")
    coverage_report = _read_json(base / f"{sid}.coverage_report.json")
    acceptance_verdict = _read_json(base / f"{sid}.acceptance_verdict.json")
    title = str(status.get("title") or sid)
    design_sections = _split_sections(design)
    plan_sections = _split_sections(plan)
    cards = [
        f'<div class="ha-card"><h3>{html.escape(name)}</h3>{_render_markdown_block(body)}</div>'
        for name, body in (design_sections[:2] + plan_sections[:2])[:4]
    ]
    body = "\n".join([
        f'<section id="summary"><h2>摘要</h2>{_render_markdown_block(_summary_text(design, plan))}</section>',
        f'<section id="architecture"><h2>架构设计</h2><div class="ha-grid-2">{"".join(cards) or "<div class=\"ha-card\"><p>N/A</p></div>"}</div></section>',
        f'<section id="flow"><h2>流程 / DAG</h2><div class="ha-diagram">{html.escape(_diagram_from_graph(graph))}</div>{_table(["节点", "模型", "技能", "Gate", "依赖"], _node_rows(graph))}</section>',
        f'<section id="requirements"><h2>Requirement Trace Matrix</h2>{_coverage_block(requirement_trace, coverage_report, acceptance_verdict)}</section>',
        f'<section id="contracts"><h2>合约 / 约束</h2>{_table(["节点", "write_scope", "risk"], _write_scope_rows(graph))}{_render_markdown_block(contract)}</section>',
        f'<section id="stack"><h2>技术栈 / 算子绑定</h2>{_table(["项", "次数", "类别"], _stack_rows(graph))}</section>',
        f'<section id="validation"><h2>验证 / 风险</h2>{_table(["节点/来源", "验收 / 验证", "计数"], _acceptance_rows(graph, [design, plan, contract]))}{_render_markdown_block(plan)}</section>',
    ])
    return _render_adapter_page(
        profile="planning",
        title=f"Planning — {title}",
        hero_title=f"Planning — {title}",
        lede=_summary_text(design, plan)[:220] or "规划、节点拆解与执行合约。",
        meta=f"Sprint: {sid} · status: {status.get('status','N/A')} · phase: {status.get('phase','N/A')}",
        body_html=body,
        badges=[
            str(status.get("priority") or "P0"),
            str(status.get("lane_hint") or "strategy"),
            "Planner",
            str(status.get("handoff_to") or "builder_main"),
        ],
    )


def _render_design_adapter(sid: str) -> str:
    base = SPRINTS_DIR
    status = _read_json(base / f"{sid}.status.json")
    design = _read_text(base / f"{sid}.design.md")
    contract = _read_text(base / f"{sid}.contract.md")
    plan = _read_text(base / f"{sid}.plan.md")
    graph = _read_json(base / f"{sid}.task_graph.json")
    requirement_trace = _read_json(base / f"{sid}.requirement_trace.json")
    coverage_report = _read_json(base / f"{sid}.coverage_report.json")
    acceptance_verdict = _read_json(base / f"{sid}.acceptance_verdict.json")
    title = str(status.get("title") or sid)
    design_sections = _split_sections(design)
    cards = [
        f'<div class="ha-card"><h3>{html.escape(name)}</h3>{_render_markdown_block(body)}</div>'
        for name, body in design_sections[:4]
    ]
    body = "\n".join([
        f'<section id="summary"><h2>摘要</h2>{_render_markdown_block(_summary_text(design, contract, plan))}</section>',
        f'<section id="architecture"><h2>架构设计</h2><div class="ha-grid-2">{"".join(cards) or "<div class=\"ha-card\"><p>N/A</p></div>"}</div></section>',
        f'<section id="flow"><h2>流程 / DAG</h2><div class="ha-diagram">{html.escape(_diagram_from_graph(graph))}</div>{_table(["节点", "模型", "技能", "Gate", "依赖"], _node_rows(graph)) if graph else ""}</section>',
        f'<section id="requirements"><h2>Requirement Trace Matrix</h2>{_coverage_block(requirement_trace, coverage_report, acceptance_verdict)}</section>',
        f'<section id="contracts"><h2>合约 / 约束</h2>{_render_markdown_block(contract)}</section>',
        f'<section id="stack"><h2>技术栈 / 算子绑定</h2>{_table(["项", "次数", "类别"], _stack_rows(graph))}</section>',
        f'<section id="validation"><h2>验证 / 风险</h2>{_table(["节点/来源", "验收 / 验证", "计数"], _acceptance_rows(graph, [design, contract, plan]))}</section>',
    ])
    return _render_adapter_page(
        profile="design",
        title=f"Design — {title}",
        hero_title=f"Design — {title}",
        lede=_summary_text(design, contract, plan)[:220] or "架构设计、边界与验证面。",
        meta=f"Sprint: {sid} · status: {status.get('status','N/A')} · phase: {status.get('phase','N/A')}",
        body_html=body,
        badges=[
            str(status.get("priority") or "P0"),
            str(status.get("lane_hint") or "strategy"),
            "Architecture",
            str(status.get("handoff_to") or "builder_main"),
        ],
    )


def _render_default(kind: str, sid: str) -> str:
    if kind == "prd":
        return _render_prd_adapter(sid)
    if kind == "planning":
        return _render_planning_adapter(sid)
    return _render_design_adapter(sid)


def render(args: argparse.Namespace) -> int:
    sid = args.sid
    kind = args.kind
    if kind not in VALID_KINDS:
        print(f"invalid kind: {kind}", file=sys.stderr)
        return 2
    output = Path(args.output).expanduser() if args.output else SPRINTS_DIR / f"{sid}.{kind}.html"
    renderer = "legacy" if os.environ.get("SOLAR_USE_LEGACY_RENDERER", "").strip() in {"1", "true", "TRUE", "yes", "on"} else "html-anything"
    warnings: list[str] = []
    try:
        html_text = _render_legacy(kind, sid) if renderer == "legacy" else _render_default(kind, sid)
    except Exception as exc:
        if renderer == "legacy":
            raise
        warnings.append(f"html_anything_fallback:{exc}")
        renderer = "legacy"
        html_text = _render_legacy(kind, sid)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    payload: dict[str, Any] = {"ok": True, "sid": sid, "kind": kind, "path": str(output), "renderer": renderer}
    if warnings:
        payload["warnings"] = warnings
    if args.register:
        helper = HARNESS_DIR / "lib" / "html_artifact.py"
        artifact_kind_map = {
            "prd": "prd_html",
            "planning": "planning_html",
            "design": "design_html",
        }
        cmd = [sys.executable, str(helper), "register", "--sid", sid, "--kind", artifact_kind_map[kind], "--path", str(output)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        payload["registered"] = proc.returncode == 0
        payload["register_stdout"] = (proc.stdout or "").strip()
        payload["register_stderr"] = (proc.stderr or "").strip()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"render_sprint_html sid={sid} kind={kind} renderer={renderer} path={output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render richer sprint HTML artifacts")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render", help="Render one sprint HTML artifact")
    p.add_argument("--sid", required=True)
    p.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    p.add_argument("--output")
    p.add_argument("--register", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=render)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
