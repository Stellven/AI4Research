import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const requireFromApp = createRequire(
  new URL("../../../../harness/status-server/react-app/package.json", import.meta.url),
);
const ts = requireFromApp("typescript");
const sourceUrl = new URL(
  "../../../../harness/status-server/react-app/src/format.ts",
  import.meta.url,
);
const source = await readFile(sourceUrl, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
  fileName: sourceUrl.pathname,
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`;
const { planNodeLabel } = await import(moduleUrl);

assert.equal(
  planNodeLabel({ node_id: "literature-discovery" }),
  "Literature Discovery",
);
assert.equal(
  planNodeLabel({ node_id: "paper-preparation-ingestion__98f149a5_c01" }),
  "Paper Preparation Ingestion · Part 1",
);
assert.equal(
  planNodeLabel({ id: "build-kv-cache-report-generation" }),
  "KV Cache Report Generation",
);
assert.equal(
  planNodeLabel({ title: "Review the final report" }),
  "Review the final report",
);

console.log("planNodeLabel: authoritative step labels passed");
