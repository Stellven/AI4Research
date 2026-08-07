"""Held-out judge calibration with auditable evidence."""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class JudgeCalibrator:
    """Fit a one-parameter affine judge correction on held-out fixtures."""

    schema_version = "solar.advanced_ai4rnd.judge_calibration.v1"

    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)
        self.state: dict[str, Any] = (
            json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}
        ) or {"schema_version": self.schema_version, "runs": []}

    def calibrate(self, heldout_fixture: Sequence[Mapping[str, Any]], evidence_path: str | Path) -> dict[str, Any]:
        if not heldout_fixture:
            raise ValueError("heldout_fixture must contain labeled judge examples")
        labels = [float(item["label"]) for item in heldout_fixture]
        raw_scores = [float(item["judge_score"]) for item in heldout_fixture]
        raw_bias = sum(label - score for label, score in zip(labels, raw_scores)) / len(labels)
        corrected = [min(1.0, max(0.0, score + raw_bias)) for score in raw_scores]
        before_mae = sum(abs(label - score) for label, score in zip(labels, raw_scores)) / len(labels)
        after_mae = sum(abs(label - score) for label, score in zip(labels, corrected)) / len(labels)
        evidence = {
            "schema_version": self.schema_version,
            "created_at": _now(),
            "fixture_kind": "held_out",
            "heldout_ids": [str(item.get("id")) for item in heldout_fixture],
            "calibration": {
                "method": "affine_bias_correction",
                "bias": round(raw_bias, 8),
                "before_mae": round(before_mae, 8),
                "after_mae": round(after_mae, 8),
                "improved": after_mae <= before_mae,
            },
            "examples": [
                {
                    "id": str(item.get("id")),
                    "label": label,
                    "raw_score": raw,
                    "calibrated_score": round(calibrated, 8),
                }
                for item, label, raw, calibrated in zip(heldout_fixture, labels, raw_scores, corrected)
            ],
        }
        self.state["latest_bias"] = raw_bias
        self.state["runs"].append(evidence)
        _atomic_write_json(self.state_path, self.state)
        _atomic_write_json(Path(evidence_path), evidence)
        return evidence

    def score(self, judge_score: float) -> float:
        bias = float(self.state.get("latest_bias", 0.0))
        return min(1.0, max(0.0, float(judge_score) + bias))
