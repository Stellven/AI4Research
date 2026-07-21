"""HF metadata enrichment provider.

Fetches paper metadata from HuggingFace Papers API.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional, Protocol

from .base import BaseEnrichmentProvider, PaperCanonicalProto


class HTTPResponse:
    status_code: int = 200
    text: str = "{}"

    def json(self) -> Any:
        return json.loads(self.text)


HTTPClient = Callable[[str], HTTPResponse]


def _default_client(url: str) -> HTTPResponse:
    import urllib.request
    resp = urllib.request.urlopen(url)
    r = HTTPResponse()
    r.status_code = resp.status
    r.text = resp.read().decode()
    return r


class HFProvider(BaseEnrichmentProvider):
    name = "huggingface"

    def __init__(self, *, http_client: Optional[HTTPClient] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = http_client or _default_client

    def _fetch(self, canonical: PaperCanonicalProto) -> dict:
        paper_id = canonical.paper_id
        url = f"https://huggingface.co/api/papers/{paper_id}"
        resp = self._client(url)

        if resp.status_code != 200:
            raise RuntimeError(f"HF API returned {resp.status_code}")

        raw = resp.json()
        return {
            "title": raw.get("title", ""),
            "authors": raw.get("authors", []),
            "summary": raw.get("summary", ""),
            "tags": raw.get("tags", []),
            "upvotes": raw.get("upvotes", 0),
            "published_at": raw.get("publishedAt", ""),
            "paper_page": f"https://huggingface.co/papers/{paper_id}",
        }
