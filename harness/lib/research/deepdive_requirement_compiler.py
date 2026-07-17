"""DeepDive-local requirement compiler.

This module intentionally does not import the PM requirement compiler.  It
copies a small set of concepts under DeepDive-specific names so long-horizon
research planning can benefit from requirement contracts without sharing route
state with normal PM / PRD work.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from .profiles import (
        DEFAULT_PROFILE as DEFAULT_INSIGHT_PROFILE,
        load_profile,
        profile_contract_to_scope_boundaries,
        validate_profile,
    )
except ImportError:  # pragma: no cover - supports direct script-style imports.
    DEFAULT_INSIGHT_PROFILE = "cais-agent-insight"
    load_profile = None  # type: ignore[assignment]
    validate_profile = None  # type: ignore[assignment]
    profile_contract_to_scope_boundaries = None  # type: ignore[assignment]


SCHEMA_VERSION = "solar.deepdive.requirement_contract.v1"
TRACE_SCHEMA_VERSION = "solar.deepdive.traceability.v1"

EXPLICIT_DEEPDIVE_PROFILES = {
    "deepdive",
    "deepdive_research",
    "deepresearch",
    "deep_research",
}

GENERIC_DEEPDIVE_PROFILES = EXPLICIT_DEEPDIVE_PROFILES | {"insight", "deepdive-insight", "deepdive_insight"}

INSIGHT_STATE_EVENTS: list[dict[str, str]] = [
    {"event": "profile_loaded", "required_metadata": "profile_id, mode, strict defaults, required outputs", "recovery": "fail_closed_if_required_fields_missing"},
    {"event": "runtime_dag_ready", "required_metadata": "D10-D18 node list, artifact paths, gates, sidecars", "recovery": "rebuild_from_compiler_metadata"},
    {"event": "signal_pack_ready", "required_metadata": "signal artifact paths, CAIS coverage gate result", "recovery": "block_D12_when_required_signals_missing"},
    {"event": "absorption_ready", "required_metadata": "map/roadmap paths, actionability gate result", "recovery": "block_D15_D18_when_thresholds_fail"},
    {"event": "claims_predictions_ready", "required_metadata": "typed claim and prediction paths", "recovery": "block_publisher_when_citation_prediction_gates_fail"},
    {"event": "cards_figures_ready", "required_metadata": "card/figure paths, gate results", "recovery": "block_HTML_if_cards_or_six_MVP_figures_missing"},
    {"event": "chief_insight_reviewed", "required_metadata": "review sidecar, template/user-question gates", "recovery": "rerun_or_fail_no_silent_publish"},
    {"event": "published_core_ready", "required_metadata": "publisher interface artifacts, audit readiness", "recovery": "S04_S05_must_finish_visual_release_validation"},
]

INSIGHT_RUNTIME_NODE_METADATA: dict[str, dict[str, Any]] = {
    "D10": {
        "artifact_paths": ["insight_thesis_plan.json"],
        "gates": ["GenericSurveyTOCGate", "UserQuestionFitnessGate"],
        "evaluator_sidecar": "insight_thesis_eval.json",
        "closeout_acceptance": "Thesis plan answers user questions; generic survey TOC absent.",
        "status_metadata": {"state": "insight_plan_ready", "reconstruct_from": "runtime_dag metadata or event records"},
    },
    "D11": {
        "artifact_paths": ["conference_signal_map.json", "cais_paper_signal_packs.jsonl"],
        "gates": ["CAISCoverageGate"],
        "evaluator_sidecar": "signal_coverage_eval.json",
        "closeout_acceptance": "Signal map binds named evidence to implications.",
        "status_metadata": {"state": "signal_pack_ready", "reconstruct_from": "signal artifact paths and CAIS coverage gate result"},
    },
    "D12": {
        "artifact_paths": ["paper_to_solar_absorption_map.json", "solar_operator_roadmap.json"],
        "gates": ["SolarActionabilityGate"],
        "evaluator_sidecar": "action_eval.json",
        "closeout_acceptance": "Every major signal has actionable implication or explicit watchlist reason.",
        "status_metadata": {"state": "absorption_ready", "reconstruct_from": "map/roadmap paths and actionability gate result"},
    },
    "D13": {
        "artifact_paths": ["typed_claims.jsonl", "claim_evidence_map.json"],
        "gates": ["CitationVisibilityGate"],
        "evaluator_sidecar": "claim_eval.json",
        "closeout_acceptance": "Claims are typed and evidence-bound.",
        "status_metadata": {"state": "claims_ready", "reconstruct_from": "typed claim and evidence paths"},
    },
    "D14": {
        "artifact_paths": ["prediction_packets.jsonl"],
        "gates": ["PredictionPacketGate"],
        "evaluator_sidecar": "prediction_eval.json",
        "closeout_acceptance": "Prediction packets are explicit and falsifiable.",
        "status_metadata": {"state": "predictions_ready", "reconstruct_from": "prediction artifact paths and gate results"},
    },
    "D15": {
        "artifact_paths": ["section_render_cards/*.json"],
        "gates": ["MachineLabelLeakGate", "CitationVisibilityGate"],
        "evaluator_sidecar": "section_render_eval.json",
        "closeout_acceptance": "SectionRender cards complete for every major chapter.",
        "status_metadata": {"state": "cards_ready", "reconstruct_from": "card paths and gate results"},
    },
    "D16": {
        "artifact_paths": ["figure_specs/*.json", "assets/figures/*.svg"],
        "gates": ["FigureRequiredGate"],
        "evaluator_sidecar": "figure_eval.json",
        "closeout_acceptance": "Every major chapter has a claim-linked figure.",
        "status_metadata": {"state": "figures_ready", "reconstruct_from": "figure spec paths and MVP gate results"},
    },
    "D17": {
        "artifact_paths": ["chief_insight_review.json", "final_machine.md"],
        "gates": ["TemplateRepetitionGate", "UserQuestionFitnessGate"],
        "evaluator_sidecar": "chief_insight_eval.json",
        "closeout_acceptance": "Chief insight review passes all insight gates.",
        "status_metadata": {"state": "chief_insight_reviewed", "reconstruct_from": "review sidecar and template/user-question gate results"},
    },
    "D18": {
        "artifact_paths": ["final.html", "assets/style.css", "visual_audit.json", "appendix_evidence_matrix.html"],
        "gates": ["MachineLabelLeakGate", "CitationVisibilityGate", "VisualAuditGate"],
        "evaluator_sidecar": "publish_eval.json",
        "closeout_acceptance": "Insight artifact package is complete and status-visible.",
        "status_metadata": {"state": "published_core_ready", "reconstruct_from": "publisher interface artifacts and audit readiness"},
    },
}


OPERATOR_MAPPING: list[dict[str, str]] = [
    {
        "pm_concept": "RawIntent capture",
        "deepdive_operator": "DeepDiveBriefCapture",
        "copy_policy": "copy_concept_rename",
        "boundary": "DeepDive-owned input contract; never writes raw_intent.json.",
    },
    {
        "pm_concept": "Requirement IR",
        "deepdive_operator": "DeepDiveResearchContract",
        "copy_policy": "copy_schema_shape_rename",
        "boundary": "Uses solar.deepdive.requirement_contract.v1, not solar.requirement_ir.v1.",
    },
    {
        "pm_concept": "Requirement item mapping",
        "deepdive_operator": "DeepDiveQuestionMapping",
        "copy_policy": "copy_algorithm_rename",
        "boundary": "Maps research questions to D* nodes only.",
    },
    {
        "pm_concept": "Research DAG skeleton",
        "deepdive_operator": "DeepDiveEvidenceDAG",
        "copy_policy": "copy_pattern_specialize",
        "boundary": "Uses dag_variant=deepdive_research; never returns standard/research PM DAG.",
    },
    {
        "pm_concept": "Coverage report",
        "deepdive_operator": "DeepDiveTraceabilityReport",
        "copy_policy": "copy_contract_rename",
        "boundary": "Checks research questions, evidence needs, claims, chapters, and verifier gates.",
    },
    {
        "pm_concept": "Acceptance verdict",
        "deepdive_operator": "DeepDiveCloseoutDecision",
        "copy_policy": "copy_gate_rename",
        "boundary": "Publishes DeepDive closeout only; does not affect PM sprint acceptance.",
    },
]


@dataclass(frozen=True)
class DeepDiveSourceRef:
    kind: str
    uri: str
    title: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "uri": self.uri,
            "title": self.title,
            "note": self.note,
        }


@dataclass(frozen=True)
class DeepDiveQuestion:
    id: str
    text: str
    evidence_need: str
    priority: str = "P1"

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "text": self.text,
            "evidence_need": self.evidence_need,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class DeepDiveCompileOptions:
    target_chars: int = 50000
    profile: str = "deepdive"
    source_channel: str = "deepdive"
    source_refs: list[DeepDiveSourceRef] = field(default_factory=list)


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def is_explicit_deepdive_request(
    text: str,
    *,
    profile: str | None = None,
    source_channel: str | None = None,
) -> bool:
    """Return true only for explicit DeepDive entrypoints.

    Generic words like "research", "调研", "论文", or "研究" are deliberately
    insufficient.  This prevents normal requirement analysis from entering the
    DeepDive compiler by accident.
    """

    candidates = {
        normalize_text(profile or "").lower(),
        normalize_text(source_channel or "").lower(),
    }
    if candidates & EXPLICIT_DEEPDIVE_PROFILES:
        return True
    normalized = normalize_text(text)
    lowered = normalized.lower()
    explicit_markers = (
        "deepdive",
        "deep dive",
        "deepresearch",
        "deep research",
        "深度研究",
        "深研",
        "深度调研报告",
    )
    return any(marker in lowered for marker in explicit_markers) or any(
        marker in normalized for marker in explicit_markers
    )


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def infer_insight_profile_id(brief: str, *, requested_profile: str | None = None) -> str | None:
    """Resolve an insight profile without forcing generic DeepDive into CAIS defaults."""

    requested = normalize_text(requested_profile or "").lower().replace("_", "-")
    if requested and requested not in {profile.replace("_", "-") for profile in GENERIC_DEEPDIVE_PROFILES}:
        return requested
    lowered = normalize_text(brief).lower()
    if "cais" in lowered and "solar" in lowered:
        return DEFAULT_INSIGHT_PROFILE
    return None


def load_insight_profile_contract(profile_id: str | None) -> dict[str, Any]:
    """Load and validate an optional profile contract for insight mode."""

    if not profile_id:
        return {"active": False, "profile_id": "", "loaded": False, "ok": False, "errors": []}
    if load_profile is None or validate_profile is None or profile_contract_to_scope_boundaries is None:
        return {
            "active": True,
            "profile_id": profile_id,
            "loaded": False,
            "ok": False,
            "errors": ["profile_loader_unavailable"],
        }
    try:
        profile = load_profile(profile_id)
        validated = validate_profile(profile)
    except Exception as exc:  # noqa: BLE001 - profile load errors must be reflected in contract.
        return {
            "active": True,
            "profile_id": profile_id,
            "loaded": False,
            "ok": False,
            "errors": [f"profile_load_failed:{type(exc).__name__}:{exc}"],
        }
    scope = profile_contract_to_scope_boundaries(validated)
    return {
        "active": True,
        "profile_id": profile_id,
        "loaded": True,
        "ok": bool(validated.get("ok")),
        "errors": list(validated.get("errors") or []),
        "required_outputs": list(validated.get("required_outputs") or []),
        "required_signal_clusters": list(validated.get("required_signal_clusters") or []),
        "required_gates": list(validated.get("required_gates") or []),
        "strict_defaults": dict(validated.get("strict_defaults") or {}),
        "scope_boundaries": scope,
    }


def extract_research_questions(brief: str) -> list[DeepDiveQuestion]:
    normalized = normalize_text(brief)
    raw_lines = [line.strip(" -\t") for line in str(brief or "").splitlines() if line.strip()]
    question_lines = [
        line
        for line in raw_lines
        if line.endswith("?")
        or line.endswith("？")
        or re.match(r"^(why|how|what|when|where|是否|为什么|如何|哪些|什么)", line, re.I)
    ]
    if not question_lines and normalized:
        question_lines = [normalized[:240]]

    questions: list[DeepDiveQuestion] = []
    for index, text in enumerate(question_lines[:12], start=1):
        questions.append(
            DeepDiveQuestion(
                id=f"DQ-{index:03d}",
                text=normalize_text(text),
                evidence_need="primary sources, contrary evidence, claim-level citations",
                priority="P0" if index <= 3 else "P1",
            )
        )
    return questions


_INSIGHT_NODE_BASE: dict[str, dict[str, Any]] = {
    "D10": {
        "gate": "DD_INSIGHT",
        "logical_operator": "DeepDiveInsightThesisPlanner",
        "goal": "Build central thesis, chapter theses, and argument load-bearing map.",
        "depends_on": ["D4", "D5"],
        "acceptance": ["Insight thesis map answers the user questions instead of a generic survey outline."],
    },
    "D11": {
        "gate": "DD_INSIGHT",
        "logical_operator": "DeepDiveSignalExtractor",
        "goal": "Extract topic-specific signals, source clusters, and evidence patterns into reusable insight assets.",
        "depends_on": ["D3"],
        "acceptance": ["Signal map binds named evidence to concrete technical, product, or strategic implications."],
    },
    "D12": {
        "gate": "DD_INSIGHT",
        "logical_operator": "DeepDiveActionMapper",
        "goal": "Map signals to actions, design implications, experiments, roadmap items, or domain-specific absorption paths.",
        "depends_on": ["D11"],
        "acceptance": ["Every major signal has an actionable implication or an explicit reason it remains watchlist-only."],
    },
    "D13": {
        "gate": "DD_INSIGHT",
        "logical_operator": "DeepDiveTypedClaimCompiler",
        "goal": "Classify factual, interpretive, predictive, and strategic claims.",
        "depends_on": ["D10", "D11", "D12"],
        "acceptance": ["Claims are typed and evidence-bound."],
    },
    "D14": {
        "gate": "DD_INSIGHT",
        "logical_operator": "DeepDivePredictionPacketBuilder",
        "goal": "Build forecast packets with drivers, leading indicators, and falsification conditions.",
        "depends_on": ["D13"],
        "acceptance": ["Prediction packets are explicit and falsifiable."],
    },
    "D15": {
        "gate": "DD_PUBLISH",
        "logical_operator": "DeepDiveSectionRenderCompiler",
        "goal": "Compile sections into render cards with body, evidence callouts, takeaways, and figure specs.",
        "depends_on": ["D13", "D14"],
        "acceptance": ["SectionRender cards are complete for every major chapter."],
    },
    "D16": {
        "gate": "DD_PUBLISH",
        "logical_operator": "DeepDiveFigureSpecRenderer",
        "goal": "Render claim-linked diagrams, roadmaps, matrices, and architecture figures.",
        "depends_on": ["D15"],
        "acceptance": ["Every major chapter has a claim-linked figure."],
    },
    "D17": {
        "gate": "DD_REVIEW",
        "logical_operator": "DeepDiveChiefInsightEditor",
        "goal": "Reject correct-but-useless prose and enforce thesis, actionability, forecast, and human-readable evidence.",
        "depends_on": ["D15", "D16"],
        "acceptance": ["Chief insight review passes all insight gates."],
    },
    "D18": {
        "gate": "DD_PUBLISH",
        "logical_operator": "DeepDiveInsightArtifactPublisher",
        "goal": "Publish final HTML, figures, signal map, action map, and insight roadmap.",
        "depends_on": ["D17"],
        "acceptance": ["Insight artifact package is complete and status-visible."],
    },
}


def build_deepdive_evidence_dag(questions: list[DeepDiveQuestion], *, insight_mode: bool = False) -> dict[str, Any]:
    question_ids = [question.id for question in questions]
    nodes = [
        {
            "id": "D1",
            "gate": "DD_SCOPE",
            "logical_operator": "DeepDiveBriefCapture",
            "goal": "Freeze the DeepDive scope, questions, boundaries, and output contract.",
            "depends_on": [],
            "question_ids": question_ids,
            "acceptance": ["DeepDive scope contract is explicit and bounded."],
        },
        {
            "id": "D2",
            "gate": "DD_SOURCE",
            "logical_operator": "DeepDiveSourcePlanner",
            "goal": "Plan source acquisition across primary, secondary, code, benchmark, and dissenting evidence.",
            "depends_on": ["D1"],
            "question_ids": question_ids,
            "acceptance": ["Source matrix covers every research question."],
        },
        {
            "id": "D3",
            "gate": "DD_SOURCE",
            "logical_operator": "DeepDiveSourceCollector",
            "goal": "Collect sources and write an auditable source manifest.",
            "depends_on": ["D2"],
            "question_ids": question_ids,
            "acceptance": ["Source manifest and fetch status are recorded."],
        },
        {
            "id": "D4",
            "gate": "DD_EVIDENCE",
            "logical_operator": "DeepDiveClaimCompiler",
            "goal": "Compile claims, evidence atoms, methods, limitations, and confidence.",
            "depends_on": ["D3"],
            "question_ids": question_ids,
            "acceptance": ["Claim ledger binds claims to source evidence."],
        },
        {
            "id": "D5",
            "gate": "DD_EVIDENCE",
            "logical_operator": "DeepDiveContradictionScanner",
            "goal": "Find contradictions, weak evidence, missing sources, and overclaim risks.",
            "depends_on": ["D4"],
            "question_ids": question_ids,
            "acceptance": ["Contradiction and evidence-gap matrix is produced."],
        },
        {
            "id": "D6",
            "gate": "DD_SYNTHESIS",
            "logical_operator": "DeepDiveChapterPlanner",
            "goal": "Compile chapter jobs and per-chapter evidence requirements.",
            "depends_on": ["D4", "D5"],
            "question_ids": question_ids,
            "acceptance": ["Each chapter maps to questions and evidence requirements."],
        },
        {
            "id": "D7",
            "gate": "DD_SYNTHESIS",
            "logical_operator": "DeepDiveChiefEditor",
            "goal": "Synthesize the final DeepDive report from verified chapter outputs.",
            "depends_on": ["D6"],
            "question_ids": question_ids,
            "acceptance": ["Final report draft answers each research question with evidence."],
        },
        {
            "id": "D8",
            "gate": "DD_REVIEW",
            "logical_operator": "DeepDiveClaimVerifier",
            "goal": "Verify claim grounding, contradiction handling, and publication readiness.",
            "depends_on": ["D7"],
            "question_ids": question_ids,
            "acceptance": ["Verifier decision and repair requirements are recorded."],
        },
        {
            "id": "D9",
            "gate": "DD_PUBLISH",
            "logical_operator": "DeepDiveArtifactPublisher",
            "goal": "Publish final report, evidence map, traceability report, and closeout decision.",
            "depends_on": ["D8"],
            "question_ids": question_ids,
            "acceptance": ["DeepDive artifact package is complete."],
        },
    ]
    if insight_mode:
        for node_id in ("D10", "D11", "D12", "D13", "D14", "D15", "D16", "D17", "D18"):
            base = _INSIGHT_NODE_BASE[node_id]
            meta = INSIGHT_RUNTIME_NODE_METADATA[node_id]
            nodes.append({
                "id": node_id,
                "gate": base["gate"],
                "logical_operator": base["logical_operator"],
                "goal": base["goal"],
                "depends_on": base["depends_on"],
                "question_ids": question_ids,
                "acceptance": base["acceptance"],
                "artifact_paths": meta["artifact_paths"],
                "gates": list(meta["gates"]),
                "verification_gates": list(meta["gates"]),
                "evaluator_sidecar": meta["evaluator_sidecar"],
                "closeout_acceptance": meta["closeout_acceptance"],
                "status_metadata": meta["status_metadata"],
            })
    required_gates = [
        "DD_SCOPE",
        "DD_SOURCE",
        "DD_EVIDENCE",
        "DD_SYNTHESIS",
        "DD_REVIEW",
        "DD_PUBLISH",
    ]
    if insight_mode:
        required_gates.insert(4, "DD_INSIGHT")
    return {
        "dag_variant": "deepdive_research",
        "runtime_owner": "DeepDive",
        "required_gates": required_gates,
        "evidence_policy": {
            "ledger_required": True,
            "claim_citation_required": True,
            "counter_evidence_required": True,
            "unsupported_claim_guard": True,
            "normal_requirement_pipeline_import_allowed": False,
        },
        "nodes": nodes,
    }


def build_traceability(contract: dict[str, Any]) -> dict[str, Any]:
    graph = contract["deepdive_dag"]
    nodes = graph["nodes"]
    items: list[dict[str, Any]] = []
    for question in contract["research_questions"]:
        mapped_nodes = [
            node["id"]
            for node in nodes
            if question["id"] in (node.get("question_ids") or [])
        ]
        items.append(
            {
                "question_id": question["id"],
                "mapped_nodes": mapped_nodes,
                "expected_artifacts": [
                    "source_manifest.json",
                    "claim_ledger.jsonl",
                    "contradiction_matrix.json",
                    "chapter_jobs.json",
                    "final_report.md",
                    "deepdive_closeout.json",
                ],
            }
        )
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "contract_id": contract["id"],
        "items": items,
    }


def compile_deepdive_brief(
    brief: str,
    *,
    options: DeepDiveCompileOptions | None = None,
    expansion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or DeepDiveCompileOptions()
    raw_normalized = normalize_text(brief)
    expanded_brief = ""
    if expansion and isinstance(expansion, dict):
        expanded_brief = normalize_text(str(expansion.get("expanded_brief") or ""))
    normalized = expanded_brief or raw_normalized
    if not normalized:
        raise ValueError("brief is required")

    lowered = normalized.lower()
    insight_mode = (
        str(options.profile or "").lower() in EXPLICIT_DEEPDIVE_PROFILES
        or "insight" in str(options.profile or "").lower()
        or str(options.source_channel or "").lower() in EXPLICIT_DEEPDIVE_PROFILES
        or "insight" in lowered
        or "洞察" in normalized
        or ("cais" in lowered and "solar" in lowered)
        or ("会议" in normalized and "洞察" in normalized)
    )
    conference_profile = any(token in lowered for token in ("conference", "会议", "学术会议", "workshop", "accepted papers"))
    solar_profile = "solar" in lowered
    insight_profile_id = infer_insight_profile_id(normalized, requested_profile=options.profile) if insight_mode else None
    insight_profile_contract = load_insight_profile_contract(insight_profile_id) if insight_mode else {"active": False}
    questions = extract_research_questions(normalized)
    source_refs = [ref.to_dict() for ref in options.source_refs]
    must_answer = [question.text for question in questions]
    if insight_mode:
        must_answer.extend([
            "What is the central thesis of this DeepDive?",
            "Which concrete signals and evidence support, weaken, or complicate the thesis?",
            "What are the key technical, product, strategic, or ecosystem implications?",
            "What actions, designs, experiments, roadmap items, schemas, operators, or quality gates should follow when applicable?",
            "What should be watched next, with drivers, leading indicators, risks, and falsification conditions?",
        ])
        profile_scope = insight_profile_contract.get("scope_boundaries") if isinstance(insight_profile_contract, dict) else {}
        for item in profile_scope.get("must_answer", []) if isinstance(profile_scope, dict) else []:
            if item not in must_answer:
                must_answer.append(item)
    must_not_do = [
        "Do not dispatch normal PM requirement nodes.",
        "Do not write raw_intent.json or requirement_ir.json.",
        "Do not promote unsupported claims into final conclusions.",
    ]
    if insight_mode:
        must_not_do.extend([
            "Do not use a generic survey taxonomy as the final report structure.",
            "Do not leak source_type labels, claim_id, evidence_id, or execution metrics into the human-facing report.",
            "Do not publish without a concrete action, design, experiment, roadmap, or watchlist mapping.",
            "Do not publish without visible citations and claim-linked figures.",
            "Do not let correct-but-non-actionable prose pass the insight gate.",
        ])
        profile_scope = insight_profile_contract.get("scope_boundaries") if isinstance(insight_profile_contract, dict) else {}
        for item in profile_scope.get("must_not_do", []) if isinstance(profile_scope, dict) else []:
            if item not in must_not_do:
                must_not_do.append(item)
    contract = {
        "schema_version": SCHEMA_VERSION,
        "id": stable_id("ddc", normalized),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_owner": "DeepDive",
        "compiler": {
            "name": "DeepDiveRequirementCompiler",
            "copy_policy": "copied_selected_requirement_pipeline_concepts_with_renamed_operators",
            "normal_requirement_pipeline_import_allowed": False,
        },
        "profile": options.profile,
        "mode": "insight" if insight_mode else "survey",
        "insight_profile": insight_profile_contract if insight_mode else {"active": False},
        "source_channel": options.source_channel,
        "raw_brief": raw_normalized,
        "brief": normalized,
        "target_chars": options.target_chars,
        "research_questions": [question.to_dict() for question in questions],
        "source_refs": source_refs,
        "scope_boundaries": {
            "must_answer": must_answer,
            "must_not_do": must_not_do,
        },
        "output_contract": {
            "reports": ["final_report.md", "final_report.html"],
            "evidence": ["source_manifest.json", "claim_ledger.jsonl", "evidence_map.json"],
            "quality": ["contradiction_matrix.json", "claim_verification.json", "deepdive_closeout.json"],
        },
        "operator_mapping": OPERATOR_MAPPING,
    }
    if insight_mode:
        profile_outputs = insight_profile_contract.get("required_outputs") if isinstance(insight_profile_contract, dict) else None
        contract["output_contract"]["insight"] = list(profile_outputs or [
            "signal_map.json",
            "action_mapping.json",
            "challenge_or_implication_matrix.json",
            "prediction_packets.jsonl",
            "section_render_cards/*.json",
            "figures/*.svg",
            "survey_insight_quality.json",
            "chief_insight_review.json",
        ])
        profile_gates = insight_profile_contract.get("required_gates") if isinstance(insight_profile_contract, dict) else None
        if profile_gates:
            contract["output_contract"]["insight_gates"] = list(profile_gates)
        signal_clusters = insight_profile_contract.get("required_signal_clusters") if isinstance(insight_profile_contract, dict) else None
        if signal_clusters:
            contract["output_contract"]["signal_clusters"] = list(signal_clusters)
        profile_extensions: list[str] = []
        if conference_profile:
            profile_extensions.append("conference_signal_map.json")
        if solar_profile:
            profile_extensions.append("solar_absorption_map.json")
        if profile_extensions:
            contract["output_contract"]["profile_extensions"] = profile_extensions
    if expansion:
        contract["brief_expansion"] = {
            "schema_version": expansion.get("schema_version"),
            "operator": "DeepDiveBriefExpander",
            "status": expansion.get("status"),
            "attempted": bool(expansion.get("attempted")),
            "output_md_path": expansion.get("output_md_path", ""),
            "output_json_path": expansion.get("output_json_path", ""),
            "normal_requirement_pipeline_import_allowed": False,
        }
    contract["deepdive_dag"] = build_deepdive_evidence_dag(questions, insight_mode=insight_mode)
    contract["traceability"] = build_traceability(contract)
    return contract


def validate_deepdive_contract(contract: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_deepdive_contract_schema")
    if contract.get("runtime_owner") != "DeepDive":
        errors.append("runtime_owner_not_deepdive")
    if "requirement_ir" in contract or contract.get("schema_version") == "solar.requirement_ir.v1":
        errors.append("normal_requirement_ir_leak")
    compiler = contract.get("compiler") if isinstance(contract.get("compiler"), dict) else {}
    if compiler.get("normal_requirement_pipeline_import_allowed") is not False:
        errors.append("normal_requirement_pipeline_import_not_disabled")
    graph = contract.get("deepdive_dag") if isinstance(contract.get("deepdive_dag"), dict) else {}
    if graph.get("dag_variant") != "deepdive_research":
        errors.append("invalid_deepdive_dag_variant")
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        errors.append("deepdive_nodes_missing")
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id.startswith("D"):
            errors.append(f"non_deepdive_node_id:{node_id or 'N/A'}")
        op = str(node.get("logical_operator") or "")
        if not op.startswith("DeepDive"):
            errors.append(f"non_deepdive_operator:{op or 'N/A'}")
    questions = contract.get("research_questions") if isinstance(contract.get("research_questions"), list) else []
    if not questions:
        errors.append("research_questions_missing")
    trace = contract.get("traceability") if isinstance(contract.get("traceability"), dict) else {}
    if trace.get("schema_version") != TRACE_SCHEMA_VERSION:
        errors.append("invalid_traceability_schema")
    for item in trace.get("items", []):
        if not item.get("mapped_nodes"):
            errors.append(f"question_unmapped:{item.get('question_id', 'N/A')}")
    if not contract.get("source_refs"):
        warnings.append("source_refs_empty")
    if contract.get("mode") == "insight":
        graph_gates = set(graph.get("required_gates") or [])
        if "DD_INSIGHT" not in graph_gates:
            errors.append("insight_gate_missing_from_dag")
        profile_contract = contract.get("insight_profile") if isinstance(contract.get("insight_profile"), dict) else {}
        if profile_contract.get("active") and not profile_contract.get("ok"):
            errors.extend(f"insight_profile_{err}" for err in profile_contract.get("errors", ["invalid"]))
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "question_count": len(questions),
            "node_count": len(nodes),
            "mapping_count": len(contract.get("operator_mapping") or []),
        },
    }
