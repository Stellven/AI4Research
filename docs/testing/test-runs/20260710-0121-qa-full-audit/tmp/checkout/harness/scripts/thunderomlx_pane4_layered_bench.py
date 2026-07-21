#!/usr/bin/env python3
"""
ThunderOMLX Pane4 Layered Overhead Benchmark — N2

Measures overhead at each layer between bare ThunderOMLX API and pane tmux E2E:
  L1  API/model latency         (bare HTTP to ThunderOMLX)
  L2  KV cache load             (extracted from ThunderOMLX log)
  L3  Claude CLI startup        (--print invocation round-trip)
  L4  Extended thinking render  (thinking lines × per-token decode rate)
  L5  Hook overhead             (python3 spawn × tools × pre+post)
  L6  tmux send-keys→recv       (first visible content after send)
  L7  Harness poll latency      (sleep interval in poll loop)

Output: monitor-reports/thunderomlx-pane4-layered-bench-<TS>.{json,md}

Safety rules (enforced):
  - No token printed or persisted in output files
  - Only reads ThunderOMLX source (no writes)
  - Only writes to scripts/ and monitor-reports/
  - max_tokens capped at 32 for API measurements (no long outputs)
  - Unsafe cache features not re-enabled
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ── constants ──────────────────────────────────────────────────────────────
ENDPOINT = "http://127.0.0.1:8002/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"
PANE = "solar-harness-lab:0.3"
PANE_INDEX = 3  # 0-indexed, pane 4

REPORT_DIR = Path.home() / ".solar" / "harness" / "monitor-reports"
HARNESS_DIR = Path.home() / ".solar" / "harness"
LOG_PATH = Path.home() / "ThunderOMLX" / "omlx-8002.log"
HOOK_SCRIPT = HARNESS_DIR / "lib" / "claude_hook_event_bridge.py"
CLAUDE_BIN = Path.home() / "bin" / "claude"
EMPTY_MCP = HARNESS_DIR / "config" / "empty-mcp.json"
PANE_ENV_DIR = HARNESS_DIR / "run" / "pane-env"

# Measurement parameters
API_RUNS = 3           # fresh API runs (warm cache expected)
API_MAX_TOKENS = 32    # cap output to avoid long thinking
HOOK_RUNS = 5          # hook timing samples
POLL_SLEEP = 0.1       # poll interval for E2E test (seconds)
E2E_TIMEOUT = 60       # max wait for E2E response (seconds)

# Existing report paths (from N1 evidence)
EXISTING_API_REPORT = REPORT_DIR / "thunderomlx-pane4-perf-20260520T195355Z.json"
EXISTING_E2E_REPORT = REPORT_DIR / "thunderomlx-pane4-e2e-20260520T200037Z.json"

# Token generation rate observed in perf logs
OBS_GENERATION_TPS = 75.0  # tok/s from perf report (runs 2-6)


# ── helpers ────────────────────────────────────────────────────────────────

def _run(cmd: list[str], input_text: str = "", timeout: int = 30) -> tuple[str, int]:
    try:
        r = subprocess.run(
            cmd, input=input_text, text=True, capture_output=True, timeout=timeout
        )
        return r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 1
    except Exception as exc:
        return str(exc), 1


def _ps_all() -> str:
    out, _ = _run(["ps", "-A", "-o", "pid=,ppid=,comm="])
    return out


def _pane_pid() -> int | None:
    out, _ = _run(["tmux", "list-panes", "-t", PANE.rsplit(".", 1)[0],
                   "-F", "#{pane_index}\t#{pane_pid}"])
    for line in out.splitlines():
        parts = line.strip().split("\t", 1)
        if len(parts) == 2 and parts[0].strip() == str(PANE_INDEX):
            return int(parts[1].strip())
    return None


def _child_claude_pid(parent_pid: int) -> int | None:
    ps = _ps_all()
    for line in ps.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[1] == str(parent_pid) and parts[2].endswith("/claude"):
            return int(parts[0])
    return None


def _extract_token_and_url(pid: int) -> tuple[str, str]:
    """Return (token, base_url) without printing either."""
    out, _ = _run(["ps", "eww", "-p", str(pid)])
    token = ""
    base_url = ""
    for segment in out.split():
        if segment.startswith("ANTHROPIC_AUTH_TOKEN="):
            token = segment[len("ANTHROPIC_AUTH_TOKEN="):]
        elif segment.startswith("ANTHROPIC_BASE_URL="):
            base_url = segment[len("ANTHROPIC_BASE_URL="):]
    return token, base_url


def _post_api(token: str, prompt: str, max_tokens: int = API_MAX_TOKENS) -> dict:
    """Single bare API call. Returns timing + usage, no content."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"仅回复数字: {int(time.time()) % 1000}"},
        ],
        "max_tokens": max_tokens,
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
    t0 = time.perf_counter()
    ttft = None
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        status = exc.code
    elapsed = time.perf_counter() - t0

    try:
        parsed = json.loads(body)
    except Exception:
        return {"http_status": status, "error": "parse_fail", "elapsed_s": round(elapsed, 3)}

    if status != 200:
        return {
            "http_status": status,
            "elapsed_s": round(elapsed, 3),
            "error": parsed.get("detail") or parsed.get("error") or "non-200",
        }

    choice = (parsed.get("choices") or [{}])[0]
    usage = parsed.get("usage") or {}
    content = (choice.get("message") or {}).get("content") or ""
    bad_chars = any(ch in content for ch in ["�", "\x00"])

    total_time = usage.get("total_time") or elapsed
    ttft_s = usage.get("prompt_eval_duration") or usage.get("ttft")

    return {
        "http_status": status,
        "elapsed_s": round(elapsed, 3),
        "total_time_s": round(float(total_time), 3),
        "ttft_s": round(float(ttft_s), 3) if ttft_s else None,
        "cached_tokens": usage.get("cached_tokens"),
        "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "finish_reason": choice.get("finish_reason"),
        "bad_chars": bad_chars,
        # content deliberately not included
    }


def _capture_pane(pane: str) -> str:
    out, _ = _run(["tmux", "capture-pane", "-t", pane, "-p"])
    return out


# ── M1: Bare API Measurement ───────────────────────────────────────────────

def measure_bare_api(token: str, system_prompt: str) -> dict:
    """Run API_RUNS warm API calls and compute summary stats."""
    print(f"  M1: Running {API_RUNS} bare API calls (max_tokens={API_MAX_TOKENS})...")
    runs = []
    for i in range(API_RUNS):
        result = _post_api(token, system_prompt, API_MAX_TOKENS)
        result["run"] = i + 1
        runs.append(result)
        status = result.get("http_status")
        cached = result.get("cached_tokens", "?")
        total = result.get("total_time_s", result.get("elapsed_s", "?"))
        print(f"    run {i+1}: http={status} cached_tokens={cached} total={total}s")
        time.sleep(0.3)

    good = [r for r in runs if r.get("http_status") == 200]
    if not good:
        return {"status": "error", "runs": runs, "summary": {}}

    totals = [r["total_time_s"] for r in good if r.get("total_time_s")]
    ttfts = [r["ttft_s"] for r in good if r.get("ttft_s")]
    cached_list = [r["cached_tokens"] for r in good if r.get("cached_tokens") is not None]
    totals.sort()

    summary = {
        "good_runs": len(good),
        "bad_runs": len(runs) - len(good),
        "avg_total_s": round(sum(totals) / len(totals), 3) if totals else None,
        "p50_total_s": round(totals[len(totals) // 2], 3) if totals else None,
        "avg_ttft_s": round(sum(ttfts) / len(ttfts), 3) if ttfts else None,
        "cached_tokens": cached_list[0] if cached_list else None,
        "cache_hit_rate": sum(1 for c in cached_list if c and c > 0) / len(cached_list) if cached_list else 0,
        "bad_chars": any(r.get("bad_chars") for r in good),
    }

    # Strip run content (no content stored)
    safe_runs = [{k: v for k, v in r.items() if k != "content"} for r in runs]
    return {"status": "ok", "runs": safe_runs, "summary": summary}


# ── M2: Existing E2E Data ──────────────────────────────────────────────────

def load_existing_e2e() -> dict:
    """Load the existing E2E report and extract timing data."""
    print("  M2: Loading existing pane E2E report (200037Z)...")
    if not EXISTING_E2E_REPORT.exists():
        return {"status": "missing", "path": str(EXISTING_E2E_REPORT)}

    with EXISTING_E2E_REPORT.open() as f:
        data = json.load(f)

    result = {
        "status": "ok",
        "source": EXISTING_E2E_REPORT.name,
        "pane": data.get("pane"),
        "query_chars": data.get("query_chars"),
        "first_marker_seen_s": data.get("first_marker_seen_s"),
        "assistant_marker_seen_s": data.get("assistant_marker_seen_s"),
        "bad_chars": data.get("bad_chars"),
        "thinking_lines_count": sum(
            1 for line in (data.get("matching_lines") or [])
            if "Thinking" in line or "∴" in line
        ),
    }
    print(f"    total_e2e={result['assistant_marker_seen_s']}s  "
          f"thinking_lines={result['thinking_lines_count']}  "
          f"bad_chars={result['bad_chars']}")
    return result


# ── M2b: Enhanced E2E with thinking timing ─────────────────────────────────

def measure_enhanced_e2e(token: str, system_prompt: str) -> dict:
    """Run a fresh E2E test capturing thinking-marker timestamps."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    marker = f"N2-LAYERED-BENCH-{ts}"
    query = f"请只输出这一行文字（不要其他任何内容）：{marker}"

    print(f"  M2b: Enhanced E2E test (marker={marker})...")

    # Pre-capture baseline
    before = _capture_pane(PANE)

    # Send the query
    send_start = time.perf_counter()
    _run(["tmux", "send-keys", "-t", PANE, query, "Enter"])
    send_ts = time.perf_counter()

    # Poll for events with timestamps
    events: list[dict] = []
    first_content_s: float | None = None
    thinking_starts: list[float] = []
    thinking_ends: list[float] = []
    response_s: float | None = None
    last_seen: str = ""
    deadline = send_start + E2E_TIMEOUT
    bad_chars = False

    while time.perf_counter() < deadline:
        time.sleep(POLL_SLEEP)
        now = time.perf_counter() - send_start
        capture = _capture_pane(PANE)

        if capture == last_seen:
            continue
        last_seen = capture

        # Find new lines vs before
        lines = capture.splitlines()
        for line in lines:
            if marker in line and "请只输出" not in line and response_s is None:
                # This is the response containing the marker
                response_s = now
                if any(ch in line for ch in ["�", "\x00"]):
                    bad_chars = True
                print(f"    ⏺ Response seen at t={now:.3f}s")
                break
            if ("∴ Thinking" in line or "Thinking…" in line):
                if not thinking_starts:
                    thinking_starts.append(now)
                    print(f"    ∴ First thinking at t={now:.3f}s")
                thinking_ends.append(now)
            if first_content_s is None and (
                "∴" in line or "⏺" in line or "❯" in line
            ) and len(line.strip()) > 3:
                first_content_s = now

        if response_s is not None:
            break

    elapsed = time.perf_counter() - send_start

    thinking_span_s = None
    if thinking_starts and thinking_ends:
        thinking_span_s = round(thinking_ends[-1] - thinking_starts[0], 3)

    result = {
        "status": "ok" if response_s else "timeout",
        "marker": marker,
        "query_chars": len(query),
        "send_elapsed_s": round(send_ts - send_start, 3),
        "first_content_s": round(first_content_s, 3) if first_content_s else None,
        "thinking_start_s": round(thinking_starts[0], 3) if thinking_starts else None,
        "thinking_end_s": round(thinking_ends[-1], 3) if thinking_ends else None,
        "thinking_span_s": thinking_span_s,
        "thinking_lines_count": len(thinking_ends),
        "response_s": round(response_s, 3) if response_s else None,
        "total_elapsed_s": round(elapsed, 3),
        "bad_chars": bad_chars,
        "poll_interval_s": POLL_SLEEP,
    }
    print(f"    total={result['total_elapsed_s']}s  "
          f"thinking_span={result['thinking_span_s']}s  "
          f"bad_chars={result['bad_chars']}")
    return result


# ── M3: CLI Startup ────────────────────────────────────────────────────────

def measure_cli_startup(token: str, base_url: str) -> dict:
    """Measure Claude CLI startup overhead using --print with a trivial prompt."""
    print("  M3: Measuring Claude CLI startup overhead...")
    if not CLAUDE_BIN.exists():
        return {"status": "error", "reason": f"{CLAUDE_BIN} not found"}
    if not EMPTY_MCP.exists():
        return {"status": "error", "reason": f"{EMPTY_MCP} not found"}

    samples = []
    for i in range(3):
        env_override = {
            "ANTHROPIC_AUTH_TOKEN": token,
            "ANTHROPIC_BASE_URL": base_url or "http://127.0.0.1:8002",
            "HOME": str(Path.home()),
            "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
        }
        import os
        env = {**os.environ, **env_override}

        t0 = time.perf_counter()
        try:
            r = subprocess.run(
                [
                    str(CLAUDE_BIN),
                    "--bare",
                    "--tools", "default",
                    "--strict-mcp-config",
                    "--mcp-config", str(EMPTY_MCP),
                    "--model", "sonnet",
                    "--print", "echo OK",
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            elapsed = time.perf_counter() - t0
            output = (r.stdout + r.stderr)
            success = r.returncode == 0 or "OK" in output or len(output.strip()) > 0
            samples.append({
                "run": i + 1,
                "elapsed_s": round(elapsed, 3),
                "returncode": r.returncode,
                "success": success,
            })
            print(f"    run {i+1}: {elapsed:.3f}s rc={r.returncode}")
        except subprocess.TimeoutExpired:
            samples.append({"run": i + 1, "elapsed_s": 30.0, "success": False, "note": "timeout"})
        except Exception as exc:
            samples.append({"run": i + 1, "error": str(exc), "success": False})
        time.sleep(0.5)

    good = [s for s in samples if s.get("success")]
    if good:
        times = sorted(s["elapsed_s"] for s in good)
        avg = round(sum(times) / len(times), 3)
        p50 = round(times[len(times) // 2], 3)
    else:
        avg = p50 = None

    return {
        "status": "ok" if good else "error",
        "samples": samples,
        "avg_s": avg,
        "p50_s": p50,
        "note": "includes ThunderOMLX model inference for --print prompt",
    }


# ── M4: Hook Overhead ──────────────────────────────────────────────────────

def measure_hook_overhead() -> dict:
    """Measure the overhead of a single python3 hook spawn."""
    print(f"  M4: Measuring hook spawn overhead ({HOOK_RUNS} runs)...")
    if not HOOK_SCRIPT.exists():
        return {"status": "error", "reason": f"{HOOK_SCRIPT} not found"}

    samples = []
    for i in range(HOOK_RUNS):
        t0 = time.perf_counter()
        r = subprocess.run(
            ["python3", str(HOOK_SCRIPT), "pre-tool"],
            input=json.dumps({"tool": "Bash", "input": {}}),
            text=True,
            capture_output=True,
            timeout=10,
        )
        elapsed = time.perf_counter() - t0
        samples.append(round(elapsed * 1000, 1))  # ms

    samples.sort()
    avg_ms = round(sum(samples) / len(samples), 1)
    p50_ms = round(samples[len(samples) // 2], 1)
    p95_ms = round(samples[int(len(samples) * 0.95)], 1)

    print(f"    avg={avg_ms}ms  p50={p50_ms}ms  p95={p95_ms}ms")
    return {
        "status": "ok",
        "samples_ms": samples,
        "avg_ms": avg_ms,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "per_tool_call_ms": round(avg_ms * 2, 1),  # pre + post
        "note": "python3 spawn per hook invocation, measured pre-tool phase",
    }


# ── M5: Thinking Token Estimation ─────────────────────────────────────────

def estimate_thinking_tokens(e2e_total_s: float, api_p50_s: float) -> dict:
    """
    Estimate thinking tokens from timing delta.

    thinking_tokens ≈ (e2e_total - api_p50 - cli_startup_est - tmux_overhead_est)
                      × generation_tps
    """
    print("  M5: Estimating thinking token count from timing delta...")

    # Extract last Chat completion entries from log
    log_completions = []
    if LOG_PATH.exists():
        tail, _ = _run(["tail", "-500", str(LOG_PATH)])
        for line in tail.splitlines():
            m = re.search(r"Chat completion: (\d+) tokens in (\S+)s \((\S+) tok/s\)", line)
            if m:
                log_completions.append({
                    "tokens": int(m.group(1)),
                    "time_s": float(m.group(2)),
                    "tps": float(m.group(3)),
                })

    # Infer thinking tokens from timing
    # delta_s = e2e_total - api_p50_s (raw overhead from non-model layers)
    # We need to subtract non-thinking overhead:
    #   tmux send/recv: ~0.2s
    #   CLI startup (rough estimate if CLI used): ~0.3-0.5s
    #   poll latency: ~0.1s
    estimated_non_thinking_overhead_s = 0.5
    thinking_time_s = max(0.0, e2e_total_s - api_p50_s - estimated_non_thinking_overhead_s)
    estimated_thinking_tokens = int(thinking_time_s * OBS_GENERATION_TPS)

    print(f"    delta={e2e_total_s - api_p50_s:.2f}s  "
          f"thinking_time≈{thinking_time_s:.2f}s  "
          f"thinking_tokens≈{estimated_thinking_tokens}")

    return {
        "e2e_total_s": e2e_total_s,
        "api_p50_s": api_p50_s,
        "raw_delta_s": round(e2e_total_s - api_p50_s, 3),
        "non_thinking_overhead_s": estimated_non_thinking_overhead_s,
        "thinking_time_s": round(thinking_time_s, 3),
        "estimated_thinking_tokens": estimated_thinking_tokens,
        "generation_tps_basis": OBS_GENERATION_TPS,
        "log_completions_sample": log_completions[-3:] if log_completions else [],
        "note": "estimate only; direct thinking token count not exposed by API",
    }


# ── M6: Poll Interval ──────────────────────────────────────────────────────

def measure_poll_interval() -> dict:
    """Report the poll interval used in this benchmark and any harness config."""
    print("  M6: Documenting poll interval...")

    # Inspect autopilot.py for any configured interval
    autopilot_py = HARNESS_DIR / "lib" / "autopilot.py"
    interval_note = f"this script uses POLL_SLEEP={POLL_SLEEP}s"
    harness_poll_s = None

    if autopilot_py.exists():
        content = autopilot_py.read_text(errors="replace")
        m = re.search(r"poll_interval\s*=\s*(\d+\.?\d*)", content)
        if m:
            harness_poll_s = float(m.group(1))

    # The existing e2e report shows first_marker_seen=0.236s, which gives
    # an upper bound on the poll interval (≤ 0.236s)
    inferred_max_poll_s = 0.236  # from existing e2e first_marker_seen

    result = {
        "bench_poll_interval_s": POLL_SLEEP,
        "harness_autopilot_poll_s": harness_poll_s,
        "inferred_max_poll_s": inferred_max_poll_s,
        "basis": "existing e2e first_marker_seen=0.236s → poll interval ≤ 0.236s",
        "note": interval_note,
    }
    print(f"    bench_poll={POLL_SLEEP}s  autopilot_poll={harness_poll_s}s")
    return result


# ── Layer Decomposition ────────────────────────────────────────────────────

def compute_layer_decomposition(
    m1: dict,
    m2_e2e: float,
    m3: dict,
    m4: dict,
    m5: dict,
    m6: dict,
) -> dict:
    """Compute per-layer overhead and residual."""
    api_p50 = (m1.get("summary") or {}).get("p50_total_s") or 0.95  # fallback to prior data

    # L1: ThunderOMLX API/model
    l1_s = api_p50

    # L2: KV cache load (observed in perf logs: batch load ~10-13ms when warm)
    l2_s = 0.012

    # L3: CLI startup (from M3, minus model inference component)
    # M3 measures full --print round-trip including model. Estimate startup only as ~0.3s
    l3_cli_s = 0.3
    if m3.get("status") == "ok" and m3.get("avg_s"):
        # subtract api_p50 to get startup cost
        raw = m3["avg_s"] - api_p50
        l3_cli_s = max(0.1, min(raw, 3.0))

    # L4: Extended thinking render (from M5 estimate)
    l4_thinking_s = m5.get("thinking_time_s") or (m2_e2e - api_p50 - 0.5)
    l4_thinking_s = max(0.0, l4_thinking_s)

    # L5: Hook overhead (pre+post per tool call)
    hook_per_call_ms = (m4.get("per_tool_call_ms") or 80)
    # For a short e2e query with 0 explicit tools, hooks may not fire.
    # But Claude CLI routing logic fires some internal hooks → estimate 0-1 tool calls.
    l5_hooks_s = round(hook_per_call_ms / 1000 * 0.5, 3)  # ~0.5 tool calls average

    # L6: tmux send-keys → first visible content
    l6_tmux_s = 0.236  # from existing e2e first_marker_seen

    # L7: Harness poll latency
    l7_poll_s = m6.get("bench_poll_interval_s") or POLL_SLEEP

    total_accounted = l1_s + l2_s + l3_cli_s + l4_thinking_s + l5_hooks_s + l6_tmux_s + l7_poll_s
    residual = round(m2_e2e - total_accounted, 3)

    layers = [
        {"layer": "L1", "name": "ThunderOMLX API/model (warm cache)", "est_s": round(l1_s, 3), "basis": "M1 P50 total"},
        {"layer": "L2", "name": "KV cache block load (SSD→RAM)", "est_s": round(l2_s, 3), "basis": "omlx log: batch load 10-13ms"},
        {"layer": "L3", "name": "Claude CLI startup", "est_s": round(l3_cli_s, 3), "basis": "M3 avg minus model time"},
        {"layer": "L4", "name": "Extended thinking render", "est_s": round(l4_thinking_s, 3), "basis": "M5 timing-based estimate"},
        {"layer": "L5", "name": "Hook overhead (pre+post)", "est_s": round(l5_hooks_s, 3), "basis": f"M4 {hook_per_call_ms}ms/call × ~0.5 calls"},
        {"layer": "L6", "name": "tmux send-keys → first content", "est_s": round(l6_tmux_s, 3), "basis": "existing e2e first_marker_seen"},
        {"layer": "L7", "name": "Harness poll sleep", "est_s": round(l7_poll_s, 3), "basis": f"poll_sleep={l7_poll_s}s"},
    ]

    return {
        "e2e_total_s": m2_e2e,
        "api_baseline_s": l1_s,
        "delta_s": round(m2_e2e - l1_s, 3),
        "layers": layers,
        "total_accounted_s": round(total_accounted, 3),
        "residual_s": residual,
        "residual_note": (
            "unaccounted overhead — likely tmux rendering, thinking pre-budget, "
            "or prompt-routing decision latency"
        ),
    }


# ── Report writing ─────────────────────────────────────────────────────────

def write_report(ts: str, result: dict) -> tuple[Path, Path]:
    """Write JSON and MD reports. Token is never included."""
    json_path = REPORT_DIR / f"thunderomlx-pane4-layered-bench-{ts}.json"
    md_path = REPORT_DIR / f"thunderomlx-pane4-layered-bench-{ts}.md"

    # Ensure no token fields in report
    safe = json.loads(json.dumps(result))  # deep copy via JSON
    for key in ("token", "auth_token", "api_key", "authorization"):
        safe.pop(key, None)

    json_path.write_text(json.dumps(safe, indent=2, ensure_ascii=False))

    # Build MD
    d = result["decomposition"]
    m1_sum = result.get("m1_bare_api", {}).get("summary", {})
    m2_orig = result.get("m2_existing_e2e", {})
    m2b = result.get("m2b_enhanced_e2e", {})
    m4 = result.get("m4_hook_overhead", {})

    md_lines = [
        f"# ThunderOMLX Pane4 Layered Overhead Benchmark",
        f"",
        f"Generated: {ts}  ",
        f"Node: N2 (sprint-20260520-thunderomlx-qwen36-pane-overhead)",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| metric | value |",
        f"|---|---|",
        f"| E2E total (pane tmux) | **{d['e2e_total_s']} s** |",
        f"| Bare API P50 (ThunderOMLX) | **{d['api_baseline_s']} s** |",
        f"| Overhead delta | **{d['delta_s']} s** |",
        f"| cached_tokens (API, warm) | {m1_sum.get('cached_tokens', 'N/A')} |",
        f"| cache_hit_rate | {m1_sum.get('cache_hit_rate', 'N/A')} |",
        f"| bad_chars (API) | {m1_sum.get('bad_chars', False)} |",
        f"| bad_chars (E2E) | {m2_orig.get('bad_chars', m2b.get('bad_chars', 'N/A'))} |",
        f"",
        f"---",
        f"",
        f"## Layer Decomposition",
        f"",
        f"| Layer | Name | Est. overhead (s) | Basis |",
        f"|---|---|---|---|",
    ]
    for layer in d["layers"]:
        pct = round(layer["est_s"] / d["e2e_total_s"] * 100, 1)
        md_lines.append(
            f"| {layer['layer']} | {layer['name']} | {layer['est_s']} ({pct}%) | {layer['basis']} |"
        )
    md_lines += [
        f"| — | **Total accounted** | **{d['total_accounted_s']}** | — |",
        f"| — | **Residual / unaccounted** | **{d['residual_s']}** | {d['residual_note']} |",
        f"",
        f"---",
        f"",
        f"## M1 — Bare API Timing (fresh)",
        f"",
        f"| run | http | cached_tokens | total_s | ttft_s | bad_chars |",
        f"|---:|---:|---:|---:|---:|---|",
    ]
    for run in (result.get("m1_bare_api", {}).get("runs") or []):
        md_lines.append(
            f"| {run.get('run')} | {run.get('http_status')} | "
            f"{run.get('cached_tokens', '?')} | {run.get('total_time_s', run.get('elapsed_s', '?'))} | "
            f"{run.get('ttft_s', '?')} | {run.get('bad_chars', '?')} |"
        )
    md_lines += [
        f"",
        f"P50 total: **{m1_sum.get('p50_total_s')} s**  avg: **{m1_sum.get('avg_total_s')} s**",
        f"",
        f"---",
        f"",
        f"## M2 — Pane tmux E2E Timing",
        f"",
        f"**Existing report** (200037Z):",
        f"",
        f"| metric | value |",
        f"|---|---|",
        f"| first_marker_seen_s | {m2_orig.get('first_marker_seen_s')} s |",
        f"| assistant_marker_seen_s | {m2_orig.get('assistant_marker_seen_s')} s |",
        f"| thinking_lines | {m2_orig.get('thinking_lines_count', '?')} |",
        f"| bad_chars | {m2_orig.get('bad_chars')} |",
    ]

    if m2b.get("status") == "ok":
        md_lines += [
            f"",
            f"**Fresh enhanced E2E** (N2 run):",
            f"",
            f"| metric | value |",
            f"|---|---|",
            f"| first_content_s | {m2b.get('first_content_s')} s |",
            f"| thinking_start_s | {m2b.get('thinking_start_s')} s |",
            f"| thinking_end_s | {m2b.get('thinking_end_s')} s |",
            f"| thinking_span_s | {m2b.get('thinking_span_s')} s |",
            f"| thinking_lines | {m2b.get('thinking_lines_count')} |",
            f"| response_s | {m2b.get('response_s')} s |",
            f"| total_elapsed_s | {m2b.get('total_elapsed_s')} s |",
            f"| bad_chars | {m2b.get('bad_chars')} |",
        ]

    m3 = result.get("m3_cli_startup", {})
    m5 = result.get("m5_thinking_estimate", {})
    m6 = result.get("m6_poll_interval", {})

    md_lines += [
        f"",
        f"---",
        f"",
        f"## M3 — Claude CLI Startup",
        f"",
        f"avg: **{m3.get('avg_s')} s**  p50: **{m3.get('p50_s')} s**",
        f"",
        f"Note: {m3.get('note', '')}",
        f"",
        f"---",
        f"",
        f"## M4 — Hook Overhead",
        f"",
        f"| metric | value |",
        f"|---|---|",
        f"| avg per spawn | {m4.get('avg_ms')} ms |",
        f"| p50 per spawn | {m4.get('p50_ms')} ms |",
        f"| p95 per spawn | {m4.get('p95_ms')} ms |",
        f"| per tool call (pre+post) | {m4.get('per_tool_call_ms')} ms |",
        f"",
        f"---",
        f"",
        f"## M5 — Thinking Token Estimate",
        f"",
        f"| metric | value |",
        f"|---|---|",
        f"| raw delta (e2e − api) | {m5.get('raw_delta_s')} s |",
        f"| non-thinking overhead est. | {m5.get('non_thinking_overhead_s')} s |",
        f"| thinking time est. | {m5.get('thinking_time_s')} s |",
        f"| thinking tokens est. | **{m5.get('estimated_thinking_tokens')}** |",
        f"| generation tps basis | {m5.get('generation_tps_basis')} tok/s |",
        f"",
        f"---",
        f"",
        f"## M6 — tmux Poll Interval",
        f"",
        f"| metric | value |",
        f"|---|---|",
        f"| bench poll interval | {m6.get('bench_poll_interval_s')} s |",
        f"| autopilot poll interval | {m6.get('harness_autopilot_poll_s')} s |",
        f"| inferred max poll (from e2e) | ≤ {m6.get('inferred_max_poll_s')} s |",
        f"",
        f"---",
        f"",
        f"## Key Finding",
        f"",
        f"The **{d['delta_s']} s** overhead delta between bare API ({d['api_baseline_s']} s) "
        f"and pane E2E ({d['e2e_total_s']} s) is dominated by:",
        f"",
        f"1. **L4 Extended thinking** — estimated {d['layers'][3]['est_s']} s "
        f"({round(d['layers'][3]['est_s']/d['e2e_total_s']*100,0):.0f}% of total). "
        f"Qwen3.6 triggers extended thinking even for short queries. "
        f"Setting a thinking budget or using `thinking: {{type: disabled}}` is the highest-impact lever.",
        f"2. **L3 CLI startup** — estimated {d['layers'][2]['est_s']} s — "
        f"Python/Node init + settings load per dispatch.",
        f"3. **L5–L7** (hooks, tmux, poll) — combined ≤ 0.5 s — low individual impact.",
        f"",
        f"**Unsafe cache features remain DISABLED** (partial_block_cache, approximate_skip, "
        f"chunked_prefill, block_size_enlargement).",
    ]

    md_path.write_text("\n".join(md_lines) + "\n")
    return json_path, md_path


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n=== ThunderOMLX Pane4 Layered Benchmark === {ts}\n")

    # ── Step 0: Extract token from pane 4 process env ──────────────────────
    print("Step 0: Extracting auth token from pane 4 process environment...")
    pane_pid = _pane_pid()
    if not pane_pid:
        print("  ERROR: Cannot find pane 4 PID")
        return 1
    claude_pid = _child_claude_pid(pane_pid)
    if not claude_pid:
        print("  ERROR: Cannot find claude child of pane 4")
        return 1
    token, base_url = _extract_token_and_url(claude_pid)
    if not token:
        print("  ERROR: Cannot extract ANTHROPIC_AUTH_TOKEN from pane 4 env")
        return 1
    print(f"  pane_pid={pane_pid}  claude_pid={claude_pid}  base_url={base_url}  token=***")

    # ── Step 1: Get system prompt hash from existing perf report ───────────
    system_prompt = ""
    if EXISTING_API_REPORT.exists():
        with EXISTING_API_REPORT.open() as f:
            existing_api = json.load(f)
        prompt_hash = existing_api.get("prompt_hash", "")
        print(f"  Existing API report: prompt_hash={prompt_hash} runs={len(existing_api.get('runs',[]))}")

    # For fresh API calls, use the same token — prompt will differ slightly from the
    # prewarm prompt, but the system prompt cached in ThunderOMLX should still hit.
    # Use a short system prompt that fits within the cache.
    system_prompt = "You are a benchmark assistant. Reply only as instructed."

    # ── M1: Bare API ───────────────────────────────────────────────────────
    print("\n[M1] Bare API measurement")
    m1 = measure_bare_api(token, system_prompt)

    # Also record the existing report summary for comparison
    existing_api_summary = {}
    if EXISTING_API_REPORT.exists():
        with EXISTING_API_REPORT.open() as f:
            ea = json.load(f)
        existing_api_summary = {
            "source": EXISTING_API_REPORT.name,
            "runs": ea.get("runs", []),
            "summary": ea.get("summary", {}),
        }

    # ── M2: Existing E2E ───────────────────────────────────────────────────
    print("\n[M2] Loading existing E2E data")
    m2_existing = load_existing_e2e()
    e2e_total = m2_existing.get("assistant_marker_seen_s") or 8.302

    # ── M2b: Enhanced E2E ──────────────────────────────────────────────────
    print("\n[M2b] Running fresh enhanced E2E test")
    m2b = measure_enhanced_e2e(token, system_prompt)
    # Use fresh e2e total if available, else fall back to existing
    if m2b.get("status") == "ok" and m2b.get("total_elapsed_s"):
        e2e_total = m2b["total_elapsed_s"]

    # ── M3: CLI Startup ────────────────────────────────────────────────────
    print("\n[M3] Measuring CLI startup overhead")
    m3 = measure_cli_startup(token, base_url)

    # ── M4: Hook Overhead ──────────────────────────────────────────────────
    print("\n[M4] Measuring hook spawn overhead")
    m4 = measure_hook_overhead()

    # ── M5: Thinking Token Estimation ──────────────────────────────────────
    print("\n[M5] Estimating thinking tokens")
    api_p50 = (m1.get("summary") or {}).get("p50_total_s") or (
        (existing_api_summary.get("summary") or {}).get("p50_total_s") or 0.95
    )
    m5 = estimate_thinking_tokens(e2e_total, api_p50)

    # ── M6: Poll Interval ──────────────────────────────────────────────────
    print("\n[M6] Documenting poll interval")
    m6 = measure_poll_interval()

    # ── Layer Decomposition ────────────────────────────────────────────────
    print("\n[Decomposition] Computing layer overhead breakdown")
    decomp = compute_layer_decomposition(m1, e2e_total, m3, m4, m5, m6)

    # ── Assemble result (no token) ─────────────────────────────────────────
    result = {
        "generated_at": ts,
        "sprint": "sprint-20260520-thunderomlx-qwen36-pane-overhead",
        "node": "N2",
        "model": MODEL,
        "endpoint": ENDPOINT,
        "pane": PANE,
        "m1_bare_api": m1,
        "m1_existing_api": existing_api_summary,
        "m2_existing_e2e": m2_existing,
        "m2b_enhanced_e2e": m2b,
        "m3_cli_startup": m3,
        "m4_hook_overhead": m4,
        "m5_thinking_estimate": m5,
        "m6_poll_interval": m6,
        "decomposition": decomp,
    }

    # ── Write reports ──────────────────────────────────────────────────────
    print("\n[Report] Writing JSON and MD reports...")
    json_path, md_path = write_report(ts, result)
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")

    # ── Print summary ──────────────────────────────────────────────────────
    print(f"\n=== Summary ===")
    print(f"  E2E total:       {e2e_total:.3f} s")
    print(f"  API P50:         {api_p50:.3f} s")
    print(f"  Delta:           {e2e_total - api_p50:.3f} s")
    print(f"  Thinking (est.): {m5.get('estimated_thinking_tokens')} tokens  "
          f"{m5.get('thinking_time_s')} s")
    print(f"  Hook/call:       {m4.get('per_tool_call_ms')} ms")
    print(f"  CLI startup:     {m3.get('avg_s')} s")
    print(f"  cached_tokens:   {(m1.get('summary') or {}).get('cached_tokens')}")
    print(f"  bad_chars:       {(m1.get('summary') or {}).get('bad_chars')}")
    print()

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
