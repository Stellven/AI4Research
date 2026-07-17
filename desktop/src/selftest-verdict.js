"use strict";

const REQUIRED_DASHBOARD_TEXT = ["What do you want done?", "Settings"];
const REQUIRED_SIGNIN_TEXT = [
  "Sign in to run Solar",
  "Use my existing sign-in",
  "Continue without signing in",
];
const RUNTIME_UI_CONTRACTS = [
  { id: "dashboard", requiredText: REQUIRED_DASHBOARD_TEXT },
  { id: "signin", requiredText: REQUIRED_SIGNIN_TEXT },
];

function parseURL(value) {
  try {
    return new URL(String(value || ""));
  } catch {
    return null;
  }
}

function assessSelftestSnapshot(snapshot) {
  const contracts = Array.isArray(snapshot.requiredText)
    ? [{ id: "custom", requiredText: snapshot.requiredText }]
    : RUNTIME_UI_CONTRACTS;
  const bodyText = String(snapshot.bodyText || "");
  const rendererErrors = Array.isArray(snapshot.rendererErrors)
    ? snapshot.rendererErrors.filter(Boolean).map(String)
    : [];
  const reasons = [];

  if (snapshot.fallbackUsed) reasons.push("fallback_renderer_loaded");

  const expected = parseURL(snapshot.expectedURL);
  const actual = parseURL(snapshot.actualURL);
  if (!expected) reasons.push("invalid_expected_url");
  if (!actual || !["http:", "https:"].includes(actual.protocol)) {
    reasons.push("unexpected_protocol");
  }
  if (!expected || !actual || actual.origin !== expected.origin) {
    reasons.push("unexpected_origin");
  }
  if (!new Set(["interactive", "complete"]).has(snapshot.readyState)) {
    reasons.push("document_not_ready");
  }
  if (!Number.isInteger(snapshot.rootChildCount) || snapshot.rootChildCount < 1) {
    reasons.push("dashboard_root_empty");
  }

  const matched = contracts.find((contract) =>
    contract.requiredText.every((text) => bodyText.includes(text)),
  );
  const missingText = Object.fromEntries(
    contracts.map((contract) => [
      contract.id,
      contract.requiredText.filter((text) => !bodyText.includes(text)),
    ]),
  );
  if (!matched) reasons.push("required_text_missing");
  if (rendererErrors.length) reasons.push("renderer_errors_present");

  return {
    ok: reasons.length === 0,
    reasons,
    expectedOrigin: expected ? expected.origin : null,
    actualOrigin: actual ? actual.origin : null,
    readyState: String(snapshot.readyState || ""),
    rootChildCount: Number(snapshot.rootChildCount || 0),
    bodyTextLength: bodyText.length,
    matchedContract: matched ? matched.id : null,
    missingText,
    rendererErrors,
    fallbackUsed: Boolean(snapshot.fallbackUsed),
  };
}

module.exports = {
  REQUIRED_DASHBOARD_TEXT,
  REQUIRED_SIGNIN_TEXT,
  RUNTIME_UI_CONTRACTS,
  assessSelftestSnapshot,
};
