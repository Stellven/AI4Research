import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFile } from "node:fs/promises";
import ts from "typescript";


const sourceUrl = new URL("../src/nodeActor.ts", import.meta.url);
const source = await readFile(sourceUrl, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2020,
    target: ts.ScriptTarget.ES2020,
  },
  fileName: sourceUrl.pathname,
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`;
const { activeNodeActor, nodeActor } = await import(moduleUrl);

const cases = [
  [{ id: "S1", logical_operator: "ImplementationWorker" }, "Builder"],
  [{ id: "S2", logical_operator: "TestRunner" }, "Evaluator"],
  [{ id: "S3", logical_operator: "Verifier" }, "Evaluator"],
  [{ id: "N0", logical_operator: "DeepArchitect" }, "Planner"],
  [{ id: "N1", logical_operator: "RequirementAnalyst" }, "PM"],
  [{ id: "N2", requested_role: "builder" }, "Builder"],
  [{ id: "N3", target_role: "evaluator" }, "Evaluator"],
  [
    {
      id: "opaque",
      executable_node: {
        schema_version: "solar.executable_node.v1",
        logical_operator: "Critic",
        dispatch_role: "evaluator",
      },
    },
    "Evaluator",
  ],
  [{ id: "S1", owner: "builder_main", task_type: "implementation" }, "Builder"],
  [{ id: "S3", owner: "builder_main", task_type: "tests" }, "Builder"],
  [{ id: "S4", owner: "verifier", task_type: "verification" }, "Evaluator"],
  [{ id: "opaque", dispatch_task_type: "implementation" }, "Builder"],
  [{ id: "opaque", owner: "latest-builder" }, "Builder"],
  [
    {
      id: "S3",
      logical_operator: "Verifier",
      required_capabilities: ["planning"],
    },
    "Evaluator",
  ],
  [
    {
      id: "build-looking-id",
      logical_operator: "Verifier",
      required_capabilities: ["implementation"],
    },
    "Evaluator",
  ],
  [{ id: "build-step", required_capabilities: ["code"] }, "Builder"],
  [{ id: "review-step", required_capabilities: ["acceptance"] }, "Evaluator"],
  [{ id: "plan-step", required_capabilities: ["design"] }, "Planner"],
  [{ id: "scope-step", required_capabilities: ["intake"] }, "PM"],
];

for (const [node, expected] of cases) {
  assert.equal(nodeActor(node), expected, JSON.stringify(node));
}

assert.equal(
  activeNodeActor({
    id: "S1",
    status: "active",
    workflow_status: "reviewing",
    owner: "builder_main",
  }),
  "Evaluator",
);
assert.equal(
  activeNodeActor({
    id: "S1",
    status: "active",
    workflow_status: "dispatched",
    owner: "builder_main",
  }),
  "Builder",
);
assert.equal(
  activeNodeActor({
    id: "S1",
    status: "active",
    workflow_status: "delegated",
    owner: "builder_main",
  }),
  "Builder",
);

console.log(`nodeActor: ${cases.length} cases passed`);
