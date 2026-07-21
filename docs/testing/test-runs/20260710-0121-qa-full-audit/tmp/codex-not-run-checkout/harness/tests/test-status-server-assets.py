#!/usr/bin/env python3
"""Regression test for Solar status-server accepted asset packages."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_assets_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory(prefix="solar-assets-test-") as td:
        base = Path(td)
        harness = base / "harness"
        knowledge = base / "Knowledge"
        sprints = harness / "sprints"
        sid = "sprint-test-assets"

        accepted_dir = knowledge / "_raw" / "solar-harness" / "accepted"
        manifest_path = knowledge / "_raw" / "solar-harness" / ".manifest" / "accepted-artifacts.json"
        dispatch_rel = "_raw/solar-harness/.dispatch/sprint-test-assets.dispatch.md"

        write(
            accepted_dir / f"{sid}.accepted.md",
            "\n".join(
                [
                    "---",
                    f"sprint_id: {sid}",
                    "title: Asset Package Test",
                    "status: passed",
                    "accepted_at: 2026-05-22T00:00:00Z",
                    "exported_at: 2026-05-22T00:01:00Z",
                    "planning_html: true",
                    "---",
                    "# Accepted Sprint Knowledge: Asset Package Test",
                    "## Human-readable HTML Artifacts",
                    "Planning HTML text.",
                ]
            ),
        )
        write(knowledge / dispatch_rel, "# Dispatch\n")
        write(
            manifest_path,
            json.dumps(
                {
                    sid: {
                        "source_hash": "abc123",
                        "ingest_dispatch": dispatch_rel,
                        "exported_at": "2026-05-22T00:01:00Z",
                    }
                }
            ),
        )
        write(
            sprints / f"{sid}.status.json",
            json.dumps(
                {
                    "status": "passed",
                    "phase": "eval_passed",
                    "title": "Asset Package Test",
                    "artifacts": {
                        "design_html": f"sprints/{sid}.design.html",
                        "planning_html": f"sprints/{sid}.planning.html",
                        "prd_html": f"sprints/{sid}.prd.html",
                    },
                }
            ),
        )
        write(sprints / f"{sid}.design.html", "<!doctype html><h1>Design HTML</h1>")
        write(sprints / f"{sid}.plan.md", "# Plan\n")
        write(sprints / f"{sid}.handoff.md", "# Handoff\n")
        write(sprints / f"{sid}.eval.md", "# Eval\n")
        write(sprints / f"{sid}.planning.html", "<!doctype html><h1>Planning HTML</h1>")
        write(sprints / f"{sid}.prd.html", "<!doctype html><h1>PRD HTML</h1>")

        mod.HARNESS_DIR = harness
        mod.SPRINTS_DIR = sprints
        mod.KNOWLEDGE_DIR = knowledge
        mod.ACCEPTED_ASSETS_DIR = accepted_dir
        mod.ACCEPTED_ASSETS_MANIFEST = manifest_path
        mod.OPEN_ALLOWED_ROOTS = [harness, knowledge]

        payload = mod._asset_packages_payload(limit=10)
        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["html_asset_packages"] == 1
        item = payload["items"][0]
        assert item["sid"] == sid
        assert item["title"] == "Asset Package Test"
        assert item["has_html"] is True
        assert item["accepted_md"]["exists"] is True
        assert item["dispatch"]["exists"] is True
        labels = {artifact["label"]: artifact for artifact in item["sprint_artifacts"]}
        assert labels["design_html"]["exists"] is True
        assert labels["planning_html"]["exists"] is True
        assert labels["planning_html"]["view_url"].startswith("/file/view?path=")
        assert labels["prd_html"]["exists"] is True
        assert "design_html" in item["artifact_labels"]
        assert "planning_html" in item["artifact_labels"]
        assert "prd_html" in item["artifact_labels"]

    print("PASS status-server asset packages")


if __name__ == "__main__":
    main()
