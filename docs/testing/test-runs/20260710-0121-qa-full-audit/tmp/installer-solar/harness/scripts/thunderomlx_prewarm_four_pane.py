#!/usr/bin/env python3
"""Prewarm ThunderOMLX cache with active four-pane system prompts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SESSION = "solar-harness-lab:0"
ENDPOINT = "http://127.0.0.1:8002/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"
REPORT_DIR = Path.home() / ".solar" / "harness" / "monitor-reports"
OMLX_SETTINGS = Path.home() / ".omlx" / "settings.json"


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)


def list_panes() -> list[dict]:
    out = run([
        "tmux",
        "list-panes",
        "-t",
        SESSION,
        "-F",
        "#{pane_index}\t#{pane_id}\t#{pane_pid}\t#{pane_title}",
    ])
    panes = []
    for line in out.splitlines():
        idx, pane_id, pane_pid, title = line.split("\t", 3)
        panes.append({
            "pane_index": int(idx),
            "pane_id": pane_id,
            "pane_pid": int(pane_pid),
            "title": title,
        })
    return panes


def child_claude_pid(parent_pid: int) -> int | None:
    out = run(["ps", "-A", "-o", "pid=", "-o", "ppid=", "-o", "comm="])
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[1] == str(parent_pid) and parts[2].endswith("/claude"):
            return int(parts[0])
    return None


def command_for_pid(pid: int) -> str:
    return run(["ps", "-ww", "-p", str(pid), "-o", "command="])


def env_for_pid(pid: int) -> str:
    return run(["ps", "eww", "-p", str(pid)])


def extract_append_prompt(command: str) -> str:
    marker = "--append-system-prompt"
    if marker not in command:
        return ""
    prompt = command.split(marker, 1)[1].strip()
    prompt = prompt.replace("\\012", "\n")
    prompt = prompt.replace("\\011", "\t")
    return prompt.strip()


def extract_token(env_text: str) -> str:
    key = "ANTHROPIC_AUTH_TOKEN="
    if key not in env_text:
        return ""
    tail = env_text.split(key, 1)[1]
    return tail.split(None, 1)[0].strip()


def settings_api_key() -> str:
    try:
        data = json.loads(OMLX_SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return ""
    key = data.get("auth", {}).get("api_key")
    return key if isinstance(key, str) and key else ""


def is_thunderomlx_env(env_text: str) -> bool:
    return (
        "ANTHROPIC_BASE_URL=http://127.0.0.1:8002" in env_text
        or "ANTHROPIC_BASE_URL=http://localhost:8002" in env_text
    )


def post_completion(token: str, prompt: str, pane_index: int, round_name: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"预热{round_name}: pane {pane_index}. 请只回复 OK。",
            },
        ],
        "max_tokens": 16,
        "temperature": 0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        status = exc.code
    elapsed = time.perf_counter() - start
    parsed = json.loads(body)
    if status != 200 or not parsed.get("choices"):
        return {
            "http_status": status,
            "elapsed_seconds": round(elapsed, 3),
            "error": parsed.get("detail") or parsed.get("error") or "missing choices",
            "bad_chars": False,
        }
    choice = (parsed.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = parsed.get("usage") or {}
    content = message.get("content")
    return {
        "http_status": status,
        "elapsed_seconds": round(elapsed, 3),
        "finish_reason": choice.get("finish_reason"),
        "content_preview": (content or "")[:80],
        "bad_chars": any(ch in (content or "") for ch in ["�", "\x00"]),
        "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "cached_tokens": usage.get("cached_tokens"),
        "prompt_eval_duration": usage.get("prompt_eval_duration"),
        "total_time": usage.get("total_time"),
    }


def main() -> int:
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    panes = list_panes()
    fallback_token = ""
    thunderomlx_token = ""
    rows = []

    for pane in panes:
        child_pid = child_claude_pid(pane["pane_pid"])
        prompt = ""
        if child_pid is not None:
            command = command_for_pid(child_pid)
            prompt = extract_append_prompt(command)
            env_text = env_for_pid(child_pid)
            child_token = extract_token(env_text)
            if child_token and not fallback_token:
                fallback_token = child_token
            if child_token and is_thunderomlx_env(env_text):
                thunderomlx_token = child_token
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] if prompt else ""
        rows.append({
            **pane,
            "child_pid": child_pid,
            "prompt_hash": prompt_hash,
            "prompt_chars": len(prompt),
            "prompt": prompt,
        })

    token = thunderomlx_token or settings_api_key() or fallback_token
    if not token:
        raise SystemExit("missing ANTHROPIC_AUTH_TOKEN from pane process environment")

    for row in rows:
        prompt = row.pop("prompt", "")
        if not prompt:
            row["status"] = "warn"
            row["error"] = "missing append system prompt"
            continue
        row["status"] = "ok"
        row["warm"] = post_completion(token, prompt, row["pane_index"], "写入")
        row["verify"] = post_completion(token, prompt, row["pane_index"], "验证")
        if row["warm"].get("http_status") != 200 or row["verify"].get("http_status") != 200:
            row["status"] = "error"

    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "session": SESSION,
        "endpoint": ENDPOINT,
        "model": MODEL,
        "note": "Model name is intentionally lowercase to verify case-insensitive resolution.",
        "panes": rows,
    }

    json_path = REPORT_DIR / f"thunderomlx-four-pane-prewarm-{started}.json"
    md_path = REPORT_DIR / f"thunderomlx-four-pane-prewarm-{started}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    lines = [
        "# ThunderOMLX four-pane system prompt prewarm",
        "",
        f"- endpoint: `{ENDPOINT}`",
        f"- model: `{MODEL}`",
        "- safety: partial block / full skip / approximate skip not changed",
        "",
        "| pane | status | prompt_chars | prompt_hash | warm_s | verify_s | cached_tokens | bad_chars |",
        "|---:|---|---:|---|---:|---:|---:|---|",
    ]
    for row in rows:
        warm = row.get("warm") or {}
        verify = row.get("verify") or {}
        lines.append(
            "| {pane} | {status} | {chars} | `{hash}` | {warm_s} | {verify_s} | {cached} | {bad} |".format(
                pane=row["pane_index"],
                status=row.get("status", "N/A"),
                chars=row.get("prompt_chars", 0),
                hash=row.get("prompt_hash") or "N/A",
                warm_s=warm.get("elapsed_seconds", "N/A"),
                verify_s=verify.get("elapsed_seconds", "N/A"),
                cached=verify.get("cached_tokens", "N/A"),
                bad=verify.get("bad_chars", "N/A"),
            )
        )
    md_path.write_text("\n".join(lines) + "\n")

    print(json.dumps({
        "status": "ok",
        "json_report": str(json_path),
        "md_report": str(md_path),
        "panes": [
            {
                "pane": r["pane_index"],
                "status": r.get("status"),
                "prompt_chars": r.get("prompt_chars"),
                "prompt_hash": r.get("prompt_hash"),
                "warm_s": (r.get("warm") or {}).get("elapsed_seconds"),
                "verify_s": (r.get("verify") or {}).get("elapsed_seconds"),
                "cached_tokens": (r.get("verify") or {}).get("cached_tokens"),
                "bad_chars": (r.get("verify") or {}).get("bad_chars"),
            }
            for r in rows
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
