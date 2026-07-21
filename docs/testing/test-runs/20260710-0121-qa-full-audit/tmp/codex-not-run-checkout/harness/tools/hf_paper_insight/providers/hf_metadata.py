"""HF metadata enrichment provider.

Fetches model/repo card metadata from HuggingFace Hub API.
"""
from __future__ import annotations

from typing import Optional

from providers.base import BaseEnrichmentProvider, ProviderResult, PaperCanonicalProto


class HFMetadataProvider(BaseEnrichmentProvider):
    """Enriches papers from HuggingFace Hub API.

    Extracts: model card, downloads, likes, tags, pipeline_tag, library_name.
    """

    name = "hf_metadata"

    def __init__(
        self,
        *,
        api_base: str = "https://huggingface.co/api",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._api_base = api_base.rstrip("/")

    def _fetch(self, canonical: PaperCanonicalProto) -> dict:
        import json
        import urllib.request
        import urllib.error

        repo_id = self._extract_repo_id(canonical.hf_url)
        if not repo_id:
            raise ValueError("no_hf_url")

        url = f"{self._api_base}/models/{repo_id}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"error": "not_found", "repo_id": repo_id}
            raise
        except urllib.error.URLError:
            return {"error": "network_error", "repo_id": repo_id}

        return {
            "repo_id": repo_id,
            "downloads": data.get("downloads", 0),
            "likes": data.get("likes", 0),
            "tags": data.get("tags", []),
            "pipeline_tag": data.get("pipeline_tag"),
            "library_name": data.get("library_name"),
            "card_data": data.get("card_data", {}),
        }

    def _extract_repo_id(self, hf_url: str) -> str:
        if not hf_url:
            return ""
        parts = hf_url.rstrip("/").split("/")
        if len(parts) >= 2:
            return "/".join(parts[-2:])
        return parts[-1] if parts else ""
