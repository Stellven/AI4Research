"""L0 InfluencerSeedRegistry — load seed accounts into InfluencerProfile objects.

Reads ``config/influence/seed_accounts.yaml`` (a superset of the legacy
ai-influence-daily-digest account list) and emits canonical ``InfluencerProfile``
records. Pure transformation: the caller decides whether to persist via
``store.persist('influencer_profiles', ...)``.
"""
from __future__ import annotations

import pathlib
from typing import Any

import yaml

from .models import InfluencerProfile


def load_seed_config(path: str | pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8")) or {}


def build_profiles(config: dict[str, Any]) -> list[InfluencerProfile]:
    """Turn a parsed seed_accounts config into InfluencerProfile objects."""
    profiles: list[InfluencerProfile] = []
    for entry in config.get("influencers", []):
        profiles.append(
            InfluencerProfile(
                influencer_id=entry["influencer_id"],
                display_name=entry.get("display_name", entry["influencer_id"]),
                tier=entry.get("tier", "T3"),
                categories=list(entry.get("categories", [])),
                platform_accounts=dict(entry.get("platform_accounts", {})),
                expertise_tags=list(entry.get("expertise_tags", [])),
                bias_profile=dict(entry.get("bias_profile", {})),
                influence_weight=float(entry.get("influence_weight", 0.5)),
                role_at_time=list(entry.get("role_at_time", [])),
            )
        )
    return profiles


def registry_from_config(path: str | pathlib.Path) -> list[InfluencerProfile]:
    return build_profiles(load_seed_config(path))
