"""ArXiv metadata enrichment provider.

Fetches paper metadata from arXiv API.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Callable, Optional

from .base import BaseEnrichmentProvider, PaperCanonicalProto


class HTTPResponse:
    status_code: int = 200
    text: str = "{}"

    def json(self) -> Any:
        return json.loads(self.text)


HTTPClient = Callable[[str], "HTTPResponse"]


def _default_client(url: str) -> "HTTPResponse":
    import urllib.request
    resp = urllib.request.urlopen(url)
    r = HTTPResponse()
    r.status_code = resp.status
    r.text = resp.read().decode()
    return r


_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _extract_arxiv_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", url)
    return m.group(1) if m else None


class ArxivProvider(BaseEnrichmentProvider):
    name = "arxiv"

    def __init__(self, *, http_client: Optional[HTTPClient] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = http_client or _default_client

    def _fetch(self, canonical: PaperCanonicalProto) -> dict:
        arxiv_id = canonical.arxiv_id or _extract_arxiv_id(canonical.arxiv_abs_url)
        if not arxiv_id:
            raise RuntimeError(f"no arxiv_id for paper {canonical.paper_id}")

        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        resp = self._client(url)

        if resp.status_code != 200:
            raise RuntimeError(f"ArXiv API returned {resp.status_code}")

        return self._parse_arxiv_response(resp.text, arxiv_id)

    def _parse_arxiv_response(self, xml_text: str, arxiv_id: str) -> dict:
        root = ET.fromstring(xml_text)
        entry = root.find("atom:entry", _ARXIV_NS)
        if entry is None:
            return {"arxiv_id": arxiv_id, "error": "no entry found"}

        title_el = entry.find("atom:title", _ARXIV_NS)
        summary_el = entry.find("atom:summary", _ARXIV_NS)
        published_el = entry.find("atom:published", _ARXIV_NS)
        authors = [
            a.find("atom:name", _ARXIV_NS).text.strip()
            for a in entry.findall("atom:author", _ARXIV_NS)
            if a.find("atom:name", _ARXIV_NS) is not None and a.find("atom:name", _ARXIV_NS).text
        ]
        categories = [
            c.get("term", "")
            for c in entry.findall("atom:category", _ARXIV_NS)
        ]

        return {
            "arxiv_id": arxiv_id,
            "title": (title_el.text.strip() if title_el is not None and title_el.text else ""),
            "summary": (summary_el.text.strip() if summary_el is not None and summary_el.text else ""),
            "authors": authors,
            "categories": categories,
            "published_at": (published_el.text.strip() if published_el is not None and published_el.text else ""),
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
        }
