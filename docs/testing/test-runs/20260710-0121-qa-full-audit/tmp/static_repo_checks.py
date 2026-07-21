from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


def tracked(checkout: Path, patterns: list[str]) -> list[str]:
    result = subprocess.run(["git", "ls-files", *patterns], cwd=checkout, text=True, capture_output=True, check=True)
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    checkout = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    failures = []
    counts = {"json": 0, "yaml": 0, "shell": 0}

    for relative in tracked(checkout, ["*.json", "**/*.json"]):
        path = checkout / relative
        if not path.is_file():
            continue
        counts["json"] += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            failures.append({"kind": "json_parse", "path": relative, "error": str(error)})

    for relative in tracked(checkout, ["*.yaml", "*.yml", "**/*.yaml", "**/*.yml"]):
        path = checkout / relative
        if not path.is_file():
            continue
        counts["yaml"] += 1
        try:
            list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except Exception as error:
            failures.append({"kind": "yaml_parse", "path": relative, "error": str(error)})

    for relative in tracked(checkout, ["*.sh", "**/*.sh"]):
        path = checkout / relative
        if not path.is_file():
            continue
        counts["shell"] += 1
        result = subprocess.run(["/opt/homebrew/bin/bash", "-n", str(path)], text=True, capture_output=True, check=False)
        if result.returncode != 0:
            failures.append({
                "kind": "shell_syntax", "path": relative, "exit_code": result.returncode,
                "error": result.stderr.strip(),
            })

    payload = {"counts": counts, "failure_count": len(failures), "failures": failures}
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": counts, "failure_count": len(failures)}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
