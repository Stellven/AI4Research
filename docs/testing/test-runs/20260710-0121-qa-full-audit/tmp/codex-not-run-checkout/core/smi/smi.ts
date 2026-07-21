#!/usr/bin/env bun
/**
 * SMI CLI - Solar Metadata Index Command Line Interface
 * 统一查询接口，替代 Grep/Glob
 */

import { SMIQuery } from "./query";
import { FileIndexer } from "./indexer";

const query = new SMIQuery();

function printTable(data: any[], headers: string[]) {
  if (data.length === 0) {
    console.log("No results found");
    return;
  }

  // Print headers
  console.log(headers.join("\t"));
  console.log("-".repeat(80));

  // Print rows
  for (const row of data) {
    const values = headers.map((h) => {
      const val = row[h];
      if (Array.isArray(val)) return val.join(",");
      return val || "";
    });
    console.log(values.join("\t"));
  }
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0];

  try {
    switch (cmd) {
      // ==================== Search Commands ====================
      case "search":
      case "s":
        const results = query.search(args[1] || "");
        printTable(results, ["entity_type", "title", "path"]);
        break;

      // ==================== Feature Commands ====================
      case "feature":
      case "f":
        const files = query.findFilesByFeature(args[1] || "");
        printTable(files, ["category", "title", "file_path"]);
        break;

      // ==================== Agent Commands ====================
      case "agents":
      case "a":
        const agents = query.findAllAgents();
        printTable(agents, ["agent_id", "role", "phase", "file_path"]);
        break;

      // ==================== Skill Commands ====================
      case "skills":
      case "sk":
        const skills = query.findAllSkills();
        printTable(skills, ["command", "name", "category", "usage_count"]);
        break;

      // ==================== Stats Commands ====================
      case "stats":
        const stats = query.getStats();
        console.log("SMI Statistics:");
        console.log(`  Total Files:    ${stats.total_files}`);
        console.log(`  Total Agents:   ${stats.total_agents}`);
        console.log(`  Total Skills:   ${stats.total_skills}`);
        console.log(`  Total Projects: ${stats.total_projects}`);
        break;

      case "feature-stats":
        const featureStats = query.getFeatureStats();
        printTable(featureStats, ["feature", "file_count"]);
        break;

      // ==================== Index Commands ====================
      case "index":
      case "i":
        const dir = args[1] || process.cwd();
        console.log(`Indexing directory: ${dir}\n`);
        const indexer = new FileIndexer();
        const indexStats = await indexer.scanDirectory(dir);
        console.log("\nIndexing Stats:");
        console.log(`  Total files: ${indexStats.total_files}`);
        console.log(`  Indexed:     ${indexStats.indexed}`);
        console.log(`  Updated:     ${indexStats.updated}`);
        console.log(`  Skipped:     ${indexStats.skipped}`);
        console.log(`  Errors:      ${indexStats.errors}`);
        console.log(`  Duration:    ${indexStats.duration_ms}ms`);
        indexer.close();
        break;

      // ==================== Help ====================
      case "help":
      case "-h":
      case "--help":
      default:
        console.log(`
SMI (Solar Metadata Index) - Unified Query Interface

Usage: smi <command> [args]

Search Commands:
  search, s <query>       Full-text search across all entities
  feature, f <name>       Find all files related to a feature

Entity Commands:
  agents, a               List all agents
  skills, sk              List all skills

Stats Commands:
  stats                   Show overall statistics
  feature-stats           Show statistics by feature

Index Commands:
  index, i [dir]          Index a directory (default: current)

Examples:
  smi search capsule      # Search for "capsule"
  smi feature backlog     # Find all Backlog-related files
  smi agents              # List all agents
  smi stats               # Show statistics
  smi index ~/Solar       # Index Solar project
        `);
    }
  } finally {
    query.close();
  }
}

main().catch((err) => {
  console.error("Error:", err);
  process.exit(1);
});
