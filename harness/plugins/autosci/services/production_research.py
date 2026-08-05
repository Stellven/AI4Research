"""Bounded production services for web, literature, and model-backed research.

The services in this module are deliberately small adapters.  They do not own
the research graph or its final state; they return serializable evidence to the
physical operators that Solar dispatches and evaluates.
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

try:
    from ..backends.literature_discover import discover_literature
    from ..operators.research_synthesis.base import ResearchOperatorError, stable_json_sha256
except ImportError:  # direct autosci_bridge.py execution loads plugins/autosci as a package root
    from backends.literature_discover import discover_literature
    from operators.research_synthesis.base import ResearchOperatorError, stable_json_sha256


FETCH_SERVICE_ID = "autosci-production-bounded-url-fetch"
DISCOVERY_SERVICE_ID = "autosci-production-literature-discovery"
MODEL_SERVICE_ID = "autosci-production-research-model"
SERVICE_VERSION = "1.0.0"
DEFAULT_FETCH_TIMEOUT_SECONDS = 30
DEFAULT_FETCH_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_FETCH_MAX_REDIRECTS = 5
DEFAULT_EXTRACTED_TEXT_CHARS = 120_000
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 90
DEFAULT_PROVIDER_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_OPENROUTER_RESEARCH_MODEL = "deepseek/deepseek-v3.2"
DEFAULT_OPENAI_RESEARCH_MODEL = "gpt-5-mini"
_ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
}
_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip(".-")
    return cleaned[:100] or "service-evidence"


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(body, encoding="utf-8")
    return _sha256(path.read_bytes())


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _response_charset(content_type: str) -> str:
    match = re.search(r"charset\s*=\s*['\"]?([^;\s'\"]+)", content_type, re.IGNORECASE)
    return str(match.group(1) if match else "utf-8").strip()


def _decode_body(body: bytes, content_type: str) -> tuple[str, str]:
    declared = _response_charset(content_type)
    tried: list[str] = []
    for encoding in (declared, "utf-8", "gb18030"):
        if encoding.lower() in tried:
            continue
        tried.append(encoding.lower())
        try:
            text = body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
        return text, encoding
    return body.decode("utf-8", errors="replace"), "utf-8-replacement"


class _VisibleHtmlParser(HTMLParser):
    """Extract visible text, title, and description without executing markup."""

    _BLOCKED = {"script", "style", "noscript", "template", "svg", "canvas"}
    _BREAKS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocked_depth = 0
        self._in_title = False
        self._chunks: list[str] = []
        self._title_chunks: list[str] = []
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in self._BLOCKED:
            self._blocked_depth += 1
        if lowered == "title":
            self._in_title = True
        if lowered == "meta":
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            name = (values.get("name") or values.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.description:
                self.description = values.get("content", "").strip()
        if lowered in self._BREAKS and self._blocked_depth == 0:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = False
        if lowered in self._BLOCKED and self._blocked_depth:
            self._blocked_depth -= 1
        if lowered in self._BREAKS and self._blocked_depth == 0:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._blocked_depth:
            return
        value = html.unescape(str(data or ""))
        if self._in_title:
            self._title_chunks.append(value)
        self._chunks.append(value)

    @property
    def title(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._title_chunks)).strip()[:500]

    @property
    def text(self) -> str:
        lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in "".join(self._chunks).splitlines()]
        return "\n".join(line for line in lines if line)


def _public_http_url(
    raw_url: str,
    *,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> urllib.parse.SplitResult:
    try:
        parsed = urllib.parse.urlsplit(str(raw_url or "").strip())
    except ValueError as exc:
        raise ResearchOperatorError(f"URL parsing failed: {exc}", error_type="invalid_url") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ResearchOperatorError("Only http and https URL schemes are allowed", error_type="invalid_url")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ResearchOperatorError("URL must contain a public host and no embedded credentials", error_type="invalid_url")
    try:
        records = resolver(parsed.hostname, parsed.port or (443 if parsed.scheme.lower() == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ResearchOperatorError(f"URL host resolution failed: {type(exc).__name__}: {exc}", error_type="dns_failure") from exc
    addresses = {str(item[4][0]).split("%", 1)[0] for item in records if len(item) > 4 and item[4]}
    if not addresses:
        raise ResearchOperatorError("URL host resolved to no usable address", error_type="dns_failure")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ResearchOperatorError("URL host returned an invalid address", error_type="dns_failure") from exc
        if not ip.is_global:
            raise ResearchOperatorError("URL host resolves to a non-public address", error_type="url_policy_rejected")
    return parsed


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, *, max_redirects: int, resolver: Callable[..., list[tuple[Any, ...]]]) -> None:
        super().__init__()
        self.max_redirects = max_redirects
        self.resolver = resolver
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        self.redirect_count += 1
        if self.redirect_count > self.max_redirects:
            raise ResearchOperatorError("URL exceeded the redirect limit", error_type="redirect_limit")
        _public_http_url(newurl, resolver=self.resolver)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class BoundedUrlFetcher:
    """Fetch and parse one public URL through bounded, auditable HTTP rules."""

    workspace_root: Path
    timeout_seconds: int = DEFAULT_FETCH_TIMEOUT_SECONDS
    max_bytes: int = DEFAULT_FETCH_MAX_BYTES
    max_redirects: int = DEFAULT_FETCH_MAX_REDIRECTS
    max_text_chars: int = DEFAULT_EXTRACTED_TEXT_CHARS
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo
    opener_factory: Callable[..., Any] = urllib.request.build_opener
    clock: Callable[[], str] = _utc_now

    service_id: str = FETCH_SERVICE_ID
    service_version: str = SERVICE_VERSION

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()

    def __call__(self, url: str, *, seed: dict[str, Any]) -> dict[str, Any]:
        _public_http_url(url, resolver=self.resolver)
        redirect_handler = _BoundedRedirectHandler(max_redirects=self.max_redirects, resolver=self.resolver)
        opener = self.opener_factory(redirect_handler)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                "Accept-Encoding": "identity",
                "User-Agent": "OpenSolar-AutoSci/1.0 (+bounded research fetch)",
            },
            method="GET",
        )
        request_hash = stable_json_sha256(
            {
                "service_id": self.service_id,
                "service_version": self.service_version,
                "method": "GET",
                "url": url,
                "seed_id": str(seed.get("seed_id") or ""),
                "timeout_seconds": self.timeout_seconds,
                "max_bytes": self.max_bytes,
                "max_redirects": self.max_redirects,
            }
        )
        started = time.monotonic()
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                final_url = str(response.geturl())
                _public_http_url(final_url, resolver=self.resolver)
                content_type_header = str(response.headers.get("Content-Type") or "").strip()
                media_type = content_type_header.split(";", 1)[0].strip().lower()
                if media_type not in _ALLOWED_CONTENT_TYPES:
                    raise ResearchOperatorError(
                        f"URL response content type is not allowed: {media_type or 'missing'}",
                        error_type="content_type_rejected",
                    )
                content_length = str(response.headers.get("Content-Length") or "").strip()
                if content_length.isdigit() and int(content_length) > self.max_bytes:
                    raise ResearchOperatorError("URL response exceeds the configured size limit", error_type="response_too_large")
                body = response.read(self.max_bytes + 1)
                status_code = int(getattr(response, "status", 200) or 200)
                selected_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                    if str(key).lower() in {"content-type", "content-length", "etag", "last-modified"}
                    and str(key).lower() not in _SENSITIVE_HEADER_NAMES
                }
        except ResearchOperatorError:
            raise
        except urllib.error.HTTPError as exc:
            raise ResearchOperatorError(
                f"URL fetch returned HTTP {exc.code}",
                error_type="http_rate_limited" if exc.code == 429 else "http_error",
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ResearchOperatorError("URL fetch timed out", error_type="fetch_timeout") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ResearchOperatorError(
                f"URL fetch failed: {type(exc).__name__}: {exc}",
                error_type="network_failure",
            ) from exc
        if len(body) > self.max_bytes:
            raise ResearchOperatorError("URL response exceeds the configured size limit", error_type="response_too_large")
        elapsed = time.monotonic() - started
        if elapsed > self.timeout_seconds + 1:
            raise ResearchOperatorError("URL fetch exceeded the configured timeout", error_type="fetch_timeout")
        decoded, encoding = _decode_body(body, content_type_header)
        parser = _VisibleHtmlParser()
        if media_type in {"text/html", "application/xhtml+xml"}:
            try:
                parser.feed(decoded)
                content = parser.text
            except Exception as exc:
                raise ResearchOperatorError(
                    f"HTML parsing failed: {type(exc).__name__}: {exc}",
                    error_type="content_parse_failure",
                ) from exc
        else:
            content = decoded
        content = content.strip()[: self.max_text_chars]
        if not content:
            raise ResearchOperatorError("URL fetch produced no visible text", error_type="empty_content")
        fetched_at = self.clock()
        raw_sha256 = _sha256(body)
        content_sha256 = _sha256(content.encode("utf-8"))
        suffix = ".html" if media_type in {"text/html", "application/xhtml+xml"} else ".txt"
        archive_path = self.workspace_root / "service-evidence" / "fetch" / f"{raw_sha256}{suffix}"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(body)
        metadata_path = archive_path.with_suffix(archive_path.suffix + ".json")
        response_hash = _write_json(
            metadata_path,
            {
                "schema": "autosci_url_fetch_evidence.v1",
                "service_id": self.service_id,
                "service_version": self.service_version,
                "request_sha256": request_hash,
                "response_sha256": raw_sha256,
                "content_sha256": content_sha256,
                "requested_url": url,
                "final_url": final_url,
                "fetched_at": fetched_at,
                "status_code": status_code,
                "content_type": content_type_header,
                "encoding": encoding,
                "response_bytes": len(body),
                "redirect_count": redirect_handler.redirect_count,
                "headers": selected_headers,
                "raw_archive_path": _display_path(archive_path, self.workspace_root),
            },
        )
        return {
            "service_id": self.service_id,
            "service_version": self.service_version,
            "request_sha256": request_hash,
            "response_sha256": raw_sha256,
            "metadata_sha256": response_hash,
            "content_sha256": content_sha256,
            "requested_url": url,
            "final_url": final_url,
            "fetched_at": fetched_at,
            "content_type": content_type_header,
            "encoding": encoding,
            "title": parser.title or str(seed.get("title") or urllib.parse.urlsplit(final_url).hostname or "Fetched web source"),
            "description": parser.description,
            "content": content,
            "response_bytes": len(body),
            "redirect_count": redirect_handler.redirect_count,
            "archive_path": _display_path(archive_path, self.workspace_root),
            "metadata_path": _display_path(metadata_path, self.workspace_root),
            "provider": "bounded_http",
            "limitations": [
                f"Visible text was capped at {self.max_text_chars} characters for downstream processing."
            ] if len(parser.text if media_type in {"text/html", "application/xhtml+xml"} else decoded) > self.max_text_chars else [],
        }


def _topic_from_snapshot(seed_snapshot: dict[str, Any], payload: dict[str, Any]) -> str:
    task_contract = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
    intent = str(task_contract.get("user_intent") or payload.get("topic") or "").strip()
    seeds = [item for item in seed_snapshot.get("seeds") or [] if isinstance(item, dict)]
    titles = [str(item.get("title") or "").strip() for item in seeds if str(item.get("title") or "").strip()]
    inline = [
        str(item.get("content") or "").strip()
        for item in seeds
        if str(item.get("seed_kind") or "") in {"topic", "research_brief"}
    ]
    # A fetched page title is normally a higher quality public-search query
    # than appending the full user instruction (which can swamp provider
    # relevance ranking). Topic-only runs retain their full explicit topic.
    query = " ".join(inline[:1] or titles[:1] or [intent]).strip()
    query = re.sub(r"^(?:survey|review|research|analy[sz]e|synthesize)\s+", "", query, flags=re.IGNORECASE)
    query = re.split(r"[,;]", query, maxsplit=1)[0].strip()
    return re.sub(r"\s+", " ", query)[:500]


def _abstract_from_openalex(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, raw_positions in value.items():
        if not isinstance(raw_positions, list):
            continue
        positions.extend((int(position), str(word)) for position in raw_positions if isinstance(position, int))
    return " ".join(word for _position, word in sorted(positions))


def _supplemental_queries(seed_snapshot: dict[str, Any], fallback: str) -> list[str]:
    """Derive compact research queries from visible headings without domain hard-coding."""

    queries: list[str] = []
    heading = re.compile(
        r"^(?:愿景[一二三四五六七八九十百\d]+|vision\s+\d+|trend\s+\d+|topic\s+\d+)\s*[:：-]\s*(.+)$",
        re.IGNORECASE,
    )
    for seed in seed_snapshot.get("seeds") or []:
        if not isinstance(seed, dict):
            continue
        for line in str(seed.get("content") or "").splitlines():
            match = heading.match(line.strip())
            if not match:
                continue
            compact = re.split(r"[，,；;。.!?！？]", match.group(1), maxsplit=1)[0].strip()
            if re.search(r"[\u3400-\u9fff]", compact):
                compact = re.split(
                    r"(?:突破|将|进入|重构|深度|走向|实现|开启|带来|迈向|成为|融合|交融)",
                    compact,
                    maxsplit=1,
                )[0].strip()
            if len(compact) >= 3 and compact not in queries:
                queries.append(compact[:100])
            if len(queries) >= 4:
                break
    if not queries:
        queries.append(fallback[:160])
    return queries


@dataclass
class LiteratureDiscoveryService:
    """Reuse AutoSci Semantic Scholar discovery with public API fallbacks."""

    workspace_root: Path
    backend: Callable[..., dict[str, Any]] = discover_literature
    timeout_seconds: int = DEFAULT_FETCH_TIMEOUT_SECONDS
    limit: int = 8
    urlopen: Callable[..., Any] = urllib.request.urlopen
    clock: Callable[[], str] = _utc_now

    service_id: str = DISCOVERY_SERVICE_ID
    service_version: str = SERVICE_VERSION

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()

    def _open_json(self, url: str) -> tuple[dict[str, Any], str]:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "OpenSolar-AutoSci/1.0"},
            method="GET",
        )
        try:
            with self.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(DEFAULT_PROVIDER_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise ResearchOperatorError(
                f"Public discovery provider returned HTTP {exc.code}",
                error_type="provider_rate_limited" if exc.code == 429 else "provider_http_error",
            ) from exc
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise ResearchOperatorError(
                f"Public discovery provider failed: {type(exc).__name__}: {exc}",
                error_type="provider_unavailable",
            ) from exc
        if len(body) > DEFAULT_PROVIDER_MAX_BYTES:
            raise ResearchOperatorError("Discovery response exceeds the size limit", error_type="provider_contract")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchOperatorError("Discovery provider returned invalid JSON", error_type="provider_contract") from exc
        if not isinstance(payload, dict):
            raise ResearchOperatorError("Discovery provider returned a non-object response", error_type="provider_contract")
        return payload, _sha256(body)

    def _openalex(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"search": query, "per-page": self.limit, "select": "id,doi,title,publication_year,primary_location,authorships,abstract_inverted_index"}
        )
        payload, response_hash = self._open_json(url)
        candidates: list[dict[str, Any]] = []
        for raw in payload.get("results") or []:
            if not isinstance(raw, dict) or not str(raw.get("title") or "").strip():
                continue
            primary = raw.get("primary_location") if isinstance(raw.get("primary_location"), dict) else {}
            source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
            authors = [
                str((item.get("author") or {}).get("display_name") or "")
                for item in raw.get("authorships") or []
                if isinstance(item, dict) and isinstance(item.get("author"), dict)
            ]
            canonical = str(raw.get("doi") or raw.get("id") or "")
            candidates.append(
                {
                    "source_id": canonical or f"openalex:{len(candidates) + 1}",
                    "canonical_id": canonical,
                    "title": str(raw.get("title") or ""),
                    "url": str(raw.get("doi") or primary.get("landing_page_url") or raw.get("id") or ""),
                    "provider": "openalex",
                    "metadata": {
                        "year": raw.get("publication_year"),
                        "venue": str(source.get("display_name") or ""),
                        "authors": [item for item in authors if item],
                    },
                    "provenance": {"provider": "openalex", "query": query, "discovered_at": self.clock()},
                    "content_summary": _abstract_from_openalex(raw.get("abstract_inverted_index")),
                }
            )
        return candidates, {"provider": "openalex", "request_url": url, "response_sha256": response_hash}

    def _crossref(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {
                "query.bibliographic": query,
                "rows": self.limit,
                "select": "DOI,title,URL,author,published,container-title,abstract,type",
            }
        )
        payload, response_hash = self._open_json(url)
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        candidates: list[dict[str, Any]] = []
        for raw in message.get("items") or []:
            if not isinstance(raw, dict):
                continue
            raw_titles = raw.get("title") if isinstance(raw.get("title"), list) else []
            title = str(raw_titles[0] if raw_titles else "").strip()
            if not title:
                continue
            doi = str(raw.get("DOI") or "").strip()
            published = raw.get("published") if isinstance(raw.get("published"), dict) else {}
            date_parts = published.get("date-parts") if isinstance(published.get("date-parts"), list) else []
            year = date_parts[0][0] if date_parts and isinstance(date_parts[0], list) and date_parts[0] else None
            authors = [
                " ".join(filter(None, (str(item.get("given") or "").strip(), str(item.get("family") or "").strip())))
                for item in raw.get("author") or []
                if isinstance(item, dict)
            ]
            abstract = re.sub(r"<[^>]+>", " ", str(raw.get("abstract") or ""))
            candidates.append(
                {
                    "source_id": f"doi:{doi}" if doi else f"crossref:{len(candidates) + 1}",
                    "canonical_id": doi or str(raw.get("URL") or ""),
                    "title": title,
                    "url": str(raw.get("URL") or (f"https://doi.org/{doi}" if doi else "")),
                    "provider": "crossref",
                    "metadata": {
                        "year": year,
                        "venue": str((raw.get("container-title") or [""])[0]),
                        "authors": [item for item in authors if item],
                        "type": str(raw.get("type") or ""),
                    },
                    "provenance": {"provider": "crossref", "query": query, "discovered_at": self.clock()},
                    "content_summary": re.sub(r"\s+", " ", abstract).strip(),
                }
            )
        return candidates, {"provider": "crossref", "request_url": url, "response_sha256": response_hash}

    def _wikipedia(self, queries: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        response_hashes: list[str] = []
        request_urls: list[str] = []
        for query in queries[:3]:
            language = "zh" if re.search(r"[\u3400-\u9fff]", query) else "en"
            url = f"https://{language}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
                {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrlimit": 2,
                    "prop": "extracts|info",
                    "exintro": 1,
                    "explaintext": 1,
                    "inprop": "url",
                    "format": "json",
                    "formatversion": 2,
                }
            )
            payload, response_hash = self._open_json(url)
            response_hashes.append(response_hash)
            request_urls.append(url)
            raw_query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
            for raw in raw_query.get("pages") or []:
                if not isinstance(raw, dict) or raw.get("missing"):
                    continue
                title = str(raw.get("title") or "").strip()
                page_id = str(raw.get("pageid") or "").strip()
                if not title or not page_id:
                    continue
                candidates.append(
                    {
                        "source_id": f"wikipedia:{language}:{page_id}",
                        "canonical_id": f"wikipedia:{language}:{page_id}",
                        "title": title,
                        "url": str(raw.get("fullurl") or f"https://{language}.wikipedia.org/?curid={page_id}"),
                        "provider": f"wikipedia_{language}",
                        "metadata": {"page_id": page_id, "language": language},
                        "provenance": {"provider": f"wikipedia_{language}", "query": query, "discovered_at": self.clock()},
                        "content_summary": str(raw.get("extract") or "")[:20_000],
                    }
                )
        return candidates, {
            "provider": "wikipedia",
            "request_urls": request_urls,
            "response_sha256": stable_json_sha256(response_hashes),
        }

    def _semantic_scholar(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
        progress = self.workspace_root / "service-evidence" / "discovery" / "semantic-scholar-progress.json"
        raw = self.backend(
            query=query,
            mode="topic",
            limit=self.limit,
            wiki_root=self.workspace_root / "wiki",
            workspace_root=self.workspace_root,
            repository_root=self.workspace_root,
            allow_network_fetch=True,
            progress_path=progress,
        )
        if not isinstance(raw, dict):
            raise ResearchOperatorError("AutoSci discovery backend returned a non-object response", error_type="provider_contract")
        candidates: list[dict[str, Any]] = []
        for item in raw.get("candidates") or []:
            if not isinstance(item, dict) or not str(item.get("title") or "").strip():
                continue
            canonical = str(item.get("arxiv_id") or item.get("paperId") or item.get("candidate_id") or "")
            candidates.append(
                {
                    "source_id": str(item.get("candidate_id") or canonical or f"s2:{len(candidates) + 1}"),
                    "canonical_id": canonical,
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("source_ref") or item.get("url") or ""),
                    "provider": "semantic_scholar",
                    "metadata": {
                        "year": item.get("year"),
                        "venue": str(item.get("venue") or ""),
                        "authors": list(item.get("authors") or []),
                        "citation_count": int(item.get("citation_count") or 0),
                        "source_channels": list(item.get("source_channels") or []),
                    },
                    "provenance": {
                        "provider": "semantic_scholar",
                        "query": query,
                        "discovered_at": self.clock(),
                        "source_channels": list(item.get("source_channels") or []),
                    },
                    "content_summary": str(item.get("abstract") or item.get("tldr") or ""),
                }
            )
        trace = {
            "provider": "semantic_scholar",
            "status": str(raw.get("status") or "unknown"),
            "response_sha256": stable_json_sha256(raw),
            "progress_path": _display_path(progress, self.workspace_root) if progress.exists() else "",
        }
        return candidates, trace, [str(item) for item in raw.get("limitations") or [] if str(item).strip()]

    def __call__(self, *, seed_snapshot: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        query = _topic_from_snapshot(seed_snapshot, payload)
        if not query:
            raise ResearchOperatorError("Source discovery requires a non-empty query", error_type="invalid_input")
        request_hash = stable_json_sha256(
            {
                "service_id": self.service_id,
                "service_version": self.service_version,
                "query": query,
                "limit": self.limit,
                "seed_snapshot_sha256": stable_json_sha256(seed_snapshot),
            }
        )
        candidates: list[dict[str, Any]] = []
        limitations: list[str] = []
        traces: list[dict[str, Any]] = []
        for seed in seed_snapshot.get("seeds") or []:
            if not isinstance(seed, dict) or str(seed.get("seed_kind") or "") != "url":
                continue
            source_id = f"url:{str(seed.get('content_sha256') or seed.get('sha256') or '')[:24]}"
            candidates.append(
                {
                    "source_id": source_id,
                    "canonical_id": str(seed.get("final_url") or seed.get("source") or source_id),
                    "title": str(seed.get("title") or "Fetched web source"),
                    "url": str(seed.get("final_url") or seed.get("source") or ""),
                    "provider": str(seed.get("provider") or "bounded_http"),
                    "metadata": {
                        "fetched_at": str(seed.get("fetched_at") or ""),
                        "content_type": str(seed.get("content_type") or ""),
                        "content_sha256": str(seed.get("content_sha256") or seed.get("sha256") or ""),
                        "raw_sha256": str(seed.get("raw_sha256") or ""),
                        "archive_path": str(seed.get("archive_path") or ""),
                    },
                    "provenance": {
                        "provider": str(seed.get("provider") or "bounded_http"),
                        "query": query,
                        "fetched_at": str(seed.get("fetched_at") or ""),
                    },
                    "content_summary": str(seed.get("content") or "")[:20_000],
                }
            )
        try:
            semantic, trace, warnings = self._semantic_scholar(query)
            candidates.extend(semantic)
            traces.append(trace)
            limitations.extend(warnings)
        except ResearchOperatorError as exc:
            limitations.append(f"Semantic Scholar fallback boundary: {exc.error_type}: {exc}")
            traces.append({"provider": "semantic_scholar", "status": "failed", "error_type": exc.error_type})
        has_fetched_url = any(
            isinstance(seed, dict) and str(seed.get("seed_kind") or "") == "url"
            for seed in seed_snapshot.get("seeds") or []
        )
        if has_fetched_url and len(candidates) < 4:
            try:
                wikipedia, trace = self._wikipedia(_supplemental_queries(seed_snapshot, query))
                candidates.extend(wikipedia)
                traces.append(trace)
            except ResearchOperatorError as exc:
                limitations.append(f"Wikipedia fallback boundary: {exc.error_type}: {exc}")
                traces.append({"provider": "wikipedia", "status": "failed", "error_type": exc.error_type})
        if len(candidates) < 3:
            try:
                openalex, trace = self._openalex(query)
                candidates.extend(openalex)
                traces.append(trace)
            except ResearchOperatorError as exc:
                limitations.append(f"OpenAlex fallback boundary: {exc.error_type}: {exc}")
                traces.append({"provider": "openalex", "status": "failed", "error_type": exc.error_type})
        if len(candidates) < 3:
            try:
                crossref, trace = self._crossref(query)
                candidates.extend(crossref)
                traces.append(trace)
            except ResearchOperatorError as exc:
                limitations.append(f"Crossref fallback boundary: {exc.error_type}: {exc}")
                traces.append({"provider": "crossref", "status": "failed", "error_type": exc.error_type})
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate.get("canonical_id") or candidate.get("url") or candidate.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            candidate["candidate_sha256"] = stable_json_sha256(candidate)
            candidate["query"] = query
            deduped.append(candidate)
            if len(deduped) >= self.limit + 1:
                break
        if not deduped:
            raise ResearchOperatorError(
                "All configured public discovery providers returned no traceable sources",
                error_type="provider_unavailable",
            )
        response_payload = {
            "schema": "autosci_source_discovery_service.v1",
            "service_id": self.service_id,
            "service_version": self.service_version,
            "request_sha256": request_hash,
            "query": query,
            "provider_traces": traces,
            "candidate_count": len(deduped),
            "candidate_hashes": [str(item["candidate_sha256"]) for item in deduped],
            "created_at": self.clock(),
            "limitations": limitations,
        }
        response_hash = stable_json_sha256(response_payload)
        archive_path = self.workspace_root / "service-evidence" / "discovery" / f"{response_hash}.json"
        archive_hash = _write_json(archive_path, response_payload)
        providers = sorted({str(item.get("provider") or "unknown") for item in deduped})
        return {
            "service_id": self.service_id,
            "service_version": self.service_version,
            "request_sha256": request_hash,
            "response_sha256": response_hash,
            "trace": "production:" + "+".join(providers),
            "query": query,
            "candidates": deduped,
            "provider_usage": [
                {
                    "provider": provider,
                    "model": "public_search_api",
                    "usage_kind": "provider_api",
                    "request_sha256": request_hash,
                    "response_sha256": response_hash,
                    "service_id": self.service_id,
                    "service_version": self.service_version,
                    "archive_path": _display_path(archive_path, self.workspace_root),
                    "archive_sha256": archive_hash,
                }
                for provider in providers
            ],
            "limitations": limitations,
        }


def _json_from_model_content(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        value = "\n".join(
            str(item.get("text") or "") for item in value if isinstance(item, dict) and item.get("text")
        )
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResearchOperatorError("Research model returned invalid JSON", error_type="provider_contract") from exc
    if not isinstance(payload, dict):
        raise ResearchOperatorError("Research model returned a non-object JSON value", error_type="provider_contract")
    return payload


@dataclass(frozen=True)
class _ProviderRoute:
    provider: str
    endpoint: str
    model: str
    api_key: str


@dataclass
class ResearchModelService:
    """Call configured OpenAI-compatible providers for bounded JSON outputs."""

    workspace_root: Path
    routes: list[_ProviderRoute]
    timeout_seconds: int = 60
    urlopen: Callable[..., Any] = urllib.request.urlopen
    clock: Callable[[], str] = _utc_now

    service_id: str = MODEL_SERVICE_ID
    service_version: str = SERVICE_VERSION
    _unavailable_providers: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()

    @classmethod
    def from_environment(cls, workspace_root: Path) -> "ResearchModelService":
        requested_model = str(os.environ.get("AUTOSCI_RESEARCH_LLM_MODEL") or "").strip()
        explicit_provider = str(os.environ.get("AUTOSCI_RESEARCH_LLM_PROVIDER") or "").strip().lower()
        allow_openai_fallback = str(
            os.environ.get("AUTOSCI_RESEARCH_ALLOW_OPENAI_FALLBACK") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        routes: list[_ProviderRoute] = []
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        custom_key = os.environ.get("AUTOSCI_REVIEW_LLM_API_KEY", "").strip()
        custom_endpoint = os.environ.get("AUTOSCI_RESEARCH_LLM_ENDPOINT", "").strip()
        if custom_endpoint and custom_key:
            custom_model = requested_model or DEFAULT_OPENROUTER_RESEARCH_MODEL
            routes.append(
                _ProviderRoute(explicit_provider or "openai_compatible", custom_endpoint, custom_model, custom_key)
            )

        openrouter_model = requested_model or DEFAULT_OPENROUTER_RESEARCH_MODEL
        if "/" not in openrouter_model:
            openrouter_model = f"openai/{openrouter_model}"
        openai_model = requested_model or DEFAULT_OPENAI_RESEARCH_MODEL
        if openai_model.startswith("openai/"):
            openai_model = openai_model.split("/", 1)[1]

        # Research traffic is OpenRouter-first and OpenAI is opt-in.  In
        # particular, legacy live-review variables must not silently bind the
        # OpenAI account or its expensive model to production research.
        if explicit_provider in {"", "openrouter"} and openrouter_key:
            routes.append(
                _ProviderRoute(
                    "openrouter",
                    "https://openrouter.ai/api/v1/chat/completions",
                    openrouter_model,
                    openrouter_key,
                )
            )
        if explicit_provider == "openai" and openai_key:
            routes.append(
                _ProviderRoute("openai", "https://api.openai.com/v1/chat/completions", openai_model, openai_key)
            )
        elif allow_openai_fallback and openai_key:
            routes.append(
                _ProviderRoute("openai", "https://api.openai.com/v1/chat/completions", openai_model, openai_key)
            )
        return cls(workspace_root=workspace_root, routes=routes)

    def _prompt(self, node_id: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        task_contract = kwargs.get("task_contract") if isinstance(kwargs.get("task_contract"), dict) else {}
        language = str((task_contract.get("deliverable") or {}).get("language") or "preserve_user_request")
        system = (
            "You are the bounded OpenSolar AutoSci research model. Return only one JSON object. "
            "Use only the supplied validated evidence, preserve source identifiers exactly, never invent sources, "
            f"and write the requested deliverable in language={language}."
        )
        if node_id == "evidence_synthesis":
            sources = [
                {
                    "source_id": str(item.get("source_id") or ""),
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "content_summary": str(item.get("content_summary") or "")[:20_000],
                    "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                }
                for item in kwargs.get("validated_sources") or []
                if isinstance(item, dict)
            ]
            user = {
                "node_id": node_id,
                "complete_user_request": str(task_contract.get("user_intent") or ""),
                "validated_sources": sources,
                "required_output": {
                    "claims": [
                        {
                            "claim_id": "claim-001",
                            "text": "source-grounded finding",
                            "evidence_ids": ["one or more exact source_id values"],
                            "uncertainty": "low|medium|high",
                            "limitations": [],
                        }
                    ],
                    "limitations": [],
                },
                "quality_requirements": [
                    "Cover the complete user request.",
                    "For surveys, compare performance trade-offs and identify open research problems.",
                    "For webpage research, use the fetched webpage as evidence and distinguish supplemental sources.",
                    "Produce at least four substantive claims when evidence supports them.",
                ],
            }
        elif node_id == "report_draft":
            synthesis = kwargs.get("evidence_synthesis") if isinstance(kwargs.get("evidence_synthesis"), dict) else {}
            user = {
                "node_id": node_id,
                "complete_user_request": str(task_contract.get("user_intent") or ""),
                "deliverable_requirements": kwargs.get("deliverable_requirements") or {},
                "grounded_claims": synthesis.get("claims") or [],
                "required_output": {
                    "report": {
                        "title": "specific report title",
                        "body": "complete structured Markdown report body",
                        "sections": [{"title": "section title", "body": "section body"}],
                        "conclusions": [
                            {
                                "conclusion_id": "conclusion-001",
                                "text": "bounded conclusion",
                                "evidence_ids": ["one or more exact claim_id values"],
                            }
                        ],
                    },
                    "limitations": [],
                },
                "quality_requirements": [
                    "The body must be non-empty, clearly structured Markdown and directly answer the whole request.",
                    "For a survey, include an explicit performance trade-offs section and an open research problems section.",
                    "For Chinese requests, write the report in Chinese.",
                    "State evidence limitations without inventing methods or conclusions.",
                ],
            }
        elif node_id == "independent_review":
            user = {
                "node_id": node_id,
                "complete_user_request": str(task_contract.get("user_intent") or ""),
                "report_draft": kwargs.get("report_draft") or {},
                "source_validation": kwargs.get("source_validation") or {},
                "required_output": {
                    "findings": [
                        {
                            "finding_id": "review-001",
                            "severity": "low|medium|high|critical",
                            "category": "evidence|relevance|structure|language|truthfulness",
                            "message": "specific finding",
                        }
                    ],
                    "verdict_suggestion": "accept|revise|reject",
                    "limitations": [],
                },
                "review_rules": [
                    "Accept only a non-empty relevant report whose conclusions are grounded in supplied source lineage.",
                    "For surveys, require performance trade-offs and open research problems.",
                    "For Chinese requests, require Chinese output.",
                    "Do not create a high-severity finding merely because the evidence has explicit limitations.",
                ],
            }
        else:
            raise ResearchOperatorError(f"Unsupported production model node: {node_id}", error_type="invalid_input")
        return system, user

    def _invoke(self, route: _ProviderRoute, node_id: str, system: str, user: dict[str, Any]) -> dict[str, Any]:
        if not route.endpoint.lower().startswith("https://"):
            raise ResearchOperatorError("Research model endpoint must use https", error_type="provider_configuration")
        request_payload = {
            "model": route.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False, sort_keys=True)},
            ],
            "response_format": {"type": "json_object"},
        }
        request_body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        request_hash = _sha256(request_body)
        headers = {"Authorization": f"Bearer {route.api_key}", "Content-Type": "application/json"}
        if route.provider == "openrouter":
            headers.update({"HTTP-Referer": "https://local.solar/autosci", "X-Title": "Solar AutoSci Research"})
        request = urllib.request.Request(route.endpoint, data=request_body, headers=headers, method="POST")
        try:
            with self.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(DEFAULT_PROVIDER_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            retry_after = str(exc.headers.get("Retry-After") or "") if exc.headers else ""
            detail = f"provider={route.provider} status={exc.code} stage={node_id}"
            if retry_after:
                detail += f" retry_after={retry_after}"
            raise ResearchOperatorError(
                detail,
                error_type="provider_rate_limited" if exc.code == 429 else "provider_http_error",
            ) from exc
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise ResearchOperatorError(
                f"provider={route.provider} stage={node_id} failure={type(exc).__name__}",
                error_type="provider_unavailable",
            ) from exc
        if len(body) > DEFAULT_PROVIDER_MAX_BYTES:
            raise ResearchOperatorError("Research model response exceeds the size limit", error_type="provider_contract")
        response_hash = _sha256(body)
        try:
            transport = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchOperatorError("Research model returned invalid transport JSON", error_type="provider_contract") from exc
        if not isinstance(transport, dict):
            raise ResearchOperatorError("Research model transport must be an object", error_type="provider_contract")
        choices = transport.get("choices") if isinstance(transport.get("choices"), list) else []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        payload = _json_from_model_content(message.get("content"))
        usage = transport.get("usage") if isinstance(transport.get("usage"), dict) else {}
        provider_usage = {
            "provider": route.provider,
            "model": str(transport.get("model") or route.model),
            "usage_kind": "llm",
            "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            "request_sha256": request_hash,
            "response_sha256": response_hash,
            "service_id": self.service_id,
            "service_version": self.service_version,
        }
        archive_payload = {
            "schema": "autosci_research_model_exchange.v1",
            "service_id": self.service_id,
            "service_version": self.service_version,
            "provider": route.provider,
            "model": provider_usage["model"],
            "node_id": node_id,
            "created_at": self.clock(),
            "request_sha256": request_hash,
            "response_sha256": response_hash,
            "request": request_payload,
            "response": transport,
        }
        archive_path = self.workspace_root / "service-evidence" / "model" / f"{node_id}-{response_hash}.json"
        archive_hash = _write_json(archive_path, archive_payload)
        provider_usage["archive_path"] = _display_path(archive_path, self.workspace_root)
        provider_usage["archive_sha256"] = archive_hash
        payload["provider"] = route.provider
        payload["model"] = provider_usage["model"]
        payload["provider_usage"] = [provider_usage]
        return payload

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        node_id = str(kwargs.get("node_id") or "")
        if not self.routes:
            raise ResearchOperatorError("No configured production research model provider is available", error_type="provider_unavailable")
        system, user = self._prompt(node_id, kwargs)
        errors: list[str] = []
        for route in self.routes:
            if route.provider in self._unavailable_providers:
                continue
            try:
                payload = self._invoke(route, node_id, system, user)
                if errors:
                    limitations = [str(item) for item in payload.get("limitations") or [] if str(item).strip()]
                    limitations.extend(f"Provider fallback: {item}" for item in errors)
                    payload["limitations"] = limitations
                    payload["provider_fallbacks"] = list(errors)
                return payload
            except ResearchOperatorError as exc:
                event = f"{self.clock()} provider={route.provider} stage={node_id} error_type={exc.error_type} summary={exc}"
                errors.append(event)
                if exc.error_type not in {"provider_rate_limited", "provider_http_error", "provider_unavailable"}:
                    raise
                self._unavailable_providers.add(route.provider)
        raise ResearchOperatorError("; ".join(errors)[:500], error_type="provider_unavailable")


def configured_secret_values(*, active_model_providers: set[str] | None = None) -> dict[str, str]:
    """Return configured provider secrets in memory; callers must never serialize them."""

    names = (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "AUTOSCI_REVIEW_LLM_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
    )
    values = {name: value for name in names if (value := os.environ.get(name, "").strip())}
    if active_model_providers is not None:
        if "openai" not in active_model_providers:
            values.pop("OPENAI_API_KEY", None)
        if "openrouter" not in active_model_providers:
            values.pop("OPENROUTER_API_KEY", None)
    return values


def production_services_from_environment(
    *,
    workspace_root: Path,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose general production services while preserving deterministic injection."""

    root = Path(workspace_root).resolve()
    model = ResearchModelService.from_environment(root)
    active_model_providers = {route.provider for route in model.routes}
    services: dict[str, Any] = {
        "fetch_url": BoundedUrlFetcher(root),
        "discover_sources": LiteratureDiscoveryService(root),
        "model_generate": model,
        "review_model_generate": model,
        "secret_values": configured_secret_values(active_model_providers=active_model_providers),
        "service_metadata": {
            "fetch_url": {"service_id": FETCH_SERVICE_ID, "version": SERVICE_VERSION},
            "discover_sources": {"service_id": DISCOVERY_SERVICE_ID, "version": SERVICE_VERSION},
            "model_generate": {"service_id": MODEL_SERVICE_ID, "version": SERVICE_VERSION},
            "review_model_generate": {"service_id": MODEL_SERVICE_ID, "version": SERVICE_VERSION},
        },
    }
    services.update(dict(overrides or {}))
    return services
