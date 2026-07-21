"""HF linked assets enrichment provider.

Fetches linked repos, datasets, spaces, and demo URLs from HF.
"""
from __future__ import annotations

from typing import Optional

from providers.base import BaseEnrichmentProvider, PaperCanonicalProto


class HFAssetsProvider(BaseEnrichmentProvider):
    """Enriches papers with HF linked assets.

    Extracts: linked model repos, datasets, spaces, demo URLs.
    """

    name = "hf_assets"

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

        payload: dict = {
            "repo_id": repo_id,
            "linked_models": [],
            "linked_datasets": [],
            "linked_spaces": [],
            "demo_urls": [],
        }

        url = f"{self._api_base}/models/{repo_id}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                payload["error"] = "not_found"
            else:
                payload["error"] = f"http_{e.code}"
            return payload
        except urllib.error.URLError:
            payload["error"] = "network_error"
            return payload

        card_data = data.get("card_data", {}) or {}
        if isinstance(card_data, dict):
            models = card_data.get("base_model", []) or []
            if isinstance(models, str):
                models = [models]
            payload["linked_models"] = models

            datasets = card_data.get("datasets", []) or []
            if isinstance(datasets, str):
                datasets = [datasets]
            payload["linked_datasets"] = datasets

        siblings = data.get("siblings", [])
        demo_files = [s for s in siblings if s.get("rfilename", "").endswith(".gradio")]
        if demo_files:
            payload["demo_urls"] = [f"https://huggingface.co/spaces/{repo_id}"]

        tags = data.get("tags", [])
        space_tags = [t for t in tags if t.startswith("space:")]
        payload["linked_spaces"] = [t.replace("space:", "", 1) for t in space_tags]

        return payload

    def _extract_repo_id(self, hf_url: str) -> str:
        if not hf_url:
            return ""
        parts = hf_url.rstrip("/").split("/")
        if len(parts) >= 2:
            return "/".join(parts[-2:])
        return parts[-1] if parts else ""
