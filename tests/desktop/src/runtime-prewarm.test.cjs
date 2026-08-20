const {
  buildWindowsRuntimePrewarmCommand,
  prewarmSucceeded,
} = require("../../../desktop/src/runtime-prewarm");

function assert(name, condition) {
  if (!condition) throw new Error(`FAIL ${name}`);
  console.log(`PASS ${name}`);
}

const command = buildWindowsRuntimePrewarmCommand("/home/solar/.solar/harness/");

assert(
  "prewarm starts the managed status server",
  command.includes("systemctl --user start solar-status-server.service"),
);
assert(
  "prewarm starts the product runtime in Codex/OpenAI mode",
  command.includes("SOLAR_PRODUCT_MODE=1") &&
    command.includes("SOLAR_PANE_RUNTIME=codex") &&
    command.includes("SOLAR_PM_DEFAULT_PROVIDERS=openai"),
);
assert(
  "prewarm creates the harness and verifies coordinator liveness",
  command.includes("solar-harness.sh' start") &&
    command.includes("tmux has-session -t solar-harness") &&
    command.includes(".coordinator.pid"),
);
assert(
  "prewarm requires an absolute WSL path",
  (() => {
    try {
      buildWindowsRuntimePrewarmCommand("relative/harness");
      return false;
    } catch {
      return true;
    }
  })(),
);
assert(
  "prewarm success requires both exit success and readiness marker",
  prewarmSucceeded({ ok: true, stdout: "SOLAR_RUNTIME_PREWARM_READY" }) &&
    !prewarmSucceeded({ ok: false, stdout: "SOLAR_RUNTIME_PREWARM_READY" }) &&
    !prewarmSucceeded({ ok: true, stdout: "" }),
);
