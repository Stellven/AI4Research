from __future__ import annotations

import json
from pathlib import Path

from evidence import JourneyRecorder
from journey_runner import action_evidence, run_autosci, write_demo_paper, write_pdf


def _paper_payload(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _paper(payload: dict) -> dict:
    return payload.get("outputs", {}).get("paper", {}) if isinstance(payload, dict) else {}


def _boundary(payload: dict) -> dict:
    paper = _paper(payload)
    return paper.get("final_source_registration_boundary") or payload.get("outputs", {}).get("final_source_registration_boundary", {})


def _section_texts(payload: dict) -> list[str]:
    return [str(section.get("text") or "") for section in _paper(payload).get("sections", []) if isinstance(section, dict)]


def _harness_artifact(harness_dir: Path, relative_path: str | None) -> Path:
    if not relative_path:
        return harness_dir
    return harness_dir / relative_path.replace("\\", "/")


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_p22_j04_paper_ingestion(repo_root: Path, tmp_path: Path) -> None:
    rec = JourneyRecorder(repo_root, "P22-J04")
    sandbox = tmp_path / "p22-j04"
    md = write_demo_paper(sandbox / "raw" / "phase22-paper.md")
    pdf = write_pdf(
        sandbox / "raw" / "phase22-paper.pdf",
        "Verifier-Guided Skill Learning for LLM Agents\nAbstract\nMethod normalizes outputs.\nResults improve exact-match accuracy.",
    )

    first, harness_dir = run_autosci(rec, sandbox, "ingest", ["--paper", str(pdf), "--run-id", "p22-j04-pdf-first"], timeout=90)
    second, _ = run_autosci(rec, sandbox, "ingest", ["--paper", str(pdf), "--run-id", "p22-j04-pdf-repeat"], timeout=90)
    markdown, _ = run_autosci(rec, sandbox, "ingest", ["--paper", str(md), "--run-id", "p22-j04-md"], timeout=90)
    first_ev = action_evidence(first, "ingest_paper")
    second_ev = action_evidence(second, "ingest_paper")
    md_ev = action_evidence(markdown, "ingest_paper")
    for path, typ in ((first_ev, "first_pdf_research_paper"), (second_ev, "repeat_pdf_research_paper"), (md_ev, "markdown_research_paper")):
        if path:
            rec.add_artifact(path, typ)
    first_payload = _paper_payload(first_ev)
    second_payload = _paper_payload(second_ev)
    md_payload = _paper_payload(md_ev)
    first_paper = _paper(first_payload)
    second_paper = _paper(second_payload)
    md_paper = _paper(md_payload)
    title = first_paper.get("title", "")
    sections = _section_texts(first_payload)
    text_blob = " ".join([first_paper.get("abstract", ""), *sections]).lower()
    boundary = _boundary(first_payload)
    registration = boundary.get("wiki_registration", {}) if isinstance(boundary, dict) else {}
    wiki_paths = {
        key: _harness_artifact(harness_dir, registration.get(key))
        for key in ("paper_page", "graph_edges_path", "log_path", "index_path", "context_brief_path")
    }
    sidecar_paths = [_harness_artifact(harness_dir, item) for item in boundary.get("sidecar_evidence_paths", [])]
    for sidecar in sidecar_paths:
        rec.add_artifact(sidecar, f"first_pdf_{sidecar.stem}")
    rec.add_assertion("first_pdf_ingest_completed", first_payload.get("schema") == "research_paper.v1", first_payload.get("schema"))
    rec.add_assertion("title_not_empty", bool(title), title)
    rec.add_assertion(
        "abstract_or_body_extracted",
        bool(first_paper.get("abstract")) or any("Method normalizes outputs" in text for text in sections),
        {"abstract": first_paper.get("abstract"), "sections": sections},
    )
    rec.add_assertion("sections_extracted", len(sections) >= 1 and any(text.strip() for text in sections), sections)
    rec.add_assertion(
        "method_and_result_text_extracted",
        "method" in text_blob and ("result" in text_blob or "accuracy" in text_blob),
        {"text_excerpt": text_blob[:500]},
    )
    rec.add_assertion(
        "source_reference_recorded",
        bool(first_paper.get("source_ref")) and bool(first_paper.get("source_type")),
        {"source_ref": first_paper.get("source_ref"), "source_type": first_paper.get("source_type")},
    )
    rec.add_assertion(
        "source_preparation_and_parse_ready",
        bool(boundary.get("source_preparation_verified")) and bool(boundary.get("parse_quality_ready")),
        boundary,
    )
    rec.add_assertion("paper_id_recorded", bool(first_paper.get("paper_id")), first_paper.get("paper_id"))
    rec.add_assertion(
        "source_registration_boundary_recorded",
        bool(boundary.get("schema")) and bool(boundary.get("paper_id")),
        boundary,
    )
    rec.add_assertion(
        "memory_and_graph_sidecars_recorded",
        bool(boundary.get("memory_sidecar_ready")) and bool(boundary.get("graph_sidecar_ready")) and all(path.exists() for path in sidecar_paths),
        {"sidecar_paths": [str(path) for path in sidecar_paths], "boundary": boundary},
    )
    for key, path in wiki_paths.items():
        rec.add_artifact(path, f"first_pdf_wiki_{key}", required=True)
    paper_page_text = wiki_paths["paper_page"].read_text(encoding="utf-8") if wiki_paths["paper_page"].exists() else ""
    graph_edges = _jsonl(wiki_paths["graph_edges_path"])
    log_text = wiki_paths["log_path"].read_text(encoding="utf-8") if wiki_paths["log_path"].exists() else ""
    index_text = wiki_paths["index_path"].read_text(encoding="utf-8") if wiki_paths["index_path"].exists() else ""
    context_text = wiki_paths["context_brief_path"].read_text(encoding="utf-8") if wiki_paths["context_brief_path"].exists() else ""
    paper_id = str(first_paper.get("paper_id") or "")
    rec.add_assertion(
        "wiki_registration_artifacts_are_independently_usable",
        all(path.exists() and path.stat().st_size > 0 for path in wiki_paths.values())
        and paper_id in paper_page_text
        and str(title) in paper_page_text
        and any(str(edge.get("target_id") or "") == paper_id for edge in graph_edges)
        and paper_id in log_text
        and f"papers/{paper_id}.md" in index_text
        and "wiki/graph/edges.jsonl" in context_text,
        {
            "wiki_paths": {key: str(path) for key, path in wiki_paths.items()},
            "paper_page_has_id": paper_id in paper_page_text,
            "paper_page_has_title": str(title) in paper_page_text,
            "graph_target_ids": [edge.get("target_id") for edge in graph_edges],
            "log_has_id": paper_id in log_text,
            "index_has_page": f"papers/{paper_id}.md" in index_text,
            "context_links_graph": "wiki/graph/edges.jsonl" in context_text,
        },
    )
    rec.add_assertion("repeat_pdf_ingest_completed", second_payload.get("schema") == "research_paper.v1", second_payload.get("schema"))
    rec.add_assertion("markdown_ingest_completed", md_payload.get("schema") == "research_paper.v1", md_payload.get("schema"))
    rec.add_assertion(
        "repeat_pdf_same_paper_id",
        first_paper.get("paper_id") == second_paper.get("paper_id"),
        {"first": first_paper.get("paper_id"), "repeat": second_paper.get("paper_id")},
    )
    rec.add_assertion(
        "markdown_title_matches_pdf",
        bool(md_paper.get("title")) and md_paper.get("title") == first_paper.get("title"),
        {"pdf": first_paper.get("title"), "markdown": md_paper.get("title")},
    )
    rec.add_l2("Workflow", "User-Supplied Material Import", "PDF and Markdown sources were submitted through AutoSci ingest", first_ev or rec.run_dir, True)
    rec.add_l2("Workflow", "Intake Qualification", "source preparation and parse-quality boundary checks were recorded", first_ev or rec.run_dir, True)
    rec.add_l2("Workflow", "Intake Context Binding", "ingest ran in an isolated AutoSci harness workspace with source references bound to the paper", first_ev or rec.run_dir, True)
    rec.add_l2("Workflow", "Intake Provenance Registration", "paper id, source type, source ref, and native preparation provenance were recorded", first_ev or rec.run_dir, True)
    rec.add_l2("Workflow", "Real-Time Intake Deduplication & Cleaning", "repeat PDF import preserved the same paper id; cross-carrier behavior is explicitly checked", second_ev or rec.run_dir, "partial")
    rec.add_l2("Foundation", "Persistent Memory & Context Retrieval", "research memory sidecar was produced under the isolated harness", sidecar_paths[0] if sidecar_paths else harness_dir / "artifacts" / "autosci", "partial")
    rec.add_l2("Foundation", "Concept Graph Management", "research graph sidecar was produced for the ingested paper", sidecar_paths[-1] if sidecar_paths else harness_dir / "artifacts" / "autosci", "partial")
    rec.add_l2("Foundation", "Memory Graph Management", "memory and graph readiness flags were recorded in the final source-registration boundary", first_ev or rec.run_dir, "partial")
    rec.add_l2("Foundation", "Trace Graph Management", "ingest command logs, provenance, and sidecar paths provide traceable run evidence", rec.run_dir / "commands.json", "partial")
    rec.add_l2("Foundation", "Evidence, Factuality & Scientific Validity Evaluator", "schema, title, method/result text, source binding, and duplicate assertions checked factual usability", first_ev or rec.run_dir, "partial")
    limitations = []
    first_id = first_paper.get("paper_id")
    md_id = md_paper.get("paper_id")
    if first_id and md_id and first_id != md_id:
        limitations.append("PDF and Markdown imports completed, but cross-carrier deduplication produced distinct paper ids.")
    if boundary and not boundary.get("final_registration_ready"):
        missing = ", ".join(boundary.get("missing") or ["unknown registration check"])
        limitations.append(f"First PDF source registration boundary is incomplete: {missing}.")
    status = "PASS" if all(item["passed"] for item in rec.assertions) and not limitations else "PASS_WITH_KNOWN_LIMITATIONS"
    if not all(item["passed"] for item in rec.assertions):
        status = "FAIL"
    rec.finalize(status, limitations=limitations)
