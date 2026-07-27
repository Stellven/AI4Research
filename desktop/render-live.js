// Render the OVERHAUL dashboard against a REAL live sprint tree (read-only) and screenshot
// it at desktop + mobile. Reads real sprint data via a symlink-sandbox HARNESS_DIR so the
// owner's running cockpit status-server (and its port file) is never touched.
//   HARNESS_DIR=<real> SID=<sprint-id> OUT_DIR=<dir> node desktop/render-live.js
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const PYTHON =
  process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

const REAL =
  process.env.HARNESS_DIR || path.join(os.homedir(), ".solar", "harness");
const SID = process.env.SID;
const OUT_DIR =
  process.env.OUT_DIR || fs.mkdtempSync(path.join(os.tmpdir(), "live-shots-"));
if (!SID) {
  console.log("need SID");
  process.exit(2);
}

const STATUS_SERVER = path.join(
  __dirname,
  "..",
  "harness",
  "lib",
  "symphony",
  "status-server.py",
);
const HARNESS_LIB = path.join(__dirname, "..", "harness", "lib");

// Symlink-sandbox: real data dirs linked in, but a private run/ dir for OUR port file.
const SBX = fs.mkdtempSync(path.join(os.tmpdir(), "live-sbx-"));
fs.mkdirSync(path.join(SBX, "run"), { recursive: true });
for (const d of [
  "sprints",
  "sessions",
  "state",
  "config",
  "reports",
  "events",
]) {
  const src = path.join(REAL, d);
  if (fs.existsSync(src)) {
    try {
      fs.symlinkSync(src, path.join(SBX, d));
    } catch {}
  } else {
    fs.mkdirSync(path.join(SBX, d), { recursive: true });
  }
}
const PORT_FILE = path.join(SBX, "run", "status-server.port");

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
          : setTimeout(tick, 300);
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

(async () => {
  const backend = spawn(PYTHON, [STATUS_SERVER], {
    cwd: SBX,
    env: {
      ...process.env,
      HARNESS_DIR: SBX,
      PYTHONPATH: HARNESS_LIB,
      SOLAR_BIND_HOST: "127.0.0.1",
      SOLAR_DB: path.join(SBX, "solar.db"),
    },
    stdio: ["ignore", "ignore", "ignore"],
  });
  let browser;
  try {
    const port = await waitPort(20000);
    const base = `http://127.0.0.1:${port}`;
    // What the real projection/deliverables actually expose (printed for the record).
    const j = (p) =>
      new Promise((res) => {
        http
          .get(`${base}${p}`, (r) => {
            let b = "";
            r.on("data", (c) => (b += c));
            r.on("end", () => {
              try {
                res(JSON.parse(b));
              } catch {
                res(null);
              }
            });
          })
          .on("error", () => res(null));
      });
    const proj = await j(
      `/api/sprints/${encodeURIComponent(SID)}/projection?mode=fast`,
    );
    const deliv = await j(`/sprints/${encodeURIComponent(SID)}/deliverables`);
    const d = proj && proj.data ? proj.data : {};
    const narr = Array.isArray(d.narrative) ? d.narrative : [];
    const items = deliv && deliv.items ? deliv.items : [];
    const result = items.find((x) => x.result);
    console.log(`LIVE ${SID}`);
    console.log(
      `  phase=${d.phase} status=${d.status} action=${(d.human_action_required || {}).type} nodes=${(d.nodes || []).length} narrative=${narr.length} deliverables=${items.length}`,
    );
    console.log(
      `  result=${result ? result.name + " [" + result.stage + "]" : "(none)"}`,
    );
    console.log(
      `  narrative_titles=${narr
        .slice(0, 6)
        .map((n) => n.title)
        .join(" | ")}`,
    );

    browser = await chromium.launch({
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    });
    for (const vp of [
      { n: "desktop", w: 1440, h: 920 },
      { n: "mobile", w: 390, h: 844 },
    ]) {
      const page = await browser.newPage({
        viewport: { width: vp.w, height: vp.h },
      });
      await page.goto(`${base}/#/sessions/${SID}`, {
        waitUntil: "domcontentloaded",
        timeout: 20000,
      });
      await page.waitForTimeout(5000);
      const present = await page.evaluate(() => ({
        overview: !!document.querySelector('[data-testid="run-overview"]'),
        plan: !!document.querySelector('[data-testid="plan-flow"]'),
        stream: !!document.querySelector('[data-testid="process-stream"]'),
        gate: !!document.querySelector('[data-testid="human-gate"]'),
        stall: !!document.querySelector('[data-testid="system-stall"]'),
        result: !!document.querySelector('[data-testid="run-result-cta"]'),
        jargon: /legacy_event|harness recorded this process step/i.test(
          document.body.innerText || "",
        ),
        logMsgSteps: (document.body.innerText.match(/Log message/g) || [])
          .length,
        tallestPlanCard: Math.max(
          0,
          ...Array.from(document.querySelectorAll(".plan-card")).map(
            (e) => e.offsetHeight,
          ),
        ),
        overflow: document.documentElement.scrollWidth - window.innerWidth,
      }));
      console.log(`  ${vp.n}: ${JSON.stringify(present)}`);
      const shot = path.join(OUT_DIR, `live-${SID.slice(0, 28)}-${vp.n}.png`);
      await page
        .screenshot({ path: shot, fullPage: true, animations: "disabled" })
        .catch(() => {});
      console.log(`  SHOT ${shot}`);
      await page.close();
    }
  } catch (e) {
    console.log("RENDER ERROR:", e.message);
  } finally {
    try {
      browser && (await browser.close());
    } catch {}
    try {
      backend.kill();
    } catch {}
    try {
      fs.rmSync(SBX, { recursive: true, force: true });
    } catch {}
  }
  console.log(`SHOTS_DIR ${OUT_DIR}`);
})();
