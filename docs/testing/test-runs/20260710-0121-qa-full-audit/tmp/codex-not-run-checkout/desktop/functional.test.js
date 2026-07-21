// Functional e2e: drive the REAL dashboard against a REAL status-server backend and verify the
// flows actually work — not just that the shell renders. Fully ISOLATED: the backend runs on a
// temp HARNESS_DIR (+ temp SOLAR_DB) so nothing touches ~/.solar or the repo; code/static resolve
// from the repo via __file__/PYTHONPATH. We do NOT submit a real intake (the backend shells out to
// the intake CLI) — we assert the intake input is usable, and exercise Settings persistence + SSE.
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

const REPO_HARNESS = path.join(__dirname, "..", "harness");
const STATUS_SERVER = path.join(
  REPO_HARNESS,
  "lib",
  "symphony",
  "status-server.py",
);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "solar-fn-"));
for (const d of ["config", "run", "sprints", "events", "sessions", "reports"]) {
  fs.mkdirSync(path.join(TMP, d), { recursive: true });
}
const PORT_FILE = path.join(TMP, "run", "status-server.port");

function waitPort(timeoutMs) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      let port = null;
      try {
        port = parseInt(fs.readFileSync(PORT_FILE, "utf8").trim(), 10);
      } catch {}
      const retry = () =>
        Date.now() - start > timeoutMs
          ? reject(new Error("backend not healthy in time"))
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

const results = [];
const check = (name, ok) => {
  results.push(ok);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
};

(async () => {
  const backend = spawn("python3", [STATUS_SERVER], {
    cwd: TMP,
    env: {
      ...process.env,
      HARNESS_DIR: TMP,
      PYTHONPATH: path.join(REPO_HARNESS, "lib"),
      SOLAR_BIND_HOST: "127.0.0.1",
      SOLAR_DB: path.join(TMP, "solar.db"),
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  let stderr = "";
  backend.stderr.on("data", (d) => (stderr += String(d)));
  let browser;
  try {
    const port = await waitPort(20000);
    const base = `http://127.0.0.1:${port}`;
    browser = await chromium.launch({
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 920 },
    });
    // Catch uncaught JS exceptions (a crash / blank screen) and note console.error output.
    const pageErrors = [];
    const consoleErrors = [];
    page.on("pageerror", (e) =>
      pageErrors.push(String(e.message).slice(0, 200)),
    );
    page.on("console", (m) => {
      if (m.type() === "error")
        consoleErrors.push(String(m.text()).slice(0, 160));
    });
    await page.goto(`${base}/`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForTimeout(1500);

    // T1: the real dashboard shell renders.
    const body = await page.evaluate(() => document.body.innerText || "");
    check(
      "dashboard shell renders (intake + Settings)",
      body.includes("What do you want done?") && body.includes("Settings"),
    );

    // T2: intake input is present + editable (we do NOT submit — that shells out to the intake CLI).
    const intakeEditable = await page.evaluate(() => {
      const el = document.querySelector("textarea, input[type='text']");
      return !!el && !el.disabled;
    });
    check("intake input present + editable", intakeEditable);

    // T3: Settings persistence round-trip through the REAL backend (same-origin fetch from the page).
    const tok = await page.evaluate(() => window.__SOLAR_TOKEN__ || "");
    const hdr = tok ? { "X-Solar-Token": tok } : {};
    const post = await page.evaluate(
      async ({ b, h }) => {
        const r = await fetch(`${b}/settings`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...h },
          body: JSON.stringify({
            role_models: {},
            api_keys: {},
            runtime: "codex",
            codex: { search: false, effort: "high" },
          }),
        });
        return { status: r.status, json: await r.json().catch(() => ({})) };
      },
      { b: base, h: hdr },
    );
    check(
      "POST /settings ok (runtime=codex, search=false, effort=high)",
      post.status === 200 && post.json.ok === true,
    );

    const get = await page.evaluate(
      async ({ b, h }) => (await fetch(`${b}/settings`, { headers: h })).json(),
      { b: base, h: hdr },
    );
    check(
      "GET /settings persisted codex (search=false, effort=high)",
      get?.codex?.search === false && String(get?.codex?.effort) === "high",
    );
    check(
      "GET /settings persisted runtime=codex",
      get?.runtime?.value === "codex",
    );

    // T3b: reload → the Settings UI reflects the persisted state (full UI round-trip).
    await page.goto(`${base}/`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForTimeout(800);
    // The app uses HASH routing (NavLink renders href="#/settings"), so click the link rather than
    // navigating directly (direct nav would hit the backend GET /settings JSON route). Then wait for
    // SettingsView to fetch /settings and render the codex controls (runtime persisted = codex).
    await page
      .locator('a[href$="/settings"]')
      .first()
      .click()
      .catch(() => {});
    await page.waitForTimeout(800);
    // The codex controls live in the "Default crew" settings section — switch to it.
    await page
      .getByRole("button", { name: "Default crew" })
      .click()
      .catch(() => {});
    await page
      .waitForSelector(".settings-codex-options", { timeout: 8000 })
      .catch(() => {});
    const reflect = await page.evaluate(() => {
      const cb = document.querySelector(
        ".settings-codex-toggle input[type='checkbox']",
      );
      const sel = document.querySelector(".settings-codex-effort select");
      return {
        hasControls: !!cb && !!sel,
        searchUnchecked: cb ? cb.checked === false : null,
        effort: sel ? sel.value : null,
      };
    });
    check(
      "Settings UI shows codex controls after reload (runtime persisted)",
      reflect.hasControls === true,
    );
    check(
      "Settings UI reflects persisted values (search off, effort=high)",
      reflect.searchUnchecked === true && reflect.effort === "high",
    );

    // T5: the SSE event stream opens end-to-end against the real backend.
    const sseOk = await page.evaluate(
      ({ b, t }) =>
        new Promise((resolve) => {
          try {
            const url =
              `${b}/events?stream=1&limit=5` +
              (t ? `&token=${encodeURIComponent(t)}` : "");
            const es = new EventSource(url);
            const timer = setTimeout(() => {
              es.close();
              resolve(false);
            }, 8000);
            es.onopen = () => {
              clearTimeout(timer);
              es.close();
              resolve(true);
            };
          } catch {
            resolve(false);
          }
        }),
      { b: base, t: tok },
    );
    check("SSE /events stream opens", sseOk === true);

    // T6: no uncaught JS exceptions during the whole run (catches the crash / blank-screen class).
    // console.error output is noted but not failed on (apps log benign errors).
    if (consoleErrors.length) {
      console.log(
        `  (console.error noted x${consoleErrors.length}; not failing)`,
      );
    }
    if (pageErrors.length) {
      console.log("  page errors:\n   " + pageErrors.slice(0, 5).join("\n   "));
    }
    check(
      "no uncaught page errors (no JS crash / blank screen)",
      pageErrors.length === 0,
    );
  } catch (e) {
    console.log("FUNCTIONAL ERROR:", e.message);
    if (stderr)
      console.log(
        "backend stderr (tail):",
        stderr.split("\n").slice(-6).join("\n"),
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

  const passed = results.filter(Boolean).length;
  console.log(`\nFUNCTIONAL: ${passed}/${results.length} passed`);
  process.exit(passed === results.length && results.length > 0 ? 0 : 1);
})();
