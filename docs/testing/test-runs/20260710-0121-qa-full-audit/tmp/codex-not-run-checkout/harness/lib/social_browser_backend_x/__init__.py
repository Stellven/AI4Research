"""Solar Harness — Social Browser Backend for X.

Schema, persistence, and dedup utilities for the multi-backend
social post collection pipeline (browser_agent / rss_public /
manual_curated / x_api_optional).
"""
from .schema import PostRecord, ensure_schema
from .dedup_keys_table import DedupKeyRecord, ensure_dedup_keys_table

__all__ = [
    "PostRecord",
    "ensure_schema",
    "DedupKeyRecord",
    "ensure_dedup_keys_table",
]
