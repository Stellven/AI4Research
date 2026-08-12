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
    const contrastSamples = await page.evaluate(() => {
      function parseColor(value) {
        const match = String(value).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
        if (!match) return null;
        return {
          rgb: match.slice(1, 4).map(Number),
          alpha: match[4] === undefined ? 1 : Number(match[4]),
        };
      }
      function luminance(rgb) {
        const channels = rgb.map((value) => {
          const normalized = value / 255;
          return normalized <= 0.04045
            ? normalized / 12.92
            : ((normalized + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
      }
      function sample(selector) {
        const element = document.querySelector(selector);
        if (!element) return { selector, present: false };
        const foreground = parseColor(getComputedStyle(element).color);
        let backgroundElement = element;
        let background = null;
        while (backgroundElement && (!background || background.alpha === 0)) {
          background = parseColor(getComputedStyle(backgroundElement).backgroundColor);
          if (background && background.alpha > 0) break;
          backgroundElement = backgroundElement.parentElement;
        }
        const ratio = foreground && background
          ? (Math.max(luminance(foreground.rgb), luminance(background.rgb)) + 0.05) /
            (Math.min(luminance(foreground.rgb), luminance(background.rgb)) + 0.05)
          : null;
        return {
          selector,
          present: true,
          foreground: foreground?.rgb || null,
          background: background?.rgb || null,
          background_source: backgroundElement?.className || backgroundElement?.tagName || null,
          ratio: ratio === null ? null : Number(ratio.toFixed(3)),
          minimum_ratio: 4.5,
          passes_aa: ratio !== null && ratio >= 4.5,
        };
      }
      return [sample(".new-task-button > span"), sample(".home-caption kbd")];
    });
    const expectedKeyboard = await page.evaluate(() => {
      const selector = [
        "a[href]",
        "button:not([disabled])",
        "textarea:not([disabled])",
        "input:not([disabled])",
        "select:not([disabled])",
        "[tabindex]:not([tabindex='-1'])",
      ].join(",");
      const visible = [...document.querySelectorAll(selector)].filter((element) => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      });
      visible.forEach((element, index) => element.setAttribute("data-solar-a11y-probe", String(index)));
      document.activeElement?.blur();
      return visible.map((element, index) => ({
        index,
        tag: element.tagName,
        text: String(element.getAttribute("aria-label") || element.textContent || "")
          .trim()
          .slice(0, 120),
      }));
    });
    const keyboardSequence = [];
    const reached = new Set();
    for (let step = 0; step < expectedKeyboard.length + 2; step += 1) {
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => {
        const active = document.activeElement;
        const probe = active?.getAttribute("data-solar-a11y-probe");
        return {
          index: probe === null || probe === undefined ? null : Number(probe),
          tag: active?.tagName || "",
          text: String(active?.getAttribute("aria-label") || active?.textContent || "")
            .trim()
            .slice(0, 120),
        };
      });
      keyboardSequence.push(focused);
      if (focused.index !== null) reached.add(focused.index);
      if (reached.size === expectedKeyboard.length) break;
    }
    await page.keyboard.press("Shift+Tab");
    const reverseFocusable = await page.evaluate(() => {
      const active = document.activeElement;
      document.querySelectorAll("[data-solar-a11y-probe]").forEach((element) =>
        element.removeAttribute("data-solar-a11y-probe"),
      );
      return Boolean(active && active !== document.body);
    });
    const keyboard = {
      focusable: reached.size > 0,
      expected_count: expectedKeyboard.length,
      reached_count: reached.size,
      all_reachable: reached.size === expectedKeyboard.length,
      reverse_focusable: reverseFocusable,
      expected: expectedKeyboard,
      sequence: keyboardSequence,
    };
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
      contrast_samples: contrastSamples,
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
        nodes: item.nodes.map((node) => ({
          target: node.target,
          failure_summary: node.failureSummary,
          any: node.any,
          all: node.all,
          none: node.none,
        })),
      })),
    };
    const evidencePath = process.env.SOLAR_ACCESSIBILITY_EVIDENCE;
    if (evidencePath) {
      fs.mkdirSync(path.dirname(path.resolve(evidencePath)), { recursive: true });
      fs.writeFileSync(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
    }
    console.log(JSON.stringify(evidence, null, 2));
    const unresolvedContrast = audit.incomplete.filter((item) => item.id === "color-contrast");
    if (contrastSamples.some((sample) => !sample.passes_aa)) {
      throw new Error("computed contrast sample did not meet WCAG AA 4.5:1");
    }
    if (unresolvedContrast.length) {
      throw new Error(`axe could not resolve ${unresolvedContrast.length} color-contrast result(s)`);
    }
    if (!keyboard.all_reachable || !keyboard.reverse_focusable) {
      throw new Error(
        `keyboard traversal reached ${keyboard.reached_count}/${keyboard.expected_count} controls`,
      );
    }
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
