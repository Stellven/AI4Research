import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const requireFromApp = createRequire(
  new URL("../../../../harness/status-server/react-app/package.json", import.meta.url),
);
const ts = requireFromApp("typescript");
const sourceUrl = new URL(
  "../../../../harness/status-server/react-app/src/runUsage.ts",
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
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`;
const { perRunUsageLabel } = await import(moduleUrl);

assert.equal(perRunUsageLabel(undefined), "unavailable per run");
assert.equal(
  perRunUsageLabel({ availability: "unavailable", not_per_sprint: true }),
  "unavailable per run",
);
assert.equal(
  perRunUsageLabel({ availability: "available", not_per_sprint: true }),
  "not reported per run",
);
assert.equal(
  perRunUsageLabel({
    availability: "available",
    not_per_sprint: false,
    total_used_tokens_label: "1.2K tokens",
  }),
  "1.2K tokens",
);

console.log("runUsage: per-run usage truthfulness passed");
