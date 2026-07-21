from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from urllib.request import Request

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research import cli as research_cli


ARXIV_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <title>Agentic Runtime Architectures</title>
    <summary>We study durable execution for agent runtimes.</summary>
    <link href="http://arxiv.org/abs/2501.00001v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2501.00001v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"organic":[{"title":"Durable Agent Runtime","link":"https://example.com/runtime","snippet":"Agent runtime source."}]}'


def test_legacy_http_search_is_disabled():
    hits, errors = research_cli.http_web_search("agentic runtime", 3)

    assert hits == []
    assert errors
    assert "legacy http search disabled" in errors[0]


def test_arxiv_search_parses_official_atom_api(monkeypatch):
    monkeypatch.setattr(research_cli, "http_get_text", lambda *args, **kwargs: ARXIV_SAMPLE)

    hits, errors = research_cli.arxiv_search("agentic runtime", 3)

    assert errors == []
    assert hits[0]["connector"] == "arxiv"
    assert hits[0]["title"] == "Agentic Runtime Architectures"
    assert hits[0]["url"].startswith("http://arxiv.org/abs/")


def test_serper_search_posts_json_api(monkeypatch, tmp_path):
    captured = {}

    def fake_urlopen(req, timeout):
        assert isinstance(req, Request)
        captured["url"] = req.full_url
        captured["api_key"] = req.headers.get("X-api-key") or req.headers.get("X-API-KEY")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setenv("SERPER_USAGE_PATH", str(tmp_path / "serper_usage.jsonl"))
    monkeypatch.setattr(research_cli.urllib.request, "urlopen", fake_urlopen)

    hits, errors = research_cli.serper_search("agentic runtime", 2)

    assert errors == []
    assert captured["url"] == "https://google.serper.dev/search"
    assert captured["api_key"] == "test-key"
    assert hits[0]["connector"] == "serper"
    assert hits[0]["url"] == "https://example.com/runtime"


def test_serper_search_requires_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    hits, errors = research_cli.serper_search("agentic runtime", 2)

    assert hits == []
    assert "serper missing SERPER_API_KEY" in errors[0]


def test_serper_usage_meter_records_request(monkeypatch, tmp_path):
    usage_path = tmp_path / "serper_usage.jsonl"
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setenv("SERPER_USAGE_PATH", str(usage_path))
    monkeypatch.setenv("SERPER_MONTHLY_LIMIT", "3")
    monkeypatch.delenv("SERPER_SHARED_USAGE_SSH", raising=False)
    monkeypatch.delenv("SERPER_SHARED_USAGE_PATH", raising=False)
    monkeypatch.setattr(research_cli.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    hits, errors = research_cli.serper_search("agentic runtime", 2)
    payload = research_cli.serper_usage_snapshot()

    assert errors == []
    assert hits
    assert payload["used"] == 1
    assert payload["limit"] == 3
    assert payload["remaining"] == 2
    assert usage_path.exists()


def test_serper_usage_meter_blocks_over_limit(monkeypatch, tmp_path):
    usage_path = tmp_path / "serper_usage.jsonl"
    month = research_cli._current_usage_month()
    usage_path.write_text('{"month":"%s","requests":1}\n' % month, encoding="utf-8")
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setenv("SERPER_USAGE_PATH", str(usage_path))
    monkeypatch.setenv("SERPER_MONTHLY_LIMIT", "1")

    hits, errors = research_cli.serper_search("agentic runtime", 2)

    assert hits == []
    assert "serper quota exhausted" in errors[0]


def test_serper_usage_snapshot_combines_shared_ledger(monkeypatch, tmp_path):
    usage_path = tmp_path / "serper_usage.jsonl"
    month = research_cli._current_usage_month()
    usage_path.write_text('{"month":"%s","requests":2}\n' % month, encoding="utf-8")
    monkeypatch.setenv("SERPER_USAGE_PATH", str(usage_path))
    monkeypatch.setenv("SERPER_SHARED_USAGE_SSH", "mini")
    monkeypatch.setenv("SERPER_SHARED_USAGE_PATH", "/remote/serper_usage.jsonl")
    monkeypatch.setenv("SERPER_MONTHLY_LIMIT", "10")
    monkeypatch.setattr(research_cli, "_read_serper_remote_usage_lines", lambda: (['{"month":"%s","requests":3}' % month], ""))

    payload = research_cli.serper_usage_snapshot()

    assert payload["local_used"] == 2
    assert payload["shared_used"] == 3
    assert payload["used"] == 5
    assert payload["remaining"] == 5


def test_serper_usage_snapshot_dedupes_shared_copy(monkeypatch, tmp_path):
    usage_path = tmp_path / "serper_usage.jsonl"
    month = research_cli._current_usage_month()
    line = '{"event_id":"same-event","month":"%s","requests":1}' % month
    usage_path.write_text(line + "\n", encoding="utf-8")
    monkeypatch.setenv("SERPER_USAGE_PATH", str(usage_path))
    monkeypatch.setenv("SERPER_SHARED_USAGE_SSH", "mini")
    monkeypatch.setenv("SERPER_SHARED_USAGE_PATH", "/remote/serper_usage.jsonl")
    monkeypatch.setattr(research_cli, "_read_serper_remote_usage_lines", lambda: ([line], ""))

    payload = research_cli.serper_usage_snapshot()

    assert payload["local_used"] == 1
    assert payload["shared_used"] == 1
    assert payload["used"] == 1


def test_serper_usage_meter_writes_shared_ledger(monkeypatch, tmp_path):
    remote_lines = []
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setenv("SERPER_USAGE_PATH", str(tmp_path / "serper_usage.jsonl"))
    monkeypatch.setenv("SERPER_SHARED_USAGE_SSH", "mini")
    monkeypatch.setenv("SERPER_SHARED_USAGE_PATH", "/remote/serper_usage.jsonl")
    monkeypatch.setattr(research_cli.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(research_cli, "_read_serper_remote_usage_lines", lambda: ([], ""))
    monkeypatch.setattr(research_cli, "_append_serper_remote_usage_event", lambda line: remote_lines.append(line) or "")

    hits, errors = research_cli.serper_search("agentic runtime", 2)

    assert errors == []
    assert hits
    assert len(remote_lines) == 1
    assert '"event_id":' in remote_lines[0]
    assert '"requests": 1' in remote_lines[0]


def test_serper_shared_usage_read_failure_does_not_block_local_snapshot(monkeypatch, tmp_path):
    usage_path = tmp_path / "serper_usage.jsonl"
    month = research_cli._current_usage_month()
    usage_path.write_text('{"month":"%s","requests":2}\n' % month, encoding="utf-8")
    monkeypatch.setenv("SERPER_USAGE_PATH", str(usage_path))
    monkeypatch.setenv("SERPER_SHARED_USAGE_SSH", "mini")
    monkeypatch.setenv("SERPER_SHARED_USAGE_PATH", "/remote/serper_usage.jsonl")
    monkeypatch.setattr(research_cli, "_read_serper_remote_usage_lines", lambda: ([], "shared_usage_read_failed:test"))

    payload = research_cli.serper_usage_snapshot()

    assert payload["used"] == 2
    assert payload["sync_errors"] == ["shared_usage_read_failed:test"]


def test_google_cse_element_requires_search_engine_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_ENGINE_ID", raising=False)

    hits, errors = research_cli.google_cse_element_search("agentic runtime", 2)

    assert hits == []
    assert "google-cse-element missing" in errors[0]


def test_google_cse_oauth_requires_client_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_CSE_ID", "cx-test")
    monkeypatch.setenv("GOOGLE_CSE_CLIENT_SECRET", str(tmp_path / "missing-client-secret.json"))

    hits, errors = research_cli.google_cse_oauth_search("agentic runtime", 2)

    assert hits == []
    assert "google-cse-oauth missing client secret" in errors[0]


def test_auto_search_never_uses_jina_or_duck(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_ENGINE_ID", raising=False)
    monkeypatch.setattr(research_cli, "google_cse_oauth_search", lambda *args, **kwargs: ([], ["oauth unavailable"]))
    monkeypatch.setattr(research_cli, "google_cse_element_search", lambda *args, **kwargs: ([], ["element unavailable"]))
    monkeypatch.setattr(research_cli, "arxiv_search", lambda *args, **kwargs: ([{"title": "Paper", "url": "https://arxiv.org/abs/1", "connector": "arxiv", "rank": 1}], []))

    hits, errors = research_cli.web_search("agentic runtime", 2, provider="auto")

    assert hits[0]["connector"] == "arxiv"
    assert not any("jina" in error.lower() or "duck" in error.lower() for error in errors)


def test_auto_search_uses_cse_element_after_json_failure(monkeypatch):
    monkeypatch.setattr(research_cli, "serper_search", lambda *args, **kwargs: ([], ["serper unavailable"]))
    monkeypatch.setattr(research_cli, "google_cse_search", lambda *args, **kwargs: ([], ["json forbidden"]))
    monkeypatch.setattr(research_cli, "google_cse_oauth_search", lambda *args, **kwargs: ([], ["oauth unavailable"]))
    monkeypatch.setattr(research_cli, "google_cse_element_search", lambda *args, **kwargs: ([{"title": "Doc", "url": "https://example.com", "connector": "google-cse-element", "rank": 1}], []))

    hits, errors = research_cli.web_search("agentic runtime", 2, provider="auto")

    assert hits[0]["connector"] == "google-cse-element"
    assert "json forbidden" in errors


def test_auto_search_uses_cse_oauth_after_json_failure(monkeypatch):
    monkeypatch.setattr(research_cli, "serper_search", lambda *args, **kwargs: ([], ["serper unavailable"]))
    monkeypatch.setattr(research_cli, "google_cse_search", lambda *args, **kwargs: ([], ["json forbidden"]))
    monkeypatch.setattr(research_cli, "google_cse_oauth_search", lambda *args, **kwargs: ([{"title": "Doc", "url": "https://example.com", "connector": "google-cse-oauth", "rank": 1}], []))

    hits, errors = research_cli.web_search("agentic runtime", 2, provider="auto")

    assert hits[0]["connector"] == "google-cse-oauth"
    assert "json forbidden" in errors


def test_auto_search_prefers_serper(monkeypatch):
    monkeypatch.setattr(research_cli, "serper_search", lambda *args, **kwargs: ([{"title": "Doc", "url": "https://example.com", "connector": "serper", "rank": 1}], []))
    monkeypatch.setattr(research_cli, "google_cse_search", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("google should not run after serper hit")))

    hits, errors = research_cli.web_search("agentic runtime", 2, provider="auto")

    assert errors == []
    assert hits[0]["connector"] == "serper"


def test_deepresearch_doctor_reports_model_and_pending_google(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_ENGINE_ID", raising=False)
    monkeypatch.setattr(research_cli.shutil, "which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(
        research_cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="SOLAR_OK\n", stderr=""),
    )

    payload = research_cli.build_deepresearch_doctor(model="sonnet", live_search=False)

    assert payload["ok"] is True
    assert payload["status"] == "pending"
    assert payload["checks"]["chief_editor_model"]["status"] == "ok"
    assert payload["checks"]["serper"]["status"] == "pending"
    assert payload["checks"]["google_cse"]["status"] == "pending"


def test_deepresearch_doctor_does_not_block_on_optional_google_when_serper_works(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "google-key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "cx")
    monkeypatch.setattr(research_cli, "serper_search", lambda *args, **kwargs: ([{"title": "Doc", "url": "https://example.com", "connector": "serper", "rank": 1}], []))
    monkeypatch.setattr(research_cli, "google_cse_search", lambda *args, **kwargs: ([], ["json forbidden"]))
    monkeypatch.setattr(research_cli, "arxiv_search", lambda *args, **kwargs: ([{"title": "Paper", "url": "https://arxiv.org/abs/1", "connector": "arxiv", "rank": 1}], []))

    payload = research_cli.build_deepresearch_doctor(skip_model=True, live_search=True, require_serper=True)

    assert payload["ok"] is True
    assert payload["status"] == "warn"
    assert payload["checks"]["serper"]["status"] == "ok"
    assert payload["checks"]["google_cse"]["status"] == "warn"
    assert "google_cse" in payload["warnings"]
    assert "google_cse" not in payload["errors"]


def test_deepresearch_doctor_warns_when_fallback_model_selected(monkeypatch):
    monkeypatch.setattr(research_cli.shutil, "which", lambda name: "/usr/local/bin/claude")

    def fake_run(cmd, **kwargs):
        model = cmd[cmd.index("--model") + 1]
        if model == "opus":
            return SimpleNamespace(returncode=1, stdout="API Error 1210", stderr="")
        return SimpleNamespace(returncode=0, stdout="SOLAR_OK\n", stderr="")

    monkeypatch.setattr(research_cli.subprocess, "run", fake_run)

    payload = research_cli.build_deepresearch_doctor(model="opus", model_candidates="sonnet")

    assert payload["ok"] is True
    assert payload["status"] == "warn"
    assert payload["checks"]["chief_editor_model"]["selected_model"] == "sonnet"
    assert "chief_editor_model" in payload["warnings"]


def test_deepresearch_doctor_can_require_google(monkeypatch):
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_ENGINE_ID", raising=False)

    payload = research_cli.build_deepresearch_doctor(skip_model=True, require_google=True)

    assert payload["ok"] is False
    assert payload["status"] == "error"
    assert "google_cse" in payload["errors"]


def test_deepresearch_doctor_arxiv_live_failure_is_warn_by_default(monkeypatch):
    monkeypatch.setattr(research_cli, "arxiv_search", lambda *args, **kwargs: ([], ["arxiv: HTTP Error 429"]))
    monkeypatch.setattr(research_cli, "_doctor_check_google_cse", lambda *args, **kwargs: {"status": "ok", "ok": True})

    payload = research_cli.build_deepresearch_doctor(skip_model=True, live_search=True)

    assert payload["ok"] is True
    assert payload["status"] in {"warn", "pending"}
    assert payload["checks"]["arxiv"]["status"] == "warn"
    assert "arxiv" in payload["warnings"]


def test_deepresearch_doctor_can_require_arxiv(monkeypatch):
    monkeypatch.setattr(research_cli, "arxiv_search", lambda *args, **kwargs: ([], ["arxiv: HTTP Error 429"]))
    monkeypatch.setattr(research_cli, "_doctor_check_google_cse", lambda *args, **kwargs: {"status": "ok", "ok": True})

    payload = research_cli.build_deepresearch_doctor(skip_model=True, live_search=True, require_arxiv=True)

    assert payload["ok"] is False
    assert payload["checks"]["arxiv"]["status"] == "error"
    assert "arxiv" in payload["errors"]
