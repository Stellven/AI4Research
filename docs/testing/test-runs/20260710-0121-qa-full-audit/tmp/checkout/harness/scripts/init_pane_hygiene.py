#!/usr/bin/env python3
"""Initialize pane-hygiene.json from tmux list-panes discovery (per data_models.md §1.5).

Does NOT write to real run/pane-hygiene.json when --dry-run is set (default for tests).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from lib.pane_hygiene_registry import PaneHygieneRegistry, PaneState
from lib.pane_role_pool import infer_role, list_tmux_panes

DEFAULT_MODEL_MAP: dict[str, str] = {
    "solar-harness:0.0": "anthropic-opus",
    "solar-harness:0.1": "glm-5.1",
    "solar-harness:0.2": "glm-5.1",
    "solar-harness:0.3": "anthropic-opus",
    "solar-harness-lab:0.0": "glm-5.1",
    "solar-harness-lab:0.1": "glm-5.1",
    "solar-harness-lab:0.2": "glm-5.1",
    "solar-harness-lab:0.3": "anthropic-sonnet",
}


def discover_panes(tmux_binary: str = "tmux") -> list[str]:
    return [item["pane"] for item in list_tmux_panes()]


def init_registry(
    output_path: str,
    pane_ids: Optional[list[str]] = None,
    *,
    tmux_binary: str = "tmux",
    pane_titles: Optional[dict[str, str]] = None,
) -> dict:
    if pane_ids is None:
        pane_ids = discover_panes(tmux_binary)
    if pane_titles is None:
        pane_titles = {item["pane"]: item["title"] for item in list_tmux_panes()}
    registry = PaneHygieneRegistry(output_path)
    registered = []
    for pid in pane_ids:
        role = infer_role(pid, pane_titles.get(pid, ""))
        model = DEFAULT_MODEL_MAP.get(pid)
        try:
            already_present = True
            try:
                registry.get_pane_state(pid)
            except KeyError:
                already_present = False
            registry.ensure_pane(pid, role, initial_state=PaneState.clean, model=model)
            if not already_present:
                registered.append(pid)
        except Exception:
            pass
    return {"registered": registered, "count": len(registered)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize pane-hygiene.json")
    parser.add_argument("--output", default=".solar/harness/run/pane-hygiene.json")
    parser.add_argument("--tmux", default="tmux")
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()

    if args.dry_run:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            result = init_registry(f.name, tmux_binary=args.tmux)
        print(json.dumps(result, indent=2))
        return

    result = init_registry(args.output, tmux_binary=args.tmux)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
