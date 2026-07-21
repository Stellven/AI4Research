"""ASR backend routing module (R3).

Routes videos to optimal ASR backend based on priority × capability.
Per D3: routing table loaded from config YAML, not hardcoded in Python.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ASRBackendSpec:
    backend: str
    model_size: str
    diarization: bool
    chunk_length_sec: int = 180
    compute_type: str = "float16_or_int8_float16"
    reason: str = ""


def route_asr(
    priority: str,
    language: str,
    duration_sec: int,
    config_routing_table: list[dict[str, Any]],
    caption_status: str = "none",
) -> ASRBackendSpec:
    """Route to ASR backend based on priority and video features.

    Per D3: routing table comes from config YAML.
    First matching row wins (table ordered by specificity).

    Args:
        priority: P0/P1/P2/P3
        language: ISO 639-1 language code
        duration_sec: Audio duration in seconds
        config_routing_table: List of routing entries from youtube_config
        caption_status: "standard" | "asr" | "none"
    """
    for entry in config_routing_table:
        if _matches(entry, caption_status, priority):
            return ASRBackendSpec(
                backend=entry.get("backend", "faster_whisper"),
                model_size=entry.get("model_size", ""),
                diarization=entry.get("diarization", False),
                chunk_length_sec=entry.get("chunk_length_sec", 180),
                compute_type=entry.get("compute_type", "float16_or_int8_float16"),
                reason=entry.get("reason", ""),
            )

    # Default fallback
    return ASRBackendSpec(
        backend="faster_whisper",
        model_size="medium",
        diarization=False,
        reason="default_fallback_no_route_matched",
    )


def _matches(entry: dict, caption_status: str, priority: str) -> bool:
    """Check if a routing table entry matches current conditions."""
    entry_caption = entry.get("caption_status", "none")
    entry_priority = entry.get("priority", "*")

    caption_match = entry_caption == caption_status
    priority_match = entry_priority in ("*", priority)

    return caption_match and priority_match
