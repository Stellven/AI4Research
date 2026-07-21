"""P7 retrieval pack contract: provenance-complete writes and strict closeout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.evaluator import evaluate_retrieval_closeout  # noqa: E402
from research.hashing import content_hash  # noqa: E402
from research.source_pack import write_source_pack  # noqa: E402
from research.sources.base import FetchResult  # noqa: E402


def _fetch(source_id: str, text: str, *, source_type: str = "paper") -> FetchResult:
    host = "arxiv.org" if source_type == "paper" else "docs.example.org"
    return FetchResult(
        source_id=source_id,
        connector_id="codex_live_search",
        title=f"Title for {source_id}",
        raw_text=text,
        source_url=f"https://{host}/{source_id.replace('/', '-')}",
        metadata={"source_type": source_type},
    )


def _valid_pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pack"
    write_source_pack(
        pack,
        [
            _fetch("web_a", "retrieval provenance lands on disk with verifying hashes"),
            _fetch("web_b", "research agents gather independent source material", source_type="official_pricing"),
        ],
    )
    return pack


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rewrite(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_writer_emits_distinct_contained_extracts_and_canonical_source_types(tmp_path):
    pack = tmp_path / "pack"
    summary = write_source_pack(
        pack,
        [
            _fetch("web/a", "first source", source_type="official_pricing"),
            _fetch("web?a", "second source", source_type="documentation"),
        ],
    )

    assert summary["source_count"] == 2
    sources = _rows(pack / "sources.jsonl")
    assert {row["source_type"] for row in sources} == {"official_doc"}
    extract_paths = [row["extract_path"] for row in sources]
    assert len(set(extract_paths)) == 2
    for row in sources:
        extract = (pack / row["extract_path"]).resolve()
        assert extract.is_relative_to((pack / "extracts").resolve())
        assert content_hash(extract.read_text(encoding="utf-8")) == row["content_sha256"]


def test_valid_pack_passes_and_can_persist_closeout(tmp_path):
    pack = _valid_pack(tmp_path)
    result = evaluate_retrieval_closeout(pack, persist=True)

    assert result["ok"] is True
    assert result["verdict"] == "pass"
    assert result["issues"] == []
    assert result["metrics"]["source_count"] == 2
    assert result["metrics"]["evidence_count"] == 2
    assert result["metrics"]["source_high_authority_count"] >= 1
    assert json.loads((pack / "retrieval_closeout.json").read_text(encoding="utf-8"))["verdict"] == "pass"


def test_retrieval_evaluation_is_pure_by_default(tmp_path):
    """An evaluator must not alter the frozen evidence it is judging."""
    pack = _valid_pack(tmp_path)
    before = {
        path.relative_to(pack): path.read_bytes()
        for path in sorted(pack.rglob("*"))
        if path.is_file()
    }

    result = evaluate_retrieval_closeout(pack)

    after = {
        path.relative_to(pack): path.read_bytes()
        for path in sorted(pack.rglob("*"))
        if path.is_file()
    }
    assert result["ok"] is True
    assert after == before


def test_missing_pack_is_repairable(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = evaluate_retrieval_closeout(empty)

    assert result["verdict"] == "repairable_fail"
    assert {"sources_jsonl_missing", "evidence_jsonl_missing"} <= set(result["issues"])


def test_tampered_extract_is_hard_fail(tmp_path):
    pack = _valid_pack(tmp_path)
    source = _rows(pack / "sources.jsonl")[0]
    extract = pack / source["extract_path"]
    extract.write_text(extract.read_text(encoding="utf-8") + " tampered", encoding="utf-8")

    result = evaluate_retrieval_closeout(pack)

    assert result["verdict"] == "hard_fail"
    assert any(issue.startswith("source_extract_hash_mismatch:web_a") for issue in result["issues"])


def test_absolute_traversing_and_symlink_escape_extracts_are_hard_fail(tmp_path):
    pack = _valid_pack(tmp_path)
    sources = _rows(pack / "sources.jsonl")
    outside = tmp_path / "outside.md"
    outside.write_text(sources[0]["title"], encoding="utf-8")

    sources[0]["extract_path"] = str(outside)
    sources[1]["extract_path"] = "extracts/../../outside.md"
    _rewrite(pack / "sources.jsonl", sources)
    absolute_and_traversal = evaluate_retrieval_closeout(pack)
    assert absolute_and_traversal["verdict"] == "hard_fail"
    assert any(issue.startswith("source_extract_path_outside_pack") for issue in absolute_and_traversal["issues"])

    pack = _valid_pack(tmp_path / "symlink-case")
    sources = _rows(pack / "sources.jsonl")
    link = pack / sources[0]["extract_path"]
    link.unlink()
    link.symlink_to(outside)
    symlink_escape = evaluate_retrieval_closeout(pack)
    assert symlink_escape["verdict"] == "hard_fail"
    assert any(issue.startswith("source_extract_path_outside_pack:web_a") for issue in symlink_escape["issues"])


def test_malformed_jsonl_and_duplicate_ids_are_hard_fail(tmp_path):
    pack = _valid_pack(tmp_path)
    with (pack / "sources.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")
    malformed = evaluate_retrieval_closeout(pack)
    assert malformed["verdict"] == "hard_fail"
    assert "sources_jsonl_invalid_json:line=3" in malformed["issues"]

    pack = _valid_pack(tmp_path / "duplicate-case")
    sources = _rows(pack / "sources.jsonl")
    sources[1]["id"] = sources[1]["source_id"] = "web_a"
    _rewrite(pack / "sources.jsonl", sources)
    duplicate = evaluate_retrieval_closeout(pack)
    assert duplicate["verdict"] == "hard_fail"
    assert "source_id_duplicate:web_a" in duplicate["issues"]


def test_evidence_hash_span_and_source_integrity_are_hard_fail(tmp_path):
    pack = _valid_pack(tmp_path)
    evidence = _rows(pack / "evidence.jsonl")
    evidence[0]["content_hash"] = "0" * 64
    evidence[0]["span_start"] = 2
    evidence[1]["source_id"] = "web_unknown"
    _rewrite(pack / "evidence.jsonl", evidence)

    result = evaluate_retrieval_closeout(pack)

    assert result["verdict"] == "hard_fail"
    assert "evidence_content_hash_mismatch:" + evidence[0]["id"] in result["issues"]
    assert "evidence_source_unknown:web_unknown" in result["issues"]
    assert "evidence_span_mismatch:" + evidence[0]["id"] in result["issues"]


def test_missing_source_metadata_is_hard_fail(tmp_path):
    pack = _valid_pack(tmp_path)
    sources = _rows(pack / "sources.jsonl")
    sources[0]["url"] = ""
    sources[0].pop("provider")
    _rewrite(pack / "sources.jsonl", sources)

    result = evaluate_retrieval_closeout(pack)

    assert result["verdict"] == "hard_fail"
    assert "source_metadata_missing:web_a:url,provider" in result["issues"]
