from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


SELECTOR = (
    "tests/journeys/phase22/code/test_j19_real_gui_dashboard.py::"
    "test_p22_j19_real_gui_dashboard"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _tail(text: str, limit: int = 2400) -> str:
    return (text or "")[-limit:]


def _redact_status_token(text: str) -> str:
    return re.sub(r'window\.__SOLAR_TOKEN__="[^"]+"', 'window.__SOLAR_TOKEN__="[redacted]"', text or "")


def _http_text(url: str, *, token: str | None = None) -> dict[str, Any]:
    headers = {"X-Solar-Token": token} if token else {}
    try:
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            body = _redact_status_token(response.read().decode("utf-8", "replace"))
            return {"status": response.status, "content_type": response.headers.get_content_type(), "body_prefix": body[:500]}
    except HTTPError as exc:
        return {
            "status": exc.code,
            "content_type": exc.headers.get_content_type(),
            "error": str(exc),
            "body_prefix": exc.read().decode("utf-8", "replace")[:500],
        }
    except URLError as exc:
        return {"status": 0, "content_type": "", "error": str(exc), "body_prefix": ""}


def _wait_for_port(port_file: Path, deadline_seconds: int = 25) -> str:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if port_file.exists() and port_file.read_text(encoding="utf-8").strip():
            return port_file.read_text(encoding="utf-8").strip()
        time.sleep(0.25)
    return ""


def _wait_for_health(base_url: str, *, token: str | None, deadline_seconds: int = 20) -> bool:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        health = _http_text(f"{base_url}/healthz", token=token)
        if health.get("status") == 200 and health.get("body_prefix") == "ok":
            return True
        time.sleep(0.3)
    return False


def _node_script() -> str:
    return r"""
const fs = require("fs");
const path = require("path");

const playwrightRoot = process.env.PHASE22_PLAYWRIGHT_NODE_MODULES;
const chromePath = process.env.PHASE22_CHROME_EXECUTABLE;
const resultPath = process.env.PHASE22_GUI_RESULT;
const screenshotPath = process.env.PHASE22_GUI_SCREENSHOT;
const profilePath = process.env.PHASE22_GUI_PROFILE;
const base = process.env.PHASE22_STATUS_BASE_URL;
const token = process.env.PHASE22_STATUS_TOKEN || "";
const progress = [];

function loadPlaywright() {
  if (!playwrightRoot) {
    return require("playwright");
  }
  return require(require.resolve("playwright", { paths: [playwrightRoot] }));
}

function writeProgress(payload) {
  fs.mkdirSync(path.dirname(resultPath), { recursive: true });
  fs.writeFileSync(resultPath, JSON.stringify({
    ...payload,
    progress,
    screenshotPath,
    chromeExecutable: chromePath || "",
    playwrightRoot: playwrightRoot || "",
  }, null, 2) + "\n");
}

(async () => {
  const watchdog = setTimeout(() => {
    writeProgress({ error: "browser probe watchdog timeout", assertions: {} });
    process.exit(2);
  }, 75000);
  const { chromium } = loadPlaywright();
  progress.push("playwright-loaded");
  const context = await chromium.launchPersistentContext(profilePath, {
    headless: true,
    executablePath: chromePath || undefined,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  progress.push("browser-launched");
  const page = context.pages()[0] || await context.newPage();
  await page.setViewportSize({ width: 1440, height: 920 });
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", error => pageErrors.push(String(error.message || error).slice(0, 300)));
  page.on("console", message => {
    if (message.type() === "error") consoleErrors.push(String(message.text()).slice(0, 300));
  });

  const assertions = {};
  const observations = {};
  try {
    progress.push("goto-root");
    await page.goto(`${base}/`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(1500);
    const body = await page.evaluate(() => document.body.innerText || "");
    observations.initialBodyPrefix = body.slice(0, 1200);
    assertions.dashboard_shell_rendered = body.includes("What do you want done?") && body.includes("Settings");
    writeProgress({ assertions, observations, pageErrors, consoleErrors });

    progress.push("edit-intake");
    const editable = await page.evaluate(() => {
      const el = document.querySelector("textarea, input[type='text']");
      if (!el) return { present: false, editable: false, value: "" };
      el.focus();
      el.value = "Phase 22 GUI journey probe";
      el.dispatchEvent(new Event("input", { bubbles: true }));
      return { present: true, editable: !el.disabled, value: el.value };
    });
    observations.intakeEditable = editable;
    assertions.intake_input_interacted = editable.present === true && editable.editable === true && editable.value.includes("Phase 22");
    writeProgress({ assertions, observations, pageErrors, consoleErrors });

    progress.push("post-settings");
    const headers = token ? { "X-Solar-Token": token } : {};
    const postSettings = await page.evaluate(async ({ b, h }) => {
      const response = await fetch(`${b}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...h },
        body: JSON.stringify({
          role_models: {},
          api_keys: {},
          runtime: "codex",
          codex: { search: false, effort: "high" },
        }),
      });
      return { status: response.status, json: await response.json().catch(() => ({})) };
    }, { b: base, h: headers });
    observations.postSettings = postSettings;
    assertions.settings_post_succeeded = postSettings.status === 200 && postSettings.json && postSettings.json.ok === true;
    writeProgress({ assertions, observations, pageErrors, consoleErrors });

    progress.push("goto-settings");
    await page.goto(`${base}/`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(800);
    await page.locator('a[href$="/settings"]').first().click({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(800);
    await page.getByRole("button", { name: "Default crew" }).click({ timeout: 5000 }).catch(() => {});
    await page.waitForSelector(".settings-codex-options", { timeout: 8000 }).catch(() => {});
    const reflect = await page.evaluate(() => {
      const cb = document.querySelector(".settings-codex-toggle input[type='checkbox']");
      const sel = document.querySelector(".settings-codex-effort select");
      return {
        hasControls: !!cb && !!sel,
        searchUnchecked: cb ? cb.checked === false : null,
        effort: sel ? sel.value : null,
        bodyPrefix: (document.body.innerText || "").slice(0, 1200),
      };
    });
    observations.settingsUi = reflect;
    assertions.settings_ui_interacted = reflect.hasControls === true;
    assertions.settings_ui_reflected_persistence = reflect.searchUnchecked === true && reflect.effort === "high";
    writeProgress({ assertions, observations, pageErrors, consoleErrors });

    progress.push("screenshot");
    await page.screenshot({ path: screenshotPath, fullPage: true, animations: "disabled", timeout: 10000 });
    assertions.screenshot_nonempty = fs.existsSync(screenshotPath) && fs.statSync(screenshotPath).size > 0;
    assertions.no_uncaught_page_errors = pageErrors.length === 0;
    progress.push("done");
  } finally {
    await Promise.race([
      context.close().catch(() => {}),
      new Promise(resolve => setTimeout(resolve, 3000)),
    ]);
    clearTimeout(watchdog);
  }

  writeProgress({
    baseUrl: base,
    assertions,
    observations,
    pageErrors,
    consoleErrors,
  });

  const ok = Object.values(assertions).every(Boolean);
  process.exit(ok ? 0 : 1);
})().catch(error => {
  fs.mkdirSync(path.dirname(resultPath), { recursive: true });
  fs.writeFileSync(resultPath, JSON.stringify({
    error: String(error.stack || error),
    assertions: {},
  }, null, 2) + "\n");
  process.exit(1);
});
"""


def test_p22_j19_real_gui_dashboard(repo_root: Path, tmp_path: Path) -> None:
    node_bin = Path(os.environ.get("PHASE22_NODE_BIN", ""))
    if not node_bin.is_file():
        pytest.skip("PHASE22_NODE_BIN must point to a working Node.js executable for the GUI journey.")

    playwright_root = os.environ.get("PHASE22_PLAYWRIGHT_NODE_MODULES", "")
    if playwright_root and not Path(playwright_root).is_dir():
        pytest.skip("PHASE22_PLAYWRIGHT_NODE_MODULES does not exist.")

    chrome_path = Path(os.environ.get("PHASE22_CHROME_EXECUTABLE", ""))
    if chrome_path and not chrome_path.is_file():
        pytest.skip("PHASE22_CHROME_EXECUTABLE is set but not a file.")

    status_server = repo_root / "harness" / "lib" / "symphony" / "status-server.py"
    if not status_server.is_file():
        pytest.skip("status-server.py is required for the real GUI dashboard journey.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"p22-j19-real-gui-dashboard-{stamp}-{os.getpid()}"
    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    sandbox_home = tmp_path / "home"
    harness_dir = tmp_path / "harness"
    for name in ["config", "run", "sprints", "events", "sessions", "reports", "state"]:
        (harness_dir / name).mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(sandbox_home),
            "USERPROFILE": str(sandbox_home),
            "HARNESS_DIR": str(harness_dir),
            "PYTHONPATH": str(repo_root / "harness" / "lib"),
            "SOLAR_BIND_HOST": "127.0.0.1",
            "SOLAR_DB": str(harness_dir / "solar.db"),
            "SOLAR_NO_MCP": "true",
            "SOLAR_NO_HOOKS": "true",
        }
    )

    started_at = _utc_now()
    backend_stdout = artifact_dir / "status-server-stdout.txt"
    backend_stderr = artifact_dir / "status-server-stderr.txt"
    stdout_handle = backend_stdout.open("w", encoding="utf-8", errors="replace")
    stderr_handle = backend_stderr.open("w", encoding="utf-8", errors="replace")
    backend = subprocess.Popen(
        [sys.executable, str(status_server)],
        cwd=harness_dir,
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
    )

    commands: list[dict[str, Any]] = []
    http_checks: dict[str, Any] = {}
    browser_result: dict[str, Any] = {}
    script_path = artifact_dir / "run-gui-probe.cjs"
    script_path.write_text(_node_script(), encoding="utf-8")
    browser_result_path = artifact_dir / "browser-result.json"
    screenshot_path = artifact_dir / "dashboard-settings.png"
    browser_profile = Path(tempfile.mkdtemp(prefix=f"{run_id}-chrome-"))

    try:
        port = _wait_for_port(harness_dir / "run" / "status-server.port")
        token_file = harness_dir / "run" / "status-server.token"
        token = token_file.read_text(encoding="utf-8").strip() if token_file.exists() else ""
        base = f"http://127.0.0.1:{port}" if port else ""
        health_ok = bool(base and _wait_for_health(base, token=token or None))
        if base:
            http_checks["root_before_browser"] = _http_text(f"{base}/", token=token or None)
            http_checks["healthz"] = _http_text(f"{base}/healthz", token=token or None)

        browser_env = os.environ.copy()
        browser_env.update(
            {
                "PHASE22_STATUS_BASE_URL": base,
                "PHASE22_STATUS_TOKEN": token,
                "PHASE22_GUI_RESULT": str(browser_result_path),
                "PHASE22_GUI_SCREENSHOT": str(screenshot_path),
                "PHASE22_GUI_PROFILE": str(browser_profile),
                "PHASE22_PLAYWRIGHT_NODE_MODULES": playwright_root,
                "PHASE22_CHROME_EXECUTABLE": str(chrome_path) if chrome_path else "",
            }
        )
        started = time.monotonic()
        proc = subprocess.run(
            [str(node_bin), str(script_path)],
            cwd=repo_root,
            env=browser_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
            check=False,
        )
        commands.append(
            {
                "label": "headless-chrome-dashboard-probe",
                "argv": [str(node_bin), str(script_path)],
                "cwd": str(repo_root),
                "exit_code": proc.returncode,
                "duration_seconds": round(time.monotonic() - started, 3),
                "stdout_tail": _tail(proc.stdout),
                "stderr_tail": _tail(proc.stderr),
            }
        )
        if browser_result_path.exists():
            browser_result = json.loads(browser_result_path.read_text(encoding="utf-8"))
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
            backend.wait(timeout=5)
        stdout_handle.close()
        stderr_handle.close()

    assertions = browser_result.get("assertions", {}) if isinstance(browser_result, dict) else {}
    browser_ok = bool(assertions) and all(assertions.values())
    screenshot_ok = screenshot_path.exists() and screenshot_path.stat().st_size > 0
    health_ok = http_checks.get("healthz", {}).get("status") == 200 and http_checks.get("healthz", {}).get("body_prefix") == "ok"
    root_ok = http_checks.get("root_before_browser", {}).get("status") == 200

    evidence = {
        "schema_version": "phase22.j19.real_gui_dashboard.v1",
        "journey_id": "P22-J19",
        "run_id": run_id,
        "selector": SELECTOR,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "platform": platform.platform(),
        "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "sandbox": {"home": str(sandbox_home), "harness_dir": str(harness_dir)},
        "commands": commands,
        "http_checks": http_checks,
        "browser_result": browser_result,
        "assertions": {
            "status_server_health_ok": health_ok,
            "dashboard_root_served": root_ok,
            "headless_chrome_probe_ok": browser_ok,
            "screenshot_nonempty": screenshot_ok,
        },
        "observed_l2": [
            {
                "category": "Vertical",
                "level_2_feature": "GUI",
                "status": "PASS_WITH_KNOWN_LIMITATIONS",
                "assertion_name": "j19_real_dashboard_browser_settings_interaction",
                "evidence_path": "journey-result.json",
                "known_limitations": [
                    "Validated the production web/status dashboard in installed Chrome headless against a local sandbox status-server; did not cover packaged Electron windows, manual attach, multi-monitor display behavior, accessibility pass, or account/channel integrations."
                ],
            }
        ],
        "status": "PASS_WITH_KNOWN_LIMITATIONS",
    }
    result_path = _write_json(run_dir / "journey-result.json", evidence)
    _write_json(artifact_dir / "commands.json", commands)
    _write_json(artifact_dir / "http-checks.json", http_checks)

    assert health_ok and root_ok and browser_ok and screenshot_ok, f"P22-J19 GUI journey failed; evidence: {result_path}"
