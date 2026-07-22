from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
PYTHON = CHECKOUT / ".venv/bin/python"


def load_tool(name: str):
    path = CHECKOUT / "tools" / name
    spec = importlib.util.spec_from_file_location(f"qa_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(CHECKOUT / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def run_tool(name: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    safe_env = dict(os.environ)
    for key in list(safe_env):
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            safe_env.pop(key, None)
    safe_env.update(
        {
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )
    if env:
        safe_env.update(env)
    return subprocess.run(
        [str(PYTHON), str(CHECKOUT / "tools" / name), *args],
        cwd=CHECKOUT,
        env=safe_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )


@pytest.mark.parametrize(
    "command,args",
    [
        ("search", ["verified agents"]),
        ("references", ["ARXIV:2601.00001"]),
        ("citations", ["ARXIV:2601.00001"]),
    ],
)
def test_semantic_scholar_offline_contract_is_typed_and_non_fabricating(command: str, args: list[str]) -> None:
    proc = run_tool("fetch_s2.py", command, *args, "--no-network-fetch")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "autosci_fetch_s2_cli.v1"
    assert payload["command"] == command
    assert payload["status"] == "inconclusive"
    assert payload["ok"] is False
    assert payload["items"] == []
    assert payload["limitations"] and "disabled" in payload["limitations"][0].lower()


def test_semantic_scholar_fixture_response_is_normalized_with_provenance(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    tool = load_tool("fetch_s2.py")
    monkeypatch.setattr(
        tool.lit,
        "_s2_search",
        lambda query, limit: [
            {
                "paperId": "s2-1",
                "title": "Verified Research Agents",
                "abstract": "Fixture provider response.",
                "url": "https://example.invalid/paper",
            }
        ],
    )
    args = tool.build_parser().parse_args(["search", "verified agents", "--limit", "1"])
    assert args.func(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["title"] == "Verified Research Agents"
    assert "search_s2" in item["source_channels"]
    assert item["url"] == "https://example.invalid/paper"


def test_deepxiv_missing_config_and_offline_contracts_are_explicit() -> None:
    offline = run_tool("fetch_deepxiv.py", "search", "verified agents", "--no-network-fetch")
    assert offline.returncode == 0
    payload = json.loads(offline.stdout)
    assert payload["schema"] == "autosci_fetch_deepxiv_cli.v1"
    assert payload["status"] == "inconclusive"
    assert payload["items"] == []
    assert "disabled" in payload["limitations"][0].lower()

    missing = run_tool(
        "fetch_deepxiv.py",
        "search",
        "verified agents",
        env={"AUTOSCI_DISABLE_NETWORK_FETCH": "0", "DEEPXIV_API_URL": ""},
    )
    assert missing.returncode == 0
    payload = json.loads(missing.stdout)
    assert payload["status"] == "inconclusive"
    assert "DEEPXIV_API_URL" in payload["limitations"][0]


def test_deepxiv_normalizes_fixture_provider_items() -> None:
    tool = load_tool("fetch_deepxiv.py")
    item = tool.normalize_item(
        {
            "id": "dx-1",
            "title": "DeepXiv fixture",
            "summary": "Provider-backed summary",
            "url": "https://example.invalid/dx-1",
        }
    )
    assert item == {
        "candidate_id": "dx-1",
        "title": "DeepXiv fixture",
        "abstract": "Provider-backed summary",
        "url": "https://example.invalid/dx-1",
        "source_channels": ["deepxiv"],
        "source_ref": "https://example.invalid/dx-1",
        "fetch_status": "fetched",
    }
    with pytest.raises(RuntimeError, match="JSON list"):
        tool._payload_items({"data": {"not": "a list"}})


@pytest.mark.parametrize("command", ["summary", "sections", "section", "wikitext"])
def test_wikipedia_provider_failure_is_typed_json(command: str) -> None:
    args = ["--timeout", "0.05", command, "QA impossible page"]
    if command == "section":
        args.extend(["--index", "0"])
    proc = run_tool("fetch_wikipedia.py", *args)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "autosci_wikipedia_fetch.v1"
    assert payload["status"] == "fetch_failed"
    assert payload.get("error")


def test_wikipedia_fixture_summary_preserves_source_url_and_timestamp(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    tool = load_tool("fetch_wikipedia.py")
    monkeypatch.setattr(
        tool,
        "fetch_json",
        lambda url, timeout: (
            {
                "title": "Solar research",
                "extract": "A bounded fixture summary.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Solar_research"}},
            },
            200,
            "",
        ),
    )
    args = argparse.Namespace(title="Solar research", timeout=1)
    assert tool.cmd_summary(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["title"] == "Solar research"
    assert payload["source_url"] == "https://en.wikipedia.org/wiki/Solar_research"
    assert payload["summary"] == "A bounded fixture summary."
    assert payload.get("retrieved_at"), "completed provider evidence omits its retrieval timestamp"


def test_arxiv_fixture_parsing_deduplicates_and_preserves_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_tool("fetch_arxiv.py")
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "title": "  Verified\nAgents ",
        "summary": "Fixture abstract",
        "authors": [{"name": "A. Researcher"}],
        "link": "https://arxiv.org/abs/2601.00001v2",
        "published": now,
    }
    monkeypatch.setattr(tool.feedparser, "parse", lambda url: SimpleNamespace(bozo=False, entries=[entry]))
    papers = tool.fetch_recent(hours=24, categories=["cs.AI", "cs.LG"])
    assert len(papers) == 1
    assert papers[0]["arxiv_id"] == "2601.00001"
    assert papers[0]["title"] == "Verified Agents"
    assert papers[0]["authors"] == ["A. Researcher"]
    assert papers[0]["arxiv_url"].startswith("https://arxiv.org/")


def test_arxiv_provider_error_returns_empty_without_synthetic_papers(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    tool = load_tool("fetch_arxiv.py")
    monkeypatch.setattr(tool.feedparser, "parse", lambda url: (_ for _ in ()).throw(RuntimeError("offline")))
    assert tool.fetch_recent(categories=["cs.AI"]) == []
    assert "failed to fetch RSS" in capsys.readouterr().err


def test_rasterize_latex_rejects_missing_required_inputs_without_writes(tmp_path: Path) -> None:
    proc = run_tool("rasterize_latex.py", "--out-dir", str(tmp_path), "--out-name", "figure")
    assert proc.returncode != 0
    assert not list(tmp_path.iterdir())
    message = (proc.stdout + proc.stderr).lower()
    assert "snippet" in message or "required" in message
