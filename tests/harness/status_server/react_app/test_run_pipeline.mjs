import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const requireFromApp = createRequire(
  new URL("../../../../harness/status-server/react-app/package.json", import.meta.url),
);
const ts = requireFromApp("typescript");

const sourceUrl = new URL(
  "../../../../harness/status-server/react-app/src/runPipeline.ts",
  import.meta.url,
);
const source = await readFile(sourceUrl, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2020,
    target: ts.ScriptTarget.ES2020,
  },
  fileName: sourceUrl.pathname,
}).outputText;
const formatUrl = new URL(
  "../../../../harness/status-server/react-app/src/format.ts",
  import.meta.url,
);
const formatSource = await readFile(formatUrl, "utf8");
const formatCompiled = ts.transpileModule(formatSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2020,
    target: ts.ScriptTarget.ES2020,
  },
  fileName: formatUrl.pathname,
}).outputText;
const formatModuleUrl = `data:text/javascript;base64,${Buffer.from(formatCompiled).toString("base64")}`;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  compiled.replace('from "./format"', `from "${formatModuleUrl}"`),
).toString("base64")}`;
const { pipelineStages, resultAvailabilityCopy } = await import(moduleUrl);

assert.deepEqual(resultAvailabilityCopy("", "report.md"), {
  title: "Deliverable available",
  summary: "report.md is available; verification is still in progress.",
  ctaLabel: "Open deliverable",
  accepted: false,
});
assert.deepEqual(resultAvailabilityCopy("success", "report.md"), {
  title: "Result is ready",
  summary: "report.md is ready to open.",
  ctaLabel: "Open result",
  accepted: true,
});

const stages = pipelineStages(
  "planning_complete",
  "active",
  false,
  "",
  "",
  "",
  "builder",
);
assert.deepEqual(stages, [
  { role: "pm", state: "done" },
  { role: "planner", state: "done" },
  { role: "builder", state: "active" },
  { role: "evaluator", state: "pending" },
]);

assert.deepEqual(
  pipelineStages("planning_complete", "active", false, "", ""),
  [
    { role: "pm", state: "done" },
    { role: "planner", state: "active" },
    { role: "builder", state: "pending" },
    { role: "evaluator", state: "pending" },
  ],
);
assert.deepEqual(
  pipelineStages("planning_complete", "active", false, "", "", "", "evaluator"),
  [
    { role: "pm", state: "done" },
    { role: "planner", state: "done" },
    { role: "builder", state: "done" },
    { role: "evaluator", state: "active" },
  ],
);
assert.deepEqual(
  pipelineStages(
    "planning_complete",
    "active",
    false,
    "",
    "plan_review",
    "",
    "evaluator",
  ),
  [
    { role: "pm", state: "done" },
    { role: "planner", state: "active" },
    { role: "builder", state: "pending" },
    { role: "evaluator", state: "pending" },
  ],
);
assert.ok(
  pipelineStages("completed", "passed", false, "success", "").every(
    (stage) => stage.state === "done",
  ),
);

console.log("runPipeline: active-node role authority passed");
