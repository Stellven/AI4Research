#!/usr/bin/env python3
"""Validate the RSI demo source pack (the INPUT corpus).

Usage: validate_rsi_source_pack.py [PACK_DIR]
Default PACK_DIR: demo-rsi/source-pack

Checks: sources.json parses; 6-9 sources; each has id/title/authors/year/
topic_tags/source_path; ids unique; each source_path note file exists and is
non-trivial; the seven required topic areas are covered.
"""
import json
import pathlib
import sys

REQUIRED_TOPICS = {
    "recursive-self-improvement",
    "self-improving-llms",
    "test-time-recursive-thinking",
    "evaluator-verifier-driven-improvement",
    "ai-research-agents",
    "rsi-safety-governance",
    "ai-scientific-research-workbenches",
}
REQUIRED_FIELDS = ["id", "title", "authors", "year", "topic_tags", "source_path"]


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    raise SystemExit(f"SOURCE_PACK_FAIL: {msg}")


def main() -> None:
    pack_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("demo-rsi/source-pack")
    sources_json = pack_dir / "sources.json"
    if not sources_json.is_file():
        fail(f"missing {sources_json}")

    try:
        data = json.loads(sources_json.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail(f"sources.json invalid JSON: {type(exc).__name__}: {exc}")

    sources = data.get("sources") if isinstance(data, dict) else data
    if not isinstance(sources, list):
        fail("sources.json has no 'sources' list")
    if not (6 <= len(sources) <= 9):
        fail(f"expected 6-9 sources, found {len(sources)}")

    seen_ids: set[str] = set()
    covered: set[str] = set()
    for src in sources:
        if not isinstance(src, dict):
            fail(f"source entry is not an object: {src!r}")
        for field in REQUIRED_FIELDS:
            if not src.get(field):
                fail(f"source {src.get('id', '?')} missing field '{field}'")
        sid = str(src["id"])
        if sid in seen_ids:
            fail(f"duplicate source id: {sid}")
        seen_ids.add(sid)
        tags = src.get("topic_tags") or []
        if not isinstance(tags, list) or not tags:
            fail(f"source {sid} has no topic_tags")
        covered.update(str(t) for t in tags)
        note = pack_dir / str(src["source_path"])
        if not note.is_file():
            fail(f"source {sid} note file missing: {note}")
        if len(note.read_text(encoding="utf-8").strip()) < 120:
            fail(f"source {sid} note file too small: {note}")

    missing_topics = REQUIRED_TOPICS - covered
    if missing_topics:
        fail(f"topic areas not covered: {sorted(missing_topics)}")

    print(
        f"source pack OK: {len(sources)} sources, ids unique, all note files present, "
        f"all {len(REQUIRED_TOPICS)} required topic areas covered"
    )


if __name__ == "__main__":
    main()
