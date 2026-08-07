from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


BASELINE = [5, 4, 5, 6]
INTERVENTION = [2, 1, 2, 1]


def mean(values: list[int]) -> float:
    return sum(values) / len(values)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_bounded_experiment.py OUTPUT_JSON")
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    baseline_mean = mean(BASELINE)
    intervention_mean = mean(INTERVENTION)
    reduction = ((baseline_mean - intervention_mean) / baseline_mean) * 100.0
    payload = {
        "schema": "phase5.local_experiment_observations.v1",
        "baseline": BASELINE,
        "intervention": INTERVENTION,
        "baseline_mean": baseline_mean,
        "intervention_mean": intervention_mean,
        "unsupported_claim_reduction_percent": reduction,
        "supports_minimum_reduction": reduction >= 50.0,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "reduction_percent": reduction}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
