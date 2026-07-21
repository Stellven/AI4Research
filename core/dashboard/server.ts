/**
 * Solar Dashboard Server
 *
 * 提供：
 * 1. 旧版 Dashboard 页面与状态 API
 * 2. Orchestrator Web 面板（事件监控 + 控制）
 */

import Database from "bun:sqlite";
import { existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { ReplySender } from "../reply/reply-sender";

const SOLAR_HOME =
  process.env.SOLAR_HOME ||
  (process.env.HOME ? `${process.env.HOME}/.solar` : "/tmp/solar");
const STATE_FILE =
  process.env.SOLAR_DASHBOARD_STATE_PATH ||
  `${SOLAR_HOME}/dashboard/state.json`;
const ORCH_DASHBOARD_FILE = Bun.file(
  import.meta.dir + "/assets/orchestrator-dashboard.html",
);
const PORT = 3721;
const DAEMON_SOCKET = "/tmp/solar.sock";
const SOLAR_DB_PATH =
  process.env.SOLAR_DB_PATH || `${process.env.HOME || ""}/.solar/db/solar.db`;
const HEALTH_CONFIG_ID = 1;
const HEALTH_ALERT_COOLDOWN_MINUTES_DEFAULT = 15;
const HEALTH_MONITOR_INTERVAL_SECONDS_DEFAULT = 60;
const DEFAULT_STATE = {
  lastUpdate: null,
  status: {
    phase: "idle",
    phaseName: "Idle",
    activeAgent: null,
    rateLimit: null,
    rateLimitStatus: "unknown",
  },
  tasks: [],
  conversations: [],
  agents: [],
  activity: [],
};

type HealthThresholdBand = { warn: number; bad: number };
type HealthThresholdConfig = {
  queueSize: HealthThresholdBand;
  failureRate24h: HealthThresholdBand;
  failureRate1h: HealthThresholdBand;
  retryingNodes: HealthThresholdBand;
  repairTasksActive: HealthThresholdBand;
  queueOldestAgeMinutes: HealthThresholdBand;
  repairTasks24h: HealthThresholdBand;
};
type HealthMonitorConfig = {
  intervalSeconds: number;
  alertCooldownMinutes: number;
  enableSystemMessageTask: boolean;
  snapshotRetentionDays: number;
  notifyTelegramEnabled: boolean;
  notifyTelegramChatId: string;
  notifyEmailEnabled: boolean;
  notifyEmailTo: string;
};
type HealthConfig = {
  thresholds: HealthThresholdConfig;
  monitor: HealthMonitorConfig;
};

const DEFAULT_HEALTH_CONFIG: HealthConfig = {
  thresholds: {
    queueSize: { warn: 50, bad: 200 },
    failureRate24h: { warn: 0.05, bad: 0.15 },
    failureRate1h: { warn: 0.05, bad: 0.15 },
    retryingNodes: { warn: 2, bad: 10 },
    repairTasksActive: { warn: 1, bad: 5 },
    queueOldestAgeMinutes: { warn: 10, bad: 60 },
    repairTasks24h: { warn: 2, bad: 8 },
  },
  monitor: {
    intervalSeconds: HEALTH_MONITOR_INTERVAL_SECONDS_DEFAULT,
    alertCooldownMinutes: HEALTH_ALERT_COOLDOWN_MINUTES_DEFAULT,
    enableSystemMessageTask: true,
    snapshotRetentionDays: 30,
    notifyTelegramEnabled: false,
    notifyTelegramChatId: "",
    notifyEmailEnabled: false,
    notifyEmailTo: "",
  },
};

const notifier = new ReplySender();

function toIsoHoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
}

function openSolarDb(): Database | null {
  try {
    if (!SOLAR_DB_PATH || !existsSync(SOLAR_DB_PATH)) return null;
    return new Database(SOLAR_DB_PATH, { readonly: true });
  } catch {
    return null;
  }
}

function openSolarDbRW(): Database | null {
  try {
    if (!SOLAR_DB_PATH || !existsSync(SOLAR_DB_PATH)) return null;
    return new Database(SOLAR_DB_PATH);
  } catch {
    return null;
  }
}

function clampBand(
  b: Partial<HealthThresholdBand>,
  fallback: HealthThresholdBand,
): HealthThresholdBand {
  const warn = Number.isFinite(Number(b.warn)) ? Number(b.warn) : fallback.warn;
  const badRaw = Number.isFinite(Number(b.bad)) ? Number(b.bad) : fallback.bad;
  const bad = badRaw < warn ? warn : badRaw;
  return { warn, bad };
}

function normalizeHealthConfig(
  raw: Partial<HealthConfig> | null | undefined,
): HealthConfig {
  const t = raw?.thresholds || {};
  const m = raw?.monitor || {};
  return {
    thresholds: {
      queueSize: clampBand(
        t.queueSize || {},
        DEFAULT_HEALTH_CONFIG.thresholds.queueSize,
      ),
      failureRate24h: clampBand(
        t.failureRate24h || {},
        DEFAULT_HEALTH_CONFIG.thresholds.failureRate24h,
      ),
      failureRate1h: clampBand(
        t.failureRate1h || {},
        DEFAULT_HEALTH_CONFIG.thresholds.failureRate1h,
      ),
      retryingNodes: clampBand(
        t.retryingNodes || {},
        DEFAULT_HEALTH_CONFIG.thresholds.retryingNodes,
      ),
      repairTasksActive: clampBand(
        t.repairTasksActive || {},
        DEFAULT_HEALTH_CONFIG.thresholds.repairTasksActive,
      ),
      queueOldestAgeMinutes: clampBand(
        t.queueOldestAgeMinutes || {},
        DEFAULT_HEALTH_CONFIG.thresholds.queueOldestAgeMinutes,
      ),
      repairTasks24h: clampBand(
        t.repairTasks24h || {},
        DEFAULT_HEALTH_CONFIG.thresholds.repairTasks24h,
      ),
    },
    monitor: {
      intervalSeconds: Math.max(
        10,
        Math.floor(
          Number(
            m.intervalSeconds ?? DEFAULT_HEALTH_CONFIG.monitor.intervalSeconds,
          ),
        ),
      ),
      alertCooldownMinutes: Math.max(
        1,
        Math.floor(
          Number(
            m.alertCooldownMinutes ??
              DEFAULT_HEALTH_CONFIG.monitor.alertCooldownMinutes,
          ),
        ),
      ),
      enableSystemMessageTask:
        typeof m.enableSystemMessageTask === "boolean"
          ? m.enableSystemMessageTask
          : DEFAULT_HEALTH_CONFIG.monitor.enableSystemMessageTask,
      snapshotRetentionDays: Math.max(
        1,
        Math.floor(
          Number(
            m.snapshotRetentionDays ??
              DEFAULT_HEALTH_CONFIG.monitor.snapshotRetentionDays,
          ),
        ),
      ),
      notifyTelegramEnabled:
        typeof m.notifyTelegramEnabled === "boolean"
          ? m.notifyTelegramEnabled
          : DEFAULT_HEALTH_CONFIG.monitor.notifyTelegramEnabled,
      notifyTelegramChatId: String(
        m.notifyTelegramChatId ??
          DEFAULT_HEALTH_CONFIG.monitor.notifyTelegramChatId,
      ),
      notifyEmailEnabled:
        typeof m.notifyEmailEnabled === "boolean"
          ? m.notifyEmailEnabled
          : DEFAULT_HEALTH_CONFIG.monitor.notifyEmailEnabled,
      notifyEmailTo: String(
        m.notifyEmailTo ?? DEFAULT_HEALTH_CONFIG.monitor.notifyEmailTo,
      ),
    },
  };
}

function initHealthInfra(): void {
  const db = openSolarDbRW();
  if (!db) return;
  try {
    db.run(`
      CREATE TABLE IF NOT EXISTS bl_orchestrator_health_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        config_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    db.run(`
      CREATE TABLE IF NOT EXISTS bl_orchestrator_health_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sampled_at TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        summary_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
    `);
    db.run(`
      CREATE INDEX IF NOT EXISTS idx_orch_health_snapshots_sampled_at
      ON bl_orchestrator_health_snapshots(sampled_at)
    `);
    db.run(`
      CREATE TABLE IF NOT EXISTS bl_orchestrator_health_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_key TEXT NOT NULL,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved INTEGER NOT NULL DEFAULT 0
      )
    `);
    db.run(`
      CREATE INDEX IF NOT EXISTS idx_orch_health_alerts_rule_created
      ON bl_orchestrator_health_alerts(rule_key, created_at)
    `);
    db.prepare(
      `
      INSERT OR IGNORE INTO bl_orchestrator_health_config (id, config_json, updated_at)
      VALUES (?, ?, ?)
    `,
    ).run(
      HEALTH_CONFIG_ID,
      JSON.stringify(DEFAULT_HEALTH_CONFIG),
      new Date().toISOString(),
    );
  } finally {
    db.close();
  }
}

function getHealthConfig(): HealthConfig {
  const db = openSolarDbRW();
  if (!db) return DEFAULT_HEALTH_CONFIG;
  try {
    const row = db
      .prepare(
        `
      SELECT config_json
      FROM bl_orchestrator_health_config
      WHERE id = ?
      LIMIT 1
    `,
      )
      .get(HEALTH_CONFIG_ID) as { config_json?: string } | null;
    if (!row?.config_json) return DEFAULT_HEALTH_CONFIG;
    try {
      return normalizeHealthConfig(JSON.parse(row.config_json));
    } catch {
      return DEFAULT_HEALTH_CONFIG;
    }
  } finally {
    db.close();
  }
}

function updateHealthConfig(patch: Partial<HealthConfig>): HealthConfig {
  const db = openSolarDbRW();
  if (!db) return DEFAULT_HEALTH_CONFIG;
  try {
    const base = getHealthConfig();
    const merged = normalizeHealthConfig({
      thresholds: { ...base.thresholds, ...(patch.thresholds || {}) },
      monitor: { ...base.monitor, ...(patch.monitor || {}) },
    });
    db.prepare(
      `
      INSERT INTO bl_orchestrator_health_config (id, config_json, updated_at)
      VALUES (?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        config_json = excluded.config_json,
        updated_at = excluded.updated_at
    `,
    ).run(HEALTH_CONFIG_ID, JSON.stringify(merged), new Date().toISOString());
    return merged;
  } finally {
    db.close();
  }
}

function severityByBand(
  value: number,
  band: HealthThresholdBand,
): "good" | "warn" | "bad" {
  if (value >= band.bad) return "bad";
  if (value >= band.warn) return "warn";
  return "good";
}

function genTaskId(prefix: string): string {
  return `${prefix}-${new Date().toISOString().replace(/[-:.TZ]/g, "")}-${Math.random().toString(16).slice(2, 8)}`;
}

function getHealthSummary() {
  const db = openSolarDb();
  const out = {
    generatedAt: new Date().toISOString(),
    windowHours: 24,
    failureRate1h: {
      failed: 0,
      completed: 0,
      ratio: 0,
    },
    queueSize: 0,
    queueOldestAgeMinutes: 0,
    failureRate: {
      failed: 0,
      completed: 0,
      ratio: 0,
    },
    retryingNodes: 0,
    repairBranchTasks: 0,
    repairBranchTasks24h: 0,
  };
  if (!db) return out;

  try {
    const queueRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_message_tasks
      WHERE status IN ('pending', 'deferred', 'queued')
    `,
      )
      .get() as { count: number } | null;
    out.queueSize = queueRow?.count || 0;

    const oldestQueueRow = db
      .prepare(
        `
      SELECT created_at AS createdAt
      FROM bl_message_tasks
      WHERE status IN ('pending', 'deferred', 'queued')
      ORDER BY datetime(created_at) ASC
      LIMIT 1
    `,
      )
      .get() as { createdAt?: string | null } | null;
    if (oldestQueueRow?.createdAt) {
      const ms = Date.now() - new Date(oldestQueueRow.createdAt).getTime();
      out.queueOldestAgeMinutes = Math.max(0, Math.floor(ms / 60000));
    }
  } catch {}

  try {
    const sinceIso = toIsoHoursAgo(out.windowHours);
    const failedRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_orchestration_events
      WHERE event_type = 'node_failed' AND created_at >= ?
    `,
      )
      .get(sinceIso) as { count: number } | null;
    const completedRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_orchestration_events
      WHERE event_type = 'node_completed' AND created_at >= ?
    `,
      )
      .get(sinceIso) as { count: number } | null;
    const failed = failedRow?.count || 0;
    const completed = completedRow?.count || 0;
    const total = failed + completed;
    out.failureRate.failed = failed;
    out.failureRate.completed = completed;
    out.failureRate.ratio = total > 0 ? failed / total : 0;

    const since1h = toIsoHoursAgo(1);
    const failed1hRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_orchestration_events
      WHERE event_type = 'node_failed' AND created_at >= ?
    `,
      )
      .get(since1h) as { count: number } | null;
    const completed1hRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_orchestration_events
      WHERE event_type = 'node_completed' AND created_at >= ?
    `,
      )
      .get(since1h) as { count: number } | null;
    const failed1h = failed1hRow?.count || 0;
    const completed1h = completed1hRow?.count || 0;
    const total1h = failed1h + completed1h;
    out.failureRate1h.failed = failed1h;
    out.failureRate1h.completed = completed1h;
    out.failureRate1h.ratio = total1h > 0 ? failed1h / total1h : 0;
  } catch {}

  try {
    const retryRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_orchestration_retries
      WHERE retry_status IN ('pending_retry', 'retrying')
    `,
      )
      .get() as { count: number } | null;
    out.retryingNodes = retryRow?.count || 0;
  } catch {}

  try {
    const repairRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_message_tasks
      WHERE metadata LIKE '%"created_by":"orchestrator_repair_flow"%'
        AND status IN ('pending', 'deferred', 'queued', 'running', 'processing')
    `,
      )
      .get() as { count: number } | null;
    out.repairBranchTasks = repairRow?.count || 0;

    const repair24hRow = db
      .prepare(
        `
      SELECT COUNT(*) AS count
      FROM bl_message_tasks
      WHERE metadata LIKE '%"created_by":"orchestrator_repair_flow"%'
        AND created_at >= ?
    `,
      )
      .get(toIsoHoursAgo(24)) as { count: number } | null;
    out.repairBranchTasks24h = repair24hRow?.count || 0;
  } catch {}

  db.close();
  return out;
}

function calcHealthStatus(
  summary: ReturnType<typeof getHealthSummary>,
  cfg: HealthConfig,
): {
  status: "good" | "warn" | "bad";
  metrics: Array<{
    key: string;
    value: number;
    severity: "good" | "warn" | "bad";
    warn: number;
    bad: number;
  }>;
} {
  const metrics = [
    {
      key: "queueSize",
      value: Number(summary.queueSize || 0),
      band: cfg.thresholds.queueSize,
    },
    {
      key: "failureRate24h",
      value: Number(summary.failureRate?.ratio || 0),
      band: cfg.thresholds.failureRate24h,
    },
    {
      key: "failureRate1h",
      value: Number(summary.failureRate1h?.ratio || 0),
      band: cfg.thresholds.failureRate1h,
    },
    {
      key: "retryingNodes",
      value: Number(summary.retryingNodes || 0),
      band: cfg.thresholds.retryingNodes,
    },
    {
      key: "repairTasksActive",
      value: Number(summary.repairBranchTasks || 0),
      band: cfg.thresholds.repairTasksActive,
    },
    {
      key: "queueOldestAgeMinutes",
      value: Number(summary.queueOldestAgeMinutes || 0),
      band: cfg.thresholds.queueOldestAgeMinutes,
    },
    {
      key: "repairTasks24h",
      value: Number(summary.repairBranchTasks24h || 0),
      band: cfg.thresholds.repairTasks24h,
    },
  ].map((m) => ({
    key: m.key,
    value: m.value,
    severity: severityByBand(m.value, m.band),
    warn: m.band.warn,
    bad: m.band.bad,
  }));

  const hasBad = metrics.some((m) => m.severity === "bad");
  const hasWarn = metrics.some((m) => m.severity === "warn");
  return { status: hasBad ? "bad" : hasWarn ? "warn" : "good", metrics };
}

function maybeCreateAlertAndTask(
  db: Database,
  cfg: HealthConfig,
  ruleKey: string,
  level: "warn" | "bad",
  message: string,
  payload: Record<string, unknown>,
) {
  const cooldownMin =
    cfg.monitor.alertCooldownMinutes || HEALTH_ALERT_COOLDOWN_MINUTES_DEFAULT;
  const last = db
    .prepare(
      `
    SELECT created_at
    FROM bl_orchestrator_health_alerts
    WHERE rule_key = ? AND resolved = 0
    ORDER BY id DESC
    LIMIT 1
  `,
    )
    .get(ruleKey) as { created_at?: string } | null;
  if (last?.created_at) {
    const deltaMin = (Date.now() - new Date(last.created_at).getTime()) / 60000;
    if (Number.isFinite(deltaMin) && deltaMin < cooldownMin) return;
  }

  const createdAt = new Date().toISOString();
  db.prepare(
    `
    INSERT INTO bl_orchestrator_health_alerts (rule_key, level, message, payload_json, created_at, resolved)
    VALUES (?, ?, ?, ?, ?, 0)
  `,
  ).run(ruleKey, level, message, JSON.stringify(payload), createdAt);

  void notifyHealthAlert(cfg, level, message, payload);

  if (!cfg.monitor.enableSystemMessageTask) return;
  try {
    const taskId = genTaskId("health-alert");
    const sourceId = `health-alert:${ruleKey}:${Date.now()}`;
    const content = `[health_alert] ${message}\npayload=${JSON.stringify(payload)}`;
    const metadata = JSON.stringify({
      created_by: "orchestrator_health_monitor",
      rule_key: ruleKey,
      level,
      health_alert: true,
      payload,
    });
    db.prepare(
      `
      INSERT INTO bl_message_tasks (
        task_id, source, source_id, sender, content, parsed_intent, priority, status, estimated_tokens, metadata
      )
      VALUES (?, 'system', ?, 'system', ?, '/review', 95, 'pending', 200, ?)
    `,
    ).run(taskId, sourceId, content, metadata);
  } catch {
    // Best-effort bridge to task queue.
  }
}

async function notifyHealthAlert(
  cfg: HealthConfig,
  level: "warn" | "bad",
  message: string,
  payload: Record<string, unknown>,
) {
  const header = `[Solar Health Alert][${level.toUpperCase()}]`;
  const content = `${header}\n${message}\n${JSON.stringify(payload, null, 2)}`;

  try {
    if (
      cfg.monitor.notifyTelegramEnabled &&
      cfg.monitor.notifyTelegramChatId.trim()
    ) {
      await notifier.send({
        channel: "telegram",
        recipient: cfg.monitor.notifyTelegramChatId.trim(),
        replyType: "notification",
        content,
      });
    }
  } catch {
    // best effort
  }

  try {
    if (cfg.monitor.notifyEmailEnabled && cfg.monitor.notifyEmailTo.trim()) {
      await notifier.send({
        channel: "gmail",
        recipient: cfg.monitor.notifyEmailTo.trim(),
        replyType: "notification",
        subject: `${header} orchestrator`,
        content,
      });
    }
  } catch {
    // best effort
  }
}

function cleanupHealthSnapshotsAndAlerts(
  db: Database,
  retentionDays: number,
): void {
  const days = Math.max(1, Math.floor(retentionDays || 30));
  db.prepare(
    `
    DELETE FROM bl_orchestrator_health_snapshots
    WHERE sampled_at < datetime('now', ?)
  `,
  ).run(`-${days} days`);
  db.prepare(
    `
    DELETE FROM bl_orchestrator_health_alerts
    WHERE resolved = 1 AND created_at < datetime('now', ?)
  `,
  ).run(`-${days} days`);
}

function getHealthAlerts(limit: number = 50, includeResolved: boolean = false) {
  const db = openSolarDbRW();
  if (!db) return [];
  const n = Math.max(1, Math.min(500, Math.floor(limit || 50)));
  try {
    const rows = db
      .prepare(
        `
      SELECT id, rule_key, level, message, payload_json, created_at, resolved
      FROM bl_orchestrator_health_alerts
      WHERE (? = 1 OR resolved = 0)
      ORDER BY id DESC
      LIMIT ?
    `,
      )
      .all(includeResolved ? 1 : 0, n) as Array<{
      id: number;
      rule_key: string;
      level: "warn" | "bad";
      message: string;
      payload_json: string | null;
      created_at: string;
      resolved: number;
    }>;
    return rows.map((r) => {
      let payload: Record<string, unknown> = {};
      try {
        payload = r.payload_json ? JSON.parse(r.payload_json) : {};
      } catch {
        payload = {};
      }
      return {
        id: r.id,
        ruleKey: r.rule_key,
        level: r.level,
        message: r.message,
        payload,
        createdAt: r.created_at,
        resolved: !!r.resolved,
      };
    });
  } finally {
    db.close();
  }
}

function persistHealthSnapshot(
  summary: ReturnType<typeof getHealthSummary>,
  source: string = "api",
): {
  status: "good" | "warn" | "bad";
  config: HealthConfig;
} {
  const db = openSolarDbRW();
  const cfg = getHealthConfig();
  const statusInfo = calcHealthStatus(summary, cfg);
  if (!db) return { status: statusInfo.status, config: cfg };
  try {
    cleanupHealthSnapshotsAndAlerts(db, cfg.monitor.snapshotRetentionDays);

    db.prepare(
      `
      INSERT INTO bl_orchestrator_health_snapshots (sampled_at, source, status, summary_json, created_at)
      VALUES (?, ?, ?, ?, ?)
    `,
    ).run(
      summary.generatedAt,
      source,
      statusInfo.status,
      JSON.stringify(summary),
      new Date().toISOString(),
    );

    for (const m of statusInfo.metrics) {
      if (m.severity === "good") continue;
      const msg = `[health/${m.key}] severity=${m.severity} value=${m.value} threshold(warn=${m.warn}, bad=${m.bad})`;
      maybeCreateAlertAndTask(
        db,
        cfg,
        `metric:${m.key}:${m.severity}`,
        m.severity,
        msg,
        {
          metric: m.key,
          value: m.value,
          warn: m.warn,
          bad: m.bad,
          sampledAt: summary.generatedAt,
        },
      );
    }
  } finally {
    db.close();
  }
  return { status: statusInfo.status, config: cfg };
}

function getHealthHistory(hours: number = 24) {
  const db = openSolarDbRW();
  const h = Math.max(1, Math.min(168, Math.floor(hours || 24)));
  const sinceIso = toIsoHoursAgo(h);
  const out: Array<{
    hour: string;
    failed: number;
    completed: number;
    retries: number;
    repairs: number;
  }> = [];
  if (!db) return out;

  try {
    const map = new Map<
      string,
      { failed: number; completed: number; retries: number; repairs: number }
    >();
    for (let i = h - 1; i >= 0; i--) {
      const d = new Date(Date.now() - i * 3600000);
      const hour = d.toISOString().slice(0, 13) + ":00";
      map.set(hour, { failed: 0, completed: 0, retries: 0, repairs: 0 });
    }

    const snapshotRows = db
      .prepare(
        `
      SELECT sampled_at, summary_json
      FROM bl_orchestrator_health_snapshots
      WHERE sampled_at >= ?
      ORDER BY sampled_at ASC
    `,
      )
      .all(sinceIso) as Array<{ sampled_at: string; summary_json: string }>;

    if (snapshotRows.length > 0) {
      for (const row of snapshotRows) {
        const hour = String(row.sampled_at || "").slice(0, 13) + ":00";
        const bucket = map.get(hour);
        if (!bucket) continue;
        try {
          const summary = JSON.parse(row.summary_json || "{}");
          bucket.failed = Math.max(
            bucket.failed,
            Number(summary.failureRate?.failed || 0),
          );
          bucket.completed = Math.max(
            bucket.completed,
            Number(summary.failureRate?.completed || 0),
          );
          bucket.retries = Math.max(
            bucket.retries,
            Number(summary.retryingNodes || 0),
          );
          bucket.repairs = Math.max(
            bucket.repairs,
            Number(summary.repairBranchTasks || 0),
          );
        } catch {
          // ignore malformed row
        }
      }
    } else {
      const eventRows = db
        .prepare(
          `
        SELECT strftime('%Y-%m-%dT%H:00', created_at) AS hour, event_type AS type, COUNT(*) AS count
        FROM bl_orchestration_events
        WHERE created_at >= ?
          AND event_type IN ('node_failed', 'node_completed', 'retry_scheduled', 'repair_branch_queued')
        GROUP BY hour, type
        ORDER BY hour ASC
      `,
        )
        .all(sinceIso) as Array<{ hour: string; type: string; count: number }>;

      for (const row of eventRows) {
        const bucket = map.get(row.hour);
        if (!bucket) continue;
        if (row.type === "node_failed") bucket.failed = row.count;
        else if (row.type === "node_completed") bucket.completed = row.count;
        else if (row.type === "retry_scheduled") bucket.retries = row.count;
        else if (row.type === "repair_branch_queued")
          bucket.repairs = row.count;
      }
    }

    for (const [hour, v] of map.entries()) {
      out.push({
        hour,
        failed: v.failed,
        completed: v.completed,
        retries: v.retries,
        repairs: v.repairs,
      });
    }
  } catch {
    // ignore and return partial/empty history
  }

  db.close();
  return out;
}

function getHealthDrilldown(type: "failures" | "repairs", limit: number = 20) {
  const db = openSolarDbRW();
  if (!db) return [];
  const n = Math.max(1, Math.min(200, Math.floor(limit || 20)));
  try {
    if (type === "failures") {
      const rows = db
        .prepare(
          `
        SELECT task_id, node_id, payload_json, created_at
        FROM bl_orchestration_events
        WHERE event_type = 'node_failed'
        ORDER BY id DESC
        LIMIT ?
      `,
        )
        .all(n) as Array<{
        task_id: string;
        node_id: string | null;
        payload_json: string | null;
        created_at: string;
      }>;
      return rows.map((r) => {
        let payload: any = {};
        try {
          payload = r.payload_json ? JSON.parse(r.payload_json) : {};
        } catch {}
        return {
          taskId: r.task_id,
          nodeId: r.node_id || "",
          at: r.created_at,
          error: String(payload.error || ""),
          durationMs: payload.durationMs ?? null,
          branchSuggestion: payload.branchSuggestion ?? null,
        };
      });
    }

    const rows = db
      .prepare(
        `
      SELECT task_id, source_id, metadata, status, created_at
      FROM bl_message_tasks
      WHERE metadata LIKE '%"created_by":"orchestrator_repair_flow"%'
      ORDER BY datetime(created_at) DESC
      LIMIT ?
    `,
      )
      .all(n) as Array<{
      task_id: string;
      source_id: string | null;
      metadata: string | null;
      status: string | null;
      created_at: string | null;
    }>;
    return rows.map((r) => {
      let meta: any = {};
      try {
        meta = r.metadata ? JSON.parse(r.metadata) : {};
      } catch {}
      return {
        repairTaskId: r.task_id,
        sourceId: r.source_id,
        status: r.status,
        createdAt: r.created_at,
        ofTaskId: meta?.repair_of?.taskId || null,
        ofNodeId: meta?.repair_of?.nodeId || null,
        branchSuggestion: meta?.branch_suggestion || null,
      };
    });
  } finally {
    db.close();
  }
}

// 读取状态
async function getState() {
  const file = Bun.file(STATE_FILE);
  if (await file.exists()) {
    return await file.json();
  }
  return JSON.parse(JSON.stringify(DEFAULT_STATE));
}

async function writeState(state: any) {
  mkdirSync(dirname(STATE_FILE), { recursive: true });
  await Bun.write(STATE_FILE, JSON.stringify(state, null, 2));
}

// 更新状态
async function updateState(updates: any) {
  const state = await getState();
  const newState = {
    ...state,
    ...updates,
    lastUpdate: new Date().toISOString(),
  };
  await writeState(newState);
  return newState;
}

// 添加对话
async function addConversation(role: string, content: string) {
  const state = await getState();
  const time = new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const conversations = Array.isArray(state.conversations)
    ? state.conversations
    : [];

  state.conversations = [
    {
      role,
      content: content.slice(0, 100) + (content.length > 100 ? "..." : ""),
      time,
    },
    ...conversations.slice(0, 19),
  ];

  await writeState(state);
  return state;
}

// 添加/更新任务
async function updateTask(task: any) {
  const state = await getState();
  const tasks = Array.isArray(state.tasks) ? state.tasks : [];

  // 将其他 in_progress 任务标记为 completed
  state.tasks = tasks.map((t: any) =>
    t.status === "in_progress" && t.id !== task.id
      ? { ...t, status: "completed" }
      : t,
  );

  // 添加或更新任务
  const existingIndex = state.tasks.findIndex((t: any) => t.id === task.id);
  if (existingIndex >= 0) {
    state.tasks[existingIndex] = task;
  } else {
    state.tasks = [task, ...state.tasks.slice(0, 4)];
  }

  state.lastUpdate = new Date().toISOString();
  await writeState(state);
  return state;
}

async function daemonGet(path: string) {
  const proc = Bun.spawn(
    [
      "curl",
      "--silent",
      "--show-error",
      "--unix-socket",
      DAEMON_SOCKET,
      `http://localhost${path}`,
    ],
    { stdout: "pipe", stderr: "pipe" },
  );
  const [stdout, stderr, exit] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]);
  if (exit !== 0) {
    throw new Error(stderr || stdout || "daemon request failed");
  }
  return JSON.parse(stdout || "{}");
}

async function daemonPost(path: string, body: any) {
  const proc = Bun.spawn(
    [
      "curl",
      "--silent",
      "--show-error",
      "--unix-socket",
      DAEMON_SOCKET,
      "-H",
      "content-type: application/json",
      "-X",
      "POST",
      "-d",
      JSON.stringify(body),
      `http://localhost${path}`,
    ],
    { stdout: "pipe", stderr: "pipe" },
  );
  const [stdout, stderr, exit] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]);
  if (exit !== 0) {
    throw new Error(stderr || stdout || "daemon request failed");
  }
  return JSON.parse(stdout || "{}");
}

initHealthInfra();

const server = Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);

    // CORS headers
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (req.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // API: 获取状态
    if (url.pathname === "/api/state") {
      const state = await getState();
      return Response.json(state, { headers: corsHeaders });
    }

    // API: 更新状态
    if (url.pathname === "/api/update" && req.method === "POST") {
      const updates = await req.json();
      const state = await updateState(updates);
      return Response.json(state, { headers: corsHeaders });
    }

    // API: 添加对话
    if (url.pathname === "/api/conversation" && req.method === "POST") {
      const { role, content } = await req.json();
      const state = await addConversation(role, content);
      return Response.json(state, { headers: corsHeaders });
    }

    // API: 更新任务
    if (url.pathname === "/api/task" && req.method === "POST") {
      const task = await req.json();
      const state = await updateTask(task);
      return Response.json(state, { headers: corsHeaders });
    }

    // Orchestrator API: events
    if (url.pathname === "/api/orchestrator/events" && req.method === "GET") {
      const limit = parseInt(url.searchParams.get("limit") || "100");
      const taskId = url.searchParams.get("taskId") || "";
      const type = url.searchParams.get("type") || "";
      const since = url.searchParams.get("since") || "";
      const query = new URLSearchParams();
      query.set("limit", String(limit));
      if (taskId) query.set("taskId", taskId);
      if (type) query.set("type", type);
      if (since) query.set("since", since);
      try {
        const data = await daemonGet(
          `/orchestrator/events?${query.toString()}`,
        );
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // Orchestrator API: state
    if (url.pathname === "/api/orchestrator/state" && req.method === "GET") {
      try {
        const data = await daemonGet("/orchestrator/state");
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // Orchestrator API: task list
    if (url.pathname === "/api/orchestrator/tasks" && req.method === "GET") {
      const limit = parseInt(url.searchParams.get("limit") || "50");
      try {
        const data = await daemonGet(`/orchestrator/tasks?limit=${limit}`);
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // Orchestrator API: health summary
    if (
      url.pathname === "/api/orchestrator/health-summary" &&
      req.method === "GET"
    ) {
      try {
        const data = getHealthSummary();
        const persisted = persistHealthSnapshot(data, "api");
        (data as any).healthStatus = persisted.status;
        (data as any).config = persisted.config;
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 500 },
        );
      }
    }

    // Orchestrator API: health config
    if (
      url.pathname === "/api/orchestrator/health-config" &&
      req.method === "GET"
    ) {
      try {
        const data = getHealthConfig();
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 500 },
        );
      }
    }

    if (
      url.pathname === "/api/orchestrator/health-config" &&
      req.method === "POST"
    ) {
      try {
        const payload = (await req.json()) as Partial<HealthConfig>;
        const data = updateHealthConfig(payload);
        startHealthMonitor();
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 500 },
        );
      }
    }

    // Orchestrator API: health history
    if (
      url.pathname === "/api/orchestrator/health-history" &&
      req.method === "GET"
    ) {
      try {
        const hours = parseInt(url.searchParams.get("hours") || "24");
        const data = getHealthHistory(hours);
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 500 },
        );
      }
    }

    if (
      url.pathname === "/api/orchestrator/health-drilldown" &&
      req.method === "GET"
    ) {
      try {
        const t = (url.searchParams.get("type") || "failures").toLowerCase();
        const type = t === "repairs" ? "repairs" : "failures";
        const limit = parseInt(url.searchParams.get("limit") || "20");
        const data = getHealthDrilldown(type, limit);
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 500 },
        );
      }
    }

    if (
      url.pathname === "/api/orchestrator/health-alerts" &&
      req.method === "GET"
    ) {
      try {
        const limit = parseInt(url.searchParams.get("limit") || "50");
        const includeResolved = url.searchParams.get("includeResolved") === "1";
        const data = getHealthAlerts(limit, includeResolved);
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 500 },
        );
      }
    }

    if (
      url.pathname === "/api/orchestrator/health-actions/retry" &&
      req.method === "POST"
    ) {
      try {
        const body = (await req.json()) as { taskId?: string; nodeId?: string };
        if (!body.taskId || !body.nodeId) {
          return Response.json(
            { ok: false, error: "taskId and nodeId are required" },
            { headers: corsHeaders, status: 400 },
          );
        }
        const data = await daemonPost("/orchestrator/control", {
          action: "retry",
          taskId: body.taskId,
          nodeId: body.nodeId,
        });
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    if (
      url.pathname === "/api/orchestrator/health-actions/repair" &&
      req.method === "POST"
    ) {
      try {
        const body = (await req.json()) as {
          taskId?: string;
          nodeId?: string;
          error?: string;
          branchSuggestion?: string;
        };
        if (!body.taskId || !body.nodeId) {
          return Response.json(
            { ok: false, error: "taskId and nodeId are required" },
            { headers: corsHeaders, status: 400 },
          );
        }
        const data = await daemonPost("/orchestrator/control", {
          action: "repair",
          taskId: body.taskId,
          nodeId: body.nodeId,
          error: body.error,
          target: body.branchSuggestion,
        });
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // Orchestrator API: graph by taskId
    if (url.pathname === "/api/orchestrator/graph" && req.method === "GET") {
      const taskId = url.searchParams.get("taskId") || "";
      if (!taskId) {
        return Response.json(
          { ok: false, error: "taskId is required" },
          { headers: corsHeaders, status: 400 },
        );
      }
      try {
        const data = await daemonGet(
          `/orchestrator/graph?taskId=${encodeURIComponent(taskId)}`,
        );
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // Orchestrator API: diagnostics by taskId
    if (
      url.pathname === "/api/orchestrator/diagnostics" &&
      req.method === "GET"
    ) {
      const taskId = url.searchParams.get("taskId") || "";
      if (!taskId) {
        return Response.json(
          { ok: false, error: "taskId is required" },
          { headers: corsHeaders, status: 400 },
        );
      }
      try {
        const data = await daemonGet(
          `/orchestrator/diagnostics?taskId=${encodeURIComponent(taskId)}`,
        );
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // Orchestrator API: retry policy
    if (
      url.pathname === "/api/orchestrator/retry-policy" &&
      req.method === "GET"
    ) {
      try {
        const data = await daemonGet("/orchestrator/retry-policy");
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    if (
      url.pathname === "/api/orchestrator/retry-policy" &&
      req.method === "POST"
    ) {
      try {
        const payload = await req.json();
        const data = await daemonPost("/orchestrator/retry-policy", payload);
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // Orchestrator API: control
    if (url.pathname === "/api/orchestrator/control" && req.method === "POST") {
      try {
        const payload = await req.json();
        const data = await daemonPost("/orchestrator/control", payload);
        return Response.json({ ok: true, data }, { headers: corsHeaders });
      } catch (error) {
        return Response.json(
          {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
          },
          { headers: corsHeaders, status: 502 },
        );
      }
    }

    // S04: /research/:sid — proxy to status-server
    const researchMatch = url.pathname.match(/^\/research\/(.+)$/);
    if (researchMatch) {
      const sid = researchMatch[1];
      const statusServerPort = Number(process.env.STATUS_SERVER_PORT || 8765);
      const upstreamUrl = `http://127.0.0.1:${statusServerPort}/research/${encodeURIComponent(sid)}`;
      try {
        const upstream = await fetch(upstreamUrl, {
          signal: AbortSignal.timeout(10000),
        });
        const body = await upstream.text();
        return new Response(body, {
          status: upstream.status,
          headers: {
            ...corsHeaders,
            "Content-Type":
              upstream.headers.get("Content-Type") || "application/json",
          },
        });
      } catch (err) {
        return Response.json(
          {
            ok: false,
            error: "status-server unavailable",
            detail: err instanceof Error ? err.message : String(err),
          },
          { headers: corsHeaders, status: 503 },
        );
      }
    }

    // Root, legacy /dashboard, and /orchestrator all serve the real,
    // data-bound orchestrator page. The old "/" page (solar-dashboard.html)
    // shipped hardcoded demo metrics (-91% token usage, "13 Agents", a
    // competitor table) over otherwise-empty state; it was a placeholder, not
    // a real surface, so it has been removed rather than fronted as live.
    if (
      url.pathname === "/" ||
      url.pathname === "/dashboard" ||
      url.pathname === "/orchestrator"
    ) {
      return new Response(ORCH_DASHBOARD_FILE, {
        headers: { "Content-Type": "text/html" },
      });
    }

    return new Response("Not Found", { status: 404 });
  },
});

let monitorTimer: Timer | null = null;
function startHealthMonitor() {
  if (monitorTimer) clearInterval(monitorTimer);
  const cfg = getHealthConfig();
  const intervalMs = Math.max(10, cfg.monitor.intervalSeconds) * 1000;
  monitorTimer = setInterval(() => {
    try {
      const summary = getHealthSummary();
      persistHealthSnapshot(summary, "monitor");
    } catch {
      // keep monitor alive even if a cycle fails
    }
  }, intervalMs);
}
startHealthMonitor();

console.log(`
┌─ ☀️ Solar Dashboard Server ─────────────────────────────────────┐
│                                                                 │
│  URL: http://localhost:${PORT}                                    │
│  Orchestrator: http://localhost:${PORT}/orchestrator              │
│                                                                 │
│  Endpoints:                                                     │
│    GET  /              Dashboard 页面                           │
│    GET  /orchestrator   Orchestrator 面板                       │
│    GET  /api/state     获取当前状态                             │
│    POST /api/update    更新状态                                 │
│    POST /api/conversation  添加对话                             │
│    POST /api/task      更新任务                                 │
│    GET  /api/orchestrator/events                                │
│    GET  /api/orchestrator/state                                 │
│    GET  /api/orchestrator/tasks                                 │
│    GET  /api/orchestrator/health-summary                        │
│    GET  /api/orchestrator/health-config                         │
│    POST /api/orchestrator/health-config                         │
│    GET  /api/orchestrator/health-history                        │
│    GET  /api/orchestrator/health-drilldown                      │
│    GET  /api/orchestrator/health-alerts                         │
│    POST /api/orchestrator/health-actions/retry                  │
│    POST /api/orchestrator/health-actions/repair                 │
│    GET  /api/orchestrator/graph                                 │
│    GET  /api/orchestrator/diagnostics                           │
│    GET  /api/orchestrator/retry-policy                          │
│    POST /api/orchestrator/retry-policy                          │
│    POST /api/orchestrator/control                               │
│                                                                 │
│  刷新周期: 3秒 (页面自动刷新)                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
`);
