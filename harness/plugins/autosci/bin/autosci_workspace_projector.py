#!/usr/bin/env python3
"""Project Solar-managed AutoSci run evidence into a human-facing workspace.

The workspace is intentionally a projection of validated run artifacts.  It is
not the execution ledger: logs, envelopes, retry metadata, and operator status
stay under artifacts/autosci/runs and harness/run.
"""
from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WORKSPACE_REL = "artifacts/autosci/workspace"
WIKI_SUBDIRS = [
    "papers",
    "foundations",
    "concepts",
    "methods",
    "people",
    "topics",
    "ideas",
    "experiments",
    "outputs",
    "graph",
]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def _windows_long_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved[2:]
    return "\\\\?\\" + resolved


def write_text_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    long_path = _windows_long_path(path)
    if path.exists():
        with open(long_path, "r", encoding="utf-8") as fh:
            if fh.read() == content:
                return False
    with open(long_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return True


def wiki_open_question_lines(root: Path) -> list[str]:
    gaps: list[str] = []
    collect_wiki_section_items(root / "papers", "Open questions", gaps, "paper")
    collect_wiki_section_items(root / "topics", "Open problems", gaps, "topic")
    collect_wiki_section_items(root / "concepts", "Open problems", gaps, "concept")
    return gaps


def collect_wiki_section_items(directory: Path, section_name: str, out: list[str], source_type: str) -> None:
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        in_section = False
        for line in content.splitlines():
            if re.match(rf"^##\s+{re.escape(section_name)}\s*$", line, re.IGNORECASE):
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section and line.lstrip().startswith(("- ", "* ")):
                bullet = line.lstrip()[2:].strip()
                if bullet:
                    out.append(f"- [{source_type}:{path.stem}] {bullet}")


def render_open_questions(root: Path) -> str:
    gap_lines = wiki_open_question_lines(root)
    body = "# Gap Map\n\n_Auto-generated open questions. Do not edit._\n\n"
    body += "\n".join(gap_lines) + "\n" if gap_lines else "_No gaps detected yet._\n"
    return body


def slugify(value: str, *, fallback: str = "item") -> str:
    raw = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or fallback


def as_posix(path: Path) -> str:
    return path.as_posix()


def rel_to_output(path: Path, output_harness: Path) -> str:
    try:
        return as_posix(path.resolve().relative_to(output_harness.resolve()))
    except ValueError:
        return str(path.resolve())


def resolve_output_ref(raw_path: Any, output_harness: Path) -> Path:
    path = Path(str(raw_path or ""))
    if path.is_absolute():
        return path
    return output_harness / path


def artifact_path(path: Path) -> str:
    return str(path.resolve())


def value_as_text(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value)


def list_lines(items: list[Any]) -> str:
    if not items:
        return "- N/A\n"
    return "".join(f"- {value_as_text(item)}\n" for item in items)


def evidence_link(path: Path, output_harness: Path) -> str:
    return rel_to_output(path, output_harness)


def frontmatter(entity_type: str, entity_id: str, title: str, run_id: str, source_evidence: str) -> str:
    return "\n".join(
        [
            "---",
            f"entity_type: {json.dumps(entity_type)}",
            f"entity_id: {json.dumps(entity_id)}",
            f"title: {json.dumps(title)}",
            f"run_id: {json.dumps(run_id)}",
            f"source_evidence: {json.dumps(source_evidence)}",
            "managed_by: \"solar-autosci-workspace-projector\"",
            "---",
            "",
        ]
    )


def bootstrap_workspace(workspace: Path) -> list[Path]:
    wiki = workspace / "wiki"
    updated: list[Path] = []
    for subdir in WIKI_SUBDIRS:
        (wiki / subdir).mkdir(parents=True, exist_ok=True)
    (workspace / "raw" / "papers").mkdir(parents=True, exist_ok=True)

    readme = """# Solar AutoSci Workspace

This is the human-facing research workspace projected from Solar AutoSci run evidence.

- Read and edit research-facing pages under `wiki/`.
- Keep execution logs, envelopes, gate results, and operator state under Solar-managed `artifacts/autosci/runs/` and `harness/run/`.
- Treat this workspace as a durable research memory view, not as the source of execution truth.
"""
    if write_text_if_changed(workspace / "README.md", readme):
        updated.append(workspace / "README.md")

    raw_readme = """# Raw Sources

This directory is reserved for explicit human-facing source references. Solar-managed run inputs and parser traces remain in `artifacts/autosci/runs/<run-id>/`.
"""
    if write_text_if_changed(workspace / "raw" / "README.md", raw_readme):
        updated.append(workspace / "raw" / "README.md")
    return updated


def project_paper(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "research_paper.analyzed.json"
    payload = load_json_if_exists(evidence_path)
    if payload is None:
        evidence_path = run_dir / "research_paper.json"
        payload = load_json_if_exists(evidence_path)
    if payload is None:
        return []

    paper = payload.get("outputs", {}).get("paper")
    if not isinstance(paper, dict):
        return []

    paper_id = value_as_text(paper.get("paper_id"), "paper-unknown")
    title = value_as_text(paper.get("title"), paper_id)
    page = wiki / "papers" / f"{slugify(paper_id)}.md"
    analysis = paper.get("analysis") if isinstance(paper.get("analysis"), dict) else {}
    sections = paper.get("sections") if isinstance(paper.get("sections"), list) else []

    body = [
        frontmatter("paper", paper_id, title, run_id, evidence_link(evidence_path, output_harness)),
        f"# {title}\n\n",
        "## Source\n\n",
        f"- Paper id: `{paper_id}`\n",
        f"- Source ref: `{value_as_text(paper.get('source_ref'))}`\n",
        f"- Source type: `{value_as_text(paper.get('source_type'))}`\n",
        f"- Parse status: `{value_as_text(paper.get('parse_status'))}`\n",
        f"- Evidence: `{evidence_link(evidence_path, output_harness)}`\n\n",
        "## Abstract\n\n",
        f"{value_as_text(paper.get('abstract'))}\n\n",
    ]
    if analysis:
        body.extend(
            [
                "## Analysis\n\n",
                f"{value_as_text(analysis.get('summary'))}\n\n",
                "### Key Concepts\n\n",
                list_lines([str(item) for item in analysis.get("key_concepts", []) if str(item).strip()]),
                "\n",
            ]
        )
    if sections:
        body.append("## Sections\n\n")
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = value_as_text(section.get("title"), value_as_text(section.get("section_id"), "Section"))
            anchor = value_as_text(section.get("source_anchor"))
            text = value_as_text(section.get("text"))
            body.extend([f"### {heading}\n\n", f"Source anchor: `{anchor}`\n\n", f"{text}\n\n"])

    if write_text_if_changed(page, "".join(body)):
        return [page]
    return []


def project_methods(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "research_method.json"
    payload = load_json_if_exists(evidence_path)
    methods = payload.get("outputs", {}).get("methods") if payload else None
    if not isinstance(methods, list):
        return []

    updated: list[Path] = []
    for method in methods:
        if not isinstance(method, dict):
            continue
        method_id = value_as_text(method.get("method_id"), "method-unknown")
        title = value_as_text(method.get("name"), method_id)
        page = wiki / "methods" / f"{slugify(method_id)}.md"
        content = "".join(
            [
                frontmatter("method", method_id, title, run_id, evidence_link(evidence_path, output_harness)),
                f"# {title}\n\n",
                f"- Method id: `{method_id}`\n",
                f"- Source anchor: `{value_as_text(method.get('source_anchor'))}`\n",
                f"- Evidence: `{evidence_link(evidence_path, output_harness)}`\n\n",
                "## Summary\n\n",
                f"{value_as_text(method.get('summary'))}\n\n",
                "## Procedure\n\n",
                list_lines([str(item) for item in method.get("procedure", []) if str(item).strip()]),
                "\n## Source Papers\n\n",
                list_lines([str(item) for item in method.get("source_papers", []) if str(item).strip()]),
            ]
        )
        if write_text_if_changed(page, content):
            updated.append(page)
    return updated


def project_claims_output(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "research_claims.json"
    payload = load_json_if_exists(evidence_path)
    claims = payload.get("outputs", {}).get("claims") if payload else None
    if not isinstance(claims, list):
        return []

    page = wiki / "outputs" / f"claims-{slugify(run_id)}.md"
    body = [
        frontmatter("claim_set", f"claims-{run_id}", f"Claims from {run_id}", run_id, evidence_link(evidence_path, output_harness)),
        f"# Claims from `{run_id}`\n\n",
        f"Evidence: `{evidence_link(evidence_path, output_harness)}`\n\n",
    ]
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = value_as_text(claim.get("claim_id"), "claim")
        body.extend(
            [
                f"## {claim_id}\n\n",
                f"{value_as_text(claim.get('text'))}\n\n",
                f"- Type: `{value_as_text(claim.get('claim_type'))}`\n",
                f"- Testability: `{value_as_text(claim.get('testability'))}`\n",
                f"- Verification: `{value_as_text(claim.get('verification_status'))}`\n",
                f"- Source anchor: `{value_as_text(claim.get('source_anchor'))}`\n\n",
            ]
        )
    if write_text_if_changed(page, "".join(body)):
        return [page]
    return []


def project_ideas(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "idea_candidate.json"
    payload = load_json_if_exists(evidence_path)
    ideas = payload.get("outputs", {}).get("ideas") if payload else None
    if not isinstance(ideas, list):
        return []

    updated: list[Path] = []
    graph_dir = wiki / "graph"
    edges_path = graph_dir / "edges.jsonl"
    existing_edges: set[str] = set()
    if edges_path.exists():
        existing_edges = {line.strip() for line in edges_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    pilot_boundary = {}
    for artifact in payload.get("artifacts") or []:
        if not isinstance(artifact, dict) or artifact.get("type") != "ideate_pilot_handoff_boundary_json":
            continue
        raw_path = str(artifact.get("path") or "").strip()
        if not raw_path:
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = output_harness / raw_path
        pilot_boundary = load_json_if_exists(candidate) or {}
        break
    pilot_ready = bool(pilot_boundary.get("pilot_handoff_ready"))
    pilot_evidence_ids = [str(item) for item in pilot_boundary.get("evidence_ids") or [] if str(item).strip()]
    new_edges: list[str] = []
    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        idea_id = value_as_text(idea.get("idea_id"), "idea-unknown")
        title = value_as_text(idea.get("title"), idea_id)
        page = wiki / "ideas" / f"{slugify(idea_id)}.md"
        content = "".join(
            [
                frontmatter("idea", idea_id, title, run_id, evidence_link(evidence_path, output_harness)),
                f"# {title}\n\n",
                f"- Idea id: `{idea_id}`\n",
                f"- Status: `{value_as_text(idea.get('status'))}`\n",
                f"- Duplicate status: `{value_as_text(idea.get('duplicate_status'))}`\n",
                f"- Evidence: `{evidence_link(evidence_path, output_harness)}`\n\n",
                "## Hypothesis\n\n",
                f"{value_as_text(idea.get('hypothesis'))}\n\n",
                "## Approach\n\n",
                f"{value_as_text(idea.get('approach'))}\n\n",
                "## Grounding\n\n",
                f"{value_as_text(idea.get('grounding_summary'))}\n",
            ]
        )
        if write_text_if_changed(page, content):
            updated.append(page)
        source_ref = f"ideas/{page.name}"
        for origin in idea.get("origin_evidence_ids") or []:
            target = str(origin).strip()
            if not target:
                continue
            edge = {
                "source": source_ref,
                "target": target,
                "relation": "generated_from",
                "run_id": run_id,
                "source_evidence": evidence_link(evidence_path, output_harness),
            }
            line = json.dumps(edge, sort_keys=True)
            if line not in existing_edges:
                existing_edges.add(line)
                new_edges.append(line)
        if pilot_ready:
            for evidence_id in pilot_evidence_ids or ["pilot_handoff"]:
                edge = {
                    "source": source_ref,
                    "target": evidence_id,
                    "relation": "has_pilot_handoff",
                    "run_id": run_id,
                    "source_evidence": evidence_link(evidence_path, output_harness),
                }
                line = json.dumps(edge, sort_keys=True)
                if line not in existing_edges:
                    existing_edges.add(line)
                    new_edges.append(line)
    if new_edges:
        edges_path.parent.mkdir(parents=True, exist_ok=True)
        with edges_path.open("a", encoding="utf-8") as handle:
            for line in new_edges:
                handle.write(line + "\n")
        updated.append(edges_path)
    return updated


def project_discovery_summary(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "literature_discovery.json"
    payload = load_json_if_exists(evidence_path)
    if payload is None:
        return []

    outputs = payload.get("outputs", {}) if isinstance(payload.get("outputs"), dict) else {}
    candidates = outputs.get("candidates") if isinstance(outputs.get("candidates"), list) else []
    source_boundary = (
        outputs.get("source_provider_boundary")
        if isinstance(outputs.get("source_provider_boundary"), dict)
        else {}
    )
    final_boundary = (
        source_boundary.get("final_shortlist_boundary")
        if isinstance(source_boundary.get("final_shortlist_boundary"), dict)
        else {}
    )

    candidate_rows: list[list[str]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = value_as_text(
            candidate.get("candidate_id")
            or candidate.get("paper_id")
            or candidate.get("paperId")
            or candidate.get("arxiv_id"),
            f"candidate-{len(candidate_rows) + 1:03d}",
        )
        channels = candidate.get("source_channels") if isinstance(candidate.get("source_channels"), list) else []
        summary = value_as_text(candidate.get("summary") or candidate.get("abstract") or candidate.get("ranking_rationale"))
        if len(summary) > 240:
            summary = summary[:237].rstrip() + "..."
        candidate_rows.append(
            [
                candidate_id,
                value_as_text(candidate.get("title"), candidate_id),
                ", ".join(value_as_text(channel) for channel in channels if str(channel).strip()) or "N/A",
                value_as_text(candidate.get("ranking_score") or candidate.get("score")),
                value_as_text(candidate.get("dedup_status")),
                value_as_text(candidate.get("fetch_status")),
                value_as_text(candidate.get("source_ref") or candidate.get("url") or candidate.get("pdf_url")),
                summary,
            ]
        )

    blocking_rows: list[list[str]] = [
        [value_as_text(reason)]
        for reason in final_boundary.get("blocking_reasons", [])
        if str(reason).strip()
    ]
    artifact_rows: list[list[str]] = []
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        artifact_rows.append(
            [
                value_as_text(artifact.get("type")),
                value_as_text(artifact.get("path")),
            ]
        )

    limitations: list[str] = []
    for item in [
        *list(payload.get("limitations") or []),
        *list(source_boundary.get("limitations") or []),
        *list(final_boundary.get("limitations") or []),
    ]:
        text = str(item).strip()
        if text and text not in limitations:
            limitations.append(text)

    page = wiki / "outputs" / "discovery.md"
    body = [
        frontmatter("output", f"discovery-{run_id}", f"Discovery summary for {run_id}", run_id, evidence_link(evidence_path, output_harness)),
        f"# Discovery Summary: `{run_id}`\n\n",
        "## Status\n\n",
        f"- Evidence status: `{value_as_text(payload.get('status'))}`\n",
        f"- Query: `{value_as_text(outputs.get('query') or payload.get('inputs', {}).get('query'))}`\n",
        f"- Mode: `{value_as_text(outputs.get('mode'))}`\n",
        f"- Limit: `{value_as_text(outputs.get('limit'))}`\n",
        f"- Candidate count: `{len([candidate for candidate in candidates if isinstance(candidate, dict)])}`\n",
        f"- Source provider boundary status: `{value_as_text(source_boundary.get('status'))}`\n",
        f"- Final shortlist ready: `{value_as_text(final_boundary.get('final_shortlist_ready'))}`\n",
        f"- Final boundary status: `{value_as_text(final_boundary.get('status'))}`\n",
        f"- Discovery evidence: `{evidence_link(evidence_path, output_harness)}`\n\n",
        "## Source Boundary\n\n",
        f"- Source channels: `{', '.join(value_as_text(channel) for channel in source_boundary.get('source_channels', []) if str(channel).strip()) or 'N/A'}`\n",
        f"- Provider channels: `{', '.join(value_as_text(channel) for channel in source_boundary.get('provider_channels', []) if str(channel).strip()) or 'N/A'}`\n",
        f"- Generic channels: `{', '.join(value_as_text(channel) for channel in source_boundary.get('generic_channels', []) if str(channel).strip()) or 'N/A'}`\n\n",
        "## Candidates\n\n",
        _markdown_table(
            ["Candidate", "Title", "Channels", "Score", "Dedup", "Fetch", "Source", "Summary"],
            candidate_rows,
        ),
        "\n## Blocking Reasons\n\n",
        _markdown_table(["Reason"], blocking_rows),
        "\n## Artifacts\n\n",
        _markdown_table(["Type", "Path"], artifact_rows),
        "\n## Limitations\n\n",
        list_lines(limitations),
    ]
    if write_text_if_changed(page, "".join(body)):
        return [page]
    return []


def project_review_summary(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "artifact_review.json"
    payload = load_json_if_exists(evidence_path)
    if payload is None:
        return []

    outputs = payload.get("outputs", {}) if isinstance(payload.get("outputs"), dict) else {}
    review = outputs.get("review") if isinstance(outputs.get("review"), dict) else {}
    artifact = outputs.get("artifact") if isinstance(outputs.get("artifact"), dict) else {}
    boundary = outputs.get("final_acceptance_boundary") if isinstance(outputs.get("final_acceptance_boundary"), dict) else {}
    findings = outputs.get("findings") if isinstance(outputs.get("findings"), list) else []
    limitations = payload.get("limitations") if isinstance(payload.get("limitations"), list) else []

    finding_rows: list[list[str]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_rows.append(
            [
                value_as_text(finding.get("finding_id"), f"finding-{len(finding_rows) + 1}"),
                value_as_text(finding.get("severity")),
                value_as_text(finding.get("summary") or finding.get("description")),
                value_as_text(finding.get("evidence")),
            ]
        )

    blocking_rows: list[list[str]] = [
        [value_as_text(reason)]
        for reason in boundary.get("blocking_reasons", [])
        if str(reason).strip()
    ]
    evidence_id_rows: list[list[str]] = [
        [value_as_text(evidence_id)]
        for evidence_id in (review.get("evidence_ids") or boundary.get("evidence_ids") or [])
        if str(evidence_id).strip()
    ]

    review_llm = review.get("review_llm") if isinstance(review.get("review_llm"), dict) else {}
    page = wiki / "outputs" / "review.md"
    body = [
        frontmatter("output", f"review-{run_id}", f"Review diagnostics for {run_id}", run_id, evidence_link(evidence_path, output_harness)),
        f"# Review Diagnostics: `{run_id}`\n\n",
        "## Status\n\n",
        f"- Evidence status: `{value_as_text(payload.get('status'))}`\n",
        f"- Target: `{value_as_text(artifact.get('path') or payload.get('inputs', {}).get('target'))}`\n",
        f"- Focus: `{value_as_text(review.get('focus') or payload.get('inputs', {}).get('focus'))}`\n",
        f"- Difficulty: `{value_as_text(review.get('difficulty') or payload.get('inputs', {}).get('difficulty'))}`\n",
        f"- Review mode: `{value_as_text(review.get('review_mode'))}`\n",
        f"- Review available: `{value_as_text(review.get('review_available'))}`\n",
        f"- Score: `{value_as_text(review.get('score'))}`\n",
        f"- Recommendation: `{value_as_text(review.get('recommendation'))}`\n",
        f"- Final acceptance ready: `{value_as_text(boundary.get('final_acceptance_ready'))}`\n",
        f"- Final boundary status: `{value_as_text(boundary.get('status'))}`\n\n",
        "## Review LLM Evidence\n\n",
        f"- Review LLM status: `{value_as_text(review_llm.get('status'))}`\n",
        f"- Invocation mode: `{value_as_text(boundary.get('invocation_mode') or review_llm.get('invocation_mode'))}`\n",
        f"- Provider: `{value_as_text(boundary.get('provider') or review_llm.get('provider'))}`\n",
        f"- Model: `{value_as_text(boundary.get('model') or review_llm.get('model'))}`\n",
        f"- Request sha256: `{value_as_text(boundary.get('request_sha256') or review_llm.get('request_sha256'))}`\n",
        f"- Response sha256: `{value_as_text(boundary.get('response_sha256') or review_llm.get('response_sha256'))}`\n\n",
        "## Evidence\n\n",
        f"- Review evidence: `{evidence_link(evidence_path, output_harness)}`\n\n",
        _markdown_table(["Evidence ID"], evidence_id_rows),
        "\n## Findings\n\n",
        _markdown_table(["Finding", "Severity", "Summary", "Evidence"], finding_rows),
        "\n## Blocking Reasons\n\n",
        _markdown_table(["Reason"], blocking_rows),
        "\n## Limitations\n\n",
        list_lines([str(item) for item in limitations if str(item).strip()]),
    ]
    if write_text_if_changed(page, "".join(body)):
        return [page]
    return []


def project_ideas_summary(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    candidate_path = run_dir / "idea_candidate.json"
    candidate_payload = load_json_if_exists(candidate_path)
    if candidate_payload is None:
        return []

    ideas = candidate_payload.get("outputs", {}).get("ideas")
    if not isinstance(ideas, list):
        return []

    evaluation_path = run_dir / "idea_evaluation.json"
    evaluation_payload = load_json_if_exists(evaluation_path)
    evaluations = (
        evaluation_payload.get("outputs", {}).get("evaluations")
        if isinstance(evaluation_payload, dict)
        else None
    )
    if not isinstance(evaluations, list):
        evaluations = []
    evaluation_by_id = {
        value_as_text(item.get("idea_id")): item
        for item in evaluations
        if isinstance(item, dict)
    }

    idea_rows: list[list[str]] = []
    selected_rows: list[list[str]] = []
    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        idea_id = value_as_text(idea.get("idea_id"), f"idea-{len(idea_rows) + 1:03d}")
        evaluation = evaluation_by_id.get(idea_id, {})
        boundary = evaluation.get("final_acceptance_boundary") if isinstance(evaluation.get("final_acceptance_boundary"), dict) else {}
        idea_rows.append(
            [
                idea_id,
                value_as_text(idea.get("title"), idea_id),
                value_as_text(idea.get("status")),
                value_as_text(idea.get("duplicate_status")),
                value_as_text(idea.get("source_mode")),
                value_as_text(evaluation.get("recommendation")),
                value_as_text(boundary.get("final_acceptance_ready")),
            ]
        )
        if idea.get("selected_for_write") is True or len(selected_rows) < 5:
            selected_rows.append(
                [
                    idea_id,
                    value_as_text(idea.get("hypothesis")),
                    value_as_text(idea.get("approach")),
                    ", ".join(value_as_text(item) for item in idea.get("origin_evidence_ids", []) if str(item).strip()) or "N/A",
                ]
            )

    limitations = [str(item) for item in candidate_payload.get("limitations", []) if str(item).strip()]
    if evaluation_payload:
        limitations.extend(str(item) for item in evaluation_payload.get("limitations", []) if str(item).strip())

    boundary_rows: list[list[str]] = []
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            continue
        boundary = evaluation.get("final_acceptance_boundary") if isinstance(evaluation.get("final_acceptance_boundary"), dict) else {}
        blocking_reasons = boundary.get("blocking_reasons") if isinstance(boundary.get("blocking_reasons"), list) else []
        boundary_rows.append(
            [
                value_as_text(evaluation.get("idea_id")),
                value_as_text(boundary.get("status")),
                value_as_text(boundary.get("external_novelty_status")),
                value_as_text(boundary.get("review_llm_status")),
                "; ".join(value_as_text(reason) for reason in blocking_reasons if str(reason).strip()) or "N/A",
            ]
        )

    page = wiki / "outputs" / "ideas.md"
    body = [
        frontmatter("output", f"ideas-{run_id}", f"Idea summary for {run_id}", run_id, evidence_link(candidate_path, output_harness)),
        f"# Idea Summary: `{run_id}`\n\n",
        "## Status\n\n",
        f"- Candidate evidence status: `{value_as_text(candidate_payload.get('status'))}`\n",
        f"- Evaluation evidence status: `{value_as_text(evaluation_payload.get('status') if evaluation_payload else None)}`\n",
        f"- Candidate count: `{len([idea for idea in ideas if isinstance(idea, dict)])}`\n",
        f"- Evaluation count: `{len(evaluations)}`\n",
        f"- Candidate evidence: `{evidence_link(candidate_path, output_harness)}`\n",
        f"- Evaluation evidence: `{evidence_link(evaluation_path, output_harness) if evaluation_payload else 'N/A'}`\n\n",
        "## Ideas\n\n",
        _markdown_table(
            ["Idea", "Title", "Status", "Duplicate", "Source Mode", "Recommendation", "Final Ready"],
            idea_rows,
        ),
        "\n## Selected Details\n\n",
        _markdown_table(["Idea", "Hypothesis", "Approach", "Origin Evidence"], selected_rows),
        "\n## Novelty And Review Boundary\n\n",
        _markdown_table(
            ["Idea", "Boundary Status", "External Novelty", "Review LLM", "Blocking Reasons"],
            boundary_rows,
        ),
        "\n## Limitations\n\n",
        list_lines(limitations),
    ]
    if write_text_if_changed(page, "".join(body)):
        return [page]
    return []


def project_experiment(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "experiment_plan.json"
    payload = load_json_if_exists(evidence_path)
    plan = payload.get("outputs", {}).get("experiment_plan") if payload else None
    result_evidence_path = run_dir / "experiment_result.json"
    result_payload = load_json_if_exists(result_evidence_path)
    result = result_payload.get("outputs", {}).get("result") if result_payload else None
    if not isinstance(plan, dict) and not isinstance(result, dict):
        return []

    plan = plan if isinstance(plan, dict) else {}
    result = result if isinstance(result, dict) else {}
    experiment_id = value_as_text(result.get("experiment_id") or plan.get("experiment_id"), "experiment-unknown")
    title = value_as_text(plan.get("objective"), experiment_id)
    status = "completed" if result_payload and result_payload.get("status") == "completed" else value_as_text(plan.get("status"), "planned")
    outcome = value_as_text(result.get("outcome"), "N/A")
    source_path = result_evidence_path if result_payload and result_evidence_path.exists() else evidence_path
    page = wiki / "experiments" / f"{slugify(experiment_id)}.md"
    metric_lines = [
        f"- {value_as_text(metric.get('name'))}: `{value_as_text(metric.get('value'))}`\n"
        for metric in result.get("metrics", [])
        if isinstance(metric, dict)
    ]
    evidence_id_lines = [
        f"- `{value_as_text(evidence_id)}`\n"
        for evidence_id in result.get("evidence_ids", [])
        if str(evidence_id).strip()
    ]
    frontmatter_lines = [
        "---",
        f"entity_type: {json.dumps('experiment')}",
        f"entity_id: {json.dumps(experiment_id)}",
        f"title: {json.dumps(title)}",
        f"run_id: {json.dumps(run_id)}",
        f"source_evidence: {json.dumps(evidence_link(source_path, output_harness))}",
        f"status: {status}",
        f"outcome: {outcome}",
        "managed_by: \"solar-autosci-workspace-projector\"",
        "---",
        "",
    ]
    content = "".join(
        [
            "\n".join(frontmatter_lines),
            f"# {title}\n\n",
            f"- Experiment id: `{experiment_id}`\n",
            f"- Status: `{status}`\n",
            f"- Outcome: `{outcome}`\n",
            f"- Execution mode: `{value_as_text(plan.get('execution_mode'))}`\n",
            f"- Approval required: `{value_as_text(plan.get('approval_required'))}`\n",
            f"- Plan evidence: `{evidence_link(evidence_path, output_harness) if evidence_path.exists() else 'N/A'}`\n",
            f"- Result evidence: `{evidence_link(result_evidence_path, output_harness) if result_evidence_path.exists() else 'N/A'}`\n\n",
            "## Hypothesis\n\n",
            f"{value_as_text(plan.get('hypothesis'))}\n\n",
            "## Procedure\n\n",
            list_lines([str(item) for item in plan.get("procedure", []) if str(item).strip()]),
            "\n## Success Criteria\n\n",
            list_lines([str(item) for item in plan.get("success_criteria", []) if str(item).strip()]),
            "\n## Result Metrics\n\n",
            "".join(metric_lines) if metric_lines else "- N/A\n",
            "\n## Result Evidence IDs\n\n",
            "".join(evidence_id_lines) if evidence_id_lines else "- N/A\n",
        ]
    )
    if write_text_if_changed(page, content):
        return [page]
    return []


def project_experiment_summary(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    plan_path = run_dir / "experiment_plan.json"
    result_path = run_dir / "experiment_result.json"
    status_path = run_dir / "experiment_status.json"
    plan_payload = load_json_if_exists(plan_path)
    result_payload = load_json_if_exists(result_path)
    status_payload = load_json_if_exists(status_path)
    if plan_payload is None and result_payload is None and status_payload is None:
        return []

    plan = plan_payload.get("outputs", {}).get("experiment_plan") if plan_payload else None
    result = result_payload.get("outputs", {}).get("result") if result_payload else None
    status_report = status_payload.get("outputs", {}).get("status_report") if status_payload else None
    plan = plan if isinstance(plan, dict) else {}
    result = result if isinstance(result, dict) else {}
    status_report = status_report if isinstance(status_report, dict) else {}
    boundary = (
        result.get("final_runtime_audit_boundary")
        or status_report.get("final_runtime_audit_boundary")
        or (result_payload or {}).get("outputs", {}).get("final_runtime_audit_boundary")
        or (status_payload or {}).get("outputs", {}).get("final_runtime_audit_boundary")
    )
    boundary = boundary if isinstance(boundary, dict) else {}
    experiment_id = value_as_text(
        result.get("experiment_id") or status_report.get("experiment_id") or plan.get("experiment_id"),
        "experiment-unknown",
    )
    metrics = result.get("metrics") if isinstance(result.get("metrics"), list) else []
    metric_rows = [
        [value_as_text(metric.get("name")), value_as_text(metric.get("value"))]
        for metric in metrics
        if isinstance(metric, dict)
    ]
    artifacts = [
        *list((plan_payload or {}).get("artifacts") or []),
        *list((result_payload or {}).get("artifacts") or []),
        *list((status_payload or {}).get("artifacts") or []),
    ]
    artifact_rows = [
        [value_as_text(artifact.get("type")), value_as_text(artifact.get("path"))]
        for artifact in artifacts
        if isinstance(artifact, dict)
    ]
    limitations = []
    for item in [
        *list((plan_payload or {}).get("limitations") or []),
        *list((result_payload or {}).get("limitations") or []),
        *list((status_payload or {}).get("limitations") or []),
        *list(boundary.get("limitations") or []),
    ]:
        text = str(item).strip()
        if text and text not in limitations:
            limitations.append(text)
    log_rows = [
        [value_as_text(line)]
        for line in result.get("logs", [])
        if str(line).strip()
    ]
    source_evidence_path = result_path if result_path.exists() else status_path if status_path.exists() else plan_path
    page = wiki / "outputs" / "experiment.md"
    body = [
        frontmatter("output", f"experiment-{run_id}", f"Experiment summary for {run_id}", run_id, evidence_link(source_evidence_path, output_harness)),
        f"# Experiment Summary: `{run_id}`\n\n",
        "## Status\n\n",
        f"- Experiment id: `{experiment_id}`\n",
        f"- Plan evidence status: `{value_as_text(plan_payload.get('status') if plan_payload else None)}`\n",
        f"- Result evidence status: `{value_as_text(result_payload.get('status') if result_payload else None)}`\n",
        f"- Status evidence status: `{value_as_text(status_payload.get('status') if status_payload else None)}`\n",
        f"- Outcome: `{value_as_text(result.get('outcome'))}`\n",
        f"- State: `{value_as_text(status_report.get('state'))}`\n",
        f"- Execution mode: `{value_as_text(result.get('execution_mode') or plan.get('execution_mode'))}`\n",
        f"- Command run: `{value_as_text(result.get('command_run'))}`\n",
        f"- Plan evidence: `{evidence_link(plan_path, output_harness) if plan_path.exists() else 'N/A'}`\n",
        f"- Result evidence: `{evidence_link(result_path, output_harness) if result_path.exists() else 'N/A'}`\n",
        f"- Status evidence: `{evidence_link(status_path, output_harness) if status_path.exists() else 'N/A'}`\n\n",
        "## Runtime Audit Boundary\n\n",
        f"- Boundary status: `{value_as_text(boundary.get('status'))}`\n",
        f"- Stage: `{value_as_text(boundary.get('stage'))}`\n",
        f"- Final runtime audit ready: `{value_as_text(boundary.get('final_runtime_audit_ready'))}`\n",
        f"- Stage audit ready: `{value_as_text(boundary.get('stage_audit_ready'))}`\n",
        f"- Approval contract verified: `{value_as_text(boundary.get('approval_contract_verified'))}`\n",
        f"- Runtime semantic verified: `{value_as_text(boundary.get('runtime_semantic_verified'))}`\n",
        f"- Result collected: `{value_as_text(boundary.get('result_collected'))}`\n",
        f"- Collection ledger recorded: `{value_as_text(boundary.get('collection_ledger_recorded'))}`\n",
        f"- Live remote collection verified: `{value_as_text(boundary.get('live_remote_collection_verified'))}`\n\n",
        "## Metrics\n\n",
        _markdown_table(["Metric", "Value"], metric_rows),
        "\n## Logs\n\n",
        _markdown_table(["Log"], log_rows),
        "\n## Artifacts\n\n",
        _markdown_table(["Type", "Path"], artifact_rows),
        "\n## Limitations\n\n",
        list_lines(limitations),
    ]
    if write_text_if_changed(page, "".join(body)):
        return [page]
    return []


def project_report(run_dir: Path, wiki: Path, output_harness: Path, run_id: str) -> list[Path]:
    evidence_path = run_dir / "scientific_report.json"
    payload = load_json_if_exists(evidence_path)
    report = payload.get("outputs", {}).get("report") if payload else None
    report_id = "report-" + slugify(run_id)
    title = f"Report from {run_id}"
    if isinstance(report, dict):
        report_id = value_as_text(report.get("report_id"), report_id)
        title = value_as_text(payload.get("inputs", {}).get("report_title"), title)

    source_report = run_dir / "report.md"
    if not source_report.exists() and payload is None:
        return []

    source_body = source_report.read_text(encoding="utf-8") if source_report.exists() else ""
    body = [
        frontmatter("output", report_id, title, run_id, evidence_link(evidence_path if evidence_path.exists() else source_report, output_harness)),
        f"# {title}\n\n",
        f"- Report id: `{report_id}`\n",
        f"- Run artifact: `{evidence_link(source_report, output_harness) if source_report.exists() else 'N/A'}`\n",
        f"- Evidence: `{evidence_link(evidence_path, output_harness) if evidence_path.exists() else 'N/A'}`\n\n",
    ]
    if source_body.strip():
        body.extend(["## Report Body\n\n", source_body.strip(), "\n"])
    elif isinstance(report, dict):
        body.append("## Sections\n\n")
        for section in report.get("sections", []):
            if not isinstance(section, dict):
                continue
            body.extend([f"### {value_as_text(section.get('title'), 'Section')}\n\n", f"{value_as_text(section.get('body'))}\n\n"])

    updated: list[Path] = []
    pages = [wiki / "outputs" / f"{slugify(report_id)}.md"]
    stable_page = wiki / "outputs" / "report.md"
    if stable_page not in pages:
        pages.append(stable_page)
    content = "".join(body)
    for page in pages:
        if write_text_if_changed(page, content):
            updated.append(page)
    return updated


def _resolve_output_ref(raw: Any, output_harness: Path) -> Path | None:
    text = value_as_text(raw, "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    return output_harness / path


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "- N/A\n"
    header = "| " + " | ".join(headers) + " |\n"
    divider = "| " + " | ".join("---" for _ in headers) + " |\n"
    body = "".join("| " + " | ".join(value_as_text(cell).replace("\n", " ") for cell in row) + " |\n" for row in rows)
    return header + divider + body


def project_lifecycle_summary(
    skill_run_path: Path,
    payload: dict[str, Any],
    wiki: Path,
    output_harness: Path,
    run_id: str,
) -> list[Path]:
    skill_run = payload.get("outputs", {}).get("skill_run", {})
    if not isinstance(skill_run, dict):
        return []
    scheduler_lifecycle = skill_run.get("scheduler_lifecycle")
    if not isinstance(scheduler_lifecycle, dict) or not scheduler_lifecycle:
        return []

    summary_path = _resolve_output_ref(scheduler_lifecycle.get("summary_path"), output_harness)
    lifecycle = load_json_if_exists(summary_path) if summary_path else None
    if not isinstance(lifecycle, dict):
        return []

    output_page = wiki / "outputs" / "lifecycle_summary.md"
    workflow_id = value_as_text(lifecycle.get("workflow_id"))
    job_id = value_as_text(lifecycle.get("job_id"))
    status = value_as_text(lifecycle.get("lifecycle_status"), value_as_text(scheduler_lifecycle.get("status")))
    execution_owner = value_as_text(lifecycle.get("execution_owner"))
    dispatch = lifecycle.get("dispatch_boundary") if isinstance(lifecycle.get("dispatch_boundary"), dict) else {}
    lifecycle_gate = lifecycle.get("lifecycle_gate_result") if isinstance(lifecycle.get("lifecycle_gate_result"), dict) else {}
    node_results = lifecycle.get("node_results") if isinstance(lifecycle.get("node_results"), dict) else {}
    gate_results = lifecycle.get("gate_results") if isinstance(lifecycle.get("gate_results"), dict) else {}
    blocked_nodes = lifecycle.get("blocked_nodes") if isinstance(lifecycle.get("blocked_nodes"), dict) else {}

    node_rows: list[list[str]] = []
    for node_id in sorted(set(node_results) | set(gate_results)):
        node_result = node_results.get(node_id) if isinstance(node_results.get(node_id), dict) else {}
        gate_result = gate_results.get(node_id) if isinstance(gate_results.get(node_id), dict) else {}
        node_rows.append(
            [
                node_id,
                value_as_text(node_result.get("status")),
                value_as_text(gate_result.get("status") or gate_result.get("gate_status")),
                value_as_text(node_result.get("artifact_path")),
            ]
        )

    blocked_rows: list[list[str]] = []
    for node_id, raw in sorted(blocked_nodes.items()):
        node = raw if isinstance(raw, dict) else {}
        required = node.get("required_evidence")
        if isinstance(required, list):
            required_text = ", ".join(value_as_text(item) for item in required)
        else:
            required_text = value_as_text(required)
        blocked_rows.append(
            [
                node_id,
                value_as_text(node.get("reason")),
                required_text,
                value_as_text(node.get("unblock_condition")),
            ]
        )

    runtime_manifest = _resolve_output_ref(lifecycle.get("runtime_manifest_path"), output_harness)
    source_summary = evidence_link(summary_path, output_harness) if summary_path else "N/A"
    runtime_manifest_ref = evidence_link(runtime_manifest, output_harness) if runtime_manifest else "N/A"
    skill_run_ref = evidence_link(skill_run_path, output_harness)

    body = [
        frontmatter("output", f"lifecycle-summary-{run_id}", f"Lifecycle summary for {run_id}", run_id, source_summary),
        f"# Lifecycle Summary: `{run_id}`\n\n",
        "## Status\n\n",
        f"- Lifecycle status: `{status}`\n",
        f"- Workflow id: `{workflow_id}`\n",
        f"- Job id: `{job_id}`\n",
        f"- Execution owner: `{execution_owner}`\n",
        f"- Dispatch boundary: `{value_as_text(dispatch.get('status'))}`\n",
        f"- Production ready: `{value_as_text(dispatch.get('production_ready'))}`\n",
        f"- Lifecycle gate: `{value_as_text(lifecycle_gate.get('status'))}`\n",
        f"- Node count: `{len(node_results)}`\n",
        f"- Blocked node count: `{len(blocked_nodes)}`\n\n",
        "## Evidence\n\n",
        f"- Skill run: `{skill_run_ref}`\n",
        f"- Lifecycle summary: `{source_summary}`\n",
        f"- Runtime manifest: `{runtime_manifest_ref}`\n\n",
        "## Node Results\n\n",
        _markdown_table(["Node", "Node Status", "Gate Status", "Artifact"], node_rows),
        "\n## Blocked Nodes\n\n",
        _markdown_table(["Node", "Reason", "Required Evidence", "Unblock Condition"], blocked_rows),
        "\n## Notes\n\n",
        "- This page is projected from Solar-managed evidence; it is not the execution ledger.\n",
        "- Missing provider, model, approval, or runtime evidence remains visible as blocked or inconclusive state.\n",
    ]
    if write_text_if_changed(output_page, "".join(body)):
        return [output_page]
    return []


def graph_evidence_paths(
    run_dir: Path,
    output_harness: Path,
    action_evidence_paths: list[str] | None = None,
) -> list[Path]:
    candidates: list[Path] = [
        *sorted(run_dir.glob("research_graph_update*.json")),
    ]
    for raw_path in action_evidence_paths or []:
        path = resolve_output_ref(raw_path, output_harness)
        candidates.append(path)
        payload = load_json_if_exists(path)
        if not payload:
            continue
        for artifact in payload.get("artifacts") or []:
            if not isinstance(artifact, dict):
                continue
            artifact_type = str(artifact.get("type") or "")
            if "research_graph_update" not in artifact_type:
                continue
            artifact_path = str(artifact.get("path") or "").strip()
            if artifact_path:
                candidates.append(resolve_output_ref(artifact_path, output_harness))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        payload = load_json_if_exists(path)
        if not payload:
            continue
        edges = payload.get("outputs", {}).get("edges")
        if payload.get("schema") == "research_graph_update.v1" or isinstance(edges, list):
            seen.add(resolved)
            unique.append(path)
    return unique


def project_graph(
    run_dir: Path,
    wiki: Path,
    output_harness: Path,
    run_id: str,
    *,
    action_evidence_paths: list[str] | None = None,
) -> list[Path]:
    updated: list[Path] = []
    graph_dir = wiki / "graph"
    edges_path = graph_dir / "edges.jsonl"
    existing: set[str] = set()
    if edges_path.exists():
        existing = {line.strip() for line in edges_path.read_text(encoding="utf-8").splitlines() if line.strip()}

    new_lines: list[str] = []
    source_paths = graph_evidence_paths(run_dir, output_harness, action_evidence_paths)
    projected_edge_count = 0
    for source_path in source_paths:
        payload = load_json_if_exists(source_path)
        edges = payload.get("outputs", {}).get("edges") if payload else None
        if not isinstance(edges, list):
            continue
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            projected_edge_count += 1
            enriched = {**edge, "run_id": run_id, "source_evidence": rel_to_output(source_path, output_harness)}
            line = json.dumps(enriched, sort_keys=True)
            if line not in existing:
                existing.add(line)
                new_lines.append(line)
    if new_lines:
        edges_path.parent.mkdir(parents=True, exist_ok=True)
        with edges_path.open("a", encoding="utf-8") as handle:
            for line in new_lines:
                handle.write(line + "\n")
        updated.append(edges_path)

    citations_path = graph_dir / "citations.jsonl"
    if write_text_if_changed(citations_path, citations_path.read_text(encoding="utf-8") if citations_path.exists() else ""):
        updated.append(citations_path)

    if source_paths:
        manifest = {
            "schema": "autosci_workspace_graph_projection.v1",
            "run_id": run_id,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source_evidence": [rel_to_output(path, output_harness) for path in source_paths],
            "projected_edge_count": projected_edge_count,
            "written_edge_count": len(new_lines),
            "edges_path": rel_to_output(edges_path, output_harness),
            "status": "projected",
            "limitations": [],
        }
        manifest_path = graph_dir / "projection_manifest.json"
        if write_text_if_changed(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n"):
            updated.append(manifest_path)

    mutation_payload = load_json_if_exists(run_dir / "novelty_writeback.json")
    mutation_write = {}
    if mutation_payload:
        candidate = mutation_payload.get("outputs", {}).get("write")
        if isinstance(candidate, dict) and candidate.get("applied"):
            mutation_write = candidate

    context_brief = "\n".join(
        [
            "# Solar AutoSci Context Brief",
            "",
            f"Last projected run: `{run_id}`",
            f"Updated at: `{datetime.now(UTC).isoformat().replace('+00:00', 'Z')}`",
            *(
                [
                    f"Mutation target: `{value_as_text(mutation_write.get('idea_path'))}`",
                    f"Mutation edge: `{value_as_text(mutation_write.get('edge_path'))}`",
                    f"Mutation log: `{value_as_text(mutation_write.get('log_path'))}`",
                ]
                if mutation_write
                else []
            ),
            "",
            "Use `wiki/papers/`, `wiki/methods/`, `wiki/ideas/`, and `wiki/experiments/` for human research navigation.",
            "Use `wiki/graph/edges.jsonl` for structured graph edges from approved mutations and projected graph evidence.",
            "Use `artifacts/autosci/runs/` for Solar-managed execution evidence.",
            "",
        ]
    )
    if write_text_if_changed(graph_dir / "context_brief.md", context_brief):
        updated.append(graph_dir / "context_brief.md")

    open_questions = render_open_questions(wiki)
    if write_text_if_changed(graph_dir / "open_questions.md", open_questions):
        updated.append(graph_dir / "open_questions.md")
    return updated


def rebuild_index(workspace: Path, run_id: str) -> list[Path]:
    wiki = workspace / "wiki"
    demo_entries = [
        (
            "what ran",
            "outputs/lifecycle_summary.md",
            "Lifecycle status, node/gate results, and blocked nodes.",
        ),
        (
            "what was produced",
            "outputs/report.md",
            "Report artifact, evidence ids, and publication limitations.",
        ),
        (
            "what is blocked",
            "outputs/review.md",
            "Review availability, findings, and blocking reasons.",
        ),
        (
            "what evidence exists",
            "outputs/ideas.md",
            "Candidate/evaluation evidence and promotion boundaries.",
        ),
        (
            "what remains incomplete",
            "outputs/experiment.md",
            "Approval/runtime audit, collection, and remote proof status.",
        ),
    ]
    demo_rows = [
        [
            question,
            "ok" if (wiki / rel_path).exists() else "pending",
            f"[{Path(rel_path).stem}]({rel_path})",
            description,
        ]
        for question, rel_path, description in demo_entries
    ]
    lines = [
        "# Solar AutoSci Wiki\n\n",
        "Human-facing research memory projected from Solar-managed evidence.\n\n",
        f"Last projected run: `{run_id}`\n\n",
        "## Demo Entry Points\n\n",
        _markdown_table(["Question", "Status", "Page", "What to inspect"], demo_rows),
        "\n",
    ]
    for subdir in ["papers", "foundations", "concepts", "methods", "people", "topics", "ideas", "experiments", "outputs"]:
        lines.append(f"## {subdir.title()}\n\n")
        pages = sorted((wiki / subdir).glob("*.md"))
        if not pages:
            lines.append("- N/A\n\n")
            continue
        for page in pages:
            lines.append(f"- [{page.stem}]({subdir}/{page.name})\n")
        lines.append("\n")

    updated: list[Path] = []
    if write_text_if_changed(wiki / "index.md", "".join(lines)):
        updated.append(wiki / "index.md")
    return updated


def project_run_to_workspace(
    skill_run_path: Path,
    *,
    output_harness: Path,
    workspace_rel: str = WORKSPACE_REL,
    include_idea_pages: bool = True,
) -> dict[str, Any]:
    payload = load_json(skill_run_path)
    inputs = payload.get("inputs", {})
    run_id = value_as_text(inputs.get("run_id"), value_as_text(payload.get("sprint_id"), "autosci-run"))
    work_dir = value_as_text(inputs.get("work_dir"), "")
    run_dir = output_harness / work_dir
    workspace = output_harness / workspace_rel
    wiki = workspace / "wiki"

    updated = bootstrap_workspace(workspace)
    updated.extend(project_paper(run_dir, wiki, output_harness, run_id))
    updated.extend(project_methods(run_dir, wiki, output_harness, run_id))
    updated.extend(project_claims_output(run_dir, wiki, output_harness, run_id))
    if include_idea_pages:
        updated.extend(project_ideas(run_dir, wiki, output_harness, run_id))
    updated.extend(project_discovery_summary(run_dir, wiki, output_harness, run_id))
    updated.extend(project_review_summary(run_dir, wiki, output_harness, run_id))
    updated.extend(project_ideas_summary(run_dir, wiki, output_harness, run_id))
    updated.extend(project_experiment(run_dir, wiki, output_harness, run_id))
    updated.extend(project_experiment_summary(run_dir, wiki, output_harness, run_id))
    updated.extend(project_report(run_dir, wiki, output_harness, run_id))
    updated.extend(project_lifecycle_summary(skill_run_path, payload, wiki, output_harness, run_id))
    action_evidence_paths = [
        str(action.get("evidence_path") or "")
        for action in (payload.get("outputs", {}).get("skill_run", {}).get("actions") or [])
        if isinstance(action, dict) and str(action.get("evidence_path") or "").strip()
    ]
    updated.extend(project_graph(
        run_dir,
        wiki,
        output_harness,
        run_id,
        action_evidence_paths=action_evidence_paths,
    ))
    updated.extend(rebuild_index(workspace, run_id))

    updated_unique = []
    seen: set[Path] = set()
    for path in updated:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            updated_unique.append(path)

    return {
        "workspace_root": artifact_path(workspace),
        "wiki_root": artifact_path(wiki),
        "solar_managed_run_dir": artifact_path(run_dir),
        "updated_count": len(updated_unique),
        "updated_paths": [artifact_path(path) for path in updated_unique],
        "index_path": artifact_path(wiki / "index.md"),
        "include_idea_pages": include_idea_pages,
        "policy": "human-facing workspace projection; execution logs remain Solar-managed",
    }
