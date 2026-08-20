"use strict";

// Build the WSL-side packaged runtime sync without temporary shell variables.
// wsl.exe can cause variables assigned inside a `bash -lc` argument to be
// expanded before that command runs, turning `$src`/`$dest` into empty paths.

function shQuote(value) {
  return "'" + String(value).replace(/'/g, "'\\''") + "'";
}

function absolutePosixPath(value, label) {
  const normalized = String(value || "").trim().replace(/\/+$/, "");
  if (!normalized.startsWith("/")) {
    throw new Error(`${label} must be an absolute WSL path`);
  }
  return normalized;
}

function buildWindowsBundledHarnessSyncCommand(source, destination, version) {
  const src = absolutePosixPath(source, "runtime source");
  const dest = absolutePosixPath(destination, "runtime destination");
  const srcQ = shQuote(src);
  const destQ = shQuote(dest);
  return (
    `set -e; mkdir -p ${destQ} "$HOME/.solar/bin"; ` +
    `cp -a ${srcQ}/. ${destQ}/; ` +
    `chmod +x ${destQ}/*.sh ${destQ}/lib/*.sh ${destQ}/tests/*.sh ${destQ}/tools/*.sh ${destQ}/tools/*.py 2>/dev/null || true; ` +
    `if [ -f ${destQ}/solar-harness.sh ]; then ln -sf ${destQ}/solar-harness.sh "$HOME/.solar/bin/solar-harness"; fi; ` +
    `printf '%s\\n' ${shQuote(version)} > ${destQ}/.desktop-runtime-version`
  );
}

module.exports = { buildWindowsBundledHarnessSyncCommand };
