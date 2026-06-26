// Solar desktop app — Electron shell.
// Spawns or attaches the local status-server runtime, renders the bundled dashboard,
// and classifies startup failures into actionable, mode-specific screens with one-click
// recovery + a telemetry-free "Copy diagnostics" bundle.
// Verification behavior: if SOLAR_BACKEND_URL is set, attach to that already-running
// backend instead of spawning one (used to verify the shell without a live runtime).
const {
  app,
  BrowserWindow,
  Menu,
  shell,
  protocol,
  clipboard,
  dialog,
} = require("electron");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

// Chromium's setuid sandbox commonly can't init on Linux/WSL/headless; disabling it there keeps
// the renderer from crashing. On Windows/macOS the sandbox works, so KEEP it (don't weaken the
// posture). SOLAR_ELECTRON_DISABLE_SANDBOX=1 forces it off anywhere (CI); =0 forces it on.
const disableSandbox =
  process.env.SOLAR_ELECTRON_DISABLE_SANDBOX === "1" ||
  (process.env.SOLAR_ELECTRON_DISABLE_SANDBOX !== "0" &&
    process.platform === "linux");
if (disableSandbox) {
  app.commandLine.appendSwitch("no-sandbox");
  app.commandLine.appendSwitch("disable-gpu-sandbox");
}
app.commandLine.appendSwitch("disable-dev-shm-usage");
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-software-rasterizer");

const HARNESS_DIR =
  process.env.HARNESS_DIR || path.join(os.homedir(), ".solar", "harness");
const STATUS_SERVER = path.join(
  HARNESS_DIR,
  "lib",
  "symphony",
  "status-server.py",
);
const PORT_FILE = path.join(HARNESS_DIR, "run", "status-server.port");
const LOG_DIR = path.join(os.homedir(), ".solar", "logs");

const IS_WIN = process.platform === "win32";
const WSL_HARNESS = process.env.SOLAR_WSL_HARNESS || "$HOME/.solar/harness";
const PRESET_URL = process.env.SOLAR_BACKEND_URL || "";
const SELFTEST = process.env.SOLAR_DESKTOP_SELFTEST === "1";
// Test hook: force the classifier to return a given mode (deterministic screenshots).
const SIMULATE = process.env.SOLAR_SIMULATE || "";

let backend = null;
let win = null;
let dashboardURL = null;
let firstAttachDone = false; // first-run gets a longer, patient startup budget
let bootstrapOffered = false; // Windows: auto-offer WSL2 setup at most once per session
let installPoll = null; // live "installing" poll: auto-advance to the dashboard when the runtime appears

// --- logging: ring buffer so a packaged app (no stdout) can still emit diagnostics ---
const LOG_RING = [];
const LOG_RING_MAX = 500;
function log(...a) {
  const line = "[solar-desktop] " + a.map((x) => String(x)).join(" ");
  LOG_RING.push(new Date().toISOString() + " " + line);
  if (LOG_RING.length > LOG_RING_MAX) LOG_RING.shift();
  console.log(line);
}

// --- Windows / WSL2 helpers ---------------------------------------------------
// On Windows the Electron app runs on the HOST; the runtime lives in WSL2. We drive
// it through wsl.exe and reach it over localhost (WSL2 localhostForwarding maps
// 127.0.0.1:<port> in the distro to the host). Distro is discovered, not hardcoded.
// WSL detection lives in a no-electron module so it's unit-testable (see runtime-detect.test.js).
// Call sites below are unchanged.
const {
  wslDistro,
  wslExec,
  wslHasDistro,
  wslState,
  resetDistroCache,
} = require("./runtime-detect");

// First-run Windows bootstrap: install WSL2 + the Linux runtime via the bundled
// install.ps1. That script self-elevates, runs `wsl --install`, and registers a RunOnce
// that resumes after the reboot WSL2 requires — so the user gets one click + one UAC
// prompt + one reboot instead of being told to hunt down and run a script themselves.
function installerScriptPath() {
  // Packaged: electron-builder copies install.ps1 next to the app via extraResources
  // (process.resourcesPath). Dev: it lives at the repo root, two levels up from desktop/src.
  const candidates = [
    path.join(process.resourcesPath || "", "install.ps1"),
    path.join(__dirname, "..", "..", "install.ps1"),
  ];
  return (
    candidates.find((p) => {
      try {
        return fs.existsSync(p);
      } catch {
        return false;
      }
    }) || ""
  );
}

function runWindowsBootstrap() {
  const ps1 = installerScriptPath();
  if (!ps1) {
    log("bootstrap: no bundled install.ps1 found; opening docs");
    shell.openExternal("https://learn.microsoft.com/windows/wsl/install");
    return false;
  }
  const quoted = "'" + ps1.replace(/'/g, "''") + "'";
  try {
    // Fire-and-forget so the UAC prompt never freezes the app. The outer (hidden)
    // PowerShell elevates via -Verb RunAs; install.ps1 then runs in its own console.
    const child = spawn(
      "powershell.exe",
      [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList " +
          "'-NoProfile','-ExecutionPolicy','Bypass','-File'," +
          quoted,
      ],
      { detached: true, stdio: "ignore", windowsHide: true },
    );
    child.unref();
    return true;
  } catch (e) {
    log("bootstrap launch failed:", String(e).slice(0, 200));
    shell.openExternal("https://learn.microsoft.com/windows/wsl/install");
    return false;
  }
}

function docsUrl() {
  return (
    "https://github.com/" +
    (process.env.SOLAR_REPO || "suraj-subrahmanyan/OpenSolar") +
    "#install"
  );
}

// macOS/Linux first-run bootstrap: install the runtime with the bundled standalone
// get-solar.sh (install.sh isn't standalone — it sources lib/installer/*). Runs headless
// and detached so the app never freezes; progress goes to ~/.solar/logs/install.log and
// the "Check again" button re-classifies once the runtime appears.
function getSolarScriptPath() {
  const candidates = [
    path.join(process.resourcesPath || "", "get-solar.sh"),
    path.join(__dirname, "..", "..", "get-solar.sh"),
  ];
  return (
    candidates.find((p) => {
      try {
        return fs.existsSync(p);
      } catch {
        return false;
      }
    }) || ""
  );
}

function runUnixBootstrap() {
  const sh = getSolarScriptPath();
  if (!sh) {
    log("bootstrap: no bundled get-solar.sh found; opening docs");
    shell.openExternal(docsUrl());
    return false;
  }
  try {
    const out = fs.openSync(path.join(LOG_DIR, "install.log"), "a");
    const child = spawn(
      "bash",
      // Include status-daemon so the in-app install also sets up the persistent
      // launchd/systemd service (parity with Windows), not just a runtime the app
      // must respawn each launch. status-daemon load is best-effort, never fatal.
      [sh, "--yes", "--components", "kernel,harness,status-daemon"],
      { detached: true, stdio: ["ignore", out, out] },
    );
    child.unref();
    return true;
  } catch (e) {
    log("unix bootstrap launch failed:", String(e).slice(0, 200));
    shell.openExternal(docsUrl());
    return false;
  }
}

// Port discovery. On Windows the port file lives in WSL; cache it for the poll loop so
// we don't spawn a cold `wsl bash -lc` every tick.
let _portCache = null;
function readPort() {
  if (IS_WIN) {
    if (_portCache) return _portCache;
    const r = wslExec(
      `cat ${WSL_HARNESS}/run/status-server.port 2>/dev/null`,
      5000,
    );
    const p = parseInt(r.stdout, 10);
    _portCache = Number.isFinite(p) && p > 0 ? p : null;
    return _portCache;
  }
  try {
    return parseInt(fs.readFileSync(PORT_FILE, "utf8").trim(), 10) || null;
  } catch {
    return null;
  }
}
function clearPortCache() {
  _portCache = null;
}

function probeHealth(port, timeoutMs = 1500, host = "127.0.0.1") {
  return new Promise((resolve) => {
    if (!port) return resolve(false);
    const req = http.get(
      { host, port, path: "/healthz", timeout: timeoutMs },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      },
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

// (Windows) is the server healthy from INSIDE WSL? Splits "server down" from
// "127.0.0.1 forwarding broken" (the known WSL #9516 edge case).
function serverHealthyInWsl(port) {
  if (!port) return false;
  const r = wslExec(
    `curl -fsS -m 2 http://127.0.0.1:${port}/healthz >/dev/null 2>&1 && echo solar-ok`,
    6000,
  );
  return r.ok && r.stdout.includes("solar-ok");
}

function runtimeInstalled() {
  if (IS_WIN) {
    return wslExec(
      `test -f ${WSL_HARNESS}/lib/symphony/status-server.py && echo y`,
      5000,
    ).stdout.includes("y");
  }
  return fs.existsSync(STATUS_SERVER);
}

// --- backend lifecycle --------------------------------------------------------
function startBackendWindows() {
  const r = wslExec(
    `systemctl --user start solar-status-server.service 2>/dev/null || ` +
      `( setsid env HARNESS_DIR=${WSL_HARNESS} PYTHONPATH=${WSL_HARNESS}/lib ` +
      `python3 ${WSL_HARNESS}/lib/symphony/status-server.py ` +
      `>/dev/null 2>&1 < /dev/null & )`,
    15000,
  );
  if (!r.ok && r.stderr) log("WSL start:", r.stderr.slice(0, 200));
  clearPortCache();
  return true;
}

function startBackend() {
  if (IS_WIN) return startBackendWindows();
  if (!fs.existsSync(STATUS_SERVER)) {
    log("WARN status-server not found at", STATUS_SERVER);
    return false;
  }
  try {
    fs.unlinkSync(PORT_FILE);
  } catch {}
  fs.mkdirSync(path.dirname(PORT_FILE), { recursive: true });
  backend = spawn("python3", [STATUS_SERVER], {
    cwd: HARNESS_DIR,
    env: { ...process.env, HARNESS_DIR },
    stdio: ["ignore", "pipe", "pipe"],
  });
  backend.stdout.on("data", (d) => log("[backend]", String(d).trim()));
  backend.stderr.on("data", (d) => log("[backend!]", String(d).trim()));
  backend.on("exit", (c) => log("backend exited", c));
  return true;
}

// Wait for health, polling. First run (cold WSL/launchd) gets a longer budget.
function waitForBackend(timeoutMs) {
  const ceiling = timeoutMs || (firstAttachDone ? 20000 : 60000);
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = async () => {
      if (IS_WIN) clearPortCache();
      const port = readPort();
      if (port && (await probeHealth(port))) {
        firstAttachDone = true;
        return resolve(`http://127.0.0.1:${port}/`);
      }
      if (Date.now() - start > ceiling) return resolve(null);
      if (win && !win.isDestroyed()) {
        const secs = Math.round((Date.now() - start) / 1000);
        win.loadURL(
          SCREENS.loading(
            secs < 8
              ? "Starting the runtime…"
              : "Still starting (first launch can take a moment)…",
            secs,
          ),
        );
      }
      setTimeout(tick, 600);
    };
    tick();
  });
}

function detectRunning(timeoutMs = 1500) {
  return new Promise(async (resolve) => {
    const port = readPort();
    if (port && (await probeHealth(port, timeoutMs))) {
      resolve(`http://127.0.0.1:${port}/`);
    } else resolve(null);
  });
}

// --- the classifier: run a diagnostic ladder, map to {mode, baseUrl?, detail} -----
async function classifyRuntimeState() {
  if (SIMULATE) return { mode: SIMULATE, detail: { simulated: true } };
  if (PRESET_URL) {
    log("attaching to backend", PRESET_URL);
    return { mode: "ok", baseUrl: PRESET_URL };
  }

  // 1. Already-running managed runtime? attach (don't double-spawn; quit won't kill it).
  const existing = await detectRunning();
  if (existing) {
    log("attached to already-running runtime", existing);
    return { mode: "ok", baseUrl: existing };
  }

  // 2. (Windows) rule out WSL-not-up before blaming the server.
  if (IS_WIN) {
    const ws = wslState();
    if (ws === "missing") return { mode: "wsl-missing", detail: {} };
    if (ws === "stopped") log("WSL installed but cold; will boot it");
  }

  // 3. Runtime installed at all?
  if (!runtimeInstalled())
    return { mode: "not-installed", detail: { path: STATUS_SERVER } };

  // 4. Start it, then wait (patient on first run).
  log("no running runtime detected; starting one");
  if (!startBackend())
    return { mode: "not-installed", detail: { path: STATUS_SERVER } };
  const url = await waitForBackend();
  if (url) return { mode: "ok", baseUrl: url };

  // 5. Didn't come up. On Windows, split "server dead" from "forwarding broken".
  if (IS_WIN) {
    const port = readPort();
    if (port && serverHealthyInWsl(port)) {
      const wslIp = wslExec(
        "hostname -I 2>/dev/null | awk '{print $1}'",
        5000,
      ).stdout;
      // W8: forwarding is broken but the server IS up in WSL. Under NAT it binds 0.0.0.0,
      // so attach directly via the WSL VM IP before surfacing an error screen.
      if (wslIp && (await probeHealth(port, 2000, wslIp))) {
        log("127.0.0.1 forwarding broken; attaching via WSL IP", wslIp);
        return { mode: "ok", baseUrl: `http://${wslIp}:${port}/` };
      }
      return { mode: "forwarding-broken", detail: { port, wslIp } };
    }
  }
  // Port file present but unhealthy ⇒ likely crashed on startup; else never started.
  return { mode: readPort() ? "crashed" : "no-start", detail: {} };
}

// --- screens: inline data-URL HTML with action buttons (no extra bundled files) ----
function esc(s) {
  return String(s).replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
  );
}
function screenHTML({ title, sub, tone = "#e7e7e7", actions = [] }) {
  const btns = actions
    .map(
      (a) =>
        `<a href="solar-action:${esc(a.id)}" style="display:inline-block;margin:6px;padding:9px 16px;` +
        `border:1px solid #3a3a3d;border-radius:8px;color:#e7e7e7;text-decoration:none;font-size:13px;` +
        `background:${a.primary ? "#1f6feb" : "#1a1a1c"};border-color:${a.primary ? "#1f6feb" : "#3a3a3d"}">${esc(a.label)}</a>`,
    )
    .join("");
  return (
    "data:text/html," +
    encodeURIComponent(
      '<body style="margin:0;background:#0b0b0c;color:#e7e7e7;font:15px -apple-system,Segoe UI,Roboto,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">' +
        '<div style="text-align:center;max-width:560px;padding:24px">' +
        `<div style="font-size:20px;margin-bottom:10px;color:${tone}">${esc(title)}</div>` +
        `<div style="opacity:.65;line-height:1.55;margin-bottom:16px">${sub}</div>` +
        `<div>${btns}</div>` +
        "</div></body>",
    )
  );
}
const DIAG = { id: "copy-diagnostics", label: "Copy diagnostics" };
const SCREENS = {
  loading: (msg, secs) =>
    screenHTML({
      title: "Solar",
      sub:
        esc(msg || "Starting the runtime…") +
        (secs ? ` <span style="opacity:.5">(${secs}s)</span>` : ""),
      actions:
        secs && secs > 12
          ? [{ id: "keep-waiting", label: "Keep waiting" }, DIAG]
          : [],
    }),
  "not-installed": (d) =>
    screenHTML({
      title: "Solar runtime isn't installed",
      sub: IS_WIN
        ? "The Solar engine isn't set up inside WSL2 yet. Install it (one click), then reload."
        : `The background runtime that powers Solar wasn't found at <code>~/.solar/harness</code>. Install the Solar runtime, then reload.`,
      tone: "#f0b429",
      actions: [
        { id: "run-installer", label: "Install Solar runtime", primary: true },
        { id: "retry", label: "Retry" },
        { id: "install-help", label: "Learn more" },
        DIAG,
      ],
    }),
  "wsl-missing": () =>
    screenHTML({
      title: "WSL2 isn't installed",
      sub: "Solar runs its engine inside WSL2 on Windows. Click below to install it automatically — approve the Windows prompt, then your PC reboots once and Solar resumes on its own.",
      tone: "#f0b429",
      actions: [
        { id: "run-installer", label: "Install WSL2 now", primary: true },
        { id: "install-help", label: "Learn more" },
        DIAG,
      ],
    }),
  // Shown while the bundled install.ps1 runs (or if it couldn't launch). Always has
  // actions so the user is never stranded on an indefinite spinner during setup.
  installing: (launched, logTail) =>
    screenHTML({
      title: launched ? "Setting up Solar…" : "Couldn't start setup",
      sub:
        (launched
          ? IS_WIN
            ? "Approve the Windows prompt to install WSL2 and the runtime. Your PC reboots once, then Solar resumes — the dashboard opens automatically when it's ready."
            : "Installing the Solar runtime in the background — this can take a few minutes (macOS may need Homebrew Python). The dashboard opens automatically when it's ready."
          : "We couldn't launch the installer automatically — retry, or open setup help.") +
        (logTail
          ? `<pre style="text-align:left;margin:14px auto 0;max-width:520px;max-height:200px;overflow:auto;background:#111114;padding:10px 12px;border-radius:8px;font-size:11px;line-height:1.45;opacity:.75;white-space:pre-wrap">${esc(logTail)}</pre>`
          : ""),
      tone: "#f0b429",
      actions: [
        { id: "retry", label: "Check again", primary: true },
        { id: "run-installer", label: "Run setup again" },
        { id: "install-help", label: "Setup help" },
        DIAG,
      ],
    }),
  crashed: () =>
    screenHTML({
      title: "The Solar runtime stopped responding",
      sub: "The engine is installed but its server isn't answering — it may have crashed on startup.",
      tone: "#ff6b6b",
      actions: [
        { id: "restart-runtime", label: "Restart runtime", primary: true },
        { id: "retry", label: "Retry" },
        DIAG,
      ],
    }),
  "no-start": () =>
    screenHTML({
      title: "Solar runtime didn't start",
      sub: "We tried to start the engine but it didn't come up in time. On first launch this can take longer.",
      tone: "#ff6b6b",
      actions: [
        { id: "keep-waiting", label: "Keep waiting", primary: true },
        { id: "restart-runtime", label: "Restart runtime" },
        DIAG,
      ],
    }),
  "forwarding-broken": (d) =>
    screenHTML({
      title: "Can't reach the runtime from Windows",
      sub: "The engine is running in WSL but Windows can't see it on localhost (a known WSL networking glitch). Reconnect, or restart WSL networking.",
      tone: "#ff6b6b",
      actions: [
        { id: "reconnect", label: "Reconnect", primary: true },
        { id: "restart-wsl-net", label: "Restart WSL networking" },
        DIAG,
      ],
    }),
  error: (msg) =>
    screenHTML({
      title: "Couldn't start Solar",
      sub: esc(msg || "An unexpected error occurred."),
      tone: "#ff6b6b",
      actions: [{ id: "retry", label: "Retry", primary: true }, DIAG],
    }),
};

// --- telemetry-FREE diagnostics bundle ----------------------------------------
function tail(file, n = 120) {
  try {
    return fs.readFileSync(file, "utf8").split(/\r?\n/).slice(-n).join("\n");
  } catch {
    return `(unavailable: ${file})`;
  }
}
function redact(s) {
  return String(s)
    .replace(
      /([A-Z0-9_]*(?:TOKEN|KEY|SECRET|CREDENTIAL)[A-Z0-9_]*\s*[:=]\s*)\S+/gi,
      "$1[REDACTED]",
    )
    .replace(/\b[A-Za-z0-9_\-]{32,}\b/g, "[REDACTED-LONG]");
}
function collectDiagnostics() {
  const parts = [];
  parts.push("=== Solar desktop diagnostics (local, no telemetry) ===");
  parts.push(`time: ${new Date().toISOString()}`);
  parts.push(
    `app: ${app.getVersion()}  electron: ${process.versions.electron}  platform: ${process.platform} ${os.release()}`,
  );
  parts.push(`HARNESS_DIR: ${HARNESS_DIR}`);
  if (IS_WIN) {
    parts.push(`wsl distro: ${wslDistro()}  state: ${wslState()}`);
    const st = spawnSync("wsl.exe", ["--status"], {
      timeout: 6000,
      encoding: "utf8",
    });
    parts.push("wsl --status:\n" + (st.stdout || st.stderr || "(none)"));
  }
  parts.push(`port: ${readPort()}`);
  parts.push(
    "\n--- desktop-app log (ring buffer) ---\n" +
      LOG_RING.slice(-200).join("\n"),
  );
  if (IS_WIN) {
    parts.push(
      "\n--- status-server (journald, in WSL) ---\n" +
        wslExec(
          "journalctl --user -u solar-status-server.service -n 120 --no-pager 2>/dev/null || true",
          8000,
        ).stdout,
    );
    parts.push(
      "\n--- daemon status (WSL) ---\n" +
        wslExec(
          "systemctl --user status solar-status-server.service --no-pager 2>/dev/null || true",
          8000,
        ).stdout,
    );
  } else if (process.platform === "darwin") {
    parts.push(
      "\n--- status-server stderr ---\n" +
        tail(path.join(LOG_DIR, "status-server-stderr.log")),
    );
    parts.push(
      "\n--- daemon status (launchd) ---\n" +
        (spawnSync(
          "launchctl",
          ["print", `gui/${process.getuid()}/com.solar.status-server`],
          { timeout: 5000, encoding: "utf8" },
        ).stdout || "(none)"),
    );
  } else {
    parts.push(
      "\n--- status-server (journald) ---\n" +
        (spawnSync(
          "journalctl",
          [
            "--user",
            "-u",
            "solar-status-server.service",
            "-n",
            "120",
            "--no-pager",
          ],
          { timeout: 6000, encoding: "utf8" },
        ).stdout || tail(path.join(LOG_DIR, "status-server-stderr.log"))),
    );
  }
  return redact(parts.join("\n"));
}

// --- install progress: live setup-log tail + auto-advance to the dashboard -----------
function installLogPath() {
  return IS_WIN
    ? path.join(process.env.LOCALAPPDATA || os.homedir(), "Solar", "setup.log")
    : path.join(LOG_DIR, "install.log");
}
function installLogTail(n = 16) {
  return redact(tail(installLogPath(), n));
}
function stopInstallPoll() {
  if (installPoll) {
    clearInterval(installPoll);
    installPoll = null;
  }
}
// Show the "installing" screen with the current setup-log tail, then poll: refresh the tail and,
// the moment the runtime answers, load the dashboard so the user never hunts for "Check again".
function showInstalling(launched) {
  if (!win || win.isDestroyed()) return;
  stopInstallPoll();
  win.loadURL(SCREENS.installing(launched, installLogTail()));
  if (!launched) return;
  let ticks = 0;
  installPoll = setInterval(async () => {
    if (!win || win.isDestroyed()) return stopInstallPoll();
    const url = await detectRunning(1200);
    if (url) {
      stopInstallPoll();
      dashboardURL = url;
      return loadDashboard(url);
    }
    if (++ticks > 600) return stopInstallPoll(); // ~20 min safety cap
    win.loadURL(SCREENS.installing(launched, installLogTail()));
  }, 2000);
}

// --- recovery actions (the solar-action: protocol handler dispatches to these) -----
async function runAction(id) {
  log("action:", id);
  stopInstallPoll(); // any explicit action supersedes a running install poll
  if (id === "copy-diagnostics") {
    clipboard.writeText(collectDiagnostics());
    if (win && !win.isDestroyed())
      win.loadURL(
        SCREENS.loading("Diagnostics copied to clipboard. Retrying…", 0),
      );
    return reload();
  }
  if (id === "install-help") {
    shell.openExternal(
      "https://github.com/" +
        (process.env.SOLAR_REPO || "suraj-subrahmanyan/OpenSolar") +
        "#install",
    );
    return;
  }
  if (id === "run-installer") {
    // Windows: bundled install.ps1 (WSL2 + runtime; self-elevating; RunOnce reboot-resume).
    // macOS/Linux: bundled get-solar.sh (headless runtime install). Both then show the
    // installing screen so "Check again" re-classifies once the runtime appears.
    const ok = IS_WIN ? runWindowsBootstrap() : runUnixBootstrap();
    showInstalling(ok);
    return;
  }
  if (id === "restart-runtime") {
    if (IS_WIN)
      wslExec(
        "systemctl --user restart solar-status-server.service 2>/dev/null || true",
        12000,
      );
    else if (process.platform === "darwin")
      spawnSync(
        "launchctl",
        ["kickstart", "-k", `gui/${process.getuid()}/com.solar.status-server`],
        { timeout: 8000 },
      );
    else
      spawnSync(
        "systemctl",
        ["--user", "restart", "solar-status-server.service"],
        { timeout: 8000 },
      );
    clearPortCache();
    return reload();
  }
  if (id === "restart-wsl-net") {
    spawnSync("wsl.exe", ["--shutdown"], { timeout: 15000 });
    clearPortCache();
    resetDistroCache();
    return reload();
  }
  if (id === "reconnect" || id === "retry" || id === "keep-waiting") {
    clearPortCache();
    return reload();
  }
}

// --- window + main flow -------------------------------------------------------
function reload() {
  return createWindow(true);
}

async function createWindow(reuse) {
  if (!win || win.isDestroyed()) {
    win = new BrowserWindow({
      width: 1440,
      height: 920,
      title: "Solar",
      backgroundColor: "#0b0b0c",
      webPreferences: {
        contextIsolation: true,
        preload: path.join(__dirname, "preload.js"),
        // Primary load is the runtime dashboard over http://127.0.0.1 (a normal secure origin,
        // same-origin with its API); the offline fallback is served over the registered secure
        // app:// scheme — so webSecurity stays ON. (Was false only to let the file:// fallback
        // load ES modules; app:// removes that need.)
        webSecurity: true,
      },
    });
    win.webContents.on("console-message", (_e, _lvl, msg) =>
      log("renderer:", String(msg).slice(0, 200)),
    );
    // Recovery buttons on the error screens are <a href="solar-action:<id>"> links.
    // Intercept the navigation (don't actually navigate), run the action instead.
    win.webContents.on("will-navigate", (e, url) => {
      if (url.startsWith("solar-action:")) {
        e.preventDefault();
        // Only OUR control screens (data: URLs) may invoke privileged recovery actions
        // (installer / restart / wsl --shutdown). NEVER honor solar-action: from the
        // runtime-served dashboard or any other loaded content.
        const current = win.webContents.getURL() || "";
        if (!current.startsWith("data:")) {
          log(
            "ignored solar-action from non-control origin:",
            current.slice(0, 48),
          );
          return;
        }
        runAction(
          decodeURIComponent(
            url.slice("solar-action:".length).replace(/^\/+/, ""),
          ),
        );
      }
    });
    Menu.setApplicationMenu(buildMenu());
  }

  win.loadURL(SCREENS.loading("Starting the runtime…", 0));
  let state;
  try {
    state = await classifyRuntimeState();
  } catch (e) {
    log("classify error:", e.message);
    state = { mode: "error", detail: { message: e.message } };
  }

  // P0: Windows first-run auto-offer. If WSL2 isn't set up, proactively ask once (one
  // confirm) and run the bundled bootstrap, rather than waiting for a button click.
  if (
    IS_WIN &&
    (state.mode === "wsl-missing" || state.mode === "not-installed") &&
    !bootstrapOffered &&
    !SELFTEST &&
    !SIMULATE
  ) {
    bootstrapOffered = true;
    const needWsl = state.mode === "wsl-missing";
    const choice = dialog.showMessageBoxSync(win, {
      type: "question",
      buttons: ["Set up Solar", "Not now"],
      defaultId: 0,
      cancelId: 1,
      title: "Set up Solar",
      message: needWsl
        ? "Solar needs to install WSL2 and its runtime."
        : "Solar needs to finish setting up its runtime in WSL2.",
      detail: needWsl
        ? "One-time setup: approve one Windows prompt and your PC reboots once. Solar resumes automatically afterward."
        : "Solar installs its engine inside WSL2 — this can take a few minutes; the dashboard opens automatically when it's ready.",
    });
    if (choice === 0) {
      const ok = runWindowsBootstrap();
      showInstalling(ok);
      return;
    }
    // "Not now" → fall through to the existing screen (manual button stays).
  }

  if (state.mode === "ok" && state.baseUrl) {
    dashboardURL = state.baseUrl;
    return loadDashboard(state.baseUrl);
  }
  const screen = SCREENS[state.mode] || SCREENS.error;
  win.loadURL(
    state.mode === "error"
      ? SCREENS.error(state.detail && state.detail.message)
      : screen(state.detail),
  );
  if (SELFTEST) {
    log("SELFTEST FAIL (mode=" + state.mode + ")");
    setTimeout(() => app.quit(), 300);
  }
}

function loadDashboard(url) {
  win.webContents.once("did-finish-load", () => {
    log("LOADED", url);
    if (SELFTEST) {
      const shot = process.env.SOLAR_DESKTOP_SHOT;
      const finish = () => {
        log("SELFTEST OK");
        setTimeout(() => app.quit(), 300);
      };
      if (shot) {
        setTimeout(() => {
          win.webContents
            .capturePage()
            .then((img) => {
              try {
                fs.writeFileSync(shot, img.toPNG());
                log("SHOT", shot, img.toPNG().length + "b");
              } catch (e) {
                log("SHOT_FAIL", e.message);
              }
              finish();
            })
            .catch((e) => {
              log("SHOT_FAIL", e.message);
              finish();
            });
        }, 2800);
      } else finish();
    }
  });
  // Load the RUNTIME's served dashboard, not the app's bundled copy. Keeps the dashboard
  // version-matched with the runtime and same-origin with its API. The bundled renderer stays
  // only as an offline fallback, served over the secure app:// scheme (so webSecurity stays on).
  // ONE did-fail-load handler: try the app:// fallback on a hard load failure, else show error.
  const RENDERER_INDEX = path.join(__dirname, "..", "renderer", "index.html");
  win.webContents.once("did-fail-load", (_e, code, desc) => {
    log("FAIL-LOAD", code, desc);
    if (code <= -100 && fs.existsSync(RENDERER_INDEX)) {
      log("runtime UI failed; falling back to bundled renderer (app://)");
      win.loadURL("app://index.html?api=http://" + new URL(url).host);
      return;
    }
    win.loadURL(SCREENS.error("Error " + code + ": " + desc));
    if (SELFTEST) {
      log("SELFTEST FAIL");
      app.quit();
    }
  });
  log("loading runtime dashboard:", url);
  win.loadURL(url);
}

function buildMenu() {
  return Menu.buildFromTemplate([
    { label: "Solar", submenu: [{ role: "quit" }] },
    {
      label: "View",
      submenu: [
        { role: "reload", click: () => reload() },
        {
          label: "Open in Browser",
          click: () => dashboardURL && shell.openExternal(dashboardURL),
        },
        { role: "toggleDevTools" },
      ],
    },
    {
      label: "Help",
      submenu: [
        {
          label: "Copy diagnostics",
          click: () => clipboard.writeText(collectDiagnostics()),
        },
        {
          label: "Save diagnostics…",
          click: async () => {
            const r = await dialog.showSaveDialog(win, {
              defaultPath: "solar-diagnostics.txt",
            });
            if (!r.canceled && r.filePath)
              fs.writeFileSync(r.filePath, collectDiagnostics());
          },
        },
        { label: "Open logs folder", click: () => shell.openPath(LOG_DIR) },
      ],
    },
  ]);
}

// --- app:// scheme: serve the bundled renderer over a real (secure) origin ---------
protocol.registerSchemesAsPrivileged([
  {
    scheme: "app",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);
function registerProtocols() {
  const RENDERER_DIR = path.join(__dirname, "..", "renderer");
  protocol.handle("app", async (request) => {
    let rel = decodeURIComponent(new URL(request.url).pathname);
    if (rel === "/" || rel === "") rel = "/index.html";
    const filePath = path.join(RENDERER_DIR, rel);
    if (path.relative(RENDERER_DIR, filePath).startsWith(".."))
      return new Response("forbidden", { status: 403 });
    try {
      const data = await fs.promises.readFile(filePath);
      const ext = path.extname(filePath).toLowerCase();
      const ct =
        {
          ".html": "text/html",
          ".js": "text/javascript",
          ".mjs": "text/javascript",
          ".css": "text/css",
          ".json": "application/json",
          ".woff2": "font/woff2",
          ".woff": "font/woff",
          ".svg": "image/svg+xml",
          ".png": "image/png",
          ".ico": "image/x-icon",
          ".map": "application/json",
        }[ext] || "application/octet-stream";
      return new Response(data, { headers: { "content-type": ct } });
    } catch {
      return new Response("not found", { status: 404 });
    }
  });
  // (Recovery-button clicks are handled by the will-navigate interceptor in createWindow.)
}

try {
  fs.mkdirSync(LOG_DIR, { recursive: true });
} catch {}

app.whenReady().then(() => {
  registerProtocols();
  createWindow();
});
app.on("window-all-closed", () => app.quit());
app.on("quit", () => {
  // Only kill a backend WE spawned; a managed/attached service is left running.
  if (backend) {
    try {
      backend.kill();
    } catch {}
  }
});
