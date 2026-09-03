import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const requireFromApp = createRequire(
  new URL("../../../../harness/status-server/react-app/package.json", import.meta.url),
);
const ts = requireFromApp("typescript");
const sourceUrl = new URL(
  "../../../../harness/status-server/react-app/src/pocPreview.ts",
  import.meta.url,
);
const source = await readFile(sourceUrl, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
  fileName: sourceUrl.pathname,
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`;
const { buildPocPreviewModel, selectPocArtifact } = await import(moduleUrl);

const model = buildPocPreviewModel({
  data: {
    status: "completed",
    phase: "graph_completed",
    summary: {
      progress: {
        total_nodes: 14,
        passed_nodes: 14,
        percent_complete: 1,
        failed_nodes: 0,
      },
    },
    plan_governance: {
      state: "certified",
      plan_compile_bounces: 1,
      compile_error_codes: [
        "DISCOVERY_NON_SCOPE_OWNERSHIP",
        "REQUIREMENT_VERIFIER_MISSING",
      ],
    },
  },
});
assert.deepEqual(model, {
  total: 14,
  done: 14,
  percent: 100,
  failed: 0,
  active: 0,
  phase: "graph_completed",
  terminal: true,
  resolvedIssues: [
    "DISCOVERY_NON_SCOPE_OWNERSHIP",
    "REQUIREMENT_VERIFIER_MISSING",
  ],
});

const poster = { name: "poster.html", rel_path: "workspace/demo/poster.html", kind: "html" };
assert.equal(
  selectPocArtifact([
    { name: "report.md", rel_path: "workspace/demo/report.md", kind: "md", result: true },
    poster,
  ]),
  poster,
);

console.log("pocPreview: live progress, repaired issues, and preview artifact passed");
