#!/usr/bin/env python3
"""Regression test for knowledge subscription management."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_subscriptions_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["solar_status_server_subscriptions_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory(prefix="solar-subscriptions-test-") as td:
        base = Path(td)
        harness = base / "harness"
        knowledge = base / "Knowledge"
        youtube_cfg = harness / "config" / "youtube-influence-digest.yaml"
        github_cfg = harness / "config" / "github-trends.yaml"
        accounts = harness / "ai-influence-digest" / "references" / "accounts_extended.txt"
        write(youtube_cfg, "version: 1\nchannels: []\n")
        write(github_cfg, "version: 1\ntracked_topics: []\ntracked_repos: []\noutput:\n  database: " + str(harness / "state" / "github.sqlite") + "\n")
        write(accounts, "tier\tcategory\thandle\tdisplay_name\tnotes\tenabled\trotation_group\n")

        mod.HARNESS_DIR = harness
        mod.KNOWLEDGE_DIR = knowledge
        mod.YOUTUBE_DIGEST_CONFIG = youtube_cfg
        mod.GITHUB_TRENDS_CONFIG = github_cfg
        mod.AI_INFLUENCE_ACCOUNTS = accounts

        assert mod._knowledge_subscriptions_payload()["youtube"]["count"] == 0
        assert mod._append_youtube_subscription({"url": "@SiliconValley101", "name": "硅谷101"})["status"] == "added"
        assert mod._append_social_subscription({"handle": "karpathy", "tier": 1, "category": "core_leader"})["status"] == "added"
        assert mod._append_github_topic({"name": "agent-runtime", "category": "agent", "query": "agent OR mcp"})["status"] == "added"
        assert mod._append_github_repo({"repo": "ggerganov/llama.cpp"})["status"] == "added"
        payload = mod._knowledge_subscriptions_payload()
        assert payload["youtube"]["count"] == 1
        assert payload["social"]["count"] == 1
        assert payload["github"]["topic_count"] == 1
        assert payload["github"]["tracked_repos"] == ["ggerganov/llama.cpp"]
        html = mod._knowledge_subscriptions_html()
        assert "知识订阅中心" in html
        assert "GitHub 分类趋势" in html

    print("PASS status-server knowledge subscriptions")


if __name__ == "__main__":
    main()
