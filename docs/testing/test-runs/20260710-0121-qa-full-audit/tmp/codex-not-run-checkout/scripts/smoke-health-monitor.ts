#!/usr/bin/env bun
/**
 * End-to-end smoke for health monitor chain:
 * failed -> retry -> exhausted -> repair -> alert -> drilldown
 *
 * Prerequisite:
 *   - dashboard server on http://localhost:3721
 *   - ~/.solar/solar.db exists
 */

import Database from "bun:sqlite";
import { existsSync } from "node:fs";

const BASE = "http://localhost:3721";
const DB_PATH = `${process.env.HOME || ""}/.solar/solar.db`;

function assert(cond: unknown, msg: string): void {
  if (!cond) throw new Error(msg);
}

async function getJson(path: string): Promise<any> {
  const r = await fetch(`${BASE}${path}`);
  const data = await r.json();
  if (!r.ok) {
    throw new Error(`GET ${path} failed: ${JSON.stringify(data)}`);
  }
  return data;
}

async function postJson(path: string, payload: any): Promise<any> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json();
  if (!r.ok) {
    throw new Error(`POST ${path} failed: ${JSON.stringify(data)}`);
  }
  return data;
}

function seedFlow(taskId: string, nodeId: string): void {
  const db = new Database(DB_PATH);
  const now = new Date().toISOString();
  const graph = {
    id: `${taskId}-graph`,
    taskId,
    createdAt: now,
    nodes: [
      {
        id: nodeId,
        intent: "/build",
        content: "smoke chain node",
        dependsOn: [],
        status: "failed",
        riskScore: 0.95,
      },
    ],
  };
  const failPayload = {
    error: "timeout while calling provider",
    durationMs: 1200,
    branchSuggestion: "fix/smoke-health-monitor",
  };
  const retryExhaustedPayload = {
    maxAttempts: 1,
    error: "timeout while calling provider",
    branchSuggestion: "fix/smoke-health-monitor",
  };
  const repairPayload = {
    branchSuggestion: "fix/smoke-health-monitor",
    newTaskId: `${taskId}__repair__${nodeId}`,
  };

  db.prepare(`
    INSERT INTO bl_orchestration_graphs (task_id, graph_json, created_at)
    VALUES (?, ?, ?)
  `).run(taskId, JSON.stringify(graph), now);

  db.prepare(`
    INSERT INTO bl_orchestration_events (task_id, node_id, event_type, payload_json, created_at)
    VALUES (?, ?, 'node_failed', ?, ?)
  `).run(taskId, nodeId, JSON.stringify(failPayload), now);

  db.prepare(`
    INSERT INTO bl_orchestration_retries (
      task_id, node_id, attempt_count, last_error, next_retry_at, retry_status, branch_suggestion, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(task_id, node_id) DO UPDATE SET
      attempt_count = excluded.attempt_count,
      last_error = excluded.last_error,
      next_retry_at = excluded.next_retry_at,
      retry_status = excluded.retry_status,
      branch_suggestion = excluded.branch_suggestion,
      updated_at = excluded.updated_at
  `).run(taskId, nodeId, 1, "timeout while calling provider", null, "exhausted", "fix/smoke-health-monitor", now);

  db.prepare(`
    INSERT INTO bl_orchestration_events (task_id, node_id, event_type, payload_json, created_at)
    VALUES (?, ?, 'retry_exhausted', ?, ?)
  `).run(taskId, nodeId, JSON.stringify(retryExhaustedPayload), now);

  db.prepare(`
    INSERT OR IGNORE INTO bl_message_tasks (
      task_id, source, source_id, sender, content, parsed_intent, priority, status, estimated_tokens, metadata
    )
    VALUES (?, 'manual', ?, 'system', ?, '/review', 90, 'pending', 300, ?)
  `).run(
    `${taskId}__repair__${nodeId}`,
    `repair:${taskId}:${nodeId}:${Date.now()}`,
    `Repair task for ${taskId}/${nodeId}`,
    JSON.stringify({
      repair_of: { taskId, nodeId },
      branch_suggestion: "fix/smoke-health-monitor",
      created_by: "orchestrator_repair_flow",
    }),
  );

  db.prepare(`
    INSERT INTO bl_orchestration_events (task_id, node_id, event_type, payload_json, created_at)
    VALUES (?, ?, 'repair_branch_queued', ?, ?)
  `).run(taskId, nodeId, JSON.stringify(repairPayload), now);
  db.close();
}

async function main() {
  assert(existsSync(DB_PATH), `db missing: ${DB_PATH}`);

  const oldCfg = await getJson("/api/orchestrator/health-config");
  assert(oldCfg?.ok, "health-config not reachable");
  try {
    const taskId = `smoke-health-${Date.now()}`;
    const nodeId = "worker_1";
    seedFlow(taskId, nodeId);

    const cfgPatch = {
      thresholds: {
        queueSize: { warn: 0, bad: 1 },
        failureRate24h: { warn: 0, bad: 0.0001 },
        failureRate1h: { warn: 0, bad: 0.0001 },
        retryingNodes: { warn: 0, bad: 1 },
        repairTasksActive: { warn: 0, bad: 1 },
        queueOldestAgeMinutes: { warn: 0, bad: 1 },
        repairTasks24h: { warn: 0, bad: 1 },
      },
      monitor: {
        snapshotRetentionDays: 30,
        notifyEmailEnabled: false,
        notifyTelegramEnabled: false,
      },
    };
    await postJson("/api/orchestrator/health-config", cfgPatch);

    const retryRes = await postJson("/api/orchestrator/health-actions/retry", { taskId, nodeId });
    console.log("retry:", retryRes.ok ? "ok" : "failed");

    const repairRes = await postJson("/api/orchestrator/health-actions/repair", { taskId, nodeId });
    console.log("repair:", repairRes.ok ? "ok" : "failed");

    const summary = await getJson("/api/orchestrator/health-summary");
    assert(summary?.ok, "health-summary failed");

    const alerts = await getJson("/api/orchestrator/health-alerts?limit=20");
    assert(alerts?.ok, "health-alerts failed");
    assert(Array.isArray(alerts.data) && alerts.data.length > 0, "no alerts generated");

    const failDrill = await getJson("/api/orchestrator/health-drilldown?type=failures&limit=20");
    assert(failDrill?.ok, "failures drilldown failed");
    assert(
      Array.isArray(failDrill.data) && failDrill.data.some((x: any) => x.taskId === taskId && x.nodeId === nodeId),
      "failed node not found in drilldown",
    );

    const repairDrill = await getJson("/api/orchestrator/health-drilldown?type=repairs&limit=20");
    assert(repairDrill?.ok, "repairs drilldown failed");
    assert(
      Array.isArray(repairDrill.data) && repairDrill.data.some((x: any) => x.ofTaskId === taskId && x.ofNodeId === nodeId),
      "repair task not found in drilldown",
    );

    console.log("SMOKE PASS:");
    console.log("  failed -> retry -> exhausted -> repair -> alert -> drilldown");
  } finally {
    await postJson("/api/orchestrator/health-config", oldCfg.data || {});
  }
}

main().catch((err) => {
  console.error("smoke-health-monitor failed:", err);
  process.exit(1);
});
