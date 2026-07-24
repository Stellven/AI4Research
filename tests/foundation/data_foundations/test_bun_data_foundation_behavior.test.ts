import { afterEach, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { detectImportance, extractKnowledge } from "../../../core/memory/auto-semantic";
import { OntologyManager } from "../../../core/ontology/manager";
import { FileIndexer } from "../../../core/smi/indexer";

const scratch: string[] = [];

afterEach(() => {
  for (const path of scratch.splice(0)) {
    rmSync(path, { recursive: true, force: true });
  }
});

describe("current Bun-backed data foundations", () => {
  test("concept and memory graph initializes an ontology snapshot", async () => {
    const db = new Database(":memory:");
    const manager = new OntologyManager(db);
    const snapshot = await manager.onSessionStart("phase22-data-foundation");
    expect(snapshot.version.length).toBeGreaterThan(0);
    expect(Array.isArray(snapshot.memory.semantic)).toBeTrue();
    db.close();
  });

  test("code graph subset indexes file metadata and skips unchanged content", async () => {
    const root = mkdtempSync(join(tmpdir(), "phase22-smi-"));
    scratch.push(root);
    const source = join(root, "probe.ts");
    const database = join(root, "smi.sqlite");
    writeFileSync(source, "export const phase22 = 'code graph probe';\n", "utf8");

    const db = new Database(database);
    db.exec(`
      CREATE TABLE smi_files (
        file_id TEXT PRIMARY KEY,
        file_path TEXT UNIQUE,
        abs_path TEXT,
        file_type TEXT,
        category TEXT,
        feature TEXT,
        project TEXT,
        title TEXT,
        description TEXT,
        tags TEXT,
        size_bytes INTEGER,
        line_count INTEGER,
        last_modified TEXT,
        content_hash TEXT,
        indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
      )
    `);
    db.close();

    const indexer = new FileIndexer(database, root);
    expect(await indexer.indexFile(source)).toBeTrue();
    expect(await indexer.indexFile(source)).toBeFalse();
    expect(indexer.getStats().indexed).toBe(1);
    expect(indexer.getStats().skipped).toBe(1);
    indexer.close();
  });

  test("semantic memory extracts explicitly important knowledge", () => {
    const detection = detectImportance("Remember this critical design decision for the project");
    expect(detection.isImportant).toBeTrue();
    const knowledge = extractKnowledge("Remember this critical design decision", detection.category!);
    expect(knowledge?.source_type).toBe("explicit");
    expect(knowledge?.confidence).toBe(1);
  });
});
