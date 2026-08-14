// SIMULATE-screen gate: launch the real Electron app forcing each error/recovery screen via
// SOLAR_SIMULATE, and assert the screen's title + action buttons render. No backend / WSL needed —
// exercises the first-run UX (U1/U2 + the recovery screens) end-to-end in Electron.
//
//   xvfb-run -a node screens.test.cjs     (Linux; needs a display)
// Note: IS_WIN is false on this host, so Windows-specific sub-copy isn't asserted here — the
// titles + action buttons are platform-agnostic; the Windows copy branch is covered by the Pester
// side. solar-action navigation is intercepted by main.js (we only assert the buttons exist).
const { _electron: electron } = require("playwright");
const fs = require("fs");
const path = require("path");
const DESKTOP = path.resolve(__dirname, "..", "..", "desktop");
const EVIDENCE_PATH = process.env.SOLAR_SCREEN_EVIDENCE || "";

function writeEvidence(payload) {
  if (!EVIDENCE_PATH) return;
  fs.mkdirSync(path.dirname(EVIDENCE_PATH), { recursive: true });
  fs.writeFileSync(EVIDENCE_PATH, JSON.stringify(payload, null, 2) + "\n");
}

const CASES = [
  {
    mode: "not-installed",
    title: "Solar runtime isn't installed",
    buttons: ["Retry", "Copy diagnostics"],
  },
  {
    mode: "runtime-symlink",
    title: "Solar runtime path is a symlink",
    buttons: ["Retry", "Setup help"],
  },
  {
    mode: "wsl-missing",
    title: "WSL2 isn't installed",
    buttons: ["Install WSL2 now", "Learn more"],
  },
  {
    mode: "crashed",
    title: "stopped responding",
    buttons: ["Restart runtime", "Retry"],
  },
  {
    mode: "no-start",
    title: "didn't start",
    buttons: ["Keep waiting", "Restart runtime"],
  },
  {
    mode: "forwarding-broken",
    title: "Can't reach the runtime",
    buttons: ["Reconnect", "Restart WSL networking"],
  },
  { mode: "error", title: "Couldn't start Solar", buttons: ["Retry"] },
];

(async () => {
  // Probe: can Electron launch here at all? Exit 2 means NOT VERIFIED; callers must never
  // translate that into a green product gate.
  try {
    const probe = await electron.launch({
      args: ["."],
      cwd: DESKTOP,
      env: {
        ...process.env,
        SOLAR_SIMULATE: "error",
        SOLAR_ELECTRON_DISABLE_SANDBOX: "1",
      },
    });
    await probe.close();
  } catch (e) {
    writeEvidence({
      schema_version: "solar.desktop.recovery_screens.v1",
      status: "ENVIRONMENT_BLOCKED",
      error: String(e.message).split("\n")[0],
      cases: [],
    });
    console.log(
      "SKIP: Electron cannot launch in this environment (" +
        String(e.message).split("\n")[0] +
        ") - screen gate skipped",
    );
    process.exit(2);
  }

  let pass = 0;
  let fail = 0;
  const results = [];
  for (const c of CASES) {
    let app;
    try {
      app = await electron.launch({
        args: ["."],
        cwd: DESKTOP,
        env: {
          ...process.env,
          SOLAR_SIMULATE: c.mode,
          SOLAR_ELECTRON_DISABLE_SANDBOX: "1",
        },
      });
      const win = await app.firstWindow();
      // The loading screen shows first, then the simulated mode screen — wait for the title.
      await win.waitForFunction(
        (t) => (document.body.innerText || "").includes(t),
        c.title,
        { timeout: 20000 },
      );
      const text = await win.evaluate(() => document.body.innerText || "");
      const missing = c.buttons.filter((b) => !text.includes(b));
      if (missing.length === 0) {
        console.log(
          `PASS  ${c.mode}  ("${c.title}" + [${c.buttons.join(", ")}])`,
        );
        pass++;
        results.push({ mode: c.mode, title: c.title, buttons: c.buttons, status: "PASS" });
      } else {
        console.log(
          `FAIL  ${c.mode}: missing button(s): ${missing.join(", ")}`,
        );
        fail++;
        results.push({ mode: c.mode, title: c.title, buttons: c.buttons, missing, status: "FAIL" });
      }
    } catch (e) {
      console.log(`FAIL  ${c.mode}: ${String(e.message).split("\n")[0]}`);
      fail++;
      results.push({ mode: c.mode, title: c.title, buttons: c.buttons, error: String(e.message).split("\n")[0], status: "FAIL" });
    } finally {
      try {
        await app?.close();
      } catch {}
    }
  }
  writeEvidence({
    schema_version: "solar.desktop.recovery_screens.v1",
    status: fail === 0 ? "PASS" : "FAIL",
    platform: process.platform,
    electron_entrypoint: "desktop/src/main.js",
    passed: pass,
    failed: fail,
    cases: results,
  });
  console.log(`\nSCREENS: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})();
