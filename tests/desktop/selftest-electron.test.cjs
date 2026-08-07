#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");
const { _electron: electron } = require("playwright");
const PYTHON =
  process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

const DESKTOP = path.resolve(__dirname, "..", "..", "desktop");
const SOURCE_HARNESS = path.resolve(DESKTOP, "..", "harness");
const ELECTRON_EXECUTABLE = process.env.SOLAR_ELECTRON_EXECUTABLE_PATH
  ? path.resolve(process.env.SOLAR_ELECTRON_EXECUTABLE_PATH)
  : "";
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "solar-desktop-selftest-"));
const tempHome = path.join(temp, "home");
const tempHarness = path.join(tempHome, ".solar", "harness");
const excluded = new Set([
  ".git",
  "node_modules",
  "__pycache__",
  "run",
  "state",
  "logs",
  "cache",
  "venvs",
  "vendor",
  "quarantine",
]);

function copyRuntimeFixture() {
  fs.mkdirSync(path.dirname(tempHarness), { recursive: true });
  fs.cpSync(SOURCE_HARNESS, tempHarness, {
    recursive: true,
    filter: (source) => {
      if (source === SOURCE_HARNESS) return true;
      const parts = path.relative(SOURCE_HARNESS, source).split(path.sep);
      return !parts.some((part) => excluded.has(part));
    },
  });
}

function waitFor(predicate, timeoutMs, label) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const result = await predicate();
        if (result) return resolve(result);
      } catch {}
      if (Date.now() - started >= timeoutMs) {
        return reject(new Error(`timed out waiting for ${label}`));
      }
      setTimeout(tick, 100);
    };
    tick();
  });
}

function healthOK(port) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: "127.0.0.1", port, path: "/healthz", timeout: 800 },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      },
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function startRealRuntime() {
  copyRuntimeFixture();
  const portFile = path.join(tempHarness, "run", "status-server.port");
  const child = spawn(
    PYTHON,
    [path.join(tempHarness, "lib", "symphony", "status-server.py")],
    {
      cwd: tempHarness,
      env: {
        ...process.env,
        HOME: tempHome,
        HARNESS_DIR: tempHarness,
        SOLAR_BIND_HOST: "127.0.0.1",
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  const port = await waitFor(async () => {
    let value = 0;
    try {
      value = Number.parseInt(fs.readFileSync(portFile, "utf8"), 10);
    } catch {}
    return value > 0 && (await healthOK(value)) ? value : 0;
  }, 15000, "real status-server health");
  return { child, url: `http://127.0.0.1:${port}/` };
}

function startBlankServer() {
  const server = http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end("<!doctype html><html><body><div id=\"root\"></div></body></html>");
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({ server, url: `http://127.0.0.1:${address.port}/` });
    });
  });
}

async function runDesktopSelftest(url, options = {}) {
  if (ELECTRON_EXECUTABLE && !fs.statSync(ELECTRON_EXECUTABLE).isFile()) {
    throw new Error(`Electron executable is not a file: ${ELECTRON_EXECUTABLE}`);
  }
  const launchOptions = {
    args: ELECTRON_EXECUTABLE ? [] : ["."],
    cwd: DESKTOP,
    env: {
      ...process.env,
      HOME: tempHome,
      HARNESS_DIR: tempHarness,
      SOLAR_BACKEND_URL: url,
      SOLAR_DESKTOP_SELFTEST: "1",
      SOLAR_DESKTOP_SELFTEST_TIMEOUT_MS: String(options.timeoutMs || 5000),
      SOLAR_DESKTOP_SHOT: options.screenshot || "",
      SOLAR_ELECTRON_DISABLE_SANDBOX: "1",
      ELECTRON_DISABLE_SECURITY_WARNINGS: "true",
    },
  };
  if (ELECTRON_EXECUTABLE) launchOptions.executablePath = ELECTRON_EXECUTABLE;
  const application = await electron.launch(launchOptions);
  const output = [];
  application.on("console", (message) => output.push(message.text()));
  const child = application.process();
  const exited = new Promise((resolve) => {
    if (child.exitCode !== null) {
      resolve({ code: child.exitCode, signal: child.signalCode });
      return;
    }
    child.once("exit", (code, signal) => resolve({ code, signal }));
  });
  let timer;
  try {
    const result = await Promise.race([
      exited,
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(new Error(`Electron selftest timed out\n${output.slice(-20).join("\n")}`)),
          20000,
        );
      }),
    ]);
    return { ...result, output: output.join("\n") };
  } finally {
    clearTimeout(timer);
    if (child.exitCode === null) await application.close().catch(() => {});
  }
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

(async () => {
  let runtime = null;
  let blank = null;
  try {
    runtime = await startRealRuntime();
    const screenshot = path.join(temp, "runtime-dashboard.png");
    const healthy = await runDesktopSelftest(runtime.url, { screenshot });
    assert.strictEqual(healthy.code, 0, healthy.output);
    assert.match(healthy.output, /SELFTEST OK/);
    assert.doesNotMatch(healthy.output, /SELFTEST FAIL/);
    assert.ok(fs.statSync(screenshot).size > 0, "selftest screenshot is empty");
    console.log("PASS  real runtime dashboard -> SELFTEST OK + nonempty screenshot");

    blank = await startBlankServer();
    const empty = await runDesktopSelftest(blank.url, { timeoutMs: 1000 });
    assert.notStrictEqual(empty.code, 0, empty.output);
    assert.match(empty.output, /SELFTEST FAIL/);
    assert.doesNotMatch(empty.output, /SELFTEST OK/);
    console.log("PASS  blank page -> nonzero + SELFTEST FAIL");

    const badShot = path.join(temp, "missing-parent", "shot.png");
    const screenshotFailure = await runDesktopSelftest(runtime.url, {
      screenshot: badShot,
    });
    assert.notStrictEqual(screenshotFailure.code, 0, screenshotFailure.output);
    assert.match(screenshotFailure.output, /screenshot_capture_failed/);
    assert.doesNotMatch(screenshotFailure.output, /SELFTEST OK/);
    console.log("PASS  unwritable screenshot -> nonzero + SELFTEST FAIL");

    console.log(
      `ELECTRON SELFTEST E2E PASS (3/3, ${ELECTRON_EXECUTABLE ? "built executable" : "development shell"})`,
    );
  } finally {
    if (blank) await new Promise((resolve) => blank.server.close(resolve));
    if (runtime) await stopChild(runtime.child);
    fs.rmSync(temp, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error("ELECTRON SELFTEST E2E FAIL:", error.stack || error);
  fs.rmSync(temp, { recursive: true, force: true });
  process.exit(1);
});
