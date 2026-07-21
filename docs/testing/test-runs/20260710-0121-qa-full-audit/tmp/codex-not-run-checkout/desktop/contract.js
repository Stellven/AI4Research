// Backend-contract gate: spawn the status-server on an isolated HARNESS_DIR and assert the
// HTTP contract the desktop shell + dashboard depend on. Pure Node (no browser, no electron),
// so it runs anywhere — Linux, macOS, and Windows node.exe. Exits 0 (PASS) / 1 (FAIL).
// Locks in the CORS/HEAD/OPTIONS/auth/runtime-info work (regressing it = 501s in the app).
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

const HARNESS_DIR =
  process.env.HARNESS_DIR || path.join(__dirname, "..", "harness");
const STATUS_SERVER = path.join(
  HARNESS_DIR,
  "lib",
  "symphony",
  "status-server.py",
);
const PORT_FILE = path.join(HARNESS_DIR, "run", "status-server.port");
const PYTHON =
  process.env.SOLAR_PYTHON ||
  (process.platform === "win32" ? "python" : "python3");

function req(port, method, p) {
  return new Promise((resolve) => {
    const r = http.request(
      { host: "127.0.0.1", port, path: p, method, timeout: 4000 },
      (res) => {
        let body = "";
        res.on("data", (d) => (body += d));
        res.on("end", () =>
          resolve({ status: res.statusCode, headers: res.headers, body }),
        );
      },
    );
    r.on("error", () => resolve({ status: 0, headers: {}, body: "" }));
    r.on("timeout", () => {
      r.destroy();
      resolve({ status: 0, headers: {}, body: "" });
    });
    r.end();
  });
}

function waitHealthy(timeoutMs) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = async () => {
      let port = null;
      try {
        port = parseInt(fs.readFileSync(PORT_FILE, "utf8").trim(), 10);
      } catch {}
      if (port && (await req(port, "GET", "/healthz")).status === 200)
        return resolve(port);
      if (Date.now() - start > timeoutMs)
        return reject(new Error("not healthy in time"));
      setTimeout(tick, 300);
    };
    tick();
  });
}

const CHECKS = [
  {
    name: "GET /healthz == 200",
    run: (p) => req(p, "GET", "/healthz").then((r) => r.status === 200),
  },
  {
    name: "OPTIONS /status == 204 (CORS preflight, was 501)",
    run: (p) => req(p, "OPTIONS", "/status").then((r) => r.status === 204),
  },
  {
    name: "OPTIONS sends Access-Control-Allow-Origin",
    run: (p) =>
      req(p, "OPTIONS", "/status").then(
        (r) => !!r.headers["access-control-allow-origin"],
      ),
  },
  {
    name: "HEAD /status == 200 (was 501)",
    run: (p) => req(p, "HEAD", "/status").then((r) => r.status === 200),
  },
  {
    name: "GET /runtime-info == 200",
    run: (p) => req(p, "GET", "/runtime-info").then((r) => r.status === 200),
  },
  {
    name: "GET /auth/status == 200",
    run: (p) => req(p, "GET", "/auth/status").then((r) => r.status === 200),
  },
  {
    name: "/auth/status leaks no token-shaped value",
    run: (p) =>
      req(p, "GET", "/auth/status").then(
        (r) => !/[A-Za-z0-9_\-]{32,}/.test(r.body),
      ),
  },
];

(async () => {
  if (!fs.existsSync(STATUS_SERVER)) {
    console.log("CONTRACT FAIL: status-server not found at", STATUS_SERVER);
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
  let allPass = false;
  try {
    const port = await waitHealthy(15000);
    const results = [];
    for (const c of CHECKS) {
      let ok = false;
      try {
        ok = await c.run(port);
      } catch {
        ok = false;
      }
      results.push({ name: c.name, ok });
      console.log(`  ${ok ? "PASS" : "FAIL"}  ${c.name}`);
    }
    allPass = results.every((r) => r.ok);
  } catch (e) {
    console.log("CONTRACT FAIL:", e.message);
  } finally {
    try {
      backend.kill();
    } catch {}
  }
  console.log(allPass ? "CONTRACT PASS" : "CONTRACT FAIL");
  process.exit(allPass ? 0 : 1);
})();
