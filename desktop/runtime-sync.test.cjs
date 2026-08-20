"use strict";

const assert = require("node:assert/strict");
const { buildWindowsBundledHarnessSyncCommand } = require("./src/runtime-sync");

const command = buildWindowsBundledHarnessSyncCommand(
  "/mnt/c/Program Files/Solar/resources/harness",
  "/home/solar/.solar/harness",
  "1.0.0-rc.9",
);

assert.match(command, /'\/mnt\/c\/Program Files\/Solar\/resources\/harness'\/\./);
assert.match(command, /'\/home\/solar\/\.solar\/harness'\/\.desktop-runtime-version/);
assert.doesNotMatch(command, /\$(?:src|dest)\b/);
assert.throws(
  () => buildWindowsBundledHarnessSyncCommand("relative", "/tmp/runtime", "v1"),
  /absolute WSL path/,
);
console.log("runtime-sync tests passed");
