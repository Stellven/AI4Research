import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const requireFromApp = createRequire(
  new URL("../../../../harness/status-server/react-app/package.json", import.meta.url),
);
const ts = requireFromApp("typescript");
const sourceUrl = new URL(
  "../../../../harness/status-server/react-app/src/api.ts",
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

const originalFetch = globalThis.fetch;
const originalLocation = globalThis.location;
const originalWindow = globalThis.window;
const calls = [];
const responses = [
  {
    ok: true,
    status: "accepted",
    request_id: "webapp-intake-contract",
    terminal: false,
    poll_after_ms: 1,
  },
  new TypeError("Failed to fetch"),
  {
    ok: true,
    status: "running",
    request_id: "webapp-intake-contract",
    job_status: "running",
    terminal: false,
    poll_after_ms: 1,
  },
  {
    ok: true,
    status: "ok",
    request_id: "webapp-intake-contract",
    job_status: "succeeded",
    terminal: true,
    sprint_id: "sprint-async-contract",
  },
];

globalThis.location = { search: "" };
globalThis.window = {
  __SOLAR_TOKEN__: "",
  setTimeout(callback) {
    callback();
    return 1;
  },
};
globalThis.fetch = async (url, init = {}) => {
  calls.push({ url, init });
  const payload = responses.shift();
  assert.ok(payload, "unexpected extra fetch");
  if (payload instanceof Error) throw payload;
  return {
    ok: true,
    status: calls.length === 1 ? 202 : 200,
    async json() {
      return payload;
    },
  };
};

try {
  const executable = compiled.replace('import.meta.env.VITE_API_BASE', '""');
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(executable).toString("base64")}`;
  const { submitIntake } = await import(moduleUrl);
  const result = await submitIntake("test async intake");

  assert.equal(result.sprint_id, "sprint-async-contract");
  assert.equal(result.job_status, "succeeded");
  assert.equal(calls.length, 4);
  assert.equal(calls[0].url, "/intake");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[1].url, "/intake/webapp-intake-contract");
  assert.equal(calls[2].url, "/intake/webapp-intake-contract");
  assert.equal(calls[3].url, "/intake/webapp-intake-contract");
} finally {
  globalThis.fetch = originalFetch;
  globalThis.location = originalLocation;
  globalThis.window = originalWindow;
}

console.log("intake api: transient polling failure retried to terminal result");
