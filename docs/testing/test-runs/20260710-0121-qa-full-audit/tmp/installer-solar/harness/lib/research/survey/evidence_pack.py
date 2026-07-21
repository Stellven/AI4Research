"""Build per-section evidence packs from DeepResearch ledger artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import EvidencePack, to_dict


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _tokens(text: str) -> set[str]:
    return {part.lower() for part in str(text or "").replace("/", " ").replace("_", " ").split() if len(part) >= 3}


def _ranked(rows: list[dict], section: dict, text_key: str) -> list[dict]:
    section_tokens = _tokens(" ".join(str(section.get(k, "")) for k in ("title", "research_question", "section_id")))
    scored = []
    for idx, row in enumerate(rows):
        row_tokens = _tokens(str(row.get(text_key) or row.get("content") or row.get("claim_text") or row.get("title") or ""))
        score = len(section_tokens & row_tokens)
        scored.append((-score, idx, row))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [row for _score, _idx, row in scored]


def build_evidence_packs(output_dir: str | Path, ast: dict) -> dict:
    root = Path(output_dir).expanduser()
    sources = _read_jsonl(root / "sources.jsonl")
    evidence = _read_jsonl(root / "evidence.jsonl")
    claims = _read_jsonl(root / "claims.jsonl")
    links = _read_jsonl(root / "claim_evidence.jsonl")
    source_by_id = {str(row.get("id") or row.get("source_id")): row for row in sources}
    evidence_by_id = {str(row.get("id") or row.get("evidence_id")): row for row in evidence}
    evidence_to_source = {
        str(row.get("id") or row.get("evidence_id")): str(row.get("source_id") or "")
        for row in evidence
    }
    claim_to_evidence: dict[str, list[str]] = {}
    for link in links:
        claim_to_evidence.setdefault(str(link.get("claim_id") or ""), []).append(str(link.get("evidence_id") or ""))

    packs: list[dict] = []
    for section in ast.get("sections", []):
        section_id = str(section.get("section_id") or "")
        min_evidence = int(section.get("min_evidence") or 4)
        min_claims = int(section.get("min_claims") or 3)
        ranked_claims = _ranked(claims, section, "claim_text")[: max(min_claims, 6)]
        claim_ids = [str(row.get("id") or row.get("claim_id")) for row in ranked_claims if row.get("id") or row.get("claim_id")]
        evidence_ids: list[str] = []
        for cid in claim_ids:
            evidence_ids.extend(eid for eid in claim_to_evidence.get(cid, []) if eid)
        if len(set(evidence_ids)) < min_evidence:
            ranked_evidence = _ranked(evidence, section, "content")
            evidence_ids.extend(str(row.get("id") or row.get("evidence_id")) for row in ranked_evidence[: min_evidence * 2])
        evidence_ids = list(dict.fromkeys(eid for eid in evidence_ids if eid and eid in evidence_by_id))[: max(min_evidence, 8)]
        source_ids = list(dict.fromkeys(evidence_to_source.get(eid, "") for eid in evidence_ids if evidence_to_source.get(eid, "")))
        present_types = {str(source_by_id.get(sid, {}).get("source_type") or "unknown") for sid in source_ids}
        required_types = set(section.get("required_source_types") or [])
        # Use the global source/evidence pool to satisfy required survey source
        # types when lexical ranking over-selects papers. Survey sections need
        # diverse evidence packs; they should not fail only because a short
        # section title lacks words that appear in code/benchmark metadata.
        for required_type in sorted(required_types - present_types):
            source = next(
                (row for row in sources if str(row.get("source_type") or "") == required_type and str(row.get("id") or row.get("source_id") or "")),
                None,
            )
            if not source:
                continue
            sid = str(source.get("id") or source.get("source_id"))
            ev = next((row for row in evidence if str(row.get("source_id") or "") == sid), None)
            if ev:
                eid = str(ev.get("id") or ev.get("evidence_id"))
                if eid and eid not in evidence_ids:
                    evidence_ids.append(eid)
            if sid not in source_ids:
                source_ids.append(sid)
        source_types = sorted({str(source_by_id.get(sid, {}).get("source_type") or "unknown") for sid in source_ids})
        blockers: list[str] = []
        if len(evidence_ids) < min_evidence:
            blockers.append(f"evidence_count_low:{len(evidence_ids)}<{min_evidence}")
        if len(claim_ids) < min_claims:
            blockers.append(f"claim_count_low:{len(claim_ids)}<{min_claims}")
        if len(source_types) < 2:
            blockers.append(f"source_diversity_low:{len(source_types)}<2")
        missing = sorted(required_types - set(source_types))
        if missing:
            blockers.append("missing_source_types:" + ",".join(missing))
        pack = EvidencePack(
            pack_id=f"pack_{section_id.replace('/', '_')}",
            section_id=section_id,
            evidence_ids=evidence_ids,
            claim_ids=claim_ids,
            source_ids=source_ids,
            source_types=source_types,
            contradiction_slots=[f"contradiction:{section_id}:required"],
            status="blocked" if blockers else "ready",
            blockers=blockers,
        )
        packs.append(to_dict(pack))
        section_dir = root / "sections" / section_id
        section_dir.mkdir(parents=True, exist_ok=True)
        (section_dir / "evidence_pack.json").write_text(json.dumps(to_dict(pack), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (section_dir / "section.spec.json").write_text(json.dumps(section, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    payload = {"ok": True, "packs": packs, "ready": sum(1 for p in packs if p["status"] == "ready"), "blocked": sum(1 for p in packs if p["status"] == "blocked")}
    (root / "survey_evidence_packs.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
