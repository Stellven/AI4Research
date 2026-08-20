// Pure Windows/WSL runtime prewarm helpers. Kept separate from Electron so the
// cold-start contract can be tested with plain Node on every platform.

function shQuote(value) {
  return "'" + String(value).replace(/'/g, "'\\''") + "'";
}

function buildWindowsRuntimePrewarmCommand(harnessDir) {
  const normalized = String(harnessDir || "").replace(/\/+$/, "");
  if (!normalized.startsWith("/")) {
    throw new Error("Windows runtime prewarm requires an absolute WSL harness path");
  }
  const harness = shQuote(normalized);
  return (
    `set -e; mkdir -p "$HOME/.solar/workspace" "$HOME/.solar/logs"; ` +
    `systemctl --user start solar-status-server.service 2>/dev/null || ` +
    `( setsid env HARNESS_DIR=${harness} PYTHONPATH=${shQuote(`${normalized}/lib`)} ` +
    `python3 ${shQuote(`${normalized}/lib/symphony/status-server.py`)} ` +
    `>>"$HOME/.solar/logs/status-server.log" 2>&1 < /dev/null & ); ` +
    `env SOLAR_PRODUCT_MODE=1 SOLAR_PANE_RUNTIME=codex ` +
    `SOLAR_PM_DEFAULT_PROVIDERS=openai SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=openai ` +
    `bash ${shQuote(`${normalized}/solar-harness.sh`)} start "$HOME/.solar/workspace" --skip-doctor; ` +
    `tmux has-session -t solar-harness 2>/dev/null; ` +
    `test -s ${shQuote(`${normalized}/.coordinator.pid`)}; ` +
    `kill -0 "$(cat ${shQuote(`${normalized}/.coordinator.pid`)})" 2>/dev/null; ` +
    `printf '%s\\n' SOLAR_RUNTIME_PREWARM_READY`
  );
}

function prewarmSucceeded(result) {
  return Boolean(
    result &&
      result.ok &&
      String(result.stdout || "").includes("SOLAR_RUNTIME_PREWARM_READY"),
  );
}

module.exports = { buildWindowsRuntimePrewarmCommand, prewarmSucceeded };
