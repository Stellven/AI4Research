"""report_draft node implementation."""

from __future__ import annotations

import re
from typing import Any

from .base import (
    display_path,
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    load_artifact,
    no_provider_result,
    output_path,
    provider_usage_from,
    redact_secrets,
    require_node,
    _read_bytes,
    _write_bytes,
    sha256_bytes,
    utc_now,
    validate_scoped_path,
    write_artifact,
)


def _load_synthesis(context: OperatorContext) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return load_artifact(
        context,
        schemas=("research_synthesis.evidence_synthesis.v1",),
        artifact_ids=("evidence_synthesis",),
        filenames=("evidence_synthesis.json",),
        payload_keys=("evidence_synthesis",),
        expected_node_ids=("evidence_synthesis",),
    )


def _task_contract(context: OperatorContext) -> dict[str, Any]:
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    return task_contract


def _deliverable_requirements(task_contract: dict[str, Any]) -> dict[str, Any]:
    deliverable = task_contract.get("deliverable") if isinstance(task_contract.get("deliverable"), dict) else {}
    return {
        "kind": str(deliverable.get("kind") or ""),
        "description": str(deliverable.get("description") or ""),
        "language": str(deliverable.get("language") or ""),
        "format": str(deliverable.get("format") or ""),
        "length": deliverable.get("length") or deliverable.get("length_words") or deliverable.get("target_length"),
        "artifact_expectations": [str(item) for item in deliverable.get("artifact_expectations", []) if str(item).strip()],
    }


def _normalized_heading(value: str) -> str:
    without_numbering = re.sub(r"^\s*\d+(?:\.\d+)*[.)\u3001\uff0e]?\s*", "", str(value or ""))
    without_numbering = re.sub(r"^\s*[一二三四五六七八九十]+[\u3001.)\uff0e]?\s*", "", without_numbering)
    return re.sub(r"[\W_]+", "", without_numbering.casefold())


def _dedupe_repeated_heading_sections(body: str) -> str:
    headings = list(re.finditer(r"(?m)^(#{2,6})\s+(.+?)\s*$", body))
    if not headings:
        return body
    remove_ranges: list[tuple[int, int]] = []
    seen: set[tuple[int, str]] = set()
    for index, heading in enumerate(headings):
        level = len(heading.group(1))
        normalized = _normalized_heading(heading.group(2))
        key = (level, normalized)
        if not normalized or key not in seen:
            seen.add(key)
            continue
        section_end = len(body)
        for following in headings[index + 1:]:
            if len(following.group(1)) <= level:
                section_end = following.start()
                break
        remove_ranges.append((heading.start(), section_end))
    if not remove_ranges:
        return body
    merged: list[tuple[int, int]] = []
    for start, end in remove_ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    compact_parts: list[str] = []
    cursor = 0
    for start, end in merged:
        compact_parts.append(body[cursor:start])
        cursor = end
    compact_parts.append(body[cursor:])
    compact = "".join(compact_parts)
    return re.sub(r"\n{3,}", "\n\n", compact).strip()


_LIMITATIONS_HEADING_RE = re.compile(
    r"(?im)^(#{2,6})\s*[^\r\n]*(?:limitations?\b|\u5c40\u9650|\u9650\u5236|\u4e0d\u8db3)[^\r\n]*$"
)
_SOURCES_HEADING_RE = re.compile(
    r"(?im)^#{2,6}\s*[^\r\n]*(?:sources?\b|references?\b|\u53c2\u8003\u8d44\u6599|\u8d44\u6599\u6765\u6e90|\u53c2\u8003\u6765\u6e90)[^\r\n]*$"
)


def _merge_limitations_section(body: str, limitations: list[str], heading: str) -> str:
    """Put every recorded limitation into ONE limitations section.

    Appending a second "## Limitations" is what produced the duplicate heading a
    reviewer flags as a critical finding, and because this ran on every revision
    attempt the operator recreated the duplicate each time -- so no revision
    could ever clear it. When the body already has a limitations section the
    missing entries are inserted into it; only otherwise is a section created.
    """
    wanted = list(dict.fromkeys(item for item in limitations if item))
    if not wanted:
        return body
    normalized_body = " ".join(body.split()).casefold()
    missing = [item for item in wanted if " ".join(item.split()).casefold() not in normalized_body]

    match = _LIMITATIONS_HEADING_RE.search(body)
    if match is None:
        if not missing:
            return body
        return body + f"\n\n## {heading}\n\n" + "\n".join(f"- {item}" for item in missing)
    if not missing:
        return body

    # Insert at the end of the existing section, before the next heading of the
    # same or higher level, so the entries land under the right heading rather
    # than at the end of the document.
    level = len(match.group(1))
    section_end = len(body)
    for following in re.finditer(r"(?m)^(#{1,6})\s+", body[match.end():]):
        if len(following.group(1)) <= level:
            section_end = match.end() + following.start()
            break
    head, tail = body[:section_end].rstrip(), body[section_end:]
    addition = "\n".join(f"- {item}" for item in missing)
    return f"{head}\n{addition}\n{tail}" if tail else f"{head}\n{addition}"


def _body_has_substantive_section(raw_body: str, title: str, section_body: str) -> bool:
    normalized_body = " ".join(raw_body.split()).casefold()
    normalized_section = " ".join(section_body.split()).casefold()
    if normalized_section and normalized_section in normalized_body:
        return True

    target = _normalized_heading(title)
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", raw_body))
    for index, heading in enumerate(headings):
        if _normalized_heading(heading.group(2)) != target:
            continue
        level = len(heading.group(1))
        section_end = len(raw_body)
        for following in headings[index + 1:]:
            if len(following.group(1)) <= level:
                section_end = following.start()
                break
        candidate = raw_body[heading.end():section_end]
        if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", candidate):
            return True
    return False


def _normalize_report(response: dict[str, Any], claim_ids: set[str]) -> dict[str, Any]:
    report = response.get("report") if isinstance(response.get("report"), dict) else response
    conclusions = report.get("conclusions") if isinstance(report.get("conclusions"), list) else response.get("conclusions")
    conclusions = conclusions if isinstance(conclusions, list) else []
    normalized_conclusions: list[dict[str, Any]] = []
    for index, item in enumerate(conclusions):
        if not isinstance(item, dict):
            continue
        evidence_ids = [str(value) for value in item.get("evidence_ids", []) if str(value).strip()]
        if not evidence_ids:
            raise ResearchOperatorError("Every major report conclusion must include evidence_ids", error_type="unsupported_report_claim")
        invalid = sorted(set(evidence_ids) - claim_ids)
        if invalid:
            # Name what was expected. The usual cause is a SOURCE id cited where
            # a CLAIM id belongs, because grounded_claims carry their own
            # `evidence_ids` of source ids under the same field name.
            raise ResearchOperatorError(
                "Report conclusion references unknown synthesis evidence: "
                f"{', '.join(invalid)}. Conclusions must cite claim_id values from "
                f"evidence_synthesis, one of: {', '.join(sorted(claim_ids)) or '<none>'}",
                error_type="unsupported_report_claim",
            )
        normalized_conclusions.append({
            "conclusion_id": str(item.get("conclusion_id") or f"conclusion-{index + 1:03d}"),
            "text": str(item.get("text") or ""),
            "evidence_ids": evidence_ids,
        })
    if not normalized_conclusions:
        raise ResearchOperatorError("model_generate returned no traceable report conclusions", error_type="provider_contract")
    title = str(report.get("title") or "Research synthesis draft").strip()
    sections: list[dict[str, str]] = []
    raw_sections = report.get("sections") if isinstance(report.get("sections"), list) else response.get("sections")
    for index, item in enumerate(raw_sections or [], start=1):
        if not isinstance(item, dict):
            continue
        section_body = str(item.get("body") or item.get("content") or item.get("text") or "").strip()
        if not section_body:
            continue
        sections.append({
            "title": str(item.get("title") or f"Section {index}").strip(),
            "body": section_body,
        })
    raw_body = str(report.get("body") or report.get("markdown") or "").strip()
    if not raw_body and not sections:
        raise ResearchOperatorError("model_generate returned an empty report body", error_type="provider_contract")
    body_parts: list[str] = []
    if raw_body:
        has_markdown_heading = bool(re.search(r"(?m)^#{1,6}\s+", raw_body))
        has_level_one_heading = bool(re.search(r"(?m)^#\s+", raw_body))
        if has_markdown_heading:
            body_parts.append(raw_body if has_level_one_heading else f"# {title}\n\n{raw_body}")
        else:
            body_parts.append(f"# {title}\n\n## Summary\n\n{raw_body}")
    else:
        body_parts.append(f"# {title}")
    # A references heading is the publication boundary promised by the model
    # contract. When it already exists, the Markdown body is authoritative and
    # the parallel ``sections`` array remains metadata only. Appending
    # differently titled section summaries after References produced stitched
    # reports whose complete body was followed by a second compressed report.
    if not _SOURCES_HEADING_RE.search(raw_body):
        body_parts.extend(
            f"## {section['title']}\n\n{section['body']}"
            for section in sections
            if not _body_has_substantive_section(raw_body, section["title"], section["body"])
        )
    body = "\n\n".join(body_parts)
    body = _dedupe_repeated_heading_sections(body)
    missing_conclusions = [
        item for item in normalized_conclusions
        if " ".join(str(item["text"]).split()).casefold() not in " ".join(body.split()).casefold()
    ]
    cjk_report = bool(re.search(r"[\u4e00-\u9fff]", title + body))
    if missing_conclusions:
        conclusion_heading = "结论" if cjk_report else "Conclusions"
        evidence_label = "证据" if cjk_report else "Evidence"
        body += f"\n\n## {conclusion_heading}\n\n" + "\n".join(
            f"- {item['text']} {evidence_label}: {', '.join(item['evidence_ids'])}."
            for item in missing_conclusions
        )
    if not re.search(r"(?im)^##\s+[^\r\n]*(?:methods?\b|\u65b9\u6cd5|\u65b9\u6cd5\u8bba)[^\r\n]*$", body):
        method_heading = "æ–¹æ³•" if cjk_report else "Evidence Method"
        method_body = (
            "æœ¬æŠ¥å‘Šåªä½¿ç”¨ evidence_synthesis ä¸­å·²è¿½æº¯çš„ä¸»è¦åˆ¤æ–­ï¼›"
            "ä»»ä½•è¶…å‡ºæ¥æºç›´æŽ¥è¡¨è¿°çš„å»ºè®®ã€æƒè¡¡æˆ–äº§ä¸šå«ä¹‰å‡åº”ç†è§£ä¸ºæ¥æºçº¦æŸä¸‹çš„ç»¼åˆæŽ¨æ–­ã€‚"
            if cjk_report
            else "This report uses only the traceable claims in evidence_synthesis; any recommendation, trade-off, or operational implication beyond direct source wording is a source-bounded synthesis."
        )
        body += f"\n\n## {method_heading}\n\n{method_body}"
    limitations = [str(item).strip() for item in response.get("limitations") or [] if str(item).strip()]
    if limitations:
        limitation_heading = "局限" if cjk_report else "Limitations"
        body = _merge_limitations_section(body, limitations, limitation_heading)
    return {
        "title": title,
        "body": body,
        "sections": sections,
        "conclusions": normalized_conclusions,
    }


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "report_draft")
    model_generate = context.services.get("model_generate")
    if model_generate is None:
        return no_provider_result(context, "model_generate")
    synthesis, synthesis_ref = _load_synthesis(context)
    claims = [item for item in synthesis.get("claims", []) if isinstance(item, dict)]
    if not claims:
        return build_node_result(
            context,
            status="blocked",
            errors=[{"error_id": "report_draft.no_claims", "error_type": "missing_synthesis", "message": "No synthesized claims were available for report drafting."}],
            limitations=["Report draft only consumes evidence_synthesis output."],
        )
    task_contract = _task_contract(context)
    deliverable_requirements = _deliverable_requirements(task_contract)
    response = model_generate(
        node_id="report_draft",
        task_contract=task_contract,
        deliverable_requirements=deliverable_requirements,
        evidence_synthesis=synthesis,
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError("model_generate service must return a JSON object", error_type="provider_contract")
    response = dict(response)
    response["limitations"] = list(dict.fromkeys([
        *[str(item) for item in synthesis.get("limitations", []) if str(item).strip()],
        *[str(item) for item in response.get("limitations", []) if str(item).strip()],
    ]))
    claim_ids = {str(item.get("claim_id")) for item in claims if item.get("claim_id")}
    report = _normalize_report(response, claim_ids)
    usage = provider_usage_from(response, usage_kind="llm")
    limitations = [str(item) for item in response.get("limitations", []) if str(item).strip()]
    artifact_payload = {
        "schema": "research_synthesis.report_draft.v1",
        "node_id": "report_draft",
        "created_at": utc_now(),
        "deliverable_requirements": deliverable_requirements,
        "report": report,
        "claim_source_lineage": {
            str(item.get("claim_id")): [str(source_id) for source_id in item.get("evidence_ids", []) if str(source_id).strip()]
            for item in claims
            if item.get("claim_id")
        },
        "evidence_lineage": [
            "evidence_synthesis",
            *[str(value) for value in (synthesis.get("input_lineage") or {}).values() if str(value).strip()],
        ],
        "input_artifact_hashes": {
            "evidence_synthesis": str((synthesis_ref or {}).get("sha256") or ""),
        },
        "writer_usage": usage,
        "limitations": limitations,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "report_draft.json"),
        artifact_payload,
        artifact_id="report_draft",
        schema="research_synthesis.report_draft.v1",
    )
    report_path = validate_scoped_path(
        output_path(context, "report.md"),
        context.write_scope,
        workspace_root=context.workspace_root,
    )
    safe_body = str(redact_secrets(report["body"], context.secret_refs, context.secret_values))
    _write_bytes(report_path, (safe_body.rstrip() + "\n").encode("utf-8"))
    report_digest = sha256_bytes(_read_bytes(report_path))
    report_artifact = {
        "artifact_id": "report_markdown",
        "path": display_path(report_path, context.workspace_root),
        "schema": "text/markdown",
        "sha256": report_digest,
    }
    report_hash = {"hash_id": "report_markdown", "algorithm": "sha256", "value": report_digest}
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact, report_artifact],
        evidence=[
            evidence_ref("report_draft.traceable", "traceable_report_draft", "Report draft conclusions are linked to synthesis evidence.", artifact["artifact_id"]),
            evidence_ref("report_draft.usable_markdown", "usable_report", "A non-empty Markdown report was written by the production report operator.", report_artifact["artifact_id"]),
        ],
        hashes=[hash_record, report_hash],
        model_provider_usage=usage,
        limitations=limitations,
    )
