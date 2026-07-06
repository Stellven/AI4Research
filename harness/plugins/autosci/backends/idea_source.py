"""Ground Solar AutoSci ideation in wiki and discovery evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _read_text(path: Path, *, limit: int = 12000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _slug(path: Path) -> str:
    return path.stem.replace(" ", "-").lower()


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _title_from_text(path: Path, text: str) -> str:
    fm = _frontmatter(text)
    if fm.get("title"):
        return fm["title"]
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def _first_paragraph(text: str) -> str:
    body = re.sub(r"^---.*?---", "", text, flags=re.S).strip()
    body = re.sub(r"^# .*$", "", body, flags=re.M).strip()
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", body) if chunk.strip()]
    if not chunks:
        return ""
    return re.sub(r"\s+", " ", chunks[0])[:500]


def _tokens(value: str) -> set[str]:
    stop_words = {
        "about",
        "agent",
        "based",
        "between",
        "evidence",
        "from",
        "idea",
        "method",
        "paper",
        "research",
        "that",
        "this",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 4 and token not in stop_words
    }


def _unique_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _is_markdown(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".md", ".markdown"}


def _wiki_roots(inputs: dict[str, Any], workspace_root: Path, repository_root: Path) -> list[Path]:
    roots: list[Path] = []
    raw = str(inputs.get("wiki_root") or "").strip()
    if raw:
        path = Path(raw)
        roots.append(path if path.is_absolute() else workspace_root / path)
    roots.extend(
        [
            workspace_root / "artifacts" / "autosci" / "workspace" / "wiki",
            workspace_root / "wiki",
            repository_root / "harness" / "artifacts" / "autosci" / "workspace" / "wiki",
        ]
    )
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        out.append(root)
    return out


def _load_wiki_sources(
    inputs: dict[str, Any],
    workspace_root: Path,
    repository_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sources: list[dict[str, Any]] = []
    failed_ideas: list[dict[str, Any]] = []
    active_ideas: list[dict[str, Any]] = []
    for root in _wiki_roots(inputs, workspace_root, repository_root):
        for group in ("papers", "methods", "concepts", "topics", "ideas"):
            for path in sorted((root / group).glob("*.md")):
                if not _is_markdown(path):
                    continue
                text = _read_text(path)
                if not text:
                    continue
                fm = _frontmatter(text)
                source = {
                    "id": f"wiki:{group}/{_slug(path)}",
                    "kind": group.rstrip("s"),
                    "title": _title_from_text(path, text),
                    "summary": _first_paragraph(text),
                    "path": str(path),
                    "status": fm.get("status", ""),
                    "failure_reason": fm.get("failure_reason", ""),
                }
                sources.append(source)
                if group == "ideas":
                    if source["status"] == "failed":
                        failed_ideas.append(source)
                    else:
                        active_ideas.append(source)
        for rel in ("graph/open_questions.md", "graph/context_brief.md"):
            path = root / rel
            text = _read_text(path)
            if text:
                sources.append(
                    {
                        "id": f"wiki:{rel}",
                        "kind": "graph",
                        "title": path.stem.replace("_", " ").title(),
                        "summary": _first_paragraph(text) or text[:500],
                        "path": str(path),
                        "status": "",
                        "failure_reason": "",
                    }
                )
    return sources, failed_ideas, active_ideas


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _discovery_paths(inputs: dict[str, Any], workspace_root: Path) -> list[Path]:
    paths: list[Path] = []
    for key in ("discovery_evidence", "latest_discovery_evidence"):
        raw = inputs.get(key)
        values = raw if isinstance(raw, list) else [raw] if raw else []
        for value in values:
            path = Path(str(value))
            paths.append(path if path.is_absolute() else workspace_root / path)
    runs_root = workspace_root / "artifacts" / "autosci" / "runs"
    if runs_root.exists():
        paths.extend(sorted(runs_root.glob("*/literature_discovery.json"), key=lambda item: item.stat().st_mtime, reverse=True))
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        out.append(path)
    return out


def _load_discovery_sources(inputs: dict[str, Any], workspace_root: Path) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for path in _discovery_paths(inputs, workspace_root):
        payload = _load_json(path)
        outputs = payload.get("outputs") if isinstance(payload, dict) else {}
        candidates = outputs.get("candidates") if isinstance(outputs, dict) else []
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            title = str(candidate.get("title") or candidate.get("paper_title") or "").strip()
            if not title:
                continue
            candidate_id = str(candidate.get("paper_id") or candidate.get("id") or title)
            sources.append(
                {
                    "id": f"discovery:{candidate_id}",
                    "kind": "discovery",
                    "title": title,
                    "summary": str(candidate.get("summary") or candidate.get("abstract") or candidate.get("reason") or "")[:500],
                    "path": str(path),
                    "status": str(payload.get("status") or ""),
                    "failure_reason": "",
                }
            )
    return sources


def collect_idea_sources(
    inputs: dict[str, Any],
    *,
    workspace_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    wiki_sources, failed_ideas, active_ideas = _load_wiki_sources(inputs, workspace_root, repository_root)
    discovery_sources = _load_discovery_sources(inputs, workspace_root)
    source_mode = "mixed" if wiki_sources and discovery_sources else "discovery" if discovery_sources else "wiki" if wiki_sources else "missing"
    return {
        "wiki_sources": wiki_sources,
        "discovery_sources": discovery_sources,
        "failed_ideas": failed_ideas,
        "active_ideas": active_ideas,
        "sources": [*discovery_sources, *wiki_sources],
        "source_mode": source_mode,
    }


def _overlaps_known(candidate_title: str, ideas: list[dict[str, Any]]) -> tuple[bool, str]:
    title_tokens = _tokens(candidate_title)
    for idea in ideas:
        idea_text = f"{idea.get('title', '')} {idea.get('failure_reason', '')} {idea.get('summary', '')}"
        if title_tokens and len(title_tokens & _tokens(idea_text)) >= 2:
            return True, str(idea.get("id") or idea.get("title") or "known-idea")
    return False, ""


def _sources_of_kind(sources: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [source for source in sources if str(source.get("kind") or "") == kind]


def _candidate_status(
    title: str,
    failed_ideas: list[dict[str, Any]],
    active_ideas: list[dict[str, Any]],
) -> tuple[str, str, str]:
    duplicate, duplicate_of = _overlaps_known(title, failed_ideas)
    if duplicate:
        return "filtered", "duplicate", duplicate_of
    duplicate, duplicate_of = _overlaps_known(title, active_ideas)
    return ("filtered" if duplicate else "candidate", "duplicate" if duplicate else "new", duplicate_of)


def _apply_max_ideas_selection(ideas: list[dict[str, Any]], max_ideas: int) -> None:
    selected = 0
    for idea in ideas:
        if str(idea.get("status") or "") in {"blocked", "filtered"}:
            idea["selected_for_write"] = False
            idea["selection_rank"] = "N/A"
            continue
        if max_ideas > 0 and selected >= max_ideas:
            idea["selected_for_write"] = False
            idea["selection_rank"] = "N/A"
            idea["selection_reason"] = f"Not selected because max_ideas={max_ideas} was reached."
            continue
        selected += 1
        idea["selected_for_write"] = True
        idea["selection_rank"] = selected


def build_idea_candidates(envelope: dict[str, Any], *, workspace_root: Path, repository_root: Path) -> dict[str, Any]:
    inputs = dict(envelope.get("inputs") or {})
    topic = str(inputs.get("topic") or inputs.get("query") or inputs.get("target") or "research workflow").strip()
    try:
        max_ideas = max(0, int(inputs.get("max_ideas") or 0))
    except (TypeError, ValueError):
        max_ideas = 0
    source_bundle = collect_idea_sources(inputs, workspace_root=workspace_root, repository_root=repository_root)
    wiki_sources = list(source_bundle["wiki_sources"])
    discovery_sources = list(source_bundle["discovery_sources"])
    failed_ideas = list(source_bundle["failed_ideas"])
    active_ideas = list(source_bundle["active_ideas"])
    sources = list(source_bundle["sources"])
    if not sources:
        return {
            "status": "inconclusive",
            "ideas": [
                {
                    "idea_id": "idea-source-missing",
                    "title": "Insufficient sourced context for ideation",
                    "hypothesis": "A research idea should not be generated without wiki, discovery, or paper evidence.",
                    "approach": "Run discovery or ingest papers, then rerun ideate with wiki/discovery evidence available.",
                    "origin_evidence_ids": ["missing:wiki-or-discovery-evidence"],
                    "novelty_hypothesis": "No novelty claim is made because no source evidence was available.",
                    "source_mode": "missing",
                    "duplicate_status": "insufficient_source",
                    "status": "blocked",
                    "generation_path": "source-required",
                }
            ],
            "limitations": ["No wiki or discovery evidence was available; ideation is inconclusive."],
            "source_summary": {
                "wiki_source_count": 0,
                "discovery_source_count": 0,
                "failed_idea_count": 0,
                "active_idea_count": 0,
                "source_ids": [],
                "source_refs": [],
            },
        }

    primary = sources[0]
    secondary = sources[1] if len(sources) > 1 else sources[0]
    methods = _sources_of_kind(sources, "method")
    source_mode = str(source_bundle["source_mode"])
    title_topic = topic if topic and topic != "research workflow" else str(primary["title"])
    title = f"Close the evidence gap around {title_topic[:80]}"
    status, duplicate_status, duplicate_of = _candidate_status(title, failed_ideas, active_ideas)
    ideas = [
        {
            "idea_id": "idea-wiki-discovery-001",
            "title": title,
            "hypothesis": (
                f"Combining `{primary['title']}` with `{secondary['title']}` can expose a testable gap "
                "that is not captured by single-source reading."
            ),
            "approach": (
                "Build an experiment plan from the shared assumptions and limitations in the cited wiki/discovery "
                "sources, then compare it against the strongest baseline found in the evidence graph."
            ),
            "origin_evidence_ids": [str(primary["id"]), str(secondary["id"])],
            "novelty_hypothesis": "The candidate is grounded in current wiki/discovery evidence and targets an explicit evidence gap.",
            "grounding_summary": f"Primary source: {primary['title']}; secondary source: {secondary['title']}.",
            "source_mode": source_mode,
            "generation_path": "A:landscape-driven",
            "duplicate_status": duplicate_status,
            "duplicate_of": duplicate_of,
            "status": status,
        }
    ]
    if methods:
        method = methods[0]
        title = f"Patch a limitation in {method['title'][:72]}"
        status, duplicate_status, duplicate_of = _candidate_status(title, failed_ideas, active_ideas)
        ideas.append(
            {
                "idea_id": "idea-method-incremental-001",
                "title": title,
                "hypothesis": (
                    f"A focused improvement to `{method['title']}` can address a method limitation visible in the wiki evidence."
                ),
                "approach": (
                    "Extract the method's stated limitation or unresolved evaluation gap, implement the smallest measurable "
                    "change, and compare against the original method under the same evidence-backed task."
                ),
                "origin_evidence_ids": [str(method["id"])],
                "novelty_hypothesis": "Incremental novelty must be confirmed by external novelty search and Review LLM validation.",
                "grounding_summary": f"Incremental path grounded in method evidence: {method['title']}.",
                "source_mode": source_mode,
                "generation_path": "B:incremental",
                "duplicate_status": duplicate_status,
                "duplicate_of": duplicate_of,
                "status": status,
            }
        )
    if len(methods) >= 2:
        first, second = methods[0], methods[1]
        title = f"Combine {first['title'][:36]} with {second['title'][:36]}"
        status, duplicate_status, duplicate_of = _candidate_status(title, failed_ideas, active_ideas)
        ideas.append(
            {
                "idea_id": "idea-method-combination-001",
                "title": title,
                "hypothesis": (
                    f"The complementary assumptions of `{first['title']}` and `{second['title']}` can be combined into a stronger method."
                ),
                "approach": (
                    "Map the tradeoff profile of both methods, keep the mechanism that improves robustness, and test whether the "
                    "combined design preserves the efficiency of the simpler baseline."
                ),
                "origin_evidence_ids": [str(first["id"]), str(second["id"])],
                "novelty_hypothesis": "Combination novelty depends on external prior-work search for the same method pair.",
                "grounding_summary": f"Combination path grounded in method evidence: {first['title']} + {second['title']}.",
                "source_mode": source_mode,
                "generation_path": "C:combination",
                "duplicate_status": duplicate_status,
                "duplicate_of": duplicate_of,
                "status": status,
            }
        )
        title = f"Break a shared assumption behind {first['title'][:48]}"
        status, duplicate_status, duplicate_of = _candidate_status(title, failed_ideas, active_ideas)
        ideas.append(
            {
                "idea_id": "idea-method-innovation-001",
                "title": title,
                "hypothesis": (
                    f"`{first['title']}` and `{second['title']}` may share an assumption that can be relaxed for a new evaluation setting."
                ),
                "approach": (
                    "Extract the assumptions implicit in both method summaries, choose the assumption most exposed by current "
                    "open questions, and design an ablation that tests the relaxed assumption directly."
                ),
                "origin_evidence_ids": [str(first["id"]), str(second["id"])],
                "novelty_hypothesis": "Innovation-path novelty must be validated against recent literature and adversarial review.",
                "grounding_summary": f"Innovation path grounded in shared method evidence: {first['title']} / {second['title']}.",
                "source_mode": source_mode,
                "generation_path": "D:innovation",
                "duplicate_status": duplicate_status,
                "duplicate_of": duplicate_of,
                "status": status,
            }
        )
    if len(sources) >= 3:
        third = sources[2]
        title = f"Stress-test method transfer from {primary['title'][:48]}"
        status, duplicate_status, duplicate_of = _candidate_status(title, failed_ideas, active_ideas)
        ideas.append(
            {
                "idea_id": "idea-wiki-discovery-002",
                "title": title,
                "hypothesis": (
                    f"A mechanism or limitation in `{primary['title']}` can be transferred to the context of "
                    f"`{third['title']}` and evaluated with a bounded pilot."
                ),
                "approach": (
                    "Extract the reusable mechanism from the first source, map assumptions against the third source, "
                    "and run a pilot that checks whether the transferred mechanism is compatible."
                ),
                "origin_evidence_ids": [str(primary["id"]), str(third["id"])],
                "novelty_hypothesis": "Cross-source transfer is considered novel only after novelty/review validation.",
                "grounding_summary": f"Transfer source: {primary['title']}; target context: {third['title']}.",
                "source_mode": source_mode,
                "generation_path": "E:cross-domain-transfer",
                "duplicate_status": duplicate_status,
                "duplicate_of": duplicate_of,
                "status": status,
            }
        )
    _apply_max_ideas_selection(ideas, max_ideas)
    return {
        "status": "completed",
        "ideas": ideas,
        "limitations": [
            "Ideas are source-grounded deterministic candidates; external novelty and Review LLM validation remain required.",
            "Failed idea overlap is checked with token overlap and should be reviewed by a human.",
        ],
        "source_summary": {
            "wiki_source_count": len(wiki_sources),
            "discovery_source_count": len(discovery_sources),
            "failed_idea_count": len(failed_ideas),
            "active_idea_count": len(active_ideas),
            "source_mode": source_mode,
            "source_ids": _unique_strings([str(source.get("id") or "") for source in sources]),
            "source_refs": _unique_strings([str(source.get("path") or "") for source in sources]),
            "generation_path_count": len({str(idea.get("generation_path") or "") for idea in ideas}),
            "max_ideas": max_ideas,
            "selected_for_write_count": len([idea for idea in ideas if idea.get("selected_for_write") is True]),
        },
    }
