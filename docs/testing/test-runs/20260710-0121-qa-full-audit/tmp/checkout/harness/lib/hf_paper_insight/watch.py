"""Watch trigger support for sustained resonance and delta tracking."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from schema import PaperEvidencePacket


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_packet_json(packet: PaperEvidencePacket, field_name: str) -> dict:
    raw = getattr(packet, field_name, "{}") or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


class WatchTrigger:
    """Persists watch specs and enqueue markers for follow-up research."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.watch_dir = self.root_dir / "watch"

    def build_watch_spec(self, packet: PaperEvidencePacket, resonance: dict, reasoning: dict | None = None) -> dict:
        canonical = _load_packet_json(packet, "canonical_summary_json")
        taxonomy = _load_packet_json(packet, "taxonomy_summary_json")
        reasoning = reasoning or {}
        authors = canonical.get("authors", [])
        watched_entities = [canonical.get("title", packet.paper_id)]
        watched_entities.extend(
            item.get("name", "") if isinstance(item, dict) else str(item)
            for item in authors[:3]
        )
        watched_entities = [item for item in watched_entities if item]
        return {
            "watch_id": "watch-" + uuid.uuid4().hex[:12],
            "paper_id": packet.paper_id,
            "priority": self._priority_from_resonance(str(resonance.get("resonance_level") or "R0")),
            "reason": reasoning.get("summary", "resonance_followup"),
            "resonance_level": resonance.get("resonance_level", "R0"),
            "watched_entities": watched_entities,
            "watched_events": [
                "paper_update",
                "model_release",
                "dataset_release",
                "benchmark_result",
                "conference_signal",
            ],
            "taxonomy": {
                "domain": taxonomy.get("domain", "other"),
                "stack_layer": taxonomy.get("stack_layer", "model"),
                "research_route": taxonomy.get("research_route", "applied_research"),
            },
            "created_at": _utc_now(),
        }

    def trigger_watch(self, paper_id: str, priority: str, reason: str) -> str:
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        watch_id = "watch-" + uuid.uuid4().hex[:12]
        path = self.watch_dir / f"{paper_id}-{watch_id}.json"
        path.write_text(
            json.dumps(
                {
                    "watch_id": watch_id,
                    "paper_id": paper_id,
                    "priority": priority,
                    "reason": reason,
                    "created_at": _utc_now(),
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        return watch_id

    def store_watch_spec(self, spec: dict) -> str:
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        path = self.watch_dir / f"{spec['paper_id']}-{spec['watch_id']}.json"
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return str(path)

    def _priority_from_resonance(self, level: str) -> str:
        if level in {"R4", "R5"}:
            return "high"
        if level in {"R2", "R3"}:
            return "normal"
        return "low"
