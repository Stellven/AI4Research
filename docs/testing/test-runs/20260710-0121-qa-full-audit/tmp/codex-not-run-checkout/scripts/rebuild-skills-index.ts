#!/usr/bin/env bun
/**
 * Rebuild skills index and verify visibility.
 *
 * Default behavior:
 * 1) Index installed skills from ~/.agents/skills
 * 2) Compare with project skills from ./skills
 * 3) Emit JSON + Markdown index files
 * 4) Exit non-zero when project skills are missing in installed directory
 *
 * Usage:
 *   bun run scripts/rebuild-skills-index.ts
 *   bun run scripts/rebuild-skills-index.ts --allow-missing
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const HOME = process.env.HOME || "";
const installedRoot = resolve(`${HOME}/.agents/skills`);
const codexRoot = resolve(`${HOME}/.codex/skills`);
const projectRoot = process.cwd();
const projectSkillsRoot = resolve(join(projectRoot, "skills"));
const allowMissing = process.argv.includes("--allow-missing");

type SkillMeta = {
  name: string;
  title: string;
  description: string;
  path: string;
};

function parseFrontmatter(filePath: string): { title: string; description: string } {
  if (!existsSync(filePath)) return { title: "", description: "" };
  const content = readFileSync(filePath, "utf8");
  const m = content.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return { title: "", description: "" };
  let title = "";
  let description = "";
  for (const line of m[1].split("\n")) {
    const idx = line.indexOf(":");
    if (idx < 0) continue;
    const key = line.slice(0, idx).trim();
    const val = line.slice(idx + 1).trim().replace(/^"|"$/g, "");
    if (key === "name") title = val;
    if (key === "description" && val !== "|" && val !== ">") description = val;
  }
  return { title, description };
}

function listSkillDirs(root: string): string[] {
  if (!existsSync(root)) return [];
  return readdirSync(root, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .filter((name) => existsSync(join(root, name, "SKILL.md")))
    .sort();
}

function collect(root: string): SkillMeta[] {
  const out: SkillMeta[] = [];
  for (const name of listSkillDirs(root)) {
    const full = join(root, name, "SKILL.md");
    const fm = parseFrontmatter(full);
    out.push({
      name,
      title: fm.title || name,
      description: fm.description || "",
      path: full,
    });
  }
  return out;
}

function ensureDir(dir: string): void {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

function main() {
  ensureDir(installedRoot);

  const installed = collect(installedRoot);
  const codex = collect(codexRoot);
  const projectSkills = listSkillDirs(projectSkillsRoot);

  const installedSet = new Set(installed.map((s) => s.name));
  const missingFromInstalled = projectSkills.filter((name) => !installedSet.has(name));

  const jsonOut = {
    generatedAt: new Date().toISOString(),
    installedRoot,
    codexRoot,
    projectSkillsRoot,
    stats: {
      installed: installed.length,
      codex: codex.length,
      project: projectSkills.length,
      missingFromInstalled: missingFromInstalled.length,
    },
    missingFromInstalled,
    installed,
    codex,
  };

  const jsonPath = join(installedRoot, "SKILLS_INDEX.json");
  writeFileSync(jsonPath, JSON.stringify(jsonOut, null, 2));

  const md: string[] = [];
  md.push("# Skills Index");
  md.push("");
  md.push(`Generated: ${jsonOut.generatedAt}`);
  md.push("");
  md.push(`- Installed root: \`${installedRoot}\``);
  md.push(`- Codex root: \`${codexRoot}\``);
  md.push(`- Project skills root: \`${projectSkillsRoot}\``);
  md.push("");
  md.push("## Summary");
  md.push("");
  md.push(`- Installed: ${installed.length}`);
  md.push(`- Codex: ${codex.length}`);
  md.push(`- Project skills: ${projectSkills.length}`);
  md.push(`- Missing from installed: ${missingFromInstalled.length}`);
  md.push("");
  if (missingFromInstalled.length > 0) {
    md.push("## Missing (Project -> Installed)");
    md.push("");
    for (const name of missingFromInstalled) md.push(`- ${name}`);
    md.push("");
  }
  md.push("## Installed Skills");
  md.push("");
  md.push("| Skill | Title | Description |");
  md.push("|---|---|---|");
  for (const s of installed) {
    md.push(`| ${s.name.replace(/\|/g, "\\|")} | ${(s.title || "").replace(/\|/g, "\\|")} | ${(s.description || "").replace(/\|/g, "\\|")} |`);
  }
  md.push("");
  const mdPath = join(installedRoot, "SKILLS_INDEX.md");
  writeFileSync(mdPath, md.join("\n"));

  console.log(`[rebuild-skills-index] json=${jsonPath}`);
  console.log(`[rebuild-skills-index] md=${mdPath}`);
  console.log(`[rebuild-skills-index] installed=${installed.length} project=${projectSkills.length} missing=${missingFromInstalled.length}`);
  if (missingFromInstalled.length > 0) {
    console.log("[rebuild-skills-index] missing:", missingFromInstalled.join(", "));
  }

  if (missingFromInstalled.length > 0 && !allowMissing) {
    process.exit(1);
  }
}

main();

