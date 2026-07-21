"""Reasoning and resonance routing for HF Paper Insight runtime."""
from __future__ import annotations

import json
from dataclasses import dataclass

from schema import PaperEvidencePacket, ResonanceLevel


def _load_packet_json(packet: PaperEvidencePacket, field_name: str) -> dict:
    raw = getattr(packet, field_name, "{}") or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    return []


@dataclass
class ResonanceMatcher:
    """Derives resonance payload from a validated evidence packet."""

    report_threshold: float = 0.35
    project_threshold: float = 0.45
    deep_research_threshold: float = 0.50

    def match_resonance(self, packet: PaperEvidencePacket) -> dict:
        canonical = _load_packet_json(packet, "canonical_summary_json")
        taxonomy = _load_packet_json(packet, "taxonomy_summary_json")
        scores = _load_packet_json(packet, "score_summary_json")
        gate = _load_packet_json(packet, "packet_gate_json")

        candidates: list[str] = []
        if float(scores.get("insight_report", 0.0)) >= self.report_threshold:
            candidates.append("report")
        if float(scores.get("attention", 0.0)) >= 0.20 or float(scores.get("research_signal", 0.0)) >= 0.25:
            candidates.append("cards")
        if float(scores.get("novelty", 0.0)) >= 0.45:
            candidates.append("seeds")
            candidates.append("topics")
        if float(scores.get("experiment", 0.0)) >= 0.35:
            candidates.append("experiments")
        if float(scores.get("open_project", 0.0)) >= self.project_threshold:
            candidates.append("projects")
        if float(scores.get("deep_research_seed", 0.0)) >= self.deep_research_threshold:
            candidates.append("deep_research")

        if not candidates:
            candidates.append("cards")

        max_score = max(
            float(scores.get("research_signal", 0.0)),
            float(scores.get("insight_report", 0.0)),
            float(scores.get("experiment", 0.0)),
            float(scores.get("open_project", 0.0)),
            float(scores.get("deep_research_seed", 0.0)),
        )
        resonance_level = self.classify_resonance_level(
            {
                "max_score": max_score,
                "candidate_assets": candidates,
                "packet_gate_passed": bool(gate.get("passed")),
            }
        )

        title = str(canonical.get("title") or "").strip()
        labels = [str(x) for x in _as_list(taxonomy.get("labels")) if str(x).strip()]
        reasons = [
            f"max_score={max_score:.3f}",
            f"stack_layer={taxonomy.get('stack_layer', 'unknown')}",
            f"research_route={taxonomy.get('research_route', 'unknown')}",
        ]
        if title:
            reasons.insert(0, f"title={title}")
        if labels:
            reasons.append("labels=" + ",".join(labels[:6]))

        return {
            "paper_id": packet.paper_id,
            "title": title,
            "candidate_assets": list(dict.fromkeys(candidates)),
            "max_score": round(max_score, 3),
            "packet_gate_passed": bool(gate.get("passed")),
            "resonance_level": resonance_level,
            "priority": "high" if resonance_level in {ResonanceLevel.R4.value, ResonanceLevel.R5.value} else "normal",
            "reasons": reasons,
        }

    def classify_resonance_level(self, resonance_payload: dict) -> str:
        if not resonance_payload.get("packet_gate_passed", False):
            return ResonanceLevel.R0.value
        max_score = float(resonance_payload.get("max_score", 0.0))
        if max_score >= 0.90:
            return ResonanceLevel.R5.value
        if max_score >= 0.75:
            return ResonanceLevel.R4.value
        if max_score >= 0.55:
            return ResonanceLevel.R3.value
        if max_score >= 0.35:
            return ResonanceLevel.R2.value
        if max_score >= 0.15:
            return ResonanceLevel.R1.value
        return ResonanceLevel.R0.value


class HighReasoningEngine:
    """Builds a local fallback reasoning contract.

    Real L7 premium insight is routed by tech_hotspot_radar.py through the
    Browser Agent. This fallback must never label itself as browser_agent.
    """

    def call_high_model(self, packet: PaperEvidencePacket, mode: str = "browser_agent") -> dict:
        canonical = _load_packet_json(packet, "canonical_summary_json")
        taxonomy = _load_packet_json(packet, "taxonomy_summary_json")
        scores = _load_packet_json(packet, "score_summary_json")
        gate = _load_packet_json(packet, "packet_gate_json")
        passed = bool(gate.get("passed"))

        effective_mode = "fallback_report"
        title = str(canonical.get("title") or packet.paper_id)
        top_dimensions = sorted(
            [
                ("research_signal", float(scores.get("research_signal", 0.0))),
                ("insight_report", float(scores.get("insight_report", 0.0))),
                ("experiment", float(scores.get("experiment", 0.0))),
                ("open_project", float(scores.get("open_project", 0.0))),
                ("deep_research_seed", float(scores.get("deep_research_seed", 0.0))),
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        hypotheses = [
            f"{title} 在 {taxonomy.get('stack_layer', 'model')} 层具备 {top_dimensions[0][0]} 潜力",
            f"研究路线 {taxonomy.get('research_route', 'applied_research')} 适合输出 {taxonomy.get('domain', 'general')} 技术洞察",
        ]
        strategic_questions = [
            "哪些可复现实验最值得先落地？",
            "它与现有技术栈或开源生态的耦合点是什么？",
        ]
        if top_dimensions[0][0] == "deep_research_seed":
            strategic_questions.append("是否值得触发更深的 Browser Agent 路由和后续监控？")

        return {
            "accepted": passed,
            "reasoning_mode": effective_mode,
            "requested_reasoning_mode": mode,
            "premium_insight_available": False,
            "routing_contract": {
                "actor_type": "batch_reasoning",
                "requires_browser": False,
                "requested_actor_type": "browser_agent" if mode == "browser_agent" else mode,
                "packet_id": packet.packet_id,
                "paper_id": packet.paper_id,
            },
            "summary": f"{title} 当前适合进入 AI Influence 论文观察池，重点关注 {top_dimensions[0][0]} 与 {taxonomy.get('stack_layer', 'model')} 价值。",
            "hypotheses": hypotheses,
            "strategic_questions": strategic_questions,
            "top_dimensions": [{"name": name, "score": round(score, 3)} for name, score in top_dimensions[:3]],
            "gate_reasons": _as_list(gate.get("reasons")),
        }

    def insight_gate_check(self, reasoning_output: dict) -> dict:
        checks = {
            "accepted": bool(reasoning_output.get("accepted")),
            "has_summary": bool(str(reasoning_output.get("summary") or "").strip()),
            "has_hypotheses": len(_as_list(reasoning_output.get("hypotheses"))) >= 1,
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "reasons": [name for name, ok in checks.items() if not ok],
        }

    def resonance_gate_check(self, resonance_payload: dict) -> dict:
        checks = {
            "packet_gate_passed": bool(resonance_payload.get("packet_gate_passed")),
            "has_candidate_assets": len(_as_list(resonance_payload.get("candidate_assets"))) >= 1,
            "resonance_level_nonzero": str(resonance_payload.get("resonance_level") or "") != ResonanceLevel.R0.value,
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "reasons": [name for name, ok in checks.items() if not ok],
        }

    def compile_research_judgment(
        self,
        packet: PaperEvidencePacket,
        reasoning_output: dict,
        resonance_payload: dict,
    ) -> dict:
        canonical = _load_packet_json(packet, "canonical_summary_json")
        taxonomy = _load_packet_json(packet, "taxonomy_summary_json")
        return {
            "paper_id": packet.paper_id,
            "title": canonical.get("title", ""),
            "judgment": reasoning_output.get("summary", ""),
            "domain": taxonomy.get("domain", "other"),
            "stack_layer": taxonomy.get("stack_layer", "model"),
            "research_route": taxonomy.get("research_route", "applied_research"),
            "resonance_level": resonance_payload.get("resonance_level", ResonanceLevel.R0.value),
            "candidate_assets": resonance_payload.get("candidate_assets", []),
            "reasoning_mode": reasoning_output.get("reasoning_mode", "fallback"),
        }
