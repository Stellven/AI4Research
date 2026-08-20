"""Write accepted sources as a DeepResearch source pack.

This workflow grew its own artifact format -- `source_validation.json` with an
`accepted` list -- while Solar already had one. `harness/lib/research` reads and
writes packs of `sources.jsonl` + `evidence.jsonl` + `extracts/`, and everything
downstream of a pack already exists: `grounded_synthesis.compile_grounded_report`
compiles one into `final.md`, `report_ast.json` and `research_eval.json`, and
`evaluator.evaluate_artifacts` gates those on citation accuracy, unsupported
rate, per-section citations and source diversity.

None of that could be used because the accepted sources were never written in
the format those components read. This module is the adapter, and it is
deliberately thin: it converts, it does not synthesise. `write_source_pack`
already refuses to invent missing data, so a source lacking text is skipped and
counted rather than padded.

Binding note: `harness/lib/research/sources/base.py` and its `tools/` twin have
diverged. The lib copy (2026-08-07) carries provider, query, retrieved_at and
response_status; the tools copy (2026-05-31) does not. Provenance is the point
of this workflow, so the lib copy is the one bound here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parents[4] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from research.source_pack import write_source_pack  # noqa: E402
from research.sources.base import FetchResult  # noqa: E402


def canonical_text(value: Any) -> str:
    """Collapse whitespace the way `evidence_synthesis` already does.

    `evidence_synthesis._normalize_quotes` verifies a quote by collapsing both
    the quote and the source text with `" ".join(x.split())`, and it stores the
    COLLAPSED quote. `grounded_synthesis` then checks `quote in evidence_text`
    byte-exactly against the pack. Those two only agree if the pack carries the
    same collapsed form, so the rule is copied here verbatim rather than
    re-derived -- a second, subtly different normalizer is precisely the seam
    this fixes.

    The live CRISPR run failed on it. Publisher text strips italic markup and
    leaves doubled spaces around the Latin phrases biomedical style italicises:

        "Benchmarking 13  in silico  prediction tools identified Cas-OFFinder"

    The model quoted it with single spaces, which is what the source reads as.
    The quote was present, normalized; absent, byte-exact; and the compile
    aborted. arXiv line-wrapped abstracts fail the same way for the same
    reason.

    Only whitespace is touched, so no word, number or character of the source
    is altered.
    """
    return " ".join(str(value or "").split())


def _text_of(source: dict[str, Any]) -> str:
    """The strongest text this source carries, without inventing any."""
    for key in ("content", "extracted_text", "content_summary", "abstract"):
        value = str(source.get(key) or "").strip()
        if value:
            return value
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return str(metadata.get("abstract") or "").strip()


def fetch_results_from_accepted(accepted: list[dict[str, Any]]) -> list[FetchResult]:
    """Adapt validated sources to the shape the pack writer consumes.

    Sources with no text are still adapted, with fetch_status "skipped" rather
    than a fabricated body. write_source_pack drops them and reports the count,
    so a thin evidence base is visible instead of silently padded.
    """
    results: list[FetchResult] = []
    for index, source in enumerate(accepted):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or f"source-{index + 1:03d}").strip()
        # Canonicalised here, at the one place text enters the pack, so that
        # content, content_hash, span_end and the extract file all derive from
        # the same string write_source_pack is handed.
        text = canonical_text(_text_of(source))
        provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        results.append(
            FetchResult(
                source_id=source_id,
                connector_id=str(source.get("provider") or provenance.get("provider") or "unknown"),
                title=str(source.get("title") or "").strip(),
                raw_text=text,
                source_url=str(source.get("url") or source.get("canonical_id") or "") or None,
                # "fetched" asserts a document was retrieved. Without text that
                # is not true, and the pack writer must be told so.
                fetch_status="fetched" if text else "skipped",
                metadata={
                    "canonical_id": str(source.get("canonical_id") or ""),
                    "year": metadata.get("year"),
                    "venue": str(metadata.get("venue") or ""),
                    "authors": metadata.get("authors") or [],
                    "acquisition_channel": str(source.get("acquisition_channel") or ""),
                    "candidate_sha256": str(source.get("candidate_sha256") or ""),
                },
            )
        )
    return results


def write_validated_pack(
    *, source_validation: dict[str, Any], output_dir: Path | str
) -> dict[str, Any]:
    """Write the accepted sources of one validation artifact as a pack."""
    accepted = [item for item in (source_validation.get("accepted") or []) if isinstance(item, dict)]
    fetches = fetch_results_from_accepted(accepted)
    manifest = write_source_pack(output_dir, fetches)
    manifest["accepted_input_count"] = len(accepted)
    # A pack with no usable text cannot ground a report. Say so here rather
    # than letting synthesis discover it as an empty evidence set.
    manifest["usable"] = bool(manifest.get("source_count"))
    return manifest
