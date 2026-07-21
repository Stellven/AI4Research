#!/usr/bin/env python3
"""JSON-first ThunderOMLX extraction contract for Solar Knowledge."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import knowledge_extracted_renderer as renderer
import knowledge_ingest_registry as registry


PROMPT_VERSION = "knowledge-extract-v2"
SCHEMA_VERSION = "extracted-json-v2"
DEFAULT_ENDPOINT = os.environ.get("THUNDEROMLX_BASE_URL", "http://127.0.0.1:8002")
DEFAULT_PROXY_MODEL = os.environ.get("THUNDEROMLX_KNOWLEDGE_MODEL", "Qwen3.6-35b-a3b")
DEFAULT_LOCAL_MODEL = os.environ.get("THUNDEROMLX_LOCAL_MODEL", "ThunderOMLX backend")
DEFAULT_SETTINGS = Path(os.environ.get("THUNDEROMLX_SETTINGS", str(Path.home() / ".omlx" / "settings.json"))).expanduser()
DEFAULT_THUNDEROMLX_PAUSE_FILE = Path.home() / ".omlx" / "run" / "maintenance.json"


def thunderomlx_pause_state(args: argparse.Namespace) -> dict[str, Any] | None:
    path = Path(getattr(args, "pause_file", "") or DEFAULT_THUNDEROMLX_PAUSE_FILE).expanduser()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"enabled": True, "mode": "ingest_pause", "reason": f"unreadable pause file: {exc}", "path": str(path)}
    if not isinstance(data, dict) or not data.get("enabled", True):
        return None
    mode = str(data.get("mode") or "ingest_pause")
    if mode not in {"ingest_pause", "all"}:
        return None
    until = data.get("until")
    if until:
        try:
            if float(until) <= time.time():
                return None
        except (TypeError, ValueError):
            pass
    data["path"] = str(path)
    return data


def default_api_key() -> str:
    env_key = os.environ.get("THUNDEROMLX_AUTH_TOKEN")
    if env_key:
        return env_key
    try:
        data = json.loads(DEFAULT_SETTINGS.read_text(encoding="utf-8"))
        key = data.get("auth", {}).get("api_key")
        if isinstance(key, str) and key:
            return key
    except Exception:
        pass
    return "local-thunderomlx"


def load_sidecar(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_output_path(sidecar: dict[str, Any], output_dir: Path) -> Path:
    doc_id = str(sidecar["doc_id"]).replace(":", "_").replace("/", "_")
    return output_dir / f"{doc_id}.extracted.candidate.json"


def markdown_output_path(candidate_path: Path) -> Path:
    return candidate_path.with_suffix("").with_suffix(".md")


def _allowed_spans(sidecar: dict[str, Any]) -> list[str]:
    return [span["span_id"] for span in sidecar.get("spans") or []]


def build_mock_candidate(sidecar: dict[str, Any], *, args: argparse.Namespace) -> dict[str, Any]:
    spans = sidecar.get("spans") or [{"span_id": "S001", "text": ""}]
    first = spans[0]
    first_text = re.sub(r"\s+", " ", first.get("text", "")).strip()
    summary = first_text[:180] or "N/A"
    doc_type = args.doc_type or "unknown"
    return {
        "doc_id": sidecar["doc_id"],
        "source_path": sidecar["source_path"],
        "source_sha256": sidecar["source_sha256"],
        "source_kind": sidecar.get("source_kind", "unknown"),
        "doc_type": doc_type,
        "profile": args.profile,
        "proxy_model": args.proxy_model,
        "local_model": args.local_model,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "summary": {"claim": summary, "evidence": [first["span_id"]]},
        "core_facts": [{"claim": summary, "evidence": [first["span_id"]], "confidence": "medium"}],
        "functional_modules": [
            {
                "name": doc_type,
                "role": "Extracted semantic unit for retrieval routing.",
                "inputs": ["source markdown spans"],
                "outputs": ["extracted markdown"],
                "dependencies": ["ThunderOMLX", "QMD"],
                "evidence": [first["span_id"]],
            }
        ],
        "commands_api_config": [],
        "architecture": [],
        "risks": [],
        "open_questions": [],
    }


def build_messages(sidecar: dict[str, Any], args: argparse.Namespace) -> list[dict[str, str]]:
    span_blocks = []
    for span in sidecar.get("spans") or []:
        span_blocks.append(
            {
                "span_id": span["span_id"],
                "heading_path": span.get("heading_path") or [],
                "start_line": span.get("start_line"),
                "end_line": span.get("end_line"),
                "text": span.get("text", ""),
            }
        )
    schema = {
        "doc_id": "string",
        "source_sha256": "string",
        "source_kind": "string",
        "doc_type": "string",
        "profile": "knowledge-extractor",
        "schema_version": SCHEMA_VERSION,
        "summary": {"claim": "string", "evidence": ["S001"]},
        "core_facts": [{"claim": "string", "evidence": ["S001"], "confidence": "high|medium|low"}],
        "functional_modules": [
            {
                "name": "string",
                "role": "string",
                "inputs": ["string"],
                "outputs": ["string"],
                "dependencies": ["string"],
                "evidence": ["S001"],
            }
        ],
        "commands_api_config": [{"kind": "cli|api|config|path", "name": "string", "value": "string", "purpose": "string", "evidence": ["S001"]}],
        "architecture": [{"component": "string", "description": "string", "evidence": ["S001"]}],
        "risks": [{"risk": "string", "impact": "string", "mitigation": "string", "evidence": ["S001"]}],
        "open_questions": [{"question": "string", "reason": "string", "evidence": ["S001"]}],
    }
    system = """你是 Solar Knowledge 的 ThunderOMLX JSON-first 语义抽取器。
只基于输入 spans 抽取，不补充外部事实。输出必须是严格 JSON 对象，不要 Markdown、不要代码围栏、不要解释。
所有 claim/fact/module/risk/command/architecture/open_question 必须引用给定 span_id。没有证据的内容只能放 open_questions。
"""
    user = json.dumps(
        {
            "doc_id": sidecar["doc_id"],
            "source_path": sidecar["source_path"],
            "source_sha256": sidecar["source_sha256"],
            "source_kind": sidecar.get("source_kind", "unknown"),
            "doc_type": args.doc_type or "unknown",
            "schema_version": SCHEMA_VERSION,
            "allowed_span_ids": _allowed_spans(sidecar),
            "output_schema": schema,
            "spans": span_blocks[: args.max_spans],
        },
        ensure_ascii=False,
        indent=2,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_json_text(text: str) -> str:
    text = re.sub(r"(?is)<think>.*?</think>\s*", "", text).strip()
    text = re.sub(r"(?is)^```(?:json)?\s*", "", text)
    text = re.sub(r"(?is)\s*```\s*$", "", text).strip()
    if "{" in text and "}" in text:
        return text[text.index("{") : text.rindex("}") + 1]
    return text


def _parse_model_response(response: dict[str, Any]) -> str:
    text_parts: list[str] = []
    if "choices" in response:
        for choice in response.get("choices") or []:
            msg = choice.get("message") or {}
            text_parts.append(str(msg.get("content") or ""))
    else:
        for item in response.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text") or ""))
            elif isinstance(item, dict) and "text" in item:
                text_parts.append(str(item.get("text") or ""))
    return "\n".join(text_parts)


def _post_json(url: str, payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", "x-api-key": args.api_key}
    if args.api_key:
        headers["authorization"] = f"Bearer {args.api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=args.timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _messages_payload(messages: list[dict[str, str]], args: argparse.Namespace) -> dict[str, Any]:
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    user_messages = [m for m in messages if m.get("role") != "system"]
    payload: dict[str, Any] = {"model": args.proxy_model, "max_tokens": args.max_tokens, "messages": user_messages}
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    return payload


def call_thunderomlx(messages: list[dict[str, str]], args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    pause = thunderomlx_pause_state(args)
    if pause:
        reason = pause.get("reason") or pause.get("path") or "maintenance pause active"
        raise RuntimeError(f"ThunderOMLX maintenance pause active: {reason}")
    started = time.monotonic()
    base = args.endpoint.rstrip("/")
    backend = "chat_completions"
    try:
        response = _post_json(
            base + "/v1/chat/completions",
            {"model": args.proxy_model, "max_tokens": args.max_tokens, "messages": messages},
            args,
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        backend = "messages"
        response = _post_json(base + "/v1/messages", _messages_payload(messages, args), args)
    latency_ms = int((time.monotonic() - started) * 1000)
    candidate = json.loads(_extract_json_text(_parse_model_response(response)))
    return candidate, {"latency_ms": latency_ms, "usage": response.get("usage") or {}, "backend": backend}


def enrich_candidate(candidate: dict[str, Any], sidecar: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    candidate.setdefault("doc_id", sidecar["doc_id"])
    candidate.setdefault("source_path", sidecar["source_path"])
    candidate.setdefault("source_sha256", sidecar["source_sha256"])
    candidate.setdefault("source_kind", sidecar.get("source_kind", "unknown"))
    candidate.setdefault("doc_type", args.doc_type or "unknown")
    candidate["profile"] = args.profile
    candidate["proxy_model"] = args.proxy_model
    candidate["local_model"] = args.local_model
    candidate["prompt_version"] = PROMPT_VERSION
    candidate["schema_version"] = SCHEMA_VERSION
    return candidate


def cmd_extract_sidecar(args: argparse.Namespace) -> int:
    if not args.mock:
        pause = thunderomlx_pause_state(args)
        if pause:
            print(json.dumps({
                "ok": True,
                "status": "paused",
                "reason": pause.get("reason") or pause.get("path") or "ThunderOMLX maintenance pause active",
                "mode": pause.get("mode", "ingest_pause"),
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    sidecar_path = Path(args.sidecar).expanduser()
    sidecar = load_sidecar(sidecar_path)
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = Path(args.output).expanduser() if args.output else candidate_output_path(sidecar, output_dir)
    report_path = candidate_path.with_suffix(".report.json")
    try:
        if args.mock:
            candidate = build_mock_candidate(sidecar, args=args)
            call_report = {"mode": "mock", "latency_ms": 0, "usage": {}}
        else:
            messages = build_messages(sidecar, args)
            candidate, call_report = call_thunderomlx(messages, args)
            candidate = enrich_candidate(candidate, sidecar, args)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        report = {
            "ok": False,
            "status": "extract_failed_auth_or_http",
            "http_status": exc.code,
            "error": body,
            "sidecar": str(sidecar_path),
            "endpoint": args.endpoint,
            "candidate": str(candidate_path),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    except Exception as exc:
        report = {
            "ok": False,
            "status": "extract_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "sidecar": str(sidecar_path),
            "endpoint": args.endpoint,
            "candidate": str(candidate_path),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_path = Path(args.markdown_output).expanduser() if args.markdown_output else markdown_output_path(candidate_path)
    md_path.write_text(renderer.render_extracted_markdown(candidate), encoding="utf-8")
    report = {"ok": True, "candidate": str(candidate_path), "markdown": str(md_path), "sidecar": str(sidecar_path), **call_report}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solar Knowledge JSON-first extractor")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--api-key", default=default_api_key())
    parser.add_argument("--proxy-model", default=DEFAULT_PROXY_MODEL)
    parser.add_argument("--local-model", default=DEFAULT_LOCAL_MODEL)
    parser.add_argument("--profile", default="knowledge-extractor")
    parser.add_argument("--max-tokens", type=int, default=2400)
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--max-spans", type=int, default=20)
    parser.add_argument("--pause-file", default=os.environ.get("THUNDEROMLX_MAINTENANCE_FILE", str(DEFAULT_THUNDEROMLX_PAUSE_FILE)))
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("extract-sidecar")
    one.add_argument("--sidecar", required=True)
    one.add_argument("--output-dir", default=str(Path.home() / "Knowledge" / "_extracted" / "thunderomlx" / DEFAULT_PROXY_MODEL))
    one.add_argument("--output")
    one.add_argument("--markdown-output")
    one.add_argument("--doc-type")
    one.add_argument("--mock", action="store_true")
    one.set_defaults(func=cmd_extract_sidecar)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
