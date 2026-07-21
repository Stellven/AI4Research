"""Knowledge store fan-out for HF Paper Insight runtime."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from schema import PaperCanonical, PaperEnrichment, PaperEvidencePacket


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    collapsed = "-".join(part for part in cleaned.split("-") if part)
    return collapsed or "unknown"


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class KnowledgeStore:
    """Writes compiled assets to raw/extracted/qmd/graph channels."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.raw_dir = self.root_dir / "raw"
        self.extracted_dir = self.root_dir / "extracted"
        self.qmd_dir = self.root_dir / "qmd"
        self.graph_dir = self.root_dir / "graph"
        self.repair_dir = self.root_dir / "repair_queue"

    def store_to_raw(self, canonical: PaperCanonical, enrichment: PaperEnrichment) -> str:
        paper_dir = self.raw_dir / canonical.paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / "canonical_enrichment.json"
        payload = {
            "paper_id": canonical.paper_id,
            "title": canonical.title,
            "canonical": canonical.__dict__,
            "enrichment": enrichment.__dict__,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return str(path)

    def store_to_extracted(self, compiled: dict[str, str], paper_id: str | None = None) -> list[str]:
        target_id = paper_id or "unknown-paper"
        paper_dir = self.extracted_dir / target_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for key, body in compiled.items():
            path = paper_dir / f"{key}.md"
            path.write_text(body, encoding="utf-8")
            written.append(str(path))
        return written

    def store_to_qmd(self, compiled: dict[str, str], paper_id: str | None = None) -> list[str]:
        target_id = paper_id or "unknown-paper"
        day_dir = self.qmd_dir / _utc_day()
        day_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for key, body in compiled.items():
            path = day_dir / f"{_slug(target_id)}--{_slug(key)}.md"
            path.write_text(
                f"---\nkind: hf_paper_insight_{key}\npaper_id: {target_id}\n---\n\n{body}",
                encoding="utf-8",
            )
            written.append(str(path))
        return written

    def store_to_graph(self, packet: PaperEvidencePacket, resonance: dict) -> list[str]:
        paper_dir = self.graph_dir / packet.paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        packet_path = paper_dir / "packet.json"
        resonance_path = paper_dir / "resonance.json"
        packet_path.write_text(
            json.dumps(packet.__dict__, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        resonance_path.write_text(
            json.dumps(resonance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return [str(packet_path), str(resonance_path)]

    def fanout(
        self,
        *,
        canonical: PaperCanonical,
        enrichment: PaperEnrichment,
        packet: PaperEvidencePacket,
        resonance: dict,
        compiled: dict[str, str],
    ) -> dict[str, list[str] | str]:
        try:
            raw_path = self.store_to_raw(canonical, enrichment)
            extracted_paths = self.store_to_extracted(compiled, paper_id=packet.paper_id)
            qmd_paths = self.store_to_qmd(compiled, paper_id=packet.paper_id)
            graph_paths = self.store_to_graph(packet, resonance)
            return {
                "raw": raw_path,
                "extracted": extracted_paths,
                "qmd": qmd_paths,
                "graph": graph_paths,
            }
        except OSError as exc:
            self.repair_dir.mkdir(parents=True, exist_ok=True)
            queue_path = self.repair_dir / f"{packet.paper_id}.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "paper_id": packet.paper_id,
                        "error": str(exc),
                        "compiled_keys": sorted(compiled),
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            raise
