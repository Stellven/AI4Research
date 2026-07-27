// frontend-scenarios.test.js — headless-browser scenarios that DISCRIMINATE the session-isolation
// frontend fixes from the baseline. Self-contained: starts the given ref's REAL status-server
// (which serves that ref's just-built static/p0-app bundle), drives it with real chromium, and
// prints machine-parseable `RESULT <key> <PASS|FAIL>` lines for the differential runner.
//
// Driven by env so scripts/compare-webapp-frontend.sh can point it at any materialized ref:
//   SOLAR_STATUS_SERVER  path to that ref's harness/lib/symphony/status-server.py   (required)
//   SOLAR_HARNESS_LIB    that ref's harness/lib (PYTHONPATH)                          (required)
//   SOLAR_REF_LABEL      label for logs                                              (optional)
//
// Scenarios (no backend seeding needed — the session topbar renders on any route):
//   provenance-chips    the transparency provenance chips render on a session view   (X1/X2; Codex)
//   freshness-visible   the view surfaces data freshness / scope (updated / events: / status:)
//   session-no-crash    navigating to a session route throws no uncaught JS error    (router/SSE smoke)
const path = require("path");
const { chromium } = require(
  path.join(__dirname, "node_modules", "playwright"),
);
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const http = require("http");
const PYTHON =
  process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

const STATUS_SERVER = process.env.SOLAR_STATUS_SERVER;
const HARNESS_LIB = process.env.SOLAR_HARNESS_LIB;
const LABEL = process.env.SOLAR_REF_LABEL || "ref";
if (!STATUS_SERVER || !HARNESS_LIB) {
  console.error("need SOLAR_STATUS_SERVER + SOLAR_HARNESS_LIB");
  process.exit(2);
}

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "solar-fe-"));
for (const d of ["config", "run", "sprints", "events", "sessions", "reports"]) {
  fs.mkdirSync(path.join(TMP, d), { recursive: true });
}
const PORT_FILE = path.join(TMP, "run", "status-server.port");

function waitPort(ms) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      let port = null;
      try {
        port = parseInt(fs.readFileSync(PORT_FILE, "utf8").trim(), 10);
      } catch {}
      const retry = () =>
        Date.now() - start > ms
          ? reject(new Error("backend not healthy"))
          : setTimeout(tick, 250);
      if (port) {
        const req = http.get(
          { host: "127.0.0.1", port, path: "/healthz", timeout: 1500 },
          (r) => {
            r.resume();
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

const result = (key, ok) =>
  console.log(`RESULT ${key} ${ok ? "PASS" : "FAIL"}`);

(async () => {
  const backend = spawn(PYTHON, [STATUS_SERVER], {
    cwd: TMP,
    env: {
      ...process.env,
      HARNESS_DIR: TMP,
      PYTHONPATH: HARNESS_LIB,
      SOLAR_BIND_HOST: "127.0.0.1",
      SOLAR_DB: path.join(TMP, "solar.db"),
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  let stderr = "";
  backend.stderr.on("data", (d) => (stderr += String(d)));
  let browser,
    ok = { prov: false, fresh: false, nocrash: false };
  try {
    const port = await waitPort(20000);
    const base = `http://127.0.0.1:${port}`;
    browser = await chromium.launch({
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 920 },
    });
    const pageErrors = [];
    page.on("pageerror", (e) =>
      pageErrors.push(String(e.message).slice(0, 200)),
    );
    await page.goto(`${base}/#/sessions/diff-probe`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForTimeout(2500);

    const probe = await page.evaluate(() => {
      const txt = document.body.innerText || "";
      return {
        prov:
          !!document.querySelector(".topbar-provenance") ||
          !!document.querySelector(".provenance-chip"),
        fresh:
          /updated\s|events:\s|status:\s|scoped|cached|live|retrying/i.test(
            txt,
          ),
        rendered: txt.length > 50,
      };
    });
    ok.prov = probe.prov;
    ok.fresh = probe.fresh;
    ok.nocrash = pageErrors.length === 0 && probe.rendered;
    if (pageErrors.length)
      console.log("  pageerrors: " + pageErrors.slice(0, 3).join(" | "));
  } catch (e) {
    console.log(`  [${LABEL}] ERROR ${e.message}`);
    if (stderr)
      console.log(
        "  backend stderr: " + stderr.split("\n").slice(-4).join(" "),
      );
  } finally {
    if (browser) await browser.close().catch(() => {});
    try {
      backend.kill();
    } catch {}
    try {
      fs.rmSync(TMP, { recursive: true, force: true });
    } catch {}
  }
  result("provenance-chips", ok.prov);
  result("freshness-visible", ok.fresh);
  result("session-no-crash", ok.nocrash);
  process.exit(ok.prov && ok.fresh && ok.nocrash ? 0 : 1);
})();
