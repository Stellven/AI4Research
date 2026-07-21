#!/usr/bin/env python3
"""Run heavyweight proof checks for Solar/Solar-Harness integrations.

Unlike the fast structural benchmarks, this script executes selected runtime
paths and saves raw command evidence so results can be audited.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
REPORTS = HARNESS / "reports"
SOLAR_BIN = HARNESS / "solar-harness.sh"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(
    name: str,
    cmd: list[str],
    evidence_dir: Path,
    *,
    timeout: int = 120,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        result = {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "duration_s": round(time.time() - started, 3),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": cmd,
            "cwd": str(cwd) if cwd else None,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "exit_code": 99,
            "duration_s": round(time.time() - started, 3),
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "cmd": cmd,
            "cwd": str(cwd) if cwd else None,
        }
    stem = safe_name(name)
    write_json(evidence_dir / "commands" / f"{stem}.json", {k: v for k, v in result.items() if k not in {"stdout", "stderr"}})
    write_text(evidence_dir / "commands" / f"{stem}.stdout.txt", result["stdout"][-60000:])
    write_text(evidence_dir / "commands" / f"{stem}.stderr.txt", result["stderr"][-60000:])
    return result


def extract_json_tail(stdout: str) -> dict[str, Any]:
    marker = "JSON_RESULT_START\n"
    if marker in stdout:
        candidate = stdout.split(marker, 1)[1].strip()
        return json.loads(candidate)
    idx = stdout.rfind("{")
    if idx >= 0:
        return json.loads(stdout[idx:])
    raise ValueError("no JSON object found in command stdout")


def scenario(name: str, ok: bool, evidence: dict[str, Any], notes: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "status": "ok" if ok else "error",
        "passed": bool(ok),
        "notes": notes,
        "evidence": evidence,
    }


def bench_mempalace_search(evidence_dir: Path) -> dict[str, Any]:
    script = evidence_dir / "runtime" / "mempalace_search_probe.py"
    write_text(
        script,
        textwrap.dedent(
            """\
            import json
            import sys
            import warnings
            from pathlib import Path

            warnings.filterwarnings("ignore")
            sys.path.insert(0, str(Path.home() / ".solar" / "mempalace"))

            from mempalace_mcp_server import mempalace_search, mempalace_stats

            payload = {
                "stats": mempalace_stats(),
                "search": mempalace_search("Solar Harness 知识库 记忆 系统", top_k=3),
            }
            print("JSON_RESULT_START")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            """
        ),
    )
    result = run_command(
        "mempalace_true_semantic_search",
        ["python3.11", str(script)],
        evidence_dir,
        timeout=180,
        cwd=HOME / ".solar" / "mempalace",
    )
    parsed: dict[str, Any] = {}
    ok = False
    reason = ""
    try:
        parsed = extract_json_tail(result["stdout"])
        stats = parsed.get("stats", {})
        search = parsed.get("search", {})
        ok = result["ok"] and int(stats.get("total_docs", 0)) >= 50 and int(search.get("count", 0)) > 0
        reason = f"total_docs={stats.get('total_docs')} hits={search.get('count')}"
    except Exception as exc:
        reason = f"parse_failed={exc}"
    write_json(evidence_dir / "runtime" / "mempalace_search.json", parsed or {"parse_error": reason})
    return scenario("MemPalace real semantic search", ok, {"command_ok": result["ok"], "reason": reason}, "Loads embedding model and queries the live Chroma collection.")


def bench_apple_notes_mock_ingest(evidence_dir: Path) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="solar-heavy-notes-"))
    harness = root / "harness"
    vault = root / "vault"
    mock = root / "mock-notes"
    (harness / "config").mkdir(parents=True, exist_ok=True)
    mock.mkdir(parents=True, exist_ok=True)
    write_json(
        harness / "config" / "apple-notes-ingest.json",
        {
            "notes_folder": "Solar Inbox",
            "tags": ["#solar"],
            "interval_seconds": 3600,
            "raw_dir": str(vault / "_raw" / "apple-notes"),
            "all_notes": True,
            "fetch_wechat": False,
        },
    )
    write_json(
        mock / "note-001.json",
        {
            "note_id": "mock-note-001",
            "title": "Solar Heavy Proof Apple Notes",
            "modified_at": "2026-05-09T00:00:00Z",
            "created_at": "2026-05-09T00:00:00Z",
            "source_url": "https://example.com/solar-heavy-proof",
            "body": "这是一个 Apple Notes / WeChat ingest 重型证明样本，要求进入 _raw 并生成 wiki ingest dispatch。",
            "source_app": "Apple Notes",
        },
    )
    env = os.environ.copy()
    env.update({"HARNESS_DIR": str(harness), "APPLE_NOTES_MOCK_DIR": str(mock)})
    result = run_command(
        "apple_notes_mock_to_wiki_dispatch",
        ["python3", str(HARNESS / "lib" / "apple_notes_ingest.py"), "scan", "--force-dispatch", "--json"],
        evidence_dir,
        timeout=60,
        env=env,
    )
    parsed: dict[str, Any] = {}
    ok = False
    reason = ""
    try:
        parsed = json.loads(result["stdout"])
        exported = [Path(p) for p in parsed.get("exported", [])]
        dispatches = [Path(p) for p in parsed.get("wiki_dispatches", [])]
        ok = result["ok"] and parsed.get("ok") is True and any(p.exists() for p in exported) and any(p.exists() for p in dispatches)
        reason = f"exported={len(exported)} wiki_dispatches={len(dispatches)}"
        if exported:
            shutil.copy2(exported[0], evidence_dir / "runtime" / "apple-notes-exported.md")
        if dispatches:
            shutil.copy2(dispatches[0], evidence_dir / "runtime" / "apple-notes-wiki-dispatch.md")
    except Exception as exc:
        reason = f"parse_failed={exc}"
    write_json(evidence_dir / "runtime" / "apple_notes_ingest.json", parsed or {"parse_error": reason})
    return scenario("Apple Notes mock source to wiki dispatch", ok, {"command_ok": result["ok"], "reason": reason}, "Uses isolated paths to avoid writing mock notes into the real vault.")


def bench_accepted_artifact_export(evidence_dir: Path) -> dict[str, Any]:
    sid = os.environ.get("SOLAR_HEAVY_ACCEPTED_SID", "sprint-20260508-accepted-artifact-knowledge")
    root = Path(tempfile.mkdtemp(prefix="solar-heavy-accepted-"))
    vault = root / "vault"
    result = run_command(
        "accepted_artifact_export_to_wiki_dispatch",
        [
            "python3",
            str(HARNESS / "lib" / "accepted-artifact-export.py"),
            "export",
            "--sid",
            sid,
            "--vault",
            str(vault),
            "--force",
            "--json",
        ],
        evidence_dir,
        timeout=60,
        cwd=HARNESS,
    )
    parsed: dict[str, Any] = {}
    ok = False
    reason = ""
    try:
        parsed = json.loads(result["stdout"])
        out = Path(parsed.get("output", ""))
        dispatch = Path(parsed.get("dispatch", ""))
        ok = result["ok"] and parsed.get("ok") is True and out.exists() and dispatch.exists()
        reason = f"sid={sid} bytes={parsed.get('bytes')} dispatch_exists={dispatch.exists()}"
        if out.exists():
            shutil.copy2(out, evidence_dir / "runtime" / "accepted-artifact.md")
        if dispatch.exists():
            shutil.copy2(dispatch, evidence_dir / "runtime" / "accepted-artifact-dispatch.md")
    except Exception as exc:
        reason = f"parse_failed={exc}"
    write_json(evidence_dir / "runtime" / "accepted_artifact_export.json", parsed or {"parse_error": reason})
    return scenario("Accepted sprint artifact to wiki dispatch", ok, {"command_ok": result["ok"], "reason": reason}, "Exports a real finalized sprint into an isolated vault and creates the ingest dispatch.")


def bench_browser_use_navigation(evidence_dir: Path) -> dict[str, Any]:
    browser_root = HOME / ".claude" / "mcp-servers" / "browser-use"
    browser_python = browser_root / ".venv" / "bin" / "python"
    script = evidence_dir / "runtime" / "browser_use_probe.py"
    write_text(
        script,
        textwrap.dedent(
            f"""\
            import asyncio
            import importlib.util
            import json
            import os
            import tempfile
            import threading
            from functools import partial
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
            from pathlib import Path

            root = Path(tempfile.mkdtemp(prefix="solar-browser-use-page-"))
            (root / "index.html").write_text(
                "<!doctype html><html><head><title>Solar Heavy Proof</title></head>"
                "<body><main><h1>Solar Browser Use Proof</h1>"
                "<p id='marker'>SOLAR_BROWSER_USE_HEAVY_PROOF_MARKER</p></main></body></html>",
                encoding="utf-8",
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            spec = importlib.util.spec_from_file_location("solar_browser_use_server", "{str(browser_root / "server.py")}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            async def main():
                url = f"http://127.0.0.1:{{port}}/index.html"
                try:
                    nav = await mod.browser_navigate(url)
                    text = nav[0].text if nav else ""
                    shot = await mod.browser_screenshot(url=url, save_path="{str(evidence_dir / "runtime" / "browser-use-screenshot.png")}")
                    await mod.browser_close()
                    return {{
                        "url": url,
                        "marker_found": "SOLAR_BROWSER_USE_HEAVY_PROOF_MARKER" in text,
                        "title_found": "Solar Heavy Proof" in text,
                        "navigate_preview": text[:1000],
                        "screenshot_result": shot[0].text[:200] if shot else "",
                    }}
                finally:
                    server.shutdown()

            print("JSON_RESULT_START")
            print(json.dumps(asyncio.run(main()), ensure_ascii=False, indent=2))
            """
        ),
    )
    result = run_command(
        "browser_use_real_navigation",
        [str(browser_python if browser_python.exists() else sys.executable), str(script)],
        evidence_dir,
        timeout=120,
        cwd=browser_root,
    )
    parsed: dict[str, Any] = {}
    ok = False
    reason = ""
    try:
        parsed = extract_json_tail(result["stdout"])
        screenshot = evidence_dir / "runtime" / "browser-use-screenshot.png"
        ok = result["ok"] and parsed.get("marker_found") is True and screenshot.exists() and screenshot.stat().st_size > 1000
        reason = f"marker_found={parsed.get('marker_found')} screenshot_bytes={screenshot.stat().st_size if screenshot.exists() else 0}"
    except Exception as exc:
        reason = f"parse_failed={exc}"
    write_json(evidence_dir / "runtime" / "browser_use_navigation.json", parsed or {"parse_error": reason})
    return scenario("Browser-use real browser navigation", ok, {"command_ok": result["ok"], "reason": reason}, "Uses browser-use MCP server module to navigate a local page and save a screenshot; no LLM extraction is used.")


def render_markdown(results: list[dict[str, Any]], threshold: int) -> str:
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    score = round(100 * passed / total) if total else 0
    lines = [
        "# Solar Heavy Proof Benchmark",
        "",
        f"- Generated: {now()}",
        f"- Score: {score} ({passed}/{total})",
        f"- Threshold: {threshold}",
        "",
        "```text",
        "┌────┬────────────────────────────────────────┬────────┬──────────────────────────────────────────────┐",
        "│ #  │ Proof                                  │ 状态   │ 证据摘要                                     │",
        "├────┼────────────────────────────────────────┼────────┼──────────────────────────────────────────────┤",
    ]
    for idx, item in enumerate(results, 1):
        name = item["name"][:38]
        status = item["status"]
        reason = str(item.get("evidence", {}).get("reason", item.get("notes", "")))[:44]
        lines.append(f"│ {idx:<2} │ {name:<38} │ {status:<6} │ {reason:<44} │")
    lines.extend([
        "└────┴────────────────────────────────────────┴────────┴──────────────────────────────────────────────┘",
        "```",
        "",
        "## Scope Boundary",
        "",
        "- This benchmark proves selected live runtime paths, not every possible production workflow.",
        "- Apple Notes and accepted-artifact writes use isolated temporary vaults to avoid polluting the real vault.",
        "- Browser-use proof uses deterministic navigation/screenshot, not token-consuming AI extraction.",
        "",
        "## Evidence",
        "",
        "- Raw stdout/stderr and command metadata are under `reports/heavy-proof-evidence/latest/commands/`.",
        "- Runtime artifacts are under `reports/heavy-proof-evidence/latest/runtime/`.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Solar heavyweight integration proof benchmark")
    parser.add_argument("--threshold", type=int, default=75)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    evidence_dir = REPORTS / "heavy-proof-evidence" / "latest"
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    results = [
        bench_mempalace_search(evidence_dir),
        bench_apple_notes_mock_ingest(evidence_dir),
        bench_accepted_artifact_export(evidence_dir),
        bench_browser_use_navigation(evidence_dir),
    ]
    passed = sum(1 for r in results if r["passed"])
    score = round(100 * passed / len(results)) if results else 0
    payload = {
        "ok": score >= args.threshold,
        "generated_at": now(),
        "threshold": args.threshold,
        "score": score,
        "passed": passed,
        "total": len(results),
        "results": results,
        "evidence_dir": str(evidence_dir),
    }
    write_json(REPORTS / "heavy-proof-benchmark-latest.json", payload)
    write_text(REPORTS / "heavy-proof-benchmark-latest.md", render_markdown(results, args.threshold))

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(results, args.threshold))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
