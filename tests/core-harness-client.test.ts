import { expect, test } from "bun:test";
import {
  CORE_TO_HARNESS_SCHEMA_VERSION,
  buildCaptureArgs,
  buildConsumeArgs,
  renderCoreRequestEnvelope,
  validateCoreToHarnessRequest,
  type CoreToHarnessRequest,
} from "../core/harness";

const request: CoreToHarnessRequest = {
  schema_version: CORE_TO_HARNESS_SCHEMA_VERSION,
  request_id: "intent-test-core-harness",
  created_at: "2026-06-08T00:00:00Z",
  source: {
    channel: "codex_app",
    actor: "user",
    device: "mac",
    session_id: "session-1",
    thread_ref: "thread-1",
    source_trust: "user_direct",
  },
  workspace: {
    repo: "/repo",
    cwd: "/repo",
    knowledge_query: "core harness migration",
  },
  routing: {
    mode: "delivery",
    urgency: "normal",
    allow_autodispatch: false,
    requires_human_confirm: true,
    require_research_artifact: false,
  },
  raw_input: {
    text: "Switch Core from Claude to Codex.",
    attachments: ["/tmp/context.md"],
    quoted_context: ["prior thread summary"],
  },
  core_analysis: {
    title: "Codex Core migration",
    objective: "Route Core requests through Harness RawIntent.",
    constraints: ["Do not change Harness interfaces."],
    acceptance: ["Capture returns an intent_id."],
    suggested_logical_operators: ["RequirementCompiler", "Planner"],
  },
  consume: {
    enabled: true,
    dispatch_planner: true,
    auto_dispatch_planner: false,
  },
};

test("validates required CoreToHarness fields", () => {
  expect(validateCoreToHarnessRequest(request)).toEqual([]);
  expect(validateCoreToHarnessRequest({ ...request, request_id: "" })).toContain("request_id is required");
});

test("renders soft Core fields into markdown envelope", () => {
  const envelope = renderCoreRequestEnvelope(request);
  expect(envelope).toContain("# Solar Core Request");
  expect(envelope).toContain("Switch Core from Claude to Codex.");
  expect(envelope).toContain("Route Core requests through Harness RawIntent.");
  expect(envelope).toContain("- RequirementCompiler");
});

test("maps hard Core fields to existing intent_gateway flags", () => {
  const args = buildCaptureArgs(request, "/tmp/request.md", "/repo/harness");
  expect(args).toContain("/repo/harness/lib/intent_gateway.py");
  expect(args).toContain("capture");
  expect(args).toContain("--source-channel");
  expect(args).toContain("codex_app");
  expect(args).toContain("--no-autodispatch");
  expect(args).toContain("--requires-human-confirm");
  expect(args).toContain("--file");
  expect(args).toContain("/tmp/request.md");
});

test("maps consume policy to existing intent_consumer flags", () => {
  const args = buildConsumeArgs(request, "intent-test-core-harness", "/repo/harness");
  expect(args).toContain("/repo/harness/lib/intent_consumer.py");
  expect(args).toContain("consume");
  expect(args).toContain("--dispatch-planner");
  expect(args).toContain("--no-auto-dispatch-planner");
});

