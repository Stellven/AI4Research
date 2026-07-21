"""Execution metrics for DeepResearch final reports.

Provider token ledgers are not always available, especially for deterministic,
pane, or local-command runs.  When no real token ledger is present, the report
still records a deterministic estimate and labels it as estimated instead of
presenting it as provider-billed usage.
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any


TOKEN_KEYS = {
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "completion_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
}
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-_'][A-Za-z0-9]+)*|[\u4e00-\u9fff]")


def document_word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(math.ceil(len(text) / 4)))


def _walk_json(value: Any) -> dict[str, int]:
    totals: dict[str, int] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            key_norm = str(key)
            if key_norm in TOKEN_KEYS and isinstance(item, (int, float)) and item >= 0:
                totals[key_norm] = totals.get(key_norm, 0) + int(item)
            nested = _walk_json(item)
            for nested_key, nested_value in nested.items():
                totals[nested_key] = totals.get(nested_key, 0) + nested_value
    elif isinstance(value, list):
        for item in value:
            nested = _walk_json(item)
            for nested_key, nested_value in nested.items():
                totals[nested_key] = totals.get(nested_key, 0) + nested_value
    return totals


def extract_token_usage(value: Any) -> dict[str, int]:
    """Extract provider token fields from a nested JSON-like payload."""
    return _walk_json(value)


def extract_text_from_model_payload(value: Any) -> str:
    """Best-effort extraction for model CLI JSON outputs."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("result", "completion", "content", "text", "output"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
        content = value.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "\n".join(parts)
    return ""


def parse_model_cli_output(stdout: str, stderr: str = "") -> tuple[str, dict[str, int], list[dict[str, Any]]]:
    """Parse text/json/stream-json model CLI output into text plus token usage."""
    text = (stdout or "").strip()
    usage: dict[str, int] = {}
    payloads: list[dict[str, Any]] = []
    raw = "\n".join(part for part in (stdout, stderr) if part)

    def merge(row: dict[str, int]) -> None:
        for key, value in row.items():
            usage[key] = usage.get(key, 0) + value

    try:
        value = json.loads(stdout)
        if isinstance(value, dict):
            payloads.append(value)
            merge(_walk_json(value))
            extracted = extract_text_from_model_payload(value)
            if extracted:
                text = extracted.strip()
            return text, usage, payloads
    except json.JSONDecodeError:
        pass

    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
            merge(_walk_json(value))
            extracted = extract_text_from_model_payload(value)
            if extracted:
                text = extracted.strip()
    return text, usage, payloads


def build_model_usage_event(
    *,
    backend: str,
    model: str = "",
    prompt: str = "",
    output: str = "",
    usage: dict[str, int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    real_usage = {key: int(value) for key, value in (usage or {}).items() if key in TOKEN_KEYS and int(value or 0) >= 0}
    if real_usage:
        input_tokens = int(real_usage.get("input_tokens") or real_usage.get("prompt_tokens") or 0)
        output_tokens = int(real_usage.get("output_tokens") or real_usage.get("completion_tokens") or 0)
        total_tokens = int(real_usage.get("total_tokens") or sum(real_usage.values()))
        event: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "backend": backend,
            "model": model,
            "token_usage_source": "provider_usage_ledger",
            "token_usage_is_estimated": False,
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            **real_usage,
        }
    else:
        event = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "backend": backend,
            "model": model,
            "token_usage_source": "estimated_from_model_io",
            "token_usage_is_estimated": True,
            "estimated_total_tokens": estimate_tokens(prompt) + estimate_tokens(output),
            "estimated_input_tokens": estimate_tokens(prompt),
            "estimated_output_tokens": estimate_tokens(output),
        }
    if metadata:
        event["metadata"] = metadata
    return event


def append_model_usage_event(path: str | Path, event: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _read_usage_json(path: Path) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict) and value.get("token_usage_is_estimated") is True:
                    continue
                rows.append(_walk_json(value))
            except json.JSONDecodeError:
                continue
    else:
        try:
            value = json.loads(text)
            if isinstance(value, dict) and value.get("token_usage_is_estimated") is True:
                return rows
            rows.append(_walk_json(value))
        except json.JSONDecodeError:
            return rows
    return [row for row in rows if any(row.values())]


def _discover_token_usage(root: Path | None) -> tuple[dict[str, int], list[str]]:
    totals: dict[str, int] = {}
    files: list[str] = []
    if not root or not root.exists():
        return totals, files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "execution_metrics" in path.name:
            continue
        name = path.name.lower()
        if "usage" not in name and "token" not in name and "backend" not in name:
            continue
        if path.suffix not in {".json", ".jsonl"}:
            continue
        for row in _read_usage_json(path):
            if row:
                files.append(str(path))
            for key, value in row.items():
                totals[key] = totals.get(key, 0) + value
    return totals, sorted(set(files))


def _usage_ledger_metadata(root: Path | None) -> tuple[str, int]:
    if not root or not root.exists():
        return "", 0
    candidates = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".json", ".jsonl"}
        and ("usage" in path.name.lower() or "token" in path.name.lower())
        and "execution_metrics" not in path.name
    )
    ledger_path = ""
    ledger_lines = 0
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.strip():
            continue
        if not ledger_path or path.name == "model_usage.jsonl":
            ledger_path = str(path)
        if path.suffix == ".jsonl":
            ledger_lines += sum(1 for line in text.splitlines() if line.strip())
        else:
            ledger_lines += 1
    return ledger_path, ledger_lines


def _estimate_input_tokens(root: Path | None) -> int:
    if not root or not root.exists():
        return 0
    total = 0
    candidates = list(root.glob("**/prompt_packets/*.json")) + list(root.glob("**/prompt_packets/*.md"))
    candidates.extend(root.glob("chief_editor/prompts/*.md"))
    candidates.extend(root.glob("*.jsonl"))
    for path in candidates:
        try:
            total += estimate_tokens(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return total


def build_execution_metrics(final_text: str, output_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(output_dir).expanduser() if output_dir else None
    provider_usage, usage_files = _discover_token_usage(root)
    ledger_path, ledger_lines = _usage_ledger_metadata(root)
    output_tokens = estimate_tokens(final_text)
    if provider_usage:
        total_tokens = int(provider_usage.get("total_tokens") or 0)
        if not total_tokens:
            total_tokens = sum(
                int(provider_usage.get(key) or 0)
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            )
        input_tokens = int(provider_usage.get("input_tokens") or provider_usage.get("prompt_tokens") or 0)
        output_tokens = int(provider_usage.get("output_tokens") or provider_usage.get("completion_tokens") or output_tokens)
        source = "provider_usage_ledger"
        estimated = False
    else:
        input_tokens = _estimate_input_tokens(root)
        total_tokens = input_tokens + output_tokens
        source = "estimated_from_report_artifacts"
        estimated = True
    fallback_reason = None if not estimated else "no_provider_usage"
    return {
        "sprint_id": root.name if root else "",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "document_word_count": document_word_count(final_text),
        "document_char_count": len(final_text),
        "total_token_consumption": int(total_tokens),
        "total_tokens": int(total_tokens),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "token_usage_source": source,
        "token_usage_is_estimated": estimated,
        "usage_source": source,
        "estimated": estimated,
        "fallback_reason": fallback_reason,
        "token_usage_files": usage_files,
        "ledger_path": ledger_path,
        "ledger_lines": int(ledger_lines),
    }


def render_execution_metrics_section(metrics: dict[str, Any]) -> str:
    estimate_note = "yes" if metrics.get("token_usage_is_estimated") else "no"
    return "\n".join([
        "## Execution Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Document word count | {int(metrics.get('document_word_count') or 0)} |",
        f"| Document character count | {int(metrics.get('document_char_count') or 0)} |",
        f"| Total token consumption | {int(metrics.get('total_token_consumption') or 0)} |",
        f"| Input tokens | {int(metrics.get('input_tokens') or 0)} |",
        f"| Output tokens | {int(metrics.get('output_tokens') or 0)} |",
        "",
        "---",
        f"Document word count: {int(metrics.get('document_word_count') or 0)}",
        f"Total token consumption: {int(metrics.get('total_token_consumption') or 0)}",
        f"Token usage source: {metrics.get('token_usage_source') or 'N/A'}",
        f"Token usage estimated: {estimate_note}",
        "---",
    ]).strip() + "\n"


def append_execution_metrics_section(markdown: str, output_dir: str | Path | None = None) -> tuple[str, dict[str, Any]]:
    base = (markdown or "").rstrip()
    first = build_execution_metrics(base + "\n", output_dir)
    candidate = base + "\n\n" + render_execution_metrics_section(first)
    final = build_execution_metrics(candidate, output_dir)
    text = base + "\n\n" + render_execution_metrics_section(final)
    return text.rstrip() + "\n", final


def write_execution_metrics(path: str | Path, metrics: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
