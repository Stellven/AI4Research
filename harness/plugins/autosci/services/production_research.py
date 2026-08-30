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
import math
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
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
IDEA_SERVICE_ID = "autosci-production-idea-generator"
SERVICE_VERSION = "1.0.0"
DEFAULT_FETCH_TIMEOUT_SECONDS = 30
DEFAULT_FETCH_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_FETCH_MAX_REDIRECTS = 5
DEFAULT_EXTRACTED_TEXT_CHARS = 120_000
MIN_DISCOVERY_PROVIDERS = 2
_RELEVANCE_GENERIC_TERMS = {
    "about", "analysis", "analyze", "assessment", "based", "collect", "compare", "comparison",
    "current", "data", "demonstrate", "describe", "discuss", "effect", "evaluate", "evidence",
    "finding", "findings", "identify", "investigate", "literature", "main", "method", "methods",
    "deliverable", "deliverables", "paper", "papers", "produce", "relevant", "report", "research",
    "result", "results", "review", "source", "sources", "study", "studies", "synthesize", "systematic",
    "using", "work",
}
_DISCOVERY_NON_TOPIC_SCOPE_TERMS = {
    "answer", "auditable", "chain", "comprehensive", "end", "explicit", "extensible",
    "future", "landscape", "off", "one", "oriented", "provenance", "supported",
    "technical", "traceability", "type", "workflow",
}
_DISCOVERY_TERM_CANONICAL = {
    "compress": "compression",
    "compressed": "compression",
    "evict": "eviction",
    "evicted": "eviction",
    "prune": "sparsification",
    "pruning": "sparsification",
    "quantize": "quantization",
    "quantized": "quantization",
    "select": "selection",
    "selected": "selection",
    "sparse": "sparsification",
    "sparsity": "sparsification",
}
_DISCOVERY_PROVIDER_ALIASES = {
    "compression": "compressed",
    "eviction": "evict heavy-hitter retention",
    "quantization": "quantized low-bit",
    "selection": "token retention",
    "sparsification": "sparse pruning",
}
_DISCOVERY_COVERAGE_RECOVERY_PROVIDERS = (
    ("arxiv", "_arxiv", "arXiv"),
    ("openalex", "_openalex", "OpenAlex"),
)
_RELEVANCE_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "between", "by", "can", "could", "do", "does",
    "for", "from", "how", "in", "into", "is", "it", "its", "of", "on", "or", "our", "that",
    "the", "their", "these", "this", "through", "to", "use", "used", "versus", "we", "what",
    "when", "where", "which", "with", "without",
}
_XML_ENTITY_DECLARATION_RE = re.compile(rb"<!(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_ARXIV_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 90
DEFAULT_PROVIDER_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_PROVIDER_MAX_ATTEMPTS = 3
DEFAULT_PROVIDER_RETRY_MAX_SLEEP_SECONDS = 5.0
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


def _fs_path(path: Path) -> str:
    resolved = str(Path(path).resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def _mkdir(path: Path) -> None:
    os.makedirs(_fs_path(path), exist_ok=True)


def _write_bytes(path: Path, body: bytes) -> None:
    _mkdir(path.parent)
    with open(_fs_path(path), "wb") as handle:
        handle.write(body)


def _read_bytes(path: Path) -> bytes:
    with open(_fs_path(path), "rb") as handle:
        return handle.read()


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_bytes(path, body.encode("utf-8"))
    return _sha256(_read_bytes(path))


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
        _write_bytes(archive_path, body)
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


# This module is imported both as part of the package and as a bare module by
# the autosci_bridge subprocess, which runs without the repo root on sys.path.
# The absolute "harness.*" form fails in that second case, so fall back to
# loading the helper directly by path. It is never silently skipped: a failure
# to import here must raise, or the provider query would quietly go back to
# being the whole user request.
try:  # package import
    from ..operators.research_synthesis.base import distill_search_query
except ImportError:  # bare-module import by the bridge subprocess
    import importlib.util as _ilu
    import sys as _sys
    from pathlib import Path as _Path

    _base_path = _Path(__file__).resolve().parents[1] / "operators" / "research_synthesis" / "base.py"
    _spec = _ilu.spec_from_file_location("_autosci_research_synthesis_base", _base_path)
    if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
        raise
    _base_mod = _ilu.module_from_spec(_spec)
    # base.py defines a @dataclass, and dataclass processing looks the defining
    # module up in sys.modules; without this registration it raises
    # AttributeError: 'NoneType' object has no attribute '__dict__'.
    _sys.modules[_spec.name] = _base_mod
    _spec.loader.exec_module(_base_mod)
    distill_search_query = _base_mod.distill_search_query


_DELIVERABLE_MARKER_RE = re.compile(
    r"\b(?:produce|source-linked|evidence\s+ids?|scholarly\s+sources?|"
    r"independent\s+review|conclusions|limitations|deliverables?)\b",
    re.IGNORECASE,
)


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
    has_topic_seed = any(
        isinstance(item, dict) and str(item.get("seed_kind") or "") in {"topic", "research_brief"}
        for item in seeds
    )
    # A fetched page title is normally a higher quality public-search query
    # than appending the full user instruction (which can swamp provider
    # relevance ranking). Topic-only runs first distill the subject from
    # common research-instruction phrasing while preserving the user's domain.
    # Only a fetched PAGE TITLE is already a good provider query. An inline
    # topic/research_brief seed carries the user's own request text, so it needs
    # the same distillation as the raw intent -- otherwise the frozen pack's
    # topic seed re-supplies the full instruction and the search is buried again.
    from_page_title = bool(titles[:1]) and not inline[:1]
    query = " ".join(inline[:1] or titles[:1] or [intent]).strip()
    # A planner-owned Required coverage clause is the cleanest retrieval query:
    # it retains the named subject without the surrounding workflow request.
    # The full intent remains authoritative for the later relevance gate.  In
    # particular, do not send providers prose such as "Discover a ranked,
    # reviewable ... source set"; public bibliographic search ranks those
    # instruction words and can return unrelated papers even when the scope is
    # otherwise exact.
    authoritative_clauses = _authoritative_scope_clauses(intent)
    topical_clauses = _topical_scope_clauses(intent)
    if topical_clauses and not from_page_title:
        query = " ".join(topical_clauses)
        query = re.sub(
            r"^(?:compare|evaluate|assess|analy[sz]e|investigate|review)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
    if not authoritative_clauses and (has_topic_seed or not titles):
        match = re.search(
            r"\b(?:survey|review|report|analysis|brief)\s+(?:on|about|for)\s+(.+)",
            query,
            flags=re.IGNORECASE,
        )
        if match:
            query = match.group(1).strip()
        query = re.split(
            r"(?:\.\s+|\n+)(?:cover|include|discuss|address|compare|state|with)\b",
            query,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
    elif not authoritative_clauses:
        query = re.sub(r"^(?:survey|review|research|analy[sz]e|synthesize)\s+", "", query, flags=re.IGNORECASE)
        query = re.split(r"[,;]", query, maxsplit=1)[0].strip()
    # Planner-appended coverage clauses are evaluation authority, not search
    # keywords. Keep them available to the relevance gate through user_intent,
    # but do not send the whole contract to public search providers.
    query = re.split(
        r"\s*Authoritative discovery scope\s*:\s*",
        query,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    query = re.sub(r"\s+", " ", query).strip()
    # The phrase patterns above only catch "survey/review on X" shapes. A request
    # like "Research and compare CRISPR ... Produce a source-linked report with
    # evidence IDs, ..." matches none of them and previously went to the
    # providers whole, which buried the topic: OpenAlex returned 4 hits (image
    # profiling, bibliometrics) instead of 939 CRISPR papers. Token-distil only
    # when the instruction survived, so inputs the patterns already handle keep
    # their cleaner phrasing, and never touch a fetched page title.
    if not authoritative_clauses and not from_page_title and _DELIVERABLE_MARKER_RE.search(query):
        distilled = distill_search_query(query)
        if distilled:
            query = distilled
    return query[:500]


def _candidate_key(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("canonical_id") or candidate.get("url") or candidate.get("title") or ""
    ).strip().lower()


def _candidate_title_key(candidate: dict[str, Any]) -> str:
    """Normalized title, used to collapse the same work seen twice.

    Identifier dedup alone is not enough: a preprint and its published version
    carry different DOIs, and providers disagree on punctuation and case, so the
    same paper was arriving twice and spending two slots of the budget.
    """
    return re.sub(r"[^a-z0-9]+", " ", str(candidate.get("title") or "").lower()).strip()


def _relevance_stem(token: str) -> str:
    """Apply a deliberately small, deterministic English inflection fold."""

    value = str(token or "").lower().strip()
    if len(value) > 5 and value.endswith("ies"):
        return value[:-3] + "y"
    if len(value) > 5 and value.endswith(("ches", "shes", "sses", "xes", "zes")):
        return value[:-2]
    if len(value) > 4 and value.endswith("s") and not value.endswith(("ss", "us", "is")):
        return value[:-1]
    return value


def _relevance_terms(value: Any, *, remove_generic: bool) -> set[str]:
    terms: set[str] = set()
    for raw in re.findall(r"[a-z0-9]+", str(value or "").lower()):
        if len(raw) < 2 or raw in _RELEVANCE_STOPWORDS:
            continue
        term = _relevance_stem(raw)
        if remove_generic and term in _RELEVANCE_GENERIC_TERMS:
            continue
        terms.add(term)
        canonical = _DISCOVERY_TERM_CANONICAL.get(raw) or _DISCOVERY_TERM_CANONICAL.get(term)
        if canonical:
            terms.add(canonical)
    return terms


def _candidate_relevance_text(candidate: dict[str, Any]) -> str:
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    return " ".join(
        str(value or "")
        for value in (
            candidate.get("title"),
            candidate.get("content_summary"),
            metadata.get("venue"),
            " ".join(str(item) for item in metadata.get("fields_of_study") or []),
        )
    )


def _coverage_anchor_items(clause: str) -> list[dict[str, Any]]:
    """Human required-coverage items, preserved as phrase-level anchors."""

    text = re.sub(r"\s+", " ", str(clause or "").replace("-", " ")).strip(" .;")
    text = re.sub(r"^the\s+comparison\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^(?:is\s+)?limited\s+to(?:\s+the)?(?:\s+named)?(?:\s+chemistr(?:y|ies))?\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^(?:must|should|shall)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^(?:compare|evaluate|assess|analy[sz]e|investigate|review)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    parts = [item.strip(" .;") for item in re.split(r"\s*[;,]\s*|\s+\band\b\s+", text) if item.strip()]
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for raw in parts:
        label = re.sub(r"^(?:and|or)\s+", "", raw, flags=re.IGNORECASE)
        # Scope nouns after chemistry names ("batteries for grid storage") are
        # not part of the chemistry anchor and let unrelated grid papers match.
        if re.search(r"\b(?:lithium|sodium|solid|sulfur)\b", label, re.IGNORECASE):
            label = re.split(r"\b(?:battery|batteries)\b", label, maxsplit=1, flags=re.IGNORECASE)[0]
        terms = tuple(sorted(
            _relevance_terms(label, remove_generic=True)
            - _DISCOVERY_NON_TOPIC_SCOPE_TERMS
            - {"battery", "batteries", "storage", "grid", "energy"}
        ))
        if not terms or terms in seen:
            continue
        seen.add(terms)
        items.append({"label": label.strip(), "terms": list(terms)})
    if items:
        return items
    terms = sorted(_relevance_terms(clause, remove_generic=True) - _DISCOVERY_NON_TOPIC_SCOPE_TERMS)
    return [{"label": clause.strip(), "terms": terms}] if terms else []


def _matched_anchor_items(group: dict[str, Any], candidate_terms: set[str]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for item in group.get("anchor_items") or []:
        terms = {str(term) for term in item.get("terms") or []}
        if terms and terms <= candidate_terms:
            matched.append({"label": str(item.get("label") or ""), "terms": sorted(terms)})
    return matched


def _coverage_anchor_groups(query: str) -> list[dict[str, Any]]:
    """Extract planner-preserved `Required coverage:` clauses as anchor groups.

    Each clause remains authoritative even when the planner repeats its exact
    terms in the base objective. Generic research/deliverable words are already
    removed by `_relevance_terms`; subtracting the base terms would erase every
    chemistry and criterion from a correctly scoped planner objective.
    """

    groups: list[dict[str, Any]] = []
    for clause in _topical_scope_clauses(query):
        anchor_items = _coverage_anchor_items(clause)
        terms = {term for item in anchor_items for term in item.get("terms", [])}
        # These are grammatical glue inside chemistry names, not useful
        # discriminators by themselves. `solid` and `sulfur` remain anchors.
        terms -= {"ion", "state", "battery", "storage", "energy"}
        if terms:
            groups.append(
                {
                    "group_id": f"coverage-{len(groups) + 1}",
                    "clause": clause,
                    "anchor_terms": sorted(terms),
                    "anchor_items": anchor_items,
                }
            )
    return groups


def _authoritative_scope_clauses(query: str) -> list[str]:
    """Return human topic clauses from the planner's discovery scope.

    Older planner output placed human prose after ``Required coverage:``.
    Current output puts deterministic verifier labels there and keeps the
    human-readable requirement before the marker.  Treating labels such as
    ``constraint_satisfied`` as search terms produced convincing but entirely
    off-topic provider results, so support both shapes explicitly.
    """

    text = str(query or "")
    marker = re.search(r"Authoritative discovery scope\s*:", text, re.IGNORECASE)
    if not marker:
        return []
    clauses: list[str] = []
    for raw_line in text[marker.end() :].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^-\s*\[[^\]]+\]\s*", "", line)
        parts = re.split(r"\s+Required coverage\s*:\s*", line, maxsplit=1, flags=re.IGNORECASE)
        description = parts[0].strip().rstrip(".;")
        required = parts[1].strip().rstrip(".;") if len(parts) == 2 else ""
        required_items = [item.strip() for item in re.split(r"[;,]", required) if item.strip()]
        verifier_labels = bool(required_items) and all(
            re.fullmatch(r"[a-z][a-z0-9_]*", item, re.IGNORECASE) and "_" in item
            for item in required_items
        )
        clause = description if verifier_labels or not required else required
        if clause:
            clauses.append(clause)
    return clauses


def _topical_scope_clauses(query: str) -> list[str]:
    """Keep discovery subjects while excluding workflow/report obligations."""

    topical: list[str] = []
    for clause in _authoritative_scope_clauses(query):
        terms = _relevance_terms(clause, remove_generic=True)
        if terms - _DISCOVERY_NON_TOPIC_SCOPE_TERMS:
            topical.append(clause)
    return topical


def _topical_scope_query(query: str) -> str:
    clauses = _topical_scope_clauses(query)
    if clauses:
        return re.sub(r"\s+", " ", " ".join(clauses)).strip()
    return re.split(
        r"\s*Authoritative discovery scope\s*:\s*",
        str(query or ""),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()


def _coverage_recovery_queries(query: str, audit: dict[str, Any]) -> list[str]:
    """Build bounded provider queries for aggregate coverage gaps."""

    context_parts = [
        clause
        for clause in _topical_scope_clauses(query)
        if len(_coverage_anchor_items(clause)) == 1
    ]
    context = re.sub(r"\s+", " ", " ".join(context_parts)).strip()
    queries: list[str] = []
    for group in audit.get("aggregate_coverage_missing") or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("missing_anchor_items") or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            alias_phrases = [
                _DISCOVERY_PROVIDER_ALIASES[term]
                for term in sorted(_relevance_terms(label, remove_generic=True))
                if term in _DISCOVERY_PROVIDER_ALIASES
            ]
            aliases = " ".join(dict.fromkeys(alias_phrases))
            candidate = re.sub(r"\s+", " ", f"{context} {label} {aliases}").strip()[:500]
            if candidate and candidate not in queries:
                queries.append(candidate)
    return queries[:5]


def apply_discovery_relevance_gate(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    minimum_relevant_candidates: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reject candidates that do not share enough topic signal with the query.

    This is intentionally lexical rather than model-backed: the result is
    deterministic, cheap, and every decision can be reproduced from the saved
    query terms and candidate record. Generic research/deliverable words do not
    count as relevance. A rich query requires two topic matches; a short query
    requires one. If filtering leaves only a small fraction of a larger result
    set, the entire shortlist remains incomplete instead of publishing a weak
    partial list as final.
    """

    subject_query = _topical_scope_query(query) or str(query or "")
    query_terms = _relevance_terms(subject_query, remove_generic=True)
    coverage_groups = _coverage_anchor_groups(query)
    requires_battery_domain = bool(coverage_groups) and "battery" in query_terms
    required_overlap = 2 if len(query_terms) >= 4 else 1
    raw_count = len(candidates)
    if minimum_relevant_candidates is None:
        # One result is enough when the provider only returned one. For a
        # larger pool, require a meaningful retained subset before finality.
        minimum_relevant_candidates = max(1, min(3, math.ceil(raw_count * 0.30)))
    minimum_relevant_candidates = max(1, int(minimum_relevant_candidates))

    accepted: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_text = _candidate_relevance_text(candidate)
        candidate_terms = _relevance_terms(candidate_text, remove_generic=False)
        matched = sorted(query_terms & candidate_terms)
        coverage_matches = []
        for group in coverage_groups:
            matched_items = _matched_anchor_items(group, candidate_terms)
            coverage_matches.append(
                {
                    "group_id": str(group["group_id"]),
                    "matched_anchor_terms": sorted(set(group["anchor_terms"]) & candidate_terms),
                    "matched_anchor_items": matched_items,
                }
            )
        unmatched_coverage_groups = [
            str(item["group_id"])
            for item in coverage_matches
            if not item["matched_anchor_items"]
        ]
        topic_threshold_met = bool(query_terms) and len(matched) >= required_overlap
        coverage_signal_met = not coverage_groups or any(
            item["matched_anchor_items"] for item in coverage_matches
        )
        battery_domain_met = (
            not requires_battery_domain
            or (
                "battery" in candidate_terms
                and not re.search(r"\b(?:not|non)\s+batter(?:y|ies)\b", candidate_text, re.IGNORECASE)
            )
        )
        # The shortlist is collectively comprehensive. Specialist papers need
        # not each cover every requested method family; aggregate coverage is
        # enforced below after per-candidate topical admission.
        is_relevant = topic_threshold_met and coverage_signal_met and battery_domain_met
        decision = {
            "candidate_id": str(candidate.get("source_id") or candidate.get("canonical_id") or ""),
            "canonical_id": str(candidate.get("canonical_id") or candidate.get("url") or ""),
            "title": str(candidate.get("title") or ""),
            "provider": str(candidate.get("provider") or "unknown"),
            "accepted": is_relevant,
            "matched_query_terms": matched,
            "matched_term_count": len(matched),
            "required_term_count": required_overlap,
            "coverage_group_matches": coverage_matches,
            "unmatched_coverage_groups": unmatched_coverage_groups,
            "reason": (
                "topic_term_threshold_met"
                if is_relevant
                else "required_coverage_anchor_missing"
                if topic_threshold_met and not coverage_signal_met
                else "required_battery_domain_missing"
                if topic_threshold_met and not battery_domain_met
                else "query_has_no_specific_topic_terms"
                if not query_terms
                else "insufficient_topic_term_overlap"
            ),
        }
        decisions.append(decision)
        if is_relevant:
            item = dict(candidate)
            item["relevance_gate"] = {
                "status": "accepted",
                "matched_query_terms": matched,
                "required_term_count": required_overlap,
                "coverage_group_matches": coverage_matches,
            }
            accepted.append(item)

    aggregate_missing: list[dict[str, Any]] = []
    if coverage_groups:
        accepted_terms = _relevance_terms(
            " ".join(_candidate_relevance_text(item) for item in accepted),
            remove_generic=False,
        )
        for group in coverage_groups:
            missing_items = [
                {"label": str(item.get("label") or ""), "terms": list(item.get("terms") or [])}
                for item in group.get("anchor_items") or []
                if not ({str(term) for term in item.get("terms") or []} <= accepted_terms)
            ]
            if missing_items:
                aggregate_missing.append(
                    {
                        "group_id": str(group["group_id"]),
                        "clause": str(group["clause"]),
                        "missing_anchor_items": missing_items,
                    }
                )
    gate_passed = bool(query_terms) and len(accepted) >= minimum_relevant_candidates and not aggregate_missing
    audit = {
        "schema": "autosci_discovery_relevance_audit.v1",
        "status": "passed" if gate_passed else "incomplete",
        "query": str(query),
        "subject_query": subject_query,
        "query_terms": sorted(query_terms),
        "gate_mode": "required_coverage" if coverage_groups else "topic_overlap",
        "authoritative_coverage_required": bool(coverage_groups),
        "coverage_anchor_groups": coverage_groups,
        "required_term_count_per_candidate": required_overlap,
        "minimum_relevant_candidates": minimum_relevant_candidates,
        "input_candidate_count": raw_count,
        "accepted_candidate_count": len(accepted),
        "rejected_candidate_count": raw_count - len(accepted),
        "aggregate_coverage_missing": aggregate_missing,
        "decisions": decisions,
        "blocking_reasons": (
            []
            if gate_passed
            else ["query_has_no_specific_topic_terms"]
            if not query_terms
            else ["authoritative_coverage_incomplete"]
            if aggregate_missing
            else [
                f"only {len(accepted)} candidate(s) met the deterministic relevance threshold; "
                f"{minimum_relevant_candidates} required"
            ]
        ),
    }
    # Do not leak a weak partial shortlist to a consumer that treats any
    # non-empty candidate list as final-ready. The audit retains those records.
    return (accepted if gate_passed else []), audit


def _select_candidates(
    seeded: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Take seeded sources first, then round-robin across discovery providers.

    Straight concatenation let whichever provider ran first fill the whole
    candidate budget, so a broad-but-poorly-ranked provider could crowd out the
    on-topic results a later provider had already returned. Round-robin gives
    every provider that answered the same shot at the budget, and the relevance
    gate downstream still decides what is admissible.
    """
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_titles: set[str] = set()

    def take(candidate: dict[str, Any]) -> bool:
        key = _candidate_key(candidate)
        if not key or key in seen:
            return False
        title_key = _candidate_title_key(candidate)
        if title_key and title_key in seen_titles:
            return False
        seen.add(key)
        if title_key:
            seen_titles.add(title_key)
        selected.append(candidate)
        return len(selected) >= limit

    for candidate in seeded:
        if take(candidate):
            return selected

    by_provider: dict[str, list[dict[str, Any]]] = {}
    for candidate in discovered:
        by_provider.setdefault(str(candidate.get("provider") or "unknown"), []).append(candidate)
    queues = list(by_provider.values())
    for index in range(max((len(queue) for queue in queues), default=0)):
        for queue in queues:
            if index < len(queue) and take(queue[index]):
                return selected
    return selected


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
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    max_attempts_per_provider: int = 2
    max_total_wait_seconds: float = 12.0
    _attempts: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _attempt_paths: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False)

    service_id: str = DISCOVERY_SERVICE_ID
    service_version: str = SERVICE_VERSION

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()

    def _record_discovery_attempt(
        self,
        *,
        provider: str,
        url: str,
        attempt: int,
        status: str,
        status_code: int,
        body: bytes,
        retry_wait_seconds: float,
        error_type: str = "",
        response_kind: str = "raw_http_body",
    ) -> dict[str, Any]:
        attempt_id = f"{len(self._attempts) + 1:03d}-{_safe_component(provider)}-attempt-{attempt}"
        root = self.workspace_root / "service-evidence" / "discovery" / "attempts"
        request_payload = {
            "schema": "autosci_public_discovery_request.v1",
            "provider": provider,
            "method": "GET",
            "url": url,
            "attempt": attempt,
            "credential_mode": (
                "api_key"
                if provider == "semantic_scholar" and os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
                else "public_no_key"
            ),
            "requested_at": self.clock(),
        }
        request_path = root / f"{attempt_id}-request.json"
        request_sha = _write_json(request_path, request_payload)
        response_path = root / f"{attempt_id}-response.bin"
        _write_bytes(response_path, body)
        response_sha = _sha256(body)
        metadata = {
            "schema": "autosci_public_discovery_attempt.v1",
            "provider": provider,
            "attempt": attempt,
            "status": status,
            "status_code": status_code,
            "request_path": _display_path(request_path, self.workspace_root),
            "request_sha256": request_sha,
            "response_path": _display_path(response_path, self.workspace_root),
            "response_sha256": response_sha,
            "response_bytes": len(body),
            "response_kind": response_kind,
            "retry_wait_seconds": retry_wait_seconds,
            "error_type": error_type,
            "recorded_at": self.clock(),
        }
        metadata_path = root / f"{attempt_id}-metadata.json"
        metadata_sha = _write_json(metadata_path, metadata)
        metadata["metadata_path"] = _display_path(metadata_path, self.workspace_root)
        metadata["metadata_sha256"] = metadata_sha
        paths = [
            _display_path(request_path, self.workspace_root),
            _display_path(response_path, self.workspace_root),
            _display_path(metadata_path, self.workspace_root),
        ]
        self._attempts.append(metadata)
        self._attempt_paths.setdefault(provider, []).extend(paths)
        return metadata

    def _open_body(self, provider: str, url: str, *, accept: str = "application/json") -> tuple[bytes, str]:
        request = urllib.request.Request(
            url,
            headers={"Accept": accept, "User-Agent": "OpenSolar-AutoSci/1.0"},
            method="GET",
        )
        waited = 0.0
        body = b""
        for attempt in range(1, max(1, min(int(self.max_attempts_per_provider), 2)) + 1):
            try:
                with self.urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read(DEFAULT_PROVIDER_MAX_BYTES + 1)
                self._record_discovery_attempt(
                    provider=provider, url=url, attempt=attempt, status="completed",
                    status_code=int(getattr(response, "status", 200) or 200), body=body,
                    retry_wait_seconds=0.0,
                )
                break
            except urllib.error.HTTPError as exc:
                error_body = exc.read(DEFAULT_PROVIDER_MAX_BYTES + 1) if hasattr(exc, "read") else b""
                retryable = exc.code == 429 or 500 <= int(exc.code) <= 599
                retry_after = str((exc.headers or {}).get("Retry-After") or "0")
                try:
                    requested_wait = max(0.0, float(retry_after))
                except ValueError:
                    requested_wait = 0.0
                wait = min(5.0, requested_wait or float(attempt), max(0.0, self.max_total_wait_seconds - waited))
                self._record_discovery_attempt(
                    provider=provider, url=url, attempt=attempt, status="failed",
                    status_code=int(exc.code), body=error_body, retry_wait_seconds=wait,
                    error_type="provider_rate_limited" if exc.code == 429 else "provider_http_error",
                )
                if not retryable or attempt >= self.max_attempts_per_provider or wait <= 0:
                    raise ResearchOperatorError(
                        f"Public discovery provider returned HTTP {exc.code}",
                        error_type="provider_rate_limited" if exc.code == 429 else "provider_http_error",
                    ) from exc
                self.sleep(wait)
                waited += wait
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                wait = min(5.0, float(attempt), max(0.0, self.max_total_wait_seconds - waited))
                self._record_discovery_attempt(
                    provider=provider, url=url, attempt=attempt, status="failed",
                    status_code=0, body=b"", retry_wait_seconds=wait,
                    error_type="provider_unavailable",
                )
                if attempt >= self.max_attempts_per_provider or wait <= 0:
                    raise ResearchOperatorError(
                        f"Public discovery provider failed: {type(exc).__name__}: {exc}",
                        error_type="provider_unavailable",
                    ) from exc
                self.sleep(wait)
                waited += wait
        if len(body) > DEFAULT_PROVIDER_MAX_BYTES:
            raise ResearchOperatorError("Discovery response exceeds the size limit", error_type="provider_contract")
        return body, _sha256(body)

    def _open_json(self, provider: str, url: str) -> tuple[dict[str, Any], str]:
        body, response_hash = self._open_body(provider, url)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchOperatorError("Discovery provider returned invalid JSON", error_type="provider_contract") from exc
        if not isinstance(payload, dict):
            raise ResearchOperatorError("Discovery provider returned a non-object response", error_type="provider_contract")
        return payload, response_hash

    def _arxiv(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": self.limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        body, response_hash = self._open_body("arxiv", url, accept="application/atom+xml")
        # This is the only place the service parses XML from the network.
        # ElementTree expands internal entities, so a declared entity is a
        # memory-amplification vector even though the body itself is size
        # capped. A legitimate Atom feed declares none, so refuse outright
        # rather than relying on the parser to stay bounded.
        if _XML_ENTITY_DECLARATION_RE.search(body[:8192]):
            raise ResearchOperatorError(
                "arXiv response declares an XML entity, which a feed never needs",
                error_type="provider_contract",
            )
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as exc:
            raise ResearchOperatorError(
                "arXiv returned a response that is not parseable Atom",
                error_type="provider_contract",
            ) from exc
        candidates: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", _ARXIV_NAMESPACES):
            title = re.sub(r"\s+", " ", entry.findtext("atom:title", "", _ARXIV_NAMESPACES)).strip()
            abs_url = str(entry.findtext("atom:id", "", _ARXIV_NAMESPACES)).strip()
            if not title or not abs_url:
                continue
            # arXiv states its entry id over http; downstream fetching only
            # accepts https, so canonicalize here rather than leaking a scheme
            # that the URL policy will reject.
            if abs_url.startswith("http://"):
                abs_url = "https://" + abs_url[len("http://") :]
            doi = str(entry.findtext("arxiv:doi", "", _ARXIV_NAMESPACES)).strip()
            published = str(entry.findtext("atom:published", "", _ARXIV_NAMESPACES)).strip()
            primary = entry.find("arxiv:primary_category", _ARXIV_NAMESPACES)
            category = str(primary.get("term") or "") if primary is not None else ""
            authors = [
                str(node.findtext("atom:name", "", _ARXIV_NAMESPACES)).strip()
                for node in entry.findall("atom:author", _ARXIV_NAMESPACES)
            ]
            canonical = f"https://doi.org/{doi}" if doi else abs_url
            candidates.append(
                {
                    "source_id": f"arxiv:{abs_url.rsplit('/', 1)[-1]}",
                    "canonical_id": canonical,
                    "title": title,
                    "url": abs_url,
                    "provider": "arxiv",
                    "metadata": {
                        "year": int(published[:4]) if published[:4].isdigit() else None,
                        "venue": str(entry.findtext("arxiv:journal_ref", "", _ARXIV_NAMESPACES)).strip() or "arXiv preprint",
                        "authors": [item for item in authors if item],
                        "primary_category": category,
                        "doi": doi,
                    },
                    "provenance": {"provider": "arxiv", "query": query, "discovered_at": self.clock()},
                    "content_summary": re.sub(r"\s+", " ", entry.findtext("atom:summary", "", _ARXIV_NAMESPACES)).strip(),
                }
            )
        return candidates, {"provider": "arxiv", "request_url": url, "response_sha256": response_hash}

    def _europe_pmc(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(
            {"query": query, "format": "json", "pageSize": self.limit, "resultType": "core"}
        )
        payload, response_hash = self._open_json("europe_pmc", url)
        results = payload.get("resultList") if isinstance(payload.get("resultList"), dict) else {}
        candidates: list[dict[str, Any]] = []
        for raw in results.get("result") or []:
            if not isinstance(raw, dict):
                continue
            title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip().rstrip(".")
            if not title:
                continue
            doi = str(raw.get("doi") or "").strip()
            record_id = str(raw.get("id") or "").strip()
            source = str(raw.get("source") or "").strip()
            if doi:
                canonical = f"https://doi.org/{doi}"
            elif source and record_id:
                canonical = f"https://europepmc.org/article/{source}/{record_id}"
            else:
                continue
            journal = raw.get("journalInfo") if isinstance(raw.get("journalInfo"), dict) else {}
            journal_title = journal.get("journal") if isinstance(journal.get("journal"), dict) else {}
            year = str(raw.get("pubYear") or "").strip()
            candidates.append(
                {
                    "source_id": f"doi:{doi}" if doi else f"europepmc:{source}/{record_id}",
                    "canonical_id": canonical,
                    "title": title,
                    "url": canonical,
                    "provider": "europe_pmc",
                    "metadata": {
                        "year": int(year) if year.isdigit() else None,
                        "venue": str(journal_title.get("title") or ""),
                        "authors": [
                            item.strip()
                            for item in str(raw.get("authorString") or "").split(",")
                            if item.strip()
                        ],
                        "doi": doi,
                        "pmid": str(raw.get("pmid") or ""),
                    },
                    "provenance": {"provider": "europe_pmc", "query": query, "discovered_at": self.clock()},
                    "content_summary": re.sub(r"<[^>]+>", " ", str(raw.get("abstractText") or "")).strip(),
                }
            )
        return candidates, {"provider": "europe_pmc", "request_url": url, "response_sha256": response_hash}

    def _openalex(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"search": query, "per-page": self.limit, "select": "id,doi,title,publication_year,primary_location,authorships,abstract_inverted_index"}
        )
        payload, response_hash = self._open_json("openalex", url)
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
        payload, response_hash = self._open_json("crossref", url)
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
            payload, response_hash = self._open_json("wikipedia", url)
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
            # The lifecycle owns a bounded total runtime and has independent
            # public-provider fallbacks.  Do not let one provider's long
            # Retry-After sequence consume the whole lifecycle budget.
            max_retries=max(0, min(int(self.max_attempts_per_provider) - 1, 1)),
            max_retry_wait_seconds=min(5.0, max(0.0, float(self.max_total_wait_seconds))),
        )
        if not isinstance(raw, dict):
            raise ResearchOperatorError("AutoSci discovery backend returned a non-object response", error_type="provider_contract")
        semantic_url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
            {"query": query, "limit": self.limit}
        )
        normalized_body = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self._record_discovery_attempt(
            provider="semantic_scholar",
            url=semantic_url,
            attempt=1,
            status="completed" if str(raw.get("status") or "") == "completed" else str(raw.get("status") or "unknown"),
            status_code=200,
            body=normalized_body,
            retry_wait_seconds=0.0,
            response_kind="normalized_backend_payload",
        )
        if progress.exists():
            self._attempt_paths.setdefault("semantic_scholar", []).append(_display_path(progress, self.workspace_root))
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
        self._attempts.clear()
        self._attempt_paths.clear()
        task_contract = payload.get("task_contract") if isinstance(payload.get("task_contract"), dict) else {}
        full_query = str(task_contract.get("user_intent") or payload.get("topic") or "").strip()
        query = _topic_from_snapshot(seed_snapshot, payload)
        if not query:
            raise ResearchOperatorError("Source discovery requires a non-empty query", error_type="invalid_input")
        relevance_query = (
            full_query
            if re.search(r"Authoritative discovery scope\s*:", full_query, re.IGNORECASE)
            else query
        )
        request_hash = stable_json_sha256(
            {
                "service_id": self.service_id,
                "service_version": self.service_version,
                "query": query,
                "relevance_query": relevance_query,
                "limit": self.limit,
                "seed_snapshot_sha256": stable_json_sha256(seed_snapshot),
            }
        )
        seeded: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        limitations: list[str] = []
        traces: list[dict[str, Any]] = []
        try:
            min_provider_families = max(1, int(task_contract.get("min_provider_families") or 1))
        except (TypeError, ValueError):
            min_provider_families = 1
        for seed in seed_snapshot.get("seeds") or []:
            if not isinstance(seed, dict) or str(seed.get("seed_kind") or "") != "url":
                continue
            source_id = f"url:{str(seed.get('content_sha256') or seed.get('sha256') or '')[:24]}"
            seeded.append(
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
        contributed: set[str] = set()
        # What each provider actually did, so a provider that answered honestly
        # with nothing on topic is not later reported as having failed.
        answered: dict[str, str] = {}
        try:
            semantic, trace, warnings = self._semantic_scholar(query)
            candidates.extend(semantic)
            traces.append(trace)
            limitations.extend(warnings)
            answered["semantic_scholar"] = "completed" if semantic else "empty"
            if semantic:
                contributed.add("semantic_scholar")
        except ResearchOperatorError as exc:
            limitations.append(f"Semantic Scholar fallback boundary: {exc.error_type}: {exc}")
            traces.append({"provider": "semantic_scholar", "status": "failed", "error_type": exc.error_type})
            answered["semantic_scholar"] = "failed"
        has_fetched_url = bool(seeded)
        if has_fetched_url and len(seeded) + len(candidates) < 4:
            try:
                wikipedia, trace = self._wikipedia(_supplemental_queries(seed_snapshot, query))
                candidates.extend(wikipedia)
                traces.append(trace)
            except ResearchOperatorError as exc:
                limitations.append(f"Wikipedia fallback boundary: {exc.error_type}: {exc}")
                traces.append({"provider": "wikipedia", "status": "failed", "error_type": exc.error_type})
        # Bibliographic providers are consulted as a chain rather than a
        # single-shot fallback. The previous rule stopped as soon as any one
        # provider returned three rows, which let one weakly-ranked provider be
        # the sole basis for the evidence set; downstream relevance filtering
        # then had nothing on-topic left to choose from. Keep going until at
        # least two independent providers have contributed, or the chain is
        # exhausted.
        # arXiv covers computing, physics and mathematics; Europe PMC covers the
        # life sciences. Neither alone spans the topics this workflow accepts,
        # and OpenAlex ranks too loosely to be trusted on its own, so the chain
        # deliberately mixes a domain-specific pair with the broad catalogues.
        required_contributors = max(MIN_DISCOVERY_PROVIDERS, min_provider_families)
        for provider, backend, boundary in (
            ("arxiv", self._arxiv, "arXiv"),
            ("europe_pmc", self._europe_pmc, "Europe PMC"),
            ("openalex", self._openalex, "OpenAlex"),
            ("crossref", self._crossref, "Crossref"),
        ):
            enough = len(seeded) + len(candidates) >= self.limit
            if enough and len(contributed) >= required_contributors:
                break
            try:
                found, trace = backend(query)
            except ResearchOperatorError as exc:
                limitations.append(f"{boundary} fallback boundary: {exc.error_type}: {exc}")
                traces.append({"provider": provider, "status": "failed", "error_type": exc.error_type})
                answered[provider] = "failed"
                continue
            candidates.extend(found)
            traces.append(trace)
            answered[provider] = "completed" if found else "empty"
            if found:
                contributed.add(provider)
        selected = _select_candidates(seeded, candidates, limit=self.limit + 1)
        if not selected:
            raise ResearchOperatorError(
                "All configured public discovery providers returned no traceable sources",
                error_type="provider_unavailable",
            )
        minimum_relevant_raw = (
            task_contract.get("minimum_relevant_candidates")
            if task_contract.get("minimum_relevant_candidates") is not None
            else payload.get("minimum_live_sources")
        )
        try:
            minimum_relevant = int(minimum_relevant_raw) if minimum_relevant_raw is not None else None
        except (TypeError, ValueError):
            minimum_relevant = None
        deduped, relevance_audit = apply_discovery_relevance_gate(
            relevance_query,
            selected,
            minimum_relevant_candidates=minimum_relevant,
        )
        recovery_queries: list[str] = []
        if relevance_audit["status"] != "passed" and relevance_audit.get("aggregate_coverage_missing"):
            recovery_candidates: list[dict[str, Any]] = []
            recovery_queries = _coverage_recovery_queries(relevance_query, relevance_audit)
            for recovery_query in recovery_queries:
                for provider, backend_name, boundary in _DISCOVERY_COVERAGE_RECOVERY_PROVIDERS:
                    backend = getattr(self, backend_name)
                    try:
                        found, trace = backend(recovery_query)
                    except ResearchOperatorError as exc:
                        limitations.append(
                            f"{boundary} coverage recovery boundary: {exc.error_type}: {exc}"
                        )
                        traces.append({
                            "provider": provider,
                            "status": "failed",
                            "error_type": exc.error_type,
                            "recovery_query": recovery_query,
                        })
                        continue
                    trace["recovery_query"] = recovery_query
                    traces.append(trace)
                    recovery_candidates.extend(found)
                    if found:
                        contributed.add(provider)
                        answered[provider] = "completed"
            if recovery_candidates:
                selected = _select_candidates(
                    seeded,
                    [*recovery_candidates, *candidates],
                    limit=self.limit + 1,
                )
                deduped, relevance_audit = apply_discovery_relevance_gate(
                    relevance_query,
                    selected,
                    minimum_relevant_candidates=minimum_relevant,
                )
        if recovery_queries:
            relevance_audit["coverage_recovery_queries"] = recovery_queries
        relevance_audit_hash = stable_json_sha256(relevance_audit)
        relevance_audit_path = (
            self.workspace_root
            / "service-evidence"
            / "discovery"
            / "relevance"
            / f"{relevance_audit_hash}.json"
        )
        relevance_audit_sha = _write_json(relevance_audit_path, relevance_audit)
        relevance_audit["audit_path"] = _display_path(relevance_audit_path, self.workspace_root)
        relevance_audit["audit_sha256"] = relevance_audit_sha
        for candidate in deduped:
            candidate["candidate_sha256"] = stable_json_sha256(candidate)
            candidate["query"] = relevance_query
        if relevance_audit["status"] != "passed":
            limitations.append(
                "Deterministic relevance gate left the discovery shortlist incomplete: "
                + "; ".join(str(item) for item in relevance_audit.get("blocking_reasons") or [])
                + f". Audit: {relevance_audit['audit_path']}"
            )
        response_payload = {
            "schema": "autosci_source_discovery_service.v1",
            "service_id": self.service_id,
            "service_version": self.service_version,
            "request_sha256": request_hash,
            "query": relevance_query,
            "provider_query": query,
            "provider_traces": traces,
            "provider_attempts": list(self._attempts),
            "candidate_count": len(deduped),
            "relevance_gate": relevance_audit,
            "candidate_hashes": [str(item["candidate_sha256"]) for item in deduped],
            "candidate_records": [
                {
                    "source_id": str(item.get("source_id") or ""),
                    "canonical_id": str(item.get("canonical_id") or ""),
                    "url": str(item.get("url") or ""),
                    "provider": str(item.get("provider") or ""),
                    "candidate_sha256": str(item.get("candidate_sha256") or ""),
                }
                for item in deduped
            ],
            "created_at": self.clock(),
            "limitations": limitations,
        }
        response_hash = stable_json_sha256(response_payload)
        archive_path = self.workspace_root / "service-evidence" / "discovery" / f"{response_hash}.json"
        archive_hash = _write_json(archive_path, response_payload)
        providers = sorted({str(item.get("provider") or "unknown") for item in selected})
        attempted_providers = sorted(set(self._attempt_paths) | set(providers) | set(answered))
        return {
            "service_id": self.service_id,
            "service_version": self.service_version,
            "request_sha256": request_hash,
            "response_sha256": response_hash,
            "trace": "production:" + "+".join(providers),
            "query": relevance_query,
            "provider_query": query,
            "status": "completed" if relevance_audit["status"] == "passed" else "inconclusive",
            "candidates": deduped,
            "relevance_gate": relevance_audit,
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
                | {
                    "status": answered.get(provider, "completed" if provider in providers else "failed"),
                    "evidence_paths": sorted(set(self._attempt_paths.get(provider) or [])),
                }
                for provider in attempted_providers
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
    max_attempts: int = DEFAULT_PROVIDER_MAX_ATTEMPTS
    retry_max_sleep_seconds: float = DEFAULT_PROVIDER_RETRY_MAX_SLEEP_SECONDS
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
        if node_id == "idea_generate":
            evidence = kwargs.get("evidence") if isinstance(kwargs.get("evidence"), list) else []
            allowed_evidence_ids = _explicit_evidence_ids(evidence)
            if not allowed_evidence_ids:
                raise ResearchOperatorError(
                    "Idea generation requires explicit source evidence identifiers",
                    error_type="missing_input",
                )
            user = {
                "node_id": node_id,
                "allowed_evidence_ids": allowed_evidence_ids,
                "evidence": evidence,
                "constraints": kwargs.get("constraints") if isinstance(kwargs.get("constraints"), dict) else {},
                "required_output": {
                    "ideas": [
                        {
                            "idea_id": "idea-001",
                            "title": "specific evidence-grounded idea",
                            "hypothesis": "falsifiable hypothesis",
                            "approach": "bounded proposed approach",
                            "origin_evidence_ids": ["one or more exact allowed_evidence_ids values"],
                            "risks": ["specific risk"],
                            "falsifiability": "observable condition that would reject the hypothesis",
                            "validation_method": "method that measures the hypothesis",
                            "minimum_experiment": "smallest real experiment that can test the hypothesis",
                            "novelty_hypothesis": "bounded novelty claim, or empty string",
                        }
                    ],
                    "limitations": [],
                },
                "quality_requirements": [
                    "Generate only ideas supported by the supplied evidence.",
                    "Copy every origin_evidence_ids value exactly from allowed_evidence_ids.",
                    "Do not invent source identifiers, results, measurements, or experimental outcomes.",
                    "Make each idea falsifiable and specify a minimum executable experiment.",
                    "State material risks and uncertainty in limitations.",
                ],
            }
        elif node_id == "evidence_synthesis":
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
            allowed_source_ids = [str(item["source_id"]) for item in sources if str(item.get("source_id") or "").strip()]
            user = {
                "node_id": node_id,
                "complete_user_request": str(task_contract.get("user_intent") or ""),
                "allowed_source_ids": allowed_source_ids,
                "validated_sources": sources,
                "required_output": {
                    "claims": [
                        {
                            "claim_id": "claim-001",
                            "text": "source-grounded finding",
                            "evidence_ids": ["one or more exact source_id values"],
                            # The exact sentence the claim rests on, per cited
                            # source. Without it a claim records WHICH source
                            # supported it but never WHICH TEXT, so nothing
                            # downstream can verify the support -- only the
                            # linkage.
                            "evidence_quotes": [
                                {
                                    "source_id": "exact source_id value",
                                    "quote": "verbatim sentence copied from that source's content_summary",
                                }
                            ],
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
                    "When two or more validated sources are available, cite at least two distinct exact source_id values across the claims.",
                    "Every evidence_ids entry must be copied exactly from allowed_source_ids; do not abbreviate, hash, prefix, suffix, or repair source ids.",
                    "Produce at least four substantive claims when evidence supports them.",
                    "Every claim must carry an evidence_quotes entry for each cited source_id.",
                    "Each quote must be copied VERBATIM from that source's content_summary, "
                    "long enough to stand alone (at least 40 characters), and must contain "
                    "wording the claim itself relies on. Do not paraphrase, reflow, or repair "
                    "a quote: it is checked as an exact substring of the source text.",
                    # A verbatim quote proves the TEXT exists; it does not prove the
                    # claim rests on it. Each claim is additionally checked against the
                    # full source text with a lexical support test, and claims that
                    # fail are refused and sent back. These four rules are that test,
                    # stated so the model can satisfy it directly.
                    "Cite EVERY validated source that genuinely supports a claim, not just "
                    "one. A claim resting on two sources must list both.",
                    "At least one of a claim's cited sources must support it ON ITS OWN, "
                    "because support is assessed per source. Only split a claim when NO "
                    "single source carries it; do not drop a corroborating source merely to "
                    "keep one citation per claim.",
                    "Write each claim in the source's own vocabulary. At least 45 percent of "
                    "the claim's substantive words must also appear in that source's text, so "
                    "reuse the source's terms rather than substituting synonyms.",
                    "Every number, percentage, or count in a claim must also appear in the "
                    "cited source. Do not compute, round, or infer figures.",
                    "Do not use absolute wording such as all, always, never, every, none, "
                    "proves, guarantees, or cures: a claim scoped that broadly is refused.",
                ],
                # Populated only on a repair attempt, listing the claims that were
                # refused and exactly why, so the retry is targeted rather than a
                # blind regeneration.
                "grounding_feedback": kwargs.get("grounding_feedback") or [],
                "synthesis_attempt": kwargs.get("synthesis_attempt") or 1,
                "max_synthesis_attempts": kwargs.get("max_synthesis_attempts") or 1,
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
                                # CLAIM ids, not source ids. Each grounded_claim
                                # carries its OWN `evidence_ids` holding source
                                # ids, so the same field name means two different
                                # id spaces one level apart. Showing the shape
                                # here is what stops the writer citing the wrong.
                                "evidence_ids": ["claim-001", "claim-002"],
                            }
                        ],
                    },
                    "limitations": [],
                },
                "quality_requirements": [
                    "Every conclusion's evidence_ids must be claim_id values taken from "
                    "grounded_claims, such as claim-001. Never put a source id there, such "
                    "as openalex-rag-01. Each grounded_claim has its own evidence_ids field "
                    "listing the SOURCES it rests on; that is a different id space and a "
                    "conclusion citing it is rejected.",
                    "The body must be non-empty, clearly structured Markdown and directly answer the whole request.",
                    "Include an explicit Method or Evidence Method section that explains how supplied sources were used.",
                    "When grounded claims cite two or more distinct source ids, the report must preserve at least two distinct cited sources.",
                    "For a survey, include an explicit performance trade-offs section and an open research problems section.",
                    "For Chinese requests, write the report in Chinese.",
                    "Use each requested dimension once; avoid repeating the same Failure modes, Observability, Conclusions, or Limitations material in multiple sections.",
                    "Any recommendation, benchmark design, operational practice, or industry implication that is synthesized beyond a source's direct wording must be explicitly labeled as synthesis, proposed practice, or conditional inference.",
                    "Preserve the uncertainty and limitation qualifiers from grounded_claims; do not expand a source-specific finding into a general guarantee.",
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
                    "Require an explicit Method or Evidence Method section when the requested deliverable is a survey or technical report.",
                    "Require at least two cited source lineages when two or more validated sources are available.",
                    "For surveys, require performance trade-offs and open research problems.",
                    "For Chinese requests, require Chinese output.",
                    "Do not create a high-severity finding merely because the evidence has explicit limitations.",
                ],
            }
        elif node_id == "report_revision":
            synthesis = kwargs.get("evidence_synthesis") if isinstance(kwargs.get("evidence_synthesis"), dict) else {}
            review = kwargs.get("independent_review") if isinstance(kwargs.get("independent_review"), dict) else {}
            preservation = kwargs.get("preservation_requirements") if isinstance(kwargs.get("preservation_requirements"), dict) else {}
            user = {
                "node_id": node_id,
                "complete_user_request": str(task_contract.get("user_intent") or ""),
                "deliverable_requirements": kwargs.get("deliverable_requirements") or {},
                "grounded_claims": synthesis.get("claims") or [],
                "original_report": kwargs.get("original_report") or {},
                "independent_review_findings": review.get("findings") or [],
                "basis_verdict": str(review.get("verdict_suggestion") or ""),
                "required_preservation": preservation,
                "revision_attempt": int(kwargs.get("revision_attempt") or 1),
                "max_revision_attempts": int(kwargs.get("max_revision_attempts") or 1),
                # Populated only on a retry: the exact deterministic rejection
                # the previous attempt produced, so the reviser is told what it
                # dropped instead of guessing.
                "previous_attempt_rejected_because": str(kwargs.get("preservation_feedback") or ""),
                "required_output": {
                    "report": {
                        "title": "specific revised report title",
                        "body": "complete structured Markdown report body",
                        "sections": [{"title": "section title", "body": "section body"}],
                        "conclusions": [
                            {
                                "conclusion_id": "conclusion-001",
                                "text": "bounded revised conclusion",
                                # CLAIM ids, not source ids. Each grounded_claim
                                # carries its OWN `evidence_ids` holding source
                                # ids, so the same field name means two different
                                # id spaces one level apart. Showing the shape
                                # here is what stops the writer citing the wrong.
                                "evidence_ids": ["claim-001", "claim-002"],
                            }
                        ],
                    },
                    "limitations": [],
                    "preservation": preservation,
                },
                "quality_requirements": [
                    "Repair only issues identified by the independent review or deterministic quality checks.",
                    "Use only supplied grounded_claims and preserve exact claim_id values in conclusion evidence_ids.",
                    "Do not invent sources, evidence ids, benchmarks, metrics, or methods that are not supported by grounded_claims.",
                    "Preserve uncertainty and limitation qualifiers from grounded_claims.",
                    "Copy required_preservation exactly, preserve every listed conclusion unchanged, retain the accepted method text, and render every listed limitation verbatim under a substantive Limitations section.",
                    "The revised body must directly answer the complete user request in the requested language.",
                    "Include an explicit Method or Evidence Method section when the requested deliverable is a survey or technical report.",
                    "Replace the report body instead of appending duplicate section summaries from prior drafts.",
                    "Keep one coherent set of Methods, Findings, Limitations, and Conclusions sections.",
                    "Do not claim immutable evidence_synthesis claim_source_lineage was removed; instead restrict the report text to the source scopes supported by each claim limitation.",
                ],
            }
        elif node_id == "report_revision_review":
            prior_review = kwargs.get("prior_review") if isinstance(kwargs.get("prior_review"), dict) else {}
            user = {
                "node_id": node_id,
                "complete_user_request": str(task_contract.get("user_intent") or ""),
                "revised_report_draft": kwargs.get("report_draft") or {},
                "source_validation": kwargs.get("source_validation") or {},
                "prior_review_findings": prior_review.get("findings") or [],
                "required_output": {
                    "findings": [
                        {
                            "finding_id": "revision-review-001",
                            "severity": "low|medium|high|critical",
                            "category": "evidence|relevance|structure|language|truthfulness",
                            "message": "specific finding",
                        }
                    ],
                    "verdict_suggestion": "accept|revise|reject",
                    "limitations": [],
                },
                "review_rules": [
                    "Accept only if the revised report resolves high and critical prior review findings.",
                    "Require conclusions to cite exact claim_id values present in the revised report lineage.",
                    "Require the revised report to remain grounded in supplied source validation and evidence synthesis lineage.",
                    "Do not require report_revision to mutate immutable evidence_synthesis claim_source_lineage; judge whether the revised report text uses sources within the stated claim limitations.",
                    "For Chinese requests, require Chinese output.",
                    "Return accept when all remaining findings are low-severity nits that do not require another writing pass.",
                    "Return revise only for medium, high, or critical issues that require another writing pass.",
                    "Return reject when unsupported new claims, missing methods, or language mismatch remain and cannot be repaired within the bounded loop.",
                ],
            }
        else:
            raise ResearchOperatorError(f"Unsupported production model node: {node_id}", error_type="invalid_input")
        return system, user

    def _provider_retry_delay(self, retry_after: str, attempt: int) -> float:
        parsed = 0.0
        try:
            parsed = float(retry_after)
        except (TypeError, ValueError):
            parsed = 0.0
        if parsed <= 0:
            parsed = min(float(attempt), self.retry_max_sleep_seconds)
        return max(0.0, min(parsed, self.retry_max_sleep_seconds))

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
        retry_events: list[dict[str, Any]] = []
        attempts = max(1, int(self.max_attempts or 1))
        for attempt in range(1, attempts + 1):
            try:
                with self.urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read(DEFAULT_PROVIDER_MAX_BYTES + 1)
                break
            except urllib.error.HTTPError as exc:
                retry_after = str(exc.headers.get("Retry-After") or "") if exc.headers else ""
                detail = f"provider={route.provider} status={exc.code} stage={node_id}"
                if retry_after:
                    detail += f" retry_after={retry_after}"
                if exc.code == 429 and attempt < attempts:
                    delay = self._provider_retry_delay(retry_after, attempt)
                    retry_events.append(
                        {
                            "attempt": attempt,
                            "max_attempts": attempts,
                            "provider": route.provider,
                            "status_code": exc.code,
                            "retry_after": retry_after,
                            "delay_seconds": delay,
                        }
                    )
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise ResearchOperatorError(
                    f"{detail} attempts={attempts}",
                    error_type="provider_rate_limited" if exc.code == 429 else "provider_http_error",
                ) from exc
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                if attempt < attempts:
                    delay = self._provider_retry_delay("", attempt)
                    retry_events.append(
                        {
                            "attempt": attempt,
                            "max_attempts": attempts,
                            "provider": route.provider,
                            "failure": type(exc).__name__,
                            "delay_seconds": delay,
                        }
                    )
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise ResearchOperatorError(
                    f"provider={route.provider} stage={node_id} failure={type(exc).__name__} attempts={attempts}",
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
        if retry_events:
            provider_usage["retry_events"] = retry_events
            provider_usage["attempt_count"] = len(retry_events) + 1
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


def _explicit_evidence_ids(value: Any) -> list[str]:
    """Collect only identifiers explicitly present in supplied evidence."""

    collected: list[str] = []
    scalar_keys = {"source_id", "claim_id", "method_id", "paper_id", "evidence_id", "artifact_id"}
    list_keys = {"evidence_ids", "origin_evidence_ids"}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                if key in scalar_keys and isinstance(nested, (str, int)) and str(nested).strip():
                    collected.append(str(nested).strip())
                elif key in list_keys and isinstance(nested, list):
                    collected.extend(str(entry).strip() for entry in nested if str(entry).strip())
                else:
                    visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return list(dict.fromkeys(collected))[:500]


@dataclass
class ProductionIdeaGenerator:
    """Adapt the production research model to the idea-generator service contract."""

    model: ResearchModelService
    service_id: str = IDEA_SERVICE_ID
    service_version: str = SERVICE_VERSION

    def __call__(self, *, evidence: list[dict[str, Any]], constraints: dict[str, Any]) -> dict[str, Any]:
        allowed = set(_explicit_evidence_ids(evidence))
        if not allowed:
            raise ResearchOperatorError(
                "Idea generation requires explicit source evidence identifiers",
                error_type="missing_input",
            )
        response = self.model(node_id="idea_generate", evidence=evidence, constraints=constraints)
        ideas = response.get("ideas") if isinstance(response.get("ideas"), list) else []
        if not ideas:
            raise ResearchOperatorError("Idea model returned no ideas", error_type="provider_contract")
        for idea in ideas:
            if not isinstance(idea, dict):
                raise ResearchOperatorError("Idea model returned a non-object idea", error_type="provider_contract")
            origin = {str(item).strip() for item in idea.get("origin_evidence_ids") or [] if str(item).strip()}
            if not origin or not origin.issubset(allowed):
                raise ResearchOperatorError(
                    "Idea model returned an origin evidence id outside the supplied evidence",
                    error_type="provider_contract",
                )
        return response


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
    idea_generator = ProductionIdeaGenerator(model)
    from .bounded_experiment import BoundedLocalExperimentExecutor

    experiment_executor = BoundedLocalExperimentExecutor(root)
    active_model_providers = {route.provider for route in model.routes}
    services: dict[str, Any] = {
        "fetch_url": BoundedUrlFetcher(root),
        "discover_sources": LiteratureDiscoveryService(root),
        "model_generate": model,
        "review_model_generate": model,
        "idea_generator": idea_generator,
        "experiment_executor": experiment_executor,
        "secret_values": configured_secret_values(active_model_providers=active_model_providers),
        "service_metadata": {
            "fetch_url": {"service_id": FETCH_SERVICE_ID, "version": SERVICE_VERSION},
            "discover_sources": {"service_id": DISCOVERY_SERVICE_ID, "version": SERVICE_VERSION},
            "model_generate": {"service_id": MODEL_SERVICE_ID, "version": SERVICE_VERSION},
            "review_model_generate": {"service_id": MODEL_SERVICE_ID, "version": SERVICE_VERSION},
            "idea_generator": {"service_id": IDEA_SERVICE_ID, "version": SERVICE_VERSION},
            "experiment_executor": {
                "service_id": experiment_executor.service_id,
                "version": experiment_executor.service_version,
            },
        },
    }
    services.update(dict(overrides or {}))
    return services
