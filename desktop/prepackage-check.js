#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const harnessDir = path.join(root, "harness");
const failures = [];

function rel(p) {
  return path.relative(root, p).split(path.sep).join("/");
}

function walk(dir) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    failures.push(`${rel(dir)}: cannot read directory: ${err.message}`);
    return;
  }

  for (const entry of entries) {
    const abs = path.join(dir, entry.name);
    const entryRel = rel(abs);
    let stat;
    try {
      stat = fs.lstatSync(abs);
    } catch (err) {
      failures.push(`${entryRel}: cannot stat: ${err.message}`);
      continue;
    }

    if (stat.isSymbolicLink()) {
      let target = "";
      try {
        target = fs.readlinkSync(abs);
      } catch (err) {
        target = `unreadable: ${err.message}`;
      }
      failures.push(`${entryRel}: symlink is not allowed in packaged harness (target: ${target})`);
      continue;
    }

    if (stat.isDirectory()) {
      walk(abs);
    }
  }
}

if (!fs.existsSync(harnessDir)) {
  failures.push(`${rel(harnessDir)}: missing harness directory`);
} else {
  walk(harnessDir);
}

if (failures.length) {
  console.error("[prepackage-check] packaged harness is not portable:");
  for (const failure of failures) {
    console.error(`  - ${failure}`);
  }
  process.exit(1);
}

console.log("[prepackage-check] OK: harness contains no symlinks");
