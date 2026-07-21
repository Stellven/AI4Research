"""HF linked assets enrichment provider.

Fetches models, datasets, and spaces linked to a paper on HuggingFace.
"""
from __future__ import annotations

import json
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


class HFAssetsProvider(BaseEnrichmentProvider):
    name = "hf_assets"

    def __init__(self, *, http_client: Optional[HTTPClient] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = http_client or _default_client

    def _fetch(self, canonical: PaperCanonicalProto) -> dict:
        paper_id = canonical.paper_id
        url = f"https://huggingface.co/api/papers/{paper_id}/repos"
        resp = self._client(url)

        if resp.status_code != 200:
            raise RuntimeError(f"HF Assets API returned {resp.status_code}")

        raw_list = resp.json()
        models = []
        datasets = []
        spaces = []

        for item in raw_list:
            item_type = item.get("type", "")
            entry = {
                "id": item.get("id", ""),
                "name": item.get("name", item.get("id", "").split("/")[-1]),
                "url": f"https://huggingface.co/{item.get('id', '')}",
                "likes": item.get("likes", 0),
                "downloads": item.get("downloads", 0),
            }
            if item_type == "model":
                models.append(entry)
            elif item_type == "dataset":
                datasets.append(entry)
            elif item_type == "space":
                spaces.append(entry)

        return {
            "models": models,
            "datasets": datasets,
            "spaces": spaces,
            "total_assets": len(models) + len(datasets) + len(spaces),
        }
