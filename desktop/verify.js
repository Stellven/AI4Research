// F4 visual-verify gate: spawn a fresh status-server backend on an isolated
// HARNESS_DIR, render the dashboard in chromium, assert the key UI text, save a
// screenshot, exit 0 (PASS) / 1 (FAIL). One command, deterministic, no live runtime.
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");
const PYTHON =
  process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

const HARNESS_DIR =
  process.env.HARNESS_DIR || path.join(__dirname, "..", "harness");
const STATUS_SERVER = path.join(
  HARNESS_DIR,
  "lib",
  "symphony",
  "status-server.py",
);
const PORT_FILE = path.join(HARNESS_DIR, "run", "status-server.port");
const OUT = process.env.OUT || "gate-dashboard.png";
const MUST_CONTAIN = ["What do you want done?", "Settings"];

function waitHealthy(timeoutMs) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      let port = null;
      try {
        port = parseInt(fs.readFileSync(PORT_FILE, "utf8").trim(), 10);
      } catch {}
      const retry = () =>
        Date.now() - start > timeoutMs
          ? reject(new Error("not healthy in time"))
          : setTimeout(tick, 300);
      if (port) {
        const req = http.get(
          { host: "127.0.0.1", port, path: "/healthz", timeout: 1500 },
          (res) => {
            res.resume();
            resolve(port);
          },
        );
        req.on("error", retry);
        req.on("timeout", () => {
          req.destroy();
          retry();
        });
      } else retry();
    };
    tick();
  });
}

(async () => {
  if (!fs.existsSync(STATUS_SERVER)) {
    console.log("GATE FAIL: status-server not found at", STATUS_SERVER);
    process.exit(1);
  }
  try {
    fs.unlinkSync(PORT_FILE);
  } catch {}
  fs.mkdirSync(path.dirname(PORT_FILE), { recursive: true });
  const backend = spawn(PYTHON, [STATUS_SERVER], {
    cwd: HARNESS_DIR,
    env: { ...process.env, HARNESS_DIR },
    stdio: ["ignore", "ignore", "ignore"],
  });

  let pass = false;
  let found = [];
  let url = "";
  try {
    const port = await waitHealthy(15000);
    url = `http://127.0.0.1:${port}/`;
    const browser = await chromium.launch({
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 920 },
    });
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForTimeout(2500);
    const text = await page.evaluate(() => document.body.innerText || "");
    found = MUST_CONTAIN.filter((s) => text.includes(s));
    await page
      .screenshot({ path: OUT, timeout: 10000, animations: "disabled" })
      .catch(() => {});
    await browser.close();
    pass = found.length === MUST_CONTAIN.length;
  } catch (e) {
    console.log("GATE FAIL:", e.message);
  } finally {
    try {
      backend.kill();
    } catch {}
  }

  console.log(
    `backend=${url || "(none)"} asserted=[${found.join(", ")}] of [${MUST_CONTAIN.join(", ")}] screenshot=${OUT}`,
  );
  console.log(pass ? "GATE PASS" : "GATE FAIL");
  process.exit(pass ? 0 : 1);
})();
