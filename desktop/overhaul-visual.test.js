// Visual + responsive gate for the dashboard overhaul (WS1–WS6). Seeds a realistic
// mid-run sprint on an ISOLATED temp HARNESS_DIR (+ temp SOLAR_DB / workdir — nothing
// touches ~/.solar), spawns the REAL status-server, and renders the REAL session view in
// headless chromium at DESKTOP and MOBILE viewports. Asserts every overhaul surface is
// present (run overview, run health, legible DAG, narrative timeline, gate, result CTA,
// deliverables hierarchy) and that mobile has no horizontal overflow. Screenshots saved.
//
//   node desktop/overhaul-visual.test.js
//
// Missing playwright/chromium => exits non-zero with the exact fix command (never a fake pass).
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  console.log(
    "NOT VERIFIED: playwright missing — fix: ( cd desktop && npm ci && npx playwright install chromium )",
  );
  process.exit(1);
}

const REPO_HARNESS = path.join(__dirname, "..", "harness");
const STATUS_SERVER = path.join(
  REPO_HARNESS,
  "lib",
  "symphony",
  "status-server.py",
);
const HARNESS_LIB =
  process.env.SOLAR_HARNESS_LIB || path.join(REPO_HARNESS, "lib");
const REAL_SOLAR = path.join(os.homedir(), ".solar");

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "solar-ovh-"));
// Workdir must live OUTSIDE HARNESS_DIR (the server rejects a workdir inside it).
const WORKDIR = fs.mkdtempSync(path.join(os.tmpdir(), "solar-ovh-wd-"));
for (const d of ["config", "run", "sprints", "events", "sessions", "reports"]) {
  fs.mkdirSync(path.join(TMP, d), { recursive: true });
}
const OUT_DIR =
  process.env.OUT_DIR ||
  fs.mkdtempSync(path.join(os.tmpdir(), "solar-ovh-shots-"));

const SID = "sprint-20260626-overhaul--abc123";
const PORT_FILE = path.join(TMP, "run", "status-server.port");
const sp = (name) => path.join(TMP, "sprints", name);
const writeJson = (p, obj) => fs.writeFileSync(p, JSON.stringify(obj, null, 2));

// --- seed: status + plan/DAG + process artifacts + workdir output + events -------------
writeJson(sp(`${SID}.status.json`), {
  sprint_id: SID,
  id: SID,
  title: "Build the dashboard overhaul",
  status: "reviewing", // -> eval_review human gate
  phase: "build_complete",
  created_at: "2026-06-20T00:00:00Z",
});
writeJson(sp(`${SID}.task_graph.json`), {
  nodes: [
    {
      id: "prd-1",
      goal: "Write the product requirements",
      status: "passed",
      required_capabilities: ["doc.write"],
    },
    {
      id: "design-1",
      goal: "Design the system architecture",
      status: "passed",
      depends_on: ["prd-1"],
    },
    {
      id: "build-api",
      goal: "Implement the API endpoints",
      status: "passed",
      depends_on: ["design-1"],
      required_capabilities: ["code.python"],
    },
    {
      id: "build-ui",
      goal: "Implement the dashboard UI",
      status: "active",
      depends_on: ["design-1"],
      required_capabilities: ["code.react"],
    },
    {
      id: "eval-1",
      goal: "Evaluate the integrated result",
      status: "blocked",
      depends_on: ["build-api", "build-ui"],
      required_capabilities: ["gpu.cuda"],
      route_decision: "no_matching_worker",
      blocked_reason: "no_matching_worker",
      missing_capabilities: ["gpu.cuda"],
    },
  ],
  edges: [
    { from: "prd-1", to: "design-1" },
    { from: "design-1", to: "build-api" },
    { from: "design-1", to: "build-ui" },
    { from: "build-api", to: "eval-1" },
    { from: "build-ui", to: "eval-1" },
  ],
});
// Process artifacts (pipeline-stage ordering + eval gate source artifacts).
fs.writeFileSync(sp(`${SID}.prd.md`), "# PRD\nBuild a clearer dashboard.\n");
fs.writeFileSync(
  sp(`${SID}.design.md`),
  "# Design\nRun overview + narrative + result hierarchy.\n",
);
fs.writeFileSync(sp(`${SID}.plan.md`), "# Plan\nWS1..WS6.\n");
writeJson(sp(`${SID}.handoff.json`), {
  status: "submitted",
  summary: "builder handoff",
});
writeJson(sp(`${SID}.eval.json`), {
  verdict: "pending",
  notes: "under review",
});
writeJson(sp(`${SID}.acceptance_verdict.json`), {
  verdict: "pending",
  reasons: [],
});
// Workdir: the REAL produced output (the canonical result) + a source file.
fs.writeFileSync(
  path.join(WORKDIR, "report.html"),
  "<!doctype html><html><body><h1>Overhaul Report</h1><p>" +
    "x".repeat(4000) +
    "</p></body></html>",
);
fs.writeFileSync(
  path.join(WORKDIR, "app.py"),
  "print('hello')\n" + "# code\n".repeat(50),
);
writeJson(sp(`${SID}.raw_intent.json`), {
  cwd: WORKDIR,
  request: "build the dashboard overhaul",
});

// Events: a real action double-written (log_message + command sibling, same legacy_event),
// machine noise (must be dropped), a blocked dispatch, and a state change.
const sessDir = path.join(TMP, "sessions", SID);
fs.mkdirSync(sessDir, { recursive: true });
const ev = (over) => ({
  sprint_id: SID,
  ts: over.ts,
  type: over.type,
  actor: over.actor || "coordinator",
  payload: over.payload,
});
const events = [
  ev({
    ts: "2026-06-26T10:00:00Z",
    type: "log_message",
    actor: "coordinator",
    payload: { legacy_event: "intake_created" },
  }),
  ev({
    ts: "2026-06-26T10:00:05Z",
    type: "log_message",
    payload: {
      legacy_event: "dispatched",
      node_id: "build-api",
      role: "builder",
      round: 1,
    },
  }),
  ev({
    ts: "2026-06-26T10:00:05Z",
    type: "command_issued",
    payload: {
      legacy_event: "dispatched",
      node_id: "build-api",
      role: "builder",
      round: 1,
    },
  }),
  ev({
    ts: "2026-06-26T10:00:30Z",
    type: "log_message",
    actor: "solar-autopilot",
    payload: { legacy_event: "autopilot_kb_probe_failed" },
  }),
  ev({
    ts: "2026-06-26T10:00:45Z",
    type: "log_message",
    payload: {
      legacy_event: "handle_passed_completed",
      node_id: "build-api",
      role: "builder",
      round: 1,
    },
  }),
  ev({
    ts: "2026-06-26T10:01:10Z",
    type: "log_message",
    payload: {
      legacy_event: "dispatch_failed",
      node_id: "eval-1",
      role: "evaluator",
      reason: "no_matching_worker",
      decision: "no_matching_worker",
    },
  }),
  ev({
    ts: "2026-06-26T10:01:20Z",
    type: "log_message",
    payload: {
      legacy_event: "state_changed",
      to: "reviewing",
      role: "coordinator",
    },
  }),
];
fs.writeFileSync(
  path.join(sessDir, "events.jsonl"),
  events.map((e) => JSON.stringify(e)).join("\n") + "\n",
);

// A second, NON-stalled sprint in eval review so the human GATE (GateCard) renders
// (the primary sprint above is blocked on a capability gate, so it correctly shows the
// system-pause card instead — both decision-zone states get visual coverage).
const SID2 = "sprint-20260626-gate--def456";
const sp2 = (name) => path.join(TMP, "sprints", name);
writeJson(sp2(`${SID2}.status.json`), {
  sprint_id: SID2,
  id: SID2,
  title: "Review the evaluator output",
  status: "reviewing",
  phase: "build_complete",
  created_at: "2026-06-20T00:00:00Z",
});
writeJson(sp2(`${SID2}.task_graph.json`), {
  nodes: [
    { id: "build-1", goal: "Implement the feature", status: "passed" },
    {
      id: "eval-2",
      goal: "Evaluate the result",
      status: "active",
      depends_on: ["build-1"],
    },
  ],
  edges: [{ from: "build-1", to: "eval-2" }],
});
writeJson(sp2(`${SID2}.handoff.json`), { status: "submitted" });
writeJson(sp2(`${SID2}.eval.json`), { verdict: "pending" });
fs.mkdirSync(path.join(TMP, "sessions", SID2), { recursive: true });
fs.writeFileSync(
  path.join(TMP, "sessions", SID2, "events.jsonl"),
  JSON.stringify({
    sprint_id: SID2,
    ts: "2026-06-26T11:00:00Z",
    type: "log_message",
    actor: "coordinator",
    payload: {
      legacy_event: "handle_passed_completed",
      node_id: "build-1",
      role: "builder",
    },
  }) + "\n",
);

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

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 920 },
  { name: "mobile", width: 390, height: 844 },
];
// Components the overhaul must render on the (blocked) session view.
const REQUIRED = [
  "run-overview",
  "run-health",
  "plan-flow",
  "process-stream",
  "run-result-cta",
];

let failures = 0;
const log = (k, ok, extra = "") => {
  if (!ok) failures += 1;
  console.log(
    `RESULT ${k} ${ok ? "PASS" : "FAIL"}${extra ? " :: " + extra : ""}`,
  );
};

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
  let browser;
  try {
    const port = await waitPort(15000);
    const base = `http://127.0.0.1:${port}`;
    browser = await chromium.launch({
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    });

    for (const vp of VIEWPORTS) {
      const page = await browser.newPage({
        viewport: { width: vp.width, height: vp.height },
      });
      await page.goto(`${base}/#/sessions/${SID}`, {
        waitUntil: "domcontentloaded",
        timeout: 15000,
      });
      await page.waitForTimeout(2500);
      const present = await page.evaluate((ids) => {
        const out = {};
        for (const id of ids)
          out[id] = !!document.querySelector(`[data-testid="${id}"]`);
        return out;
      }, REQUIRED);
      for (const id of REQUIRED) log(`${vp.name}:${id}`, present[id]);

      // The decision zone must show SOMETHING actionable — the human gate OR the
      // enriched system-pause card (this seed is capability-blocked, so it's the latter).
      const decision = await page.evaluate(() => ({
        gate: !!document.querySelector('[data-testid="human-gate"]'),
        stall: !!document.querySelector('[data-testid="system-stall"]'),
      }));
      log(`${vp.name}:decision-surface`, decision.gate || decision.stall);

      // The result CTA must actually point at the canonical result (one click to the output).
      const resultText = await page.evaluate(() => {
        const el = document.querySelector('[data-testid="run-result-cta"]');
        return el ? el.textContent || "" : "";
      });
      log(
        `${vp.name}:result-cta-names-output`,
        /report\.html|result/i.test(resultText),
        resultText.trim(),
      );

      // No raw coordinator jargon / fallback line should leak into the rendered timeline.
      const body = await page.evaluate(() => document.body.innerText || "");
      log(
        `${vp.name}:no-raw-jargon`,
        !/legacy_event|log_message|harness recorded this process step/i.test(
          body,
        ),
      );
      log(
        `${vp.name}:narrative-humanized`,
        /Routed|finished|completed|Dispatch blocked|Moved to/i.test(body),
      );

      // Responsive: no horizontal overflow on mobile.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      // Allow a few px of sub-pixel/vw rounding — anything under ~8px is not a real
      // horizontal scroll, just rounding from viewport-relative widths.
      if (vp.name === "mobile")
        log(
          `${vp.name}:no-horizontal-overflow`,
          overflow <= 8,
          `overflow=${overflow}px`,
        );

      const shot = path.join(OUT_DIR, `overhaul-${vp.name}.png`);
      await page
        .screenshot({ path: shot, fullPage: true, animations: "disabled" })
        .catch(() => {});
      console.log(`SHOT ${vp.name} ${shot}`);
      await page.close();
    }

    // Gate-focused render: the non-stalled review sprint must show the GateCard with
    // clickable artifact chips and the honest "no worker running" note (WS5).
    {
      const page = await browser.newPage({
        viewport: { width: 1440, height: 920 },
      });
      await page.goto(`${base}/#/sessions/${SID2}`, {
        waitUntil: "domcontentloaded",
        timeout: 15000,
      });
      await page.waitForTimeout(2500);
      const gate = await page.evaluate(() => {
        const g = document.querySelector('[data-testid="human-gate"]');
        return {
          present: !!g,
          chips: g ? g.querySelectorAll(".decision-artifact-chip").length : 0,
          workerNote: g
            ? /no worker is currently running/i.test(g.textContent || "")
            : false,
        };
      });
      log("gate:human-gate-renders", gate.present);
      log("gate:artifact-chips", gate.chips > 0, `chips=${gate.chips}`);
      log("gate:honest-worker-note", gate.workerNote);
      const shot = path.join(OUT_DIR, "overhaul-gate.png");
      await page
        .screenshot({ path: shot, fullPage: true, animations: "disabled" })
        .catch(() => {});
      console.log(`SHOT gate ${shot}`);
      await page.close();
    }

    // Isolation: this run's unique sprint must NOT have leaked into the real ~/.solar.
    const leaked = ["sprints/" + SID + ".status.json", "sessions/" + SID].some(
      (rel) => fs.existsSync(path.join(REAL_SOLAR, "harness", rel)),
    );
    log("isolation-real-solar-untouched", !leaked);
  } catch (e) {
    console.log("GATE ERROR:", e.message);
    failures += 1;
  } finally {
    try {
      browser && (await browser.close());
    } catch {}
    try {
      backend.kill();
    } catch {}
    try {
      fs.rmSync(WORKDIR, { recursive: true, force: true });
    } catch {}
  }

  console.log(`\nSCREENSHOTS: ${OUT_DIR}`);
  console.log(
    failures === 0
      ? "OVERHAUL VISUAL GATE: GREEN"
      : `OVERHAUL VISUAL GATE: RED (${failures} failed)`,
  );
  process.exit(failures === 0 ? 0 : 1);
})();
