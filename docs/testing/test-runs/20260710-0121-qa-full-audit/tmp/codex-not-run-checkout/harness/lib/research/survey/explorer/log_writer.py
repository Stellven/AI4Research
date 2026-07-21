"""Incremental JSONL writer for elimination_log.jsonl.

S03 N6 implementation per S02 exploration-arch.md §3 (each EliminationRecord
written at the moment of elimination, not in batch) and §10 FM-3 (write
failures must surface, not silently swallow). Resume semantics: opening an
existing log file does NOT truncate; subsequent appends are concatenated so
a runner restart preserves prior records.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import asdict
from typing import Any

from research.survey.schemas import EliminationRecord


class LogWriter:
    """Append-only JSONL writer with per-record flush + fsync.

    Atomicity contract: each call to ``append()`` writes one complete JSON
    line followed by a newline, then flushes the file buffer and fsyncs the
    underlying descriptor before returning. A crash between two appends loses
    at most the in-flight record; previously appended records are durable.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Touch the file in append mode so a fresh LogWriter without any
        # append() call still creates an empty log artifact (S05 evidence).
        if not self.path.exists():
            self.path.touch()

    def append(self, record: EliminationRecord | dict[str, Any]) -> None:
        if isinstance(record, EliminationRecord):
            payload: dict[str, Any] = asdict(record)
        elif isinstance(record, dict):
            payload = dict(record)
        else:
            raise TypeError(
                "LogWriter.append: record must be EliminationRecord or dict, "
                f"got {type(record).__name__}"
            )

        kill_reason = payload.get("kill_reason", "")
        if not isinstance(kill_reason, str) or not kill_reason.strip():
            raise ValueError(
                "LogWriter.append: kill_reason must be a non-empty string "
                "(per exploration-arch.md §3 constraints)"
            )

        evidence_refs = payload.get("evidence_refs")
        if not isinstance(evidence_refs, list) or len(evidence_refs) == 0:
            raise ValueError(
                "LogWriter.append: evidence_refs must be a non-empty list "
                "(per exploration-arch.md §3 constraints)"
            )

        decision_ts = payload.get("decision_ts", "")
        if not isinstance(decision_ts, str) or not decision_ts.strip():
            raise ValueError(
                "LogWriter.append: decision_ts must be set at elimination "
                "moment (per exploration-arch.md §3)"
            )

        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for raw in f:
                stripped = raw.strip()
                if not stripped:
                    continue
                records.append(json.loads(stripped))
        return records

    def count(self) -> int:
        return len(self.read_all())
