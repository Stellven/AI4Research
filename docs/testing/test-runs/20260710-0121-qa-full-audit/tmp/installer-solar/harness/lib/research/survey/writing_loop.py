"""Deterministic section writer/reviewer/reviser loop for survey reports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .backends import HumanResponseMissingError, LocalCommandWriterError, PanePacketPendingError, get_writer_backend
from .schemas import SectionPromptPacket, SectionReview, SectionRevisionTrace, to_dict

PROFESSOR_GRADE_WRITING_POLICY = {
    "policy_id": "solar.survey.professor_grade_writing.v1",
    "purpose": "Turn evidence packs into auditable professor-grade survey sections instead of generic long-form summaries.",
    "section_template": [
        "Research Question",
        "Position",
        "Claim Map",
        "Evidence Map",
        "Source Map",
        "Literature Lineage",
        "Method Taxonomy",
        "Architecture Synthesis",
        "Comparative Positioning",
        "Terminology Evolution",
        "Evaluation Protocol Matrix",
        "Evaluation And Risk Boundary",
        "Limitations And Failure Modes",
        "Controversy Matrix",
        "Contradiction Slots",
        "Open Problems",
    ],
    "synthesis_rules": [
        "Separate mechanism, system, evaluation, and deployment claims.",
        "State which source type supports each important conclusion.",
        "Prefer bounded conclusions when evidence comes from narrow benchmarks or partial implementations.",
        "Surface contradictions and missing evidence in the main body, not only in footnotes.",
        "Preserve claim/evidence tags so factuality gates can audit the section mechanically.",
    ],
    "forbidden_patterns": [
        "Do not invent source names, URLs, metrics, benchmarks, or paper results.",
        "Do not collapse paper evidence, official docs, code, and benchmarks into one undifferentiated citation bucket.",
        "Do not turn open problems into vague future-work filler.",
    ],
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _row_id(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _load_ledgers(root: Path) -> dict[str, dict[str, dict]]:
    sources = {_row_id(row, "id", "source_id"): row for row in _read_jsonl(root / "sources.jsonl")}
    evidence = {_row_id(row, "id", "evidence_id"): row for row in _read_jsonl(root / "evidence.jsonl")}
    claims = {_row_id(row, "id", "claim_id"): row for row in _read_jsonl(root / "claims.jsonl")}
    return {"sources": sources, "evidence": evidence, "claims": claims}


def _evidence_text(row: dict) -> str:
    return str(row.get("content") or row.get("span_text") or row.get("clean_markdown") or row.get("text") or row.get("title") or "")


def _claim_text(row: dict) -> str:
    return str(row.get("claim_text") or row.get("text") or row.get("title") or "")


def _inline_text(value: Any, *, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"\b(Title|URL|Publisher|Published|Source Type):\s*", r"\1=", text)
    return text[:limit].strip()


def _section_anchor(section_id: str, title: str, chapter: dict[str, Any]) -> str:
    chapter_id = str(chapter.get("chapter_id") or section_id.split("/", 1)[0])
    order = str(chapter.get("section_order_in_chapter") or "N/A")
    return f"{chapter_id}#{order}::{section_id}::{title}"


def _section_lens(title: str, question: str, source_types: list[str], order: int) -> dict[str, str]:
    title_l = title.lower()
    question_l = question.lower()
    if re.search(r"architecture|架构|mechanism|机制|method|taxonomy|分类", title_l + " " + question_l):
        axis = "architecture"
        focus = "机制分层、状态表示、系统边界和可复现实现路径"
        risk = "把机制可行性误读为工程可控性"
    elif re.search(r"eval|benchmark|评估|评价|metric|数据", title_l + " " + question_l):
        axis = "evaluation"
        focus = "任务覆盖、指标口径、baseline 公平性和外推边界"
        risk = "用单一 benchmark 结果替代跨任务可靠性判断"
    elif re.search(r"deploy|engineering|system|工程|部署|成本", title_l + " " + question_l):
        axis = "deployment"
        focus = "调度成本、观测性、失败恢复和生产约束"
        risk = "忽略隐状态方法在真实调用链中的可诊断性成本"
    elif re.search(r"contradiction|limit|risk|争议|局限|失败", title_l + " " + question_l):
        axis = "controversy"
        focus = "反证来源、负例任务、不可复现实验和术语冲突"
        risk = "只保留支持性证据而删除失败路径"
    else:
        axis = ["mechanism", "evidence", "integration", "roadmap"][max(order - 1, 0) % 4]
        focus = "概念边界、证据类型、章节衔接和后续研究问题"
        risk = "把材料摘要写成无可审计边界的泛化结论"
    primary_source = source_types[0] if source_types else "unknown"
    secondary_source = source_types[1] if len(source_types) > 1 else primary_source
    return {
        "axis": axis,
        "focus": focus,
        "risk": risk,
        "primary_source": primary_source,
        "secondary_source": secondary_source,
    }


def _dedupe_sentences(text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        key = re.sub(r"\s+", " ", line.strip().lower())
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def _chapter_context(root: Path, section_id: str, spec: dict) -> dict[str, Any]:
    ast = _read_json(root / "survey_report_ast.json")
    chapter_id = str(spec.get("chapter_id") or section_id.split("/", 1)[0])
    chapters = ast.get("chapters", []) if isinstance(ast.get("chapters"), list) else []
    sections = ast.get("sections", []) if isinstance(ast.get("sections"), list) else []
    chapter = next((row for row in chapters if str(row.get("chapter_id") or "") == chapter_id), {})
    sibling_sections = [
        {
            "section_id": str(row.get("section_id") or ""),
            "title": str(row.get("title") or ""),
            "research_question": str(row.get("research_question") or ""),
        }
        for row in sections
        if str(row.get("chapter_id") or "") == chapter_id
    ]
    return {
        "chapter_id": chapter_id,
        "chapter_title": str(chapter.get("title") or chapter_id),
        "chapter_objective": str(chapter.get("objective") or ""),
        "section_order_in_chapter": next((idx + 1 for idx, row in enumerate(sibling_sections) if row.get("section_id") == section_id), 0),
        "sibling_sections": sibling_sections,
        "chapter_prompt_packet": str(root / "chapters" / chapter_id / "prompt_packet.md"),
    }


def _source_type_guidance(source_types: list[str]) -> list[str]:
    guidance = {
        "paper": "Use papers for mechanisms, assumptions, experimental claims, and limits of generalization.",
        "preprint": "Treat preprints as useful but provisional; preserve uncertainty.",
        "official_doc": "Use official docs for system boundaries, APIs, deployment constraints, and supported behavior.",
        "code": "Use code repositories for reproducibility, implementation cost, integration boundaries, and maintenance risk.",
        "repo": "Use repositories for reproducibility, implementation cost, integration boundaries, and maintenance risk.",
        "benchmark": "Use benchmarks for evaluation scope, metric caveats, and comparability limits.",
        "dataset": "Use datasets for task coverage, distribution assumptions, leakage, and annotation limits.",
    }
    return [guidance.get(str(item), f"Use {item} sources only for claims they directly support.") for item in source_types]


def build_section_prompt_packet(root: Path, section_id: str, round_index: int = 0, writer_backend: str = "deterministic") -> dict:
    section_dir = root / "sections" / section_id
    spec = _read_json(section_dir / "section.spec.json")
    pack = _read_json(section_dir / "evidence_pack.json")
    source_types = [str(item) for item in pack.get("source_types", []) if str(item)] if isinstance(pack.get("source_types"), list) else []
    chapter_context = _chapter_context(root, section_id, spec)
    packet = SectionPromptPacket(
        section_id=section_id,
        round_index=round_index,
        writer_backend=writer_backend,
        role="professor-grade technical survey section writer",
        task=f"Write or revise section '{spec.get('title') or section_id}' from the provided evidence pack only.",
        constraints=[
            "Use the section evidence pack as the source of truth.",
            "Bind important factual claims to [claim:<id>] and [evidence:<id>] tags.",
            "Separate architecture synthesis, evaluation limits, contradiction slots, and open problems.",
            "Do not invent sources, results, paper names, URLs, or benchmark numbers.",
            "Preserve uncertainty when evidence is weak or contradictory.",
        ],
        output_contract=[
            "Markdown section draft.",
            "At least six second-level headings.",
            "Follow the professor-grade section template in writing_policy.section_template.",
            "Include Literature Lineage, Method Taxonomy, Architecture Synthesis, Comparative Positioning, Terminology Evolution, Evaluation Protocol Matrix, Evaluation And Risk Boundary, Limitations And Failure Modes, Controversy Matrix, Contradiction Slots, and Open Problems.",
            "All core claims must reference claim_id and evidence_id tags.",
        ],
        artifact_paths={
            "section_spec": str(section_dir / "section.spec.json"),
            "evidence_pack": str(section_dir / "evidence_pack.json"),
            "human_response": str(section_dir / "human_responses" / f"round_{round_index:02d}.md"),
            "pane_dispatch": str(section_dir / "pane_dispatch" / f"round_{round_index:02d}.md"),
            "prompt_packet_md": str(section_dir / "prompt_packets" / f"round_{round_index:02d}.md"),
            "draft": str(section_dir / "draft.md"),
            "review": str(section_dir / "review.json"),
            "revision_trace": str(section_dir / "revision_trace.json"),
            "final": str(section_dir / "final.md"),
            "model_usage": str(root / "model_usage.jsonl"),
        },
    )
    payload = to_dict(packet)
    payload["section_spec"] = spec
    payload["evidence_pack"] = pack
    payload["chapter_context"] = chapter_context
    payload["writing_policy"] = PROFESSOR_GRADE_WRITING_POLICY
    payload["source_type_guidance"] = _source_type_guidance(source_types)
    payload["synthesis_outline"] = [
        "Define the local research question and scope.",
        "Map claims to evidence and source types.",
        "Synthesize architecture mechanisms before evaluation claims.",
        "Compare source families instead of flattening them into citations.",
        "State evaluation limits and failure modes.",
        "End with open problems that can feed chapter-level synthesis.",
    ]
    payload["required_claim_ids"] = list(pack.get("claim_ids", [])[:6])
    payload["required_evidence_ids"] = list(pack.get("evidence_ids", [])[:8])
    return payload


def _write_chapter_prompt_packet(root: Path, packet: dict) -> None:
    chapter = packet.get("chapter_context") if isinstance(packet.get("chapter_context"), dict) else {}
    chapter_id = str(chapter.get("chapter_id") or "")
    if not chapter_id:
        return
    chapter_dir = root / "chapters" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "chapter_id": chapter_id,
        "chapter_title": chapter.get("chapter_title") or chapter_id,
        "chapter_objective": chapter.get("chapter_objective") or "",
        "active_section_id": packet.get("section_id"),
        "writer_backend": packet.get("writer_backend"),
        "writing_policy": packet.get("writing_policy"),
        "sibling_sections": chapter.get("sibling_sections") or [],
        "chapter_synthesis_contract": [
            "Ensure sibling sections do not repeat the same argument.",
            "Keep terminology consistent across the chapter.",
            "Preserve contradiction slots for chief-editor review.",
            "Make source-type differences visible in section conclusions.",
        ],
    }
    (chapter_dir / "prompt_packet.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# Chapter Prompt Packet: {payload['chapter_title']}",
        "",
        f"- Chapter ID: {chapter_id}",
        f"- Active Section: {payload.get('active_section_id')}",
        "",
        "## Objective",
        "",
        str(payload.get("chapter_objective") or ""),
        "",
        "## Professor-Grade Section Template",
        "",
    ]
    lines.extend(f"- {item}" for item in (payload.get("writing_policy") or {}).get("section_template", []))
    lines.extend(["", "## Sibling Sections", ""])
    for section in payload.get("sibling_sections", []):
        lines.append(f"- {section.get('section_id')}: {section.get('title')}")
    lines.extend(["", "## Chapter Synthesis Contract", ""])
    lines.extend(f"- {item}" for item in payload.get("chapter_synthesis_contract", []))
    (chapter_dir / "prompt_packet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_prompt_packet(section_dir: Path, packet: dict) -> None:
    prompt_dir = section_dir / "prompt_packets"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    round_index = int(packet.get("round_index") or 0)
    json_path = prompt_dir / f"round_{round_index:02d}.json"
    md_path = prompt_dir / f"round_{round_index:02d}.md"
    json_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = [
        f"# Survey Section Prompt Packet: {packet.get('section_id')}",
        "",
        f"- Backend: {packet.get('writer_backend')}",
        f"- Round: {round_index}",
        f"- Role: {packet.get('role')}",
        "",
        "## Task",
        "",
        str(packet.get("task") or ""),
        "",
        "## Constraints",
        "",
    ]
    md.extend(f"- {item}" for item in packet.get("constraints", []))
    md.extend(["", "## Output Contract", ""])
    md.extend(f"- {item}" for item in packet.get("output_contract", []))
    md.extend(["", "## Chapter Context", ""])
    chapter = packet.get("chapter_context") if isinstance(packet.get("chapter_context"), dict) else {}
    md.extend([
        f"- Chapter: {chapter.get('chapter_id', 'N/A')} / {chapter.get('chapter_title', 'N/A')}",
        f"- Section Order In Chapter: {chapter.get('section_order_in_chapter', 'N/A')}",
        f"- Chapter Packet: {chapter.get('chapter_prompt_packet', 'N/A')}",
    ])
    md.extend(["", "## Professor-Grade Section Template", ""])
    md.extend(f"- {item}" for item in (packet.get("writing_policy") or {}).get("section_template", []))
    md.extend(["", "## Source-Type Guidance", ""])
    md.extend(f"- {item}" for item in packet.get("source_type_guidance", []))
    md.extend(["", "## Synthesis Outline", ""])
    md.extend(f"- {item}" for item in packet.get("synthesis_outline", []))
    md.extend(["", "## Required Claims", ""])
    md.extend(f"- {item}" for item in packet.get("required_claim_ids", []))
    md.extend(["", "## Required Evidence", ""])
    md.extend(f"- {item}" for item in packet.get("required_evidence_ids", []))
    md.extend([
        "",
        "## Human Response Path",
        "",
        str((packet.get("artifact_paths") or {}).get("human_response") or "N/A"),
        "",
        "## Return Instructions",
        "",
        "Write the completed Markdown section to the human response path above, then rerun the same survey command.",
    ])
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    _write_chapter_prompt_packet(section_dir.parents[2], packet)


def build_section_draft(root: Path, section_id: str, round_index: int = 0) -> str:
    section_dir = root / "sections" / section_id
    spec = _read_json(section_dir / "section.spec.json")
    pack = _read_json(section_dir / "evidence_pack.json")
    ledgers = _load_ledgers(root)
    chapter_context = _chapter_context(root, section_id, spec)
    claims = [ledgers["claims"].get(cid, {}) for cid in pack.get("claim_ids", [])]
    evidence = [ledgers["evidence"].get(eid, {}) for eid in pack.get("evidence_ids", [])]
    sources = [ledgers["sources"].get(sid, {}) for sid in pack.get("source_ids", [])]
    claim_ids = [cid for cid in pack.get("claim_ids", []) if cid]
    evidence_ids = [eid for eid in pack.get("evidence_ids", []) if eid]
    title = spec.get("title") or section_id
    question = spec.get("research_question") or ""
    source_type_list = [str(item) for item in pack.get("source_types", []) if str(item)] if isinstance(pack.get("source_types"), list) else []
    source_types = ", ".join(source_type_list) or "N/A"
    anchor = _section_anchor(section_id, str(title), chapter_context)
    lens = _section_lens(str(title), str(question), source_type_list, int(chapter_context.get("section_order_in_chapter") or 0))
    primary_claims = claims[: max(3, min(len(claims), 6))]
    primary_evidence = evidence[: max(4, min(len(evidence), 8))]

    claim_lines = []
    for idx, row in enumerate(primary_claims, start=1):
        cid = claim_ids[idx - 1] if idx - 1 < len(claim_ids) else f"claim_{idx}"
        eid = evidence_ids[(idx - 1) % len(evidence_ids)] if evidence_ids else "evidence_missing"
        text = _inline_text(_claim_text(row), limit=260) or f"{title} needs explicit claim support."
        claim_lines.append(f"{idx}. {anchor} claim-slot-{idx} turns '{text}' into a bounded {lens['axis']} claim instead of a generic survey assertion. [claim:{cid}] [evidence:{eid}]")

    evidence_lines = []
    for idx, row in enumerate(primary_evidence, start=1):
        eid = evidence_ids[idx - 1] if idx - 1 < len(evidence_ids) else f"evidence_{idx}"
        sid = str(row.get("source_id") or "")
        src = ledgers["sources"].get(sid, {})
        source_type = src.get("source_type") or "unknown"
        text = _inline_text(_evidence_text(row), limit=220) or f"{title} evidence span."
        evidence_lines.append(f"- {anchor} evidence-slot-{idx}: {eid} / {source_type} supports {lens['focus']} with span summary '{text}'. [evidence:{eid}]")

    source_lines = []
    for idx, row in enumerate(sources[:8], start=1):
        sid = _row_id(row, "id", "source_id") or "source_unknown"
        source_lines.append(f"- {anchor} source-slot-{idx}: {sid}: {row.get('source_type', 'unknown')} / {_inline_text(row.get('title', 'untitled'), limit=120)}")

    if round_index == 0:
        compact_claim_lines = []
        for idx, cid in enumerate(claim_ids[:2] or ["claim_missing"], start=1):
            eid = evidence_ids[(idx - 1) % len(evidence_ids)] if evidence_ids else "evidence_missing"
            compact_claim_lines.append(f"{idx}. {anchor} maps claim {cid} to {lens['axis']} scope and source boundary. [claim:{cid}] [evidence:{eid}]")
        compact_evidence_lines = []
        for idx, eid in enumerate(evidence_ids[:3] or ["evidence_missing"], start=1):
            compact_evidence_lines.append(f"- {anchor} evidence-slot-{idx}: {eid} checks {lens['focus']}. [evidence:{eid}]")
        compact_source_lines = source_lines[:3] or [f"- {anchor} source-slot-1: source_unknown / N/A"]
        compact = f"""# {title}

## Research Question

{question}

## Position

{anchor} frames this section around {lens['focus']} with source types `{source_types}` and keeps `{lens['risk']}` as the downgrade condition. [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Claim Map

{chr(10).join(compact_claim_lines)}

## Evidence Map

{chr(10).join(compact_evidence_lines)}

## Source Map

{chr(10).join(compact_source_lines)}

## Literature Lineage

{anchor} maps the local literature lineage from explicit reasoning-chain baselines to continuous thought, hidden-state deliberation, and Coconut-style latent reasoning while keeping paper, code, benchmark, and official documentation evidence separate. [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Method Taxonomy

{anchor} classifies methods by representation, control policy, supervision signal, and observability boundary so latent-state architecture claims do not collapse into one generic mechanism bucket. [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Architecture Synthesis

{anchor} separates mechanism, system, and evaluation layers for {lens['axis']} analysis so implementation and evidence claims stay auditable. [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Comparative Positioning

{anchor} treats `{lens['primary_source']}` as the primary source family and `{lens['secondary_source']}` as calibration evidence; missing families lower confidence. [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Terminology Evolution

{anchor} tracks the terminology path from chain-of-thought and explicit reasoning chains toward continuous thought, hidden-state deliberation, Coconut-style latent reasoning, and auditable hybrid systems. [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Evaluation And Risk Boundary

{anchor} checks task form, metric scope, reproducibility, and deployment transfer before allowing strong conclusions. [claim:{claim_ids[1] if len(claim_ids) > 1 else 'claim_missing'}] [evidence:{evidence_ids[1] if len(evidence_ids) > 1 else 'evidence_missing'}]

## Evaluation Protocol Matrix

{anchor} compares benchmark task family, baseline or ablation design, metric interpretation, reproducibility evidence, and deployment transfer risk before any claim can become a chapter-level conclusion. [claim:{claim_ids[1] if len(claim_ids) > 1 else 'claim_missing'}] [evidence:{evidence_ids[1] if len(evidence_ids) > 1 else 'evidence_missing'}]

## Limitations And Failure Modes

{anchor} keeps short-task bias, single-model evidence, benchmark mismatch, and missing failure-path documentation in the main text. [claim:{claim_ids[1] if len(claim_ids) > 1 else 'claim_missing'}] [evidence:{evidence_ids[1] if len(evidence_ids) > 1 else 'evidence_missing'}]

## Controversy Matrix

{anchor} separates support evidence, negative evidence, baseline disputes, interpretability disputes, and deployment-risk disputes so the section does not hide controversy behind a single limitations paragraph. [claim:{claim_ids[2] if len(claim_ids) > 2 else 'claim_missing'}] [evidence:{evidence_ids[2] if len(evidence_ids) > 2 else 'evidence_missing'}]

## Contradiction Slots

{anchor} reserves contradiction slots for narrow evidence coverage, source-family disagreement, and unobserved failure modes connected to `{lens['risk']}`. [claim:{claim_ids[2] if len(claim_ids) > 2 else 'claim_missing'}] [evidence:{evidence_ids[2] if len(evidence_ids) > 2 else 'evidence_missing'}]

## Open Problems

{anchor} needs later expansion on {lens['focus']}, source comparability, terminology consistency, and claim-to-evidence traceability.
"""
        return _dedupe_sentences(compact)

    expansion = ""
    if round_index >= 1:
        expansion = f"""
## Revision: Architecture And Evaluation Detail

{anchor} 的本轮修订围绕 {lens['focus']} 展开，而不是复述通用写作模板；`{source_types}` 证据被拆成主来源 `{lens['primary_source']}` 与校验来源 `{lens['secondary_source']}`，前者限定论证入口，后者校准评价或工程边界。该节结论必须显式标注 `{lens['risk']}` 这一降级条件，避免把局部实验直接升级为通用规律。 [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Revision: Terminology Evolution And Academic Survey Frame

{anchor} 将术语演进显式写入正文：chain-of-thought 或显式推理链强调 token-level narration，continuous thought 强调连续隐变量计算，hidden-state deliberation 强调内部状态迁移，Coconut-style latent reasoning 则把这些机制放入可训练和可评估的架构 taxonomy。教授级 survey 必须同时记录 baseline、ablation、evaluation protocol、reproducibility、deployment 和 auditability，否则长文只是材料堆叠。 [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]
"""
    if round_index >= 2:
        expansion += f"""
## Revision: Contradictions, Open Problems, And Survey Position

{anchor} 的反证段落进入主论证而不是附录：当 `{lens['axis']}` 证据只覆盖窄任务、单模型或不可观测 hidden-state trajectory 时，本节必须区分“机制上可行”“工程上可控”“评估上可信”三个层级。该节保留的开放问题聚焦 {lens['focus']}，并把 `{lens['risk']}` 作为 chief-editor 后续重写时必须处理的风险项。 [claim:{claim_ids[-1] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[-1] if evidence_ids else 'evidence_missing'}]
"""

    draft = f"""# {title}

## Research Question

{question}

## Position

{anchor} 以 evidence pack 为事实源，目标不是堆材料，而是围绕 {lens['focus']} 建立可审计的 survey 论证；本节先限定 `{lens['axis']}` 问题边界，再比较证据强度、工程代价、评价可信度和开放争议。当前证据包包含来源类型 `{source_types}`，其中 `{lens['primary_source']}` 只能支持其直接覆盖的结论，不能替代跨章节 synthesis。 [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Claim Map

{chr(10).join(claim_lines)}

## Evidence Map

{chr(10).join(evidence_lines)}

## Source Map

{chr(10).join(source_lines)}

## Literature Lineage

{anchor} 的 literature lineage 不按来源顺序机械拼接，而是把显式 chain-of-thought 基线、continuous thought 过渡、hidden-state deliberation、Coconut-style latent reasoning 和生产可审计混合系统放到一条可批判的演进线上。论文证据负责机制与实验假设，代码证据负责可复现路径，benchmark 证据负责评价协议，official_doc 负责部署边界。 [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Method Taxonomy

{anchor} 的 method taxonomy 按四个轴拆分：representation 轴区分 token、continuous state 与 hidden state；control policy 轴区分固定步数、adaptive deliberation 与 verifier-coupled search；supervision 轴区分 imitation、RL、self-training 与 synthetic traces；observability 轴区分可审计 token trace、弱可解释 latent trajectory 与黑箱内部状态。 [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Architecture Synthesis

在 {anchor} 中，架构 synthesis 先拆成机制层、系统层和评价层：机制层解释 {lens['focus']} 为什么可能成立，系统层检查它如何被实现、调度、复现和迁移，评价层判断现有 `{source_types}` 是否足以支撑本节结论。三层必须保持分离，否则 `{lens['axis']}` 主题会把概念说明、经验判断和工程结论混成看似深入但不可审计的叙述。 [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Comparative Positioning

{anchor} 的 comparative positioning 不把所有引用压成同一权重：`{lens['primary_source']}` 提供本节主证据，`{lens['secondary_source']}` 用来检查外推边界，其余来源只补充实现、评价或部署侧信息。若某一来源类型缺失，本节结论必须降级为局部判断；只有多类来源围绕 {lens['focus']} 相互支撑时，才可以进入章节级 survey 判断。 [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Terminology Evolution

{anchor} tracks the terminology path from chain-of-thought and explicit reasoning chains toward continuous thought, hidden-state deliberation, Coconut-style latent reasoning, and auditable hybrid systems. [claim:{claim_ids[0] if claim_ids else 'claim_missing'}] [evidence:{evidence_ids[0] if evidence_ids else 'evidence_missing'}]

## Evaluation Protocol Matrix

{anchor} 的 evaluation protocol matrix 至少比较五列：task family 是否覆盖长程推理，baseline/ablation 是否公平，metric 是否区分准确率、成本与可审计性，reproducibility 是否能由代码或数据卡复核，deployment transfer 是否会引入观测性和回滚成本。缺任一列时，本节结论必须降级。 [claim:{claim_ids[1] if len(claim_ids) > 1 else 'claim_missing'}] [evidence:{evidence_ids[1] if len(evidence_ids) > 1 else 'evidence_missing'}]

## Evaluation And Risk Boundary

{anchor} 的 evaluation boundary 必须说明数据集、任务形态、指标口径和外推边界，并把 `{lens['risk']}` 标为主要降级风险。若证据来自论文，应检查实验设置和 baseline；若证据来自代码，应检查可运行性、维护状态和实现约束；若证据来自 benchmark，应检查任务覆盖和指标是否与本节 `{lens['axis']}` 场景一致。 [claim:{claim_ids[1] if len(claim_ids) > 1 else 'claim_missing'}] [evidence:{evidence_ids[1] if len(evidence_ids) > 1 else 'evidence_missing'}]

## Limitations And Failure Modes

{anchor} 必须把 failure modes 写在正文中：{lens['focus']} 可能只在短任务、单模型、单 benchmark 或不可复现实验中成立，代码证据可能缺少生产约束，官方文档也可能只描述支持路径而不覆盖失败路径。因此，本节结论需要标注适用条件、不可外推区域和后续 evidence miner 必须补齐的缺口。 [claim:{claim_ids[1] if len(claim_ids) > 1 else 'claim_missing'}] [evidence:{evidence_ids[1] if len(evidence_ids) > 1 else 'evidence_missing'}]

## Controversy Matrix

{anchor} 的 controversy matrix 分成支持证据、负面证据、baseline 争议、interpretability 争议和 deployment-risk 争议五栏。若 `{lens['primary_source']}` 与 `{lens['secondary_source']}` 在任务规模、实现假设或评价口径上冲突，本节必须把冲突保留为争议项，而不是在 narrative synthesis 中抹平。 [claim:{claim_ids[2] if len(claim_ids) > 2 else 'claim_missing'}] [evidence:{evidence_ids[2] if len(evidence_ids) > 2 else 'evidence_missing'}]

## Contradiction Slots

{anchor} 保留三个反证槽位：第一，`{lens['primary_source']}` 证据可能只覆盖 {lens['focus']} 的局部任务；第二，`{lens['secondary_source']}` 与主来源之间可能存在时间差、实现差或评价口径差；第三，`{lens['risk']}` 可能没有被现有 benchmark 捕捉。后续 chapter synthesis 必须消费这些槽位，不能只保留支持性证据。 [claim:{claim_ids[2] if len(claim_ids) > 2 else 'claim_missing'}] [evidence:{evidence_ids[2] if len(evidence_ids) > 2 else 'evidence_missing'}]
{expansion}
## Open Problems

{anchor} 的开放问题不是通用 future-work 列表，而是要求下一轮围绕 {lens['focus']} 补充反证来源、统一 `{lens['axis']}` 术语、复核 `{lens['primary_source']}` 与 `{lens['secondary_source']}` 的可比性，并量化 `{lens['risk']}` 对章节结论的影响。该节最终版本应把这些问题映射回 claim_id 和 evidence_id，而不是依赖模型自由发挥。
"""
    return _dedupe_sentences(draft)


def review_section_text(root: Path, section_id: str, text: str, min_chars: int = 1200) -> SectionReview:
    section_dir = root / "sections" / section_id
    pack = _read_json(section_dir / "evidence_pack.json")
    issues: list[str] = []
    if pack.get("status") != "ready":
        issues.extend(pack.get("blockers") or ["evidence_pack_blocked"])
    if len(text) < min_chars:
        issues.append(f"section_chars_low:{len(text)}<{min_chars}")
    claim_tags = set(re.findall(r"\[claim:([^\]]+)\]", text))
    evidence_tags = set(re.findall(r"\[evidence:([^\]]+)\]", text))
    required_claims = set(str(x) for x in pack.get("claim_ids", [])[:3])
    required_evidence = set(str(x) for x in pack.get("evidence_ids", [])[:4])
    missing_claims = sorted(required_claims - claim_tags)
    missing_evidence = sorted(required_evidence - evidence_tags)
    if missing_claims:
        issues.append("missing_claim_tags:" + ",".join(missing_claims))
    if missing_evidence:
        issues.append("missing_evidence_tags:" + ",".join(missing_evidence))
    headings = len(re.findall(r"^##\s+", text, flags=re.M))
    if headings < 6:
        issues.append(f"section_structure_shallow:{headings}<6")
    if not re.search(r"Contradiction|反证|争议", text, flags=re.I):
        issues.append("contradiction_section_missing")
    if not re.search(r"Evaluation|评价|评估", text, flags=re.I):
        issues.append("evaluation_section_missing")
    if not re.search(r"Comparative Positioning|比较|对比", text, flags=re.I):
        issues.append("comparative_positioning_missing")
    if not re.search(r"Limitations|Failure Modes|局限|失败模式", text, flags=re.I):
        issues.append("limitations_failure_modes_missing")
    source_types = pack.get("source_types", [])
    source_diversity = min(len(source_types) / 4, 1.0)
    if source_diversity < 0.5:
        issues.append(f"source_diversity_low:{source_diversity:.2f}<0.50")
    unsupported = len(missing_claims) / max(len(required_claims), 1)
    citation_accuracy = 1.0 - (len(missing_evidence) / max(len(required_evidence), 1))
    paragraphs = [re.sub(r"\s+", " ", p.strip().lower()) for p in text.split("\n\n") if p.strip()]
    repetition = 1.0 - (len(set(paragraphs)) / max(len(paragraphs), 1))
    verdict = "PASS" if not issues else "REVISE"
    return SectionReview(
        section_id=section_id,
        verdict=verdict,
        unsupported_claim_rate=round(unsupported, 4),
        citation_span_accuracy=round(citation_accuracy, 4),
        source_diversity_score=round(source_diversity, 4),
        repetition_score=round(repetition, 4),
        issues=issues,
    )


def run_section_revision_loop(
    output_dir: str | Path,
    section_id: str,
    *,
    finalize: bool = True,
    max_rounds: int = 3,
    start_round_index: int = 0,
    min_chars: int = 1200,
    writer_backend: str = "deterministic",
    writer_command: str = "",
    writer_timeout: int = 120,
    pane_target: str = "",
    pane_send: bool = False,
    emit_prompt_packet: bool = True,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    section_dir = root / "sections" / section_id
    spec = _read_json(section_dir / "section.spec.json")
    pack = _read_json(section_dir / "evidence_pack.json")
    section_dir.mkdir(parents=True, exist_ok=True)
    if not spec:
        return {"ok": False, "section_id": section_id, "reason": "section_spec_missing"}
    if not pack:
        return {"ok": False, "section_id": section_id, "reason": "evidence_pack_missing"}
    if pack.get("status") != "ready":
        review = SectionReview(
            section_id=section_id,
            verdict="BLOCKED",
            unsupported_claim_rate=1.0,
            citation_span_accuracy=0.0,
            source_diversity_score=0.0,
            repetition_score=0.0,
            issues=list(pack.get("blockers") or ["evidence_pack_blocked"]),
        )
        (section_dir / "review.json").write_text(json.dumps(to_dict(review), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"ok": False, "section_id": section_id, "reason": "evidence_pack_blocked", "review": to_dict(review)}

    traces: list[dict] = []
    text = ""
    review = None
    backend = get_writer_backend(
        writer_backend,
        local_command=writer_command,
        timeout_seconds=writer_timeout,
        pane_target=pane_target,
        pane_send=pane_send,
    )
    start_round = max(int(start_round_index or 0), 0)
    for round_index in range(start_round, start_round + max(max_rounds, 1)):
        packet = build_section_prompt_packet(root, section_id, round_index=round_index, writer_backend=backend.name)
        if emit_prompt_packet:
            _write_prompt_packet(section_dir, packet)
        fallback_text = build_section_draft(root, section_id, round_index=round_index)
        try:
            text = backend.write(packet, fallback_text)
        except HumanResponseMissingError as exc:
            trace = SectionRevisionTrace(
                section_id=section_id,
                round_index=round_index,
                verdict="WAITING_FOR_HUMAN",
                changed=False,
                issues_before=[str(exc)],
                actions=["fill_human_response_markdown", "rerun_survey_write_section"],
            )
            traces.append(to_dict(trace))
            review = SectionReview(
                section_id=section_id,
                verdict="WAITING_FOR_HUMAN",
                unsupported_claim_rate=1.0,
                citation_span_accuracy=0.0,
                source_diversity_score=0.0,
                repetition_score=0.0,
                issues=[str(exc)],
            )
            (section_dir / "review.json").write_text(json.dumps(to_dict(review), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (section_dir / "revision_trace.json").write_text(json.dumps({"section_id": section_id, "rounds": traces}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return {
                "ok": False,
                "section_id": section_id,
                "reason": "human_response_missing",
                "writer_backend": backend.name,
                "prompt_packets": str(section_dir / "prompt_packets") if emit_prompt_packet else "",
                "expected_response": exc.response_path,
                "review": to_dict(review),
            }
        except LocalCommandWriterError as exc:
            trace = SectionRevisionTrace(
                section_id=section_id,
                round_index=round_index,
                verdict="WRITER_FAILED",
                changed=False,
                issues_before=[str(exc)],
                actions=["fix_writer_command", "rerun_survey_write_section"],
            )
            traces.append(to_dict(trace))
            review = SectionReview(
                section_id=section_id,
                verdict="WRITER_FAILED",
                unsupported_claim_rate=1.0,
                citation_span_accuracy=0.0,
                source_diversity_score=0.0,
                repetition_score=0.0,
                issues=[str(exc)],
            )
            (section_dir / "review.json").write_text(json.dumps(to_dict(review), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (section_dir / "revision_trace.json").write_text(json.dumps({"section_id": section_id, "rounds": traces}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return {
                "ok": False,
                "section_id": section_id,
                "reason": "writer_failed",
                "writer_backend": backend.name,
                "prompt_packets": str(section_dir / "prompt_packets") if emit_prompt_packet else "",
                "writer_error": exc.reason,
                "review": to_dict(review),
            }
        except PanePacketPendingError as exc:
            trace = SectionRevisionTrace(
                section_id=section_id,
                round_index=round_index,
                verdict="WAITING_FOR_PANE",
                changed=False,
                issues_before=[str(exc)],
                actions=["let_pane_write_response_markdown", "rerun_survey_write_section"],
            )
            traces.append(to_dict(trace))
            review = SectionReview(
                section_id=section_id,
                verdict="WAITING_FOR_PANE",
                unsupported_claim_rate=1.0,
                citation_span_accuracy=0.0,
                source_diversity_score=0.0,
                repetition_score=0.0,
                issues=[str(exc)],
            )
            (section_dir / "review.json").write_text(json.dumps(to_dict(review), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (section_dir / "revision_trace.json").write_text(json.dumps({"section_id": section_id, "rounds": traces}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return {
                "ok": False,
                "section_id": section_id,
                "reason": "pane_response_missing",
                "writer_backend": backend.name,
                "prompt_packets": str(section_dir / "prompt_packets") if emit_prompt_packet else "",
                "pane_dispatch": exc.dispatch_path,
                "expected_response": exc.response_path,
                "pane_target": exc.pane_target,
                "pane_submitted": exc.submitted,
                "review": to_dict(review),
            }
        review = review_section_text(root, section_id, text, min_chars=min_chars)
        traces.append(to_dict(SectionRevisionTrace(
            section_id=section_id,
            round_index=round_index,
            verdict=review.verdict,
            changed=round_index > start_round,
            issues_before=list(review.issues),
            actions=[] if review.verdict == "PASS" else ["expand_structure", "bind_missing_citations", "add_evaluation_or_contradiction"],
        )))
        if review.verdict == "PASS":
            break

    assert review is not None
    (section_dir / "draft.md").write_text(text, encoding="utf-8")
    (section_dir / "review.json").write_text(json.dumps(to_dict(review), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (section_dir / "revision_trace.json").write_text(json.dumps({"section_id": section_id, "rounds": traces}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if review.verdict == "PASS" and finalize:
        final = text + "\n## Section Review\n\nVerdict: PASS\n"
        (section_dir / "final.md").write_text(final, encoding="utf-8")
    return {
        "ok": review.verdict == "PASS",
        "section_id": section_id,
        "finalized": bool(finalize and review.verdict == "PASS"),
        "rounds": len(traces),
        "writer_backend": backend.name,
        "prompt_packets": str(section_dir / "prompt_packets") if emit_prompt_packet else "",
        "review": to_dict(review),
    }


def run_ready_sections(
    output_dir: str | Path,
    *,
    limit: int = 3,
    max_rounds: int = 3,
    min_chars: int = 1200,
    writer_backend: str = "deterministic",
    writer_command: str = "",
    writer_timeout: int = 120,
    pane_target: str = "",
    pane_send: bool = False,
    emit_prompt_packet: bool = True,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    packs = _read_json(root / "survey_evidence_packs.json")
    results: list[dict] = []
    unlimited = limit <= 0
    for pack in packs.get("packs", []):
        if pack.get("status") != "ready":
            continue
        section_id = str(pack.get("section_id") or "")
        if not section_id:
            continue
        final = root / "sections" / section_id / "final.md"
        if final.exists():
            continue
        results.append(run_section_revision_loop(
            root,
            section_id,
            max_rounds=max_rounds,
            min_chars=min_chars,
            writer_backend=writer_backend,
            writer_command=writer_command,
            writer_timeout=writer_timeout,
            pane_target=pane_target,
            pane_send=pane_send,
            emit_prompt_packet=emit_prompt_packet,
        ))
        if not unlimited and len(results) >= limit:
            break
    return {
        "ok": all(item.get("ok") for item in results) if results else False,
        "processed": len(results),
        "passed": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "results": results,
    }


def watch_pane_responses(
    output_dir: str | Path,
    *,
    limit: int = 0,
    min_chars: int = 1200,
    round_index: int = 0,
) -> dict[str, Any]:
    """Finalize sections whose pane/human response artifact already exists."""
    root = Path(output_dir).expanduser()
    ast = _read_json(root / "survey_report_ast.json")
    sections = ast.get("sections", []) if isinstance(ast.get("sections"), list) else []
    results: list[dict] = []
    pending: list[str] = []
    skipped_final: list[str] = []
    unlimited = limit <= 0
    for section in sections:
        section_id = str(section.get("section_id") or "")
        if not section_id:
            continue
        section_dir = root / "sections" / section_id
        final = section_dir / "final.md"
        response = section_dir / "human_responses" / f"round_{round_index:02d}.md"
        if final.exists():
            skipped_final.append(section_id)
            continue
        if not response.exists() or not response.read_text(encoding="utf-8").strip():
            pending.append(section_id)
            continue
        results.append(run_section_revision_loop(
            root,
            section_id,
            max_rounds=1,
            min_chars=min_chars,
            writer_backend="human-packet",
            emit_prompt_packet=True,
        ))
        if not unlimited and len(results) >= limit:
            break
    payload = {
        "ok": all(item.get("ok") for item in results) if results else False,
        "processed": len(results),
        "passed": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "pending_responses": len(pending),
        "skipped_final": len(skipped_final),
        "results": results,
        "pending_section_ids": pending[:20],
    }
    (root / "pane_response_watch.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
