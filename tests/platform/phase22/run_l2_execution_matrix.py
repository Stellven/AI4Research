"""Execute the Phase 22 L2 matrix and write classification receipts."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
MATRIX = Path(__file__).with_name("l2_execution_matrix.json")


def command_for(probe: dict, *, python: str, node: str | None, bash: str | None, bun: str | None) -> list[str] | None:
    runner = probe["runner"]
    target = probe["target"]
    if runner == "pytest":
        return [python, "-m", "pytest", "-q", target]
    if runner == "python_script":
        return [python, target]
    if runner == "node":
        if not node:
            return None
        return [node, "--test", str(REPO / target)]
    if runner == "node_ts":
        if not node:
            return None
        return [
            node,
            "--experimental-transform-types",
            "--loader",
            "./tests/platform/phase22/node_typescript_loader.mjs",
            "--test",
            f"./{target}",
        ]
    if runner == "bash":
        if not bash:
            return None
        return [
            bash,
            "-lc",
            (
                'chmod +x "$(pwd)/tests/platform/phase22/bin/python3"; '
                f'PATH="$(pwd)/tests/platform/phase22/bin:$PATH" {target}'
            ),
        ]
    if runner == "bun":
        if not bun:
            return None
        return [bun, "test", target]
    raise ValueError(f"Unknown runner: {runner}")


def execute_probe(
    probe_id: str,
    probe: dict,
    *,
    python: str,
    node: str | None,
    bash: str | None,
    bun: str | None,
    audit_home: Path,
    timeout: int,
) -> tuple[str, dict]:
    command = command_for(probe, python=python, node=node, bash=bash, bun=bun)
    if command is None:
        return probe_id, {
            "probe_id": probe_id,
            "status": "FAIL",
            "returncode": 127,
            "duration_seconds": 0.0,
            "command": "",
            "stdout_tail": "",
            "stderr_tail": f"Required runner is unavailable for {probe['runner']}: {probe['target']}",
        }

    probe_home = audit_home / probe_id
    probe_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(probe_home),
            "USERPROFILE": str(probe_home),
            "PYTHONPATH": str(REPO / "harness"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        returncode = 124
        stdout = error.stdout or ""
        stderr = (error.stderr or "") + f"\nTimed out after {timeout} seconds."
    except OSError as error:
        returncode = 127
        stdout = ""
        stderr = f"{type(error).__name__}: {error}"
    duration = time.monotonic() - started
    return probe_id, {
        "probe_id": probe_id,
        "status": "PASS" if returncode == 0 else "FAIL",
        "returncode": returncode,
        "duration_seconds": round(duration, 3),
        "command": subprocess.list2cmdline(command),
        "stdout_tail": stdout[-12000:],
        "stderr_tail": stderr[-12000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--bash", default=shutil.which("bash"))
    parser.add_argument("--bun", default=shutil.which("bun"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_home = Path(tempfile.mkdtemp(prefix="opensolar-phase22-l2-"))
    try:
        probe_ids = sorted({row["probe_id"] for row in matrix["features"] if row["probe_id"]})
        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(
                    execute_probe,
                    probe_id,
                    matrix["probes"][probe_id],
                    python=args.python,
                    node=args.node,
                    bash=args.bash,
                    bun=args.bun,
                    audit_home=audit_home,
                    timeout=args.timeout,
                ): probe_id
                for probe_id in probe_ids
            }
            for future in as_completed(futures):
                probe_id, result = future.result()
                results[probe_id] = result
                print(f"{probe_id}: {result['status']} ({result['duration_seconds']:.3f}s)", flush=True)
    finally:
        shutil.rmtree(audit_home, ignore_errors=True)

    classifications = []
    for row in matrix["features"]:
        item = dict(row)
        if row["implementation_status"] == "NOT_IMPLEMENTED":
            item.update(
                {
                    "classification_code": 3,
                    "classification": "Function not implemented and test blocked",
                    "test_result": "BLOCKED",
                    "runner_command": "",
                    "returncode": "",
                    "duration_seconds": 0.0,
                    "evidence_summary": row["blocked_reason"],
                }
            )
        else:
            result = results[row["probe_id"]]
            passed = result["status"] == "PASS"
            item.update(
                {
                    "classification_code": 1 if passed else 2,
                    "classification": (
                        "Function implemented and test passed"
                        if passed
                        else "Function implemented but test failed"
                    ),
                    "test_result": result["status"],
                    "runner_command": result["command"],
                    "returncode": result["returncode"],
                    "duration_seconds": result["duration_seconds"],
                    "evidence_summary": (
                        "Executable representative-core probe passed."
                        if passed
                        else (result["stderr_tail"] or result["stdout_tail"])[-1200:]
                    ),
                }
            )
        classifications.append(item)

    counts = {
        "total_l2": len(classifications),
        "implemented_pass": sum(row["classification_code"] == 1 for row in classifications),
        "implemented_fail": sum(row["classification_code"] == 2 for row in classifications),
        "not_implemented_blocked": sum(row["classification_code"] == 3 for row in classifications),
        "unique_probes": len(results),
        "passing_probes": sum(result["status"] == "PASS" for result in results.values()),
        "failing_probes": sum(result["status"] == "FAIL" for result in results.values()),
    }
    payload = {
        "schema": "phase22.l2_execution_results.v1",
        "matrix": str(args.matrix.resolve()),
        "counts": counts,
        "probe_results": {key: results[key] for key in sorted(results)},
        "classifications": classifications,
    }
    json_path = args.output_dir / "phase22_l2_execution_results.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    csv_fields = [
        "case_id",
        "sheet",
        "level_1_feature",
        "level_2_feature",
        "classification_code",
        "classification",
        "test_result",
        "probe_id",
        "runner_command",
        "returncode",
        "duration_seconds",
        "implementation_entrypoints",
        "supported_boundaries_exclusions",
        "evidence_summary",
    ]
    with (args.output_dir / "phase22_l2_classification.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(classifications)

    lines = [
        "# Phase 22 L2 execution classification",
        "",
        f"- Total L2 features: {counts['total_l2']}",
        f"- Implemented and passed: {counts['implemented_pass']}",
        f"- Implemented but failed: {counts['implemented_fail']}",
        f"- Not implemented / blocked: {counts['not_implemented_blocked']}",
        f"- Unique executable probes: {counts['unique_probes']} ({counts['passing_probes']} passed, {counts['failing_probes']} failed)",
        "",
        "| Sheet | Level 1 | Level 2 | Classification | Probe |",
        "|---|---|---|---|---|",
    ]
    for row in classifications:
        lines.append(
            f"| {row['sheet']} | {row['level_1_feature']} | {row['level_2_feature']} | "
            f"{row['classification']} | {row['probe_id'] or 'BLOCKED'} |"
        )
    (args.output_dir / "phase22_l2_classification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
