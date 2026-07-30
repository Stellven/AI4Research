import csv
import json
import statistics
import sys
import time
from pathlib import Path


def main(argv):
    if len(argv) != 3:
        print(json.dumps({"error": "usage: python run_text_experiment.py <samples.csv> <output.json>"}))
        return 2

    data_path = Path(argv[1])
    output_path = Path(argv[2])
    rows = list(csv.DictReader(data_path.open(encoding="utf-8")))
    details = []
    summaries = {}

    for mode in ("baseline", "variant"):
        correct = 0
        latencies = []
        for row in rows:
            start = time.perf_counter()
            text = row["text"]
            if mode == "baseline":
                probe = text
                prediction = "positive" if probe.startswith("pass:") or probe.startswith("pass with") else "negative"
            else:
                probe = text.lower().replace(" - ", ": ").replace("-", ":")
                prediction = "positive" if probe.startswith("pass:") or probe.startswith("pass with") else "negative"
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)
            correct += int(prediction == row["label"])
            details.append(
                {
                    "mode": mode,
                    "text": text,
                    "label": row["label"],
                    "prediction": prediction,
                    "latency_ms": elapsed,
                }
            )
        summaries[mode] = {
            "accuracy": correct / len(rows),
            "median_latency_ms": statistics.median(latencies),
        }

    metrics = [
        {"name": "baseline_accuracy", "value": summaries["baseline"]["accuracy"]},
        {"name": "variant_accuracy", "value": summaries["variant"]["accuracy"]},
        {"name": "accuracy_uplift", "value": summaries["variant"]["accuracy"] - summaries["baseline"]["accuracy"]},
        {"name": "variant_median_latency_ms", "value": summaries["variant"]["median_latency_ms"]},
    ]
    payload = {
        "schema": "experiment_result.v1",
        "task_id": "phase22-j21-local-runtime",
        "sprint_id": "phase22-j21-local-runtime",
        "node_id": "node-phase22-j21-local-runtime",
        "status": "completed",
        "inputs": {"dataset_path": str(data_path)},
        "outputs": {
            "result": {
                "experiment_id": "p22-j21-local-experiment",
                "outcome": "supports",
                "metrics": metrics,
                "evidence_ids": ["runtime:p22-j21-local-experiment"],
                "logs": ["Fixture runtime executed bounded local CSV classification experiment."],
                "details": details,
            }
        },
        "artifacts": [{"type": "local_experiment_result", "path": str(output_path)}],
        "provenance": {
            "operator_id": "phase22-j21-fixture-runtime",
            "implementation_package": "tests.journeys.phase22.fixtures.j21_experiment_build_handoff"
        },
        "limitations": ["Bounded local fixture runtime; not an external benchmark."]
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
