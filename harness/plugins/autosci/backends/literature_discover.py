"""Solar-native literature discovery backend for AutoSci `/discover`."""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import requests

    HAS_REQUESTS = True
except ImportError:  # pragma: no cover - requests is expected in AutoSci envs
    requests = None
    HAS_REQUESTS = False


S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"
S2_RECOMMENDATIONS_URL = "https://api.semanticscholar.org/recommendations/v1"
S2_FIELDS = (
    "paperId,title,abstract,authors,year,citationCount,influentialCitationCount,"
    "venue,publicationTypes,fieldsOfStudy,tldr,externalIds,url"
)
S2_FLAT_FIELDS = (
    "paperId,title,abstract,authors,year,citationCount,influentialCitationCount,"
    "venue,publicationTypes,fieldsOfStudy,externalIds,url"
)
ARXIV_ID_RE = re.compile(
    r"(?:arxiv:|arxiv_id:|arxiv\.org/(?:abs|pdf)/)?"
    r"([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?|[a-z\-]+(?:\.[A-Z]{2})?/[0-9]{7}(?:v[0-9]+)?)",
    re.IGNORECASE,
)
CURRENT_YEAR = 2026


def normalize_arxiv_id(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    value = value.removeprefix("ARXIV:").removeprefix("arxiv:")
    return re.sub(r"v\d+$", "", value, flags=re.IGNORECASE)


def extract_arxiv_id(text: str) -> str:
    match = ARXIV_ID_RE.search(str(text or ""))
    if match:
        return normalize_arxiv_id(match.group(1))
    return ""


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "discover"


def _normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^0-9a-zA-Z\s.+/_-]", " ", str(text or "").lower()).split())


def _tokens(text: str) -> list[str]:
    stop = {"a", "an", "and", "are", "as", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with"}
    return [token for token in re.split(r"[^0-9a-zA-Z.+/_-]+", _normalize_text(text)) if len(token) >= 3 and token not in stop]


def _resolve_path(path_text: str | Path, workspace_root: Path, repository_root: Path | None = None) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    for root in [workspace_root, repository_root or workspace_root]:
        candidate = root / path
        if candidate.exists():
            return candidate
    return workspace_root / path


def _display_path(path: Path, workspace_root: Path, repository_root: Path | None = None) -> str:
    for root in [workspace_root, repository_root or workspace_root]:
        try:
            return str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            continue
    return str(path)


def _read_text(path: Path, limit: int = 120_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _title_from_page(text: str, fallback: str) -> str:
    for line in str(text or "").splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()[:300]
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"')[:300]
    return fallback


def scan_wiki_papers(wiki_root: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    papers_dir = wiki_root / "papers"
    if not papers_dir.exists():
        return []
    pages: list[dict[str, Any]] = []
    for path in sorted(papers_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        text = _read_text(path)
        arxiv_id = extract_arxiv_id(text)
        if not arxiv_id:
            continue
        title = _title_from_page(text, path.stem.replace("-", " ").title())
        pages.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "path": path,
                "mtime": path.stat().st_mtime,
            }
        )
        if len(pages) >= limit:
            break
    return pages


def _s2_headers() -> dict[str, str]:
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    return {"x-api-key": api_key} if api_key else {}


def _s2_request(method: str, url: str, *, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None) -> Any:
    if not HAS_REQUESTS:
        raise RuntimeError("requests unavailable")
    response = requests.request(
        method,
        url,
        params=params or {},
        json=json_body,
        headers=_s2_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _bare_arxiv_id(value: str) -> str:
    return normalize_arxiv_id(value)


def _s2_search(query: str, limit: int) -> list[dict[str, Any]]:
    data = _s2_request(
        "GET",
        f"{S2_BASE_URL}/paper/search",
        params={"query": query, "limit": max(limit, 1), "fields": S2_FIELDS},
    )
    return list(data.get("data") or [])


def _s2_citations(arxiv_id: str, limit: int) -> list[dict[str, Any]]:
    data = _s2_request(
        "GET",
        f"{S2_BASE_URL}/paper/ARXIV:{_bare_arxiv_id(arxiv_id)}/citations",
        params={"limit": max(limit, 1), "fields": f"isInfluential,{S2_FLAT_FIELDS}"},
    )
    out: list[dict[str, Any]] = []
    for item in data.get("data") or []:
        paper = item.get("citingPaper") or {}
        if paper:
            paper["_is_influential_edge"] = bool(item.get("isInfluential"))
            out.append(paper)
    return out


def _s2_references(arxiv_id: str, limit: int) -> list[dict[str, Any]]:
    data = _s2_request(
        "GET",
        f"{S2_BASE_URL}/paper/ARXIV:{_bare_arxiv_id(arxiv_id)}/references",
        params={"limit": max(limit, 1), "fields": f"isInfluential,{S2_FLAT_FIELDS}"},
    )
    out: list[dict[str, Any]] = []
    for item in data.get("data") or []:
        paper = item.get("citedPaper") or {}
        if paper:
            paper["_is_influential_edge"] = bool(item.get("isInfluential"))
            out.append(paper)
    return out


def _normalize_s2_id(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith(("ARXIV:", "arxiv:")):
        return f"ARXIV:{_bare_arxiv_id(value)}"
    if value and value[0].isdigit() and "." in value:
        return f"ARXIV:{value}"
    return value


def _s2_recommend(positive_ids: list[str], negative_ids: list[str], limit: int) -> list[dict[str, Any]]:
    positive = [_normalize_s2_id(item) for item in positive_ids if item]
    negative = [_normalize_s2_id(item) for item in negative_ids if item]
    if not positive:
        return []
    if len(positive) == 1 and not negative:
        data = _s2_request(
            "GET",
            f"{S2_RECOMMENDATIONS_URL}/papers/forpaper/{positive[0]}",
            params={"limit": max(limit, 1), "fields": S2_FLAT_FIELDS},
        )
    else:
        data = _s2_request(
            "POST",
            f"{S2_RECOMMENDATIONS_URL}/papers",
            params={"limit": max(limit, 1), "fields": S2_FLAT_FIELDS},
            json_body={"positivePaperIds": positive, "negativePaperIds": negative},
        )
    return list(data.get("recommendedPapers") or [])


def _candidate_from_raw(raw: dict[str, Any], *, source: str, anchor: str = "") -> dict[str, Any]:
    external = raw.get("externalIds") if isinstance(raw.get("externalIds"), dict) else {}
    arxiv_id = normalize_arxiv_id(str(raw.get("arxiv_id") or external.get("ArXiv") or external.get("arXiv") or ""))
    paper_id = str(raw.get("paperId") or raw.get("s2_id") or "")
    title = str(raw.get("title") or "").strip()
    if not title:
        return {}
    tldr = raw.get("tldr")
    tldr_text = tldr.get("text") if isinstance(tldr, dict) else str(tldr or "")
    candidate_id = f"arxiv:{arxiv_id}" if arxiv_id else f"s2:{paper_id}" if paper_id else f"title:{slugify(title)}"
    authors = raw.get("authors") if isinstance(raw.get("authors"), list) else []
    return {
        "candidate_id": candidate_id,
        "paperId": paper_id,
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": str(raw.get("abstract") or ""),
        "tldr": tldr_text,
        "year": raw.get("year"),
        "venue": str(raw.get("venue") or ""),
        "authors": [str(item.get("name") or "") for item in authors if isinstance(item, dict) and item.get("name")],
        "citation_count": int(raw.get("citationCount") or 0),
        "influential_citation_count": int(raw.get("influentialCitationCount") or 0),
        "fields_of_study": list(raw.get("fieldsOfStudy") or []),
        "publication_types": list(raw.get("publicationTypes") or []),
        "url": str(raw.get("url") or ""),
        "source_channels": [source],
        "anchor_ids": [anchor] if anchor else [],
        "is_influential_edge": bool(raw.get("_is_influential_edge")),
        "fetch_status": "not_requested",
    }


def _candidate_key(candidate: dict[str, Any]) -> str:
    if candidate.get("arxiv_id"):
        return f"arxiv:{candidate['arxiv_id']}"
    if candidate.get("paperId"):
        return f"s2:{candidate['paperId']}"
    return f"title:{_normalize_text(candidate.get('title', ''))}"


def _merge_candidate(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    for channel in incoming.get("source_channels") or []:
        if channel not in existing["source_channels"]:
            existing["source_channels"].append(channel)
    for anchor in incoming.get("anchor_ids") or []:
        if anchor and anchor not in existing.setdefault("anchor_ids", []):
            existing["anchor_ids"].append(anchor)
    for key in ("abstract", "tldr", "venue", "url"):
        if not existing.get(key) and incoming.get(key):
            existing[key] = incoming[key]
    for key in ("citation_count", "influential_citation_count"):
        existing[key] = max(int(existing.get(key) or 0), int(incoming.get(key) or 0))
    existing["is_influential_edge"] = bool(existing.get("is_influential_edge") or incoming.get("is_influential_edge"))


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not candidate:
            continue
        key = _candidate_key(candidate)
        if key in merged:
            _merge_candidate(merged[key], candidate)
        else:
            merged[key] = candidate
    return list(merged.values())


def _known_arxiv_ids(wiki_root: Path) -> set[str]:
    ids = set()
    papers_dir = wiki_root / "papers"
    if not papers_dir.exists():
        return ids
    for path in papers_dir.glob("*.md"):
        arxiv_id = extract_arxiv_id(_read_text(path, limit=30_000))
        if arxiv_id:
            ids.add(arxiv_id)
    return ids


def _score_candidate(candidate: dict[str, Any], query_terms: list[str]) -> float:
    text = f"{candidate.get('title', '')} {candidate.get('abstract', '')} {candidate.get('tldr', '')}"
    candidate_terms = set(_tokens(text))
    overlap = len(set(query_terms) & candidate_terms) / max(len(set(query_terms)), 1) if query_terms else 0.0
    year = candidate.get("year")
    try:
        freshness = max(0.0, min(1.0, 1.0 - (CURRENT_YEAR - int(year)) / 12.0)) if year else 0.35
    except (TypeError, ValueError):
        freshness = 0.35
    citations = min(math.log1p(int(candidate.get("citation_count") or 0)) / math.log1p(2000), 1.0)
    channels = min(len(candidate.get("source_channels") or []) / 3.0, 1.0)
    influential = 0.15 if candidate.get("is_influential_edge") else 0.0
    return round(0.45 * overlap + 0.2 * freshness + 0.2 * citations + 0.15 * channels + influential, 4)


def _finalize_candidates(
    candidates: list[dict[str, Any]],
    *,
    wiki_root: Path,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    known_arxiv = _known_arxiv_ids(wiki_root)
    query_terms = _tokens(query)
    finalized: list[dict[str, Any]] = []
    for candidate in _dedupe_candidates(candidates):
        arxiv_id = str(candidate.get("arxiv_id") or "")
        dedup_status = "known" if arxiv_id and arxiv_id in known_arxiv else "new" if arxiv_id else "unknown"
        if dedup_status == "known":
            continue
        score = _score_candidate(candidate, query_terms)
        channels = ", ".join(candidate.get("source_channels") or ["unknown"])
        rationale_bits = [f"source={channels}"]
        if candidate.get("anchor_ids"):
            rationale_bits.append(f"anchors={len(candidate['anchor_ids'])}")
        if candidate.get("is_influential_edge"):
            rationale_bits.append("influential anchor edge")
        if candidate.get("citation_count"):
            rationale_bits.append(f"citations={candidate['citation_count']}")
        if candidate.get("year"):
            rationale_bits.append(f"year={candidate['year']}")
        candidate.update(
            {
                "ranking_score": score,
                "ranking_rationale": "; ".join(rationale_bits),
                "dedup_status": dedup_status,
                "fetch_status": candidate.get("fetch_status") or "not_requested",
                "source_ref": candidate.get("url") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else str(candidate.get("paperId") or "")),
            }
        )
        finalized.append(candidate)
    finalized.sort(key=lambda item: item.get("ranking_score", 0), reverse=True)
    return finalized[:limit]


def _paper_copilot_url(venue: str, year: int) -> str:
    canonical = {"neurips": "nips"}.get(str(venue).lower(), str(venue).lower())
    return f"https://raw.githubusercontent.com/papercopilot/paperlists/main/{canonical}/{canonical}{year}.json"


def _venue_candidates(venue: str, year: int, limit: int) -> list[dict[str, Any]]:
    url = _paper_copilot_url(venue, year)
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected Paper Copilot response shape: {type(payload).__name__}")
    out: list[dict[str, Any]] = []
    for item in payload[: max(limit * 4, limit)]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        arxiv_id = extract_arxiv_id(json.dumps(item, ensure_ascii=False))
        out.append(
            {
                "candidate_id": f"arxiv:{arxiv_id}" if arxiv_id else f"title:{slugify(title)}",
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": str(item.get("abstract") or item.get("summary") or ""),
                "year": year,
                "venue": venue,
                "source_channels": ["paper_copilot"],
                "fetch_status": "not_requested",
                "source_ref": str(item.get("url") or item.get("paper_url") or ""),
                "citation_count": int(item.get("citations") or 0) if str(item.get("citations") or "0").isdigit() else 0,
            }
        )
    return out


def discover_literature(
    *,
    query: str = "",
    mode: str = "",
    anchors: list[str] | None = None,
    negative_ids: list[str] | None = None,
    venue: str = "",
    year: int | None = None,
    limit: int = 10,
    wiki_root: Path,
    workspace_root: Path,
    repository_root: Path | None = None,
    allow_network_fetch: bool = True,
    no_citation_expand: bool = False,
    fixture_fallback: bool = False,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 10), 50))
    anchors = [normalize_arxiv_id(item) or str(item) for item in anchors or [] if str(item).strip()]
    negative_ids = [normalize_arxiv_id(item) or str(item) for item in negative_ids or [] if str(item).strip()]
    wiki_root = wiki_root.resolve()
    warnings: list[str] = []
    artifacts: list[dict[str, str]] = []
    candidate_raw: list[dict[str, Any]] = []

    if fixture_fallback and not mode:
        return {
            "query": query or "solar-native scientific evidence adapters",
            "mode": "fixture",
            "limit": limit,
            "candidates": [
                {
                    "candidate_id": "candidate-autosci-fixture-paper",
                    "title": "AutoSci Adapter Fixture Paper",
                    "source_channels": ["local_fixture"],
                    "ranking_score": 1.0,
                    "ranking_rationale": "Fixture-mode candidate matches the requested Solar evidence adapter smoke test.",
                    "dedup_status": "known",
                    "fetch_status": "fetched",
                    "source_ref": "plugins/autosci/tests/fixtures/sample_paper.md",
                }
            ],
            "status": "completed",
            "limitations": ["Fixture discovery uses local candidates, not live literature search."],
            "artifacts": [],
        }

    if not mode:
        if anchors:
            mode = "anchors"
        elif query:
            mode = "topic"
        elif venue:
            mode = "venue"
        else:
            mode = "wiki"

    if mode == "wiki":
        seed_pages = scan_wiki_papers(wiki_root, limit=5)
        anchors = [item["arxiv_id"] for item in seed_pages]
        if not query and seed_pages:
            query = " ".join(item["title"] for item in seed_pages[:3])
        artifacts.extend(
            {"type": "wiki_seed_paper", "path": _display_path(item["path"], workspace_root, repository_root)}
            for item in seed_pages
        )
        if not anchors:
            return {
                "query": query or "from-wiki",
                "mode": mode,
                "limit": limit,
                "candidates": [],
                "status": "inconclusive",
                "limitations": [f"Wiki mode found no anchorable arXiv papers under {wiki_root}."],
                "artifacts": artifacts,
            }

    if mode == "venue" and (not venue or not year):
        return {
            "query": query or "from-venue",
            "mode": mode,
            "limit": limit,
            "candidates": [],
            "status": "failed",
            "limitations": ["Venue mode requires both --venue and --year."],
            "artifacts": artifacts,
        }

    if not allow_network_fetch:
        return {
            "query": query or ", ".join(anchors) or "from-wiki",
            "mode": mode,
            "limit": limit,
            "anchors": anchors,
            "candidates": [],
            "status": "inconclusive",
            "limitations": ["Network discovery disabled; no synthetic literature candidates were emitted."],
            "artifacts": artifacts,
        }

    if not HAS_REQUESTS and mode != "venue":
        return {
            "query": query or ", ".join(anchors) or "from-wiki",
            "mode": mode,
            "limit": limit,
            "anchors": anchors,
            "candidates": [],
            "status": "inconclusive",
            "limitations": ["requests is unavailable; Semantic Scholar discovery could not run."],
            "artifacts": artifacts,
        }

    try:
        if mode == "topic":
            for raw in _s2_search(query, max(limit * 2, limit)):
                candidate_raw.append(_candidate_from_raw(raw, source="search_s2"))
        elif mode in {"anchors", "wiki"}:
            for anchor in anchors:
                try:
                    for raw in _s2_recommend([anchor], negative_ids, max(limit * 2, limit)):
                        candidate_raw.append(_candidate_from_raw(raw, source="recommend", anchor=anchor))
                except Exception as exc:
                    warnings.append(f"recommend failed for {anchor}: {exc}")
                if not no_citation_expand:
                    for channel, fetcher in (("references", _s2_references), ("citations", _s2_citations)):
                        try:
                            for raw in fetcher(anchor, max(limit, 10)):
                                candidate_raw.append(_candidate_from_raw(raw, source=channel, anchor=anchor))
                        except Exception as exc:
                            warnings.append(f"{channel} failed for {anchor}: {exc}")
                time.sleep(0.05)
        elif mode == "venue":
            candidate_raw.extend(_venue_candidates(venue, int(year or 0), limit))
            query = query or f"{venue} {year}"
        else:
            return {
                "query": query or "unknown",
                "mode": mode,
                "limit": limit,
                "candidates": [],
                "status": "failed",
                "limitations": [f"Unsupported discovery mode: {mode}"],
                "artifacts": artifacts,
            }
    except Exception as exc:
        return {
            "query": query or ", ".join(anchors) or "from-wiki",
            "mode": mode,
            "limit": limit,
            "anchors": anchors,
            "candidates": [],
            "status": "inconclusive",
            "limitations": [f"Discovery source failed: {exc}", *warnings],
            "artifacts": artifacts,
        }

    candidates = _finalize_candidates(candidate_raw, wiki_root=wiki_root, query=query or " ".join(anchors), limit=limit)
    status = "completed" if candidates else "inconclusive"
    limitations = warnings[:]
    if not candidates:
        limitations.append("Discovery returned no new candidates after wiki deduplication and source filtering.")
    return {
        "query": query or ", ".join(anchors) or "from-wiki",
        "mode": mode,
        "limit": limit,
        "anchors": anchors,
        "negative_ids": negative_ids,
        "venue": venue,
        "year": year,
        "candidates": candidates,
        "status": status,
        "limitations": limitations or ["Live literature discovery completed; candidates still require human review before ingest."],
        "artifacts": artifacts,
    }
