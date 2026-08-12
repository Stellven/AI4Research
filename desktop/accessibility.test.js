#!/usr/bin/env node
"use strict";

// Automated WCAG smoke against the real dashboard and status server. This is
// intentionally a release gate for serious/critical issues, not a substitute
// for manual screen-reader or multi-monitor testing.
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const harnessSource = path.resolve(__dirname, "..", "harness");
const statusServer = path.join(harnessSource, "lib", "symphony", "status-server.py");
const axeSource = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "solar-a11y-"));
for (const name of ["config", "run", "sprints", "events", "sessions", "reports"]) {
  fs.mkdirSync(path.join(temp, name), { recursive: true });
}

function healthOK(port) {
  return new Promise((resolve) => {
    const request = http.get(
      { host: "127.0.0.1", port, path: "/healthz", timeout: 800 },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      },
    );
    request.on("error", () => resolve(false));
    request.on("timeout", () => {
      request.destroy();
      resolve(false);
    });
  });
}

async function waitForPort(file, timeoutMs = 20000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    let port = 0;
    try {
      port = Number.parseInt(fs.readFileSync(file, "utf8"), 10);
    } catch {}
    if (port > 0 && (await healthOK(port))) return port;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("status server did not become healthy");
}

async function stop(child) {
  if (!child || child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

(async () => {
  const portFile = path.join(temp, "run", "status-server.port");
  const backend = spawn("python3", [statusServer], {
    cwd: temp,
    env: {
      ...process.env,
      HARNESS_DIR: temp,
      PYTHONPATH: path.join(harnessSource, "lib"),
      SOLAR_BIND_HOST: "127.0.0.1",
      SOLAR_DB: path.join(temp, "solar.db"),
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  let browser;
  try {
    const port = await waitForPort(portFile);
    browser = await chromium.launch({
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    });
    const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
    await page.goto(`http://127.0.0.1:${port}/`, {
      // The production dashboard keeps an SSE connection open, so networkidle
      // is not a valid readiness signal.
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    await page.getByText("What do you want done?").waitFor({ timeout: 20000 });
    await page.addScriptTag({ content: axeSource });
    const audit = await page.evaluate(async () =>
      window.axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        },
        resultTypes: ["violations", "incomplete"],
      }),
    );
    await page.keyboard.press("Tab");
    const keyboard = await page.evaluate(() => {
      const active = document.activeElement;
      return {
        tag: active?.tagName || "",
        text: String(active?.getAttribute("aria-label") || active?.textContent || "")
          .trim()
          .slice(0, 120),
        focusable: Boolean(active && active !== document.body),
      };
    });
    const blocking = audit.violations.filter((item) =>
      ["critical", "serious"].includes(item.impact),
    );
    const evidence = {
      tool: `axe-core ${require("axe-core/package.json").version}`,
      standard: ["WCAG 2.0 A", "WCAG 2.0 AA", "WCAG 2.1 A", "WCAG 2.1 AA"],
      url: `http://127.0.0.1:${port}/`,
      viewport: { width: 1440, height: 920 },
      blocking_violation_count: blocking.length,
      violation_count: audit.violations.length,
      incomplete_count: audit.incomplete.length,
      keyboard,
      violations: audit.violations.map((item) => ({
        id: item.id,
        impact: item.impact,
        description: item.description,
        nodes: item.nodes.map((node) => node.target),
      })),
      incomplete: audit.incomplete.map((item) => ({
        id: item.id,
        impact: item.impact,
        description: item.description,
        nodes: item.nodes.map((node) => node.target),
      })),
    };
    const evidencePath = process.env.SOLAR_ACCESSIBILITY_EVIDENCE;
    if (evidencePath) {
      fs.mkdirSync(path.dirname(path.resolve(evidencePath)), { recursive: true });
      fs.writeFileSync(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
    }
    console.log(JSON.stringify(evidence, null, 2));
    if (!keyboard.focusable) throw new Error("Tab did not reach a focusable control");
    if (blocking.length) {
      throw new Error(`axe found ${blocking.length} serious/critical WCAG violation(s)`);
    }
    console.log("ACCESSIBILITY AUDIT PASS (axe serious/critical 0 + keyboard focus reachable)");
  } finally {
    if (browser) await browser.close().catch(() => {});
    await stop(backend);
    fs.rmSync(temp, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error("ACCESSIBILITY AUDIT FAIL:", error.stack || error);
  fs.rmSync(temp, { recursive: true, force: true });
  process.exit(1);
});
