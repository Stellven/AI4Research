#!/usr/bin/env node
"use strict";

const assert = require("assert");
const { assessSelftestSnapshot } = require("./selftest-verdict");

function healthy(overrides = {}) {
  return {
    expectedURL: "http://127.0.0.1:8765/",
    actualURL: "http://127.0.0.1:8765/",
    readyState: "complete",
    rootChildCount: 1,
    bodyText: "AI4Research\nWhat do you want done?\nSettings\nStart work",
    rendererErrors: [],
    fallbackUsed: false,
    ...overrides,
  };
}

const cases = [
  ["real runtime dashboard passes", healthy(), true, []],
  [
    "real runtime sign-in screen passes on a fresh machine",
    healthy({
      bodyText:
        "Sign in to run Solar\nUse my existing sign-in\nSign in with a device code\nContinue without signing in",
    }),
    true,
    [],
  ],
  [
    "dashboard-only smoke rejects a sign-in screen",
    healthy({
      requiredContract: "dashboard",
      bodyText:
        "Sign in to run Solar\nUse my existing sign-in\nContinue without signing in",
      targetMarkers: {
        homeLanding: false,
        authChecking: false,
        taskInputAccessibleName: "",
      },
    }),
    false,
    ["required_text_missing", "dashboard_target_markers_missing"],
  ],
  [
    "dashboard-only smoke requires target markers and named task input",
    healthy({
      requiredContract: "dashboard",
      targetMarkers: {
        homeLanding: true,
        authChecking: false,
        taskInputAccessibleName: "What do you want done?",
      },
    }),
    true,
    [],
  ],
  [
    "blank page fails",
    healthy({ rootChildCount: 0, bodyText: "" }),
    false,
    ["dashboard_root_empty", "required_text_missing"],
  ],
  [
    "wrong origin fails",
    healthy({ actualURL: "http://127.0.0.1:9999/" }),
    false,
    ["unexpected_origin"],
  ],
  [
    "bundled fallback cannot prove runtime dashboard",
    healthy({ actualURL: "app://index.html", fallbackUsed: true }),
    false,
    ["fallback_renderer_loaded", "unexpected_protocol", "unexpected_origin"],
  ],
  [
    "control error page fails even after load",
    healthy({
      actualURL: "data:text/html,error",
      rootChildCount: 0,
      bodyText: "Couldn't start Solar Retry",
    }),
    false,
    ["unexpected_protocol", "unexpected_origin", "dashboard_root_empty"],
  ],
  [
    "uncaught renderer error fails",
    healthy({ rendererErrors: ["ReferenceError: missingSymbol is not defined"] }),
    false,
    ["renderer_errors_present"],
  ],
];

let passed = 0;
for (const [name, input, expectedOK, expectedReasons] of cases) {
  const result = assessSelftestSnapshot(input);
  assert.strictEqual(result.ok, expectedOK, `${name}: ${JSON.stringify(result)}`);
  for (const reason of expectedReasons) {
    assert.ok(result.reasons.includes(reason), `${name}: missing ${reason}`);
  }
  console.log(`PASS  ${name}`);
  passed += 1;
}

console.log(`SELFTEST VERDICT TEST PASS (${passed}/${cases.length})`);
