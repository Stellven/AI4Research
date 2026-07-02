#!/usr/bin/env python3
"""Generate Codex-native wrapper skills for Solar-orchestrated AutoSci routes."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS_ROOT = REPO_ROOT / "harness"
ROUTE_CONFIG = HARNESS_ROOT / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
DEFAULT_OUTPUT = REPO_ROOT / ".agents" / "skills"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def parse_frontmatter_description(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if line.strip().startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def skill_name_ok(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name))


def route_description(route: dict[str, Any], source_skills: Path | None) -> str:
    skill = str(route["native_skill"])
    source_description = ""
    if source_skills:
        source_description = parse_frontmatter_description(source_skills / skill / "SKILL.md")
    base = source_description or (
        f"Solar AutoSci wrapper for ${skill}. Use when the user invokes ${skill}, "
        f"asks for AutoSci {skill}, or requests the corresponding Solar research workflow."
    )
    capability = str(route.get("solar_capability") or "Solar AutoSci")
    backend_action = str(route.get("solar_backend_action") or "route")
    return (
        f"{base} This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution "
        f"through Solar Harness ({capability}, backend action {backend_action}); do not execute native "
        "AutoSci repo tools directly."
    )


def wrapper_body(route: dict[str, Any]) -> str:
    skill = str(route["native_skill"])
    command = f"${skill}"
    backend_action = str(route.get("solar_backend_action") or "N/A")
    capability = str(route.get("solar_capability") or "N/A")
    status = str(route.get("coverage_status") or "N/A")
    side_effect_policy = str(route.get("side_effect_policy") or "N/A")
    limitations = [str(item) for item in route.get("limitations") or []]
    limitation_lines = "".join(f"- {item}\n" for item in limitations) or "- N/A\n"
    return f"""# {command}

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${{HARNESS_DIR:-$HOME/.solar/harness}}/solar-harness.sh" '{command}' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '{command}' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `{capability}`
- Backend action: `{backend_action}`
- Coverage status: `{status}`
- Side-effect policy: `{side_effect_policy}`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

{limitation_lines}"""


def generate(route_config: Path, output_dir: Path, source_skills: Path | None = None) -> dict[str, Any]:
    payload = load_json(route_config)
    routes = [item for item in payload.get("routes") or [] if isinstance(item, dict) and item.get("native_skill")]
    written: list[str] = []
    for route in sorted(routes, key=lambda item: str(item["native_skill"])):
        skill = str(route["native_skill"])
        if not skill_name_ok(skill):
            raise ValueError(f"invalid skill name for Codex projection: {skill}")
        skill_dir = output_dir / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        description = route_description(route, source_skills)
        content = "\n".join(
            [
                "---",
                f"name: {skill}",
                f"description: {json.dumps(description)}",
                "---",
                "",
                wrapper_body(route),
            ]
        )
        if not skill_path.exists() or skill_path.read_text(encoding="utf-8") != content:
            skill_path.write_text(content, encoding="utf-8")
        written.append(str(skill_path))
    return {"ok": True, "count": len(written), "output_dir": str(output_dir.resolve()), "skills": written}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-config", default=str(ROUTE_CONFIG))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--source-skills", help="Optional source .agents/skills directory for trigger descriptions")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = generate(
        Path(args.route_config),
        Path(args.output_dir),
        Path(args.source_skills) if args.source_skills else None,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
