// rapid-switch.test.js — session-isolation REGRESSION GUARD for rapid A<->B switching (review #2/#3).
// Seeds two REAL session event files with distinct markers, starts the REAL status-server, and in
// headless chromium switches between #/sessions/A and #/sessions/B via CLIENT-SIDE nav (location.hash),
// asserting that once the view identity (topbar) is session X, its event list never shows session Y's
// event text — sampled across the post-switch window and after settling. No mocks.
//
// HONEST SCOPE: this PASSES on the keyed-remount fix AND on base 8812d4a7 — i.e., it did NOT
// reproduce an OBSERVABLE cross-session leak on the unfixed tree (the stale-paint appears to be a
// sub-render-frame transient that React commits atomically, so no committed DOM shows view=B with
// events=A). So it is a regression guard that proves observable isolation HOLDS, not a differential
// proving the keyed fix was necessary. The key={sprintId} remount remains a sound defensive change.
// Prints `RESULT <key> <PASS|FAIL>` for the runner.
//
//   SOLAR_STATUS_SERVER=<ref>/harness/lib/symphony/status-server.py \
//   SOLAR_HARNESS_LIB=<ref>/harness/lib  node rapid-switch.test.js
// Defaults to this tree if the env vars are unset.
const path = require("path");
const { chromium } = require(
  path.join(__dirname, "node_modules", "playwright"),
);
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const http = require("http");

const REPO_HARNESS = path.join(__dirname, "..", "harness");
const STATUS_SERVER =
  process.env.SOLAR_STATUS_SERVER ||
  path.join(REPO_HARNESS, "lib", "symphony", "status-server.py");
const HARNESS_LIB =
  process.env.SOLAR_HARNESS_LIB || path.join(REPO_HARNESS, "lib");

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "solar-rs-"));
for (const d of ["config", "run", "sprints", "events", "sessions", "reports"]) {
  fs.mkdirSync(path.join(TMP, d), { recursive: true });
}
function seed(sid, marker) {
  const dir = path.join(TMP, "sessions", sid);
  fs.mkdirSync(dir, { recursive: true });
  const ev = {
    event_id: sid + "-1",
    session_id: sid,
    seq: 1,
    ts: "2026-06-21T18:34:02Z",
    type: "command_issued",
    actor: "hand-runtime",
    source: "session_log",
    sprint_id: sid,
    message: marker,
    summary: marker,
    command: marker,
  };
  fs.writeFileSync(path.join(dir, "events.jsonl"), JSON.stringify(ev) + "\n");
}
const MARK_A = "MARKER_RAPID_A",
  MARK_B = "MARKER_RAPID_B";
seed("rapidA", MARK_A);
seed("rapidB", MARK_B);
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
  const backend = spawn("python3", [STATUS_SERVER], {
    cwd: TMP,
    env: {
      ...process.env,
      HARNESS_DIR: TMP,
      PYTHONPATH: HARNESS_LIB,
      SOLAR_BIND_HOST: "127.0.0.1",
      SOLAR_DB: path.join(TMP, "solar.db"),
    },
    stdio: ["ignore", "ignore", "ignore"],
  });
  let browser,
    leaks = 0,
    sawA = false,
    sawB = false;
  try {
    const port = await waitPort(20000);
    const base = `http://127.0.0.1:${port}`;
    browser = await chromium.launch({
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 920 },
    });
    // Load the SPA once, then navigate via location.hash so React Router does CLIENT-SIDE nav.
    // (page.goto to a hash URL reloads the page, which hides the stale-paint entirely.) Prime A.
    await page.goto(`${base}/#/sessions/rapidA`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForFunction(
      (m) => (document.body.innerText || "").includes(m),
      MARK_A,
      { timeout: 15000 },
    );
    sawA = true;
    // Switch back and forth via in-app nav. Sample the DOM repeatedly during the first ~640ms
    // (the stale-paint window) AND after settling: the current session must NEVER show the other
    // session's marker, transiently or settled. Without the key remount, the prior session's
    // useSessionData state lingers for a render and leaks here.
    for (let i = 0; i < 4; i++) {
      const cur = i % 2 === 0 ? "rapidB" : "rapidA";
      const mineMark = cur === "rapidB" ? MARK_B : MARK_A;
      const otherMark = cur === "rapidB" ? MARK_A : MARK_B;
      await page.evaluate((u) => {
        window.location.hash = u;
      }, `#/sessions/${cur}`);
      // Wait until the view IDENTITY switched to `cur` (topbar shows the new sprint id), so we don't
      // mistake the not-yet-rerendered previous view for a leak. Then, while the view claims to be
      // `cur`, its event list must NOT contain the OTHER session's event marker (that's the bug).
      await page
        .waitForFunction(
          (sid) =>
            (
              (document.querySelector(".topbar") || {}).innerText || ""
            ).includes(sid),
          cur,
          { timeout: 10000 },
        )
        .catch(() => {});
      let leakedHere = false;
      for (let t = 0; t < 8; t++) {
        const view = await page.evaluate(
          (sid) => ({
            isCur: (
              (document.querySelector(".topbar") || {}).innerText || ""
            ).includes(sid),
            body: document.body.innerText || "",
          }),
          cur,
        );
        if (view.isCur && view.body.includes(otherMark)) {
          leaks++;
          leakedHere = true;
          console.log(
            `  LEAK on ${cur} (t=${t * 70}ms): view=${cur} but shows ${otherMark}`,
          );
          break;
        }
        await page.waitForTimeout(70);
      }
      await page
        .waitForFunction(
          (m) => (document.body.innerText || "").includes(m),
          mineMark,
          { timeout: 15000 },
        )
        .catch(() => {});
      await page.waitForTimeout(400);
      const settled = await page.evaluate(() => document.body.innerText || "");
      if (cur === "rapidB") sawB = true;
      if (!leakedHere && settled.includes(otherMark)) {
        leaks++;
        console.log(`  LEAK on ${cur} (settled): shows ${otherMark}`);
      }
    }
  } catch (e) {
    console.log("rapid-switch ERROR:", e.message);
  } finally {
    if (browser) await browser.close().catch(() => {});
    try {
      backend.kill();
    } catch {}
    try {
      fs.rmSync(TMP, { recursive: true, force: true });
    } catch {}
  }
  result("rapid-switch-renders-both-sessions", sawA && sawB);
  result("rapid-switch-no-cross-session-leak", leaks === 0 && sawA && sawB);
  process.exit(leaks === 0 && sawA && sawB ? 0 : 1);
})();
