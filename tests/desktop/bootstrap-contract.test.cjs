// Bootstrap/package contract checks for the desktop app. These are static by design:
// they catch release-path regressions without launching Electron or touching ~/.solar.
const fs = require("fs");
const path = require("path");
const DESKTOP = path.resolve(__dirname, "..", "..", "desktop");

function read(relPath) {
  return fs.readFileSync(path.join(DESKTOP, relPath), "utf8");
}

function assert(name, ok, detail = "") {
  if (!ok) {
    console.error(`FAIL ${name}${detail ? `: ${detail}` : ""}`);
    process.exitCode = 1;
  } else {
    console.log(`PASS ${name}`);
  }
}

const main = read("src/main.js");
const getSolar = read("../get-solar.sh");
const releaseVersion = read("../VERSION").trim();
const app = read("../harness/status-server/react-app/src/App.tsx");
const pkg = JSON.parse(read("package.json"));
const autotest = read("autotest.sh");
const selftestElectron = read("../tests/desktop/selftest-electron.test.cjs");
const buildRenderer = read("build-renderer.js");
const prepareResources = read("prepare-package-resources.js");
// Keep static workflow assertions portable across Git's CRLF/LF checkout
// policy. The contract is structural; line-ending normalization must not turn
// a valid Windows checkout into a false release-gate failure.
const desktopWorkflow = read("../.github/workflows/desktop-build.yml").replace(
  /\r\n/g,
  "\n",
);
const desktopGateJob = desktopWorkflow.split("\n  gate:\n")[1] || "";
const macResources = (pkg.build.mac.extraResources || []).map((entry) => entry.to);
const harnessResource = (pkg.build.extraResources || []).find(
  (entry) => entry.to === "harness",
);

assert(
  "fresh packaged app syncs bundled harness before network installer",
  main.includes("!runtimeInstalled()") &&
    main.includes("SOLAR_DESKTOP_ALLOW_DEV_RUNTIME_SYNC") &&
    main.includes("install action: using bundled harness before network installer"),
);

assert(
  "symlinked ~/.solar/harness is rejected before sync/start",
  main.includes("runtimeSymlinkIssue") &&
    main.includes("runtime-symlink") &&
    main.includes("refusing bundled harness sync into symlinked runtime"),
);

assert(
  "stale runtime pid/port/token markers are cleared before start",
  main.includes("clearRuntimeStateMarkers") &&
    main.includes("status-server.pid") &&
    main.includes("status-server.port"),
);

assert(
  "macOS bundled sync installs LaunchAgent",
  main.includes("installMacLaunchAgent") &&
    main.includes("com.solar.status-server.plist") &&
    main.includes("launchctl"),
);

assert(
  "mac package carries LaunchAgent helper resources",
  macResources.includes("runtime/install-macos-agent.sh") &&
    macResources.includes("runtime/uninstall-macos-agent.sh") &&
    macResources.includes("runtime/com.solar.status-server.plist"),
);

assert(
  "get-solar fallback defaults to the package release channel",
  getSolar.includes(`SOLAR_CHANNEL="\${SOLAR_CHANNEL:-v${releaseVersion}}"`),
);

assert(
  "session UI has an error boundary fallback",
  app.includes("class AppErrorBoundary") &&
    app.includes("componentDidCatch") &&
    app.includes("Session view could not render"),
);

assert(
  "desktop persists renderer/runtime diagnostics to log file",
  main.includes("appendDesktopLog") &&
    main.includes("desktop.log") &&
    main.includes("renderer-process-gone") &&
    main.includes("window-unresponsive"),
);

assert(
  "desktop selftest validates the loaded runtime dashboard",
  main.includes("assessSelftestSnapshot") &&
    main.includes("collectSelftestSnapshot") &&
    main.includes("fallback_renderer_loaded") &&
    main.includes("finishSelftest(false") &&
    main.includes("app.exit(code)"),
);

assert(
  "desktop selftest fails when a requested screenshot cannot be written",
  main.includes('reason: "screenshot_capture_failed"') &&
    main.includes("capturePage returned an empty PNG") &&
    !main.includes("SHOT_FAIL"),
);

assert(
  "desktop selftest fails immediately on renderer crash or unresponsiveness",
  main.includes('reason: "renderer_process_gone"') &&
    main.includes('reason: "window_unresponsive"'),
);

assert(
  "dashboard listener cleanup tolerates renderer teardown",
  main.includes("const targetWebContents = win.webContents") &&
    main.includes("if (targetWebContents.isDestroyed()) return") &&
    main.includes("targetWebContents.removeListener"),
);

assert(
  "desktop autotest runs the selftest truth suite",
  autotest.includes("node ../tests/desktop/src/selftest-verdict.test.cjs") &&
    autotest.includes("node ../tests/desktop/selftest-electron.test.cjs"),
);

assert(
  "desktop packaging uses cross-platform renderer and private-state-free staging",
  pkg.scripts["build:renderer"] === "node build-renderer.js" &&
    pkg.scripts["build:win"].includes("node prepare-package-resources.js") &&
    pkg.scripts["build:mac"].includes("node prepare-package-resources.js") &&
    pkg.scripts["build:linux"].includes("node prepare-package-resources.js") &&
    harnessResource?.from === ".packaging/harness" &&
    buildRenderer.includes("vite.js") &&
    prepareResources.includes('"run"') &&
    prepareResources.includes('"quarantine"'),
);

assert(
  "desktop autotest runs automated accessibility audit",
  autotest.includes("node accessibility.test.js") &&
    pkg.scripts["test:accessibility"] === "node accessibility.test.js",
);

assert(
  "Electron selftest can verify a built executable",
  selftestElectron.includes("SOLAR_ELECTRON_EXECUTABLE_PATH") &&
    selftestElectron.includes("executablePath") &&
    desktopWorkflow.includes("dist/linux-unpacked/solar-desktop"),
);

assert(
  "Linux desktop entry matches Electron's runtime window class",
  pkg.desktopName === "solar-desktop.desktop" &&
    pkg.build.linux.syncDesktopName === true,
);

assert(
  "desktop autotest runs this bootstrap/package contract",
  autotest.includes("node ../tests/desktop/bootstrap-contract.test.cjs"),
);

assert(
  "desktop artifacts wait for the gate before building",
  /\n  build:\n    needs: gate\n/.test(desktopWorkflow),
);

assert(
  "desktop tag gate runs release coherence before packaging",
  desktopGateJob.includes("bash scripts/check-release-coherence.sh"),
);
