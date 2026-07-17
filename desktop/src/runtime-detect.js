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

function wslDistro() {
  const override = String(process.env.SOLAR_WSL_DISTRO || "").trim();
  if (isSolarWslDistro(override)) return override;
  if (_distroCache !== null) return _distroCache;
  try {
    const r = cp.spawnSync("wsl.exe", ["-l", "-q"], {
      timeout: 5000,
      encoding: "utf8",
    });
    const first = usableWslDistros(r.stdout)[0];
    _distroCache = first || "Ubuntu-24.04";
  } catch {
    _distroCache = "Ubuntu-24.04";
  }
  return _distroCache;
}

function wslExec(cmd, timeoutMs = 8000) {
  const r = cp.spawnSync(
    "wsl.exe",
    ["-d", wslDistro(), "--", "bash", "-lc", cmd],
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

// Does WSL have at least one registered distro? `wsl.exe -l -q` lists them; on a PC with the
// wsl.exe stub present but no distro this is empty — a case `wsl --status` alone misses.
function wslHasDistro() {
  const r = cp.spawnSync("wsl.exe", ["-l", "-q"], {
    timeout: 5000,
    encoding: "utf8",
  });
  if (r.error || r.status !== 0) return false;
  return usableWslDistros(r.stdout).length > 0;
}

// 'missing' (WSL/distro not usable) | 'stopped' (installed, VM cold) | 'up'.
function wslState() {
  const status = cp.spawnSync("wsl.exe", ["--status"], {
    timeout: 6000,
    encoding: "utf8",
  });
  if (status.error) return "missing"; // wsl.exe absent entirely
  if (!wslHasDistro()) return "missing"; // stub present but no distro → needs install
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
