from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--feature-ids", default="")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("missing command after --")

    run_root = Path(args.run_root).resolve()
    evidence_dir = run_root / "evidence" / "commands"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = evidence_dir / f"{args.id}.stdout.txt"
    stderr_path = evidence_dir / f"{args.id}.stderr.txt"
    meta_path = evidence_dir / f"{args.id}.meta.json"
    env = os.environ.copy()
    for item in args.env:
        key, separator, value = item.partition("=")
        if not separator:
            parser.error(f"invalid --env value: {item}")
        env[key] = value

    started = iso_now()
    started_clock = datetime.now(timezone.utc)
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        try:
            completed = subprocess.run(
                command,
                cwd=Path(args.cwd).resolve(),
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                check=False,
                timeout=args.timeout_seconds,
            )
            return_code = completed.returncode
        except FileNotFoundError as error:
            stderr_handle.write(f"COMMAND_NOT_FOUND: {error}\n".encode("utf-8"))
            return_code = 127
        except subprocess.TimeoutExpired as error:
            stderr_handle.write(
                f"COMMAND_TIMEOUT: exceeded {args.timeout_seconds} seconds: {error}\n".encode("utf-8")
            )
            return_code = 124
    ended_clock = datetime.now(timezone.utc)
    ended = iso_now()
    duration = (ended_clock - started_clock).total_seconds()
    command_text = subprocess.list2cmdline(command)
    row = {
        "command_id": args.id,
        "phase": args.phase,
        "linked_feature_ids": args.feature_ids,
        "cwd": str(Path(args.cwd).resolve()),
        "command": command_text,
        "start_time": started,
        "end_time": ended,
        "duration_seconds": f"{duration:.3f}",
        "exit_code": return_code,
        "stdout_path": str(stdout_path.relative_to(run_root)),
        "stderr_path": str(stderr_path.relative_to(run_root)),
    }
    log_path = run_root / "command-log.tsv"
    fieldnames = list(row)
    write_header = not log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    meta_path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"command_id": args.id, "exit_code": return_code, "duration_seconds": duration}))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
