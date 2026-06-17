#!/usr/bin/env python3
"""Dev-only visual feedback loop for the Solar Harness P0 dashboard.

This script creates a realistic temporary HARNESS_DIR, starts the existing
stdlib status server against that data, drives the dashboard with Playwright,
captures full-page and section screenshots, and writes a small visual audit.

It is intentionally not part of the runtime or install path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATUS_SERVER = ROOT / "harness" / "lib" / "symphony" / "status-server.py"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def today() -> str:
    return dt.datetime.now().astimezone().date().isoformat()


def node(node_id: str, goal: str, status: str, depends_on: list[str], capabilities: list[str]) -> dict:
    return {
        "id": node_id,
        "goal": goal,
        "status": status,
        "depends_on": depends_on,
        "acceptance": [f"{node_id} evidence exists"],
        "priority": 1,
        "required_phase": None,
        "required_node_id": depends_on[-1] if depends_on else None,
        "required_node_status": "passed" if depends_on else None,
        "required_capabilities": capabilities,
        "write_scope": ["harness/status-server"],
        "read_scope": ["harness"],
        "estimated_cost": 1.0 + len(capabilities),
    }


def seed_harness(harness: Path) -> Path:
    sid = "rich-sprint-001"
    running_sid = "rich-sprint-running"
    done_sid = "rich-sprint-002"
    sprints = harness / "sprints"
    state = harness / "state"
    sessions = harness / "sessions"
    bin_dir = harness / "dev-bin"

    write_json(
        sprints / f"{sid}.status.json",
        {
            "sprint_id": sid,
            "title": "Build Codex-style dashboard observability",
            "status": "active",
            "phase": "planning_complete",
            "epic_id": "visual-demo",
        },
    )
    write_json(
        sprints / f"{running_sid}.status.json",
        {
            "sprint_id": running_sid,
            "title": "Live build sprint with active agents",
            "status": "active",
            "phase": "planning_complete",
            "epic_id": "visual-demo",
        },
    )
    write_json(
        sprints / f"{done_sid}.status.json",
        {
            "sprint_id": done_sid,
            "title": "Completed report sprint",
            "status": "completed",
            "phase": "build_complete",
            "epic_id": "visual-demo",
        },
    )
    write_json(
        sprints / f"{sid}.task_dag.state.json",
        {
            "sprint_id": sid,
            "dag_variant": "standard",
            "required_gates": ["spec", "prd", "plan", "build"],
            "runtime_state": {
                "nodes": {
                    "spec": {"status": "passed"},
                    "prd": {"status": "passed"},
                    "plan": {"status": "passed"},
                    "build": {"status": "gate_blocked"},
                }
            },
            "nodes": [
                node("spec", "Turn the request into a concise sprint brief.", "passed", [], ["product"]),
                node("prd", "Produce the PRD-ready scope and acceptance notes.", "passed", ["spec"], ["planning"]),
                node("plan", "Create the DAG and route work to the available pane pool.", "passed", ["prd"], ["planning", "routing"]),
                node(
                    "build",
                    "Implement rich activity, agent state, DAG progress, deliverables, usage, and honest stalls.",
                    "gate_blocked",
                    ["plan"],
                    ["frontend", "status-server", "nonexistent-skill"],
                ),
            ],
        },
    )
    write_json(
        sprints / f"{running_sid}.closure.json",
        {
            "sprint_id": running_sid,
            "runtime_state": {
                "nodes": {
                    "spec": {"status": "passed"},
                    "prd": {"status": "passed"},
                    "plan": {"status": "passed"},
                    "build": {"status": "active"},
                    "review": {"status": "pending"},
                }
            },
            "nodes": [
                node("spec", "Capture the developer observability task.", "passed", [], ["product"]),
                node("prd", "Shape the app shell acceptance path.", "passed", ["spec"], ["planning"]),
                node("plan", "Prepare the implementation DAG.", "passed", ["prd"], ["planning"]),
                node("build", "Build the React app shell and live views.", "active", ["plan"], ["frontend", "status-server"]),
                node("review", "Review screenshots and run gates.", "pending", ["build"], ["evaluation"]),
            ],
        },
    )
    write_json(
        sprints / f"{done_sid}.task_graph.json",
        {
            "sprint_id": done_sid,
            "nodes": [
                node("report", "Generate finished HTML report.", "passed", [], ["research", "writing"]),
                node("review", "Accept final report evidence.", "passed", ["report"], ["evaluation"]),
            ],
        },
    )
    write_json(
        state / "autopilot-state.json",
        {
            "routing_decisions": [
                {
                    "sprint_id": sid,
                    "node_id": "plan",
                    "decision": "dispatched",
                    "target_pane": "%1:0.1",
                    "provided_capabilities": ["planning", "routing"],
                },
                {
                    "sprint_id": sid,
                    "node_id": "build",
                    "decision": "no_matching_worker",
                    "target_pane": "",
                    "blocked_reason": "no_matching_worker: required capability nonexistent-skill",
                    "provided_capabilities": ["frontend"],
                },
                {
                    "sprint_id": running_sid,
                    "node_id": "build",
                    "decision": "dispatched",
                    "target_pane": "%1:0.2",
                    "provided_capabilities": ["frontend", "status-server"],
                },
            ]
        },
    )
    write_json(
        state / "pane-state.json",
        [
            {"id": "%1:0.0", "role": "PM", "state": "idle", "model": "claude-sonnet"},
            {"id": "%1:0.1", "role": "Planner", "state": "running", "model": "claude-sonnet"},
            {"id": "%1:0.2", "role": "Builder", "state": "blocked", "model": "claude-sonnet"},
            {"id": "%1:0.3", "role": "Evaluator", "state": "idle", "model": "claude-sonnet"},
        ],
    )
    events = [
        (
            "2026-06-16T10:00:00Z",
            "intake_created",
            "PM",
            {
                "message": "PM scoped the dashboard request into a Phase-0 app-shell sprint.",
                "thought": "The owner wants observability that feels like an agent workspace, not an admin panel.",
                "phase": "spec",
            },
        ),
        (
            "2026-06-16T10:01:00Z",
            "phase_transition",
            "PM",
            {
                "phase": "prd_ready",
                "status": "active",
                "summary": "Acceptance path is clear: intake, live process stream, deliverables, usage, and honest stalls.",
            },
        ),
        (
            "2026-06-16T10:02:00Z",
            "dispatch_decision",
            "Planner",
            {
                "node_id": "plan",
                "target_pane": "%1:0.1",
                "decision": "dispatched",
                "thought": "Planner built a four-node DAG and routed planning to the available pane.",
            },
        ),
        (
            "2026-06-16T10:03:00Z",
            "model_session_started",
            "Planner",
            {
                "model": "claude-sonnet",
                "node_id": "plan",
                "summary": "Planner is resolving dependencies and matching required capabilities to pane supply.",
            },
        ),
        (
            "2026-06-16T10:04:00Z",
            "gate_blocked",
            "Builder",
            {
                "node_id": "build",
                "decision": "no_matching_worker",
                "reason": "required capability nonexistent-skill",
                "phase": "planning_complete",
                "thought": "Builder cannot start because the DAG requires a capability no registered worker advertises.",
            },
        ),
    ]
    write_text(
        sessions / sid / "events.jsonl",
        "".join(json.dumps({"ts": ts, "sprint_id": sid, "type": typ, "actor": actor, "payload": payload}) + "\n" for ts, typ, actor, payload in events),
    )
    running_events = [
        ("2026-06-16T11:00:00Z", "intake_created", "PM", {"message": "PM accepted the app shell sprint and summarized the owner intent.", "phase": "spec"}),
        ("2026-06-16T11:01:00Z", "phase_transition", "Planner", {"phase": "planning_complete", "status": "active", "summary": "Planner converted the scope into a buildable DAG."}),
        ("2026-06-16T11:02:00Z", "dispatch_decision", "Planner", {"node_id": "build", "target_pane": "%1:0.2", "decision": "dispatched", "thought": "The build node matches the Builder pane capabilities."}),
        ("2026-06-16T11:03:00Z", "model_session_started", "Builder", {"model": "claude-sonnet", "node_id": "build", "summary": "Builder is replacing the card grid with a process stream and separate results rail."}),
    ]
    write_text(
        sessions / running_sid / "events.jsonl",
        "".join(json.dumps({"ts": ts, "sprint_id": running_sid, "type": typ, "actor": actor, "payload": payload}) + "\n" for ts, typ, actor, payload in running_events),
    )
    done_events = [
        ("2026-06-16T12:00:00Z", "phase_transition", "Evaluator", {"phase": "build_complete", "status": "completed", "summary": "Evaluator moved the sprint into build complete after artifact review."}),
        ("2026-06-16T12:02:00Z", "milestone_completed", "Evaluator", {"node_id": "review", "message": "Final artifact accepted", "summary": "Evaluator accepted the HTML report and evidence package."}),
    ]
    write_text(
        sessions / done_sid / "events.jsonl",
        "".join(json.dumps({"ts": ts, "sprint_id": done_sid, "type": typ, "actor": actor, "payload": payload}) + "\n" for ts, typ, actor, payload in done_events),
    )
    write_text(harness / "events" / "all.jsonl", "")
    write_json(state / "quota-footer" / "claude-sonnet.json", {"date": today(), "model_key": "claude-sonnet", "used_tokens": 44100000})
    write_json(state / "quota-footer" / "claude-opus.json", {"date": today(), "model_key": "claude-opus", "used_tokens": 8200000})
    write_text(harness / "config.env", "LAB_MODEL_MATRIX=all-claude-default\nSOLAR_PLANNER_MODEL=claude-sonnet\n")
    write_text(
        sprints / sid / ".research" / "dashboard-report.html",
        "<!doctype html><html><body><h1>Visual Mock Report</h1><p>Generated by dev-only dashboard visual harness.</p></body></html>",
    )
    write_text(sprints / sid / ".research" / "notes.md", "# Visual mock notes\n")
    write_text(
        sprints / done_sid / ".research" / "final-report.html",
        "<!doctype html><html><body><h1>Completed Report</h1><p>Finished sprint artifact.</p></body></html>",
    )

    fake_solar = bin_dir / "solar"
    write_text(
        fake_solar,
        """#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path

root = Path(os.environ["HARNESS_DIR"])
task = ""
args = sys.argv[1:]
for idx, value in enumerate(args):
    if value == "--request" and idx + 1 < len(args):
        task = args[idx + 1]
sid = "visual-intake-" + str(int(time.time()))
sprints = root / "sprints"
sessions = root / "sessions" / sid
sprints.mkdir(parents=True, exist_ok=True)
sessions.mkdir(parents=True, exist_ok=True)
(sprints / f"{sid}.status.json").write_text(json.dumps({
    "sprint_id": sid,
    "title": task or "Visual intake task",
    "status": "active",
    "phase": "spec",
    "epic_id": "visual-demo"
}), encoding="utf-8")
(sprints / f"{sid}.task_graph.json").write_text(json.dumps({
    "sprint_id": sid,
    "nodes": [{
        "id": "spec",
        "goal": "Capture the submitted dashboard task.",
        "status": "active",
        "depends_on": [],
        "acceptance": ["task accepted"],
        "priority": 1,
        "required_phase": None,
        "required_node_id": None,
        "required_node_status": None,
        "required_capabilities": ["product"]
    }]
}), encoding="utf-8")
(sessions / "events.jsonl").write_text(json.dumps({
    "ts": "2026-06-16T10:05:00Z",
    "sprint_id": sid,
    "type": "intake_created",
    "actor": "PM",
    "payload": {"message": "Created from Playwright visual run", "phase": "spec"}
}) + "\\n", encoding="utf-8")
print(f"Sprint created: {sid}")
""",
    )
    fake_solar.chmod(0o755)
    return bin_dir


def wait_for_server(harness: Path, proc: subprocess.Popen[str]) -> int:
    port_file = harness / "run" / "status-server.port"
    deadline = time.time() + 12
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"status server exited early with {proc.returncode}")
        if port_file.exists():
            port = int(port_file.read_text(encoding="utf-8").strip())
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.5) as response:
                    if response.read().decode("utf-8") == "ok":
                        return port
            except Exception:
                pass
        time.sleep(0.2)
    raise TimeoutError("status server did not become ready")


def parse_rgb(value: str) -> tuple[int, int, int] | None:
    value = value.strip()
    if value.startswith("#") and len(value) == 7:
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
    if value.startswith("rgb"):
        nums = value[value.find("(") + 1 : value.find(")")].replace("/", ",").split(",")
        try:
            return tuple(int(float(part.strip().split()[0])) for part in nums[:3])  # type: ignore[return-value]
        except Exception:
            return None
    return None


def luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        s = value / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float | None:
    rgb_a = parse_rgb(a)
    rgb_b = parse_rgb(b)
    if not rgb_a or not rgb_b:
        return None
    l1, l2 = sorted([luminance(rgb_a), luminance(rgb_b)], reverse=True)
    return round((l1 + 0.05) / (l2 + 0.05), 2)


def audit(page) -> dict:
    raw = page.evaluate(
        """() => {
          const css = getComputedStyle(document.documentElement);
          const token = (name) => css.getPropertyValue(name).trim();
          const size = (sel) => {
            const el = document.querySelector(sel);
            return el ? getComputedStyle(el).fontSize : "";
          };
          const bordered = Array.from(document.querySelectorAll('*')).filter((el) => {
            const s = getComputedStyle(el);
            return s.borderStyle !== 'none' && parseFloat(s.borderWidth) > 0;
          });
          const boxes = Array.from(document.querySelectorAll('.panel,.metric,.process-step,.primary-deliverable,.compact-session-header,.process-stream-panel'));
          const clickables = Array.from(document.querySelectorAll('button,select,textarea,a')).map((el) => {
            const r = el.getBoundingClientRect();
            return { tag: el.tagName.toLowerCase(), width: Math.round(r.width), height: Math.round(r.height) };
          });
          return {
            tokens: {
              bg: token('--bg'), panel: token('--panel'), panel2: token('--panel-2'),
              text: token('--text'), muted: token('--muted'), green: token('--green'),
              blue: token('--blue'), amber: token('--amber'), red: token('--red'),
              accent: token('--accent'), line: token('--line'), focusRing: token('--focus-ring'),
              radius: token('--radius'), display: token('--type-display')
            },
            fontSizes: {
              h1: size('h1'), h2: size('h2'), metric: size('.metric span'),
              agentActivity: size('.agent-activity'), event: size('.event-row p')
            },
            borderedCount: bordered.length,
            majorBoxCount: boxes.length,
            gradientCount: Array.from(document.querySelectorAll('*')).filter((el) => {
              const s = getComputedStyle(el);
              return s.backgroundImage && s.backgroundImage.includes('gradient');
            }).length,
            clickables,
            viewport: { width: window.innerWidth, height: window.innerHeight },
            bodyScrollHeight: document.body.scrollHeight,
            performance: (() => {
              const nav = performance.getEntriesByType('navigation')[0];
              const fcp = performance.getEntriesByName('first-contentful-paint')[0];
              const fp = performance.getEntriesByName('first-paint')[0];
              return {
                firstPaint: fp ? Math.round(fp.startTime) : null,
                firstContentfulPaint: fcp ? Math.round(fcp.startTime) : null,
                domContentLoaded: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
                loadEventEnd: nav ? Math.round(nav.loadEventEnd) : null
              };
            })()
          };
        }"""
    )
    ratios = {
        "text_on_bg": contrast(raw["tokens"]["text"], raw["tokens"]["bg"]),
        "muted_on_bg": contrast(raw["tokens"]["muted"], raw["tokens"]["bg"]),
        "text_on_panel": contrast(raw["tokens"]["text"], raw["tokens"]["panel"]),
        "amber_on_bg": contrast(raw["tokens"]["amber"], raw["tokens"]["bg"]),
        "green_on_bg": contrast(raw["tokens"]["green"], raw["tokens"]["bg"]),
        "blue_on_bg": contrast(raw["tokens"]["blue"], raw["tokens"]["bg"]),
    }
    flags = []
    h1_size = float(str(raw["fontSizes"]["h1"]).replace("px", "") or 0)
    if h1_size < 22:
        flags.append("Primary heading is below 22px; hierarchy may read flat.")
    if raw["borderedCount"] >= 110 and raw["majorBoxCount"] >= 34:
        flags.append("Many major regions render as bordered boxes; reduce div-soup with whitespace/dividers.")
    if any(item["height"] < 36 for item in raw["clickables"] if item["tag"] in {"button", "select", "textarea"}):
        flags.append("One or more controls are below a comfortable desktop hit target.")
    for name, value in ratios.items():
        if value is not None and value < 3:
            flags.append(f"Low contrast: {name} ratio {value}.")
    raw["contrast"] = ratios
    raw["flags"] = flags
    return raw


def measure_session_switch(page, link_name: str, title_fragment: str) -> dict:
    started = time.perf_counter()
    saw_skeleton = False
    page.get_by_role("link", name=link_name).click()
    deadline = time.perf_counter() + 6
    while time.perf_counter() < deadline:
        if page.locator(".loading-workbench,.loading-panel").count() > 0:
            saw_skeleton = True
        titles = page.locator("[data-testid='process-header'] h1")
        if titles.count() > 0 and title_fragment in titles.first.inner_text(timeout=500):
            return {
                "target": title_fragment,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "saw_skeleton": saw_skeleton,
            }
        page.wait_for_timeout(50)
    return {
        "target": title_fragment,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "saw_skeleton": saw_skeleton,
        "timeout": True,
    }


def screenshot(page, output_dir: Path, name: str, selector: str | None = None) -> None:
    path = output_dir / f"{name}.png"
    if not selector:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(100)
    if selector:
        loc = page.locator(selector).first
        loc.screenshot(path=str(path))
    else:
        page.screenshot(path=str(path), full_page=True)


def wait_for_hero_title(page, title_fragment: str) -> None:
    page.wait_for_function(
        """fragment => {
          const loading = document.querySelector(".loading-panel,.loading-workbench");
          const heroes = Array.from(document.querySelectorAll("[data-testid='process-header'] h1, [data-testid='hero-status'] h1"));
          const hero = heroes.find((el) => {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && el.textContent && el.textContent.includes(fragment);
          });
          return !loading && Boolean(hero);
        }""",
        arg=title_fragment,
        timeout=9000,
    )


def wait_for_text(page, text: str) -> None:
    page.wait_for_function(
        """needle => document.body && document.body.textContent && document.body.textContent.includes(needle)""",
        arg=text,
        timeout=9000,
    )


def stop_proc(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def start_server(harness: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(STATUS_SERVER)],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def screenshot_empty_state(base: Path, screenshots: Path, width: int, height: int) -> int:
    empty_harness = base / "empty-harness"
    write_text(empty_harness / "events" / "all.jsonl", "")
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(empty_harness)
    proc = start_server(empty_harness, env)
    try:
        port = wait_for_server(empty_harness, proc)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.wait_for_selector("[data-testid='empty-state']", timeout=9000)
            screenshot(page, screenshots, "empty-state")
            context.close()
            browser.close()
        return port
    finally:
        stop_proc(proc)


def run(args: argparse.Namespace) -> int:
    base = Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp(prefix="solar-p0-visual-"))
    harness = base / "harness"
    screenshots = base / "screenshots" / args.label
    screenshots.mkdir(parents=True, exist_ok=True)
    bin_dir = seed_harness(harness)

    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    proc = start_server(harness, env)
    try:
        port = wait_for_server(harness, proc)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": args.width, "height": args.height}, device_scale_factor=1)
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.wait_for_selector("[data-testid='process-stream']", timeout=10000)
            page.wait_for_selector("[data-testid='results-rail']", timeout=10000)
            page.get_by_role("link", name="Build Codex-style dashboard").click()
            wait_for_hero_title(page, "Build Codex-style")
            wait_for_text(page, "3/4 nodes")
            screenshot(page, screenshots, "blocked-full-page")
            sections = {
                "process-header": "[data-testid='process-header']",
                "agent-presence": "[data-testid='agent-presence']",
                "process-stream": "[data-testid='process-stream']",
                "results-rail": "[data-testid='results-rail']",
                "deliverables": "[data-testid='deliverables-panel']",
                "usage": "[data-testid='usage-panel']",
            }
            for name, selector in sections.items():
                screenshot(page, screenshots, name, selector)
            page.locator(".new-task-button").hover()
            page.locator("[data-testid='process-step-blocked'] button").first.focus()
            screenshot(page, screenshots, "hover-focus-microstates")
            screenshot(page, screenshots, "focused-process-stream", "[data-testid='process-stream']")
            collapsed_step = page.locator("[data-testid='process-step-completed']:has(button[aria-expanded='false'])").first
            collapsed_step.screenshot(path=str(screenshots / "completed-step-collapsed.png"))
            collapsed_step.locator("button").click()
            page.wait_for_timeout(350)
            collapsed_step.screenshot(path=str(screenshots / "completed-step-expanded.png"))
            audit_before = audit(page)

            first_switch = measure_session_switch(page, "Live build sprint with active", "Live build sprint")
            wait_for_hero_title(page, "Live build sprint")
            wait_for_text(page, "3/5 nodes")
            screenshot(page, screenshots, "running-session")

            second_switch = measure_session_switch(page, "Completed report sprint", "Completed report sprint")
            wait_for_hero_title(page, "Completed report sprint")
            wait_for_text(page, "2/2 nodes")
            screenshot(page, screenshots, "complete-session")

            repeat_switch = measure_session_switch(page, "Build Codex-style dashboard", "Build Codex-style")
            wait_for_hero_title(page, "Build Codex-style")
            wait_for_text(page, "3/4 nodes")
            screenshot(page, screenshots, "revisited-session")

            audit_before["sessionSwitch"] = {
                "first_uncached": first_switch,
                "second_uncached": second_switch,
                "repeat_cached": repeat_switch,
            }
            write_json(base / f"audit-{args.label}.json", audit_before)

            page.get_by_role("link", name="Settings").click()
            page.wait_for_selector("[data-testid='settings-view']", timeout=5000)
            page.wait_for_selector("text=Lab matrix", timeout=9000)
            screenshot(page, screenshots, "settings")

            page.get_by_role("button", name="New task").first.click()
            page.get_by_placeholder("Build, investigate, verify, or produce an artifact...").fill(args.task)
            page.get_by_role("button", name="Start work").click()
            page.wait_for_selector("text=visual-intake-", timeout=8000)
            page.wait_for_timeout(800)
            screenshot(page, screenshots, "intake-interaction")
            context.close()
            browser.close()

        empty_port = screenshot_empty_state(base, screenshots, args.width, args.height)
        print(json.dumps({"output_dir": str(base), "screenshots": str(screenshots), "port": port, "empty_port": empty_port, "audit": audit_before}, indent=2))
        return 0
    finally:
        stop_proc(proc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture P0 dashboard screenshots with realistic mock data.")
    parser.add_argument("--output-dir", default="", help="Scratch directory. Defaults to /tmp/solar-p0-visual-*.")
    parser.add_argument("--label", default="run", help="Screenshot subdirectory label, e.g. before or after.")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1100)
    parser.add_argument("--task", default="Improve the dashboard visual hierarchy and preserve honest stalls.")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
