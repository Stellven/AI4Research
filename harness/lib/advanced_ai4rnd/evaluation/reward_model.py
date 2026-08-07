"""Tiny trainable reward model with persistent reference artifacts."""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokens(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_RE.findall(text)]


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class RewardModel:
    """A deterministic linear reward scorer that can train and reload."""

    schema_version = "solar.advanced_ai4rnd.reward_model.v1"

    def __init__(self, artifact_path: str | Path):
        self.artifact_path = Path(artifact_path)
        self.state: dict[str, Any] = (
            json.loads(self.artifact_path.read_text(encoding="utf-8")) if self.artifact_path.exists() else {}
        ) or {"schema_version": self.schema_version, "weights": {}, "updates": []}

    def train(self, examples: Sequence[Mapping[str, Any]], *, learning_rate: float = 0.25) -> dict[str, Any]:
        if not examples:
            raise ValueError("reward training requires examples")
        before = dict(self.state.get("weights", {}))
        weights = Counter({str(k): float(v) for k, v in before.items()})
        for example in examples:
            text = f"{example.get('prompt', '')} {example.get('response', '')}"
            target = float(example["reward"])
            prediction = self.score(text)
            error = target - prediction
            for token in set(_tokens(text)):
                weights[token] += learning_rate * error
        self.state["weights"] = {key: round(value, 8) for key, value in sorted(weights.items()) if abs(value) > 1e-9}
        update = {
            "created_at": _now(),
            "reference_path": str(self.artifact_path),
            "example_count": len(examples),
            "weight_count_before": len(before),
            "weight_count_after": len(self.state["weights"]),
            "changed": before != self.state["weights"],
        }
        self.state["updates"].append(update)
        _atomic_write_json(self.artifact_path, self.state)
        return update

    def score(self, text: str) -> float:
        weights = self.state.get("weights", {})
        total = sum(float(weights.get(token, 0.0)) for token in set(_tokens(text)))
        return 1.0 / (1.0 + math.exp(-total))
