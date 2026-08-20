// Pure WSL / runtime detection helpers, extracted from the Electron main process so they can be
// unit-tested without electron or a display (main.js can't be required in plain Node — it pulls in
// electron and runs app side-effects on import). No electron here — only child_process. main.js
// imports these; tests mock child_process.spawnSync via the shared module object.
//
// Bug class this locks down: a Windows PC with the wsl.exe stub present but NO distro must classify
// as 'missing' (offer to install WSL2), not fall through to "runtime not installed". `wsl --status`
// alone can exit 0 on such a box, so wslState() also requires a registered distro.
const cp = require("child_process");

let _distroCache = null;
const INTERNAL_WSL_DISTRO = /^docker-desktop(?:-data)?$/i;

// Docker Desktop registers implementation-only WSL distributions that are not
// user Linux environments. Solar must never install into or start inside them.
function isSolarWslDistro(name) {
  const value = String(name || "").trim();
  return Boolean(value) && !INTERNAL_WSL_DISTRO.test(value);
}

function usableWslDistros(stdout) {
  return String(stdout || "")
    .replace(/\x00/g, "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(isSolarWslDistro);
}

// Reset the discovered-distro cache (e.g. after `wsl --shutdown`, the default distro may change).
function resetDistroCache() {
  _distroCache = null;
}

function splitWslOutput(raw) {
  return String(raw || "")
    .replace(/\x00/g, "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function defaultWslDistro() {
  const status = cp.spawnSync("wsl.exe", ["--list"], {
    timeout: 5000,
    encoding: "utf8",
  });
  const lines = splitWslOutput(status.stdout);
  const defaultLine = lines.find((line) => line.includes("(Default)"));
  return defaultLine ? defaultLine.split(/[()\s]+/)[0] : "";
}

function wslExecInDistro(distro, cmd, timeoutMs = 8000) {
  const r = cp.spawnSync(
    "wsl.exe",
    ["-d", String(distro), "--", "bash", "-lc", cmd],
    {
      timeout: timeoutMs,
      encoding: "utf8",
  },
  );
  return {
    ok: r.status === 0,
    status: r.status,
    stdout: (r.stdout || "").trim(),
    stderr: (r.stderr || "").trim(),
  };
}

function wslStatusPortInDistro(distro) {
  const r = wslExecInDistro(
    distro,
    "cat ~/.solar/harness/run/status-server.port 2>/dev/null | tr -d \"[:space:]\"",
    5000,
  );
  const port = parseInt(r.stdout, 10);
  return Number.isFinite(port) && port > 0 ? port : null;
}

function wslRuntimeHasFiles(distro) {
  const r = wslExecInDistro(
    distro,
    "test -f ~/.solar/harness/lib/symphony/status-server.py && echo y || echo n",
  );
  return r.stdout.includes("y");
}

function wslRuntimeHealthy(distro) {
  const port = wslStatusPortInDistro(distro);
  if (!port) return false;
  const r = wslExecInDistro(
    distro,
    `curl -fsS -m 2 http://127.0.0.1:${port}/healthz >/dev/null 2>&1 && echo y`,
    5000,
  );
  return r.ok && r.stdout.includes("y");
}

function wslDistro() {
  if (_distroCache !== null) return _distroCache;
  const override = String(process.env.SOLAR_WSL_DISTRO || "").trim();

  if (isSolarWslDistro(override)) {
    _distroCache = override;
    return _distroCache;
  }

  const distros = usableWslDistros(
    cp.spawnSync("wsl.exe", ["-l", "-q"], { timeout: 5000, encoding: "utf8" })
      .stdout,
  );

  for (const distro of distros) {
    if (wslRuntimeHealthy(distro)) {
      _distroCache = distro;
      return distro;
    }
  }

  for (const distro of distros) {
    if (wslRuntimeHasFiles(distro)) {
      _distroCache = distro;
      return distro;
    }
  }

  const fallback = defaultWslDistro() || distros[0] || "Ubuntu-24.04";
  _distroCache = fallback;
  return _distroCache;
}

function wslExec(cmd, timeoutMs = 8000) {
  const r = wslExecInDistro(wslDistro(), cmd, timeoutMs);
  return {
    ok: r.status === 0,
    status: r.status,
    stdout: (r.stdout || "").trim(),
    stderr: (r.stderr || "").trim(),
  };
}

function wslHasDistro() {
  const r = cp.spawnSync("wsl.exe", ["-l", "-q"], {
    timeout: 5000,
    encoding: "utf8",
  });
  if (r.error || r.status !== 0) return false;
  return usableWslDistros(r.stdout).length > 0;
}

// Preserve old behavior for existing callers: "missing" if no distro is registered.
function wslState() {
  const status = cp.spawnSync("wsl.exe", ["--status"], {
    timeout: 6000,
    encoding: "utf8",
  });
  if (status.error) return "missing";
  if (!wslHasDistro()) return "missing";
  const probe = wslExec("echo solar-wsl-up", 10000);
  return probe.ok && probe.stdout.includes("solar-wsl-up") ? "up" : "stopped";
}

module.exports = {
  wslDistro,
  wslExec,
  wslHasDistro,
  wslState,
  resetDistroCache,
  isSolarWslDistro,
};
