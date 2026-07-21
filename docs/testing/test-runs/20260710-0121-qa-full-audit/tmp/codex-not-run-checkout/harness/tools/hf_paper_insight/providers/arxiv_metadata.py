"""arXiv metadata enrichment provider.

Fetches paper metadata from arXiv API by arxiv_id or title search.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from providers.base import BaseEnrichmentProvider, PaperCanonicalProto


class ArxivMetadataProvider(BaseEnrichmentProvider):
    """Enriches papers from arXiv API.

    Extracts: abstract, authors, categories, published/updated dates, title.
    """

    name = "arxiv_metadata"

    def __init__(
        self,
        *,
        api_base: str = "http://export.arxiv.org/api/query",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._api_base = api_base

    def _fetch(self, canonical: PaperCanonicalProto) -> dict:
        arxiv_id = canonical.arxiv_id
        if not arxiv_id and canonical.arxiv_abs_url:
            arxiv_id = canonical.arxiv_abs_url.rstrip("/").split("/")[-1]

        if arxiv_id:
            return self._fetch_by_id(arxiv_id)

        if canonical.title:
            return self._search_by_title(canonical.title)

        raise ValueError("no_arxiv_id_or_title")

    def _fetch_by_id(self, arxiv_id: str) -> dict:
        import urllib.request
        import urllib.error

        url = f"{self._api_base}?id_list={arxiv_id}&max_results=1"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError):
            return {"error": "network_error", "arxiv_id": arxiv_id}

        return self._parse_arxiv_response(xml_data, arxiv_id=arxiv_id)

    def _search_by_title(self, title: str) -> dict:
        import urllib.parse
        import urllib.request
        import urllib.error

        query = urllib.parse.quote(f'ti:"{title}"')
        url = f"{self._api_base}?search_query={query}&max_results=1"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError):
            return {"error": "network_error", "title_search": title}

        return self._parse_arxiv_response(xml_data)

    def _parse_arxiv_response(self, xml_data: bytes, *, arxiv_id: str = "") -> dict:
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            return {"error": "parse_error", "arxiv_id": arxiv_id}

        entries = root.findall("atom:entry", ns)
        if not entries:
            return {"error": "not_found", "arxiv_id": arxiv_id}

        entry = entries[0]
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        published_el = entry.find("atom:published", ns)
        updated_el = entry.find("atom:updated", ns)

        authors = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        categories = []
        for cat_el in entry.findall("atom:category", ns):
            term = cat_el.get("term", "")
            if term:
                categories.append(term)

        entry_id = ""
        id_el = entry.find("atom:id", ns)
        if id_el is not None and id_el.text:
            entry_id = id_el.text.rstrip("/").split("/")[-1]

        return {
            "arxiv_id": arxiv_id or entry_id,
            "title": (title_el.text or "").strip().replace("\n", " ") if title_el is not None else "",
            "abstract": (summary_el.text or "").strip() if summary_el is not None else "",
            "authors": authors,
            "categories": categories,
            "published": published_el.text.strip() if published_el is not None and published_el.text else None,
            "updated": updated_el.text.strip() if updated_el is not None and updated_el.text else None,
        }
