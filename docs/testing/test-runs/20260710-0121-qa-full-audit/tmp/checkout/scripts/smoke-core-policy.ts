#!/usr/bin/env bun
/**
 * Smoke test for Solar-MAX core policy API.
 * Auto-syncs daemon + dashboard server before API checks.
 */

import { spawnSync } from "node:child_process";

const BASE = "http://127.0.0.1:3721";
const ENSURE_SCRIPT = "scripts/ensure-background-services.sh";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ensureBackgroundServices(): void {
  const r = spawnSync("bash", [ENSURE_SCRIPT], {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (r.status !== 0) {
    throw new Error(
      `ensure-background-services failed (code=${r.status}):\n${r.stdout || ""}\n${r.stderr || ""}`.trim(),
    );
  }
}

async function waitForCorePolicyApi(maxAttempts = 20, intervalMs = 500): Promise<void> {
  let lastError = "";
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const r = await fetch(`${BASE}/api/orchestrator/core-policy`);
      if (r.ok) return;
      lastError = `status=${r.status}`;
    } catch (e: any) {
      lastError = String(e?.message || e);
    }
    await sleep(intervalMs);
  }
  throw new Error(
    `core-policy API not ready at ${BASE}/api/orchestrator/core-policy after ${
      maxAttempts * intervalMs
    }ms, lastError=${lastError}`,
  );
}

async function getJson(path: string): Promise<any> {
  const r = await fetch(`${BASE}${path}`);
  const data = await r.json();
  if (!r.ok) throw new Error(`GET ${path} failed: ${JSON.stringify(data)}`);
  return data;
}

async function postJson(path: string, payload: any): Promise<any> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`POST ${path} failed: ${JSON.stringify(data)}`);
  return data;
}

async function main() {
  ensureBackgroundServices();
  await waitForCorePolicyApi();

  const oldRes = await getJson("/api/orchestrator/core-policy");
  if (!oldRes?.ok || !oldRes?.data?.ok || !oldRes?.data?.policy) {
    throw new Error("core-policy get failed");
  }
  const oldPolicy = oldRes.data.policy;

  try {
    const newRounds = Number(oldPolicy?.rolePolicy?.debate?.defaultDebateRounds || 2) + 1;
    const patch = {
      rolePolicy: {
        debate: {
          defaultDebateRounds: newRounds,
        },
      },
    };
    const setRes = await postJson("/api/orchestrator/core-policy", patch);
    if (!setRes?.ok || !setRes?.data?.ok) throw new Error("core-policy set failed");
    const now = setRes?.data?.policy?.rolePolicy?.debate?.defaultDebateRounds;
    if (now !== newRounds) {
      throw new Error(`core-policy mismatch expected=${newRounds} got=${now}`);
    }
    console.log("core-policy update ok:", now);
  } finally {
    await postJson("/api/orchestrator/core-policy", oldPolicy);
  }

  console.log("SMOKE PASS: core-policy get/set/restore");
}

main().catch((err) => {
  console.error("smoke-core-policy failed:", err);
  process.exit(1);
});
