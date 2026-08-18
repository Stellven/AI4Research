#!/usr/bin/env node
"use strict";

// Build an explicit, private-state-free harness tree for electron-builder.
// electron-builder may stat source entries before applying glob exclusions, so
// pointing it at the live harness can both fail on protected runtime state and
// risk packaging local credentials.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const source = path.join(root, "harness");
const stagingRoot = path.join(__dirname, ".packaging");
const destination = path.join(stagingRoot, "harness");
const excluded = new Set([
  ".git",
  "node_modules",
  "__pycache__",
  "templates/persona",
  "run",
  "state",
  "logs",
  "cache",
  "venvs",
  "vendor",
  "quarantine",
]);

function copyTree(from, to, relative = "") {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const entryRelative = relative ? `${relative}/${entry.name}` : entry.name;
    if (excluded.has(entry.name) || excluded.has(entryRelative)) continue;
    if (entry.name.endsWith(".pyc")) continue;
    const input = path.join(from, entry.name);
    const output = path.join(to, entry.name);
    const stat = fs.lstatSync(input);
    if (stat.isSymbolicLink()) {
      throw new Error(`symlink is not allowed in packaged harness: ${entryRelative}`);
    }
    if (stat.isDirectory()) copyTree(input, output, entryRelative);
    else if (stat.isFile()) fs.copyFileSync(input, output);
  }
}

fs.rmSync(stagingRoot, { recursive: true, force: true });
copyTree(source, destination);
const forbidden = ["run", "state", "logs", "cache", "venvs", "vendor", "quarantine"];
for (const name of forbidden) {
  if (fs.existsSync(path.join(destination, name))) {
    throw new Error(`forbidden runtime directory entered package staging: ${name}`);
  }
}
console.log(`[prepare-package-resources] OK -> ${destination}`);
