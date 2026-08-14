"""Local novelty and review signals for Solar AutoSci ideas."""

from __future__ import annotations

import json
import os
import re
import hashlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backends.artifact_review import _review_llm_assessment
from backends.idea_source import collect_idea_sources


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


def _idea_text(idea: dict[str, Any]) -> str:
    return " ".join(
        str(idea.get(field) or "")
        for field in ("title", "hypothesis", "approach", "novelty_hypothesis", "grounding_summary")
    )


def _source_text(source: dict[str, Any]) -> str:
    return f"{source.get('title', '')} {source.get('summary', '')} {source.get('failure_reason', '')}"


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _closest_sources(idea: dict[str, Any], sources: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    idea_tokens = _tokens(_idea_text(idea))
    rows: list[dict[str, Any]] = []
    for source in sources:
        score = _similarity(idea_tokens, _tokens(_source_text(source)))
        if score <= 0:
            continue
        rows.append(
            {
                "source_id": str(source.get("id") or ""),
                "title": str(source.get("title") or ""),
                "kind": str(source.get("kind") or ""),
                "path": str(source.get("path") or ""),
                "similarity": round(score, 3),
            }
        )
    return sorted(rows, key=lambda item: item["similarity"], reverse=True)[:limit]


def _failed_overlap(idea: dict[str, Any], failed_ideas: list[dict[str, Any]]) -> tuple[bool, str]:
    idea_tokens = _tokens(_idea_text(idea))
    for failed in failed_ideas:
        score = _similarity(idea_tokens, _tokens(_source_text(failed)))
        if score >= 0.35:
            return True, str(failed.get("id") or failed.get("title") or "failed-idea")
    return False, ""


def _resolve_external_paths(inputs: dict[str, Any], workspace_root: Path) -> list[Path]:
    values: list[Any] = []
    for key in (
        "novelty_evidence",
        "external_novelty_evidence",
        "semantic_scholar_evidence",
        "deepxiv_evidence",
        "web_evidence",
    ):
        raw = inputs.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw:
            values.append(raw)
    env_value = os.environ.get("AUTOSCI_NOVELTY_EVIDENCE", "").strip()
    if env_value:
        values.extend([item for item in env_value.split(os.pathsep) if item])

    paths: list[Path] = []
    for value in values:
        path = Path(str(value))
        paths.append(path if path.is_absolute() else workspace_root / path)
    return paths


def _load_external_payload(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"cannot read external novelty evidence: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"invalid external novelty evidence JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "external novelty evidence must be a JSON object"
    return payload, ""


def _candidate_items(payload: dict[str, Any]) -> list[Any]:
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    for container in (outputs, payload):
        for key in ("sources", "candidates", "results", "papers", "items", "data", "organic"):
            values = container.get(key) if isinstance(container, dict) else None
            if isinstance(values, list):
                return values
    return []


def _canonical_provider(value: str) -> str:
    provider = value.strip().lower().replace("-", "_")
    aliases = {
        "semantic scholar": "semantic_scholar",
        "semanticscholar": "semantic_scholar",
        "s2": "semantic_scholar",
        "serper": "web",
        "google": "web",
        "web_search": "web",
        "deep_xiv": "deepxiv",
    }
    return aliases.get(provider, provider or "external")


def _external_id(external_ids: dict[str, Any], *keys: str) -> str:
    lowered = {str(key).lower(): value for key, value in external_ids.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value:
            return str(value)
    return ""


def _valid_http_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _url_domain(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.lower()


def _payload_sha256(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _archive_dir(inputs: dict[str, Any], workspace_root: Path) -> Path | None:
    raw = str(
        inputs.get("novelty_payload_archive_dir")
        or os.environ.get("AUTOSCI_NOVELTY_PAYLOAD_ARCHIVE_DIR", "")
    ).strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else workspace_root / path


def _archive_payload(
    payload: dict[str, Any],
    inputs: dict[str, Any],
    workspace_root: Path,
    *,
    provider: str,
    payload_hash: str,
    source_path: Path | None = None,
) -> dict[str, str]:
    if not payload_hash:
        return {"status": "missing", "path": "", "reason": "raw payload sha256 is missing"}
    archive_dir = _archive_dir(inputs, workspace_root)
    if archive_dir is None:
        return {"status": "unavailable", "path": "", "reason": "no novelty payload archive directory configured"}
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{_canonical_provider(provider)}-{payload_hash[:16]}.json"
        if source_path is not None and source_path.exists():
            archive_path.write_bytes(source_path.read_bytes())
        else:
            archive_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"status": "failed", "path": "", "reason": str(exc)}
    return {"status": "completed", "path": str(archive_path), "reason": ""}


def _normalize_external_source(
    item: Any,
    path: Path | str,
    index: int,
    *,
    provider_hint: str = "external",
    raw_payload_ref: str = "",
    raw_payload_sha256: str = "",
    raw_payload_archive_path: str = "",
    raw_payload_archive_status: str = "",
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or item.get("paper_title") or item.get("name") or "").strip()
    if not title:
        return None
    provider = _canonical_provider(str(item.get("provider") or item.get("source") or item.get("kind") or provider_hint or "external"))
    path_text = str(path)
    path_stem = Path(path_text).stem if "://" not in path_text else provider
    source_id = str(
        item.get("id")
        or item.get("paper_id")
        or item.get("paperId")
        or item.get("deepxiv_id")
        or item.get("deepxivId")
        or item.get("url")
        or item.get("link")
        or f"{path_stem}:{index + 1:03d}"
    )
    external_ids = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
    url = str(item.get("url") or item.get("link") or "")
    doi = str(item.get("doi") or _external_id(external_ids, "DOI", "Doi") or "")
    arxiv_id = str(item.get("arxiv_id") or item.get("arxivId") or _external_id(external_ids, "ArXiv", "arXiv") or "")
    s2_id = str(item.get("paperId") or item.get("s2_id") or item.get("semantic_scholar_id") or "")
    deepxiv_id = str(item.get("deepxiv_id") or item.get("deepxivId") or item.get("deepxiv_paper_id") or "")
    tldr = item.get("tldr")
    tldr_text = tldr.get("text") if isinstance(tldr, dict) else str(tldr or "")
    summary = str(item.get("summary") or item.get("abstract") or item.get("snippet") or tldr_text or item.get("reason") or "")[:800]
    provider_identifier_status = _provider_identifier_status(
        provider=provider,
        source_id=source_id,
        url=url,
        doi=doi,
        arxiv_id=arxiv_id,
        s2_id=s2_id,
        deepxiv_id=deepxiv_id,
    )
    return {
        "id": f"external:{provider}:{source_id}",
        "kind": provider,
        "title": title,
        "summary": summary,
        "path": path_text,
        "status": "",
        "failure_reason": "",
        "url": url,
        "provenance": {
            "provider": provider,
            "source_id": source_id,
            "url": url,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "s2_id": s2_id,
            "deepxiv_id": deepxiv_id,
            "url_domain": _url_domain(url) if _valid_http_url(url) else "",
            "identifier_status": provider_identifier_status["status"],
            "provider_schema": provider_identifier_status["schema"],
            "provider_required_any": provider_identifier_status["required_any"],
            "provider_identifier_issues": provider_identifier_status["issues"],
            "raw_payload_ref": raw_payload_ref or path_text,
            "raw_payload_sha256": raw_payload_sha256,
            "raw_payload_status": "passed" if raw_payload_sha256 else "missing",
            "raw_payload_archive_path": raw_payload_archive_path,
            "raw_payload_archive_status": raw_payload_archive_status or ("completed" if raw_payload_archive_path else "missing"),
        },
    }


def _provider_identifier_status(
    *,
    provider: str,
    source_id: str,
    url: str,
    doi: str,
    arxiv_id: str,
    s2_id: str,
    deepxiv_id: str,
) -> dict[str, Any]:
    provider = _canonical_provider(provider)
    valid_url = _valid_http_url(url)
    if provider == "semantic_scholar":
        issues = [] if (s2_id or doi or arxiv_id) else ["semantic_scholar requires paperId, DOI, or arXiv id."]
        return {
            "schema": "semantic_scholar",
            "required_any": ["paperId", "externalIds.DOI", "externalIds.ArXiv"],
            "status": "passed" if not issues else "missing",
            "issues": issues,
        }
    if provider == "web":
        issues = [] if valid_url else ["web requires an absolute http(s) URL."]
        return {
            "schema": "web",
            "required_any": ["url"],
            "status": "passed" if not issues else "missing",
            "issues": issues,
        }
    if provider == "deepxiv":
        issues = [] if (deepxiv_id or doi or arxiv_id or valid_url) else ["deepxiv requires deepxiv id, DOI, arXiv id, or absolute http(s) URL."]
        return {
            "schema": "deepxiv",
            "required_any": ["deepxiv_id", "DOI", "arxiv_id", "url"],
            "status": "passed" if not issues else "missing",
            "issues": issues,
        }
    if provider == "openalex":
        issues = (
            []
            if (_valid_http_url(source_id) or doi or valid_url)
            else ["openalex requires a work id URL, DOI, or absolute http(s) URL."]
        )
        return {
            "schema": "openalex",
            "required_any": ["id", "DOI", "url"],
            "status": "passed" if not issues else "missing",
            "issues": issues,
        }
    issues = [] if (valid_url or doi or arxiv_id or s2_id or deepxiv_id or source_id) else ["external source requires a durable id or URL."]
    return {
        "schema": "external",
        "required_any": ["source_id", "url", "DOI", "arxiv_id", "paperId"],
        "status": "passed" if not issues else "missing",
        "issues": issues,
    }


def _payload_query(payload: dict[str, Any]) -> str:
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    return str(
        outputs.get("query")
        or inputs.get("query")
        or inputs.get("topic")
        or inputs.get("target")
        or payload.get("query")
        or ""
    )


def _payload_timestamp(payload: dict[str, Any]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    return str(
        payload.get("fetched_at")
        or payload.get("retrieved_at")
        or outputs.get("fetched_at")
        or outputs.get("retrieved_at")
        or provenance.get("timestamp")
        or ""
    )


def _external_provenance_report(external: dict[str, Any]) -> dict[str, Any]:
    sources = list(external.get("sources") or [])
    provider_statuses = [item for item in list(external.get("provider_statuses") or []) if isinstance(item, dict)]
    if str(external.get("status") or "") != "completed":
        return {
            "status": str(external.get("status") or "unavailable"),
            "checked_source_count": len(sources),
            "completed_provider_count": 0,
            "issues": [str(external.get("reason") or "External novelty evidence is not completed.")],
        }
    issues: list[str] = []
    completed = [item for item in provider_statuses if item.get("status") == "completed"]
    if not completed:
        issues.append("No completed provider status was recorded.")
    for status in completed:
        provider = str(status.get("provider") or "unknown")
        if not str(status.get("query") or "").strip():
            issues.append(f"{provider} provider status is missing query metadata.")
        if not str(status.get("fetched_at") or "").strip():
            issues.append(f"{provider} provider status is missing fetched_at timestamp.")
    for source in sources:
        provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
        source_id = str(source.get("id") or "unknown")
        if not str(provenance.get("provider") or source.get("kind") or "").strip():
            issues.append(f"{source_id} is missing provider metadata.")
        if provenance.get("identifier_status") != "passed":
            provider_issues = [
                str(item)
                for item in provenance.get("provider_identifier_issues", [])
                if str(item).strip()
            ]
            if provider_issues:
                issues.extend(f"{source_id}: {issue}" for issue in provider_issues)
            else:
                issues.append(f"{source_id} is missing provider-specific durable identifiers.")
        if not str(provenance.get("raw_payload_sha256") or "").strip():
            issues.append(f"{source_id} is missing raw provider payload sha256.")
        if provenance.get("raw_payload_archive_status") != "completed":
            issues.append(f"{source_id} is missing a completed raw provider payload archive.")
    return {
        "status": "passed" if not issues else "failed",
        "checked_source_count": len(sources),
        "completed_provider_count": len(completed),
        "provider_schemas": sorted(
            {
                str((source.get("provenance") or {}).get("provider_schema") or "external")
                for source in sources
                if isinstance(source, dict)
            }
        ),
        "required_fields": [
            "provider",
            "query",
            "fetched_at",
            "semantic_scholar.paperId_or_externalIds",
            "openalex.work_id_or_doi_or_url",
            "web.absolute_http_url",
            "deepxiv.deepxiv_id_or_doi_or_arxiv_or_url",
            "raw_payload_sha256",
            "raw_payload_archive_path",
        ],
        "issues": issues[:20],
    }


def _network_disabled(inputs: dict[str, Any]) -> tuple[bool, str]:
    raw_allow = inputs.get("allow_network_fetch")
    if str(raw_allow).lower() in {"0", "false", "no"}:
        return True, "inputs.allow_network_fetch=false"
    if os.environ.get("AUTOSCI_DISABLE_NETWORK_FETCH", "").lower() in {"1", "true", "yes"}:
        return True, "AUTOSCI_DISABLE_NETWORK_FETCH is set"
    native = inputs.get("native_options") if isinstance(inputs.get("native_options"), dict) else {}
    if native.get("quick"):
        return True, "native quick mode skips online novelty fetch"
    return False, ""


def _online_requested(inputs: dict[str, Any]) -> bool:
    native = inputs.get("native_options") if isinstance(inputs.get("native_options"), dict) else {}
    return bool(inputs.get("online_novelty") or native.get("online") or native.get("full"))


def _online_query(idea: dict[str, Any], inputs: dict[str, Any]) -> str:
    return str(inputs.get("topic") or inputs.get("target") or inputs.get("query") or _idea_text(idea)).strip()


def _online_providers(inputs: dict[str, Any]) -> list[str]:
    raw = inputs.get("novelty_providers")
    if isinstance(raw, list) and raw:
        values = [str(item) for item in raw]
    else:
        env_value = os.environ.get("AUTOSCI_NOVELTY_PROVIDERS", "").strip()
        values = env_value.split(",") if env_value else ["semantic_scholar", "openalex", "web", "deepxiv"]
    out: list[str] = []
    for value in values:
        provider = value.strip().lower().replace("-", "_")
        if provider and provider not in out:
            out.append(provider)
    return out


def _fetch_json_url(url: str, *, query: str, limit: int, method: str = "GET", headers: dict[str, str] | None = None) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    final_url = url
    body = None
    if parsed.scheme != "file":
        if "{query}" in final_url or "{limit}" in final_url:
            final_url = final_url.replace("{query}", urllib.parse.quote(query)).replace("{limit}", str(limit))
        else:
            parts = urllib.parse.urlparse(final_url)
            params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
            params.setdefault("query", query)
            params.setdefault("limit", str(limit))
            final_url = urllib.parse.urlunparse(parts._replace(query=urllib.parse.urlencode(params)))
    if method == "POST":
        body = json.dumps({"q": query, "query": query, "num": limit, "limit": limit}).encode("utf-8")
    req = urllib.request.Request(
        final_url,
        data=body,
        headers=headers or {"User-Agent": "Solar-AutoSci-Novelty/1.0"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=int(os.environ.get("AUTOSCI_NOVELTY_FETCH_TIMEOUT", "15"))) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _semantic_scholar_endpoint() -> str:
    return os.environ.get("AUTOSCI_SEMANTIC_SCHOLAR_SEARCH_URL", "https://api.semanticscholar.org/graph/v1/paper/search")


def _semantic_scholar_headers() -> dict[str, str]:
    headers = {"User-Agent": "Solar-AutoSci-Novelty/1.0"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _fetch_semantic_scholar_sources(
    query: str,
    limit: int,
    inputs: dict[str, Any],
    workspace_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    endpoint = _semantic_scholar_endpoint()
    try:
        payload = _fetch_json_url(
            endpoint,
            query=query,
            limit=limit,
            headers=_semantic_scholar_headers(),
        )
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError) as exc:
        return [], {"provider": "semantic_scholar", "status": "failed", "reason": str(exc), "query": query}
    payload_hash = _payload_sha256(payload)
    archive = _archive_payload(
        payload,
        inputs,
        workspace_root,
        provider="semantic_scholar",
        payload_hash=payload_hash,
    )
    sources = [
        source
        for index, item in enumerate(_candidate_items(payload))
        if (source := _normalize_external_source(
            item,
            endpoint,
            index,
            provider_hint="semantic_scholar",
            raw_payload_ref=endpoint,
            raw_payload_sha256=payload_hash,
            raw_payload_archive_path=archive["path"],
            raw_payload_archive_status=archive["status"],
        )) is not None
    ]
    return sources, {
        "provider": "semantic_scholar",
        "status": "completed" if sources else "inconclusive",
        "source_count": len(sources),
        "query": query,
        "endpoint": endpoint,
        "raw_payload_ref": endpoint,
        "raw_payload_sha256": payload_hash,
        "raw_payload_archive_path": archive["path"],
        "raw_payload_archive_status": archive["status"],
    }


def _fetch_openalex_sources(
    query: str,
    limit: int,
    inputs: dict[str, Any],
    workspace_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    endpoint = os.environ.get(
        "AUTOSCI_OPENALEX_SEARCH_URL",
        "https://api.openalex.org/works?search={query}&per-page={limit}&select=id,doi,title",
    )
    try:
        payload = _fetch_json_url(endpoint, query=query, limit=limit)
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        return [], {
            "provider": "openalex",
            "status": "failed",
            "reason": str(exc),
            "query": query,
            "endpoint": endpoint,
        }
    payload_hash = _payload_sha256(payload)
    archive = _archive_payload(payload, inputs, workspace_root, provider="openalex", payload_hash=payload_hash)
    normalized_items: list[dict[str, Any]] = []
    for item in _candidate_items(payload):
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized["title"] = item.get("title") or item.get("display_name") or ""
        normalized["url"] = item.get("url") or item.get("id") or ""
        normalized["provider"] = "openalex"
        normalized_items.append(normalized)
    sources = [
        source
        for index, item in enumerate(normalized_items)
        if (source := _normalize_external_source(
            item,
            endpoint,
            index,
            provider_hint="openalex",
            raw_payload_ref=endpoint,
            raw_payload_sha256=payload_hash,
            raw_payload_archive_path=archive["path"],
            raw_payload_archive_status=archive["status"],
        )) is not None
    ]
    return sources, {
        "provider": "openalex",
        "status": "completed" if sources else "inconclusive",
        "source_count": len(sources),
        "query": query,
        "endpoint": endpoint,
        "raw_payload_ref": endpoint,
        "raw_payload_sha256": payload_hash,
        "raw_payload_archive_path": archive["path"],
        "raw_payload_archive_status": archive["status"],
    }


def _fetch_web_sources(
    query: str,
    limit: int,
    inputs: dict[str, Any],
    workspace_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    endpoint = os.environ.get("AUTOSCI_WEB_SEARCH_EVIDENCE_URL", "").strip()
    method = "GET"
    headers = {"User-Agent": "Solar-AutoSci-Novelty/1.0"}
    if not endpoint and os.environ.get("SERPER_API_KEY"):
        endpoint = os.environ.get("SERPER_SEARCH_URL", "https://google.serper.dev/search")
        method = "POST"
        headers = {
            "User-Agent": "Solar-AutoSci-Novelty/1.0",
            "Content-Type": "application/json",
            "X-API-KEY": os.environ["SERPER_API_KEY"],
        }
    if not endpoint:
        return [], {"provider": "web", "status": "unavailable", "reason": "missing AUTOSCI_WEB_SEARCH_EVIDENCE_URL or SERPER_API_KEY", "query": query}
    try:
        payload = _fetch_json_url(endpoint, query=query, limit=limit, method=method, headers=headers)
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError) as exc:
        return [], {"provider": "web", "status": "failed", "reason": str(exc), "query": query, "endpoint": endpoint}
    payload_hash = _payload_sha256(payload)
    archive = _archive_payload(payload, inputs, workspace_root, provider="web", payload_hash=payload_hash)
    sources = [
        source
        for index, item in enumerate(_candidate_items(payload))
        if (source := _normalize_external_source(
            item,
            endpoint,
            index,
            provider_hint="web",
            raw_payload_ref=endpoint,
            raw_payload_sha256=payload_hash,
            raw_payload_archive_path=archive["path"],
            raw_payload_archive_status=archive["status"],
        )) is not None
    ]
    return sources, {
        "provider": "web",
        "status": "completed" if sources else "inconclusive",
        "source_count": len(sources),
        "query": query,
        "endpoint": endpoint,
        "raw_payload_ref": endpoint,
        "raw_payload_sha256": payload_hash,
        "raw_payload_archive_path": archive["path"],
        "raw_payload_archive_status": archive["status"],
    }


def _fetch_deepxiv_sources(
    query: str,
    limit: int,
    inputs: dict[str, Any],
    workspace_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    endpoint = os.environ.get("AUTOSCI_DEEPXIV_SEARCH_URL", "").strip()
    if not endpoint:
        return [], {"provider": "deepxiv", "status": "unavailable", "reason": "missing AUTOSCI_DEEPXIV_SEARCH_URL", "query": query}
    try:
        payload = _fetch_json_url(endpoint, query=query, limit=limit)
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError) as exc:
        return [], {"provider": "deepxiv", "status": "failed", "reason": str(exc), "query": query, "endpoint": endpoint}
    payload_hash = _payload_sha256(payload)
    archive = _archive_payload(payload, inputs, workspace_root, provider="deepxiv", payload_hash=payload_hash)
    sources = [
        source
        for index, item in enumerate(_candidate_items(payload))
        if (source := _normalize_external_source(
            item,
            endpoint,
            index,
            provider_hint="deepxiv",
            raw_payload_ref=endpoint,
            raw_payload_sha256=payload_hash,
            raw_payload_archive_path=archive["path"],
            raw_payload_archive_status=archive["status"],
        )) is not None
    ]
    return sources, {
        "provider": "deepxiv",
        "status": "completed" if sources else "inconclusive",
        "source_count": len(sources),
        "query": query,
        "endpoint": endpoint,
        "raw_payload_ref": endpoint,
        "raw_payload_sha256": payload_hash,
        "raw_payload_archive_path": archive["path"],
        "raw_payload_archive_status": archive["status"],
    }


def _fetch_online_sources(idea: dict[str, Any], inputs: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    query = _online_query(idea, inputs)
    if not query:
        return {"status": "unavailable", "sources": [], "source_count": 0, "provider_statuses": [], "reason": "No query was available for online novelty fetch."}
    disabled, reason = _network_disabled(inputs)
    if disabled:
        return {"status": "unavailable", "sources": [], "source_count": 0, "provider_statuses": [], "reason": f"Online novelty fetch disabled: {reason}"}
    limit = max(1, min(int(inputs.get("limit") or inputs.get("max_external_sources") or 8), 20))
    fetchers = {
        "semantic_scholar": _fetch_semantic_scholar_sources,
        "s2": _fetch_semantic_scholar_sources,
        "openalex": _fetch_openalex_sources,
        "open_alex": _fetch_openalex_sources,
        "web": _fetch_web_sources,
        "deepxiv": _fetch_deepxiv_sources,
    }
    sources: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for provider in _online_providers(inputs):
        fetcher = fetchers.get(provider)
        if not fetcher:
            statuses.append({"provider": provider, "status": "unsupported", "reason": "unsupported novelty provider", "query": query, "fetched_at": fetched_at})
            continue
        provider_sources, status = fetcher(query, limit, inputs, workspace_root)
        status["fetched_at"] = fetched_at
        statuses.append(status)
        sources.extend(provider_sources)
    return {
        "status": "completed" if sources else "unavailable",
        "sources": sources,
        "source_count": len(sources),
        "provider_statuses": statuses,
        "query": query,
        "reason": "" if sources else "Online novelty providers returned no usable sources.",
    }


def _external_novelty_sources(inputs: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    paths = _resolve_external_paths(inputs, workspace_root)
    if not paths:
        return {}

    checked: list[str] = []
    sources: list[dict[str, Any]] = []
    invalid_reasons: list[str] = []
    payload_refs: list[str] = []
    payload_hashes: list[str] = []
    payload_archive_paths: list[str] = []
    payload_archive_statuses: list[str] = []
    for path in paths:
        checked.append(str(path))
        payload, error = _load_external_payload(path)
        if error:
            invalid_reasons.append(error)
            continue
        assert payload is not None
        if payload.get("status") not in {"completed", "inconclusive", None}:
            invalid_reasons.append(f"{path}: unsupported external evidence status {payload.get('status')}")
            continue
        payload_hash = _file_sha256(path)
        archive = _archive_payload(
            payload,
            inputs,
            workspace_root,
            provider="supplied_evidence",
            payload_hash=payload_hash,
            source_path=path,
        )
        payload_refs.append(str(path))
        payload_hashes.append(payload_hash)
        payload_archive_paths.append(archive["path"])
        payload_archive_statuses.append(archive["status"])
        for index, item in enumerate(_candidate_items(payload)):
            source = _normalize_external_source(
                item,
                path,
                index,
                raw_payload_ref=str(path),
                raw_payload_sha256=payload_hash,
                raw_payload_archive_path=archive["path"],
                raw_payload_archive_status=archive["status"],
            )
            if source:
                sources.append(source)

    if sources:
        query = next((value for value in (_payload_query(_load_external_payload(path)[0] or {}) for path in paths) if value), "")
        fetched_at = next((value for value in (_payload_timestamp(_load_external_payload(path)[0] or {}) for path in paths) if value), "")
        return {
            "status": "completed",
            "sources": sources,
            "source_count": len(sources),
            "checked_paths": checked,
            "provider_statuses": [
                {
                    "provider": "supplied_evidence",
                    "status": "completed",
                    "source_count": len(sources),
                    "query": query,
                    "fetched_at": fetched_at,
                    "raw_payload_ref": payload_refs[0] if payload_refs else "",
                    "raw_payload_sha256": payload_hashes[0] if payload_hashes else "",
                    "raw_payload_refs": payload_refs,
                    "raw_payload_sha256s": payload_hashes,
                    "raw_payload_archive_path": payload_archive_paths[0] if payload_archive_paths else "",
                    "raw_payload_archive_status": payload_archive_statuses[0] if payload_archive_statuses else "missing",
                    "raw_payload_archive_paths": payload_archive_paths,
                    "raw_payload_archive_statuses": payload_archive_statuses,
                }
            ],
            "reason": "",
        }
    return {
        "status": "invalid",
        "sources": [],
        "source_count": 0,
        "checked_paths": checked,
        "provider_statuses": [{"provider": "supplied_evidence", "status": "invalid", "reason": "; ".join(invalid_reasons)}],
        "reason": "; ".join(invalid_reasons) or "No external novelty candidates were found in supplied evidence.",
    }


def _review_llm_for_novelty(inputs: dict[str, Any], workspace_root: Path, idea: dict[str, Any]) -> dict[str, Any]:
    native = inputs.get("native_options") if isinstance(inputs.get("native_options"), dict) else {}
    difficulty = str(inputs.get("difficulty") or native.get("difficulty") or "standard") or "standard"
    focus = str(inputs.get("focus") or native.get("focus") or "novelty") or "novelty"
    # Persist then reload a reviewer snapshot.  The review path must not treat
    # the caller's mutable idea dict as review evidence.
    writer_snapshot = {
        "schema": "autosci_novelty_reviewer_input.v1",
        "idea_id": str(idea.get("idea_id") or ""),
        "title": str(idea.get("title") or ""),
        "hypothesis": str(idea.get("hypothesis") or ""),
        "approach": str(idea.get("approach") or ""),
        "source_mode": str(idea.get("source_mode") or ""),
    }
    serialized = json.dumps(writer_snapshot, ensure_ascii=False, sort_keys=True)
    snapshot_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    snapshot_path = workspace_root / "artifacts" / "autosci" / "reviewer-inputs" / f"novelty-{snapshot_hash[:16]}.json"
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(serialized + "\n", encoding="utf-8")
        reloaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
        reloaded_text = json.dumps(reloaded, ensure_ascii=False, sort_keys=True)
        snapshot_reloaded = True
    except (OSError, json.JSONDecodeError):
        reloaded = {}
        reloaded_text = ""
        snapshot_reloaded = False
    review_inputs = {
        key: value
        for key, value in inputs.items()
        if key not in {"writer_output", "writer_verdict", "writer_result", "writer_context"}
    }
    review_inputs.setdefault("target", str(idea.get("title") or idea.get("idea_id") or inputs.get("target") or "N/A"))
    review_inputs["review_target"] = {
        "type": "persisted_novelty_snapshot",
        "path": str(snapshot_path),
        "sha256": snapshot_hash,
        "text": reloaded_text,
        "snapshot": reloaded,
    }
    result = _review_llm_assessment(review_inputs, workspace_root=workspace_root, difficulty=difficulty, focus=focus)
    result["reviewer_separation"] = {
        "reviewer_role": "independent_reviewer",
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_hash,
        "snapshot_reloaded_from_disk": snapshot_reloaded,
        "writer_output_excluded_from_reviewer_context": True,
    }
    return result


def _idea_recommendation_with_review(local: str, review_recommendation: str) -> str:
    local = local if local in {"advance", "revise", "reject", "inconclusive"} else "revise"
    review_recommendation = review_recommendation.strip()
    if local in {"reject", "inconclusive"}:
        return local
    if review_recommendation == "inconclusive":
        return "inconclusive"
    if review_recommendation in {"revise", "revise_required"}:
        return "revise"
    return local


def evaluate_novelty_and_review(
    idea: dict[str, Any],
    inputs: dict[str, Any],
    *,
    workspace_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    bundle = collect_idea_sources(inputs, workspace_root=workspace_root, repository_root=repository_root)
    review_llm = _review_llm_for_novelty(inputs, workspace_root, idea)
    external = _external_novelty_sources(inputs, workspace_root)
    if not external:
        external = (
            _fetch_online_sources(idea, inputs, workspace_root)
            if _online_requested(inputs)
            else {
                "status": "unavailable",
                "sources": [],
                "source_count": 0,
                "checked_paths": [],
                "provider_statuses": [],
                "reason": "No OpenAlex/Web/Semantic Scholar/DeepXiv novelty evidence path was supplied and online novelty fetch was not requested.",
            }
        )
    external_sources = list(external.get("sources") or [])
    provenance = _external_provenance_report(external)
    local_sources = list(bundle["sources"])
    sources = [*local_sources, *external_sources]
    source_mode = str(idea.get("source_mode") or bundle["source_mode"])
    if source_mode == "missing" and external_sources:
        source_mode = "external"
    closest = _closest_sources(idea, sources)
    failed_overlap, failed_ref = _failed_overlap(idea, list(bundle["failed_ideas"]))
    max_similarity = float(closest[0]["similarity"]) if closest else 0.0
    source_count = len(sources)

    if source_mode == "missing" or source_count == 0:
        novelty = 0.0
        review_score = 0.0
        recommendation = "inconclusive"
        risks = ["No wiki or discovery source evidence was available for novelty/review."]
    else:
        novelty = max(0.2, min(0.85, 0.78 - max_similarity * 0.45))
        if failed_overlap:
            novelty = max(0.1, novelty - 0.2)
        review_score = max(0.2, min(0.85, 0.45 + min(source_count, 6) * 0.05 - max_similarity * 0.15))
        if novelty < 0.35:
            recommendation = "reject"
        elif novelty < 0.55 or review_score < 0.55:
            recommendation = "revise"
        else:
            recommendation = "revise"
        risks = [
            "Review LLM cross-verify is not connected; this is a local conservative review signal.",
            "Run /novelty with live search and /review with Review LLM before promotion.",
        ]
        if failed_overlap:
            risks.append(f"Overlaps failed idea memory: {failed_ref}.")
        if external.get("status") != "completed":
            risks.append("External OpenAlex/Web/Semantic Scholar/DeepXiv novelty evidence is unavailable or invalid.")

    review_mode = "local_surrogate"
    review_available = False
    review_rationale = (
        "Local review checks source grounding, failed-idea overlap, and closest-prior similarity; "
        "independent Review LLM evidence is still required."
    )
    if review_llm.get("status") == "completed":
        review_mode = "review_llm"
        review_available = True
        try:
            review_score = round(min(float(review_score), float(review_llm.get("score", review_score))), 3)
        except (TypeError, ValueError):
            review_score = round(float(review_score), 3)
        recommendation = _idea_recommendation_with_review(
            str(recommendation),
            str(review_llm.get("recommendation") or ""),
        )
        risks = [risk for risk in risks if "Review LLM cross-verify is not connected" not in risk]
        invocation_mode = str(review_llm.get("invocation_mode") or "evidence")
        if invocation_mode == "provider":
            risks.append("Review LLM evidence was produced through the configured provider path.")
            review_rationale = (
                "Local review score is conservatively bounded by provider-produced Review LLM evidence."
            )
        elif invocation_mode == "command":
            risks.append("Review LLM evidence was produced through the configured command bridge.")
            review_rationale = (
                "Local review score is conservatively bounded by command-bridge Review LLM evidence."
            )
        else:
            risks.append("Review LLM evidence was supplied externally.")
            review_rationale = (
                "Local review score is conservatively bounded by supplied Review LLM evidence."
            )
    elif review_llm.get("status") == "invalid":
        risks.append(f"Invalid Review LLM evidence was ignored: {review_llm.get('reason')}")

    novelty_label = "missing" if source_count == 0 else "high-overlap" if max_similarity >= 0.5 else "source-grounded"
    return {
        "novelty": round(novelty, 3),
        "review_score": round(review_score, 3),
        "recommendation": recommendation,
        "risks": risks,
        "closest_prior_work": closest,
        "source_mode": source_mode,
        "source_count": source_count,
        "local_source_count": len(local_sources),
        "external_source_count": len(external_sources),
        "external_novelty": {
            "status": str(external.get("status") or "unavailable"),
            "source_count": int(external.get("source_count") or 0),
            "checked_paths": list(external.get("checked_paths") or []),
            "provider_statuses": list(external.get("provider_statuses") or []),
            "query": str(external.get("query") or ""),
            "provenance": provenance,
            "reason": str(external.get("reason") or ""),
        },
        "review_mode": review_mode,
        "review_available": review_available,
        "review_llm": review_llm,
        "novelty_label": novelty_label,
        "failed_overlap": failed_ref if failed_overlap else "",
        "novelty_rationale": (
            "Novelty is estimated from overlap against local wiki/discovery evidence and supplied external novelty evidence. "
            f"Closest similarity={max_similarity:.3f}; source_count={source_count}; external_source_count={len(external_sources)}."
        ),
        "review_rationale": review_rationale,
    }
