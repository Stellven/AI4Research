/**
 * Solar Harness — Webhook 触发器
 *
 * 轻量 HTTP server，接收外部请求并只写 RawIntent
 *
 * 启动: bun ~/.solar/harness/webhook-server.ts
 * 端口: 9876 (可通过 HARNESS_PORT 环境变量修改)
 *
 * API:
 *   POST /sprint         — 捕获 RawIntent（兼容旧路径，不直接建 Sprint）
 *   POST /sprint/status  — 更新 Sprint 状态
 *   GET  /status          — 查看当前状态
 *   GET  /health          — 健康检查
 *
 * 触发方式:
 *   curl -X POST localhost:9876/sprint -d '{"title":"实现XX功能","description":"详细描述"}'
 *   Slack webhook → 转发到本 server
 *   GitHub webhook (issue created) → 捕获 RawIntent
 */

import { execFileSync, execSync } from "child_process";
import { readFileSync, existsSync, readdirSync } from "fs";

const PORT = parseInt(process.env.HARNESS_PORT || "9876");
const HARNESS_DIR = `${process.env.HOME}/.solar/harness`;
const SPRINTS_DIR = `${HARNESS_DIR}/sprints`;
const SESSION_NAME = "solar-harness";

// --- Helpers ---

type IntentCapture = {
  ok: boolean;
  intent_id?: string;
  title?: string;
  lane?: string;
  rewrite_method?: string;
  raw_intent?: string;
  rewritten_intent?: string;
  requirement_ir?: string;
  requirement_trace?: string;
  error?: string;
};

function getLatestSprint(): { id: string; status: string; title: string; round: number } | null {
  const files = readdirSync(SPRINTS_DIR).filter(f => f.endsWith(".status.json")).sort();
  if (files.length === 0) return null;
  const data = JSON.parse(readFileSync(`${SPRINTS_DIR}/${files[files.length - 1]}`, "utf-8"));
  return data;
}

function captureRawIntent(
  title: string,
  description: string,
  sourceChannel: string,
  sourceTrust: string,
  threadRef = "",
): IntentCapture {
  const text = (description || title || "Untitled Intent").trim();
  const args = [
    `${HARNESS_DIR}/lib/intent_gateway.py`,
    "capture",
    "--source-channel", sourceChannel,
    "--actor", "user",
    "--device", "mac_mini_webhook",
    "--repo", HARNESS_DIR,
    "--source-trust", sourceTrust,
    "--thread-ref", threadRef,
    "--text", text,
    "--json",
  ];
  const output = execFileSync("python3", args, { encoding: "utf-8", timeout: 15000 });
  const payload = JSON.parse(output) as IntentCapture;
  if (payload.intent_id) {
    const consumerOutput = execFileSync(
      "python3",
      [`${HARNESS_DIR}/lib/intent_consumer.py`, "consume", "--intent-id", payload.intent_id, "--json"],
      { encoding: "utf-8", timeout: 120000 }
    );
    (payload as any).consumer = JSON.parse(consumerOutput);
  }
  return payload;
}

// --- Server ---

const server = Bun.serve({
  port: PORT,

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const headers = { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" };

    // CORS preflight
    if (req.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...headers, "Access-Control-Allow-Methods": "GET,POST", "Access-Control-Allow-Headers": "Content-Type" } });
    }

    // GET /health
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", port: PORT }), { headers });
    }

    // GET /status
    if (url.pathname === "/status" && req.method === "GET") {
      const sprint = getLatestSprint();
      const tmuxRunning = (() => {
        try { execSync(`tmux has-session -t ${SESSION_NAME}`, { timeout: 2000 }); return true; } catch { return false; }
      })();
      return new Response(JSON.stringify({ harness_running: tmuxRunning, current_sprint: sprint }), { headers });
    }

    // POST /sprint — 捕获 RawIntent（兼容旧路径）
    if (url.pathname === "/sprint" && req.method === "POST") {
      try {
        const body = await req.json() as { title?: string; description?: string; text?: string; source_channel?: string; thread_ref?: string };

        // 支持多种格式: {title, description} 或 Slack 格式 {text}
        const title = body.title || body.text || "Untitled Sprint";
        const description = body.description || body.text || title;

        const intent = captureRawIntent(title, description, body.source_channel || "webhook", "webhook", body.thread_ref || "");
        return new Response(JSON.stringify({ ok: true, intent_id: intent.intent_id, title: intent.title, lane: intent.lane, artifacts: intent, message: `RawIntent captured: ${intent.intent_id}` }), { headers });
      } catch (e: any) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 400, headers });
      }
    }


    // POST /intent or /mobile — 捕获 RawIntent（mobile/webhook 原生入口）
    if ((url.pathname === "/intent" || url.pathname === "/mobile") && req.method === "POST") {
      try {
        const body = await req.json() as { title?: string; description?: string; text?: string; source_channel?: string; thread_ref?: string };
        const title = body.title || body.text || "Untitled Intent";
        const description = body.description || body.text || title;
        const source = body.source_channel || (url.pathname === "/mobile" ? "mobile_webhook" : "webhook");
        const intent = captureRawIntent(title, description, source, source, body.thread_ref || "");
        return new Response(JSON.stringify({ ok: true, intent_id: intent.intent_id, title: intent.title, lane: intent.lane, artifacts: intent }), { headers });
      } catch (e: any) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 400, headers });
      }
    }

    // POST /sprint/status — 更新状态 (外部控制)
    if (url.pathname === "/sprint/status" && req.method === "POST") {
      try {
        const body = await req.json() as { sprint_id?: string; status: string };
        const sprint = getLatestSprint();
        const sid = body.sprint_id || sprint?.id;
        if (!sid) return new Response(JSON.stringify({ ok: false, error: "no sprint found" }), { status: 404, headers });

        const sf = `${SPRINTS_DIR}/${sid}.status.json`;
        if (!existsSync(sf)) return new Response(JSON.stringify({ ok: false, error: "sprint not found" }), { status: 404, headers });

        const data = JSON.parse(readFileSync(sf, "utf-8"));
        data.status = body.status;
        data.updated_at = new Date().toISOString();
        data.history.push({ ts: data.updated_at, event: `status_changed_to_${body.status}`, by: "webhook" });
        writeFileSync(sf, JSON.stringify(data, null, 2));

        return new Response(JSON.stringify({ ok: true, sprint_id: sid, status: body.status }), { headers });
      } catch (e: any) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 400, headers });
      }
    }

    // POST /github — GitHub webhook (issue opened)
    if (url.pathname === "/github" && req.method === "POST") {
      try {
        const body = await req.json() as any;
        if (body.action === "opened" && body.issue) {
          const title = body.issue.title;
          const description = `${body.issue.title}\n\n${body.issue.body || ""}\n\nSource: ${body.issue.html_url}`;
          const intent = captureRawIntent(title, description, "github_webhook", "github_webhook", body.issue.html_url || "");
          return new Response(JSON.stringify({ ok: true, intent_id: intent.intent_id, artifacts: intent }), { headers });
        }
        return new Response(JSON.stringify({ ok: true, skipped: true, reason: "not an issue.opened event" }), { headers });
      } catch (e: any) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 400, headers });
      }
    }

    return new Response(JSON.stringify({ error: "not found" }), { status: 404, headers });
  },
});

console.log(`Solar Harness Webhook Server listening on http://localhost:${PORT}`);
console.log(`  POST /sprint         — 捕获 RawIntent`);
console.log(`  POST /sprint/status  — 更新状态`);
console.log(`  POST /github         — GitHub issue RawIntent`);
console.log(`  GET  /status         — 查看状态`);
console.log(`  GET  /health         — 健康检查`);
