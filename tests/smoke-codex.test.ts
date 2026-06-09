import { expect, test } from "bun:test";
import { runCodexSmoke, SMOKE_RESPONSE, SMOKE_REQUEST_MARKER, CALL_CHAIN } from "../core/codex-smoke";

test("installed solar codex smoke request returns the expected greeting", () => {
  const result = runCodexSmoke(SMOKE_REQUEST_MARKER);

  expect(result.ok).toBe(true);
  expect(result.request).toBe(SMOKE_REQUEST_MARKER);
  expect(result.response).toBe(SMOKE_RESPONSE);
  expect(result.callChain.join(" > ")).toContain("runCodexSmoke");
  expect(result.callChain).toEqual(CALL_CHAIN);
});

test("unknown request returns failure with clear error response", () => {
  const result = runCodexSmoke("unknown request");

  expect(result.ok).toBe(false);
  expect(result.response).toContain("Unknown smoke request");
  expect(result.callChain).toEqual(CALL_CHAIN);
});
