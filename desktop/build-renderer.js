#!/usr/bin/env node
"use strict";

// Cross-platform renderer build entrypoint. Keep build-renderer.sh as a thin
// developer convenience, but do not require Bash for Windows packaging.
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const appDir = __dirname;
const repoRoot = path.resolve(process.env.SOLAR_REPO_ROOT || path.join(appDir, ".."));
const reactApp = path.resolve(
  process.env.SOLAR_REACT_APP || path.join(repoRoot, "harness", "status-server", "react-app"),
);
const out = path.join(appDir, "renderer");
function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, env: process.env, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

if (!fs.existsSync(reactApp) || !fs.statSync(reactApp).isDirectory()) {
  console.error(`ERROR: react-app not found: ${reactApp}`);
  process.exit(1);
}

console.log(`[build-renderer] source : ${reactApp}`);
console.log(`[build-renderer] output : ${out}`);
if (!fs.existsSync(path.join(reactApp, "node_modules"))) {
  const npmCli = process.env.npm_execpath;
  if (!npmCli || !fs.existsSync(npmCli)) {
    console.error("ERROR: renderer dependencies are missing; run npm install in the react-app");
    process.exit(1);
  }
  run(process.execPath, [npmCli, "install"], reactApp);
}
const viteCli = path.join(reactApp, "node_modules", "vite", "bin", "vite.js");
if (!fs.existsSync(viteCli)) {
  console.error(`ERROR: Vite CLI not found after dependency install: ${viteCli}`);
  process.exit(1);
}
run(
  process.execPath,
  [viteCli, "build", "--base=./", "--outDir", out, "--emptyOutDir"],
  reactApp,
);

const indexPath = path.join(out, "index.html");
if (!fs.existsSync(indexPath)) {
  console.error("ERROR: build produced no index.html");
  process.exit(1);
}
const assetCount = fs.existsSync(path.join(out, "assets"))
  ? fs.readdirSync(path.join(out, "assets")).length
  : 0;
console.log(
  `[build-renderer] OK -> ${assetCount} asset(s), index.html ${fs.statSync(indexPath).size}b`,
);
