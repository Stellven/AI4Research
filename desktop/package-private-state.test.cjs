"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const desktop = __dirname;
const result = spawnSync(process.execPath, [path.join(desktop, "prepare-package-resources.js")], {
  cwd: desktop,
  encoding: "utf8",
});
assert.equal(result.status, 0, result.stderr || result.stdout);

const staged = path.join(desktop, ".packaging", "harness");
for (const name of [
  ".env",
  ".coordinator-state",
  ".coordinator.log",
  ".planner-last-notice",
  ".planner-last-notice.read",
  "artifacts",
  "events",
  "sessions",
  "sprints",
  "tmp",
]) {
  assert.equal(fs.existsSync(path.join(staged, name)), false, `${name} entered package staging`);
}
assert.equal(fs.existsSync(path.join(staged, ".env.example")), true);
console.log("package private-state test passed");
