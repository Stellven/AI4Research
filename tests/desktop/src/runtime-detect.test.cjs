// Bootstrap-logic unit test — no electron, no display, runs anywhere (incl. Windows node.exe).
// Mocks child_process.spawnSync to simulate wsl.exe and asserts the WSL detection. Locks in the
// stub-but-no-distro classification bug (must be 'missing', not fall through).
const cp = require("child_process");

// Install a fake `wsl.exe` from a scenario spec. runtime-detect calls cp.spawnSync (property access
// at call time), so reassigning it here takes effect for the (freshly required) module.
function mockWsl(scn) {
  cp.spawnSync = (file, args) => {
    if (file !== "wsl.exe") return { status: 1, stdout: "", stderr: "" };
    if (args[0] === "--status") {
      if (scn.statusErr)
        return {
          error: new Error("ENOENT"),
          status: null,
          stdout: "",
          stderr: "",
        };
      return {
        status: scn.statusExit == null ? 0 : scn.statusExit,
        stdout: "WSL ok",
        stderr: "",
      };
    }
    if (args[0] === "-l" && args[1] === "-q") {
      if (scn.listErr)
        return {
          error: new Error("ENOENT"),
          status: null,
          stdout: "",
          stderr: "",
        };
      return {
        status: 0,
        stdout: (scn.distros || []).join("\r\n"),
        stderr: "",
      };
    }
    if (args[0] === "-d") {
      return scn.probeOk
        ? { status: 0, stdout: "solar-wsl-up", stderr: "" }
        : { status: 1, stdout: "", stderr: "down" };
    }
    return { status: 1, stdout: "", stderr: "" };
  };
}

// Fresh module per case so _distroCache doesn't bleed between scenarios.
function loadFresh() {
  delete require.cache[require.resolve("../../../desktop/src/runtime-detect")];
  return require("../../../desktop/src/runtime-detect");
}

const cases = [
  [
    "wsl.exe absent -> missing",
    { statusErr: true },
    (m) => m.wslState() === "missing",
  ],
  [
    "stub present, NO distro -> missing (the bug)",
    { statusExit: 0, distros: [] },
    (m) => m.wslState() === "missing",
  ],
  [
    "distro present + warm -> up",
    { statusExit: 0, distros: ["Ubuntu-24.04"], probeOk: true },
    (m) => m.wslState() === "up",
  ],
  [
    "distro present + cold -> stopped",
    { statusExit: 0, distros: ["Ubuntu-24.04"], probeOk: false },
    (m) => m.wslState() === "stopped",
  ],
  [
    "wslHasDistro false when list empty",
    { distros: [] },
    (m) => m.wslHasDistro() === false,
  ],
  [
    "wslHasDistro true when distro listed",
    { distros: ["Ubuntu-24.04"] },
    (m) => m.wslHasDistro() === true,
  ],
  [
    "Docker Desktop internal distros do not count as a Solar distro",
    { statusExit: 0, distros: ["docker-desktop", "docker-desktop-data"] },
    (m) => m.wslHasDistro() === false && m.wslState() === "missing",
  ],
  [
    "first real Linux distro wins over Docker Desktop internals",
    {
      distros: ["docker-desktop", "docker-desktop-data", "Ubuntu-24.04"],
    },
    (m) => m.wslDistro() === "Ubuntu-24.04",
  ],
  [
    "wslDistro honors SOLAR_WSL_DISTRO env",
    { distros: ["Ubuntu-24.04"] },
    (m) => {
      process.env.SOLAR_WSL_DISTRO = "Custom-Distro";
      const ok = m.wslDistro() === "Custom-Distro";
      delete process.env.SOLAR_WSL_DISTRO;
      return ok;
    },
  ],
  [
    "internal SOLAR_WSL_DISTRO override cannot target Docker Desktop",
    { distros: ["docker-desktop", "Debian"] },
    (m) => {
      process.env.SOLAR_WSL_DISTRO = "docker-desktop";
      const ok = m.wslDistro() === "Debian";
      delete process.env.SOLAR_WSL_DISTRO;
      return ok;
    },
  ],
];

let pass = 0,
  fail = 0;
for (const [name, scn, check] of cases) {
  delete process.env.SOLAR_WSL_DISTRO;
  mockWsl(scn);
  const m = loadFresh();
  let ok = false;
  try {
    ok = check(m) === true;
  } catch {
    ok = false;
  }
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
  ok ? pass++ : fail++;
}
console.log(
  `\n${fail === 0 ? "LOGIC TEST PASS" : "LOGIC TEST FAIL"} (${pass}/${pass + fail})`,
);
process.exit(fail === 0 ? 0 : 1);
